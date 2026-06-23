# Automated Taxonomy Evaluation (API)

This directory contains the automation scripts, configurations, and results for evaluating and refining the AI4RSE taxonomy against the IEEE Taxonomy (2025 edition).

The primary entry point is [run_evaluation.py](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/API/run_evaluation.py), a command-line utility that processes thousands of AI4RSE concepts using the Gemini API.

---

## Table of Contents
1. [Prerequisites & Setup](#prerequisites--setup)
2. [CLI Commands](#cli-commands)
3. [Architecture & Key Features](#architecture--key-features)
   - [Context Caching (10x Input Cost Reduction)](#context-caching-10x-input-cost-reduction)
   - [Structured JSON Batching](#structured-json-batching)
   - [Crash-Safe Resume](#crash-safe-resume)
   - [Exponential Backoff Rate-Limit Handling](#exponential-backoff-rate-limit-handling)
4. [File Descriptions](#file-descriptions)
5. [Evaluation Response Schema](#evaluation-response-schema)

---

## Prerequisites & Setup

1. **Environment Setup**: Ensure your Python virtual environment is activated.
   ```bash
   source .venv/bin/activate
   ```

2. **API Credentials**: The script reads the Gemini API key from a `.env` file at the project root. Create or update the `.env` file to include:
   ```env
   GEMINI_API=your_gemini_api_key_here
   ```

3. **Input Data Dependencies**:
   - [prompts_slim.json](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/prompts_slim.json): Contains the 10,542 concepts to be evaluated.
   - [system_prompt.txt](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/system_prompt.txt): The system prompt template where the taxonomy JSON is injected.
   - [ieee_taxonomy.json](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/taxonomy/ieee_taxonomy.json): The reference taxonomy file.

---

## CLI Commands

The [run_evaluation.py](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/API/run_evaluation.py) script supports the following commands:

### 1. Test Run
Runs a fast test using the first 20 batches (400 concepts total) to verify prompting, schema validation, and API connection.
```bash
python API/run_evaluation.py test
```

### 2. Full Evaluation
Runs the full evaluation on all 10,542 concepts. It automatically resumes from where it last stopped using progress tracking.
```bash
python API/run_evaluation.py run
```

### 3. Export Results
Consolidates raw line-by-line batch results into a single merged JSON file and generates a TSV file tailored for Google Sheets. It also outputs the issue distribution statistics.
```bash
python API/run_evaluation.py export
```

### 4. Cache Status
Lists active context caches associated with your API key to check billing/lifespan.
```bash
python API/run_evaluation.py cache-status
```

### 5. Clear Caches
Deletes all active context caches to prevent unexpected storage costs.
```bash
python API/run_evaluation.py cache-delete
```

---

## Architecture & Key Features

### Context Caching (10x Input Cost Reduction)
Because the reference IEEE 2025 taxonomy is large, sending it along with every single API call would result in huge input token counts and high latency/cost. 
The script uses the **Gemini Context Caching** API:
- It constructs the system instruction by reading [system_prompt.txt](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/system_prompt.txt) and replacing the `{here is the json taxonomy here}` placeholder with the serialized [ieee_taxonomy.json](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/taxonomy/ieee_taxonomy.json).
- It caches this static system instruction with a TTL of 2 hours (`7200s`).
- Subsequent requests point to this cache using the `cached_content` parameter, reducing input token read costs by roughly **10x**.

### Structured JSON Batching
- Concepts are grouped into batches of **20** to minimize request overhead and rate limits.
- The request configuration uses `response_mime_type="application/json"` combined with a strict `RESPONSE_SCHEMA` (`type: "object"`, containing a `results` array of objects).
- This guarantees the model's output perfectly matches the expected structure.

### Crash-Safe Resume
Processing 10,000+ concepts takes time and is vulnerable to network interruptions or script crashes. The script implements progress-tracking:
- **Progress Tracking File**: [evaluation_progress.json](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/API/evaluation_progress.json) stores the current `cache_name` and the `last_completed_batch` index.
- **Incremental Outputs**: Each batch response is immediately appended to [evaluation_results.jsonl](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/API/evaluation_results.jsonl).
- If the script is aborted, running `python API/run_evaluation.py run` will reload the cached content reference and pick up from the next uncompleted batch.

### Exponential Backoff Rate-Limit Handling
Transient issues or rate limits (e.g. HTTP codes `429`, `500`, `503`, and gRPC errors like `RESOURCE_EXHAUSTED` or `UNAVAILABLE`) are handled with exponential backoff and jitter:
- **Max Retries**: 6 attempts per batch.
- **Base Delay**: Starts at 5 seconds, doubling on each failure with random jitter added to prevent thundering herd issues.

---

## File Descriptions

The evaluation process generates and maintains the following files in the [API/](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/API) directory:

- [evaluation_progress.json](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/API/evaluation_progress.json): Keeps track of progress metadata to support resumes.
- [evaluation_results.jsonl](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/API/evaluation_results.jsonl): Append-only log storing individual batch results, response timestamps, and batch indexes. If a batch fails completely after all retries, an error record with the corresponding concept names is written here.
- [evaluation_results_all.json](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/API/evaluation_results_all.json): Created during `export`. Contains all sorted, merged evaluations in a single JSON structure.
- [evaluation_for_sheets.tsv](file:///Users/samettok/Documents/GitHub/taxonomy-evaluation/API/evaluation_for_sheets.tsv): Created during `export`. A tab-separated file containing the evaluated fields, designed to be imported directly into Google Sheets.

---

## Evaluation Response Schema

Each evaluated concept contains the following properties:

| Property Name | Type | Description |
| :--- | :--- | :--- |
| `concept_name` | String | The concept name copied verbatim from the input. |
| `issue` | String | The categorization issue label. Must be one of: `none`, `misclassified`, `ambiguous`, `overly_generic`, or `irrelevant`. |
| `phantom_category` | Boolean | Set to `true` if the concept's low-level category does not exist in the IEEE 2025 taxonomy. |
| `suggested_low_level`| String | If `issue` is `misclassified`, the exact name of the suggested IEEE 2025 low-level category verbatim. For any other issue, this must be an empty string `""`. |
| `confidence` | Number | Confidence score between `0.0` and `1.0`. |
| `reasoning` | String | A brief rationale (15 words or fewer). If it is a phantom category, this starts with `phantom:`. |
