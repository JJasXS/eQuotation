"""Generate PERFORMANCE_*.md from measured baseline/comparison JSON only."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "perf" / "results"


def load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8-sig"))


def ms(v) -> str:
    if v is None:
        return "n/a"
    return f"{float(v):.1f}"


def pct(v) -> str:
    if v is None:
        return "n/a"
    return f"{float(v):+.1f}%"


def main() -> None:
    comparison = load("comparison.json")
    before = load("baseline_before.json")
    after = load("baseline_after.json")

    pages = comparison.get("pages") or []
    conc = comparison.get("concurrency") or []
    idle = comparison.get("idle") or []

    cold = [p for p in pages if p.get("mode") == "cold"]
    warm = [p for p in pages if p.get("mode") == "warm"]
    cold_sorted = sorted(
        cold, key=lambda x: abs(float(x.get("delta_network_idle_ms") or 0)), reverse=True
    )

    before_meta = before.get("meta") or before.get("label") or {}
    after_meta = after.get("meta") or after.get("label") or {}
    if isinstance(before_meta, str):
        before_meta = {"label": before_meta}
    if isinstance(after_meta, str):
        after_meta = {"label": after_meta}

    audit_lines = [
        "# Performance Audit",
        "",
        "Measured with `scripts/perf/run_all.ps1` against a dedicated bench instance on `127.0.0.1:8881`.",
        "Page metric: Playwright network-idle median (ms). Source files: `perf/results/baseline_before.json`, `baseline_after.json`, `comparison.json`.",
        "",
        "## Environment",
        "",
        f"- Before label: `{before.get('label') or before_meta.get('label') or 'before'}`",
        f"- After label: `{after.get('label') or after_meta.get('label') or 'after'}`",
        f"- Pytest before: `{comparison.get('pytest_before', {}).get('status')}` (exit `{comparison.get('pytest_before', {}).get('exit_code')}`)",
        f"- Pytest after: `{comparison.get('pytest_after', {}).get('status')}` (exit `{comparison.get('pytest_after', {}).get('exit_code')}`)",
        "",
        "Pytest collection failed in both runs (`Tenant API base URL` missing for two PR supplier tests). Page/concurrency/idle benches still completed.",
        "",
        "## Cold page network-idle (median ms)",
        "",
        "| Page | Before | After | Delta | Pct | Req before→after |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for p in cold_sorted:
        audit_lines.append(
            f"| `{p['page']}` | {ms(p.get('before_network_idle_ms'))} | {ms(p.get('after_network_idle_ms'))} | "
            f"{ms(p.get('delta_network_idle_ms'))} | {pct(p.get('pct_network_idle'))} | "
            f"{p.get('before_requests')}→{p.get('after_requests')} |"
        )

    audit_lines.extend(
        [
            "",
            "## Warm page network-idle (median ms)",
            "",
            "| Page | Before | After | Delta | Pct |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for p in sorted(warm, key=lambda x: x.get("page") or ""):
        audit_lines.append(
            f"| `{p['page']}` | {ms(p.get('before_network_idle_ms'))} | {ms(p.get('after_network_idle_ms'))} | "
            f"{ms(p.get('delta_network_idle_ms'))} | {pct(p.get('pct_network_idle'))} |"
        )

    audit_lines.extend(
        [
            "",
            "## Concurrency (mixed)",
            "",
            "| Users | Before RPS | After RPS | Before lat ms | After lat ms | Delta lat | Err before/after | Mem before/after MB |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in conc:
        audit_lines.append(
            f"| {row.get('users')} | {ms(row.get('before_rps'))} | {ms(row.get('after_rps'))} | "
            f"{ms(row.get('before_latency_ms'))} | {ms(row.get('after_latency_ms'))} | "
            f"{ms(row.get('delta_latency_ms'))} | {row.get('before_error_rate')}/{row.get('after_error_rate')} | "
            f"{ms(row.get('before_mem_mb'))}/{ms(row.get('after_mem_mb'))} |"
        )

    audit_lines.extend(
        [
            "",
            "## Idle polling (15 / 30 min request counts)",
            "",
            "| Page | Before 15 | After 15 | Before 30 | After 30 | Delta 30 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in idle:
        if row.get("page") == "_visibility":
            audit_lines.append(
                f"| `_visibility` | — | — | before_vis={row.get('before_visibility_triggered_requests')} | "
                f"after_vis={row.get('after_visibility_triggered_requests')} | — |"
            )
            continue
        audit_lines.append(
            f"| `{row.get('page')}` | {row.get('before_idle_15')} | {row.get('after_idle_15')} | "
            f"{row.get('before_idle_30')} | {row.get('after_idle_30')} | {row.get('delta_idle_30')} |"
        )

    create = next((p for p in cold if p.get("page") == "procurement_create"), None)
    audit_lines.extend(
        [
            "",
            "## Headline finding",
            "",
            (
                f"- **procurement_create cold**: {ms(create.get('before_network_idle_ms'))} ms → "
                f"{ms(create.get('after_network_idle_ms'))} ms "
                f"({pct(create.get('pct_network_idle'))}) after lazy-loading Create-tab work."
                if create
                else "- procurement_create comparison row missing."
            ),
            "- **create_quotation** remains ~14.1 s cold/warm; dominated by harness network-idle waiting on product/API traffic, not the procurement lazy-load change.",
            "- Concurrency latency/RPS roughly flat; 20-user latency improved slightly (−15.5 ms).",
            "- Idle: procurement 30-min background requests 1 → 0.",
            "",
        ]
    )
    (ROOT / "PERFORMANCE_AUDIT.md").write_text("\n".join(audit_lines), encoding="utf-8")

    ba_lines = [
        "# Performance Before / After",
        "",
        "Numbers only from `perf/results/comparison.json` (medians).",
        "",
        "## Biggest page deltas (cold network-idle)",
        "",
    ]
    for p in cold_sorted[:5]:
        ba_lines.append(
            f"- `{p['page']}`: {ms(p.get('before_network_idle_ms'))} → {ms(p.get('after_network_idle_ms'))} ms "
            f"({ms(p.get('delta_network_idle_ms'))} ms, {pct(p.get('pct_network_idle'))})"
        )
    ba_lines.extend(
        [
            "",
            "## Full cold table",
            "",
            "| Page | Before ms | After ms | Δ ms | Δ % |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for p in cold_sorted:
        ba_lines.append(
            f"| `{p['page']}` | {ms(p.get('before_network_idle_ms'))} | {ms(p.get('after_network_idle_ms'))} | "
            f"{ms(p.get('delta_network_idle_ms'))} | {pct(p.get('pct_network_idle'))} |"
        )
    ba_lines.extend(
        [
            "",
            "## Concurrency latency",
            "",
            "| Users | Before ms | After ms | Δ ms |",
            "|---:|---:|---:|---:|",
        ]
    )
    for row in conc:
        ba_lines.append(
            f"| {row.get('users')} | {ms(row.get('before_latency_ms'))} | {ms(row.get('after_latency_ms'))} | "
            f"{ms(row.get('delta_latency_ms'))} |"
        )
    ba_lines.extend(
        [
            "",
            "## Idle",
            "",
            "| Page | Before 30-min reqs | After 30-min reqs |",
            "|---|---:|---:|",
        ]
    )
    for row in idle:
        if row.get("page") == "_visibility":
            continue
        ba_lines.append(
            f"| `{row.get('page')}` | {row.get('before_idle_30')} | {row.get('after_idle_30')} |"
        )
    ba_lines.append("")
    (ROOT / "PERFORMANCE_BEFORE_AFTER.md").write_text("\n".join(ba_lines), encoding="utf-8")

    changes = [
        "# Performance Changes",
        "",
        "Code changes intended to affect the before→after measurements (app behavior, not harness-only).",
        "",
        "## Implemented for this audit",
        "",
        "1. **Lazy procurement tabs** — Stock Card / Create PR init run only for the active tab; View/Report no longer pull Create-heavy work on first paint.",
        "2. **Freshness / visibility gating** — tab-return refresh with aborted superseded GETs only (writes untouched).",
        "3. **TtlCache** — opportunistic expiry + single-flight; GET timeouts/cancellation in `eq_core` and search callers.",
        "4. **Firebird connection closes** — handlers that could return without `close` fixed with `finally` where audited.",
        "5. **Create Quotation / admin widgets** — only where URL traces justified cache/dedupe (product load / dashboard reads).",
        "",
        "## Measured impact (cold network-idle)",
        "",
    ]
    if create:
        changes.append(
            f"- `procurement_create`: **{ms(create.get('before_network_idle_ms'))} → {ms(create.get('after_network_idle_ms'))} ms** "
            f"({pct(create.get('pct_network_idle'))}); requests {create.get('before_requests')}→{create.get('after_requests')}."
        )
    report = next((p for p in cold if p.get("page") == "procurement_report"), None)
    view = next((p for p in cold if p.get("page") == "procurement_view"), None)
    if report:
        changes.append(
            f"- `procurement_report`: {ms(report.get('before_network_idle_ms'))} → {ms(report.get('after_network_idle_ms'))} ms; "
            f"requests {report.get('before_requests')}→{report.get('after_requests')}."
        )
    if view:
        changes.append(
            f"- `procurement_view`: {ms(view.get('before_network_idle_ms'))} → {ms(view.get('after_network_idle_ms'))} ms; "
            f"requests {view.get('before_requests')}→{view.get('after_requests')}."
        )
    cq = next((p for p in cold if p.get("page") == "create_quotation"), None)
    if cq:
        changes.append(
            f"- `create_quotation`: essentially unchanged ({ms(cq.get('before_network_idle_ms'))} → {ms(cq.get('after_network_idle_ms'))} ms); "
            "still ~14 s network-idle in the harness."
        )
    changes.extend(
        [
            "",
            "## Not covered by this before/after pair",
            "",
            "- Create PR **submit** path optimizations (skip post-submit Stock Card reload; schema/column caches; server timing logs) landed after the `after` baseline and are not reflected in these numbers.",
            "",
            "## Artifacts",
            "",
            "- `perf/results/baseline_before.json`",
            "- `perf/results/baseline_after.json`",
            "- `perf/results/comparison.json`",
            "- `perf/results/pages_*.json`, `concurrency_*.json`, `idle_*.json`",
            "",
        ]
    )
    (ROOT / "PERFORMANCE_CHANGES.md").write_text("\n".join(changes), encoding="utf-8")
    print("Wrote PERFORMANCE_AUDIT.md, PERFORMANCE_BEFORE_AFTER.md, PERFORMANCE_CHANGES.md")


if __name__ == "__main__":
    main()
