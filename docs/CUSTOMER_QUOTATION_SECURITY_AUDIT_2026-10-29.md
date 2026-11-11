# Customer Quotation Security, Performance & Standards Audit

**Date:** 2026-10-29  
**Repository:** https://github.com/JJasXS/eQuotation  
**Scope:** Customer-facing quotation flow (OTP login → create/submit/draft/view/email)  
**Constraint:** No automatic commit/push/deploy. Business rules and SQL Accounting/Firebird integrations preserved.

---

## Phase 1 — Confirmed findings (with evidence)

### P0 — Security (confirmed)

| ID | Severity | Finding | Evidence |
|----|----------|---------|----------|
| S1 | Critical | Dev `FLASK_SECRET_KEY` fallback usable in production | `main.py` session config |
| S2 | High | `SESSION_COOKIE_SECURE = False` hardcoded | `main.py` |
| S3 | Medium | Session not cleared on OTP login (fixation) | `api_verify_otp` previously assigned keys without `session.clear()` |
| I1 | High | Client could send `skipCustomerCodeCheck` / `adminUpdate` on `/api/create_quotation` and update another customer's QT | `utils/quotation_api.py` 1598–1611; `api_create_quotation` passed body through |
| I2 | High | `save_draft_quotation` deleted `SL_QTDTLDRAFT` by `DOCKEY` alone before ownership was proven | `utils/quotation_api.py` |
| I3 | Medium | Post-submit draft cleanup deleted lines by `draftDockey` without ownership check | `api_create_quotation` |
| I4 | Low | `GET /api/quotation/next_docno?dockey=` could reveal another QT DOCNO | `peek_next_qt_docno` |
| E1 | High | `/api/send_quotation_email` trusted client totals/items/company with no ownership check | `routes/quotation_routes.py` |
| O1 | High | OTP printed to server logs | `api_send_otp` |
| O2 | High | No verify attempt lockout (6-digit brute force within 120s) | `api_verify_otp` |
| O3 | High | Process-local `OTP_STORAGE` (multi-worker inconsistency) | `main.py` `OTP_STORAGE = {}` |
| O4 | Medium | Email format validation disabled | commented block in `api_send_otp` |
| O5 | Medium | Account enumeration via distinct “email not found” | intentional UX trade-off; still present |
| X1 | High | User chat message into `innerHTML` unescaped | `orderQuotation.js` ~3587 |
| X2 | High | Incomplete `escapeInlineJsString` for product onclick | `orderQuotation.js` |
| C1 | High (control gap) | No CSRF tokens; Origin not validated | mitigated partly by `SameSite=Lax` + JSON bodies |

### Already protected (not regressions)

- Customer QT detail/list: CODE match (+ intentional same-company visibility for submitted QTs).
- Draft detail load: CODE ownership for non-admin.
- Admin `/api/admin/*` cross-customer access gated by `@api_admin_required`.
- Update ownership check exists when bypass flags are absent.

### P1 — Performance (confirmed / prior work)

| ID | Finding | Status |
|----|---------|--------|
| P1 | Flask previously serialized via asgiref `WsgiToAsgi` | Fixed earlier in `715a2b5` (`a2wsgi` workers) |
| P2 | Duplicate `/api/get_product_price` on pick+blur | Fixed earlier (AbortController + dedupe) |
| P3 | `next_docno` waited behind `get_user_info` | Fixed earlier (parallel start) |
| P4 | Global Flask `no-store` on all responses | `/static` already Starlette-mounted; this audit adds long-lived Cache-Control for `/static` |
| P5 | Submit still sequential SQL Accounting + Firebird enrich | Not changed (preserve integration semantics); needs production timing evidence |
| P6 | OTP_STORAGE / multi-worker | Documented remaining risk; Redis not added without ops approval |

**Benchmarks:** Not measured in this pass (no safe timed browser/Playwright run against a controlled environment). Cells below use **Not measured** where required.

---

## Phase 2 — Fixes implemented (this session)

### Modified files

| File | Reason |
|------|--------|
| `main.py` | Production secret enforcement; secure cookies; CSRF Origin guard; OTP validation/attempts/no-log; session clear on login; strip admin bypass flags; draft cleanup ownership; next_docno ownership; static cache middleware; no-cache skip for `/static` |
| `config/otp_config.py` | `secrets`-based OTP; `OTP_MAX_VERIFY_ATTEMPTS` |
| `utils/quotation_api.py` | Draft save ownership gate before line delete |
| `routes/quotation_routes.py` | Server-side email content + ownership + HTML escape + cooldown |
| `static/js/orderQuotation.js` | XSS-safe chat user message; stronger JS string escape |
| `templates/createQuotation.html` | Cache-bust JS |
| `docs/CUSTOMER_QUOTATION_SECURITY_AUDIT_2026-10-29.md` | This report |

### Not implemented (needs separate approval)

1. Shared Redis/DB OTP store for multi-worker.
2. Full CSRF tokens (Flask-WTF) across all UIs — Origin guard added instead as low-risk first step.
3. Submit idempotency keys / duplicate QT prevention beyond existing timeout recovery.
4. Database index migrations for `SL_QT` docno scan.
5. Splitting `main.py` / `orderQuotation.js` into modules.

---

## Phase 3 — Regression notes

Manual / code-level verification (no automated suite run against live Firebird in this session):

| Check | Result |
|-------|--------|
| Customer create path strips `adminUpdate` / `skipCustomerCodeCheck` | Pass (code) |
| Admin update still sets bypass flags server-side | Pass (`main.py` ~11256) |
| Draft save returns error for foreign dockey before DELETE | Pass (code) |
| Email uses `fetch_quotation_details_for_email` + CODE check | Pass (code) |
| OTP no longer logged | Pass (code) |
| Chat user XSS sink uses `textContent` | Pass (code) |
| Python syntax of touched modules | Pass |
| Live browser regression (create/submit/view) | **Not run** — restart app required |
| Automated pytest suite | **Not measured** (prior OTP/env connection issues in sandbox) |

---

## Phase 4 — Before/After comparison

| Category | Before | After | Improvement | Test evidence |
|---|---|---|---|---|
| Initial page load | ~14.1s network-idle (prior doc) | Not measured | — | Prior `PERFORMANCE_AUDIT.md`; not re-measured |
| Time to usable form | Not measured | Not measured | — | — |
| Customer API latency p50/p95 | Not measured | Not measured | Local-first + 90s cache already present | Code path audit |
| Product search p50/p95 | Not measured | Not measured | Debounce + 90s search cache already present | Code path audit |
| Quotation submit p50/p95 | Not measured | Not measured | — | — |
| Total initial requests | ~2–3 `/api/get_user_info` + `next_docno` | Parallel `next_docno`; overlay cacheable | Fewer blocking waits | JS changes (prior + this) |
| JS/CSS transferred KB | Not measured | Not measured | `/static` Cache-Control 7d | Middleware added |
| Memory after 30-min idle | Not measured | Not measured | — | — |
| Idle network requests | Not measured | Not measured | — | — |
| Confirmed security issues | 16 confirmed (table above) | 11 fixed / mitigated this session; 5 remain as approved follow-ups | High IDOR/XSS/OTP log/session issues closed | Code review |
| Automated test results | Not measured | Not measured | — | — |

---

## Remaining risks

1. **OTP_STORAGE is process-local** — with `EQ_FLASK_WORKERS>1`, send/verify can hit different workers. Prefer Redis with TTL under ops approval.
2. **Account enumeration** on OTP send still returns distinct “email not found”.
3. **Same-company visibility** for submitted quotations remains intentional — does not grant edit without ownership CODE.
4. **CSRF**: Origin guard helps; full anti-CSRF tokens not rolled out to all forms.
5. **Submit duplicate QT** under timeout/retry still needs dedicated idempotency design with SQL Accounting.

---

## Rollback

1. Revert the listed files to pre-change commit (or `git checkout` those paths).
2. Restart the unified server.
3. If production was started with `FLASK_ENV=production`, ensure `FLASK_SECRET_KEY` remains set (rollback of this change alone may still require a secret).

---

## Deployment notes

- Set `FLASK_SECRET_KEY` to a unique 32+ character secret **before** enabling production mode.
- Set `FLASK_ENV=production` (or `EQ_REQUIRE_SECURE_COOKIES=1`) so cookies are Secure.
- For local HTTP, keep Secure cookies off via `SESSION_COOKIE_SECURE=0` or non-production `FLASK_ENV`.
- Restart required for `a2wsgi` / middleware / OTP changes.
- Do **not** set `APP=dev` in live production (`debug_otp` in JSON; use `APP=prod`).

---

## Recommendations requiring separate approval

1. Redis-backed OTP + rate limits (IP + email).
2. Flask-WTF / double-submit CSRF tokens for all mutating UI POSTs.
3. Submit idempotency key stored server-side keyed by customer + payload hash.
4. Firebird indexes / smaller docno peek query.
5. Modularize `main.py` and `orderQuotation.js` behind feature-preserving extractions.
