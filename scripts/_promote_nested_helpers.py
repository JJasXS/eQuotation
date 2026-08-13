#!/usr/bin/env python3
"""Promote nested helpers in main.py to utils.pr_route_helpers imports."""
from __future__ import annotations

import re
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "main.py"

NESTED_SIGS = [
    "def _status_text(",
    "def _num(",
    "def _truthy(",
    "def _fmt_date(",
    "def _fb_text(",
    "def _normalize_currency(",
    "def _resolve_supplier_master(",
    "def _to_bool_or_none(",
]


def remove_all_nested(source: str, sig: str) -> tuple[str, int]:
    removed = 0
    pos = 0
    while True:
        idx = source.find(sig, pos)
        if idx < 0:
            break
        line_start = source.rfind("\n", 0, idx) + 1
        indent = source[line_start:idx]
        if indent == "":
            # top-level — skip
            pos = idx + len(sig)
            continue
        colon = source.find(":", idx)
        if colon < 0:
            break
        nl = source.find("\n", colon)
        if nl < 0:
            break
        body_start = nl + 1
        i = body_start
        end = body_start
        while i < len(source):
            line_end = source.find("\n", i)
            if line_end < 0:
                line_end = len(source)
            line = source[i:line_end]
            if line.strip() == "":
                end = line_end + (1 if line_end < len(source) else 0)
                i = end
                continue
            m = re.match(r"[ \t]*", line)
            line_indent = m.group(0) if m else ""
            if len(line_indent) <= len(indent):
                break
            end = line_end + (1 if line_end < len(source) else 0)
            i = end
        source = source[:line_start] + source[end:]
        removed += 1
        # continue from line_start (content shifted)
        pos = line_start
    return source, removed


def main() -> None:
    text = MAIN.read_text(encoding="utf-8")
    total = 0
    for sig in NESTED_SIGS:
        text, n = remove_all_nested(text, sig)
        print(f"{sig}: removed {n}")
        total += n

    import_block = (
        "from utils.pr_route_helpers import (\n"
        "    _fb_text,\n"
        "    _fmt_date,\n"
        "    _normalize_currency,\n"
        "    _num,\n"
        "    _resolve_supplier_master,\n"
        "    _status_text,\n"
        "    _to_bool_or_none,\n"
        "    _truthy,\n"
        ")\n"
    )
    if "from utils.pr_route_helpers import" not in text:
        anchor = "from utils.firebird_helpers import _safe_float\n"
        if anchor not in text:
            raise SystemExit("import anchor missing")
        text = text.replace(anchor, anchor + import_block, 1)

    MAIN.write_text(text, encoding="utf-8", newline="\n")
    print(f"total removed nested defs: {total}")
    print(f"main.py lines: {text.count(chr(10)) + 1}")


if __name__ == "__main__":
    main()
