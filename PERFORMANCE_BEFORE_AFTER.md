# Performance Before / After

Numbers only from `perf/results/comparison.json` (medians).

## Biggest page deltas (cold network-idle)

- `procurement_create`: 14103.4 → 657.6 ms (-13445.8 ms, -95.3%)
- `invoice_aging`: 1618.2 → 934.8 ms (-683.5 ms, -42.2%)
- `procurement_view`: 647.7 → 599.1 ms (-48.6 ms, -7.5%)
- `procurement_report`: 620.8 → 593.4 ms (-27.4 ms, -4.4%)
- `view_quotation`: 598.2 → 588.2 ms (-10.0 ms, -1.7%)

## Full cold table

| Page | Before ms | After ms | Δ ms | Δ % |
|---|---:|---:|---:|---:|
| `procurement_create` | 14103.4 | 657.6 | -13445.8 | -95.3% |
| `invoice_aging` | 1618.2 | 934.8 | -683.5 | -42.2% |
| `procurement_view` | 647.7 | 599.1 | -48.6 | -7.5% |
| `procurement_report` | 620.8 | 593.4 | -27.4 | -4.4% |
| `view_quotation` | 598.2 | 588.2 | -10.0 | -1.7% |
| `create_quotation` | 14091.4 | 14097.8 | 6.5 | +0.1% |
| `login` | 552.2 | 557.1 | 4.9 | +0.9% |
| `admin_view_quotations` | 643.7 | 645.7 | 2.0 | +0.3% |
| `supplier_bidding` | 556.6 | 558.3 | 1.7 | +0.3% |
| `admin` | 1624.5 | 1623.7 | -0.8 | -0.1% |

## Concurrency latency

| Users | Before ms | After ms | Δ ms |
|---:|---:|---:|---:|
| 1 | 2.9 | 3.0 | 0.1 |
| 5 | 56.1 | 49.3 | -6.8 |
| 10 | 90.1 | 91.4 | 1.4 |
| 20 | 190.1 | 174.6 | -15.4 |

## Idle

| Page | Before 30-min reqs | After 30-min reqs |
|---|---:|---:|
| `admin` | 0 | 0 |
| `create_quotation` | 0 | 0 |
| `procurement` | 1 | 0 |
