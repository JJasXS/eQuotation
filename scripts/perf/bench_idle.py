"""Idle / inactivity benchmarks (15 and 30 minute observations)."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

PERF_DIR = Path(__file__).resolve().parent
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

from bench_common import (  # noqa: E402
    RESULTS_DIR,
    base_url,
    ensure_dirs,
    read_bench_pid,
    sample_process,
    seed_session,
    wait_for_server,
    write_json,
)

IDLE_PAGES = [
    {"id": "admin", "path": "/admin", "role": "admin"},
    {"id": "create_quotation", "path": "/create-quotation", "role": "customer"},
    {"id": "procurement", "path": "/admin/procurement?tab=report", "role": "admin"},
]


def _cookies_for(role: str, url: str) -> list[dict[str, Any]]:
    import httpx
    from urllib.parse import urlparse

    host = urlparse(url).hostname or "127.0.0.1"
    with httpx.Client(base_url=url, follow_redirects=True, timeout=20.0) as client:
        seed_session(client, role)
        return [
            {"name": c.name, "value": c.value, "domain": host, "path": "/"}
            for c in client.cookies.jar
        ]


def _heap(page) -> dict[str, Any] | None:
    try:
        return page.evaluate(
            """() => performance.memory ? {
              usedJSHeapSize: performance.memory.usedJSHeapSize,
              totalJSHeapSize: performance.memory.totalJSHeapSize
            } : null"""
        )
    except Exception:
        return None


def _set_hidden(page, hidden: bool) -> None:
    page.evaluate(
        """(hidden) => {
          Object.defineProperty(document, 'visibilityState', {
            configurable: true,
            get: () => hidden ? 'hidden' : 'visible'
          });
          Object.defineProperty(document, 'hidden', {
            configurable: true,
            get: () => !!hidden
          });
          document.dispatchEvent(new Event('visibilitychange'));
        }""",
        hidden,
    )


def run(label: str, minutes_15: int = 15, minutes_30: int = 30) -> dict[str, Any]:
    ensure_dirs()
    url = base_url()
    # Allow short smoke via env without fabricating results — still records actual durations.
    minutes_15 = int(os.getenv("EQ_PERF_IDLE_MIN_15", str(minutes_15)))
    minutes_30 = int(os.getenv("EQ_PERF_IDLE_MIN_30", str(minutes_30)))
    if minutes_30 < minutes_15:
        minutes_30 = minutes_15

    if not wait_for_server(url):
        return {"label": label, "status": "NOT RUN", "blocker": f"server not reachable at {url}"}

    server_start = sample_process(read_bench_pid())
    pages_result: dict[str, Any] = {}

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception as exc:
            return {"label": label, "status": "NOT RUN", "blocker": f"msedge launch failed: {exc}"}

        contexts = []
        pages = []
        cookie_cache: dict[str, list] = {}
        for spec in IDLE_PAGES:
            role = spec["role"]
            if role not in cookie_cache:
                cookie_cache[role] = _cookies_for(role, url)
            ctx = browser.new_context()
            ctx.add_cookies(cookie_cache[role])
            page = ctx.new_page()
            reqs: list[dict[str, Any]] = []

            def _on_req(req, bucket=reqs):
                bucket.append({"url": req.url, "method": req.method, "t": time.time()})

            page.on("request", _on_req)
            # Prefer load + settle: create-quotation product fetch can prevent true networkidle.
            page.goto(url.rstrip("/") + spec["path"], wait_until="load", timeout=90000)
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                page.wait_for_timeout(3000)
            pages.append(
                {
                    "id": spec["id"],
                    "path": spec["path"],
                    "page": page,
                    "ctx": ctx,
                    "reqs": reqs,
                    "heap0": _heap(page),
                    "t0": time.time(),
                }
            )
            contexts.append(ctx)

        # Baseline request counts after initial load settle
        for item in pages:
            item["reqs_after_load"] = len(item["reqs"])
            item["reqs"].clear()

        # Visibility churn while "active" for first minute, then idle
        visibility_reloads = 0
        for item in pages:
            if item["id"] != "procurement":
                continue
            before = len(item["reqs"])
            _set_hidden(item["page"], True)
            time.sleep(0.6)
            _set_hidden(item["page"], False)
            time.sleep(1.0)
            after = len(item["reqs"])
            visibility_reloads = max(0, after - before)

        markers = {
            "at_15": None,
            "at_30": None,
        }
        deadline_15 = time.time() + minutes_15 * 60
        deadline_30 = time.time() + minutes_30 * 60

        def snapshot(tag: str) -> dict[str, Any]:
            out = {"tag": tag, "t": time.time(), "pages": {}, "server": sample_process(read_bench_pid())}
            for item in pages:
                out["pages"][item["id"]] = {
                    "idle_requests": len(item["reqs"]),
                    "idle_request_urls": [r["url"] for r in item["reqs"][:50]],
                    "heap": _heap(item["page"]),
                    "heap0": item["heap0"],
                }
            return out

        # Sleep in chunks so we can mark 15 then 30
        while time.time() < deadline_30:
            remaining = deadline_30 - time.time()
            if markers["at_15"] is None and time.time() >= deadline_15:
                markers["at_15"] = snapshot("15m")
            time.sleep(min(30.0, max(1.0, remaining)))
        if markers["at_15"] is None:
            markers["at_15"] = snapshot("15m")
        markers["at_30"] = snapshot("30m")

        for item in pages:
            pages_result[item["id"]] = {
                "path": item["path"],
                "heap0": item["heap0"],
                "idle_requests_15": markers["at_15"]["pages"][item["id"]]["idle_requests"],
                "idle_requests_30": markers["at_30"]["pages"][item["id"]]["idle_requests"],
                "heap_15": markers["at_15"]["pages"][item["id"]]["heap"],
                "heap_30": markers["at_30"]["pages"][item["id"]]["heap"],
                "idle_urls_30": markers["at_30"]["pages"][item["id"]]["idle_request_urls"],
            }
            item["ctx"].close()
        browser.close()

    return {
        "label": label,
        "status": "ok",
        "base_url": url,
        "minutes_15": minutes_15,
        "minutes_30": minutes_30,
        "visibility_triggered_requests": visibility_reloads,
        "server_start": server_start,
        "server_15": markers["at_15"]["server"] if markers["at_15"] else None,
        "server_30": markers["at_30"]["server"] if markers["at_30"] else None,
        "pages": pages_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="before", choices=["before", "after"])
    parser.add_argument("--min15", type=int, default=15)
    parser.add_argument("--min30", type=int, default=30)
    args = parser.parse_args()
    result = run(args.label, minutes_15=args.min15, minutes_30=args.min30)
    out = RESULTS_DIR / f"idle_{args.label}.json"
    write_json(out, result)
    print(f"[perf] wrote {out} status={result.get('status')}", flush=True)
    return 0 if result.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
