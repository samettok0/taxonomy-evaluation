#!/usr/bin/env python3
"""
AI4RSE — Normalize concept `low_level` capitalisation to the IEEE taxonomy.

The source data uses Title Case ("Neural Networks") while the IEEE 2025 taxonomy
is Sentence-cased ("Neural networks"). Under the strict verbatim phantom rule
this makes ~25% of concepts look like phantom categories purely over casing.

This script fixes that deterministically:
  - For each concept whose `low_level` matches a taxonomy category
    case-insensitively (but not exactly), rewrite it to the exact taxonomy
    casing.
  - Concepts with no taxonomy match (genuine phantoms) are left untouched.
  - The original value is preserved in a new `low_level_raw` column, so the
    change is fully reversible (`--revert`).

Idempotent and safe to run twice.

    ../.venv/bin/python normalize_low_level.py            # apply
    ../.venv/bin/python normalize_low_level.py --dry-run  # preview only
    ../.venv/bin/python normalize_low_level.py --revert   # restore originals
"""

import os
import json
import argparse

from backend.config import DB_FILE, TAXONOMY_FILE
from backend.db import get_db


def _taxonomy_names():
    with open(TAXONOMY_FILE, "r", encoding="utf-8") as f:
        tax = json.load(f)
    names = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                names.append(k)
                walk(v)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, str):
                    names.append(item)
                else:
                    walk(item)

    walk(tax)
    return names


def _ensure_backup_column(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(concepts)").fetchall()]
    if "low_level_raw" not in cols:
        conn.execute("ALTER TABLE concepts ADD COLUMN low_level_raw TEXT")
        # Preserve the current (pre-normalization) value as the backup.
        conn.execute("UPDATE concepts SET low_level_raw = low_level WHERE low_level_raw IS NULL")
        conn.commit()


def apply(dry_run=False):
    names = _taxonomy_names()
    exact = set(names)
    ci = {}
    for n in names:
        ci.setdefault(n.lower(), n)  # lowercased -> canonical taxonomy casing

    conn = get_db()
    if not dry_run:
        _ensure_backup_column(conn)

    rows = conn.execute("SELECT id, low_level FROM concepts").fetchall()
    changed = 0
    samples = []
    for r in rows:
        ll = r["low_level"] or ""
        if ll in exact:
            continue
        canon = ci.get(ll.lower())
        if canon and canon != ll:
            if len(samples) < 12:
                samples.append((ll, canon))
            if not dry_run:
                conn.execute("UPDATE concepts SET low_level = ? WHERE id = ?", (canon, r["id"]))
            changed += 1

    if not dry_run:
        conn.commit()
    conn.close()

    print(f"{'[DRY RUN] would normalize' if dry_run else 'Normalized'} {changed} concept low_level values.")
    print("Examples:")
    for a, b in samples:
        print(f"    {a!r:<40} -> {b!r}")
    if not dry_run:
        print("\nOriginal values backed up in concepts.low_level_raw (use --revert to restore).")


def revert():
    conn = get_db()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(concepts)").fetchall()]
    if "low_level_raw" not in cols:
        conn.close()
        raise SystemExit("❌ No backup column found — nothing to revert.")
    n = conn.execute(
        "UPDATE concepts SET low_level = low_level_raw WHERE low_level_raw IS NOT NULL AND low_level != low_level_raw"
    ).rowcount
    conn.commit()
    conn.close()
    print(f"Reverted {n} concept low_level values to their originals.")


def main():
    ap = argparse.ArgumentParser(description="Normalize low_level capitalisation to the IEEE taxonomy.")
    ap.add_argument("--dry-run", action="store_true", help="Preview changes without writing.")
    ap.add_argument("--revert", action="store_true", help="Restore original values from backup.")
    args = ap.parse_args()
    if args.revert:
        revert()
    else:
        apply(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
