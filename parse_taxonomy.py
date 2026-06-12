"""
parse_taxonomy.py – Convert the 2026 IEEE Taxonomy text file into a nested JSON tree.

Hierarchy encoding in the source file:
    Level 1 (top-level family)  →  0 leading dots   (e.g.  "Aerospace and electronic systems")
    Level 2                     →  4 leading dots   (e.g.  "....Aerospace control")
    Level 3                     →  8 leading dots   (e.g.  "........Air traffic control")
    Level 4                     → 12 leading dots   (e.g.  "............Air safety")

The depth of a term is computed as: dot_count // 4  (0, 1, 2, or 3).

The script maintains a `parent_stack` list that always holds a reference to the
current parent dictionary at each depth level so that newly encountered terms can
be inserted into the correct place in the tree.

Line-continuation handling:
    The raw text file was converted from a PDF, so some long term names are split
    across two lines.  For example:
        ........Electromagnetic propagation in absorbing
        media
    The continuation line ("media") has no leading dots and typically starts with
    a lowercase letter or a known continuation fragment (e.g. "on Climate Change").
    The pre-processing step detects these and joins them back with the previous
    content line before the hierarchy is parsed.
"""

import json
import re
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
INPUT_FILE  = Path(__file__).parent / "taxonomy" / "ieee-taxonomy.txt"
OUTPUT_FILE = Path(__file__).parent / "ieee_taxonomy.json"

# ── Lines to skip ────────────────────────────────────────────────────────────
# Page headers/footers and boilerplate produced during PDF-to-text conversion.
SKIP_PATTERNS = [
    re.compile(r"^January\s+2026"),              # "January 2026" / "January 2026 IEEE Taxonomy"
    re.compile(r"^IEEE\s+Taxonomy"),              # standalone "IEEE Taxonomy …" header lines
    re.compile(r"^Version"),                      # "Version"
    re.compile(r"^\d+\.\d+"),                     # "1.05" version number
    re.compile(r"^Created by"),                   # "Created by"
    re.compile(r"^The Institute of"),             # "The Institute of"
    re.compile(r"^Electrical and"),               # "Electrical and"
    re.compile(r"^Electronics Engineers"),         # "Electronics Engineers"
    re.compile(r"^\(IEEE\)"),                     # "(IEEE)"
    re.compile(r"Creative Commons"),              # CC license footer text
    re.compile(r"^International License"),        # continuation of CC license line
    re.compile(r"^Engineers \(IEEE\)"),           # continuation of CC license line
    re.compile(r"^Page\s+\d+"),                   # "Page 2", "Page 75", …
    re.compile(r"^The IEEE Taxonomy comprises"),  # intro paragraph lines
    re.compile(r"^term-families are arranged"),    # intro paragraph continuation
    re.compile(r"^hierarchy goes to no more"),     # intro paragraph continuation
    re.compile(r"^preceding the next level"),      # intro paragraph continuation
    re.compile(r"^can appear more than"),          # intro paragraph continuation
    re.compile(r"^way so that it is always"),      # intro paragraph continuation
    re.compile(r"^branch\) that is formed"),       # intro paragraph continuation
    re.compile(r"^\x0c"),                         # form-feed characters (\f)
]


def should_skip(line: str) -> bool:
    """Return True if `line` is empty or matches any boilerplate pattern."""
    if not line:
        return True
    return any(pat.search(line) for pat in SKIP_PATTERNS)


def is_continuation_line(line: str) -> bool:
    """
    Return True if `line` is a continuation of the previous term name.

    A continuation line has NO leading dots and is NOT a proper Level-1
    category.  Heuristic: it starts with a lowercase letter, or matches
    one of the known multi-word continuation fragments.
    """
    if not line or line.startswith("."):
        return False
    # Lines starting with lowercase are almost certainly continuations.
    if line[0].islower():
        return True
    # Known continuation fragments that start with uppercase.
    uppercase_continuations = [
        "Change",             # "Intergovernmental Panel on Climate" + "Change"
        "on Climate Change",  # "United Nations Framework Convention" + "on Climate Change"
    ]
    return line in uppercase_continuations


def preprocess_lines(filepath: Path) -> list[str]:
    """
    Read the raw file, strip boilerplate, and join continuation lines.

    Returns a list of clean content lines, each potentially prefixed with
    dots indicating its hierarchical depth.

    Continuation-line logic:
        After stripping boilerplate, if a content line has no leading dots
        and starts with a lowercase letter (or is a known continuation
        fragment), it is appended to the *previous* content line with a
        space separator.  This reconstructs the full term name that was
        split across lines during PDF-to-text conversion.
    """
    content_lines: list[str] = []

    with open(filepath, encoding="utf-8") as fh:
        for raw_line in fh:
            # Strip trailing whitespace / newline but preserve leading dots.
            line = raw_line.rstrip()
            # Remove form-feed characters that may be embedded in the line.
            line = line.replace("\x0c", "")
            # Strip only leading whitespace (spaces/tabs), NOT dots.
            line = line.lstrip(" \t")
            # Skip boilerplate and blank lines.
            if should_skip(line):
                continue
            # Detect continuation lines and merge with the previous entry.
            if is_continuation_line(line) and content_lines:
                # Append to the previous line with a space to reconstruct
                # the full term name.
                content_lines[-1] = content_lines[-1] + " " + line
            else:
                content_lines.append(line)

    return content_lines


def parse_taxonomy(filepath: Path) -> dict:
    """
    Parse the IEEE Taxonomy text file and return a nested dict.

    Structure of the returned dict
    ──────────────────────────────
    {
        "Aerospace and electronic systems": {
            "Aerospace control": {
                "Air traffic control": {},
                "Attitude control": {},
                "Ground support": {}
            },
            "Aerospace engineering": {
                "Aerospace biophysics": {},
                ...
            },
            ...
        },
        "Antennas and propagation": { ... },
        ...
    }

    Tracking the current parent at each depth
    ──────────────────────────────────────────
    `parent_stack` is a list of dict references, one per depth level seen so far.

      parent_stack[0]  →  the root dict        (contains all Level-1 entries)
      parent_stack[1]  →  the current Level-1 dict  (children of the active family)
      parent_stack[2]  →  the current Level-2 dict  (children of the active L2 term)
      parent_stack[3]  →  the current Level-3 dict  (children of the active L3 term)

    When we encounter a new term at depth d we:
      1. Create an empty dict for it inside parent_stack[d].
      2. Store that new dict as parent_stack[d+1] so that deeper terms
         know where to attach themselves.
      3. Truncate parent_stack to length d+2, discarding stale references
         from any deeper levels that are no longer current (this handles
         the case where the hierarchy jumps back to a shallower level).
    """

    # Pre-process: strip boilerplate and join continuation lines.
    content_lines = preprocess_lines(filepath)

    # The root dictionary that will hold every Level-1 family.
    taxonomy: dict = {}

    # parent_stack[0] always points to `taxonomy` (the root).
    # Subsequent entries point to the dict of the most-recently-seen term
    # at that depth, so children can be inserted into the right place.
    parent_stack: list[dict] = [taxonomy]

    # Regex that captures an optional run of leading dots, then the term text.
    # Group 1: the dots (may be empty for Level-1 terms).
    # Group 2: the term name (stripped of surrounding whitespace by the regex).
    term_re = re.compile(r"^(\.*)(.+)$")

    for line in content_lines:
        # Attempt to match the expected term pattern.
        m = term_re.match(line)
        if not m:
            continue

        dots = m.group(1)       # e.g. "........"
        name = m.group(2).strip()  # e.g. "Air traffic control"

        # Depth is determined by the number of leading dots.
        # Every 4 dots corresponds to one level of nesting.
        #   0 dots  → depth 0  (Level 1 / top-level family)
        #   4 dots  → depth 1  (Level 2)
        #   8 dots  → depth 2  (Level 3)
        #  12 dots  → depth 3  (Level 4)
        dot_count = len(dots)
        if dot_count % 4 != 0:
            # Safety check: skip malformed lines whose dot count
            # is not a multiple of 4.
            continue
        depth = dot_count // 4

        # Ensure we have a valid parent for this depth.
        # If `depth` is beyond the current stack length, the file
        # has skipped a level — skip the line to avoid a crash.
        if depth >= len(parent_stack):
            continue

        # Insert the new term as a child of its parent.
        # parent_stack[depth] is the dict that should hold this term.
        parent_stack[depth][name] = {}

        # Update the stack so that the next deeper level knows its parent.
        # parent_stack[depth + 1] must point to the dict we just created.
        if depth + 1 < len(parent_stack):
            # Overwrite the existing entry and discard anything deeper,
            # because the hierarchy has moved to a new branch.
            parent_stack[depth + 1] = parent_stack[depth][name]
            # Trim stale deeper entries.
            del parent_stack[depth + 2:]
        else:
            # We are extending the stack for the first time at this depth.
            parent_stack.append(parent_stack[depth][name])

    return taxonomy


def main() -> None:
    print(f"Reading  : {INPUT_FILE}")
    taxonomy = parse_taxonomy(INPUT_FILE)

    # Write the nested dictionary as pretty-printed JSON.
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(taxonomy, fh, indent=2, ensure_ascii=False)

    # Quick summary statistics.
    level_1 = len(taxonomy)
    level_2 = sum(len(v) for v in taxonomy.values())
    level_3 = sum(len(vv) for v in taxonomy.values() for vv in v.values())
    level_4 = sum(
        len(vvv)
        for v in taxonomy.values()
        for vv in v.values()
        for vvv in vv.values()
    )

    print(f"Written  : {OUTPUT_FILE}")
    print(f"Level 1 (families) : {level_1}")
    print(f"Level 2 terms      : {level_2}")
    print(f"Level 3 terms      : {level_3}")
    print(f"Level 4 terms      : {level_4}")
    print(f"Total terms        : {level_1 + level_2 + level_3 + level_4}")


if __name__ == "__main__":
    main()
