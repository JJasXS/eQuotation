"""Benchmark View e-PR list/detail API timings (run with Flask on :8880)."""
import json
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8880"


def timed(url: str, label: str) -> float | None:
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            body = resp.read()
    except Exception as exc:
        print(f"{label}: FAIL — {exc}")
        return None
    client_ms = (time.perf_counter() - t0) * 1000
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(f"{label}: {client_ms:.0f} ms (non-JSON)")
        return client_ms
    perf = data.get("perf") if isinstance(data.get("perf"), dict) else {}
    rows = len(data.get("data") or [])
    print(
        f"{label}: client={client_ms:.0f}ms server={perf.get('totalMs')} "
        f"upstream={perf.get('upstreamMs')} supplier={perf.get('supplierMs')} "
        f"qty={perf.get('qtyMs')} cacheHit={perf.get('cacheHit')} rows={rows}"
    )
    return client_ms


def main() -> None:
    list_url = (
        f"{BASE}/api/admin/procurement/purchase-requests"
        "?offset=0&limit=15&fast=1&include_qty=0"
    )
    print("=== PR list (fast mode) ===")
    a = timed(list_url, "list-1 (warm server cache)")
    b = timed(list_url, "list-2 (server cache hit)")
    c = timed(list_url + "&no_cache=1", "list-3 (no_cache, like Refresh)")
    print()
    print("=== PR detail ===")
    for rid, docno in [(55, "PR-26060031"), (47, "PR-26060024"), (58, "PR-26060034")]:
        url = (
            f"{BASE}/api/admin/procurement/purchase-requests/details"
            f"?request_id={rid}&request_no={docno}"
        )
        timed(url, f"detail {docno}")
    print()
    if a and b and c:
        print("=== Comparison ===")
        print(f"  Cached repeat:     {b:.0f} ms")
        print(f"  Cold/no_cache:     {c:.0f} ms  ({c / max(b, 1):.1f}x slower than cache hit)")


if __name__ == "__main__":
    main()
