# API

FastAPI is served under `EQ_SQL_API_MOUNT_PATH` (default `/eq-sql-api`) when running `python main.py`. Auth headers used by the Postman collection: `X-Access-Key` and `X-Secret-Key` (`API_ACCESS_KEY` / `API_SECRET_KEY`).

Base URL example: `http://localhost:8880/eq-sql-api`.

## Health

| Method | Path | Notes |
|--------|------|--------|
| GET | `/health` | Liveness |

## Customers

| Method | Path | Notes |
|--------|------|--------|
| POST | `/customers` | Create customer |
| GET | `/customers/{customer_code}/state` | Customer state |
| GET | `/local/customers/all` | Local Firebird customer list |
| POST | `/local/customers` | Create/update local customer |

## Auth

| Method | Path | Notes |
|--------|------|--------|
| GET | `/auth/email-lookup` | Email lookup for sign-in |

## Suppliers

| Method | Path | Notes |
|--------|------|--------|
| GET | `/supplier` | Supplier list |

## Purchase requests

| Method | Path | Notes |
|--------|------|--------|
| GET | `/purchaserequest` | List |
| GET | `/purchaserequest/{request_ref}` | Detail |
| POST | `/purchaserequest/detail-approval` | Line approval |
| POST | `/purchaserequest/header-status` | Header status |

## Dashboard

| Method | Path | Notes |
|--------|------|--------|
| GET | `/dashboard/sales-cycle-metrics` | Metrics |
| GET | `/dashboard/sales-cycle-details` | Details |
| GET | `/dashboard/qt-iv-conversion-report` | QT to IV report |

## Debug

| Method | Path | Notes |
|--------|------|--------|
| GET | `/debug/com/customer-metadata` | COM metadata (debug) |

Postman collection: [eQuotation_API.postman_collection.json](eQuotation_API.postman_collection.json). Setup: [FASTAPI_SETUP.md](FASTAPI_SETUP.md).
