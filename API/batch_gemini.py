"""
Gemini Batch API: Prepare and submit taxonomy validation prompts.

This script:
1. Converts prompts.json into a JSONL file (GenerateContentRequest per line)
2. Uploads the JSONL file via the Gemini Files API
3. Submits a batch job referencing the uploaded file
4. Polls for completion and downloads results

Usage:
    # Step 1: Prepare JSONL + submit batch (first 30 for testing)
    python batch_gemini.py prepare --count 30

    # Step 2: Check job status
    python batch_gemini.py status --job <JOB_NAME>

    # Step 3: Download results when complete
    python batch_gemini.py results --job <JOB_NAME>

    # Full run (all prompts):
    python batch_gemini.py prepare --count all
"""

import argparse
import json
import os
import sys
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

# ─── Load environment ───────────────────────────────────────────────
load_dotenv()
api_key = os.getenv("GEMINI_API")
if not api_key:
    raise RuntimeError("GEMINI_API not found in .env file")

client = genai.Client(api_key=api_key)

# ─── Shared config ──────────────────────────────────────────────────
MODEL = "gemini-2.5-flash"

# Structured output schema (as dict for JSONL embedding)
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "alignment": {
            "type": "string",
            "description": "The evaluation of whether the concept belongs to the assigned category path.",
            "enum": ["Correct", "Partially Correct", "Incorrect"],
        },
        "suggested_path": {
            "type": "string",
            "description": "The suggested IEEE category path (High → Mid → Low) if alignment is Partially Correct or Incorrect. If Correct, provide the current path.",
        },
        "confidence": {
            "type": "integer",
            "description": "Confidence rating of the evaluation from 1 (very low) to 5 (very high).",
            "minimum": 1,
            "maximum": 5,
        },
        "reasoning": {
            "type": "string",
            "description": "A short, concise, single-sentence explanation of the reasoning behind this validation.",
        },
    },
    "required": ["alignment", "suggested_path", "confidence", "reasoning"],
}


# ─── Step 1: Prepare JSONL ──────────────────────────────────────────
def prepare_and_submit(count: int | str):
    """Convert prompts to JSONL, upload, and submit batch job."""

    # Load IEEE Taxonomy for system instruction
    with open("taxonomy/ieee_taxonomy.json", "r") as f:
        ieee_taxonomy = json.load(f)

    system_instruction = (
        "You are a taxonomy validation system. You must output raw JSON "
        "matching the requested schema.\nEvaluate the user's concept against "
        "this official IEEE Taxonomy mapping:\n"
        + json.dumps(ieee_taxonomy)
    )

    # Load prompts
    with open("prompts.json", "r") as f:
        prompts_data = json.load(f)

    all_prompts = prompts_data["prompts"]

    if count == "all":
        subset = all_prompts
    else:
        subset = all_prompts[: int(count)]

    print(f"📦 Preparing JSONL for {len(subset)} prompts...")

    # Build JSONL file — each line is a GenerateContentRequest
    jsonl_path = f"batch_requests_{len(subset)}.jsonl"
    with open(jsonl_path, "w") as jf:
        for entry in subset:
            request_obj = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": entry["prompt"]}],
                    }
                ],
                "systemInstruction": {
                    "parts": [{"text": system_instruction}]
                },
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": RESPONSE_SCHEMA,
                    "temperature": 0.1,
                },
            }
            jf.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

    file_size_mb = os.path.getsize(jsonl_path) / (1024 * 1024)
    print(f"   ✅ JSONL created: {jsonl_path} ({file_size_mb:.1f} MB, {len(subset)} lines)")

    # Upload the file
    print(f"\n📤 Uploading JSONL to Gemini Files API...")
    try:
        uploaded_file = client.files.upload(
            file=jsonl_path,
            config=types.UploadFileConfig(
                display_name=f"taxonomy-validation-{len(subset)}",
                mime_type="application/jsonl",
            ),
        )
        print(f"   ✅ Upload complete: {uploaded_file.name}")
    except Exception as e:
        print(f"   ❌ Upload failed: {e}")
        print(f"   💡 Trying with text/plain MIME type as fallback...")
        uploaded_file = client.files.upload(
            file=jsonl_path,
            config=types.UploadFileConfig(
                display_name=f"taxonomy-validation-{len(subset)}",
                mime_type="text/plain",
            ),
        )
        print(f"   ✅ Upload complete (fallback): {uploaded_file.name}")

    # Submit batch job
    print(f"\n🚀 Submitting batch job...")
    batch_job = client.batches.create(
        model=MODEL,
        src=uploaded_file.name,
        config=types.CreateBatchJobConfig(
            display_name=f"taxonomy-validation-{len(subset)}-prompts",
        ),
    )

    print(f"   ✅ Batch job created!")
    print(f"   📋 Job name: {batch_job.name}")
    print(f"   📊 State:    {batch_job.state}")
    print(f"\n   💡 Check status with:")
    print(f"      .venv/bin/python batch_gemini.py status --job {batch_job.name}")
    print(f"\n   💡 Get results with:")
    print(f"      .venv/bin/python batch_gemini.py results --job {batch_job.name}")

    # Save job info for reference
    job_info = {
        "job_name": batch_job.name,
        "model": MODEL,
        "prompt_count": len(subset),
        "jsonl_file": jsonl_path,
        "uploaded_file": uploaded_file.name,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open("batch_job_info.json", "w") as f:
        json.dump(job_info, f, indent=2)
    print(f"\n   💾 Job info saved to batch_job_info.json")


# ─── Step 2: Check status ──────────────────────────────────────────
def check_status(job_name: str):
    """Poll the batch job status."""
    print(f"🔍 Checking status for: {job_name}")
    batch_job = client.batches.get(name=job_name)

    print(f"   📊 State: {batch_job.state}")

    if hasattr(batch_job, "dest") and batch_job.dest:
        print(f"   📁 Destination: {batch_job.dest}")

    return batch_job


# ─── Step 3: Download results ──────────────────────────────────────
def download_results(job_name: str):
    """Download and parse batch results."""
    print(f"📥 Fetching results for: {job_name}")
    batch_job = client.batches.get(name=job_name)

    state_str = str(batch_job.state)
    if "SUCCEEDED" not in state_str:
        print(f"   ⏳ Job not yet complete. State: {batch_job.state}")
        print(f"   💡 Re-run this command later.")
        return

    print(f"   ✅ Job completed! Downloading results...")

    # The batch job result is available in batch_job.dest
    # or via iterating over the results
    results = []
    try:
        # Try to get results from the batch job
        for result in client.batches.list():
            if result.name == job_name:
                print(f"   Found job: {result.name}")
                break

        # Download result file
        if hasattr(batch_job, "dest") and batch_job.dest:
            result_file_name = batch_job.dest
            print(f"   📁 Result file: {result_file_name}")

            # Download the result
            result_content = client.files.download(name=result_file_name)
            output_file = "batch_results.jsonl"
            with open(output_file, "wb") as f:
                f.write(result_content)
            print(f"   💾 Raw results saved to: {output_file}")

            # Parse JSONL results
            parsed_results = []
            with open(output_file, "r") as f:
                for line in f:
                    if line.strip():
                        parsed_results.append(json.loads(line))

            # Save as formatted JSON
            formatted_file = "batch_results_formatted.json"
            with open(formatted_file, "w") as f:
                json.dump(parsed_results, f, indent=2, ensure_ascii=False)
            print(f"   💾 Formatted results saved to: {formatted_file}")

            # Summary
            if parsed_results:
                print(f"\n   📊 Results Summary ({len(parsed_results)} entries):")
                alignments = {}
                for r in parsed_results:
                    try:
                        resp = r.get("response", {})
                        candidates = resp.get("candidates", [{}])
                        if candidates:
                            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
                            data = json.loads(text)
                            a = data.get("alignment", "Unknown")
                            alignments[a] = alignments.get(a, 0) + 1
                    except Exception:
                        alignments["Parse Error"] = alignments.get("Parse Error", 0) + 1

                for label, ct in sorted(alignments.items()):
                    pct = ct / len(parsed_results) * 100
                    print(f"      {label:<20s}: {ct:3d} ({pct:5.1f}%)")

    except Exception as e:
        print(f"   ❌ Error downloading results: {e}")
        print(f"   💡 Raw batch job object: {batch_job}")


# ─── CLI ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Gemini Batch API for taxonomy validation")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # prepare
    prep = subparsers.add_parser("prepare", help="Prepare JSONL and submit batch job")
    prep.add_argument("--count", default="30", help="Number of prompts (or 'all')")

    # status
    stat = subparsers.add_parser("status", help="Check batch job status")
    stat.add_argument("--job", required=True, help="Batch job name")

    # results
    res = subparsers.add_parser("results", help="Download batch results")
    res.add_argument("--job", required=True, help="Batch job name")

    # list
    subparsers.add_parser("list", help="List all batch jobs")

    args = parser.parse_args()

    if args.command == "prepare":
        prepare_and_submit(args.count)
    elif args.command == "status":
        check_status(args.job)
    elif args.command == "results":
        download_results(args.job)
    elif args.command == "list":
        print("📋 Listing batch jobs...")
        for job in client.batches.list():
            print(f"   {job.name} — {job.state}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
