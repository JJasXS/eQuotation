# Performance Audit

Measured with `scripts/perf/run_all.ps1` against a dedicated bench instance on `127.0.0.1:8881`.
Page metric: Playwright network-idle median (ms). Source files: `perf/results/baseline_before.json`, `baseline_after.json`, `comparison.json`.

## Environment

- Before label: `before`
- After label: `after`
- Pytest before: `failed` (exit `2`)
- Pytest after: `failed` (exit `2`)

Pytest collection failed in both runs (`Tenant API base URL` missing for two PR supplier tests). Page/concurrency/idle benches still completed.

## Cold page network-idle (median ms)

| Page | Before | After | Delta | Pct | Req before→after |
|---|---:|---:|---:|---:|---:|
| `procurement_create` | 14103.4 | 657.6 | -13445.8 | -95.3% | 23.0→22.0 |
| `invoice_aging` | 1618.2 | 934.8 | -683.5 | -42.2% | 14.0→14.0 |
| `procurement_view` | 647.7 | 599.1 | -48.6 | -7.5% | 21.0→19.0 |
| `procurement_report` | 620.8 | 593.4 | -27.4 | -4.4% | 19.0→18.0 |
| `view_quotation` | 598.2 | 588.2 | -10.0 | -1.7% | 13.0→13.0 |
| `create_quotation` | 14091.4 | 14097.8 | 6.5 | +0.1% | 14.0→14.0 |
| `login` | 552.2 | 557.1 | 4.9 | +0.9% | 6.0→6.0 |
| `admin_view_quotations` | 643.7 | 645.7 | 2.0 | +0.3% | 15.0→15.0 |
| `supplier_bidding` | 556.6 | 558.3 | 1.7 | +0.3% | 10.0→10.0 |
| `admin` | 1624.5 | 1623.7 | -0.8 | -0.1% | 15.0→15.0 |

## Warm page network-idle (median ms)

| Page | Before | After | Delta | Pct |
|---|---:|---:|---:|---:|
| `admin` | 1608.2 | 1618.4 | 10.2 | +0.6% |
| `admin_view_quotations` | 647.4 | 645.0 | -2.4 | -0.4% |
| `create_quotation` | 14088.1 | 14081.1 | -7.0 | -0.1% |
| `invoice_aging` | 1633.7 | 1630.8 | -2.9 | -0.2% |
| `login` | 548.4 | 545.2 | -3.2 | -0.6% |
| `procurement_create` | 671.7 | 631.1 | -40.6 | -6.0% |
| `procurement_report` | 630.6 | 607.0 | -23.7 | -3.8% |
| `procurement_view` | 640.7 | 594.1 | -46.6 | -7.3% |
| `supplier_bidding` | 558.5 | 557.9 | -0.6 | -0.1% |
| `view_quotation` | 599.0 | 595.6 | -3.4 | -0.6% |

## Concurrency (mixed)

| Users | Before RPS | After RPS | Before lat ms | After lat ms | Delta lat | Err before/after | Mem before/after MB |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 83.4 | 80.2 | 2.9 | 3.0 | 0.1 | 0.0/0.0 | 158.0/153.4 |
| 5 | 80.7 | 86.3 | 56.1 | 49.3 | -6.8 | 0.0/0.0 | 158.8/155.2 |
| 10 | 88.3 | 86.4 | 90.1 | 91.4 | 1.4 | 0.0/0.0 | 159.4/154.4 |
| 20 | 81.7 | 84.3 | 190.1 | 174.6 | -15.4 | 0.0/0.0 | 159.7/156.0 |

## Idle polling (15 / 30 min request counts)

| Page | Before 15 | After 15 | Before 30 | After 30 | Delta 30 |
|---|---:|---:|---:|---:|---:|
| `admin` | 0 | 0 | 0 | 0 | 0.0 |
| `create_quotation` | 0 | 0 | 0 | 0 | 0.0 |
| `procurement` | 1 | 0 | 1 | 0 | -1.0 |
| `_visibility` | — | — | before_vis=0 | after_vis=0 | — |

## Headline finding

- **procurement_create cold**: 14103.4 ms → 657.6 ms (-95.3%) after lazy-loading Create-tab work.
- **create_quotation** remains ~14.1 s cold/warm; dominated by harness network-idle waiting on product/API traffic, not the procurement lazy-load change.
- Concurrency latency/RPS roughly flat; 20-user latency improved slightly (−15.5 ms).
- Idle: procurement 30-min background requests 1 → 0.
