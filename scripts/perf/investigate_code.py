"""Static investigation for the 8 known performance concerns. Read-only."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PERF_DIR = Path(__file__).resolve().parent
REPO_ROOT = PERF_DIR.parents[1]
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

from bench_common import INVESTIGATION_DIR, ensure_dirs, write_json  # noqa: E402


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _largest_files(glob: str, n: int = 5) -> list[dict[str, Any]]:
    files = []
    for p in REPO_ROOT.rglob(glob):
        s = str(p)
        if any(x in s for x in (".venv", "venv", "node_modules", "site-packages", "_staged")):
            continue
        files.append({"path": str(p.relative_to(REPO_ROOT)).replace("\\", "/"), "bytes": p.stat().st_size})
    files.sort(key=lambda x: x["bytes"], reverse=True)
    return files[:n]


def investigate() -> dict[str, Any]:
    ensure_dirs()
    js = _read("static/js/procurement/precurement_app.js")
    ttl = _read("utils/ttl_cache.py")
    main = _read("main.py")

    # Concern 1: eager loadStockCardRows
    dom_idx = js.find("document.addEventListener('DOMContentLoaded'")
    eager_call = False
    eager_line = None
    if dom_idx >= 0:
        chunk = js[dom_idx : dom_idx + 2500]
        if "loadStockCardRows()" in chunk:
            eager_call = True
            eager_line = main.count  # placeholder
            eager_line = js[: dom_idx + chunk.find("loadStockCardRows()")].count("\n") + 1

    # Concern 2: AbortController / fetch
    abort_count = js.count("AbortController")
    fetch_count = len(re.findall(r"\bfetch\s*\(", js))

    # Concern 3: ttl cache cleanup
    has_purge = "purge" in ttl.lower() or "evict" in ttl.lower() or "max_entries" in ttl
    expired_only_on_get = ("del self._store[key]" in ttl) and ("for " not in ttl.split("def get_or_load")[1][:800] if "def get_or_load" in ttl else True)

    # Concern 4: visibilitychange
    vis_idx = js.find("visibilitychange")
    vis_line = js[:vis_idx].count("\n") + 1 if vis_idx >= 0 else None
    has_min_age = "lastLoad" in js[vis_idx : vis_idx + 800] if vis_idx >= 0 else False

    # Concern 5: db connections — look for finally close in surrounding 120 lines
    leak_suspects = []
    lines = main.splitlines()
    for i, line in enumerate(lines):
        if re.search(r"con\s*=\s*get_db_connection\s*\(", line):
            window = "\n".join(lines[i : i + 120])
            if "con.close" not in window and "close()" not in window:
                leak_suspects.append(i + 1)

    # Concern 6: timers
    set_intervals = []
    for rel in [
        "static/js/login.js",
        "static/js/orderQuotation.js",
        "static/js/procurement/precurement_app.js",
        "static/js/viewQuotation.js",
        "static/js/adminViewQuotations.js",
    ]:
        p = REPO_ROOT / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"setInterval\s*\(", text):
            set_intervals.append({"file": rel, "line": text[: m.start()].count("\n") + 1})

    # Concern 7: large files
    large_js = _largest_files("*.js")
    large_py = _largest_files("*.py")

    # Concern 8: requests without timeout in production code
    no_timeout = []
    for p in REPO_ROOT.rglob("*.py"):
        s = str(p)
        if any(x in s for x in (".venv", "venv", "site-packages", "_staged", "scripts/perf")):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"requests\.(get|post|put|delete|request)\s*\(", text):
            chunk = "\n".join(text[m.start() :].splitlines()[:12])
            if "timeout" not in chunk:
                no_timeout.append(
                    {
                        "file": str(p.relative_to(REPO_ROOT)).replace("\\", "/"),
                        "line": text[: m.start()].count("\n") + 1,
                    }
                )

    cache_dicts = {
        "PURCHASE_REQUEST_LIST_CACHE": "PURCHASE_REQUEST_LIST_CACHE" in main,
        "ADMIN_DASHBOARD_API_CACHE": "ADMIN_DASHBOARD_API_CACHE" in main,
        "ttl_cache_sql_api_master": "sql_api_master_cache" in ttl,
    }

    report = {
        "architecture": {
            "entry": "main.py unified Starlette+uvicorn (Flask WSGI + FastAPI mount + /static)",
            "default_port": 8880,
            "db": "Firebird via utils/db_utils.get_db_connection / db_connection contextmanager",
            "background_threads": [
                "utils/tenant_bootstrap.start_tenant_config_refresh_worker (default 24h)",
                "main.py RFQ email daemon threads on PR invite",
                "utils/procurement_purchase_request.py pr-sql-line-sync daemon",
            ],
        },
        "concerns": {
            "1_eager_stock_card": {
                "confirmed": eager_call,
                "evidence": f"loadStockCardRows() inside DOMContentLoaded near line {eager_line}",
                "file": "static/js/procurement/precurement_app.js",
            },
            "2_fetch_timeouts": {
                "confirmed": abort_count <= 1,
                "abort_controllers": abort_count,
                "fetch_calls_in_precurement_app": fetch_count,
                "note": "Writes must never be auto-aborted; only GET reads are candidates for timeout helpers.",
            },
            "3_ttl_cache_growth": {
                "confirmed": not has_purge,
                "expired_only_on_access": True,
                "has_max_entries": "max_entries" in ttl,
                "dict_caches": cache_dicts,
            },
            "4_visibility_refresh": {
                "confirmed": vis_idx >= 0,
                "line": vis_line,
                "has_min_age_guard": has_min_age,
            },
            "5_db_connection_cleanup": {
                "confirmed": len(leak_suspects) > 0,
                "suspect_lines_no_close_in_120": leak_suspects[:30],
                "note": "Many handlers are long; prefer db_connection() contextmanager. Confirm each before changing.",
            },
            "6_timers_workers": {
                "confirmed": len(set_intervals) > 0,
                "setInterval_sites": set_intervals,
                "pagehide_cleanup_present": "pagehide" in js,
            },
            "7_large_files": {
                "confirmed": True,
                "largest_js": large_js,
                "largest_py": large_py,
            },
            "8_external_api_timeouts": {
                "confirmed": len(no_timeout) > 0,
                "no_timeout_sites": no_timeout,
            },
        },
        "inactivity_policy": {
            "pause_polling_when_hidden": True,
            "refresh_on_visible_only_if_older_than_sec": 60,
            "do_not_change_session_expiry": True,
        },
    }
    write_json(INVESTIGATION_DIR / "concerns.json", report)
    return report


def main() -> int:
    report = investigate()
    confirmed = sum(1 for c in report["concerns"].values() if c.get("confirmed"))
    print(f"[perf] investigated {len(report['concerns'])} concerns; confirmed={confirmed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
