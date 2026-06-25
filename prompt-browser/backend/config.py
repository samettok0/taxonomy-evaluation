"""
AI4RSE Prompt Browser — Configuration & Constants

Centralizes all paths, model parameters, and schema definitions
used across backend modules.
"""

import os
import json

# ─── Paths ──────────────────────────────────────────────────────────
BROWSER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BROWSER_DIR)
DB_FILE = os.path.join(PROJECT_ROOT, "taxonomy.db")
TAXONOMY_FILE = os.path.join(PROJECT_ROOT, "taxonomy", "ieee_taxonomy.json")
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

# ─── Server ─────────────────────────────────────────────────────────
PORT = 8080

# ─── Load Environment Variables ──────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)
except ImportError:
    pass

# ─── Gemini Model ───────────────────────────────────────────────────
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
BATCH_SIZE = 20
DELAY_BETWEEN_REQUESTS = 5.0
MAX_RETRIES = 10  # Increased from 6 to 10 for better resilience under high demand
BASE_DELAY = 5.0
CACHE_TTL = "7200s"

CACHE_DISPLAY_NAME = "ai4rse-taxonomy-evaluation"

# ─── Gemini Response Schema ────────────────────────────────────────
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept_name": {"type": "string"},
                    "issue": {
                        "type": "string",
                        "enum": ["none", "misclassified", "ambiguous", "overly_generic", "irrelevant"],
                    },
                    "phantom_category": {"type": "boolean"},
                    "suggested_low_level": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"},
                },
                "required": [
                    "concept_name", "issue", "phantom_category",
                    "suggested_low_level", "confidence", "reasoning",
                ],
            },
        }
    },
    "required": ["results"],
}


def build_system_instruction(template_content):
    """Build full system instruction by injecting taxonomy JSON into template."""
    if os.path.exists(TAXONOMY_FILE):
        with open(TAXONOMY_FILE, "r", encoding="utf-8") as f:
            taxonomy = json.load(f)
        taxonomy_str = json.dumps(taxonomy)
        instruction = template_content.replace("{here is the json taxonomy here}", taxonomy_str)
    else:
        instruction = template_content

    instruction += (
        "\n\nIMPORTANT: The user will send concepts as a JSON array. "
        "Each element has keys: concept_name, definition, current_low_level. "
        "Evaluate each concept and return a JSON object with a 'results' array "
        "containing one evaluation per concept, in the same order."
    )
    return instruction
