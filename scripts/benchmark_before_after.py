#!/usr/bin/env python3
"""
Before/after style benchmark for recent perf-related changes.

1) Simulated customer master fetch (paginated API walk): two refreshes without cache vs with TTL cache.
2) Optional live FastAPI /customer first vs second call (same worker; tests network + server).

Run from repo root: python scripts/benchmark_before_after.py
"""

from __future__ import annotations

import os
import statistics
import sys
import time

# Repo root on path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_ROOT, ".env"), override=True)
except Exception:
    pass


def _pct_improve(before: float, after: float) -> str:
    if before <= 0:
        return "n/a"
    return f"{100.0 * (before - after) / before:.1f}% faster"


def bench_simulated_paginated_customer_fetch(
    *,
    pages: int = 5,
    latency_ms_per_page: float = 25.0,
    rounds: int = 5,
) -> tuple[float, float]:
    """
    Old behaviour: each 'dashboard refresh' walks all pages sequentially.
    New behaviour: second refresh within TTL hits in-process cache (0 extra 'API' work).

    Returns (mean_ms_before, mean_ms_after) over `rounds` trials.
    """
    from utils.ttl_cache import TtlCache

    delay = latency_ms_per_page / 1000.0

    def paginated_walk():
        for _ in range(pages):
            time.sleep(delay)
        return pages

    cache = TtlCache(default_ttl_seconds=3600.0)
    before_samples = []
    after_samples = []

    for _ in range(rounds):
        # Before: two full walks (no master cache)
        t0 = time.perf_counter()
        paginated_walk()
        paginated_walk()
        before_samples.append((time.perf_counter() - t0) * 1000.0)

        # After: first walk loads cache, second is hit (same as sql_api_master_cache pattern)
        cache.clear()
        t0 = time.perf_counter()
        cache.get_or_load("customer_all_v1", paginated_walk)
        cache.get_or_load("customer_all_v1", paginated_walk)
        after_samples.append((time.perf_counter() - t0) * 1000.0)

    return statistics.mean(before_samples), statistics.mean(after_samples)


def bench_live_customer_page(url: str, headers: dict | None, runs: int = 5) -> tuple[float | None, float | None]:
    """Mean latency run 1 vs mean of runs 2..N for GET /customer?page1 (connection reuse)."""
    import requests

    times = []
    for i in range(runs):
        t0 = time.perf_counter()
        r = requests.get(url, headers=headers or None, params={"offset": 0, "limit": 50}, timeout=30)
        times.append((time.perf_counter() - t0) * 1000.0)
        if r.status_code >= 400:
            return None, None
    first = times[0]
    rest_mean = statistics.mean(times[1:]) if len(times) > 1 else times[0]
    return first, rest_mean


def main() -> int:
    rows = []

    b_sim, a_sim = bench_simulated_paginated_customer_fetch()
    rows.append(
        (
            "Simulated: two full customer paginations vs TTL cache (5 pages x 25 ms each walk)",
            f"{b_sim:.0f}",
            f"{a_sim:.0f}",
            _pct_improve(b_sim, a_sim),
        )
    )

    # Parallel vs sequential PHP-style line posts (admin update-order change)
    from concurrent.futures import ThreadPoolExecutor

    line_calls = 8
    line_delay_ms = 20.0
    line_sleep = line_delay_ms / 1000.0

    seq_samples = []
    par_samples = []
    for _ in range(5):
        t0 = time.perf_counter()
        for _ in range(line_calls):
            time.sleep(line_sleep)
        seq_samples.append((time.perf_counter() - t0) * 1000.0)

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=min(8, line_calls)) as pool:
            list(pool.map(lambda _: time.sleep(line_sleep), range(line_calls)))
        par_samples.append((time.perf_counter() - t0) * 1000.0)

    b_par = statistics.mean(seq_samples)
    a_par = statistics.mean(par_samples)
    rows.append(
        (
            f"Simulated: {line_calls} order-line updates sequential vs parallel ( {line_delay_ms:.0f} ms each)",
            f"{b_par:.0f}",
            f"{a_par:.0f}",
            _pct_improve(b_par, a_par),
        )
    )

    fast = (os.getenv("BENCHMARK_FASTAPI_URL") or os.getenv("FASTAPI_BASE_URL") or "").strip().rstrip("/")
    ak = (os.getenv("BENCHMARK_ACCESS_KEY") or os.getenv("API_ACCESS_KEY") or "").strip()
    sk = (os.getenv("BENCHMARK_SECRET_KEY") or os.getenv("API_SECRET_KEY") or "").strip()
    headers = {}
    if ak and sk:
        headers["X-Access-Key"] = ak
        headers["X-Secret-Key"] = sk

    if fast:
        url = f"{fast}/customer"
        first, warmed = bench_live_customer_page(url, headers if headers else None)
        if first is not None and warmed is not None:
            rows.append(
                (
                    "Live: GET /customer (page 1), 1st vs mean of runs 2–5 (HTTP reuse)",
                    f"{first:.0f}",
                    f"{warmed:.0f}",
                    _pct_improve(first, warmed),
                )
            )
        else:
            rows.append(
                (
                    "Live: GET /customer (skipped: unreachable or non-200)",
                    "n/a",
                    "n/a",
                    "start FastAPI + keys",
                )
            )
    else:
        rows.append(
            (
                "Live: GET /customer",
                "n/a",
                "n/a",
                "set BENCHMARK_FASTAPI_URL",
            )
        )

    print()
    print("| Test case | Before (approx.) | After (approx.) | Improvement |")
    print("|-----------|------------------|-----------------|-------------|")
    for name, b, a, imp in rows:
        print(f"| {name} | {b} ms | {a} ms | {imp} |")
    print()
    print(
        "Notes: "
        "Simulated row models repeated `_fetch_all_customers_from_sql_api` style work without vs with `sql_api_master_cache`. "
        "Live row compares first HTTP GET to warmed connection only (server-side unchanged)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
