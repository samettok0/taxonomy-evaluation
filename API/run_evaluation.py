#!/usr/bin/env python3
"""
Automated Taxonomy Evaluation via Gemini API (Paid Tier).

Processes all 10,542 AI4RSE concepts through Gemini 2.5 Flash with:
- Context caching for IEEE taxonomy (10x cheaper input reads)
- Structured JSON batch input (20 concepts per request)
- Crash-safe resume via JSONL + progress tracking
- Exponential backoff on rate-limit errors
- TSV export for Google Sheets

Usage:
    # Test run (1 batch = 20 concepts)
    .venv/bin/python API/run_evaluation.py test

    # Full run (all concepts, auto-resumes)
    .venv/bin/python API/run_evaluation.py run

    # Export results to TSV for Google Sheets
    .venv/bin/python API/run_evaluation.py export

    # Cache management
    .venv/bin/python API/run_evaluation.py cache-status
    .venv/bin/python API/run_evaluation.py cache-delete
"""

import argparse
import json
import os
import sys
import time
import random
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai import types

# ─── Paths ──────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

PROMPTS_FILE = os.path.join(PROJECT_ROOT, "prompts_slim.json")
SYSTEM_PROMPT_FILE = os.path.join(PROJECT_ROOT, "system_prompt.txt")
TAXONOMY_FILE = os.path.join(PROJECT_ROOT, "taxonomy", "ieee_taxonomy.json")
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

RESULTS_JSONL = os.path.join(SCRIPT_DIR, "evaluation_results.jsonl")
RESULTS_JSON = os.path.join(SCRIPT_DIR, "evaluation_results_all.json")
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "evaluation_progress.json")
TSV_FILE = os.path.join(SCRIPT_DIR, "evaluation_for_sheets.tsv")

# ─── Config ─────────────────────────────────────────────────────────
MODEL = "gemini-2.5-flash"
BATCH_SIZE = 20
DELAY_BETWEEN_REQUESTS = 2.0  # seconds
MAX_RETRIES = 6
BASE_DELAY = 5.0  # initial backoff delay (seconds)
CACHE_TTL = "7200s"  # 2 hours
CACHE_DISPLAY_NAME = "ai4rse-taxonomy-evaluation"

# ─── Response Schema ────────────────────────────────────────────────
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept_name": {
                        "type": "string",
                        "description": "The concept name, copied exactly from input.",
                    },
                    "issue": {
                        "type": "string",
                        "description": "The issue label for this concept.",
                        "enum": [
                            "none",
                            "misclassified",
                            "ambiguous",
                            "overly_generic",
                            "irrelevant",
                        ],
                    },
                    "phantom_category": {
                        "type": "boolean",
                        "description": "True if the current low-level category does NOT exist in the IEEE 2025 taxonomy.",
                    },
                    "suggested_low_level": {
                        "type": "string",
                        "description": "If misclassified, the exact IEEE 2025 category name. Otherwise empty string.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence score from 0.0 to 1.0.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Reasoning in 15 words or fewer. If phantom category, start with 'phantom:'.",
                    },
                },
                "required": [
                    "concept_name",
                    "issue",
                    "phantom_category",
                    "suggested_low_level",
                    "confidence",
                    "reasoning",
                ],
            },
        }
    },
    "required": ["results"],
}

# ─── Initialize ─────────────────────────────────────────────────────
load_dotenv(ENV_FILE)
api_key = os.getenv("GEMINI_API")
if not api_key:
    print("❌ GEMINI_API not found in .env file")
    sys.exit(1)

client = genai.Client(api_key=api_key)


# ─── Data Loading ───────────────────────────────────────────────────
def load_prompts():
    """Load all concepts from prompts_slim.json."""
    print(f"📂 Loading prompts from {os.path.basename(PROMPTS_FILE)}...")
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    prompts = data["prompts"]
    print(f"   ✅ Loaded {len(prompts):,} concepts")
    return prompts


def build_system_instruction():
    """Build the full system instruction by injecting taxonomy into template."""
    print(f"📂 Loading system prompt template...")
    with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
        template = f.read()

    print(f"📂 Loading IEEE taxonomy JSON ({os.path.getsize(TAXONOMY_FILE) / 1024:.0f} KB)...")
    with open(TAXONOMY_FILE, "r", encoding="utf-8") as f:
        taxonomy = json.load(f)

    taxonomy_str = json.dumps(taxonomy)

    # Replace the placeholder in the system prompt
    system_instruction = template.replace(
        "{here is the json taxonomy here}", taxonomy_str
    )

    # Append structured input format instructions
    system_instruction += "\n\nIMPORTANT: The user will send concepts as a JSON array. Each element has keys: concept_name, definition, current_low_level. Evaluate each concept and return a JSON object with a 'results' array containing one evaluation per concept, in the same order."

    print(f"   ✅ System instruction built ({len(system_instruction):,} characters)")
    return system_instruction


# ─── Context Cache Management ──────────────────────────────────────
def create_cache(system_instruction: str) -> str:
    """Create a context cache with the system instruction + taxonomy."""
    print(f"\n🗄️  Creating context cache (TTL: {CACHE_TTL})...")

    cache = client.caches.create(
        model=MODEL,
        config=types.CreateCachedContentConfig(
            display_name=CACHE_DISPLAY_NAME,
            system_instruction=system_instruction,
            ttl=CACHE_TTL,
        ),
    )

    print(f"   ✅ Cache created: {cache.name}")

    # Save cache name for resume
    save_progress(cache_name=cache.name)

    return cache.name


def find_existing_cache() -> str | None:
    """Check if a valid cache already exists from a previous run."""
    progress = load_progress()
    cached_name = progress.get("cache_name")

    if cached_name:
        try:
            cache = client.caches.get(name=cached_name)
            print(f"   ♻️  Found existing cache: {cache.name}")
            return cache.name
        except Exception:
            print(f"   ⚠️  Previous cache expired or invalid, will create new one.")
            return None
    return None


def delete_cache(cache_name: str):
    """Delete a context cache to stop storage billing."""
    try:
        client.caches.delete(name=cache_name)
        print(f"   🗑️  Cache deleted: {cache_name}")
    except Exception as e:
        print(f"   ⚠️  Could not delete cache: {e}")


def show_cache_status():
    """List all active caches."""
    print("🗄️  Active context caches:")
    found = False
    for cache in client.caches.list():
        found = True
        print(f"   📋 {cache.name}")
        print(f"      Display name: {cache.display_name}")
        print(f"      Model: {cache.model}")
        if hasattr(cache, "expire_time") and cache.expire_time:
            print(f"      Expires: {cache.expire_time}")
    if not found:
        print("   (none)")


def delete_all_caches():
    """Delete all caches for this project."""
    found = False
    for cache in client.caches.list():
        found = True
        print(f"   🗑️  Deleting {cache.name}...")
        try:
            client.caches.delete(name=cache.name)
        except Exception as e:
            print(f"      ⚠️  Failed: {e}")
    if not found:
        print("   (no caches to delete)")


# ─── Progress Tracking ─────────────────────────────────────────────
def load_progress() -> dict:
    """Load progress from JSON file."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_completed_batch": -1, "cache_name": None, "total_batches": 0}


def save_progress(
    last_completed_batch: int | None = None,
    cache_name: str | None = None,
    total_batches: int | None = None,
):
    """Save progress to JSON file."""
    progress = load_progress()
    if last_completed_batch is not None:
        progress["last_completed_batch"] = last_completed_batch
    if cache_name is not None:
        progress["cache_name"] = cache_name
    if total_batches is not None:
        progress["total_batches"] = total_batches
    progress["updated_at"] = datetime.now().isoformat()

    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2)


# ─── Batch Building ────────────────────────────────────────────────
def build_batches(prompts: list, batch_size: int = BATCH_SIZE) -> list:
    """Split prompts into batches of batch_size."""
    batches = []
    for i in range(0, len(prompts), batch_size):
        batch = prompts[i : i + batch_size]
        batches.append(batch)
    return batches


def build_user_message(batch: list) -> str:
    """Build the user message as a JSON array of concepts."""
    concepts = []
    for entry in batch:
        concepts.append(
            {
                "concept_name": entry["concept_name"],
                "definition": entry.get("concept_definition", ""),
                "current_low_level": entry.get("low_level", ""),
            }
        )
    return json.dumps(concepts, ensure_ascii=False)


# ─── API Call with Retry ───────────────────────────────────────────
def call_gemini(cache_name: str, user_message: str, batch_idx: int) -> dict | None:
    """Send a single batch to Gemini with retry + exponential backoff."""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=user_message,
                config=types.GenerateContentConfig(
                    cached_content=cache_name,
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                    temperature=0.1,
                ),
            )

            result = json.loads(response.text)

            # Log token usage if available
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                um = response.usage_metadata
                cached = getattr(um, "cached_content_token_count", 0) or 0
                prompt_tokens = getattr(um, "prompt_token_count", 0) or 0
                output_tokens = getattr(um, "candidates_token_count", 0) or 0
                if cached > 0:
                    print(
                        f"      📊 Tokens — cached: {cached:,} | prompt: {prompt_tokens:,} | output: {output_tokens:,}"
                    )

            return result

        except Exception as e:
            error_str = str(e)
            is_retryable = any(
                code in error_str
                for code in [
                    "429",
                    "503",
                    "500",
                    "RESOURCE_EXHAUSTED",
                    "UNAVAILABLE",
                    "INTERNAL",
                ]
            )

            if is_retryable and attempt < MAX_RETRIES:
                delay = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 2)
                print(
                    f"      ⏳ Retry {attempt}/{MAX_RETRIES} for batch {batch_idx} in {delay:.1f}s... ({error_str[:80]})"
                )
                time.sleep(delay)
                continue
            else:
                print(f"      ❌ Batch {batch_idx} FAILED after {attempt} attempts: {error_str[:120]}")
                return None

    return None


# ─── Main Processing Loop ──────────────────────────────────────────
def run_evaluation(test_mode: bool = False):
    """Run the full evaluation pipeline."""

    # 1. Load data
    prompts = load_prompts()
    system_instruction = build_system_instruction()

    # 2. Build batches
    batches = build_batches(prompts)
    total_batches = len(batches)
    print(f"\n📦 {len(prompts):,} concepts → {total_batches} batches of {BATCH_SIZE}")

    if test_mode:
        batches = batches[:1]
        total_batches = 1
        print(f"   🧪 TEST MODE: Processing only batch #1 ({len(batches[0])} concepts)")

    # 3. Set up or reuse context cache
    cache_name = find_existing_cache()
    if not cache_name:
        cache_name = create_cache(system_instruction)

    save_progress(total_batches=total_batches)

    # 4. Determine where to resume from
    progress = load_progress()
    start_batch = progress.get("last_completed_batch", -1) + 1

    if start_batch > 0 and not test_mode:
        print(f"\n♻️  Resuming from batch {start_batch + 1}/{total_batches}")

    # 5. Process batches
    start_time = time.time()
    success_count = 0
    error_count = 0

    print(f"\n{'═' * 70}")
    print(f"  🚀 Starting evaluation ({total_batches} batches)")
    print(f"  📊 Model: {MODEL}")
    print(f"  🗄️  Cache: {cache_name}")
    print(f"  ⏱️  Delay: {DELAY_BETWEEN_REQUESTS}s between requests")
    print(f"{'═' * 70}\n")

    for batch_idx in range(start_batch, len(batches)):
        batch = batches[batch_idx]
        batch_start = batch_idx * BATCH_SIZE
        batch_end = batch_start + len(batch)

        print(
            f"  [{batch_idx + 1:>4}/{total_batches}] "
            f"Concepts {batch_start + 1}–{batch_end} ...",
            end="",
            flush=True,
        )

        # Build user message
        user_message = build_user_message(batch)

        # Call API
        result = call_gemini(cache_name, user_message, batch_idx)

        if result and "results" in result:
            # Validate result count
            expected = len(batch)
            got = len(result["results"])
            if got != expected:
                print(f" ⚠️  Expected {expected} results, got {got}")

            # Enrich results with metadata
            for i, res in enumerate(result["results"]):
                if i < len(batch):
                    res["global_index"] = batch[i]["global_index"]
                    res["original_row"] = batch[i]["original_row"]
                    res["category_path"] = batch[i]["category_path"]
                    res["low_level"] = batch[i].get("low_level", "")

            # Append to JSONL
            with open(RESULTS_JSONL, "a", encoding="utf-8") as f:
                record = {
                    "batch_index": batch_idx,
                    "batch_start": batch_start,
                    "batch_end": batch_end,
                    "timestamp": datetime.now().isoformat(),
                    "results": result["results"],
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            success_count += 1
            # Print summary of this batch
            issues = {}
            for r in result["results"]:
                iss = r.get("issue", "unknown")
                issues[iss] = issues.get(iss, 0) + 1
            issue_summary = " | ".join(f"{k}:{v}" for k, v in sorted(issues.items()))
            print(f" ✅ ({got} results) [{issue_summary}]")

        else:
            error_count += 1
            # Write error record
            with open(RESULTS_JSONL, "a", encoding="utf-8") as f:
                record = {
                    "batch_index": batch_idx,
                    "batch_start": batch_start,
                    "batch_end": batch_end,
                    "timestamp": datetime.now().isoformat(),
                    "error": True,
                    "concepts": [b["concept_name"] for b in batch],
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f" ❌ FAILED")

        # Update progress
        save_progress(last_completed_batch=batch_idx)

        # Delay between requests (skip on last batch)
        if batch_idx < len(batches) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    # 6. Summary
    elapsed = time.time() - start_time
    processed_batches = len(batches) - start_batch

    print(f"\n{'═' * 70}")
    print(f"  ✅ Completed: {success_count}/{processed_batches} batches")
    print(f"  ❌ Failed:    {error_count}/{processed_batches} batches")
    print(f"  ⏱️  Elapsed:   {elapsed:.1f}s ({elapsed / 60:.1f} min)")
    print(f"  💾 Results:   {RESULTS_JSONL}")
    print(f"{'═' * 70}")

    if not test_mode and error_count == 0:
        # Auto-export and cleanup
        print("\n📤 Auto-exporting results...")
        export_results()
        print("\n🗑️  Cleaning up cache...")
        delete_cache(cache_name)
    elif test_mode:
        print(f"\n🧪 Test complete! Review results in {RESULTS_JSONL}")
        print(f"   Run 'python API/run_evaluation.py export' to generate TSV")
        print(f"   Run 'python API/run_evaluation.py run' for the full evaluation")


# ─── Export ─────────────────────────────────────────────────────────
def export_results():
    """Export JSONL results to a merged JSON and a TSV for Google Sheets."""

    if not os.path.exists(RESULTS_JSONL):
        print(f"❌ No results file found: {RESULTS_JSONL}")
        return

    print(f"📤 Exporting results from {os.path.basename(RESULTS_JSONL)}...")

    all_results = []
    error_batches = []

    with open(RESULTS_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("error"):
                error_batches.append(record)
            else:
                all_results.extend(record.get("results", []))

    print(f"   📊 Total results: {len(all_results)}")
    if error_batches:
        print(f"   ⚠️  Error batches: {len(error_batches)}")

    # Sort by global_index for consistent ordering
    all_results.sort(key=lambda r: r.get("global_index", 0))

    # 1. Save merged JSON
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(
            {
                "exported_at": datetime.now().isoformat(),
                "total_results": len(all_results),
                "error_batches": len(error_batches),
                "results": all_results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"   💾 Merged JSON: {RESULTS_JSON}")

    # 2. Generate TSV for Google Sheets
    # Columns: Reasoning | Issue | Phantom Category | Suggested Low Level | Confidence
    with open(TSV_FILE, "w", encoding="utf-8") as f:
        # Header
        f.write("Reasoning\tIssue\tPhantom Category\tSuggested Low Level\tConfidence\n")

        for r in all_results:
            reasoning = (r.get("reasoning") or "").replace("\t", " ").replace("\n", " ")
            issue = r.get("issue", "")
            phantom = "TRUE" if r.get("phantom_category") else "FALSE"
            suggested = (r.get("suggested_low_level") or "").replace("\t", " ")
            confidence = str(r.get("confidence", ""))

            f.write(f"{reasoning}\t{issue}\t{phantom}\t{suggested}\t{confidence}\n")

    print(f"   💾 TSV for Sheets: {TSV_FILE} ({len(all_results)} rows)")

    # 3. Print issue distribution
    issues = {}
    phantoms = 0
    for r in all_results:
        iss = r.get("issue", "unknown")
        issues[iss] = issues.get(iss, 0) + 1
        if r.get("phantom_category"):
            phantoms += 1

    print(f"\n   📊 Issue Distribution:")
    for label, count in sorted(issues.items(), key=lambda x: -x[1]):
        pct = count / len(all_results) * 100
        print(f"      {label:<20s}: {count:5,} ({pct:5.1f}%)")
    print(f"      {'phantom categories':<20s}: {phantoms:5,}")


# ─── CLI ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Automated Taxonomy Evaluation via Gemini API"
    )
    parser.add_argument(
        "command",
        choices=["test", "run", "export", "cache-status", "cache-delete"],
        help="Command to execute",
    )
    args = parser.parse_args()

    if args.command == "test":
        run_evaluation(test_mode=True)
    elif args.command == "run":
        run_evaluation(test_mode=False)
    elif args.command == "export":
        export_results()
    elif args.command == "cache-status":
        show_cache_status()
    elif args.command == "cache-delete":
        delete_all_caches()


if __name__ == "__main__":
    main()
