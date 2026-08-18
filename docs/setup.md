# Setup

## Requirements

- Python 3.12 recommended
- SQL Accounting Firebird client libraries (`fdb`)
- Tenant-config API URL when using `TENANT_CODE`

## Local run

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill `TENANT_CODE`, `TENANT_BOOTSTRAP_API_URL`, `DB_PASSWORD`, and `FLASK_SECRET_KEY`. For local work without AWS: `TENANT_BOOTSTRAP_SKIP_SECRETS=1` and set `DB_*` / `SQL_API_*` in `.env`. API-oriented keys: `.env.example.api`.

```powershell
python main.py
```

UI: `http://localhost:8880` (`FLASK_PORT`). FastAPI: `http://localhost:8880/eq-sql-api`.

Firebird notes: [FIREBIRD_SETUP.md](FIREBIRD_SETUP.md). Auth: [AUTH_SETUP.md](AUTH_SETUP.md). FastAPI: [FASTAPI_SETUP.md](FASTAPI_SETUP.md).
