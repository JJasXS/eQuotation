# Create PR Submit — Before / After

Focus: **Submit / Save Draft** on `/admin/procurement?tab=create` (not page load).
Page-load gains are in `PERFORMANCE_BEFORE_AFTER.md` (Create tab cold ~14.1s → ~0.66s).

These submit changes landed **after** the official `baseline_after.json` harness run, so they are **not** in that measured pair. Use server log line `[PROCUREMENT CREATE PR] timing …` to verify locally.

---

## Before (submit path)

| Step | What happened | Why it felt slow |
|---|---|---|
| Validate lines | Each line called `enrich_pr_submit_line_item` with **SQL Accounting stockitem GETs** (+ often a new Firebird open per code) | Network + DB per line on the request thread |
| Schema check | Extra Firebird connection every submit (`ensure_purchase_request_schema`) | Extra round-trip before insert |
| Column / numeric meta | Re-queried system tables often | Metadata overhead |
| Detail keys | `MAX` + generator probe **per line** | N heavy key lookups |
| Upstream | Sync `POST` to `PROCUREMENT_CREATE_PR_URL` (timeout 8s, retries) before response | Could block submit for seconds |
| Suppliers | Second DB open after create (`_save_selected_suppliers`) | Another connect/commit |
| SQL API line sync | Already background (OK) | — |
| Browser after OK | Reloaded **Stock Card** while switching to View PR | UI stayed busy after API returned |

---

## After (what we changed)

| Step | Now | Effect |
|---|---|---|
| Validate lines | No remote enrich; client UDFs kept as sent | Removes SQL API waits from submit |
| Local ST_ITEM fill | Once inside create, **same cursor**, `allow_remote=False` | One connection; no stockitem HTTP |
| Full stock enrich | Still in **background** SQL API sync / upstream builders | Correctness kept off the hot path |
| Schema check | Cached ~5 min; runs on create cursor when needed | No extra connect on warm submits |
| Table columns | TTL cache (~5 min) | Fewer system-table reads |
| Numeric column type | Process cache | One lookup per column lifetime |
| Detail keys | **Batch** `_next_keys` + remember working generator | One MAX + N `GEN_ID`, not N×MAX |
| Upstream | **After commit**, daemon thread; default timeout **3s**, fewer retries | Submit returns without waiting on upstream |
| Suppliers | `persist_selected_suppliers` in **same create transaction** | One commit; create API no second save |
| Stock Card | Not reloaded after submit/draft | View PR shows without report refresh |
| UX copy | “Saved. Accounting sync continues in the background.” when `sqlSyncPending` | Sets expectation that sync is async |
| Timing log | `schema / enrich / meta / alloc / insert / suppliers / total` | See which stage still costs |

---

## Expected feel (qualitative)

| | Before | After |
|---|---|---|
| User wait | Validate + remote stock + insert + optional upstream + supplier DB + Stock Card reload | Validate + local Firebird insert/commit (async work continues) |
| Success | Modal after all of the above | Modal as soon as local save returns |
| Risk tradeoff | Upstream failure could fail the whole submit | Local PR is saved; upstream/SQL sync failures log as warnings |

---

## Files touched

- `utils/procurement_purchase_request.py` — create path, batch keys, async upstream, suppliers-in-tx, timing
- `utils/stock_items_catalog.py` — `allow_remote` / `db_cur` on enrich
- `main.py` — create API relies on in-tx supplier save; edit still uses `_save_selected_suppliers` helper
- `static/js/procurement/precurement_app.js` — no Stock Card reload; sync-pending success text

---

## How to confirm

1. Restart eQuotation.
2. Submit a Create e-PR.
3. Server console should show something like:  
   `[PROCUREMENT CREATE PR] timing schema=…ms enrich=…ms meta=…ms alloc=…ms insert=…ms suppliers=…ms total=…ms`
4. UI should switch to View PR and show the success modal without waiting on Stock Card.
