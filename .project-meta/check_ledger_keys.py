#!/usr/bin/env python3
"""Pre-commit invariant: reject duplicate JSON keys in ledger.json.

RFC 8259 §4 says duplicate keys have undefined behaviour — Python's
json.loads() silently keeps the last value, hiding data loss.  This
script parses ledger.json with a strict decoder that raises on any
duplicate key at any nesting depth.

Exit 0 = clean.  Exit 1 = duplicate found (prints the offending key
and its path).  Designed to be called by the daily builder before
every commit that touches ledger.json.

Usage:
    python .project-meta/check_ledger_keys.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LEDGER = Path(__file__).resolve().parent / "ledger.json"


def _check_duplicates(pairs: list[tuple[str, object]], path: str = "$") -> dict:
    """json.loads object_pairs_hook that raises on duplicate keys."""
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            print(f"FAIL: duplicate key {key!r} in object at {path}", file=sys.stderr)
            sys.exit(1)
        seen[key] = value
    return seen


def main() -> None:
    if not LEDGER.exists():
        print(f"SKIP: {LEDGER} not found", file=sys.stderr)
        sys.exit(0)

    text = LEDGER.read_text(encoding="utf-8")
    try:
        json.loads(text, object_pairs_hook=_check_duplicates)
    except json.JSONDecodeError as exc:
        print(f"FAIL: ledger.json is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    print("OK: ledger.json has no duplicate keys")


if __name__ == "__main__":
    main()
