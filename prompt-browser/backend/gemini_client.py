import os
import json
import threading
from backend.config import ENV_FILE, MODEL, RESPONSE_SCHEMA, build_system_instruction
from backend.db import get_concept_by_index, get_concepts_range, get_system_prompt_by_id

_gemini_client = None
_gemini_lock = threading.Lock()

def get_gemini_client():
    """Lazy-load the Gemini client."""
    global _gemini_client
    with _gemini_lock:
        if _gemini_client is not None:
            return _gemini_client
        try:
            from dotenv import load_dotenv
            load_dotenv(ENV_FILE)
        except ImportError:
            pass

        api_key = os.getenv("GEMINI_API")
        if not api_key:
            raise RuntimeError("GEMINI_API not found in environment or .env file")

        from google import genai
        _gemini_client = genai.Client(api_key=api_key)
        return _gemini_client

def evaluate_range(concept_index, count, system_prompt_id):
    """Evaluate a range of concepts starting from concept_index with a specific system prompt via Gemini."""
    concepts = get_concepts_range(concept_index, count)
    if not concepts:
        raise ValueError("Concepts not found")

    prompt_row = get_system_prompt_by_id(system_prompt_id)
    if not prompt_row:
        raise ValueError("System prompt not found")

    system_instruction = build_system_instruction(prompt_row["content"])

    user_message = json.dumps([
        {
            "concept_name": c["concept_name"],
            "definition": c["concept_definition"] or "",
            "current_low_level": c["low_level"] or "",
        }
        for c in concepts
    ], ensure_ascii=False)

    client = get_gemini_client()
    from google.genai import types

    response = None
    import time
    import random
    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                    temperature=0.1,
                ),
            )
            break
        except Exception as e:
            error_str = str(e)
            is_retryable = any(
                code in error_str
                for code in ["429", "503", "500", "403", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL"]
            )
            if is_retryable and attempt < 3:
                time.sleep(2.0 * attempt + random.uniform(0, 1))
            else:
                raise

    result = json.loads(response.text)

    token_info = {}
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        um = response.usage_metadata
        token_info = {
            "cached": getattr(um, "cached_content_token_count", 0) or 0,
            "prompt": getattr(um, "prompt_token_count", 0) or 0,
            "output": getattr(um, "candidates_token_count", 0) or 0,
        }

    return {
        "result": result,
        "tokens": token_info,
        "system_prompt_id": system_prompt_id,
    }
