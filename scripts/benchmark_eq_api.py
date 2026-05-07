#!/usr/bin/env python3
"""
Measure HTTP latencies for eQuotation / SQL API style endpoints.

Usage (from project root, with .env loaded or env vars set):
  python scripts/benchmark_eq_api.py

Env:
  BENCHMARK_BASE_URL   — Flask app, e.g. http://127.0.0.1:8880
  BENCHMARK_FASTAPI_URL — FastAPI, e.g. http://127.0.0.1:8000
  BENCHMARK_ACCESS_KEY / BENCHMARK_SECRET_KEY — optional API headers

Output: TSV table to stdout; run before/after optimizations and diff manually.
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from typing import Any
from urllib.parse import urljoin

import requests

try:
    from dotenv import load_dotenv

    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(_root, ".env"), override=True)
except Exception:
    pass


def _ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000.0


def time_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    runs: int = 3,
    timeout: float = 60.0,
) -> tuple[float, int | None, int]:
    """Return (mean_ms, status_code, approx_response_bytes)."""
    times: list[float] = []
    last_status = None
    last_len = 0
    for _ in range(max(1, runs)):
        t0 = time.perf_counter()
        r = requests.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=timeout,
        )
        times.append(_ms(t0))
        last_status = r.status_code
        last_len = len(r.content or b"")
    return statistics.mean(times), last_status, last_len


def main() -> int:
    base = (os.getenv("BENCHMARK_BASE_URL") or "http://127.0.0.1:8880").rstrip("/")
    fast = (os.getenv("BENCHMARK_FASTAPI_URL") or "http://127.0.0.1:8000").rstrip("/")
    ak = (os.getenv("BENCHMARK_ACCESS_KEY") or os.getenv("API_ACCESS_KEY") or "").strip()
    sk = (os.getenv("BENCHMARK_SECRET_KEY") or os.getenv("API_SECRET_KEY") or "").strip()
    headers: dict[str, str] = {}
    if ak and sk:
        headers["X-Access-Key"] = ak
        headers["X-Secret-Key"] = sk

    rows: list[tuple[str, str, float, int | None, int, str]] = []

    def add(name: str, method: str, url: str, **kwargs: Any) -> None:
        mean_ms, st, nbytes = time_request(method, url, headers=headers if headers else None, **kwargs)
        note = "ok" if st and st < 400 else f"http {st}"
        rows.append((name, url, mean_ms, st, nbytes, note))

    # FastAPI
    add("Health (FastAPI)", "GET", f"{fast}/health")
    add("Customer list page1", "GET", f"{fast}/customer", params={"offset": 0, "limit": 50})

    # Flask admin (require session in real tests — may 401 without cookies)
    add("Admin customer status (Flask)", "GET", f"{base}/api/admin/customer_status_summary")
    add("Procurement stock-card (Flask)", "GET", f"{base}/api/admin/procurement/stock-card")

    print("Feature / Test case\tURL\tmean_ms (3 runs)\tstatus\tbytes\tnote")
    for name, url, mean_ms, st, nbytes, note in rows:
        print(f"{name}\t{url}\t{mean_ms:.0f}\t{st}\t{nbytes}\t{note}")
    print()
    print("Fill a 'Before' and 'After' sheet from two runs; compute Improvement% = (before-after)/before.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
