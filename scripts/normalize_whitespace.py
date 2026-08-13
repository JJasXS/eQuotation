#!/usr/bin/env python3
"""Collapse runs of 2+ blank lines to a single blank line.

Safe for HTML/JS/CSS/Python sources that do not rely on significant blank
runs (e.g. no <pre> blocks). Use --check to report without writing.

Usage:
  py scripts/normalize_whitespace.py path/to/file.html
  py scripts/normalize_whitespace.py --check path/to/file.html
  py scripts/normalize_whitespace.py templates/precurement/precurement.html templates/adminBidding.html
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_BLANK_RUN = re.compile(r"\n{3,}")


def normalize(text: str) -> str:
    # Normalize newlines first, then collapse 2+ blank lines (3+ newlines) to one blank.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _BLANK_RUN.sub("\n\n", text)
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def process(path: Path, *, check: bool) -> int:
    original = path.read_text(encoding="utf-8")
    updated = normalize(original)
    if original == updated:
        print(f"OK   {path} (unchanged)")
        return 0
    before = original.count("\n") + (0 if original.endswith("\n") else 1)
    after = updated.count("\n")
    if check:
        print(f"DIRTY {path} ({before} -> {after} lines)")
        return 1
    path.write_text(updated, encoding="utf-8", newline="\n")
    print(f"FIXED {path} ({before} -> {after} lines)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--check", action="store_true", help="Report only; exit 1 if dirty")
    args = parser.parse_args(argv)
    status = 0
    for path in args.paths:
        if not path.is_file():
            print(f"MISSING {path}", file=sys.stderr)
            status = 1
            continue
        status = max(status, process(path, check=args.check))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
