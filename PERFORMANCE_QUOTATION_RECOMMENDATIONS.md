# Quotation module — speed findings & recommendations

Measured Create Quotation cold load (official after baseline): **~14.1 s network-idle**.
DOM/load themselves are fast (~30–65 ms). Almost all wait is API/upstream.

## What is slow today

| Area | Evidence | Impact |
|---|---|---|
| `/api/get_user_info` | ~5.2 s in harness (often waiting on SQL Accounting `/customer`) | Blocks customer panel + currency before Save/Submit feel ready |
| Harness `networkidle` | 12 s timeout + 2 s fallback ≈ **14 s** | Inflates page metric when any request lingers |
| Submit `/api/create_quotation` | SQL Accounting `/salesquotation` + per-line stock enrich + DOCNO retries | Can feel like “no response” without button busy state |
| Save draft | Was awaiting full `get_user_info` every click; currency hard-gate | Click appeared dead when currency/API slow |
| Product catalog | Typeahead `/api/search_stock_items` (OK) | Fine if kept search-as-you-type (already not full dump) |

## Applied

1. **`get_user_info` local-first** — `AR_CUSTOMER` first (`EQ_USER_INFO_LOCAL_FIRST=1`).
2. **Shorter SQL customer GET** — 2.5 s when SQL path is used.
3. **90s TTL cache** for `get_user_info` (`user_info_cache`) and stock search (`stock_search_cache`).
4. **Background SQL overlay** — after local paint, `?prefer_sql=1&nocache=1` upgrades fields without blocking.
5. **Save Draft / Submit UX** — “Saving…” / “Submitting…”; currency refresh capped; server resolves currency.
6. **Pre-reserve DOCNO** — submit sends `dataset.previewDocno` so create skips re-scan when possible.
7. **Skip remote stock enrich** on submit when line already has `stockDetail` / itemCode.
8. **Lazy-load quotation chat JS** until the bubble is clicked (CSS stays for bubble styling).

Restart the app and hard-refresh Create Quotation (`orderQuotation.js?v=20261028_quote_speed2`).

## Still optional later

- “Still working with Accounting…” toast after ~4 s on submit
- View Quotations list paging / lighter payloads
- Ops: stabilize SQL Accounting `/customer` endpoint
- Tune `SQL_API_QUOTATION_TIMEOUT_SECONDS`

## Env knobs

| Variable | Default | Meaning |
|---|---|---|
| `EQ_USER_INFO_LOCAL_FIRST` | `1` | Return Firebird customer first (fast). Set `0` to prefer SQL API first (old behavior). |
| `SQL_API_QUOTATION_TIMEOUT_SECONDS` | (global SQL timeout) | Upstream `/salesquotation` read timeout |

## Related docs

- Page load before/after (procurement lazy-load, etc.): `PERFORMANCE_BEFORE_AFTER.md`
- Create PR submit: `PERFORMANCE_SUBMIT_BEFORE_AFTER.md`
