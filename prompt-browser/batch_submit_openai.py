#!/usr/bin/env python3
"""
AI4RSE — OpenAI Batch API evaluator (auto-chunked sequential).

Submits concepts as sequential chunked Batch jobs — each chunk stays under
the org-wide 2M enqueued-token limit. Fully automatic: submit chunk, poll
until done, ingest, submit next chunk. One command, walk away.

If interrupted (close lid, Ctrl-C), just run `resume` to continue.

    ../.venv/bin/python batch_submit_openai.py submit --all
    ../.venv/bin/python batch_submit_openai.py resume          # after interruption
    ../.venv/bin/python batch_submit_openai.py status
    ../.venv/bin/python batch_submit_openai.py cancel
"""

import os
import json
import copy
import time
import tempfile
import argparse
from datetime import datetime

from backend.config import (
    BATCH_SIZE, RESPONSE_SCHEMA, build_system_instruction, ENV_FILE,
)
from backend.db import get_db

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openai_batch_state.json")
SCHEMA_NAME = "taxonomy_eval"

TERMINAL_STATES = {"completed", "failed", "expired", "cancelled"}
NO_TEMPERATURE_MODELS = {"gpt-5-mini", "gpt-5-nano", "gpt-5", "o1", "o1-mini", "o3", "o3-mini", "o4-mini"}

# Org-wide enqueued limit is 2M tokens. Enqueued count = input + RESERVED output
# per request. Input ≈ 49k, reserved output capped at MAX_OUTPUT_TOKENS below.
# 25 × (49k + 4k) ≈ 1.33M — safe margin under 2M.
MAX_REQUESTS_PER_CHUNK = 25
# 20 concepts produce ~1-2k output tokens; 4k is ample and shrinks the reservation.
MAX_OUTPUT_TOKENS = 4000

PRICE_IN, PRICE_CACHED, PRICE_OUT = 0.10, 0.01, 0.40


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


def get_openai_client():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
    except ImportError:
        pass
    api_key = os.getenv("OPENAI_API") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("❌ OPENAI_API not set. Add to .env: OPENAI_API=sk-...")
    from openai import OpenAI
    return OpenAI(api_key=api_key)


def _strict_schema(schema):
    s = copy.deepcopy(schema)
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node.setdefault("additionalProperties", False)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(s)
    return s


def _resolve_prompt_id(conn, prompt_id):
    if prompt_id is not None:
        return int(prompt_id)
    row = conn.execute(
        "SELECT id FROM system_prompts WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        row = conn.execute("SELECT id FROM system_prompts ORDER BY created_at DESC LIMIT 1").fetchone()
    if not row:
        raise SystemExit("❌ No system prompts found.")
    return row["id"]


def _get_remaining(conn, write_prompt_id):
    all_rows = conn.execute(
        """SELECT id, global_index, concept_name, concept_definition, low_level
           FROM concepts ORDER BY global_index"""
    ).fetchall()
    evaluated = {
        r["global_index"]
        for r in conn.execute(
            """SELECT c.global_index FROM evaluation_results e
               JOIN concepts c ON c.id = e.concept_id
               WHERE e.system_prompt_id = ?""",
            (write_prompt_id,),
        ).fetchall()
    }
    return [dict(c) for c in all_rows if c["global_index"] not in evaluated]


def _submit_one_chunk(client, chunk_batches, system_instruction, strict_schema, write_prompt_id, chunk_num, total_chunks):
    index_map = {}
    lines = []
    for idx, batch in enumerate(chunk_batches):
        user_message = json.dumps(
            [{"concept_name": c["concept_name"],
              "definition": c["concept_definition"] or "",
              "current_low_level": c["low_level"] or ""}
             for c in batch],
            ensure_ascii=False,
        )
        custom_id = f"batch-{idx}"
        index_map[custom_id] = [c["id"] for c in batch]
        body = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_message},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": SCHEMA_NAME, "strict": True, "schema": strict_schema},
            },
            "max_completion_tokens": MAX_OUTPUT_TOKENS,
        }
        if MODEL not in NO_TEMPERATURE_MODELS:
            body["temperature"] = 0.1
        lines.append(json.dumps({"custom_id": custom_id, "method": "POST",
                                  "url": "/v1/chat/completions", "body": body},
                                 ensure_ascii=False))

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as tf:
        tf.write("\n".join(lines) + "\n")
        tmp_path = tf.name

    _log(f"⬆️  Chunk {chunk_num}/{total_chunks}: uploading {len(lines)} requests...")
    with open(tmp_path, "rb") as fh:
        up = client.files.create(file=fh, purpose="batch")
    os.unlink(tmp_path)

    job = client.batches.create(
        input_file_id=up.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={"project": "ai4rse-taxonomy", "chunk": f"{chunk_num}/{total_chunks}"},
    )
    _log(f"   ✅ {job.id} (status={job.status})")
    return job.id, index_map


def _poll_until_done(client, batch_id, interval=30):
    while True:
        batch = client.batches.retrieve(batch_id)
        rc = getattr(batch, "request_counts", None)
        counts = f" ({rc.completed}/{rc.total} done, {rc.failed} failed)" if rc else ""
        _log(f"   📡 {batch.status}{counts}")
        if batch.status in TERMINAL_STATES:
            return batch
        time.sleep(interval)


def _ingest(client, batch, index_map, prompt_id, run_mode):
    if batch.status not in ("completed", "partially_succeeded"):
        _log(f"   💥 {batch.status}")
        if getattr(batch, "errors", None):
            _log(f"      {batch.errors}")
        return 0, 0, 0, 0, 0, 0

    out_id = getattr(batch, "output_file_id", None)
    if not out_id:
        _log("   ⚠️  No output file.")
        return 0, 0, 0, 0, 0, 0

    content = client.files.content(out_id).text
    conn = get_db()
    tot_in = tot_cached = tot_out = 0
    ok = failed = written = 0
    timestamp = datetime.now().isoformat()

    for raw in content.splitlines():
        if not raw.strip():
            continue
        item = json.loads(raw)
        cid = item.get("custom_id")
        concept_ids = index_map.get(cid)
        if concept_ids is None:
            failed += 1
            continue
        if item.get("error"):
            _log(f"   ❌ {cid}: {str(item['error'])[:100]}")
            failed += 1
            continue

        body = item["response"]["body"]
        try:
            text = body["choices"][0]["message"]["content"]
            results = json.loads(text)["results"]
        except Exception as e:
            _log(f"   ❌ {cid}: bad JSON ({str(e)[:80]})")
            failed += 1
            continue

        usage = body.get("usage") or {}
        tot_in += usage.get("prompt_tokens", 0)
        tot_out += usage.get("completion_tokens", 0)
        tot_cached += (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)

        batch_idx = int(cid.split("-")[-1]) if "-" in cid else 0
        for j, res in enumerate(results):
            if j < len(concept_ids):
                conn.execute(
                    """INSERT INTO evaluation_results
                       (concept_id, system_prompt_id, issue, phantom_category,
                        suggested_low_level, confidence, reasoning, timestamp,
                        run_mode, batch_index)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        concept_ids[j], prompt_id,
                        res.get("issue", ""),
                        1 if res.get("phantom_category") else 0,
                        res.get("suggested_low_level", ""),
                        res.get("confidence", 0.0),
                        res.get("reasoning", ""),
                        timestamp, run_mode, batch_idx,
                    ),
                )
                written += 1
        ok += 1

    conn.commit()
    conn.close()
    return written, ok, failed, tot_in, tot_cached, tot_out


def _run_chunks(client, write_prompt_id, source_prompt_id, system_instruction,
                strict_schema, remaining, batch_size, run_mode):
    """Submit chunks one by one: submit -> poll -> ingest -> next. Fully automatic."""
    batches = [remaining[i:i + batch_size] for i in range(0, len(remaining), batch_size)]
    chunks = [batches[i:i + MAX_REQUESTS_PER_CHUNK]
              for i in range(0, len(batches), MAX_REQUESTS_PER_CHUNK)]

    _log(f"📊 {len(remaining)} concepts -> {len(batches)} requests -> {len(chunks)} sequential chunks")

    grand_written = grand_in = grand_cached = grand_out = 0

    for ci, chunk_batches in enumerate(chunks, 1):
        batch_id, index_map = _submit_one_chunk(
            client, chunk_batches, system_instruction, strict_schema,
            write_prompt_id, ci, len(chunks),
        )

        _save_state({
            "write_prompt_id": write_prompt_id,
            "source_prompt_id": source_prompt_id,
            "model": MODEL,
            "run_mode": run_mode,
            "current_chunk": ci,
            "total_chunks": len(chunks),
            "batch_id": batch_id,
            "finished": False,
        })

        done_batch = _poll_until_done(client, batch_id)
        w, ok, fail, ti, tc, to = _ingest(client, done_batch, index_map, write_prompt_id, run_mode)
        grand_written += w
        grand_in += ti
        grand_cached += tc
        grand_out += to

        _log(f"   chunk {ci}/{len(chunks)}: {w} results ({fail} failed)")

        if done_batch.status == "failed":
            _log(f"❌ Chunk {ci} failed. Run `resume` to retry remaining.")
            _save_state({
                "write_prompt_id": write_prompt_id,
                "source_prompt_id": source_prompt_id,
                "model": MODEL,
                "run_mode": run_mode,
                "current_chunk": ci,
                "total_chunks": len(chunks),
                "finished": False,
            })
            return

    new_in = max(0, grand_in - grand_cached)
    est = new_in / 1e6 * PRICE_IN + grand_cached / 1e6 * PRICE_CACHED + grand_out / 1e6 * PRICE_OUT
    _save_state({
        "write_prompt_id": write_prompt_id,
        "source_prompt_id": source_prompt_id,
        "model": MODEL,
        "finished": True,
        "total_written": grand_written,
    })
    _log("═" * 60)
    _log(f"🎉 ALL DONE! {grand_written} results across {len(chunks)} chunks.")
    _log(f"📊 Tokens — input: {grand_in:,} (cached: {grand_cached:,} | new: {new_in:,}) | output: {grand_out:,}")
    if grand_cached > 0:
        _log("   ✔️  Prompt caching applied.")
    _log(f"💵 Estimated cost: ${est:.3f}")
    _log("═" * 60)


# ─── Submit ─────────────────────────────────────────────────────────
def submit(prompt_id=None, limit=None, run_mode="batch_openai", batch_size=None,
           all_concepts=False, target_name=None):
    batch_size = int(batch_size) if batch_size else BATCH_SIZE

    existing = _load_state()
    if existing and not existing.get("finished"):
        raise SystemExit("❌ Active run exists. Run `resume` to continue or `cancel` first.")

    conn = get_db()
    client = get_openai_client()

    prompt_id = _resolve_prompt_id(conn, prompt_id)
    prompt_row = conn.execute(
        "SELECT name, content FROM system_prompts WHERE id = ?", (prompt_id,)
    ).fetchone()
    if not prompt_row:
        raise SystemExit(f"❌ System prompt {prompt_id} not found.")
    system_instruction = build_system_instruction(prompt_row["content"])
    strict_schema = _strict_schema(RESPONSE_SCHEMA)

    if all_concepts:
        from backend.db import create_system_prompt
        clone_name = target_name or f"{prompt_row['name']} · OpenAI {MODEL}"
        write_prompt_id = create_system_prompt(clone_name, prompt_row["content"])
        _log(f"🧬 Cloned prompt {prompt_id} -> {write_prompt_id} ({clone_name!r}).")
    else:
        write_prompt_id = prompt_id

    remaining = _get_remaining(conn, write_prompt_id)
    conn.close()

    if not remaining:
        _log("✅ All concepts already evaluated.")
        return
    if limit:
        remaining = remaining[: int(limit)]

    _log(f"📊 model {MODEL} | {len(remaining)} concepts | batch size {batch_size}")
    _run_chunks(client, write_prompt_id, prompt_id, system_instruction,
                strict_schema, remaining, batch_size, run_mode)


# ─── Resume ─────────────────────────────────────────────────────────
def resume():
    state = _load_state()
    if not state:
        raise SystemExit("❌ No saved state. Run `submit` first.")
    if state.get("finished"):
        _log("✅ Previous run already finished.")
        return

    write_pid = state["write_prompt_id"]
    source_pid = state["source_prompt_id"]

    conn = get_db()
    client = get_openai_client()

    prompt_row = conn.execute(
        "SELECT content FROM system_prompts WHERE id = ?", (source_pid,)
    ).fetchone()
    if not prompt_row:
        raise SystemExit(f"❌ Source prompt {source_pid} not found.")
    system_instruction = build_system_instruction(prompt_row["content"])
    strict_schema = _strict_schema(RESPONSE_SCHEMA)

    remaining = _get_remaining(conn, write_pid)
    conn.close()

    if not remaining:
        _log("✅ All concepts already evaluated. Nothing to resume.")
        state["finished"] = True
        _save_state(state)
        return

    _log(f"♻️  Resuming: {len(remaining)} concepts remaining for prompt {write_pid}.")
    _run_chunks(client, write_pid, source_pid, system_instruction,
                strict_schema, remaining, BATCH_SIZE, state.get("run_mode", "batch_openai"))


# ─── Status / cancel ────────────────────────────────────────────────
def status():
    st = _load_state()
    if not st:
        raise SystemExit("❌ No saved state.")
    _log(f"Model:    {st.get('model')}")
    _log(f"Write:    prompt {st.get('write_prompt_id')}")
    _log(f"Chunk:    {st.get('current_chunk')}/{st.get('total_chunks')}")
    _log(f"Finished: {st.get('finished')}")
    if st.get("batch_id") and not st.get("finished"):
        client = get_openai_client()
        batch = client.batches.retrieve(st["batch_id"])
        rc = getattr(batch, "request_counts", None)
        _log(f"Batch:    {batch.id} -> {batch.status}"
             + (f" ({rc.completed}/{rc.total} done)" if rc else ""))


def cancel():
    client = get_openai_client()
    st = _load_state()
    if not st:
        raise SystemExit("❌ No saved state.")
    bid = st.get("batch_id")
    if bid and not st.get("finished"):
        client.batches.cancel(bid)
        _log(f"🛑 Cancelled {bid}.")
    else:
        _log("Nothing to cancel.")


def main():
    ap = argparse.ArgumentParser(description="OpenAI Batch API evaluator (auto-chunked).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("submit", help="Submit concepts as auto-chunked batch jobs.")
    s.add_argument("--prompt-id", type=int, default=None)
    s.add_argument("--limit", type=int, default=None, help="Cap concepts (for testing).")
    s.add_argument("--batch-size", type=int, default=None, help="Concepts per request (default: 20).")
    s.add_argument("--all", dest="all_concepts", action="store_true",
                   help="All concepts under a fresh cloned prompt.")
    s.add_argument("--target-name", default=None)

    sub.add_parser("resume", help="Resume an interrupted run.")
    sub.add_parser("status", help="Print state.")
    sub.add_parser("cancel", help="Cancel current chunk.")

    args = ap.parse_args()
    if args.cmd == "submit":
        submit(prompt_id=args.prompt_id, limit=args.limit, batch_size=args.batch_size,
               all_concepts=args.all_concepts, target_name=args.target_name)
    elif args.cmd == "resume":
        resume()
    elif args.cmd == "status":
        status()
    elif args.cmd == "cancel":
        cancel()


if __name__ == "__main__":
    main()
