"""Quotation API orchestration helpers."""

import json
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import random

import requests

from api.clients import SqlAccountingApiClient, SqlAccountingApiError
from api.config import load_sql_accounting_api_settings


_QT_DOCNO_RE = re.compile(r"^QT-(\d{5})$")


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _app_docno_range() -> tuple[int, int]:
    """Return inclusive app reservation range for QT-%.5d numbers."""
    min_seq = _int_env("SQL_API_QUOTATION_DOCNO_MIN", 80000)
    max_seq = _int_env("SQL_API_QUOTATION_DOCNO_MAX", 99999)
    if min_seq < 1:
        min_seq = 1
    if max_seq > 99999:
        max_seq = 99999
    if min_seq > max_seq:
        min_seq, max_seq = 80000, 99999
    return min_seq, max_seq


def _decode_php_json_response(response, endpoint_path):
    """Parse JSON from PHP; return a failed dict if empty/non-JSON."""
    text = (response.text or "").strip()
    if not text:
        return {
            "success": False,
            "error": (
                f"Empty response from {endpoint_path} (HTTP {response.status_code}). "
                "Check that Apache/PHP is running and BASE_API_URL points at your web root."
            ),
        }
    try:
        return response.json()
    except json.JSONDecodeError:
        snippet = text[:400].replace("\n", " ")
        return {
            "success": False,
            "error": (
                f"Non-JSON response from {endpoint_path} (HTTP {response.status_code}): {snippet}"
            ),
        }


def _as_decimal(value, default="0.00"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _fmt_money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


def _format_qt_docno(sequence: int) -> str:
    if sequence < 1:
        sequence = 1
    return f"QT-{sequence:05d}"


def _read_qt_sequences_from_db(limit: int = 2000) -> tuple[int, set[int]]:
    """Return (max_seq, existing_seq_set) for DOCNO values matching QT-%.5d."""
    db_path = (os.getenv("DB_PATH") or "").strip()
    db_host = (os.getenv("DB_HOST") or "").strip()
    db_user = (os.getenv("DB_USER") or "sysdba").strip()
    db_password = (os.getenv("DB_PASSWORD") or "masterkey").strip()
    if not db_path:
        return 0, set()

    try:
        import fdb

        dsn = db_path if not db_host else f"{db_host}:{db_path}"
        con = fdb.connect(dsn=dsn, user=db_user, password=db_password, charset="UTF8")
        cur = con.cursor()
        cur.execute(f"SELECT FIRST {int(limit)} DOCNO FROM SL_QT ORDER BY DOCKEY DESC")
        rows = cur.fetchall() or []
        cur.close()
        con.close()

        max_seq = 0
        existing = set()
        for row in rows:
            raw = str(row[0] or "").strip()
            m = _QT_DOCNO_RE.match(raw)
            if not m:
                continue
            seq = int(m.group(1))
            existing.add(seq)
            if seq > max_seq:
                max_seq = seq
        return max_seq, existing
    except Exception:
        return 0, set()


def _fallback_qt_docno() -> str:
    # Last-resort formatter that still follows QT-%.5d.
    return _format_qt_docno(int(datetime.now().strftime("%H%M%S")) % 100000 or 1)


def _next_qt_docno_candidate(max_seq: int, existing: set[int], attempt: int) -> str:
    """Pick a docno candidate in QT-%.5d format with low collision probability."""
    min_seq, max_seq_allowed = _app_docno_range()

    if attempt == 0:
        baseline = max(max_seq, min_seq - 1)
        candidate = baseline + 1
        if candidate <= max_seq_allowed and candidate not in existing:
            return _format_qt_docno(candidate)

    # On retries, pick random available 5-digit slot to avoid racing with other systems using max+1.
    for _ in range(30):
        seq = random.randint(min_seq, max_seq_allowed)
        if seq not in existing:
            return _format_qt_docno(seq)

    # Fallback to linear probe if random space is saturated.
    start = max(min_seq, max_seq + 1)
    if start > max_seq_allowed:
        start = min_seq
    span = (max_seq_allowed - min_seq) + 1
    for i in range(span):
        seq = min_seq + ((start - min_seq + i) % span)
        if seq not in existing:
            return _format_qt_docno(seq)

    # Range exhausted.
    return ""


def _is_unique_docno_error(status: int, parsed, raw: str) -> bool:
    if status < 400:
        return False
    detail = raw or ""
    if isinstance(parsed, dict):
        detail = str(parsed.get("message") or parsed.get("error") or parsed)
    text = detail.lower()
    return (
        ("unique" in text or "duplicate value" in text)
        and ("document no" in text or "docno" in text or "doc no" in text)
    )


def _build_salesquotation_payload(customer_code, data, *, doc_no: str):
    today = date.today().isoformat()
    valid_until = str(data.get("validUntil") or data.get("validity") or "").strip()
    doc_date = today
    post_date = today
    tax_date = today
    currency_code = str(data.get("currencyCode") or "MYR").strip() or "MYR"
    currency_rate = _as_decimal(data.get("currencyRate") or "1.00", "1.00")

    company_name = str(data.get("companyName") or "").strip()
    address1 = str(data.get("address1") or "").strip()
    address2 = str(data.get("address2") or "").strip()
    address3 = str(data.get("address3") or "").strip()
    address4 = str(data.get("address4") or "").strip()
    phone1 = str(data.get("phone1") or "").strip()
    terms = str(data.get("terms") or data.get("creditTerm") or "30 Days").strip() or "30 Days"
    description = str(data.get("description") or "Quotation").strip() or "Quotation"
    shipper = str(data.get("shipper") or "----").strip() or "----"

    detail_rows = []
    total_doc_amt = Decimal("0.00")
    for idx, item in enumerate(data.get("items") or [], start=1):
        qty = _as_decimal(item.get("qty") or 0)
        unit_price = _as_decimal(item.get("price") or 0)
        discount = _as_decimal(item.get("discount") or 0)
        gross = qty * unit_price
        line_amount = gross - discount
        if line_amount < Decimal("0.00"):
            line_amount = Decimal("0.00")
        total_doc_amt += line_amount

        delivery_date = str(item.get("deliveryDate") or "").strip() or doc_date
        product_desc = str(item.get("product") or "").strip()
        if not product_desc:
            continue

        detail_rows.append(
            {
                "dtlkey": 0,
                "dockey": 0,
                "seq": idx,
                "styleid": "",
                "number": "",
                "itemcode": "",
                "location": "",
                "batch": "",
                "project": "",
                "description": product_desc,
                "description2": "",
                "description3": "",
                "permitno": "",
                "qty": _fmt_money(qty),
                "uom": "",
                "rate": "1.00",
                "sqty": _fmt_money(qty),
                "suomqty": _fmt_money(qty),
                "unitprice": _fmt_money(unit_price),
                "deliverydate": delivery_date,
                "disc": "",
                "tax": "",
                "tariff": "",
                "taxexemptionreason": "",
                "irbm_classification": "",
                "taxrate": "",
                "taxamt": "0.00",
                "localtaxamt": "0.00",
                "exempted_taxrate": "",
                "exempted_taxamt": "0.00",
                "taxinclusive": True,
                "amount": _fmt_money(line_amount),
                "localamount": _fmt_money(line_amount * currency_rate),
                "amountwithtax": _fmt_money(line_amount),
                "printable": True,
                "transferable": False,
                "remark1": "",
                "remark2": "",
                "companyitemcode": "",
                "initialpurchasecost": "0.00",
                "changed": True,
            }
        )

    return {
        "dockey": 0,
        "docno": doc_no,
        "docnoex": "",
        "docdate": doc_date,
        "postdate": post_date,
        "taxdate": tax_date,
        "code": str(customer_code or "").strip(),
        "companyname": company_name,
        "address1": address1,
        "address2": address2,
        "address3": address3,
        "address4": address4,
        "postcode": "",
        "city": "",
        "state": "",
        "country": "",
        "phone1": phone1,
        "mobile": "",
        "fax1": "",
        "attention": "",
        "area": "",
        "agent": "",
        "project": "",
        "terms": terms,
        "currencycode": currency_code,
        "currencyrate": _fmt_money(currency_rate),
        "shipper": shipper,
        "description": description,
        "cancelled": False,
        "status": 0,
        "docamt": _fmt_money(total_doc_amt),
        "localdocamt": _fmt_money(total_doc_amt * currency_rate),
        "validity": valid_until,
        "deliveryterm": "",
        "cc": "",
        "docref1": "",
        "docref2": "",
        "docref3": "",
        "docref4": "",
        "branchname": "",
        "daddress1": address1,
        "daddress2": address2,
        "daddress3": address3,
        "daddress4": address4,
        "dpostcode": "",
        "dcity": "",
        "dstate": "",
        "dcountry": "",
        "dattention": "",
        "dphone1": phone1,
        "dmobile": "",
        "dfax1": "",
        "taxexemptno": "",
        "salestaxno": "",
        "servicetaxno": "",
        "tin": "",
        "idtype": 0,
        "idno": "",
        "tourismno": "",
        "sic": "",
        "incoterms": "",
        "businessunit": "",
        "attachments": "",
        "submissiontype": 0,
        "note": "",
        "approvestate": "",
        "updatecount": 0,
        "transferable": False,
        "printcount": 0,
        "lastmodified": 0,
        "sdsdocdetail": detail_rows,
        "changed": True,
        "docnosetkey": 0,
        "nextdocno": "",
        "im_scan_autokey": 0,
    }


def create_or_update_quotation(base_api_url, customer_code, data):
    """Create quotation via SQL Accounting API salesquotation endpoint.

    Returns a dict compatible with Flask caller expectations.
    """
    if not customer_code:
        return {"success": False, "error": "Customer code not found in session"}

    items = data.get("items") or []
    if not items:
        return {"success": False, "error": "At least one item is required"}

    settings = load_sql_accounting_api_settings()
    quote_path = (os.getenv("SQL_API_SALES_QUOTATION_PATH") or settings.quotation_create_path or "").strip()
    if not quote_path:
        return {"success": False, "error": "SQL_API_SALES_QUOTATION_PATH is not configured in .env"}
    if not settings.access_key or not settings.secret_key:
        return {"success": False, "error": "SQL API keys are not configured"}

    provided_docno = str(data.get("docno") or data.get("docNo") or "").strip()

    client = SqlAccountingApiClient(settings)
    last_error = ""
    for attempt in range(20):
        if provided_docno:
            doc_no = provided_docno
        else:
            max_seq, existing = _read_qt_sequences_from_db(limit=2000)
            if max_seq == 0 and not existing and attempt == 0:
                doc_no = _fallback_qt_docno()
            else:
                doc_no = _next_qt_docno_candidate(max_seq, existing, attempt)

        if not doc_no:
            min_seq, max_seq_allowed = _app_docno_range()
            return {
                "success": False,
                "error": (
                    f"No available quotation number in reserved range QT-{min_seq:05d}..QT-{max_seq_allowed:05d}."
                ),
            }

        payload = _build_salesquotation_payload(customer_code, data, doc_no=doc_no)
        if not payload.get("sdsdocdetail"):
            return {"success": False, "error": "No valid quotation item rows to submit"}

        try:
            status, parsed, raw = client.post_json(settings.resolved_quotation_create_url(), payload)
        except SqlAccountingApiError as exc:
            return {"success": False, "error": str(exc)}

        if status < 400:
            response_dict = parsed if isinstance(parsed, dict) else {}
            data_obj = response_dict.get("data") if isinstance(response_dict.get("data"), dict) else {}
            return {
                "success": True,
                "dockey": response_dict.get("dockey") or data_obj.get("dockey") or data_obj.get("docKey") or 0,
                "docno": response_dict.get("docno") or data_obj.get("docno") or data_obj.get("docNo") or doc_no,
                "message": response_dict.get("message") or "Quotation created successfully",
                "upstream": response_dict or {"raw": raw},
            }

        detail = raw
        if isinstance(parsed, dict):
            detail = str(parsed.get("message") or parsed.get("error") or parsed)
        last_error = f"SQL Accounting API returned HTTP {status}: {detail}"

        if provided_docno or not _is_unique_docno_error(status, parsed, raw):
            return {"success": False, "error": last_error}

    return {"success": False, "error": last_error or "Failed to create quotation"}


def save_draft_quotation(base_api_url, customer_code, data):
    """Save a quotation draft directly to Firebird DB (no PHP)."""
    from utils import get_db_connection
    import traceback
    dockey = data.get('dockey')
    description = (data.get('description', '') or '').strip() or 'Draft Quotation'
    valid_until = data.get('validUntil', '')
    currency_code = data.get('currencyCode', 'MYR')
    docno_input = str(data.get('docno') or data.get('docNo') or '').strip()
    shipper = str(data.get('shipper') or '----').strip() or '----'
    company_name = data.get('companyName', '')
    address1 = data.get('address1', '')
    address2 = data.get('address2', '')
    phone1 = data.get('phone1', '')
    items = data.get('items', [])
    docdate = datetime.now().date()
    terms = str(data.get('terms') or data.get('creditTerm') or '30 Days').strip() or '30 Days'
    total_doc_amt = sum(float(item.get('qty', 0)) * float(item.get('price', 0)) for item in items)

    try:
        con = get_db_connection()
        cur = con.cursor()
        # Insert or update draft header
        if dockey:
            # Update existing draft
            cur.execute("""
                UPDATE SL_QTDRAFT SET DESCRIPTION=?, VALIDITY=?, TERMS=?, DOCAMT=?, COMPANYNAME=?, ADDRESS1=?, ADDRESS2=?, PHONE1=?, CURRENCYCODE=?, DOCDATE=?
                WHERE DOCKEY=? AND CODE=?
            """, (description, valid_until, terms, total_doc_amt, company_name, address1, address2, phone1, currency_code, docdate, dockey, customer_code))
        else:
            # Get next DOCKEY from generator/sequence (fallback to MAX+1 if generator is unavailable)
            try:
                cur.execute("SELECT GEN_ID(GEN_SL_QTDRAFT_ID, 1) FROM RDB$DATABASE")
                dockey = cur.fetchone()[0]
            except Exception:
                cur.execute("SELECT COALESCE(MAX(DOCKEY), 0) + 1 FROM SL_QTDRAFT")
                dockey = cur.fetchone()[0]

            docno = docno_input or f"DRAFT-{int(dockey):05d}"
            cur.execute("""
                INSERT INTO SL_QTDRAFT (DOCKEY, DOCNO, CODE, DESCRIPTION, VALIDITY, TERMS, DOCAMT, SHIPPER, COMPANYNAME, ADDRESS1, ADDRESS2, PHONE1, CURRENCYCODE, DOCDATE)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (dockey, docno, customer_code, description, valid_until, terms, total_doc_amt, shipper, company_name, address1, address2, phone1, currency_code, docdate))

        # Remove old draft items
        cur.execute("DELETE FROM SL_QTDTLDRAFT WHERE DOCKEY=?", (dockey,))
        # Insert draft items
        for idx, item in enumerate(items, start=1):
            qty = float(item.get('qty', 0))
            price = float(item.get('price', 0))
            discount = float(item.get('discount', 0))
            product_desc = str(item.get('product', '')).strip()
            if not product_desc:
                continue
            try:
                cur.execute("SELECT GEN_ID(GEN_SL_QTDTLDRAFT_ID, 1) FROM RDB$DATABASE")
                dtlkey = cur.fetchone()[0]
            except Exception:
                cur.execute("SELECT COALESCE(MAX(DTLKEY), 0) + 1 FROM SL_QTDTLDRAFT")
                dtlkey = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO SL_QTDTLDRAFT (DTLKEY, DOCKEY, SEQ, DESCRIPTION, QTY, UNITPRICE, DISC)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (dtlkey, dockey, idx, product_desc, qty, price, str(discount)))

        con.commit()
        cur.close()
        con.close()
        return {"success": True, "dockey": dockey, "docno": None, "message": "Draft saved"}
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}
