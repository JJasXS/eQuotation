"""Cold/warm page load benchmarks via Playwright (msedge channel)."""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

PERF_DIR = Path(__file__).resolve().parent
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

from bench_common import (  # noqa: E402
    PAGE_SPECS,
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


def _cookie_jar_to_playwright(cookies: dict[str, str], url: str) -> list[dict[str, Any]]:
    host = urlparse(url).hostname or "127.0.0.1"
    out = []
    for name, value in cookies.items():
        out.append({"name": name, "value": value, "domain": host, "path": "/"})
    return out


def _seed_cookies(role: str | None, url: str) -> list[dict[str, Any]]:
    if not role:
        return []
    import httpx

    with httpx.Client(base_url=url, follow_redirects=True, timeout=20.0) as client:
        seed_session(client, role)
        jar = {c.name: c.value for c in client.cookies.jar}
    return _cookie_jar_to_playwright(jar, url)


def _path_key(full_url: str) -> str:
    try:
        p = urlparse(full_url)
        return p.path or full_url
    except Exception:
        return full_url


def _measure_once(browser, url: str, path: str, cookies: list[dict[str, Any]], cold: bool) -> dict[str, Any]:
    context = browser.new_context(bypass_csp=True)
    if cookies:
        context.add_cookies(cookies)
    if cold:
        context.set_extra_http_headers({"Cache-Control": "no-cache", "Pragma": "no-cache"})
    page = context.new_page()
    request_count = 0
    bytes_total = 0
    url_timings: list[dict[str, Any]] = []
    started: dict[str, float] = {}

    def on_request(req):
        started[req.url] = time.perf_counter()

    def on_response(resp):
        nonlocal request_count, bytes_total
        request_count += 1
        try:
            size = int(resp.headers.get("content-length") or 0)
        except Exception:
            size = 0
        bytes_total += max(size, 0)
        t0 = started.pop(resp.url, None)
        duration_ms = round((time.perf_counter() - t0) * 1000, 2) if t0 is not None else None
        url_timings.append(
            {
                "url": resp.url,
                "path": _path_key(resp.url),
                "status": resp.status,
                "duration_ms": duration_ms,
                "method": resp.request.method,
            }
        )

    page.on("request", on_request)
    page.on("response", on_response)
    t0 = time.perf_counter()
    response = page.goto(url.rstrip("/") + path, wait_until="load", timeout=90000)
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        page.wait_for_timeout(2000)
    network_idle_ms = (time.perf_counter() - t0) * 1000
    try:
        timing = page.evaluate(
            """() => {
              const n = performance.getEntriesByType('navigation')[0];
              if (!n) return null;
              return {
                ttfb: n.responseStart,
                domContentLoaded: n.domContentLoadedEventEnd,
                load: n.loadEventEnd,
                transferSize: n.transferSize || 0
              };
            }"""
        )
    except Exception:
        timing = None
    try:
        resource_bytes = page.evaluate(
            """() => performance.getEntriesByType('resource')
                .reduce((s, e) => s + (e.transferSize || e.encodedBodySize || 0), 0)"""
        )
        if resource_bytes and resource_bytes > bytes_total:
            bytes_total = int(resource_bytes)
    except Exception:
        pass
    heap = None
    try:
        heap = page.evaluate(
            """() => {
              if (performance.memory) {
                return {
                  usedJSHeapSize: performance.memory.usedJSHeapSize,
                  totalJSHeapSize: performance.memory.totalJSHeapSize
                };
              }
              return null;
            }"""
        )
    except Exception:
        heap = None

    # Aggregate duplicate path hits (stock-card, products, etc.).
    path_counts = Counter(u["path"] for u in url_timings)
    api_paths = [u for u in url_timings if "/api/" in (u.get("path") or "")]
    slowest_apis = sorted(
        [u for u in api_paths if u.get("duration_ms") is not None],
        key=lambda x: x["duration_ms"],
        reverse=True,
    )[:15]

    status = response.status if response else None
    result = {
        "status": status,
        "ttfb_ms": None if not timing else round(timing.get("ttfb") or 0, 2),
        "dom_content_loaded_ms": None if not timing else round(timing.get("domContentLoaded") or 0, 2),
        "load_ms": None if not timing else round(timing.get("load") or 0, 2),
        "network_idle_ms": round(network_idle_ms, 2),
        "request_count": request_count,
        "bytes": bytes_total,
        "heap": heap,
        "wall_ms": round((time.perf_counter() - t0) * 1000, 2),
        "path_hit_counts": dict(path_counts.most_common(40)),
        "slowest_apis": slowest_apis,
        "duplicate_api_paths": {
            p: c for p, c in path_counts.items() if "/api/" in p and c > 1
        },
    }
    context.close()
    return result


def _aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in runs if r.get("status") and int(r["status"]) < 500]
    if not ok:
        return {"status": "NOT RUN", "blocker": "no successful runs", "runs": runs}
    # Merge path hit counts across runs (median of counts per path).
    all_paths = set()
    for r in ok:
        all_paths.update((r.get("path_hit_counts") or {}).keys())
    path_medians = {}
    for p in all_paths:
        vals = [float((r.get("path_hit_counts") or {}).get(p, 0)) for r in ok]
        path_medians[p] = summarize_ms(vals)["median"]
    return {
        "status": "ok",
        "runs": len(ok),
        "ttfb_ms": summarize_ms([r["ttfb_ms"] for r in ok if r.get("ttfb_ms") is not None]),
        "dom_content_loaded_ms": summarize_ms(
            [r["dom_content_loaded_ms"] for r in ok if r.get("dom_content_loaded_ms") is not None]
        ),
        "load_ms": summarize_ms([r["load_ms"] for r in ok if r.get("load_ms") is not None]),
        "network_idle_ms": summarize_ms([r["network_idle_ms"] for r in ok if r.get("network_idle_ms") is not None]),
        "request_count": summarize_ms([float(r["request_count"]) for r in ok]),
        "bytes": summarize_ms([float(r["bytes"]) for r in ok]),
        "heap_used": summarize_ms(
            [float(r["heap"]["usedJSHeapSize"]) for r in ok if r.get("heap") and r["heap"].get("usedJSHeapSize")]
        ),
        "path_hit_count_medians": path_medians,
        "samples": ok,
    }


def run(label: str, repeats: int = 5) -> dict[str, Any]:
    ensure_dirs()
    url = base_url()
    if not wait_for_server(url):
        return {
            "label": label,
            "status": "NOT RUN",
            "blocker": f"server not reachable at {url}",
            "pages": {},
        }

    cookies_by_role: dict[str, list] = {}
    pages_out: dict[str, Any] = {}
    server_before = sample_process(read_bench_pid())

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception as exc:
            return {
                "label": label,
                "status": "NOT RUN",
                "blocker": f"msedge launch failed: {exc}",
                "pages": {},
            }

        for spec in PAGE_SPECS:
            role = spec.get("role")
            page_id = spec["id"]
            path = spec["path"]
            settle = float(spec.get("settle_before_sec") or 0)
            print(f"[perf] page {page_id} {path} ...", flush=True)
            try:
                if role and role not in cookies_by_role:
                    cookies_by_role[role] = _seed_cookies(role, url)
                cookies = cookies_by_role.get(role) if role else []
                if settle > 0:
                    time.sleep(settle)
                cold_runs = []
                warm_runs = []
                for i in range(repeats):
                    if settle > 0 and i > 0:
                        time.sleep(settle)
                    cold_runs.append(_measure_once(browser, url, path, cookies or [], cold=True))
                    print(f"  cold {i+1}/{repeats} idle={cold_runs[-1].get('network_idle_ms')} reqs={cold_runs[-1].get('request_count')}", flush=True)
                for i in range(repeats):
                    if settle > 0:
                        time.sleep(settle)
                    warm_runs.append(_measure_once(browser, url, path, cookies or [], cold=False))
                    print(f"  warm {i+1}/{repeats}", flush=True)
                pages_out[page_id] = {
                    "path": path,
                    "role": role,
                    "cold": _aggregate(cold_runs),
                    "warm": _aggregate(warm_runs),
                }
            except Exception as exc:
                print(f"  FAIL {exc}", flush=True)
                pages_out[page_id] = {
                    "path": path,
                    "role": role,
                    "status": "NOT RUN",
                    "blocker": str(exc)[:300],
                }

        browser.close()

    return {
        "label": label,
        "status": "ok",
        "base_url": url,
        "repeats": repeats,
        "server_before": server_before,
        "server_after": sample_process(read_bench_pid()),
        "pages": pages_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="before", choices=["before", "after"])
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    result = run(args.label, repeats=args.repeats)
    out = RESULTS_DIR / f"pages_{args.label}.json"
    write_json(out, result)
    print(f"[perf] wrote {out} status={result.get('status')}", flush=True)
    return 0 if result.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
