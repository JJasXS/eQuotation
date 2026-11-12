"""Create/Update SL_QT via SQLAcc.BizApp (Phase 2.3b). Metadata-verified mappings only.

Lifecycle (Create/Update) is implemented but not proven until ACC-ANOZ CUD lab.
Never call this path without AllowLiveCom + SQLACC_SDK_QUOTATION_CUD_ENABLED.
"""
from __future__ import annotations

import logging
from typing import Any

from api.clients import SqlAccountingApiError

logger = logging.getLogger(__name__)

_BIZ_QUOTATION = "SL_QT"
_MAIN = "MainDataSet"
_DETAIL = "cdsDocDetail"

# REST keys with no COM FieldName on ACC-ANOZ SL_QT (Phase 2.3a).
_UNSUPPORTED_HEADER = frozenset({"nextdocno"})
_UNSUPPORTED_DETAIL = frozenset({"udf_eprice"})

# REST lower-case → COM FieldName (verified MainDataSet / cdsDocDetail).
_HEADER_MAP = {
    "dockey": "DOCKEY",
    "docno": "DOCNO",
    "docnoex": "DOCNOEX",
    "docdate": "DOCDATE",
    "postdate": "POSTDATE",
    "taxdate": "TAXDATE",
    "code": "CODE",
    "companyname": "COMPANYNAME",
    "address1": "ADDRESS1",
    "address2": "ADDRESS2",
    "address3": "ADDRESS3",
    "address4": "ADDRESS4",
    "postcode": "POSTCODE",
    "city": "CITY",
    "state": "STATE",
    "country": "COUNTRY",
    "phone1": "PHONE1",
    "mobile": "MOBILE",
    "fax1": "FAX1",
    "attention": "ATTENTION",
    "area": "AREA",
    "agent": "AGENT",
    "project": "PROJECT",
    "terms": "TERMS",
    "currencycode": "CURRENCYCODE",
    "currencyrate": "CURRENCYRATE",
    "shipper": "SHIPPER",
    "description": "DESCRIPTION",
    "cancelled": "CANCELLED",
    "status": "STATUS",
    "docamt": "DOCAMT",
    "localdocamt": "LOCALDOCAMT",
    "validity": "VALIDITY",
    "deliveryterm": "DELIVERYTERM",
    "cc": "CC",
    "docref1": "DOCREF1",
    "docref2": "DOCREF2",
    "docref3": "DOCREF3",
    "docref4": "DOCREF4",
    "branchname": "BRANCHNAME",
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
    "salestaxno": "SALESTAXNO",
    "servicetaxno": "SERVICETAXNO",
    "tin": "TIN",
    "idtype": "IDTYPE",
    "idno": "IDNO",
    "tourismno": "TOURISMNO",
    "sic": "SIC",
    "incoterms": "INCOTERMS",
    "businessunit": "BUSINESSUNIT",
    "attachments": "ATTACHMENTS",
    "submissiontype": "SUBMISSIONTYPE",
    "note": "NOTE",
    "approvestate": "APPROVESTATE",
    "updatecount": "UPDATECOUNT",
    "transferable": "TRANSFERABLE",
    "printcount": "PRINTCOUNT",
    "lastmodified": "LASTMODIFIED",
    "changed": "CHANGED",
    "docnosetkey": "DocNoSetKey",
    "im_scan_autokey": "IM_Scan_AutoKey",
    "udf_status": "UDF_Status",
}

_DETAIL_MAP = {
    "dtlkey": "DTLKEY",
    "dockey": "DOCKEY",
    "seq": "SEQ",
    "styleid": "STYLEID",
    "number": "NUMBER",
    "itemcode": "ITEMCODE",
    "location": "LOCATION",
    "batch": "BATCH",
    "project": "PROJECT",
    "description": "DESCRIPTION",
    "description2": "DESCRIPTION2",
    "description3": "DESCRIPTION3",
    "permitno": "PERMITNO",
    "qty": "QTY",
    "uom": "UOM",
    "rate": "RATE",
    "sqty": "SQTY",
    "suomqty": "SUOMQTY",
    "unitprice": "UNITPRICE",
    "deliverydate": "DELIVERYDATE",
    "disc": "DISC",
    "tax": "TAX",
    "tariff": "TARIFF",
    "taxexemptionreason": "TAXEXEMPTIONREASON",
    "irbm_classification": "IRBM_Classification",
    "taxrate": "TAXRATE",
    "taxamt": "TAXAMT",
    "localtaxamt": "LOCALTAXAMT",
    "exempted_taxrate": "EXEMPTED_TAXRATE",
    "exempted_taxamt": "EXEMPTED_TAXAMT",
    "taxinclusive": "TAXINCLUSIVE",
    "amount": "AMOUNT",
    "localamount": "LOCALAMOUNT",
    "amountwithtax": "AmountWithTax",
    "printable": "PRINTABLE",
    "transferable": "TRANSFERABLE",
    "remark1": "REMARK1",
    "remark2": "REMARK2",
    "companyitemcode": "CompanyItemCode",
    "initialpurchasecost": "InitialPurchaseCost",
    "changed": "CHANGED",
    "udf_stdprice": "UDF_StdPrice",
    "udf_mtype": "UDF_MType",
    "udf_thickness": "UDF_Thickness",
    "udf_width": "UDF_Width",
    "udf_length": "UDF_Length",
    "udf_wts": "UDF_WTS",
    "udf_qtno": "UDF_QTNo",
    "udf_stockgroup": "UDF_StockGroup",
    "udf_2uom": "UDF_2UOM",
    "udf_formula": "UDF_Formula",
    "udf_pricekg": "UDF_PriceKG",
    "udf_dleadtime": "UDF_DLeadTime",
    "udf_moq": "UDF_MOQ",
    "udf_bundle": "UDF_Bundle",
    "udf_addlength": "UDF_AddLength",
    "udf_addwidth": "UDF_AddWidth",
    "udf_ds": "UDF_dS",
    "udf_dsys": "UDF_dSys",
    "udf_dfs": "UDF_dfS",
    "udf_dfsys": "UDF_dfSys",
    "udf_wtsys": "UDF_WTSys",
}

_SKIP_HEADER_WRITE = frozenset({"sdsdocdetail", "nextdocno"})
_SKIP_DETAIL_WRITE = frozenset({"udf_status", "udf_eprice", "sdsSerialNumber", "sdsserialnumber"})


def _null_if_empty(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "T" if value else "F"
    text = str(value).strip()
    return text if text else None


def _is_meaningful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    return bool(str(value).strip())


def _is_nonzero_money(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    try:
        return abs(float(text)) > 0
    except ValueError:
        return True


def collect_unresolved_mappings(payload: dict[str, Any]) -> list[str]:
    """Return human-readable unresolved REST→COM mapping issues (never silent)."""
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ["payload is not a dict"]

    for key in _UNSUPPORTED_HEADER:
        if key in payload and _is_meaningful(payload.get(key)):
            issues.append(
                f"Unsupported header field '{key}' has a value but no COM FieldName on SL_QT."
            )

    for idx, row in enumerate(payload.get("sdsdocdetail") or [], start=1):
        if not isinstance(row, dict):
            continue
        for key in _UNSUPPORTED_DETAIL:
            raw = row.get(key)
            if key == "udf_eprice":
                if _is_nonzero_money(raw) or (
                    _is_meaningful(raw) and str(raw).strip() not in ("0", "0.00", "0.0")
                ):
                    issues.append(
                        f"Line {idx}: unsupported detail field 'udf_eprice' "
                        f"(value={raw!r}) has no COM FieldName on SL_QT cdsDocDetail."
                    )
            elif key in row and _is_meaningful(raw):
                issues.append(
                    f"Line {idx}: unsupported detail field '{key}' has no COM FieldName."
                )
    return issues


def assert_quotation_mapping_supported(payload: dict[str, Any]) -> None:
    issues = collect_unresolved_mappings(payload)
    if issues:
        raise SqlAccountingApiError(
            "Unresolved SL_QT COM mapping: " + "; ".join(issues),
            status_code=422,
        )


def _set_field(dataset: Any, name: str, value: Any) -> None:
    field = dataset.Fields.FindField(name)
    if field is None:
        raise SqlAccountingApiError(
            f"SL_QT field '{name}' not found on COM dataset.",
            status_code=500,
        )
    if isinstance(value, bool):
        field.AsString = "T" if value else "F"
    elif value is None:
        field.AsString = ""
    else:
        field.AsString = str(value)


def _set_if(dataset: Any, name: str, value: Any) -> None:
    text = _null_if_empty(value) if not isinstance(value, bool) else ("T" if value else "F")
    if text is None and not isinstance(value, bool):
        return
    try:
        field = dataset.Fields.FindField(name)
        if field is None:
            return
        field.AsString = text if text is not None else ""
    except Exception:
        logger.debug("Optional COM field %s skipped", name, exc_info=True)


def _is_present_key(key: Any) -> bool:
    if key is None or isinstance(key, bool):
        return bool(key) if isinstance(key, bool) else False
    if isinstance(key, (int, float)):
        return key != 0
    text = str(key).strip()
    return bool(text) and text != "0"


def find_quotation_key_by_docno(biz: Any, doc_no: str) -> Any | None:
    doc_no = (doc_no or "").strip()
    if not doc_no:
        return None
    for field in ("DocNo", "DOCNO"):
        try:
            key = biz.FindKeyByRef(field, doc_no)
            if _is_present_key(key):
                return key
        except Exception:
            continue
    return None


def _query_first_row(app: Any, sql: str) -> dict[str, str] | None:
    ds = None
    try:
        ds = app.DBManager.NewDataSet(sql)
        if int(ds.RecordCount) <= 0:
            return None
        ds.First()
        fields = ds.Fields
        row: dict[str, str] = {}
        for i in range(int(fields.Count)):
            field = fields.Items(i)
            name = str(getattr(field, "FieldName", None) or f"F{i}")
            try:
                val = field.AsString
            except Exception:
                val = getattr(field, "value", "")
            row[name] = ("" if val is None else str(val)).strip()
        return row
    finally:
        ds = None


def _load_qt_persistence(app: Any, doc_no: str) -> dict[str, str] | None:
    safe = doc_no.replace("'", "''")
    return _query_first_row(
        app,
        "SELECT FIRST 1 DOCKEY, TRIM(DOCNO) AS DOCNO, TRIM(CODE) AS CODE, UPDATECOUNT "
        f"FROM SL_QT WHERE TRIM(DOCNO) = '{safe}'",
    )


def _apply_header(main: Any, payload: dict[str, Any]) -> None:
    for rest_key, com_name in _HEADER_MAP.items():
        if rest_key in _SKIP_HEADER_WRITE or rest_key not in payload:
            continue
        value = payload.get(rest_key)
        if rest_key == "cancelled" and isinstance(value, bool):
            _set_field(main, com_name, value)
            continue
        if value is None:
            continue
        # Never write DOCKEY=0 on a New() master — COM detail.Post then fails with
        # "No corresponding master record found."
        if rest_key == "dockey" and not _is_present_key(value):
            continue
        if rest_key in (
            "dockey",
            "updatecount",
            "printcount",
            "lastmodified",
            "docnosetkey",
            "im_scan_autokey",
            "status",
            "idtype",
            "submissiontype",
        ):
            _set_if(main, com_name, value)
            continue
        _set_if(main, com_name, value)


def _clear_detail_rows(detail: Any) -> None:
    """Best-effort clear of cdsDocDetail before rewrite (update path; unproven on live QT)."""
    try:
        while int(detail.RecordCount) > 0:
            detail.Last()
            detail.Delete()
    except Exception:
        logger.debug("cdsDocDetail clear loop failed", exc_info=True)


def _append_detail_rows(detail: Any, rows: list[Any]) -> None:
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        detail.Append()
        dtlkey = row.get("dtlkey")
        if not _is_present_key(dtlkey):
            dtlkey = -idx
        _set_field(detail, "DTLKEY", dtlkey)
        dockey = row.get("dockey")
        if _is_present_key(dockey):
            _set_if(detail, "DOCKEY", dockey)
        else:
            _set_if(detail, "DOCKEY", -1)
        for rest_key, com_name in _DETAIL_MAP.items():
            if rest_key in _SKIP_DETAIL_WRITE or rest_key in ("dtlkey", "dockey"):
                continue
            if rest_key not in row:
                continue
            value = row.get(rest_key)
            if value is None:
                continue
            if rest_key in ("taxinclusive", "printable", "transferable", "changed") and isinstance(
                value, bool
            ):
                _set_field(detail, com_name, value)
            else:
                _set_if(detail, com_name, value)
        detail.Post()


def _read_main_field(main: Any, name: str) -> str:
    try:
        field = main.Fields.FindField(name)
        if field is None:
            return ""
        try:
            return str(field.AsString or "").strip()
        except Exception:
            return str(getattr(field, "value", "") or "").strip()
    except Exception:
        return ""


def _save_close(biz: Any, action: str) -> None:
    try:
        biz.Save()
    except Exception as exc:
        try:
            biz.Close()
        except Exception:
            pass
        raise SqlAccountingApiError(
            f"SL_QT {action} Save failed: {exc}",
            status_code=502,
        ) from exc
    try:
        biz.Close()
    except Exception:
        logger.debug("SL_QT Close after Save failed", exc_info=True)


def _save_and_read_docno(biz: Any, main: Any, action: str) -> str:
    """Save then read allocated DOCNO before Close (native <<New>> → company number)."""
    try:
        biz.Save()
    except Exception as exc:
        try:
            if hasattr(biz, "Cancel"):
                biz.Cancel()
            else:
                biz.Close()
        except Exception:
            pass
        raise SqlAccountingApiError(
            f"SL_QT {action} Save failed: {exc}",
            status_code=502,
        ) from exc
    allocated = _read_main_field(main, "DOCNO")
    try:
        biz.Close()
    except Exception:
        logger.debug("SL_QT Close after Save failed", exc_info=True)
    return allocated


def create_quotation_via_com(app: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create-only SL_QT write using company SY_DOCNO auto-number (DOCNO left as <<New>>)."""
    assert_quotation_mapping_supported(payload)
    lines = payload.get("sdsdocdetail") or []
    if not lines:
        raise SqlAccountingApiError("sdsdocdetail is required for SDK quotation create.", status_code=400)

    # Optional explicit DOCNO only for rollback/lab; normal create leaves COM <<New>>.
    explicit_docno = str(payload.get("docno") or "").strip()
    if explicit_docno.upper() in ("<<NEW>>", "NEW", "AUTO", "ON SAVE", "ON_SAVE"):
        explicit_docno = ""

    biz = app.BizObjects.Find(_BIZ_QUOTATION)
    if explicit_docno and find_quotation_key_by_docno(biz, explicit_docno) is not None:
        raise SqlAccountingApiError(
            f"Quotation DOCNO '{explicit_docno}' already exists in SL_QT (duplicate DocNo).",
            status_code=422,
        )

    main = biz.DataSets.Find(_MAIN)
    detail = biz.DataSets.Find(_DETAIL)
    biz.New()
    # CHM sales-doc pattern: DocKey=-1 on New before detail Append/Post.
    _set_field(main, "DOCKEY", -1)
    # Keep New() DOCNO=<<New>> and company DocNoSetKey — never force DocNoSetKey=0.
    header_payload = {
        key: value
        for key, value in payload.items()
        if key not in ("docno", "docnosetkey", "nextdocno")
    }
    _apply_header(main, header_payload)
    if explicit_docno:
        _set_field(main, "DOCNO", explicit_docno)
    _set_field(main, "DOCKEY", -1)
    _append_detail_rows(detail, list(lines))
    allocated = _save_and_read_docno(biz, main, "create")
    if not allocated or allocated.upper() == "<<NEW>>":
        raise SqlAccountingApiError(
            "Save reported success but SQL Accounting did not allocate a DOCNO.",
            status_code=502,
        )

    persisted = _load_qt_persistence(app, allocated)
    if not persisted or not (persisted.get("DOCNO") or "").strip():
        raise SqlAccountingApiError(
            f"Save reported success but DOCNO '{allocated}' was not found after Close.",
            status_code=502,
        )
    return {
        "dockey": int(float(persisted.get("DOCKEY") or 0)),
        "docno": persisted.get("DOCNO") or allocated,
        "code": persisted.get("CODE") or payload.get("code"),
        "message": "Quotation created successfully",
        "provider": "Sdk",
        "docnoSource": "sql_accounting_sy_docno" if not explicit_docno else "explicit",
        "lifecycle": "create-native-docno",
    }


def update_quotation_via_com(
    app: Any,
    payload: dict[str, Any],
    *,
    dockey: int,
) -> dict[str, Any]:
    """
    Update SL_QT via FindKeyByRef → Params DocKey → Open → Edit → Save.

    Pattern inferred from CHM SL_IV / sqlSign docs — not proven for SL_QT until CUD lab.
    """
    assert_quotation_mapping_supported(payload)
    doc_no = str(payload.get("docno") or "").strip()
    if not doc_no:
        raise SqlAccountingApiError("DOCNO is required for SDK quotation update.", status_code=400)
    if dockey <= 0:
        raise SqlAccountingApiError("DOCKEY is required for SDK quotation update.", status_code=400)
    lines = payload.get("sdsdocdetail") or []
    if not lines:
        raise SqlAccountingApiError("sdsdocdetail is required for SDK quotation update.", status_code=400)

    biz = app.BizObjects.Find(_BIZ_QUOTATION)
    key = find_quotation_key_by_docno(biz, doc_no)
    if key is None:
        raise SqlAccountingApiError(
            f"Quotation DOCNO '{doc_no}' not found for SDK update.",
            status_code=404,
        )

    main = biz.DataSets.Find(_MAIN)
    detail = biz.DataSets.Find(_DETAIL)
    try:
        biz.Params.Find("DocKey").Value = key
    except Exception:
        try:
            biz.Params.Find("DOCKEY").Value = key
        except Exception as exc:
            raise SqlAccountingApiError(
                f"SL_QT Params DocKey unavailable for update: {exc}",
                status_code=500,
            ) from exc

    biz.Open()
    biz.Edit()
    _apply_header(main, payload)
    _set_field(main, "DOCNO", doc_no)
    _set_if(main, "DOCKEY", dockey)
    _clear_detail_rows(detail)
    _append_detail_rows(detail, list(lines))
    _save_close(biz, "update")

    persisted = _load_qt_persistence(app, doc_no)
    if not persisted:
        raise SqlAccountingApiError(
            f"Update Save reported success but DOCNO '{doc_no}' was not found after Close.",
            status_code=502,
        )
    return {
        "dockey": int(float(persisted.get("DOCKEY") or dockey)),
        "docno": persisted.get("DOCNO") or doc_no,
        "code": persisted.get("CODE") or payload.get("code"),
        "message": "Quotation updated successfully",
        "provider": "Sdk",
        "lifecycle": "update-unproven-until-cud-lab",
        "updatecount": persisted.get("UPDATECOUNT"),
    }
