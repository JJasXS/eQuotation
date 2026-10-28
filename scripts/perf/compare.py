"""Merge before/after JSON artifacts into comparison tables."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PERF_DIR = Path(__file__).resolve().parent
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

from bench_common import RESULTS_DIR, load_json, write_json  # noqa: E402


def _med(block: dict | None, key: str = "median"):
    if not block:
        return None
    return block.get(key)


def _delta(before, after):
    if before is None or after is None:
        return None
    try:
        b = float(before)
        a = float(after)
    except Exception:
        return None
    return round(a - b, 2)


def _pct(before, after):
    if before in (None, 0) or after is None:
        return None
    try:
        b = float(before)
        a = float(after)
        if b == 0:
            return None
        return round(100.0 * (a - b) / b, 2)
    except Exception:
        return None


def compare_pages(before: dict, after: dict) -> list[dict[str, Any]]:
    rows = []
    bpages = before.get("pages") or {}
    apages = after.get("pages") or {}
    for page_id in sorted(set(bpages) | set(apages)):
        bp = bpages.get(page_id) or {}
        ap = apages.get(page_id) or {}
        for mode in ("cold", "warm"):
            bm = bp.get(mode) or {}
            am = ap.get(mode) or {}
            b_idle = _med((bm.get("network_idle_ms") or {}))
            a_idle = _med((am.get("network_idle_ms") or {}))
            b_bytes = _med((bm.get("bytes") or {}))
            a_bytes = _med((am.get("bytes") or {}))
            b_req = _med((bm.get("request_count") or {}))
            a_req = _med((am.get("request_count") or {}))
            rows.append(
                {
                    "page": page_id,
                    "mode": mode,
                    "before_status": bm.get("status") or bp.get("status"),
                    "after_status": am.get("status") or ap.get("status"),
                    "before_network_idle_ms": b_idle,
                    "after_network_idle_ms": a_idle,
                    "delta_network_idle_ms": _delta(b_idle, a_idle),
                    "pct_network_idle": _pct(b_idle, a_idle),
                    "before_bytes": b_bytes,
                    "after_bytes": a_bytes,
                    "delta_bytes": _delta(b_bytes, a_bytes),
                    "before_requests": b_req,
                    "after_requests": a_req,
                    "delta_requests": _delta(b_req, a_req),
                }
            )
    return rows


def compare_concurrency(before: dict, after: dict) -> list[dict[str, Any]]:
    rows = []
    blevels = {x["users"]: x for x in (before.get("levels") or [])}
    alevels = {x["users"]: x for x in (after.get("levels") or [])}
    for users in sorted(set(blevels) | set(alevels)):
        b = blevels.get(users) or {}
        a = alevels.get(users) or {}
        bmed = _med((b.get("latency_ms") or {}))
        amed = _med((a.get("latency_ms") or {}))
        rows.append(
            {
                "users": users,
                "before_rps": b.get("throughput_rps"),
                "after_rps": a.get("throughput_rps"),
                "before_latency_ms": bmed,
                "after_latency_ms": amed,
                "delta_latency_ms": _delta(bmed, amed),
                "before_error_rate": b.get("error_rate"),
                "after_error_rate": a.get("error_rate"),
                "before_mem_mb": (b.get("server") or {}).get("WorkingSetMB"),
                "after_mem_mb": (a.get("server") or {}).get("WorkingSetMB"),
            }
        )
    return rows


def compare_idle(before: dict, after: dict) -> list[dict[str, Any]]:
    rows = []
    bpages = before.get("pages") or {}
    apages = after.get("pages") or {}
    for page_id in sorted(set(bpages) | set(apages)):
        b = bpages.get(page_id) or {}
        a = apages.get(page_id) or {}
        rows.append(
            {
                "page": page_id,
                "before_idle_15": b.get("idle_requests_15"),
                "after_idle_15": a.get("idle_requests_15"),
                "before_idle_30": b.get("idle_requests_30"),
                "after_idle_30": a.get("idle_requests_30"),
                "delta_idle_30": _delta(b.get("idle_requests_30"), a.get("idle_requests_30")),
            }
        )
    rows.append(
        {
            "page": "_visibility",
            "before_visibility_triggered_requests": before.get("visibility_triggered_requests"),
            "after_visibility_triggered_requests": after.get("visibility_triggered_requests"),
        }
    )
    return rows


def build() -> dict[str, Any]:
    def _load(name: str) -> dict:
        path = RESULTS_DIR / name
        if not path.is_file():
            return {"status": "NOT RUN", "blocker": f"missing {path.name}"}
        return load_json(path)

    before_pages = _load("pages_before.json")
    after_pages = _load("pages_after.json")
    before_conc = _load("concurrency_before.json")
    after_conc = _load("concurrency_after.json")
    before_idle = _load("idle_before.json")
    after_idle = _load("idle_after.json")
    before_all = _load("before.json")
    after_all = _load("after.json")

    comparison = {
        "pages": compare_pages(before_pages, after_pages) if before_pages.get("pages") else [],
        "concurrency": compare_concurrency(before_conc, after_conc) if before_conc.get("levels") else [],
        "idle": compare_idle(before_idle, after_idle) if before_idle.get("pages") else [],
        "pytest_before": (before_all.get("pytest") if isinstance(before_all, dict) else None),
        "pytest_after": (after_all.get("pytest") if isinstance(after_all, dict) else None),
    }
    write_json(RESULTS_DIR / "comparison.json", comparison)
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    comparison = build()
    print(f"[perf] comparison pages={len(comparison['pages'])} conc={len(comparison['concurrency'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
