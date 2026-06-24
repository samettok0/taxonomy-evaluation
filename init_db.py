#!/usr/bin/env python3
"""
Database initialization and seeding for the AI4RSE Taxonomy Evaluation project.

Creates taxonomy.db with:
  - concepts      – all ~10,542 taxonomy concepts
  - system_prompts – versioned system prompts for evaluation
  - evaluation_results – Gemini API evaluation results linked to prompt versions
  - user_decisions – manual decisions from the prompt browser
  - app_state      – key/value store for browser UI state

Also migrates existing data from:
  - prompts_slim.json -> concepts
  - system_prompt.txt -> system_prompts (initial version)
  - prompt-browser/progress.json -> user_decisions + app_state
  - API/evaluation_results.jsonl -> evaluation_results

Usage:
    python3 init_db.py
"""

import json
import os
import sqlite3
import sys
from datetime import datetime

# ─── Paths ──────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "taxonomy.db")

PROMPTS_FILE = os.path.join(SCRIPT_DIR, "prompts_slim.json")
SYSTEM_PROMPT_FILE = os.path.join(SCRIPT_DIR, "system_prompt.txt")
BROWSER_PROGRESS_FILE = os.path.join(SCRIPT_DIR, "prompt-browser", "progress.json")
EVAL_RESULTS_JSONL = os.path.join(SCRIPT_DIR, "API", "evaluation_results.jsonl")


# ─── Schema ─────────────────────────────────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS concepts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    global_index    INTEGER UNIQUE NOT NULL,
    original_row    INTEGER,
    concept_name    TEXT NOT NULL,
    concept_definition TEXT DEFAULT '',
    high_level      TEXT DEFAULT '',
    middle_level    TEXT DEFAULT '',
    low_level       TEXT DEFAULT '',
    category_path   TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_concepts_global ON concepts(global_index);
CREATE INDEX IF NOT EXISTS idx_concepts_high   ON concepts(high_level);
CREATE INDEX IF NOT EXISTS idx_concepts_mid    ON concepts(middle_level);
CREATE INDEX IF NOT EXISTS idx_concepts_low    ON concepts(low_level);

CREATE TABLE IF NOT EXISTS system_prompts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    is_active   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS evaluation_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id          INTEGER NOT NULL,
    system_prompt_id    INTEGER NOT NULL,
    issue               TEXT DEFAULT '',
    phantom_category    INTEGER DEFAULT 0,
    suggested_low_level TEXT DEFAULT '',
    confidence          REAL DEFAULT 0.0,
    reasoning           TEXT DEFAULT '',
    timestamp           TEXT NOT NULL,
    run_mode            TEXT DEFAULT 'full',
    batch_index         INTEGER DEFAULT -1,
    FOREIGN KEY (concept_id) REFERENCES concepts(id),
    FOREIGN KEY (system_prompt_id) REFERENCES system_prompts(id)
);

CREATE INDEX IF NOT EXISTS idx_eval_concept ON evaluation_results(concept_id);
CREATE INDEX IF NOT EXISTS idx_eval_prompt  ON evaluation_results(system_prompt_id);
CREATE INDEX IF NOT EXISTS idx_eval_batch   ON evaluation_results(batch_index);

CREATE TABLE IF NOT EXISTS user_decisions (
    concept_id  INTEGER PRIMARY KEY,
    decision    TEXT DEFAULT '',
    reason      TEXT DEFAULT '',
    issues      TEXT DEFAULT '',
    new_path    TEXT DEFAULT '',
    response    TEXT DEFAULT '',
    timestamp   TEXT NOT NULL,
    FOREIGN KEY (concept_id) REFERENCES concepts(id)
);

CREATE TABLE IF NOT EXISTS app_state (
    key     TEXT PRIMARY KEY,
    value   TEXT DEFAULT ''
);
"""


def create_database():
    """Create the database and tables."""
    if os.path.exists(DB_FILE):
        print(f"⚠️  Database already exists: {DB_FILE}")
        print(f"   Delete it first if you want a fresh start.")
        print(f"   Continuing with migration of any new data...")
        return sqlite3.connect(DB_FILE)

    print(f"📦 Creating database: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    print(f"   ✅ Tables created")
    return conn


def seed_concepts(conn):
    """Import concepts from prompts_slim.json."""
    # Check if already seeded
    count = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    if count > 0:
        print(f"   ♻️  Concepts table already has {count:,} rows, skipping.")
        return

    if not os.path.exists(PROMPTS_FILE):
        print(f"   ❌ Prompts file not found: {PROMPTS_FILE}")
        return

    print(f"📂 Loading concepts from {os.path.basename(PROMPTS_FILE)}...")
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    prompts = data["prompts"]
    metadata = data.get("metadata", {})
    category_index = data.get("category_index", [])

    print(f"   Inserting {len(prompts):,} concepts...")
    conn.executemany(
        """INSERT INTO concepts
           (global_index, original_row, concept_name, concept_definition,
            high_level, middle_level, low_level, category_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                p.get("global_index", i),
                p.get("original_row", i + 1),
                p.get("concept_name", ""),
                p.get("concept_definition", ""),
                p.get("high_level", ""),
                p.get("middle_level", ""),
                p.get("low_level", ""),
                p.get("category_path", ""),
            )
            for i, p in enumerate(prompts)
        ],
    )

    # Store metadata and category_index as app_state
    conn.execute(
        "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
        ("metadata", json.dumps(metadata)),
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
        ("category_index", json.dumps(category_index)),
    )

    conn.commit()
    print(f"   ✅ Inserted {len(prompts):,} concepts")


def seed_system_prompt(conn):
    """Import the default system prompt from system_prompt.txt."""
    count = conn.execute("SELECT COUNT(*) FROM system_prompts").fetchone()[0]
    if count > 0:
        print(f"   ♻️  System prompts table already has {count} entries, skipping.")
        return

    if not os.path.exists(SYSTEM_PROMPT_FILE):
        print(f"   ❌ System prompt file not found: {SYSTEM_PROMPT_FILE}")
        return

    print(f"📝 Loading system prompt from {os.path.basename(SYSTEM_PROMPT_FILE)}...")
    with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    conn.execute(
        """INSERT INTO system_prompts (name, content, created_at, is_active)
           VALUES (?, ?, ?, 1)""",
        ("Default IEEE Alignment", content, datetime.now().isoformat()),
    )
    conn.commit()
    print(f"   ✅ Inserted default system prompt (set as active)")


def migrate_browser_progress(conn):
    """Migrate user decisions and app state from prompt-browser/progress.json."""
    if not os.path.exists(BROWSER_PROGRESS_FILE):
        print(f"   ⏭️  No browser progress file found, skipping.")
        return

    # Check if decisions already migrated
    dec_count = conn.execute("SELECT COUNT(*) FROM user_decisions").fetchone()[0]
    if dec_count > 0:
        print(f"   ♻️  User decisions already migrated ({dec_count} rows), skipping.")
        return

    print(f"📂 Loading browser progress from {os.path.basename(BROWSER_PROGRESS_FILE)}...")
    with open(BROWSER_PROGRESS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    responses = data.get("responses", {})
    if responses:
        print(f"   Migrating {len(responses)} user decisions...")
        for idx_str, resp in responses.items():
            idx = int(idx_str)
            # Look up concept_id from global_index
            row = conn.execute(
                "SELECT id FROM concepts WHERE global_index = ?", (idx,)
            ).fetchone()
            if row:
                conn.execute(
                    """INSERT OR REPLACE INTO user_decisions
                       (concept_id, decision, reason, issues, new_path, response, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row[0],
                        resp.get("decision", ""),
                        resp.get("reason", ""),
                        resp.get("issues", ""),
                        resp.get("newPath", ""),
                        resp.get("response", ""),
                        resp.get("timestamp", datetime.now().isoformat()),
                    ),
                )
        conn.commit()
        print(f"   ✅ Migrated {len(responses)} user decisions")

    # Migrate app state (templates, currentIndex, etc.)
    for key in ["currentIndex", "activeTemplateId", "lastBatchedIndex"]:
        if key in data:
            conn.execute(
                "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
                (key, json.dumps(data[key])),
            )

    if "templates" in data:
        conn.execute(
            "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
            ("templates", json.dumps(data["templates"])),
        )

    # Migrate completed set
    completed = data.get("completed", [])
    if completed:
        conn.execute(
            "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
            ("completed", json.dumps(completed)),
        )

    conn.commit()
    print(f"   ✅ Migrated app state")


def migrate_evaluation_results(conn):
    """Migrate evaluation results from API/evaluation_results.jsonl."""
    if not os.path.exists(EVAL_RESULTS_JSONL):
        print(f"   ⏭️  No evaluation results file found, skipping.")
        return

    # Check if already migrated
    count = conn.execute("SELECT COUNT(*) FROM evaluation_results").fetchone()[0]
    if count > 0:
        print(f"   ♻️  Evaluation results already migrated ({count} rows), skipping.")
        return

    # Get the first system prompt id (the default)
    prompt_row = conn.execute("SELECT id FROM system_prompts LIMIT 1").fetchone()
    if not prompt_row:
        print(f"   ⚠️  No system prompts in DB, cannot link evaluation results.")
        return
    system_prompt_id = prompt_row[0]

    print(f"📂 Loading evaluation results from {os.path.basename(EVAL_RESULTS_JSONL)}...")
    total = 0

    with open(EVAL_RESULTS_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)

            if record.get("error"):
                continue  # Skip error records

            batch_index = record.get("batch_index", -1)
            timestamp = record.get("timestamp", datetime.now().isoformat())

            for res in record.get("results", []):
                global_index = res.get("global_index")
                if global_index is None:
                    continue

                concept_row = conn.execute(
                    "SELECT id FROM concepts WHERE global_index = ?", (global_index,)
                ).fetchone()
                if not concept_row:
                    continue

                conn.execute(
                    """INSERT INTO evaluation_results
                       (concept_id, system_prompt_id, issue, phantom_category,
                        suggested_low_level, confidence, reasoning, timestamp,
                        run_mode, batch_index)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        concept_row[0],
                        system_prompt_id,
                        res.get("issue", ""),
                        1 if res.get("phantom_category") else 0,
                        res.get("suggested_low_level", ""),
                        res.get("confidence", 0.0),
                        res.get("reasoning", ""),
                        timestamp,
                        "test",  # The existing results are from a test run
                        batch_index,
                    ),
                )
                total += 1

    conn.commit()
    print(f"   ✅ Migrated {total} evaluation results")


def print_summary(conn):
    """Print a summary of the database contents."""
    print(f"\n{'═' * 50}")
    print(f"  📊 Database Summary: {DB_FILE}")
    print(f"{'═' * 50}")

    tables = [
        ("concepts", "Concepts"),
        ("system_prompts", "System Prompts"),
        ("evaluation_results", "Evaluation Results"),
        ("user_decisions", "User Decisions"),
        ("app_state", "App State Entries"),
    ]

    for table, label in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {label:.<30s} {count:>6,}")

    db_size = os.path.getsize(DB_FILE)
    print(f"\n  Database size: {db_size / 1024 / 1024:.1f} MB")
    print(f"{'═' * 50}")


def main():
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║   AI4RSE Taxonomy — Database Setup           ║")
    print(f"╚══════════════════════════════════════════════╝\n")

    conn = create_database()

    # Ensure tables exist (idempotent)
    conn.executescript(SCHEMA_SQL)

    print()
    seed_concepts(conn)
    print()
    seed_system_prompt(conn)
    print()
    print("📦 Migrating existing data...")
    migrate_browser_progress(conn)
    migrate_evaluation_results(conn)

    print_summary(conn)
    conn.close()

    print(f"\n✅ Done! You can now run:")
    print(f"   python3 prompt-browser/server.py")


if __name__ == "__main__":
    main()
