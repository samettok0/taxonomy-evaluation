import json
import threading
import time
import random
from datetime import datetime

from backend.config import MODEL, BATCH_SIZE, DELAY_BETWEEN_REQUESTS, MAX_RETRIES, BASE_DELAY, CACHE_TTL, CACHE_DISPLAY_NAME, RESPONSE_SCHEMA, build_system_instruction
from backend.db import get_db
from backend.gemini_client import get_gemini_client

# ─── Background batch state ────────────────────────────────────────
batch_state = {
    "running": False,
    "should_stop": False,
    "current_batch": 0,
    "total_batches": 0,
    "success_count": 0,
    "error_count": 0,
    "started_at": None,
    "logs": [],
    "system_prompt_id": None,
    "run_mode": "full",
    "cache_name": None,
}
batch_lock = threading.RLock()

def get_status():
    """Return current batch evaluation status."""
    with batch_lock:
        state_copy = dict(batch_state)
        state_copy["logs"] = list(batch_state["logs"][-50:])  # Last 50 lines
    return state_copy

def stop_evaluation():
    """Signal the batch evaluation to stop after the current batch."""
    with batch_lock:
        if not batch_state["running"]:
            return False
        batch_state["should_stop"] = True
    _log("⏸️ Stop requested, finishing current batch...")
    return True

def start_evaluation(system_prompt_id, run_mode="full", max_batches=None, batch_size=20):
    """Start a batch evaluation in a background thread."""
    with batch_lock:
        if batch_state["running"]:
            raise RuntimeError("Evaluation already running")

        batch_state["running"] = True
        batch_state["should_stop"] = False
        batch_state["current_batch"] = 0
        batch_state["total_batches"] = 0
        batch_state["success_count"] = 0
        batch_state["error_count"] = 0
        batch_state["started_at"] = datetime.now().isoformat()
        batch_state["logs"] = []
        batch_state["system_prompt_id"] = system_prompt_id
        batch_state["run_mode"] = run_mode
        batch_state["cache_name"] = None

    thread = threading.Thread(
        target=_run_batch_evaluation,
        args=(system_prompt_id, run_mode, max_batches, batch_size),
        daemon=True,
    )
    thread.start()

def _log(msg):
    log_str = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(log_str, flush=True)
    with batch_lock:
        batch_state["logs"].append(log_str)

def _run_batch_evaluation(system_prompt_id, run_mode, max_batches, batch_size):
    """Background thread for batch evaluation."""
    cache_name = None
    client = None
    conn = None
    try:
        from google.genai import types

        conn = get_db()
        client = get_gemini_client()

        # Get system prompt
        prompt_row = conn.execute(
            "SELECT content FROM system_prompts WHERE id = ?", (system_prompt_id,)
        ).fetchone()
        if not prompt_row:
            _log("❌ System prompt not found")
            return

        system_instruction = build_system_instruction(prompt_row["content"])

        # Find which concepts already have results for this prompt
        evaluated = set()
        rows = conn.execute(
            """SELECT c.global_index FROM evaluation_results e
               JOIN concepts c ON c.id = e.concept_id
               WHERE e.system_prompt_id = ?""",
            (system_prompt_id,),
        ).fetchall()
        for r in rows:
            evaluated.add(r["global_index"])

        # Get all concepts
        all_concepts = conn.execute(
            """SELECT id, global_index, concept_name, concept_definition, low_level
               FROM concepts ORDER BY global_index"""
        ).fetchall()

        # Filter out already-evaluated concepts
        remaining = [c for c in all_concepts if c["global_index"] not in evaluated]

        if not remaining:
            _log("✅ All concepts already evaluated with this prompt!")
            return

        # Build batches
        batches = []
        for i in range(0, len(remaining), batch_size):
            batches.append(remaining[i:i + batch_size])

        if max_batches:
            try:
                max_batches = int(max_batches)
                batches = batches[:max_batches]
            except (ValueError, TypeError):
                pass

        total_batches = len(batches)
        with batch_lock:
            batch_state["total_batches"] = total_batches

        _log(f"🚀 Starting evaluation: {len(remaining)} concepts, {total_batches} batches")
        _log(f"📊 Model: {MODEL} | Prompt ID: {system_prompt_id}")

        # Create context cache
        _log(f"🗄️ Creating context cache (TTL: {CACHE_TTL})...")
        cache_name = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                cache = client.caches.create(
                    model=MODEL,
                    config=types.CreateCachedContentConfig(
                        display_name=CACHE_DISPLAY_NAME,
                        system_instruction=system_instruction,
                        ttl=CACHE_TTL,
                    ),
                )
                cache_name = cache.name
                with batch_lock:
                    batch_state["cache_name"] = cache_name
                _log(f"   ✅ Cache created: {cache_name}")
                break
            except Exception as e:
                error_str = str(e)
                is_retryable = any(
                    code in error_str
                    for code in ["429", "503", "500", "403", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL"]
                )
                if is_retryable and attempt < MAX_RETRIES:
                    delay = min(60.0, BASE_DELAY * (2 ** (attempt - 1))) + random.uniform(0, 2)
                    clean_error = error_str.replace('\n', ' ')
                    _log(f"   ⚠️ Cache creation failed (Retry {attempt}/{MAX_RETRIES} in {delay:.1f}s): {clean_error[:100]}")
                    time.sleep(delay)
                else:
                    _log(f"   ❌ Cache creation failed after {attempt} attempts: {e}. Aborting evaluation to prevent high costs.")
                    return

        # Process batches
        for batch_idx, batch in enumerate(batches):
            with batch_lock:
                if batch_state["should_stop"]:
                    _log(f"⏸️ Stopped at batch {batch_idx + 1}/{total_batches}")
                    break
                batch_state["current_batch"] = batch_idx + 1

            # Build user message
            concepts_json = [
                {
                    "concept_name": c["concept_name"],
                    "definition": c["concept_definition"] or "",
                    "current_low_level": c["low_level"] or "",
                }
                for c in batch
            ]
            user_message = json.dumps(concepts_json, ensure_ascii=False)

            _log(f"  [{batch_idx + 1:>4}/{total_batches}] Processing {len(batch)} concepts...")

            # Call Gemini with retries
            result = None
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    config = types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=RESPONSE_SCHEMA,
                        temperature=0.1,
                    )
                    if cache_name:
                        config.cached_content = cache_name
                    else:
                        config.system_instruction = system_instruction

                    response = client.models.generate_content(
                        model=MODEL,
                        contents=user_message,
                        config=config,
                    )
                    result = json.loads(response.text)
                    break
                except Exception as e:
                    error_str = str(e)
                    is_retryable = any(
                        code in error_str
                        for code in ["429", "503", "500", "403", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL"]
                    )
                    if is_retryable and attempt < MAX_RETRIES:
                        delay = min(60.0, BASE_DELAY * (2 ** (attempt - 1))) + random.uniform(0, 2)
                        # Remove newlines from error string to keep log format clean
                        clean_error = error_str.replace('\n', ' ')
                        _log(f"      ⏳ Retry {attempt}/{MAX_RETRIES} in {delay:.1f}s... ({clean_error[:100]})")
                        
                        # Wait in small increments so we can abort immediately
                        aborted = False
                        for _ in range(int(delay * 10)):
                            with batch_lock:
                                if batch_state["should_stop"]:
                                    aborted = True
                                    break
                            time.sleep(0.1)
                            
                        if aborted:
                            _log(f"      🛑 Retry aborted due to stop request.")
                            break
                    else:
                        _log(f"      ❌ Failed after {attempt} attempts: {error_str[:100]}")
                        break

            if result and "results" in result:
                # Save to database
                timestamp = datetime.now().isoformat()
                for i, res in enumerate(result["results"]):
                    if i < len(batch):
                        conn.execute(
                            """INSERT INTO evaluation_results
                               (concept_id, system_prompt_id, issue, phantom_category,
                                suggested_low_level, confidence, reasoning, timestamp,
                                run_mode, batch_index)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                batch[i]["id"],
                                system_prompt_id,
                                res.get("issue", ""),
                                1 if res.get("phantom_category") else 0,
                                res.get("suggested_low_level", ""),
                                res.get("confidence", 0.0),
                                res.get("reasoning", ""),
                                timestamp,
                                run_mode,
                                batch_idx,
                            ),
                        )
                conn.commit()

                # Log summary
                issues = {}
                for r in result["results"]:
                    iss = r.get("issue", "?")
                    issues[iss] = issues.get(iss, 0) + 1
                summary = " | ".join(f"{k}:{v}" for k, v in sorted(issues.items()))
                
                token_str = ""
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    um = response.usage_metadata
                    cached = getattr(um, "cached_content_token_count", 0) or 0
                    prompt = getattr(um, "prompt_token_count", 0) or 0
                    out_tok = getattr(um, "candidates_token_count", 0) or 0
                    if cached > 0:
                        new_tokens = max(0, prompt - cached)
                        token_str = f" [Tokens: {cached} cached | {new_tokens} new | {out_tok} out]"
                    else:
                        token_str = f" [Tokens: 0 cached | {prompt} new | {out_tok} out]"

                _log(f"      ✅ {len(result['results'])} results [{summary}]{token_str}")

                with batch_lock:
                    batch_state["success_count"] += 1
            else:
                with batch_lock:
                    batch_state["error_count"] += 1
                _log(f"      ❌ Batch {batch_idx + 1} FAILED")

            # Delay between requests
            if batch_idx < len(batches) - 1:
                time.sleep(DELAY_BETWEEN_REQUESTS)

        _log(f"✅ Completed: {batch_state['success_count']} success, {batch_state['error_count']} errors")

    except Exception as e:
        _log(f"💥 Fatal error: {str(e)}")
        
    finally:
        # ─── GUARANTEED CLEANUP ───
        if client and cache_name:
            try:
                client.caches.delete(name=cache_name)
                _log(f"🗑️ Cache cleaned up")
            except Exception as e:
                _log(f"⚠️ Failed to clean up cache: {str(e)}")

        with batch_lock:
            batch_state["running"] = False
            batch_state["cache_name"] = None

        if conn:
            try:
                conn.close()
            except Exception:
                pass
