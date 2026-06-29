#!/usr/bin/env python3
"""
AI4RSE — Batch API evaluator (best-cost path).

Submits all remaining concepts as a SINGLE asynchronous Gemini Batch job
(50% off standard rates) where every inline request references an explicit
context cache holding the system instruction (cached-input rate on the big
taxonomy prompt). The two discounts stack: cheap cached input + halved output,
and the server-side batch queue removes the 503/429 retry churn entirely.

Because the system instruction lives in the cache, each inline request only
carries its own ~1k-token concept payload — so the whole job stays tiny.

Run from the prompt-browser/ directory:

    ../.venv/bin/python batch_submit.py submit            # submit remaining concepts
    ../.venv/bin/python batch_submit.py submit --limit 40 # small test (2 batches) first
    ../.venv/bin/python batch_submit.py poll              # check status; ingest when done
    ../.venv/bin/python batch_submit.py submit --poll     # submit then block until done
    ../.venv/bin/python batch_submit.py status            # raw job state
    ../.venv/bin/python batch_submit.py cancel            # cancel the saved job
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime

from backend.config import (
    MODEL, BATCH_SIZE, CACHE_DISPLAY_NAME, RESPONSE_SCHEMA, build_system_instruction,
)
from backend.db import get_db
from backend.gemini_client import get_gemini_client

# Batch-tier prices ($/1M): cached-input, new-input, output. Used only for the
# rough cost line printed after ingest.
BATCH_PRICES = {
    "gemini-2.5-flash": (0.03, 0.15, 1.25),
    "gemini-3.5-flash": (0.075, 0.75, 4.50),
}

# Cache must outlive the async job (batch SLA is up to 24h). We delete it the
# instant the job reaches a terminal state, so storage is billed for real
# elapsed time, not this ceiling.
BATCH_CACHE_TTL = "86400s"  # 24h ceiling
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "batch_job_state.json")

TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
    "JOB_STATE_PARTIALLY_SUCCEEDED",
}


def _log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)


def _load_state():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_prompt_id(conn, prompt_id):
    if prompt_id is not None:
        return int(prompt_id)
    row = conn.execute(
        "SELECT id FROM system_prompts WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT id FROM system_prompts ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        raise SystemExit("❌ No system prompts found in the database.")
    return row["id"]


# ─── Submit ─────────────────────────────────────────────────────────
def submit(prompt_id=None, limit=None, run_mode="batch_api", use_cache=True,
           all_concepts=False, target_name=None):
    from google.genai import types

    existing = _load_state()
    if existing and not existing.get("ingested"):
        raise SystemExit(
            f"❌ A batch job is already tracked ({existing['job_name']}, "
            f"state={existing.get('last_state')}). Run `poll` or `cancel` first, "
            f"or delete {STATE_FILE}."
        )

    conn = get_db()
    client = get_gemini_client()

    prompt_id = _resolve_prompt_id(conn, prompt_id)
    prompt_row = conn.execute(
        "SELECT name, content FROM system_prompts WHERE id = ?", (prompt_id,)
    ).fetchone()
    if not prompt_row:
        raise SystemExit(f"❌ System prompt {prompt_id} not found.")
    system_instruction = build_system_instruction(prompt_row["content"])

    # --all clones the source prompt into a fresh row so existing results
    # (e.g. the Gemini 2.5 run) are preserved; this run is a clean dataset.
    if all_concepts:
        from backend.db import create_system_prompt
        clone_name = target_name or f"{prompt_row['name']} · Gemini {MODEL}"
        write_prompt_id = create_system_prompt(clone_name, prompt_row["content"])
        _log(f"🧬 Cloned prompt {prompt_id} -> new prompt {write_prompt_id} ({clone_name!r}). "
             f"Existing rows untouched.")
    else:
        write_prompt_id = prompt_id

    # Concepts not yet evaluated under the WRITE prompt (resume-safe).
    evaluated = {
        r["global_index"]
        for r in conn.execute(
            """SELECT c.global_index FROM evaluation_results e
               JOIN concepts c ON c.id = e.concept_id
               WHERE e.system_prompt_id = ?""",
            (write_prompt_id,),
        ).fetchall()
    }
    all_rows = conn.execute(
        """SELECT id, global_index, concept_name, concept_definition, low_level
           FROM concepts ORDER BY global_index"""
    ).fetchall()
    remaining = [dict(c) for c in all_rows if c["global_index"] not in evaluated]

    if not remaining:
        conn.close()
        _log("✅ Nothing to do — all concepts already evaluated for this prompt.")
        return
    if limit:
        remaining = remaining[: int(limit)]

    # Chunk into batches of BATCH_SIZE.
    batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    _log(f"📊 source prompt {prompt_id} -> write prompt {write_prompt_id} | model {MODEL} | "
         f"{len(remaining)} concepts -> {len(batches)} inline requests (batch size {BATCH_SIZE})")

    # ── Explicit cache for the system instruction ──
    cache_name = None
    if use_cache:
        _log(f"🗄️  Creating context cache (TTL ceiling {BATCH_CACHE_TTL})...")
        cache = client.caches.create(
            model=MODEL,
            config=types.CreateCachedContentConfig(
                display_name=CACHE_DISPLAY_NAME,
                system_instruction=system_instruction,
                ttl=BATCH_CACHE_TTL,
            ),
        )
        cache_name = cache.name
        _log(f"   ✅ Cache: {cache_name}")

    # ── Build inline requests. System prompt is in the cache (or inline if --no-cache). ──
    inlined = []
    index_map = {}  # batch_index -> [concept_id,...] for writing results back
    for idx, batch in enumerate(batches):
        user_message = json.dumps(
            [
                {
                    "concept_name": c["concept_name"],
                    "definition": c["concept_definition"] or "",
                    "current_low_level": c["low_level"] or "",
                }
                for c in batch
            ],
            ensure_ascii=False,
        )
        cfg = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            temperature=0.1,
        )
        if cache_name:
            cfg.cached_content = cache_name
        else:
            cfg.system_instruction = system_instruction

        inlined.append(
            types.InlinedRequest(
                model=MODEL,
                contents=user_message,
                metadata={"batch_index": str(idx)},
                config=cfg,
            )
        )
        index_map[str(idx)] = [c["id"] for c in batch]

    # ── Create the batch job ──
    _log("🚀 Submitting batch job...")
    job = client.batches.create(
        model=MODEL,
        src=inlined,
        config=types.CreateBatchJobConfig(display_name=CACHE_DISPLAY_NAME + "-batch"),
    )
    _log(f"   ✅ Job: {job.name} (state={job.state})")

    _save_state({
        "job_name": job.name,
        "cache_name": cache_name,
        "system_prompt_id": write_prompt_id,
        "source_prompt_id": prompt_id,
        "run_mode": run_mode,
        "index_map": index_map,
        "total_requests": len(inlined),
        "last_state": str(job.state),
        "ingested": False,
        "submitted_at": datetime.now().isoformat(),
    })
    conn.close()
    _log(f"💾 Saved job state -> {STATE_FILE}")
    _log("ℹ️  Run `poll` to check status and ingest results when done.")


# ─── Poll & ingest ──────────────────────────────────────────────────
def _state_name(state):
    # state may be an enum or a plain string depending on SDK path.
    return getattr(state, "name", str(state))


def poll(block=False, interval=30):
    client = get_gemini_client()
    state = _load_state()
    if not state:
        raise SystemExit("❌ No saved batch job. Run `submit` first.")
    if state.get("ingested"):
        _log("✅ This job's results were already ingested. Nothing to do.")
        return

    job_name = state["job_name"]
    while True:
        job = client.batches.get(name=job_name)
        sname = _state_name(job.state)
        state["last_state"] = sname
        _save_state(state)
        _log(f"📡 {job_name} -> {sname}")

        if sname in TERMINAL_STATES:
            _ingest(client, job, state)
            return
        if not block:
            _log("ℹ️  Still running. Re-run `poll` later, or use `--poll` to block.")
            return
        time.sleep(interval)


def _ingest(client, job, state):
    if _state_name(job.state) == "JOB_STATE_FAILED":
        _log(f"💥 Job FAILED: {getattr(job, 'error', None)}")
        if state.get("cache_name"):
            _cleanup_cache(client, state["cache_name"])
        return

    dest = getattr(job, "dest", None)
    responses = getattr(dest, "inlined_responses", None) if dest else None
    if not responses:
        _log("⚠️  No inline responses on the job. Nothing to ingest.")
        if state.get("cache_name"):
            _cleanup_cache(client, state["cache_name"])
        return

    index_map = state["index_map"]
    prompt_id = state["system_prompt_id"]
    run_mode = state.get("run_mode", "batch_api")
    conn = get_db()

    tot_cached = tot_new = tot_out = 0
    ok = failed = written = 0
    timestamp = datetime.now().isoformat()

    for i, resp in enumerate(responses):
        # Prefer explicit metadata; fall back to positional order.
        meta = getattr(resp, "metadata", None) or {}
        bidx = meta.get("batch_index", str(i))
        concept_ids = index_map.get(bidx) or index_map.get(str(i))
        if concept_ids is None:
            _log(f"   ⚠️  Response {i}: no concept mapping; skipping.")
            failed += 1
            continue

        if getattr(resp, "error", None):
            _log(f"   ❌ Request {bidx} errored: {str(resp.error)[:120]}")
            failed += 1
            continue

        gresp = resp.response
        try:
            parsed = json.loads(gresp.text)
            results = parsed["results"]
        except Exception as e:
            _log(f"   ❌ Request {bidx}: bad JSON ({str(e)[:80]})")
            failed += 1
            continue

        um = getattr(gresp, "usage_metadata", None)
        if um:
            c = getattr(um, "cached_content_token_count", 0) or 0
            p = getattr(um, "prompt_token_count", 0) or 0
            o = getattr(um, "candidates_token_count", 0) or 0
            tot_cached += c
            tot_new += max(0, p - c)
            tot_out += o

        for j, res in enumerate(results):
            if j < len(concept_ids):
                conn.execute(
                    """INSERT INTO evaluation_results
                       (concept_id, system_prompt_id, issue, phantom_category,
                        suggested_low_level, confidence, reasoning, timestamp,
                        run_mode, batch_index)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        concept_ids[j],
                        prompt_id,
                        res.get("issue", ""),
                        1 if res.get("phantom_category") else 0,
                        res.get("suggested_low_level", ""),
                        res.get("confidence", 0.0),
                        res.get("reasoning", ""),
                        timestamp,
                        run_mode,
                        int(bidx),
                    ),
                )
                written += 1
        ok += 1

    conn.commit()
    conn.close()

    state["ingested"] = True
    _save_state(state)

    _log("─" * 60)
    _log(f"✅ Ingested {written} results from {ok} requests ({failed} failed).")
    _log(f"📊 Tokens — cached: {tot_cached:,} | new: {tot_new:,} | output: {tot_out:,}")
    if tot_cached > 0:
        _log("   ✔️  Cache discount IS applying inside batch (cached > 0).")
    else:
        _log("   ⚠️  cached == 0 — the cache did NOT apply in batch; you paid batch-rate input only.")
    # Model-aware batch pricing.
    pc, pn, po = BATCH_PRICES.get(MODEL, (0.03, 0.15, 1.25))
    est = tot_cached / 1e6 * pc + tot_new / 1e6 * pn + tot_out / 1e6 * po
    _log(f"💵 Rough {MODEL} batch-rate estimate (verify against console): ${est:.2f}")
    _log("─" * 60)

    if state.get("cache_name"):
        _cleanup_cache(client, state["cache_name"])


def _cleanup_cache(client, cache_name):
    try:
        client.caches.delete(name=cache_name)
        _log(f"🗑️  Cache deleted: {cache_name}")
    except Exception as e:
        _log(f"⚠️  Failed to delete cache {cache_name}: {str(e)[:100]}")


# ─── Status / cancel ────────────────────────────────────────────────
def status():
    client = get_gemini_client()
    st = _load_state()
    if not st:
        raise SystemExit("❌ No saved batch job.")
    job = client.batches.get(name=st["job_name"])
    _log(f"Job:    {job.name}")
    _log(f"State:  {_state_name(job.state)}")
    _log(f"Model:  {getattr(job, 'model', '?')}")
    _log(f"Reqs:   {st.get('total_requests')}")
    _log(f"Cache:  {st.get('cache_name')}")
    _log(f"Ingest: {st.get('ingested')}")
    if getattr(job, "error", None):
        _log(f"Error:  {job.error}")


def cancel():
    client = get_gemini_client()
    st = _load_state()
    if not st:
        raise SystemExit("❌ No saved batch job.")
    client.batches.cancel(name=st["job_name"])
    _log(f"🛑 Cancel requested for {st['job_name']}.")
    if st.get("cache_name"):
        _cleanup_cache(client, st["cache_name"])


def main():
    ap = argparse.ArgumentParser(description="Gemini Batch API evaluator (cache + batch).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("submit", help="Submit remaining concepts as one batch job.")
    s.add_argument("--prompt-id", type=int, default=None, help="System prompt id (default: active).")
    s.add_argument("--limit", type=int, default=None, help="Cap concepts (use for a small test).")
    s.add_argument("--no-cache", action="store_true", help="Don't use explicit cache (comparison).")
    s.add_argument("--all", dest="all_concepts", action="store_true",
                   help="Re-evaluate ALL concepts under a fresh cloned prompt (keeps existing rows).")
    s.add_argument("--target-name", default=None,
                   help="Name for the cloned prompt created by --all.")
    s.add_argument("--poll", action="store_true", help="Block and poll until the job finishes.")

    p = sub.add_parser("poll", help="Check status; ingest results if finished.")
    p.add_argument("--block", action="store_true", help="Loop until terminal state.")
    p.add_argument("--interval", type=int, default=30, help="Poll interval seconds (with --block).")

    sub.add_parser("status", help="Print raw job state.")
    sub.add_parser("cancel", help="Cancel the saved job and clean up its cache.")

    args = ap.parse_args()
    if args.cmd == "submit":
        submit(prompt_id=args.prompt_id, limit=args.limit, use_cache=not args.no_cache,
               all_concepts=args.all_concepts, target_name=args.target_name)
        if args.poll:
            poll(block=True)
    elif args.cmd == "poll":
        poll(block=args.block, interval=args.interval)
    elif args.cmd == "status":
        status()
    elif args.cmd == "cancel":
        cancel()


if __name__ == "__main__":
    main()
