import sqlite3
import json
from datetime import datetime
from backend.config import DB_FILE

def get_db():
    """Get a database connection (one per thread)."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def _ensure_playground_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS playground_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            system_prompt_id INTEGER,
            concept_index INTEGER,
            count INTEGER,
            result_json TEXT,
            timestamp TEXT,
            FOREIGN KEY(system_prompt_id) REFERENCES system_prompts(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

# Ensure tables exist on import
_ensure_playground_table()

def get_prompts_and_state():
    """Get all concepts, metadata, and category index."""
    conn = get_db()
    
    meta_row = conn.execute("SELECT value FROM app_state WHERE key='metadata'").fetchone()
    cat_row = conn.execute("SELECT value FROM app_state WHERE key='category_index'").fetchone()

    metadata = json.loads(meta_row["value"]) if meta_row else {}
    category_index = json.loads(cat_row["value"]) if cat_row else []

    rows = conn.execute(
        """SELECT global_index, original_row, concept_name, concept_definition,
                  high_level, middle_level, low_level, category_path
           FROM concepts ORDER BY global_index"""
    ).fetchall()

    prompts = [dict(r) for r in rows]
    conn.close()

    return {
        "metadata": metadata,
        "category_index": category_index,
        "prompts": prompts,
    }

def load_app_state():
    """Load progress (decisions and app state)."""
    conn = get_db()

    # Load app state
    state_rows = conn.execute("SELECT key, value FROM app_state").fetchall()
    state = {}
    for row in state_rows:
        try:
            state[row["key"]] = json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            state[row["key"]] = row["value"]

    # Load user decisions
    dec_rows = conn.execute(
        """SELECT c.global_index, d.decision, d.reason, d.issues,
                  d.new_path, d.response, d.timestamp
           FROM user_decisions d
           JOIN concepts c ON c.id = d.concept_id"""
    ).fetchall()

    responses = {}
    completed = []
    for row in dec_rows:
        idx = row["global_index"]
        responses[str(idx)] = {
            "decision": row["decision"],
            "reason": row["reason"],
            "issues": row["issues"],
            "newPath": row["new_path"],
            "response": row["response"],
            "timestamp": row["timestamp"],
        }
        completed.append(idx)

    conn.close()

    return {
        "currentIndex": state.get("currentIndex", 0),
        "responses": responses,
        "completed": completed,
        "templates": state.get("templates", []),
        "activeTemplateId": state.get("activeTemplateId", "t1"),
        "lastBatchedIndex": state.get("lastBatchedIndex", 1),
    }

def save_app_state(data):
    """Save progress (decisions and app state)."""
    conn = get_db()

    for key in ["currentIndex", "activeTemplateId", "lastBatchedIndex", "templates"]:
        if key in data:
            conn.execute(
                "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
                (key, json.dumps(data[key])),
            )

    responses = data.get("responses", {})
    for idx_str, resp in responses.items():
        idx = int(idx_str)
        concept_row = conn.execute(
            "SELECT id FROM concepts WHERE global_index = ?", (idx,)
        ).fetchone()
        if concept_row:
            conn.execute(
                """INSERT OR REPLACE INTO user_decisions
                   (concept_id, decision, reason, issues, new_path, response, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    concept_row["id"],
                    resp.get("decision", ""),
                    resp.get("reason", ""),
                    resp.get("issues", ""),
                    resp.get("newPath", ""),
                    resp.get("response", ""),
                    resp.get("timestamp", datetime.now().isoformat()),
                ),
            )

    completed = data.get("completed", [])
    conn.execute(
        "INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
        ("completed", json.dumps(completed)),
    )

    conn.commit()
    conn.close()

def get_system_prompts():
    """List all system prompts."""
    conn = get_db()
    rows = conn.execute(
        """SELECT id, name, content, created_at, is_active,
           (SELECT COUNT(*) FROM evaluation_results WHERE system_prompt_id = system_prompts.id) as result_count
           FROM system_prompts ORDER BY created_at DESC"""
    ).fetchall()
    prompts = [dict(r) for r in rows]
    conn.close()
    return prompts

def create_system_prompt(name, content):
    """Create a new system prompt."""
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO system_prompts (name, content, created_at, is_active)
           VALUES (?, ?, ?, 0)""",
        (name, content, datetime.now().isoformat()),
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def set_active_system_prompt(prompt_id):
    """Set a system prompt as the active one."""
    conn = get_db()
    conn.execute("UPDATE system_prompts SET is_active = 0")
    conn.execute("UPDATE system_prompts SET is_active = 1 WHERE id = ?", (prompt_id,))
    conn.commit()
    conn.close()

def delete_system_prompt(prompt_id):
    """Delete a system prompt (and its evaluation results). Returns True if deleted, False if last prompt."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) as c FROM system_prompts").fetchone()["c"]
    if count <= 1:
        conn.close()
        return False

    conn.execute("DELETE FROM evaluation_results WHERE system_prompt_id = ?", (prompt_id,))
    conn.execute("DELETE FROM system_prompts WHERE id = ?", (prompt_id,))
    conn.commit()
    conn.close()
    return True

def get_concept_by_index(global_index):
    conn = get_db()
    concept = conn.execute(
        """SELECT concept_name, concept_definition, low_level
           FROM concepts WHERE global_index = ?""",
        (global_index,),
    ).fetchone()
    conn.close()
    return concept

def get_concepts_range(start_index, count):
    conn = get_db()
    rows = conn.execute(
        """SELECT global_index, concept_name, concept_definition, low_level
           FROM concepts 
           WHERE global_index >= ? 
           ORDER BY global_index 
           LIMIT ?""",
        (start_index, count),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_system_prompt_by_id(prompt_id):
    conn = get_db()
    prompt = conn.execute(
        "SELECT id, content FROM system_prompts WHERE id = ?",
        (prompt_id,),
    ).fetchone()
    conn.close()
    return prompt

def get_evaluation_results(system_prompt_id):
    """Return evaluation results for a given system prompt."""
    conn = get_db()
    rows = conn.execute(
        """SELECT c.global_index, c.concept_name, c.category_path,
                  e.issue, e.phantom_category, e.suggested_low_level,
                  e.confidence, e.reasoning, e.timestamp, e.run_mode
           FROM evaluation_results e
           JOIN concepts c ON c.id = e.concept_id
           WHERE e.system_prompt_id = ?
           ORDER BY c.global_index""",
        (system_prompt_id,),
    ).fetchall()

    results = [dict(r) for r in rows]

    issues = {}
    phantoms = 0
    for r in results:
        iss = r.get("issue", "unknown")
        issues[iss] = issues.get(iss, 0) + 1
        if r.get("phantom_category"):
            phantoms += 1

    conn.close()
    return {
        "results": results,
        "total": len(results),
        "issues": issues,
        "phantoms": phantoms,
    }

def save_playground_history(system_prompt_id, concept_index, count, result_json):
    """Save a run from the live playground."""
    conn = get_db()
    conn.execute(
        """INSERT INTO playground_history 
           (system_prompt_id, concept_index, count, result_json, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        (system_prompt_id, concept_index, count, json.dumps(result_json), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_playground_history():
    """Get recent playground history."""
    conn = get_db()
    rows = conn.execute(
        """SELECT h.id, h.system_prompt_id, h.concept_index, h.count, h.result_json, h.timestamp,
                  p.name as prompt_name
           FROM playground_history h
           LEFT JOIN system_prompts p ON p.id = h.system_prompt_id
           ORDER BY h.timestamp DESC LIMIT 50"""
    ).fetchall()
    conn.close()
    
    history = []
    for r in rows:
        d = dict(r)
        try:
            d["result_json"] = json.loads(d["result_json"])
        except:
            d["result_json"] = {}
        history.append(d)
    return history

def clear_playground_history():
    """Clear all playground history."""
    conn = get_db()
    conn.execute("DELETE FROM playground_history")
    conn.commit()
    conn.close()

def get_evaluation_progress(system_prompt_id):
    """Return overall evaluation progress for a given system prompt."""
    conn = get_db()
    total_row = conn.execute("SELECT COUNT(*) as c FROM concepts").fetchone()
    total_concepts = total_row["c"] if total_row else 0
    
    eval_row = conn.execute(
        "SELECT COUNT(DISTINCT concept_id) as c FROM evaluation_results WHERE system_prompt_id = ?",
        (system_prompt_id,)
    ).fetchone()
    evaluated_concepts = eval_row["c"] if eval_row else 0
    
    conn.close()
    return {
        "total_concepts": total_concepts,
        "evaluated_concepts": evaluated_concepts,
        "remaining_concepts": max(0, total_concepts - evaluated_concepts)
    }

