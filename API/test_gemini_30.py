"""
Test script: Send the first 30 prompts to Gemini API for taxonomy validation.

Uses:
- IEEE taxonomy as system instruction
- Structured JSON output via Pydantic schema
- Sequential processing with retry + exponential backoff to respect rate limits
"""

import json
import os
import time
import random

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# ─── Configuration ──────────────────────────────────────────────────
MAX_RETRIES = 6
BASE_DELAY = 5.0        # seconds — initial backoff delay
DELAY_BETWEEN = 4.0     # seconds — pause between each request (free tier ~15 RPM)
TEST_SIZE = 30

# ─── Load environment ───────────────────────────────────────────────
load_dotenv()
api_key = os.getenv("GEMINI_API")
if not api_key:
    raise RuntimeError("GEMINI_API not found in .env file")

# ─── Pydantic schema for structured output ──────────────────────────
class TaxonomyValidation(BaseModel):
    alignment: str = Field(
        description="Must be exactly: 'Correct', 'Partially Correct', or 'Incorrect'"
    )
    suggested_path: str = Field(
        description="Suggested IEEE category path (High → Mid → Low). If Correct, provide the current path."
    )
    confidence: int = Field(
        description="Confidence rating from 1 (very low) to 5 (very high).",
        ge=1,
        le=5,
    )
    reasoning: str = Field(
        description="A short, concise, single-sentence explanation of the reasoning behind this validation."
    )

# ─── Initialize the Gemini Client ───────────────────────────────────
client = genai.Client(api_key=api_key)

# ─── Load IEEE Taxonomy for system instruction ──────────────────────
with open("taxonomy/ieee_taxonomy.json", "r") as f:
    ieee_taxonomy = json.load(f)

SYSTEM_INSTRUCTION = (
    "You are a taxonomy validation system. You must output raw JSON matching "
    "the requested schema.\nEvaluate the user's concept against this official "
    "IEEE Taxonomy mapping:\n"
    + json.dumps(ieee_taxonomy)
)

# ─── Load prompts ───────────────────────────────────────────────────
with open("prompts.json", "r") as f:
    prompts_data = json.load(f)

all_prompts = prompts_data["prompts"]


# ─── Worker function with retry ────────────────────────────────────
def process_single_prompt(prompt_entry: dict) -> dict:
    """Send a single prompt to Gemini with retry + exponential backoff."""
    idx = prompt_entry["global_index"]
    concept = prompt_entry["concept_name"]
    prompt_text = prompt_entry["prompt"]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt_text,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=TaxonomyValidation,
                    temperature=0.1,
                ),
            )
            result_json = json.loads(response.text)
            # Attach metadata for traceability
            result_json["global_index"] = idx
            result_json["original_row"] = prompt_entry["original_row"]
            result_json["concept_name"] = concept
            result_json["category_path"] = prompt_entry["category_path"]
            return result_json

        except Exception as e:
            error_str = str(e)
            is_retryable = any(code in error_str for code in ["429", "503", "500", "RESOURCE_EXHAUSTED", "UNAVAILABLE"])

            if is_retryable and attempt < MAX_RETRIES:
                delay = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
                print(f"       ⏳ Retry {attempt}/{MAX_RETRIES} for '{concept}' in {delay:.1f}s...")
                time.sleep(delay)
                continue
            else:
                return {
                    "global_index": idx,
                    "original_row": prompt_entry["original_row"],
                    "concept_name": concept,
                    "category_path": prompt_entry["category_path"],
                    "error": error_str,
                }

    # Should not reach here, but just in case
    return {
        "global_index": idx,
        "original_row": prompt_entry["original_row"],
        "concept_name": concept,
        "category_path": prompt_entry["category_path"],
        "error": "Max retries exhausted",
    }


# ─── Main test run (sequential with delay) ──────────────────────────
def run_test_30():
    test_subset = all_prompts[:TEST_SIZE]
    results = []
    start_time = time.time()

    print(f"🚀 Sending {len(test_subset)} requests to Gemini API (gemini-2.5-flash)...")
    print(f"   System instruction length: {len(SYSTEM_INSTRUCTION):,} characters")
    print(f"   Mode: Sequential with {DELAY_BETWEEN}s delay between requests")
    print(f"   Retry: up to {MAX_RETRIES}x with exponential backoff\n")

    for i, entry in enumerate(test_subset, 1):
        res = process_single_prompt(entry)
        results.append(res)

        if "error" in res:
            print(
                f"  ❌ [{i:2d}/{TEST_SIZE}] Row {res['original_row']:>5d} | "
                f"{res['concept_name'][:40]:<40s} | ERROR: {res['error'][:80]}"
            )
        else:
            alignment = res["alignment"]
            confidence = res["confidence"]
            symbol = {
                "Correct": "✅",
                "Partially Correct": "⚠️ ",
                "Incorrect": "❌",
            }.get(alignment, "❓")
            print(
                f"  {symbol} [{i:2d}/{TEST_SIZE}] Row {res['original_row']:>5d} | "
                f"{res['concept_name'][:40]:<40s} | {alignment:<20s} | conf={confidence}"
            )

        # Pause between requests to respect rate limits
        if i < len(test_subset):
            time.sleep(DELAY_BETWEEN)

    elapsed = time.time() - start_time

    # Sort results by global_index for consistent output
    results.sort(key=lambda r: r["global_index"])

    # Save results
    output_file = "test_30_results.json"
    with open(output_file, "w") as out_f:
        json.dump(results, out_f, indent=2, ensure_ascii=False)

    # ─── Summary ────────────────────────────────────────────────────
    successful = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    print(f"\n{'─' * 70}")
    print(f"  ✅ Completed: {len(successful)}/{len(test_subset)}")
    print(f"  ❌ Failed:    {len(failed)}/{len(test_subset)}")
    print(f"  ⏱  Elapsed:   {elapsed:.1f}s")

    if successful:
        alignments = {}
        for r in successful:
            a = r["alignment"]
            alignments[a] = alignments.get(a, 0) + 1

        avg_conf = sum(r["confidence"] for r in successful) / len(successful)

        print(f"\n  📊 Alignment Distribution:")
        for label in ["Correct", "Partially Correct", "Incorrect"]:
            count = alignments.get(label, 0)
            pct = count / len(successful) * 100
            print(f"     {label:<20s}: {count:3d} ({pct:5.1f}%)")
        print(f"     Avg Confidence:      {avg_conf:.2f}/5")

    if failed:
        print(f"\n  🔍 Failed entries:")
        for r in failed:
            print(f"     Row {r['original_row']}: {r['concept_name']} — {r['error'][:60]}")

    print(f"\n  💾 Results saved to: {output_file}")
    print(f"{'─' * 70}")


if __name__ == "__main__":
    run_test_30()
