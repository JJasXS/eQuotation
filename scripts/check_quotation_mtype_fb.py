"""Print SL_QTDTL.UDF_MTYPE for a quotation docno (local Firebird)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo))


def _load_dotenv() -> None:
    from utils.appsettings_env import apply_appsettings_to_environ

    apply_appsettings_to_environ(project_root=repo)
    env_path = repo / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()
from utils.tenant_bootstrap import apply_tenant_env_overrides

apply_tenant_env_overrides()

import fdb
from utils.db_utils import build_firebird_dsn

docno = (sys.argv[1] if len(sys.argv) > 1 else "QT-80019").strip()
db_path = (os.getenv("DB_PATH") or "").strip()
if not db_path:
    raise SystemExit("DB_PATH not set")
dsn = build_firebird_dsn(db_path, (os.getenv("DB_HOST") or "").strip() or None)
con = fdb.connect(
    dsn=dsn,
    user=(os.getenv("DB_USER") or "sysdba").strip(),
    password=(os.getenv("DB_PASSWORD") or "masterkey").strip(),
    charset="UTF8",
)
cur = con.cursor()
cur.execute(
    """
    SELECT d.SEQ, TRIM(d.ITEMCODE), TRIM(d.DESCRIPTION), TRIM(COALESCE(d.UDF_MTYPE, ''))
    FROM SL_QTDTL d
    JOIN SL_QT h ON h.DOCKEY = d.DOCKEY
    WHERE h.DOCNO = ?
    ORDER BY d.SEQ
    """,
    (docno,),
)
for row in cur.fetchall():
    print(row)
con.close()
