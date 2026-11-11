"""Full-function Firebird connection close audit (read-only)."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PERF = Path(__file__).resolve().parent
sys.path.insert(0, str(PERF))
from bench_common import INVESTIGATION_DIR, ensure_dirs, write_json  # noqa: E402

TARGETS = [
    REPO / "main.py",
    REPO / "utils" / "procurement_purchase_request.py",
    REPO / "utils" / "quotation_api.py",
    REPO / "utils" / "procurement_bidding.py",
    REPO / "utils" / "procurement_stock_card_queries.py",
]


def audit_file(path: Path) -> list[dict]:
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [{"file": str(path.relative_to(REPO)), "error": str(exc)}]
    lines = src.splitlines()
    findings = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            self._check(node)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self._check(node)
            self.generic_visit(node)

        def _check(self, node):
            # Function source slice
            start = node.lineno - 1
            end = (node.end_lineno or node.lineno)
            body = "\n".join(lines[start:end])
            if "get_db_connection(" not in body:
                return
            if "with db_connection(" in body:
                return
            opens = body.count("get_db_connection(")
            closes = body.count(".close(")
            # Heuristic: if opens and no close at all -> suspect
            if opens and closes == 0:
                findings.append(
                    {
                        "file": str(path.relative_to(REPO)).replace("\\", "/"),
                        "function": node.name,
                        "line": node.lineno,
                        "opens": opens,
                        "closes": closes,
                        "severity": "high",
                        "note": "get_db_connection without any .close() in function body",
                    }
                )
            elif opens and "finally:" not in body and "with " not in body:
                findings.append(
                    {
                        "file": str(path.relative_to(REPO)).replace("\\", "/"),
                        "function": node.name,
                        "line": node.lineno,
                        "opens": opens,
                        "closes": closes,
                        "severity": "medium",
                        "note": "get_db_connection without finally/with — verify closes on all paths",
                    }
                )

    Visitor().visit(tree)
    return findings


def main() -> int:
    ensure_dirs()
    all_findings = []
    for p in TARGETS:
        if p.is_file():
            all_findings.extend(audit_file(p))
    out = {
        "findings": all_findings,
        "high": [f for f in all_findings if f.get("severity") == "high"],
        "medium": [f for f in all_findings if f.get("severity") == "medium"],
    }
    write_json(INVESTIGATION_DIR / "db_close_audit.json", out)
    print(f"[perf] db close audit high={len(out['high'])} medium={len(out['medium'])}")
    for f in out["high"][:20]:
        print(f"  HIGH {f['file']}:{f['line']} {f['function']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
