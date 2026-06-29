#!/usr/bin/env python3
"""
AI4RSE — Export evaluation results for Google Sheets.

Two modes:

  compare   Side-by-side Gemini vs gpt-4.1-mini on the overlapping concepts,
            for supervisors to decide which judge to continue with.
                ../.venv/bin/python export_for_sheets.py compare

  model     One model's outputs in the supervisor sheet's column order, so the
            block can be pasted in one shot once a model is chosen.
                ../.venv/bin/python export_for_sheets.py model --prompt-id 3   # Gemini
                ../.venv/bin/python export_for_sheets.py model --prompt-id 10  # gpt-4.1-mini

Output is TSV (tab-separated) — paste directly into Google Sheets, or import.
Rows are ordered by global_index, matching the supervisor sheet order.
"""

import os
import csv
import argparse
from backend.db import get_db

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Default prompt ids in this project.
GEMINI_PID = 3
GPT_PID = 10


def _fetch(conn, prompt_id):
    """Return {global_index: result_dict} for a prompt."""
    rows = conn.execute(
        """SELECT c.global_index, e.issue, e.phantom_category,
                  e.suggested_low_level, e.confidence, e.reasoning
           FROM evaluation_results e
           JOIN concepts c ON c.id = e.concept_id
           WHERE e.system_prompt_id = ?""",
        (prompt_id,),
    ).fetchall()
    return {r["global_index"]: dict(r) for r in rows}


def _concepts(conn):
    return conn.execute(
        """SELECT global_index, concept_name, concept_definition,
                  high_level, middle_level, low_level
           FROM concepts ORDER BY global_index"""
    ).fetchall()


def export_compare():
    conn = get_db()
    gem = _fetch(conn, GEMINI_PID)
    gpt = _fetch(conn, GPT_PID)
    concepts = _concepts(conn)
    conn.close()

    out = os.path.join(OUT_DIR, "compare_gemini_vs_gpt.tsv")
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow([
            "global_index", "Concept Name", "Current Low Level",
            "Gemini Issue", "Gemini Phantom", "Gemini Suggested", "Gemini Conf", "Gemini Reasoning",
            "GPT Issue", "GPT Phantom", "GPT Suggested", "GPT Conf", "GPT Reasoning",
            "Agree?", "Concept Definition",
        ])
        for c in concepts:
            gi = c["global_index"]
            g = gem.get(gi)
            p = gpt.get(gi)
            if not g and not p:
                continue  # neither judged it
            def cell(d, k):
                return "" if not d else d.get(k, "")
            def ph(d):
                return "" if not d else ("TRUE" if d.get("phantom_category") else "FALSE")
            agree = ""
            if g and p:
                agree = "yes" if g["issue"] == p["issue"] else "NO"
            w.writerow([
                gi, c["concept_name"], c["low_level"] or "",
                cell(g, "issue"), ph(g), cell(g, "suggested_low_level"), cell(g, "confidence"), cell(g, "reasoning"),
                cell(p, "issue"), ph(p), cell(p, "suggested_low_level"), cell(p, "confidence"), cell(p, "reasoning"),
                agree, c["concept_definition"] or "",
            ])
            n += 1

    both = sum(1 for c in concepts if c["global_index"] in gem and c["global_index"] in gpt)
    disagree = 0
    for c in concepts:
        gi = c["global_index"]
        if gi in gem and gi in gpt and gem[gi]["issue"] != gpt[gi]["issue"]:
            disagree += 1
    print(f"✅ Wrote {out}")
    print(f"   {n} rows | both models judged: {both} | they disagree on issue: {disagree} "
          f"({disagree * 100 // both if both else 0}%)")
    print(f"   Paste into Google Sheets, or File > Import > Upload.")


def export_model(prompt_id):
    conn = get_db()
    name_row = conn.execute("SELECT name FROM system_prompts WHERE id=?", (prompt_id,)).fetchone()
    res = _fetch(conn, prompt_id)
    concepts = _concepts(conn)
    conn.close()

    model_tag = (name_row["name"] if name_row else f"prompt{prompt_id}").replace(" ", "_")[:40]
    out = os.path.join(OUT_DIR, f"sheet_paste_{model_tag}.tsv")

    # Column order matches the supervisor sheet's model-output block:
    # Reason | Decision | Suggested low level | Issues | Confidence ST | Phantom Category | Confidence
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow([
            "Reason", "Decision", "Suggested low level", "Issues",
            "Confidence ST", "Phantom Category", "Confidence", "Concept Name",
        ])
        for c in concepts:
            r = res.get(c["global_index"])
            if not r:
                # leave a blank-but-aligned row so paste stays in register
                w.writerow(["", "", "", "", "", "", "", c["concept_name"]])
                continue
            w.writerow([
                r.get("reasoning", ""),
                "",  # Decision — human fills
                r.get("suggested_low_level", ""),
                r.get("issue", ""),
                "",  # Confidence ST — human fills
                "TRUE" if r.get("phantom_category") else "FALSE",
                r.get("confidence", ""),
                c["concept_name"],
            ])
            n += 1

    print(f"✅ Wrote {out}")
    print(f"   {len(concepts)} rows ({n} with results) for '{name_row['name'] if name_row else prompt_id}'.")
    print(f"   Columns match the sheet's model-output block (Reason ... Confidence).")
    print(f"   Last column 'Concept Name' is for alignment-checking; delete it after pasting.")


def main():
    ap = argparse.ArgumentParser(description="Export evaluation results for Google Sheets.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("compare", help="Side-by-side Gemini vs GPT for supervisor decision.")
    m = sub.add_parser("model", help="One model's outputs in sheet column order.")
    m.add_argument("--prompt-id", type=int, required=True, help="3=Gemini, 10=gpt-4.1-mini.")
    args = ap.parse_args()

    if args.cmd == "compare":
        export_compare()
    elif args.cmd == "model":
        export_model(args.prompt_id)


if __name__ == "__main__":
    main()
