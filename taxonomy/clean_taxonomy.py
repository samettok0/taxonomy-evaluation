"""
IEEE Taxonomy — Data Cleaning & Tree Construction
==================================================

Part 1  – Data Cleaning
    Reads ieee-taxonomy.txt, removes boilerplate / noise / page numbers,
    and joins term-continuation fragments that were split across page breaks.

Part 2  – Tree Construction
    Parses the cleaned lines by counting leading dots (groups of 4) to
    determine each term's depth level, then builds a nested dictionary that
    mirrors the parent-child hierarchy.  Exports the tree to JSON.

Edge cases handled
------------------
1. Empty lines or whitespace-only lines.
2. Form-feed characters (\\x0c / \\f).
3. Page number lines  (e.g. "Page 2", "Page 34").
4. Known boilerplate substrings (license, header, description paragraphs).
5. Standalone header fragments that appear on their own line in the PDF
   header block (e.g. "January 2026", "Version", "1.05", "(IEEE)", …).
6. Taxonomy term names that were split across a line/page break:
   the continuation fragment starts with a lowercase letter because it is
   the second word(s) of a multi-word term.  After all noise is removed,
   such a fragment is appended (space-joined) to the preceding kept line.
7. Duplicate term names within the same parent — the taxonomy allows a term
   to appear more than once; we merge them into a single node so that
   children from both occurrences live under one key.
"""

import json
import re

INPUT_FILE     = "taxonomy/ieee-taxonomy.txt"
CLEANED_FILE   = "taxonomy/ieee-taxonomy-cleaned.txt"
JSON_FILE      = "ieee_taxonomy_final.json"
DOT_GROUP_SIZE = 4  # number of dots per indent level

# ═══════════════════════════════════════════════════════════════════════════
#  Part 1 — Data Cleaning
# ═══════════════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# Noise detection
# ---------------------------------------------------------------------------

# Substrings — any line containing one of these is boilerplate.
BOILERPLATE_SUBSTRINGS = [
    'January 2026 IEEE Taxonomy',
    'Version 1.05',
    'Created by',
    'The Institute of Electrical and Electronics Engineers',
    'IEEE Taxonomy: A Subset Hierarchical Display',
    'The IEEE Taxonomy comprises the first three hierarchical',
    'branch) that is formed from the top-most terms',
    'term-families are arranged alphabetically',
    'hierarchy goes to no more than three sublevels',
    'preceding the next level terms. A term can appear',
    'can appear more than once in any particular hierarchy',
    'way so that it is always a subset',
    'This work is licensed under the Creative Commons',
    'International License (CC BY-NC-ND',
    'Engineers (IEEE) for the benefit of humanity.',
]

# Exact stripped content — the cover-page header is split across many lines
# in the PDF extraction, each appearing alone on its own line.
STANDALONE_NOISE = {
    'January 2026',
    'IEEE Taxonomy',
    'Version',
    '1.05',
    'The Institute of',
    'Electrical and',
    'Electronics Engineers',
    '(IEEE)',
}

# Matches "Page 2", "Page 34", etc.
PAGE_NUMBER_RE = re.compile(r'^\s*Page\s+\d+\s*$', re.IGNORECASE)


def is_noise(raw_line: str) -> bool:
    """Return True if this raw line should be completely discarded."""
    line = raw_line.rstrip('\n')
    stripped = line.strip()

    if not stripped:                         # 1. empty / whitespace only
        return True
    if '\x0c' in line:                       # 2. form-feed character
        return True
    if PAGE_NUMBER_RE.match(stripped):       # 3. page number
        return True
    if stripped in STANDALONE_NOISE:         # 5. isolated header fragments
        return True
    for fragment in BOILERPLATE_SUBSTRINGS:  # 4. boilerplate substrings
        if fragment in line:
            return True
    return False


# ---------------------------------------------------------------------------
# Continuation detection
# ---------------------------------------------------------------------------

def is_continuation(line: str) -> bool:
    """
    Return True if this line is the tail of a term that was split across a
    page/line break.

    A genuine taxonomy entry always starts with:
      - one or more dots  (indented term), OR
      - an uppercase letter (top-level category).

    A continuation fragment starts with a lowercase letter because it is
    the second (or later) word of a multi-word term name whose first part
    ended on the previous line.  Examples seen in the file:
        '........Electromagnetic propagation in absorbing'  ← kept
        'media'                                             ← continuation
        '............Direct-sequence code-division multiple' ← kept
        'access'                                            ← continuation
        'Electromagnetic compatibility and'                 ← kept
        'interference'                                      ← continuation
    """
    s = line.strip()
    if not s:
        return False
    # Starts with a dot → it's a regular (possibly deeply indented) term.
    if line.startswith('.'):
        return False
    # Starts with uppercase → top-level category name.
    if s[0].isupper():
        return False
    # Everything else (starts lowercase) is a continuation fragment.
    return True


# ---------------------------------------------------------------------------
# Part 1 pipeline — clean & merge
# ---------------------------------------------------------------------------

def _count_leading_dots(line: str) -> int:
    """Return the number of leading dot characters in a line."""
    n = 0
    for ch in line:
        if ch == '.':
            n += 1
        else:
            break
    return n


def clean_taxonomy(input_path: str, cleaned_path: str) -> list[str]:
    """
    Read the raw taxonomy file, remove all noise, join continuation
    fragments, write cleaned lines to disk, and return the cleaned list.
    """
    # ── Pass 1: discard all noise ──────────────────────────────────────────
    with open(input_path, 'r', encoding='utf-8') as fh:
        raw_lines = fh.readlines()

    kept_after_filter: list[str] = []
    n_noise = 0
    for raw in raw_lines:
        if is_noise(raw):
            n_noise += 1
        else:
            kept_after_filter.append(raw.rstrip('\n'))

    # ── Pass 2: join LOWERCASE continuation fragments ──────────────────────
    # A line starting with a lowercase letter (no dots) is always a
    # continuation of the previous entry (e.g. "media", "access").
    after_pass2: list[str] = []
    n_joined_lower = 0
    for line in kept_after_filter:
        if is_continuation(line) and after_pass2:
            after_pass2[-1] = after_pass2[-1] + ' ' + line.strip()
            n_joined_lower += 1
        else:
            after_pass2.append(line)

    # ── Pass 3: join UPPERCASE continuation fragments ──────────────────────
    # Some term names that span a page break start with an uppercase letter
    # (e.g. "............Intergovernmental Panel on Climate" / "Change").
    # These are NOT real top-level categories.
    #
    # Detection rule:  A non-dotted line is a continuation if the NEXT line
    # has indentation deeper than level 1 (more than 4 leading dots).
    # Real top-level categories always have level-1 (4-dot) children or are
    # followed by another root category / EOF.
    merged: list[str] = []
    n_joined_upper = 0
    for i, line in enumerate(after_pass2):
        if line.startswith('.') or not line.strip():
            merged.append(line)
            continue

        # Look ahead: what depth is the next non-empty line?
        next_dots = 0
        if i + 1 < len(after_pass2):
            next_dots = _count_leading_dots(after_pass2[i + 1])

        # If the next line has > 4 dots (deeper than level 1), this line
        # cannot be a genuine root category — it's a continuation fragment.
        if next_dots > DOT_GROUP_SIZE and merged and merged[-1].strip():
            merged[-1] = merged[-1] + ' ' + line.strip()
            n_joined_upper += 1
        else:
            merged.append(line)

    n_joined = n_joined_lower + n_joined_upper

    # ── Write cleaned text file ────────────────────────────────────────────
    with open(cleaned_path, 'w', encoding='utf-8') as fh:
        for line in merged:
            fh.write(line + '\n')

    print("── Part 1: Data Cleaning ──────────────────────────────────")
    print(f"  Input lines      : {len(raw_lines)}")
    print(f"  Noise removed    : {n_noise}")
    print(f"  Fragments joined : {n_joined}  (lowercase: {n_joined_lower}, uppercase: {n_joined_upper})")
    print(f"  Output lines     : {len(merged)}")
    print(f"  Written to       : {cleaned_path}")

    return merged


# ═══════════════════════════════════════════════════════════════════════════
#  Part 2 — Tree Construction
# ═══════════════════════════════════════════════════════════════════════════

# Hierarchy encoding in the taxonomy file:
#
#   Level 0 (root categories) : no leading dots       → depth 0
#   Level 1                   : 4 leading dots  (....)   → depth 1
#   Level 2                   : 8 leading dots  (........) → depth 2
#   Level 3                   : 12 leading dots (............) → depth 3
#
# Each group of 4 dots adds one level of nesting.




def parse_line(line: str) -> tuple[int, str]:
    """
    Parse a single cleaned taxonomy line.

    Returns
    -------
    depth : int
        The nesting level (0–3).  Computed as (number of leading dots) / 4.
    name  : str
        The clean category name with all leading dots and surrounding
        whitespace removed.
    """
    # Count how many leading dots the line has.
    n_dots = 0
    for ch in line:
        if ch == '.':
            n_dots += 1
        else:
            break

    depth = n_dots // DOT_GROUP_SIZE
    name = line[n_dots:].strip()  # strip dots then whitespace
    return depth, name


def build_tree(lines: list[str]) -> dict:
    """
    Build a nested dictionary from the cleaned taxonomy lines.

    Algorithm — parent-stack tracking
    ----------------------------------
    We maintain a *stack* (Python list) of references to the dictionaries
    at each depth level that form the current path from root to the most
    recently seen node.

        stack[0]  →  the top-level root dict  (contains all level-0 entries)
        stack[1]  →  the dict of the most recent level-0 entry
        stack[2]  →  the dict of the most recent level-1 entry
        ...

    When we encounter a term at depth *d*:

    1.  The term's parent is the dict at  stack[d]  (one level above).
    2.  We create a new empty dict for this term inside its parent, or
        reuse an existing dict if the same name was already inserted
        (duplicate terms are allowed in the IEEE Taxonomy).
    3.  We record this new dict at  stack[d + 1]  so that any deeper
        entries that follow can attach themselves as its children.
    4.  We truncate the stack to length  d + 2  (discarding stale
        references from a previous deeper branch).

    This approach handles arbitrary jumps back to a shallower depth
    correctly (e.g. going from depth 3 directly back to depth 1) because
    the stack always reflects the most recent ancestor at every level.

    Returns
    -------
    tree : dict
        A nested dictionary.  Top-level keys are the 53 root categories.
        Each value is recursively a dict of child terms → their children.
        Leaf terms map to an empty dict {}.
    """
    # The root dict that will hold all level-0 entries as keys.
    tree: dict = {}

    # The stack of ancestor dicts.
    # stack[0] is always `tree` itself (the container for level-0 entries).
    stack: list[dict] = [tree]

    for line in lines:
        if not line.strip():
            continue  # skip any residual blank lines

        depth, name = parse_line(line)

        # --- Locate the parent dict for this depth ---
        # The parent is at stack[depth].  For a level-0 entry (depth 0),
        # the parent is `tree` itself (stack[0]).  For a level-1 entry
        # (depth 1), the parent is the dict of the most recent level-0
        # entry (stack[1]), and so on.
        parent = stack[depth]

        # --- Insert or reuse the child node ---
        # If this term name already exists under the same parent (duplicate
        # terms are permitted in the IEEE Taxonomy), we reuse the existing
        # dict so additional children get merged into it.
        if name not in parent:
            parent[name] = {}
        child_node = parent[name]

        # --- Update the stack ---
        # Record this node's dict at the next stack position so that
        # subsequent deeper entries will attach as its children.
        # Truncate anything beyond that (stale from an earlier deeper
        # branch that has ended).
        if len(stack) > depth + 1:
            stack[depth + 1] = child_node
            # Trim stale deeper entries.
            del stack[depth + 2:]
        else:
            stack.append(child_node)

    return tree


def export_tree(tree: dict, json_path: str) -> None:
    """Write the tree to a JSON file with 4-space indentation."""
    with open(json_path, 'w', encoding='utf-8') as fh:
        json.dump(tree, fh, indent=4, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════
#  Main — run both parts
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    # Part 1: clean the raw file
    cleaned_lines = clean_taxonomy(INPUT_FILE, CLEANED_FILE)

    # Part 2: build and export the tree
    tree = build_tree(cleaned_lines)

    # Quick stats
    n_level0 = len(tree)
    n_level1 = sum(len(v) for v in tree.values())
    n_level2 = sum(len(c) for v in tree.values() for c in v.values())
    n_level3 = sum(
        len(gc)
        for v in tree.values()
        for c in v.values()
        for gc in c.values()
    )

    print()
    print("── Part 2: Tree Construction ──────────────────────────────")
    print(f"  Level 0 (root categories) : {n_level0}")
    print(f"  Level 1 entries           : {n_level1}")
    print(f"  Level 2 entries           : {n_level2}")
    print(f"  Level 3 entries           : {n_level3}")

    export_tree(tree, JSON_FILE)
    print(f"  Tree exported to          : {JSON_FILE}")


if __name__ == "__main__":
    main()
