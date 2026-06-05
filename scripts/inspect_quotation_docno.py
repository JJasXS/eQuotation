"""Dump SL_QT / SL_QTDTL numeric fields for a docno; flag values matching targets."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
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


def _dec(v) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v).replace(",", "").strip())
    except Exception:
        return None


def _matches_target(val) -> bool:
    d = _dec(val)
    if d is None:
        return False
    for t in (Decimal("1.96800"), Decimal("0.82000"), Decimal("1.968"), Decimal("0.82")):
        if abs(d - t) < Decimal("0.00001"):
            return True
    return False


def main() -> int:
    _load_dotenv()
    from utils.tenant_bootstrap import apply_tenant_env_overrides

    apply_tenant_env_overrides()
    import fdb
    from utils.db_utils import build_firebird_dsn

    docno = (sys.argv[1] if len(sys.argv) > 1 else "QT-43143").strip()
    db_path = (os.getenv("DB_PATH") or "").strip()
    if not db_path:
        print("DB_PATH not set")
        return 1
    dsn = build_firebird_dsn(db_path, (os.getenv("DB_HOST") or "").strip() or None)
    con = fdb.connect(
        dsn=dsn,
        user=(os.getenv("DB_USER") or "sysdba").strip(),
        password=(os.getenv("DB_PASSWORD") or "masterkey").strip(),
        charset="UTF8",
    )
    cur = con.cursor()
    cur.execute("SELECT DOCKEY, DOCNO, CODE, DOCDATE FROM SL_QT WHERE DOCNO = ?", (docno,))
    hdr = cur.fetchone()
    if not hdr:
        print(f"No SL_QT for DOCNO={docno!r}")
        return 1
    dockey, docno_db, cust, docdate = hdr
    print(f"HEADER dockey={dockey} docno={docno_db!r} customer={cust!r} docdate={docdate}")

    cur.execute(
        """
        SELECT TRIM(RF.RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS RF
        WHERE TRIM(RF.RDB$RELATION_NAME) = 'SL_QTDTL'
        ORDER BY RF.RDB$FIELD_POSITION
        """
    )
    cols = [r[0] for r in cur.fetchall()]
    sql_cols = ", ".join(cols)
    cur.execute(f"SELECT {sql_cols} FROM SL_QTDTL WHERE DOCKEY = ? ORDER BY SEQ", (dockey,))
    rows = cur.fetchall()
    print(f"\nLINES ({len(rows)}):")
    hits: list[str] = []
    for row in rows:
        row_map = dict(zip(cols, row))
        seq = row_map.get("SEQ")
        item = row_map.get("ITEMCODE")
        desc = row_map.get("DESCRIPTION")
        print(f"\n--- SEQ={seq} ITEMCODE={item!r} DESC={(str(desc or '')[:70])!r} ---")
        for c in cols:
            v = row_map.get(c)
            if v is None or str(v).strip() == "":
                continue
            if isinstance(v, (int, float)) or (
                isinstance(v, str) and any(ch in str(v) for ch in ".,")
            ):
                mark = " *** TARGET ***" if _matches_target(v) else ""
                if mark:
                    hits.append(f"SEQ={seq} column=SL_QTDTL.{c} value={v}")
                print(f"  {c} = {v}{mark}")
        for c in cols:
            if c.upper().startswith("UDF_") and row_map.get(c) not in (None, ""):
                continue
    if hits:
        print("\n=== Values 1.96800 / 0.82000 found in ===")
        for h in hits:
            print(" ", h)
    else:
        print("\n(No exact 1.96800 or 0.82000 in SL_QTDTL; check header or SQL API)")

    # SQL API GET if configured
    try:
        from api.config import load_sql_accounting_api_settings
        from api.clients import SqlAccountingApiClient

        settings = load_sql_accounting_api_settings()
        if settings.access_key and settings.secret_key:
            client = SqlAccountingApiClient(settings)
            url = settings.resolved_quotation_update_url(int(dockey))
            st, parsed, raw = client.get_json(url, timeout_seconds=30.0)
            print(f"\nSQL API GET {url} HTTP {st}")
            if st < 400 and isinstance(parsed, dict):
                data = parsed.get("data") or parsed
                if isinstance(data, list) and data:
                    data = data[0]
                lines = (data or {}).get("sdsdocdetail") or []
                for i, line in enumerate(lines, 1):
                    if not isinstance(line, dict):
                        continue
                    print(f"\n--- API line {i} itemcode={line.get('itemcode')!r} ---")
                    for k, v in sorted(line.items()):
                        if v is None or v == "":
                            continue
                        mark = " *** TARGET ***" if _matches_target(v) else ""
                        if mark or k.lower() in (
                            "qty",
                            "sqty",
                            "suomqty",
                            "rate",
                            "unitprice",
                            "amount",
                        ) or str(k).lower().startswith("udf_"):
                            print(f"  {k} = {v}{mark}")
    except Exception as e:
        print(f"\nSQL API skip: {e}")

    cur.close()
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
