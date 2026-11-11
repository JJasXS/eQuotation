"""Read-only ACC-ANOZ discovery: PH_PO COM BizObject + dataset FieldNames.

Does not New/Edit/Save. Does not call paid REST. Prints mapping candidates
for a future purchase-order SDK writer.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)


def _apply_lab_env() -> None:
    os.environ["SQL_ACCOUNTING_BLOCK_REST_HTTP"] = "true"
    os.environ["SQL_API_ACCESS_KEY"] = ""
    os.environ["SQL_API_SECRET_KEY"] = ""
    os.environ["SQLACC_SDK_ALLOW_LIVE_COM"] = "true"
    os.environ.setdefault("SQLACC_COM_PROG_ID", "SQLAcc.BizApp")
    os.environ.setdefault("SQLACC_SDK_DCF_PATH", r"\\192.168.100.201\Share\SQLACC.DCF")
    os.environ.setdefault("SQLACC_SDK_DATABASE_FILE", "ACC-ANOZ.FDB")
    os.environ.setdefault("SQLACC_SDK_USER", "ADMIN")


def _field_names(dataset) -> list[str]:
    names: list[str] = []
    fields = dataset.Fields
    for i in range(int(fields.Count)):
        field = fields.Items(i)
        names.append(str(getattr(field, "FieldName", None) or f"F{i}"))
    return names


def _dataset_names(biz) -> list[str]:
    names: list[str] = []
    datasets = biz.DataSets
    for i in range(int(datasets.Count)):
        ds = datasets.Items(i)
        names.append(str(getattr(ds, "Name", None) or getattr(ds, "name", None) or f"DS{i}"))
    return names


def main() -> int:
    _apply_lab_env()
    if not (os.getenv("SQLACC_SDK_PASSWORD") or "").strip():
        print("FAIL: SQLACC_SDK_PASSWORD missing", flush=True)
        return 2

    from api.adapters.sqlacc_session import get_sqlacc_session_manager

    candidates = ("PH_PO", "PurchaseOrder", "PURCHASEORDER", "PO")

    def _discover(app):
        found = []
        for name in candidates:
            try:
                biz = app.BizObjects.Find(name)
            except Exception as exc:
                found.append({"name": name, "error": str(exc)})
                continue
            if biz is None:
                found.append({"name": name, "error": "Find returned None"})
                continue
            try:
                ds_names = _dataset_names(biz)
            except Exception as exc:
                found.append({"name": name, "error": f"DataSets: {exc}"})
                continue
            detail: dict = {"name": name, "datasets": ds_names, "fields": {}}
            for ds_name in ds_names:
                try:
                    ds = biz.DataSets.Find(ds_name)
                    detail["fields"][ds_name] = _field_names(ds)
                except Exception as exc:
                    detail["fields"][ds_name] = [f"<error {exc}>"]
            found.append(detail)
        return found

    manager = get_sqlacc_session_manager()
    print("[LAB] Discovering PO BizObject on ACC-ANOZ (read-only)…", flush=True)
    results = manager.run(_discover)
    ok = False
    for item in results:
        print("---", flush=True)
        if item.get("error"):
            print(f"  {item['name']}: ERROR {item['error']}", flush=True)
            continue
        ok = True
        print(f"  BizObject={item['name']}", flush=True)
        print(f"  DataSets={item.get('datasets')}", flush=True)
        for ds_name, fields in (item.get("fields") or {}).items():
            print(f"  [{ds_name}] ({len(fields)} fields):", flush=True)
            for fname in fields:
                print(f"    - {fname}", flush=True)
    if not ok:
        print("FAIL: no usable PH_PO BizObject found", flush=True)
        return 1
    print("PASS: PO BizObject metadata captured (no writes).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
