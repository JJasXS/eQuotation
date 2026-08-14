# Tenant AWS config refresh + license countdown banner

Reusable checklist for ProAcc apps that load tenant settings from DynamoDB via the
tenant-config HTTP API (same pattern as eQuotation / ProAccScanner).

## What this gives you

1. **Startup fetch** of tenant JSON (DB link, SQL API, OpenAI, email, **license**).
2. **Background refresh every 24 hours** so Dynamo changes (DB path, `license.expiryDate`, etc.)
   apply without a manual restart (after the interval elapses).
3. **UI banner** when license expiry is within **10 days**:
   - `10 days left` … `2 days left`
   - `1 day left`
   - `License expires today` / `License expired`

## DynamoDB shape (TENANT_CONFIG)

Partition key: `tenantCode` (e.g. `TNT10004`).

License map:

```json
"license": {
  "expiryDate": "2027-04-30",
  "licenseStatus": "ACTIVE",
  "maxUsers": "5",
  "maxDevices": "3"
}
```

(Dynamo attribute types may be `S` / `N` / `M`; the bootstrap unwraps them.)

## eQuotation implementation (reference)

| Piece | Location |
|-------|----------|
| Fetch + apply env + license snapshot | `utils/tenant_bootstrap.py` → `apply_tenant_env_overrides()` |
| 24h worker | `start_tenant_config_refresh_worker()` (started from `main.py` + `api/app.py`) |
| Banner context | `license_banner_context()` via Flask `@app.context_processor` |
| Banner HTML | `templates/components/license_expiry_banner.html` |
| Styles | `static/css/tenant_env_chip.css` (`.license-expiry-banner`) |
| Interval config | `TenantBootstrap.ConfigRefreshSeconds` / env `TENANT_BOOTSTRAP_REFRESH_SECONDS` (default `86400`; `0` = off) |

## Porting to a new project

1. Copy / share the tenant bootstrap that already calls the ProAcc tenant API.
2. On successful fetch, read `license.expiryDate` into memory (and optional env `TENANT_LICENSE_EXPIRY`).
3. Start a **daemon** refresh loop sleeping `ConfigRefreshSeconds` (86400).
4. On refresh success, re-apply DB env and resync your DB connection helper.
5. Add a shared header banner component that shows when `1 <= days_left <= 10`.
6. Document the original `expiryDate` before any temporary test change.

## Temporary test (show “10 days left”)

Today = 2026-08-14 → set expiry to **2026-08-24**.

```powershell
aws dynamodb update-item `
  --region ap-southeast-1 `
  --table-name TENANT_CONFIG `
  --key '{"tenantCode":{"S":"TNT10004"}}' `
  --update-expression "SET #lic.#exp = :d" `
  --expression-attribute-names '{"#lic":"license","#exp":"expiryDate"}' `
  --expression-attribute-values '{":d":{"S":"2026-08-24"}}'
```

Restart the app (or wait for the next refresh) so the banner picks up the new date.

### Change back (production demo expiry)

Original eQuotation / TNT10004 value before this test:

```text
2027-04-30
```

```powershell
aws dynamodb update-item `
  --region ap-southeast-1 `
  --table-name TENANT_CONFIG `
  --key '{"tenantCode":{"S":"TNT10004"}}' `
  --update-expression "SET #lic.#exp = :d" `
  --expression-attribute-names '{"#lic":"license","#exp":"expiryDate"}' `
  --expression-attribute-values '{":d":{"S":"2027-04-30"}}'
```

Then restart (or wait for refresh).

## Notes

- DynamoDB **TTL is separate** — `license.expiryDate` does **not** auto-delete the row unless you enable TTL on another attribute.
- Management still needs a process restart to see a change **immediately**; the 24h worker covers unattended updates.
- Banner threshold is hard-coded at **10 days** in eQuotation (`_LICENSE_BANNER_MAX_DAYS`).
