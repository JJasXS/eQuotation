#!/usr/bin/env python3
"""Extract the large inline <script> from precurement.html into static/js/procurement/."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "templates" / "precurement" / "precurement.html"
OUT_DIR = ROOT / "static" / "js" / "procurement"
APP_JS = OUT_DIR / "precurement_app.js"
HELPERS_JS = OUT_DIR / "procurement_helpers.js"
STOCK_JS = OUT_DIR / "procurement_stock_card.js"
VIEW_JS = OUT_DIR / "procurement_view_pr.js"
CREATE_JS = OUT_DIR / "procurement_create_pr.js"


def _extract_function(source: str, name: str) -> tuple[str, str] | None:
    """Return (chunk, source_without_chunk) for a top-level ``function name``."""
    needle = f"function {name}("
    start = source.find(needle)
    if start < 0:
        return None
    line_start = source.rfind("\n", 0, start) + 1
    brace = source.find("{", start)
    if brace < 0:
        return None
    depth = 0
    i = brace
    while i < len(source):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                if end < len(source) and source[end] == "\n":
                    end += 1
                chunk = source[line_start:end]
                return chunk, source[:line_start] + source[end:]
        i += 1
    return None


def main() -> None:
    text = HTML.read_text(encoding="utf-8")
    pattern = re.compile(r"(<script(?![^>]*\bsrc=)[^>]*>)(.*?)(</script>)", re.I | re.S)
    matches = list(pattern.finditer(text))
    if not matches:
        raise SystemExit("No inline <script> found")
    best = max(matches, key=lambda m: len(m.group(2)))
    remaining = best.group(2).strip("\n") + "\n"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    helper_names = (
        "escapeHtml",
        "escapeJs",
        "formatMoney",
        "formatPrDate",
        "formatUdfStatusLabel",
        "normalizeUdfStatus",
    )
    helper_chunks: list[str] = []
    for name in helper_names:
        found = _extract_function(remaining, name)
        if not found:
            continue
        chunk, remaining = found
        helper_chunks.append(chunk.rstrip() + "\n\n")

    # Feature stubs document planned splits; keep behavior in precurement_app.js for now.
    STOCK_JS.write_text(
        "/** Stock-card feature module (planned split from precurement_app.js). */\n"
        "window.ProcurementStockCard = window.ProcurementStockCard || {};\n",
        encoding="utf-8",
        newline="\n",
    )
    VIEW_JS.write_text(
        "/** View e-PR feature module (planned split from precurement_app.js). */\n"
        "window.ProcurementViewPr = window.ProcurementViewPr || {};\n",
        encoding="utf-8",
        newline="\n",
    )
    CREATE_JS.write_text(
        "/** Create/edit e-PR feature module (planned split from precurement_app.js). */\n"
        "window.ProcurementCreatePr = window.ProcurementCreatePr || {};\n",
        encoding="utf-8",
        newline="\n",
    )

    if helper_chunks:
        HELPERS_JS.write_text("".join(helper_chunks), encoding="utf-8", newline="\n")
    else:
        HELPERS_JS.write_text(
            "/** Procurement display helpers — populated by extract_precurement_js.py. */\n",
            encoding="utf-8",
            newline="\n",
        )

    APP_JS.write_text(remaining, encoding="utf-8", newline="\n")

    script_tags = (
        "\n"
        '    <script src="/static/js/procurement/procurement_helpers.js?v=20260813_extract"></script>\n'
        '    <script src="/static/js/procurement/procurement_stock_card.js?v=20260813_extract"></script>\n'
        '    <script src="/static/js/procurement/procurement_view_pr.js?v=20260813_extract"></script>\n'
        '    <script src="/static/js/procurement/procurement_create_pr.js?v=20260813_extract"></script>\n'
        '    <script src="/static/js/procurement/precurement_app.js?v=20260813_extract"></script>\n'
    )
    new_text = text[: best.start()] + script_tags + text[best.end() :]
    HTML.write_text(new_text, encoding="utf-8", newline="\n")

    print(f"HTML lines: {new_text.count(chr(10)) + 1}")
    print(f"APP_JS lines: {APP_JS.read_text(encoding='utf-8').count(chr(10)) + 1}")
    print(f"HELPERS_JS lines: {HELPERS_JS.read_text(encoding='utf-8').count(chr(10)) + 1}")


if __name__ == "__main__":
    main()
