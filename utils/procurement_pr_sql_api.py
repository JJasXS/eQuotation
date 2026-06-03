"""Build SQL Accounting ``/purchaserequest`` payloads from validated e-PR rows."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from utils.customer_display import _format_currency_display_value
from utils.sql_api_supplier import sql_api_currency_and_code, supplier_master_document_fields


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

_PR_LINE_UDF_KEYS = (
    "udf_stdprice",
    "udf_dleadtime",
    "udf_moq",
    "udf_bundle",
    "udf_thickness",
    "udf_width",
    "udf_length",
    "udf_dp",
    "udf_dfp",
    "udf_wtp",
    "udf_2uom",
    "udf_formula",
    "udf_costkg",
    "udf_mtype",
    "udf_pqno",
)


def strip_client_pr_currency_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove browser-supplied currency so server resolves from SQL API GET /supplier."""
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    for key in (
        "currency",
        "currencyCode",
        "currencycode",
        "CURRENCYCODE",
        "sqlApiCurrencyCode",
    ):
        out.pop(key, None)
    return out


_PH_PQ_COL_BY_FLAT_KEY: dict[str, str] = {
    "code": "CODE",
    "companyname": "COMPANYNAME",
    "companyname2": "COMPANYNAME2",
    "controlaccount": "CONTROLACCOUNT",
    "companycategory": "COMPANYCATEGORY",
    "area": "AREA",
    "agent": "AGENT",
    "currencycode": "CURRENCYCODE",
    "currencyrate": "CURRENCYRATE",
    "creditterm": "CREDITTERM",
    "terms": "TERMS",
    "creditlimit": "CREDITLIMIT",
    "businessunit": "BUSINESSUNIT",
    "branchname": "BRANCHNAME",
    "address1": "ADDRESS1",
    "address2": "ADDRESS2",
    "address3": "ADDRESS3",
    "address4": "ADDRESS4",
    "postcode": "POSTCODE",
    "city": "CITY",
    "state": "STATE",
    "country": "COUNTRY",
    "phone1": "PHONE1",
    "phone2": "PHONE2",
    "mobile": "MOBILE",
    "fax1": "FAX1",
    "fax2": "FAX2",
    "attention": "ATTENTION",
    "daddress1": "DADDRESS1",
    "daddress2": "DADDRESS2",
    "daddress3": "DADDRESS3",
    "daddress4": "DADDRESS4",
    "dpostcode": "DPOSTCODE",
    "dcity": "DCITY",
    "dstate": "DSTATE",
    "dcountry": "DCOUNTRY",
    "dattention": "DATTENTION",
    "dphone1": "DPHONE1",
    "dmobile": "DMOBILE",
    "dfax1": "DFAX1",
    "taxexemptno": "TAXEXEMPTNO",
    "brn": "BRN",
    "brn2": "BRN2",
    "gstno": "GSTNO",
    "salestaxno": "SALESTAXNO",
    "servicetaxno": "SERVICETAXNO",
    "tin": "TIN",
    "idno": "IDNO",
    "idtype": "IDTYPE",
    "tourismno": "TOURISMNO",
    "sic": "SIC",
    "submissiontype": "SUBMISSIONTYPE",
}


def ph_pq_header_updates_from_sql_supplier(row: dict[str, Any]) -> dict[str, Any]:
    """Map SQL API GET /supplier row (+ billing branch) onto PH_PQ column names."""
    flat = supplier_master_document_fields(row)
    updates: dict[str, Any] = {"SHIPPER": "----"}
    for flat_key, col in _PH_PQ_COL_BY_FLAT_KEY.items():
        if flat_key not in flat:
            continue
        updates[col] = flat[flat_key]
    code = _clean_text(updates.get("CODE"))
    if code:
        updates["SUPPLIERID"] = code
    cc = _clean_text(updates.get("CURRENCYCODE"))
    if cc:
        updates["CURRENCY"] = cc
    if "CURRENCYRATE" not in updates:
        updates["CURRENCYRATE"] = 1

    return {k: v for k, v in updates.items() if v is not None and _clean_text(v) != ""}


def resolve_pr_currency_code(supplier_code: str, *, required: bool = True) -> str:
    """Currency for purchase request header — only SQL API GET ``/supplier?code=…``."""
    code = str(supplier_code or "").strip()
    if not code:
        if required:
            raise ValueError("Supplier code is required to load currency from SQL API.")
        return ""

    fields = sql_api_currency_and_code(code)
    cc = str(fields.get("currencycode") or "").strip()
    http_status = str(fields.get("httpStatus") or "").strip()
    if not cc or cc in ("-", "—"):
        hint = f" (SQL API HTTP {http_status})" if http_status else ""
        raise ValueError(
            f"Currency not returned from SQL API GET /supplier for supplier {code!r}{hint}. "
            "Configure SQL API keys for this tenant and reload Create e-Purchase Request."
        )
    return cc


def _fmt_money_str(value: Any) -> str:
    return str(_money(_as_decimal(value, "0")))


def _pick_stock_detail(item: dict[str, Any]) -> dict[str, Any]:
    for key in ("stockDetail", "stockApi", "stockCatalog", "catalogRow"):
        raw = item.get(key)
        if isinstance(raw, dict):
            return raw
    return {}


def _detail_scalar(stock: dict[str, Any], item: dict[str, Any], *names: str) -> Any:
    lower_stock = {str(k).lower(): v for k, v in stock.items()}
    lower_item = {str(k).lower(): v for k, v in item.items()}
    for name in names:
        for src in (stock, item, lower_stock, lower_item):
            if name in src and src[name] is not None:
                return src[name]
            low = name.lower()
            if low in src and src[low] is not None:
                return src[low]
    return None


def _resolve_line_uom(item: dict[str, Any], stock: dict[str, Any]) -> str:
    """Trade UOM for PR lines: UDF_2UOM / SUOM (SQL API) then header UOM / SDSUOM base."""
    for key in ("udf_2uom", "UDF_2UOM"):
        uom = _clean_text(_detail_scalar(stock, item, key, key))
        if uom:
            return uom
    for key in ("suom", "SUOM"):
        uom = _clean_text(_detail_scalar(stock, item, key, key))
        if uom:
            return uom
    uom = _clean_text(_detail_scalar(stock, item, "uom", "UOM"))
    if uom:
        return uom
    sdsuom = stock.get("sdsuom") or stock.get("SDSUOM")
    if isinstance(sdsuom, list):
        for row in sdsuom:
            if not isinstance(row, dict):
                continue
            if row.get("isbase") is True or str(row.get("isbase", "")).lower() == "true":
                return _clean_text(row.get("uom"))
        if sdsuom and isinstance(sdsuom[0], dict):
            return _clean_text(sdsuom[0].get("uom"))
    return ""


def _line_udf_fields(stock: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    merged_sources = [stock, item]
    for src in merged_sources:
        if not isinstance(src, dict):
            continue
        for key, val in src.items():
            key_s = str(key)
            if key_s.lower().startswith("udf_") and val is not None:
                out[key_s.lower()] = val
    for key in _PR_LINE_UDF_KEYS:
        if key in out:
            continue
        val = _detail_scalar(stock, item, key, key.upper())
        if val is not None:
            out[key] = val
    return out


def build_sdsdocdetail_line(
    item: dict[str, Any],
    *,
    seq: int,
    header_project: str,
    default_delivery: date | None,
) -> dict[str, Any]:
    stock = _pick_stock_detail(item)
    item_code = _clean_text(item.get("itemCode") or item.get("itemcode") or stock.get("code") or stock.get("CODE"))
    location = _clean_text(item.get("locationCode") or item.get("location") or stock.get("location")) or "----"
    line_project = _clean_text(item.get("project")) or header_project or "----"
    description = (
        _clean_text(item.get("description") or item.get("itemName"))
        or _clean_text(stock.get("description") or stock.get("DESCRIPTION"))
        or item_code
    )

    from utils.procurement_purchase_request import parse_line_qty_sq_su

    qty_sq, qty_su, pricing_qty, _basis = parse_line_qty_sq_su(item)
    pricing_qty_dec = _as_decimal(str(pricing_qty), "0")
    unit_price = _as_decimal(item.get("unitPrice") if item.get("unitPrice") is not None else item.get("unitprice"), "0")
    tax = _as_decimal(item.get("tax") if item.get("tax") is not None else item.get("taxamt"), "0")
    line_uom = _resolve_line_uom(item, stock)
    amount = _money(_as_decimal(item.get("amount"), str(pricing_qty_dec * unit_price + tax)))

    delivery_raw = _clean_text(item.get("deliveryDate") or item.get("deliverydate"))
    delivery_date = delivery_raw or (default_delivery.isoformat() if default_delivery else "")

    row: dict[str, Any] = {
        "seq": seq,
        "itemcode": item_code,
        "location": location,
        "batch": None,
        "project": line_project,
        "description": description,
        "description2": _clean_text(_detail_scalar(stock, item, "description2", "DESCRIPTION2")) or None,
        "description3": None,
        "qty": _fmt_money_str(pricing_qty),
        "uom": line_uom,
        "rate": None,
        "sqty": _fmt_money_str(qty_sq),
        "suomqty": _fmt_money_str(qty_su),
        "unitprice": _fmt_money_str(unit_price),
        "deliverydate": delivery_date,
        "disc": "0",
        "tax": _fmt_money_str(tax),
        "amount": _fmt_money_str(amount),
        "changed": False,
    }
    row.update(_line_udf_fields(stock, item))
    return row


def build_purchaserequest_upstream_payload(validated: dict[str, Any], *, request_number: str) -> dict[str, Any]:
    """Full SQL Accounting purchase request body for upstream POST."""
    supplier_code = _clean_text(validated.get("supplierId"))
    supplier_name = _clean_text(validated.get("supplierName"))
    header_project = _clean_text(validated.get("project")) or "----"
    request_date = _clean_text(validated.get("requestDate"))
    if not request_date:
        request_date = date.today().isoformat()

    # Create/submit: SQL PR is header-only (lines + dates); vendor/currency set after bidding award.
    if not supplier_code:
        supplier_code = "----"
        supplier_name = ""
    currency_code = _clean_text(validated.get("currency"))
    if not currency_code and supplier_code and supplier_code != "----":
        currency_code = resolve_pr_currency_code(supplier_code, required=True)
    if not currency_code:
        currency_code = "----"
    status_text = _clean_text(validated.get("status")).upper()
    status_num = 1 if status_text == "SUBMITTED" else 0

    req_date_obj = date.fromisoformat(request_date[:10])
    details: list[dict[str, Any]] = []
    for idx, item in enumerate(validated.get("lineItems") or [], start=1):
        if not isinstance(item, dict):
            continue
        details.append(
            build_sdsdocdetail_line(
                item,
                seq=idx,
                header_project=header_project,
                default_delivery=req_date_obj,
            )
        )

    total = _fmt_money_str(validated.get("totalAmount"))

    return {
        "docno": request_number,
        "docnoex": request_number,
        "docdate": request_date,
        "postdate": request_date,
        "taxdate": request_date,
        "code": supplier_code,
        "companyname": supplier_name,
        "project": header_project,
        "currencycode": currency_code,
        "currencyrate": "1",
        "shipper": "----",
        "description": _clean_text(validated.get("description")),
        "status": status_num,
        "docamt": total,
        "note": _clean_text(validated.get("notes")),
        "daddress1": None,
        "sdsdocdetail": details,
        "changed": False,
        "udf_status": "PENDING" if status_text == "SUBMITTED" else "",
    }
