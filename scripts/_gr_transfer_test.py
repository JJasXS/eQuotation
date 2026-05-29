"""TEMP diagnostic: test PO -> Goods Received transfer via SQL Accounting API (/goodsreceived).

Usage (run from eQuotation repo root):
  python scripts/_gr_transfer_test.py inspect  <TENANT_CODE> <PO_DOCNO>
  python scripts/_gr_transfer_test.py transfer <TENANT_CODE> <PO_DOCNO>

`inspect`  = read-only. Fetches the PO + a sample goods-received doc so we can see the
             exact field names and how a transferred line links back (fromdoctype/fromdockey/fromdtlkey).
`transfer` = builds a /goodsreceived payload from the PO lines and POSTs it (creates a real GR).

AWS creds + region are read from the deployed service env (C:\\Apps\\eQuotation\\.env).
"""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_DEPLOYED_ENV = r"C:\Apps\eQuotation\.env"


def _load_deployed_aws_env() -> None:
    """Pull AWS_* creds/region from the deployed .env so Secrets Manager + tenant API work."""
    if not os.path.exists(_DEPLOYED_ENV):
        print(f"WARN: {_DEPLOYED_ENV} not found; relying on ambient AWS creds.", flush=True)
        return
    with open(_DEPLOYED_ENV, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            # Only import AWS plumbing; tenant code comes from argv.
            if k.startswith("AWS_"):
                os.environ.setdefault(k, v)


def _client():
    from api.clients.sql_accounting_client import SqlAccountingApiClient
    from api.config.sql_accounting_api import load_sql_accounting_api_settings

    settings = load_sql_accounting_api_settings()
    if not settings.access_key or not settings.secret_key:
        print("ERROR: SQL_API keys not populated after tenant bootstrap.", flush=True)
        sys.exit(2)
    return SqlAccountingApiClient(settings), settings


def _base(settings) -> str:
    scheme = "https" if settings.use_tls else "http"
    return f"{scheme}://{settings.host.strip().rstrip('/')}"


def _bootstrap(tenant_code: str) -> None:
    _load_deployed_aws_env()
    os.environ["TENANT_CODE"] = tenant_code
    os.environ.pop("TenantBootstrap__TenantCode", None)
    from utils.tenant_bootstrap import apply_tenant_env_overrides

    applied = apply_tenant_env_overrides()
    print(f"tenant_bootstrap applied={applied} tenant={tenant_code}", flush=True)


def _get_po(client, settings, docno: str):
    url = f"{_base(settings)}/purchaseorder/*?docno={docno}"
    status, parsed, raw = client.get_json(url, timeout_seconds=40.0)
    print(f"GET {url} -> HTTP {status}", flush=True)
    return status, parsed, raw


def cmd_inspect(tenant_code: str, docno: str) -> int:
    _bootstrap(tenant_code)
    client, settings = _client()

    print("\n=== PURCHASE ORDER ===", flush=True)
    status, parsed, raw = _get_po(client, settings, docno)
    if not parsed:
        print(f"raw[:2000]={raw[:2000]!r}", flush=True)
    else:
        print(json.dumps(parsed, indent=2, default=str)[:6000], flush=True)

    print("\n=== GOODS RECEIVED (sample list) ===", flush=True)
    url = f"{_base(settings)}/goodsreceived?offset=0"
    status, parsed, raw = client.get_json(url, timeout_seconds=40.0)
    print(f"GET {url} -> HTTP {status}", flush=True)
    sample_docno = None
    if isinstance(parsed, list) and parsed:
        sample_docno = (parsed[0] or {}).get("docno") if isinstance(parsed[0], dict) else None
        print(f"first list item keys: {list(parsed[0].keys()) if isinstance(parsed[0], dict) else parsed[0]}", flush=True)
    elif isinstance(parsed, dict):
        print(f"dict keys: {list(parsed.keys())}", flush=True)
    else:
        print(f"raw[:1500]={raw[:1500]!r}", flush=True)

    if sample_docno:
        print(f"\n=== GOODS RECEIVED single ({sample_docno}) — look for fromdoctype on lines ===", flush=True)
        url = f"{_base(settings)}/goodsreceived/*?docno={sample_docno}"
        status, parsed, raw = client.get_json(url, timeout_seconds=40.0)
        print(f"GET {url} -> HTTP {status}", flush=True)
        if parsed:
            print(json.dumps(parsed, indent=2, default=str)[:6000], flush=True)
        else:
            print(f"raw[:2000]={raw[:2000]!r}", flush=True)
    return 0


def _po_root(parsed):
    """PO GET returns {"data":[{...}]} (or sometimes a bare list/dict)."""
    if isinstance(parsed, dict) and isinstance(parsed.get("data"), list) and parsed["data"]:
        first = parsed["data"][0]
        return first if isinstance(first, dict) else None
    if isinstance(parsed, list) and parsed:
        return parsed[0] if isinstance(parsed[0], dict) else None
    if isinstance(parsed, dict):
        return parsed
    return None


def cmd_transfer(tenant_code: str, docno: str) -> int:
    _bootstrap(tenant_code)
    client, settings = _client()

    status, parsed, raw = _get_po(client, settings, docno)
    po = _po_root(parsed)
    if not po:
        print(f"Could not load PO {docno}. raw[:1500]={raw[:1500]!r}", flush=True)
        return 1

    po_dockey = po.get("dockey")
    lines = po.get("sdsdocdetail") or []
    if not po_dockey or not lines:
        print(f"PO missing dockey/sdsdocdetail. keys={list(po.keys())}", flush=True)
        return 1

    today = __import__("datetime").date.today().isoformat()

    detail = []
    for ln in lines:
        if not isinstance(ln, dict):
            continue
        # For a transfer, leave qty at 0 so SQL pulls the outstanding balance from the
        # source PO line (providing qty here gets ADDED on top of the pulled balance).
        qty_env = (os.getenv("GR_LINE_QTY") or "0").strip()
        detail.append({
            "dtlkey": -1,
            "seq": ln.get("seq", 0),
            "itemcode": ln.get("itemcode", ""),
            "location": ln.get("location", "") or "----",
            "batch": ln.get("batch") or "",
            "project": ln.get("project", "") or "----",
            "description": ln.get("description", "") or "",
            "qty": qty_env,
            "uom": ln.get("uom", ""),
            "unitprice": str(ln.get("unitprice") or "0"),
            "irbm_classification": ln.get("irbm_classification") or "",
            "deliverydate": ln.get("deliverydate") or today,
            # Transfer linkage back to the source PO line:
            "fromdoctype": "PO",
            "fromdockey": po_dockey,
            "fromdtlkey": ln.get("dtlkey", 0),
            "transferable": True,
        })

    def _c(key, default=""):
        v = po.get(key)
        return v if v not in (None, "") else default

    payload = {
        "dockey": 0,
        "docno": "",
        "docdate": today,
        "postdate": today,
        "taxdate": today,
        "code": _c("code"),
        "companyname": _c("companyname"),
        "area": _c("area", "----"),
        "agent": _c("agent", "----"),
        "project": _c("project", "----"),
        "terms": _c("terms"),
        "shipper": _c("shipper", "----"),
        "currencycode": _c("currencycode", "----"),
        "currencyrate": str(_c("currencyrate", "1")),
        "branchname": _c("branchname"),
        "tin": _c("tin"),
        "sic": _c("sic"),
        "description": f"GR from {docno} (API transfer test)",
        "cancelled": False,
        "status": 0,
        "transferable": True,
        "sdsdocdetail": detail,
    }

    url = f"{_base(settings)}/goodsreceived"
    start_seq = int(sys.argv[4]) if len(sys.argv) >= 5 else 5
    status = None
    parsed = None
    raw = ""
    for seq in range(start_seq, start_seq + 20):
        payload["docno"] = f"GR-{seq:05d}"
        print(f"\n=== POST /goodsreceived docno={payload['docno']} ===", flush=True)
        if seq == start_seq:
            print(json.dumps(payload, indent=2, default=str)[:6000], flush=True)
        status, parsed, raw = client.post_json(url, payload, timeout_seconds=60.0)
        print(f"-> HTTP {status} : {raw[:600]!r}", flush=True)
        text = (raw or "").lower()
        if status and status >= 400 and ("unique" in text and "document" in text):
            continue  # docno collision -> try next number
        break

    print("\n=== RE-FETCH PO to confirm transferred ===", flush=True)
    status2, parsed2, raw2 = _get_po(client, settings, docno)
    po2 = _po_root(parsed2)
    if po2:
        print(f"PO transferable={po2.get('transferable')} status={po2.get('status')}", flush=True)
        for ln in (po2.get("sdsdocdetail") or []):
            if isinstance(ln, dict):
                print(f"  line dtlkey={ln.get('dtlkey')} qty={ln.get('qty')} transferable={ln.get('transferable')}", flush=True)
    return 0


def cmd_listpo(tenant_code: str) -> int:
    _bootstrap(tenant_code)
    client, settings = _client()
    url = f"{_base(settings)}/purchaseorder?offset=0"
    status, parsed, raw = client.get_json(url, timeout_seconds=40.0)
    print(f"GET {url} -> HTTP {status}", flush=True)
    rows = parsed.get("data") if isinstance(parsed, dict) else parsed
    if isinstance(rows, list):
        print(f"{len(rows)} PO rows (showing up to 15):", flush=True)
        for r in rows[:15]:
            if isinstance(r, dict):
                print(f"  docno={r.get('docno')} dockey={r.get('dockey')} "
                      f"code={r.get('code')} company={r.get('companyname')} "
                      f"transferable={r.get('transferable')} status={r.get('status')}", flush=True)
        if rows and isinstance(rows[0], dict):
            print(f"\nfirst PO row keys: {list(rows[0].keys())}", flush=True)
    else:
        print(f"raw[:2000]={raw[:2000]!r}", flush=True)
    return 0


def cmd_newpo(tenant_code: str) -> int:
    """Create a fresh PO (clone of PO-00004's item) so we have outstanding balance to transfer."""
    _bootstrap(tenant_code)
    client, settings = _client()
    src_status, src_parsed, _ = _get_po(client, settings, "PO-00004")
    src = _po_root(src_parsed)
    if not src:
        print("Could not load template PO-00004.", flush=True)
        return 1
    ln = (src.get("sdsdocdetail") or [{}])[0]
    today = __import__("datetime").date.today().isoformat()
    qty = (os.getenv("PO_LINE_QTY") or "5").strip()
    payload = {
        "dockey": 0, "docno": "", "docdate": today, "postdate": today, "taxdate": today,
        "code": src.get("code", ""), "companyname": src.get("companyname", ""),
        "area": "----", "agent": "----", "project": "----", "terms": src.get("terms", ""),
        "shipper": "----", "currencycode": src.get("currencycode", "----"),
        "currencyrate": str(src.get("currencyrate") or "1"),
        "description": "API transfer test PO", "cancelled": False, "status": 0, "transferable": True,
        "sdsdocdetail": [{
            "dtlkey": -1, "seq": 1000, "itemcode": ln.get("itemcode", ""),
            "location": ln.get("location", "") or "----", "batch": ln.get("batch") or "",
            "project": "----", "description": ln.get("description", "") or "",
            "qty": qty, "uom": ln.get("uom", ""), "unitprice": "0",
            "irbm_classification": ln.get("irbm_classification") or "", "transferable": True,
        }],
    }
    url = f"{_base(settings)}/purchaseorder"
    for seq in range(90001, 90021):
        payload["docno"] = f"PO-{seq:05d}"
        status, parsed, raw = client.post_json(url, payload, timeout_seconds=60.0)
        print(f"POST {url} docno={payload['docno']} -> HTTP {status} : {raw[:300]!r}", flush=True)
        text = (raw or "").lower()
        if status and status >= 400 and "unique" in text and "document" in text:
            continue
        break
    return 0


def cmd_delete(tenant_code: str, entity: str, dockey: str) -> int:
    _bootstrap(tenant_code)
    client, settings = _client()
    url = f"{_base(settings)}/{entity}/{dockey}"
    resp = client._sign_and_send_json("DELETE", url, b"", timeout_seconds=40.0)
    print(f"DELETE {url} -> HTTP {resp.status_code} : {(resp.text or '')[:400]!r}", flush=True)
    return 0


def cmd_listgr(tenant_code: str) -> int:
    _bootstrap(tenant_code)
    client, settings = _client()
    url = f"{_base(settings)}/goodsreceived?offset=0"
    status, parsed, raw = client.get_json(url, timeout_seconds=40.0)
    print(f"GET {url} -> HTTP {status}", flush=True)
    rows = parsed.get("data") if isinstance(parsed, dict) else parsed
    pag = parsed.get("pagination") if isinstance(parsed, dict) else None
    print(f"pagination={pag}", flush=True)
    if isinstance(rows, list):
        print(f"{len(rows)} GR rows:", flush=True)
        for r in rows[:20]:
            if isinstance(r, dict):
                print(f"  docno={r.get('docno')} dockey={r.get('dockey')} status={r.get('status')}", flush=True)
    else:
        print(f"raw[:1500]={raw[:1500]!r}", flush=True)
    return 0


def cmd_getgr(tenant_code: str, docno: str) -> int:
    _bootstrap(tenant_code)
    client, settings = _client()
    url = f"{_base(settings)}/goodsreceived/*?docno={docno}"
    status, parsed, raw = client.get_json(url, timeout_seconds=40.0)
    print(f"GET {url} -> HTTP {status}", flush=True)
    root = _po_root(parsed)
    if root:
        print(f"GR docno={root.get('docno')} dockey={root.get('dockey')} status={root.get('status')}", flush=True)
        for ln in (root.get("sdsdocdetail") or []):
            if isinstance(ln, dict):
                print("  FULL LINE: " + json.dumps(ln, default=str), flush=True)
    else:
        print(f"raw[:2000]={raw[:2000]!r}", flush=True)
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "listpo":
        return cmd_listpo(sys.argv[2])
    if len(sys.argv) >= 3 and sys.argv[1] == "listgr":
        return cmd_listgr(sys.argv[2])
    if len(sys.argv) >= 4 and sys.argv[1] == "getgr":
        return cmd_getgr(sys.argv[2], sys.argv[3])
    if len(sys.argv) >= 3 and sys.argv[1] == "newpo":
        return cmd_newpo(sys.argv[2])
    if len(sys.argv) >= 5 and sys.argv[1] == "delete":
        return cmd_delete(sys.argv[2], sys.argv[3], sys.argv[4])
    if len(sys.argv) < 4:
        print(__doc__, flush=True)
        return 64
    cmd, tenant_code, docno = sys.argv[1], sys.argv[2], sys.argv[3]
    if cmd == "inspect":
        return cmd_inspect(tenant_code, docno)
    if cmd == "transfer":
        return cmd_transfer(tenant_code, docno)
    print(f"Unknown command {cmd!r}", flush=True)
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
