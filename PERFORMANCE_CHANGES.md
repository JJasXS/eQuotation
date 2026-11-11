# Performance Changes

Code changes intended to affect the before→after measurements (app behavior, not harness-only).

## Implemented for this audit

1. **Lazy procurement tabs** — Stock Card / Create PR init run only for the active tab; View/Report no longer pull Create-heavy work on first paint.
2. **Freshness / visibility gating** — tab-return refresh with aborted superseded GETs only (writes untouched).
3. **TtlCache** — opportunistic expiry + single-flight; GET timeouts/cancellation in `eq_core` and search callers.
4. **Firebird connection closes** — handlers that could return without `close` fixed with `finally` where audited.
5. **Create Quotation / admin widgets** — only where URL traces justified cache/dedupe (product load / dashboard reads).

## Measured impact (cold network-idle)

- `procurement_create`: **14103.4 → 657.6 ms** (-95.3%); requests 23.0→22.0.
- `procurement_report`: 620.8 → 593.4 ms; requests 19.0→18.0.
- `procurement_view`: 647.7 → 599.1 ms; requests 21.0→19.0.
- `create_quotation`: essentially unchanged (14091.4 → 14097.8 ms); still ~14 s network-idle in the harness.

## Create PR submit (after harness baseline)

See **`PERFORMANCE_SUBMIT_BEFORE_AFTER.md`** for full before/after.

Short version: remote stock enrich + upstream POST moved off the request; suppliers saved in the same Firebird tx; detail keys batched; no Stock Card reload after submit. Not included in `comparison.json` numbers.

## Artifacts

- `perf/results/baseline_before.json`
- `perf/results/baseline_after.json`
- `perf/results/comparison.json`
- `perf/results/pages_*.json`, `concurrency_*.json`, `idle_*.json`
