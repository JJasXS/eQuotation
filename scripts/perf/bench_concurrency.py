"""Read-only concurrency benchmark with httpx (1/5/10/20 users)."""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any

import httpx

PERF_DIR = Path(__file__).resolve().parent
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

from bench_common import (  # noqa: E402
    READONLY_API_ONLY_PATHS,
    READONLY_API_PATHS,
    RESULTS_DIR,
    base_url,
    ensure_dirs,
    read_bench_pid,
    sample_process,
    seed_session,
    summarize_ms,
    wait_for_server,
    write_json,
)


async def _worker(
    client: httpx.AsyncClient,
    paths: list[str],
    stop_at: float,
    latencies: list[float],
    errors: list[str],
    counters: dict[str, int],
) -> None:
    i = 0
    while time.perf_counter() < stop_at:
        path = paths[i % len(paths)]
        i += 1
        t0 = time.perf_counter()
        try:
            r = await client.get(path, timeout=30.0)
            ms = (time.perf_counter() - t0) * 1000
            latencies.append(ms)
            counters["ok"] = counters.get("ok", 0) + 1
            if r.status_code >= 500:
                errors.append(f"{path} HTTP {r.status_code}")
                counters["http_err"] = counters.get("http_err", 0) + 1
            elif r.status_code >= 400:
                counters["client_err"] = counters.get("client_err", 0) + 1
        except Exception as exc:
            latencies.append((time.perf_counter() - t0) * 1000)
            errors.append(f"{path} {type(exc).__name__}")
            counters["exc"] = counters.get("exc", 0) + 1


async def _run_level(
    url: str,
    cookie_header: str,
    users: int,
    duration_sec: int,
    paths: list[str],
) -> dict[str, Any]:
    headers = {}
    if cookie_header:
        headers["Cookie"] = cookie_header
    latencies: list[float] = []
    errors: list[str] = []
    counters: dict[str, int] = {}
    stop_at = time.perf_counter() + duration_sec
    limits = httpx.Limits(max_connections=max(users * 2, 10), max_keepalive_connections=users)
    async with httpx.AsyncClient(
        base_url=url,
        headers=headers,
        follow_redirects=True,
        limits=limits,
    ) as client:
        tasks = [
            asyncio.create_task(_worker(client, paths, stop_at, latencies, errors, counters))
            for _ in range(users)
        ]
        await asyncio.gather(*tasks)
    total = counters.get("ok", 0) + counters.get("exc", 0)
    err_n = counters.get("http_err", 0) + counters.get("exc", 0)
    return {
        "users": users,
        "duration_sec": duration_sec,
        "requests": total,
        "throughput_rps": round(total / max(duration_sec, 1), 2),
        "latency_ms": summarize_ms(latencies),
        "error_rate": round(err_n / total, 4) if total else None,
        "counters": counters,
        "error_samples": errors[:20],
        "server": sample_process(read_bench_pid()),
    }


def _admin_cookie(url: str) -> str:
    with httpx.Client(base_url=url, follow_redirects=True, timeout=20.0) as client:
        seed_session(client, "admin")
        return "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)


def _run_slice(
    label_slice: str,
    url: str,
    cookie: str,
    paths: list[str],
    duration_sec: int,
    levels: list[int],
) -> dict[str, Any]:
    out_levels = []
    for n in levels:
        before = sample_process(read_bench_pid())
        print(f"[perf] concurrency {label_slice} users={n} ...", flush=True)
        level = asyncio.run(_run_level(url, cookie, n, duration_sec, paths))
        level["server_before"] = before
        out_levels.append(level)
        time.sleep(2)
    return {
        "slice": label_slice,
        "paths": paths,
        "levels": out_levels,
    }


def run(label: str, duration_sec: int = 60, levels: list[int] | None = None) -> dict[str, Any]:
    ensure_dirs()
    url = base_url()
    levels = levels or [1, 5, 10, 20]
    if not wait_for_server(url):
        return {"label": label, "status": "NOT RUN", "blocker": f"server not reachable at {url}"}
    try:
        cookie = _admin_cookie(url)
    except Exception as exc:
        return {"label": label, "status": "NOT RUN", "blocker": f"auth seed failed: {exc}"}

    mixed = _run_slice("mixed", url, cookie, READONLY_API_PATHS, duration_sec, levels)
    api_only = _run_slice("api_only", url, cookie, READONLY_API_ONLY_PATHS, duration_sec, levels)

    return {
        "label": label,
        "status": "ok",
        "base_url": url,
        "paths": READONLY_API_PATHS,
        "levels": mixed["levels"],
        "slices": {
            "mixed": mixed,
            "api_only": api_only,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="before", choices=["before", "after"])
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--levels", default="1,5,10,20")
    args = parser.parse_args()
    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    result = run(args.label, duration_sec=args.duration, levels=levels)
    out = RESULTS_DIR / f"concurrency_{args.label}.json"
    write_json(out, result)
    print(f"[perf] wrote {out} status={result.get('status')}", flush=True)
    return 0 if result.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
