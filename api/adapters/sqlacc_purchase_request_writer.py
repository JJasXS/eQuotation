"""Create/Update PH_PQ via SQLAcc.BizApp (Phase 2.4b). Metadata-verified mappings only.

Lifecycle (Create/Update) is implemented but not proven until ACC-ANOZ CUD lab.
Never call this path without AllowLiveCom + SQLACC_SDK_PR_CUD_ENABLED.

Award supplier UDFs (UDF_SUPCODE / UDF_SUPNAME) exist in Firebird PH_PQDTL but are
not exposed on COM cdsDocDetail Fields/XMLFieldDefs (Phase 2.4a). There is no
documented BizObject FindField / FieldByName / XMLFieldDefs mechanism to write
unregistered columns. Sdk awards sync must fail closed before New/Edit/Save.
"""
from __future__ import annotations

import logging
from typing import Any

from api.clients import SqlAccountingApiError

logger = logging.getLogger(__name__)

_BIZ_PURCHASE_REQUEST = "PH_PQ"
_MAIN = "MainDataSet"
_DETAIL = "cdsDocDetail"

# Phase 2.4a: present in Firebird, absent from COM Fields / XMLFieldDefs.
_AWARD_SUPPLIER_UDF_KEYS = frozenset({"udf_supcode", "udf_supname"})

# Flip only after live COM Fields.FindField verifies both names on cdsDocDetail.
COM_EXPOSES_AWARD_SUPPLIER_UDFS = False

_UNSUPPORTED_HEADER = frozenset(
    {
        "companyname2",
        "controlaccount",
        "companycategory",
        "creditterm",
        "phone2",
        "fax2",
        "brn",
        "brn2",
        "gstno",
    }
)
_UNSUPPORTED_DETAIL = frozenset(
    {
        "udf_stdprice",
        "udf_pqapproved",
        *_AWARD_SUPPLIER_UDF_KEYS,
    }
)

# REST lower-case → COM FieldName (verified MainDataSet / cdsDocDetail on ACC-ANOZ).
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
    "udf_pqcreatedby": "UDF_PQCreatedBy",
    "udf_pqcreatedon": "UDF_PQCreatedOn",
    "udf_pqno": "UDF_PQNo",
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
    "irbm_classification": "IRBM_CLASSIFICATION",
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
    "changed": "CHANGED",
    "udf_pqno": "UDF_PQNo",
    "udf_stockgroup": "UDF_StockGroup",
    "udf_inspection": "UDF_Inspection",
    "udf_location": "UDF_Location",
    "udf_2uom": "UDF_2UOM",
    "udf_formula": "UDF_Formula",
    "udf_mtype": "UDF_MType",
    "udf_costkg": "UDF_CostKG",
    "udf_dleadtime": "UDF_DLeadTime",
    "udf_moq": "UDF_MOQ",
    "udf_bundle": "UDF_Bundle",
    "udf_thickness": "UDF_Thickness",
    "udf_width": "UDF_Width",
    "udf_length": "UDF_Length",
    "udf_dp": "UDF_dP",
    "udf_dfp": "UDF_dfP",
    "udf_wtp": "UDF_WTP",
}

_SKIP_HEADER_WRITE = frozenset({"sdsdocdetail"})
_SKIP_DETAIL_WRITE = frozenset(_AWARD_SUPPLIER_UDF_KEYS | {"udf_stdprice", "udf_pqapproved"})


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


def _line_has_award_supplier_udf(row: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    lower = {str(k).lower(): v for k, v in row.items()}
    for key in _AWARD_SUPPLIER_UDF_KEYS:
        if key in lower and _is_meaningful(lower.get(key)):
            hits.append(key)
    return hits


def payload_award_supplier_udf_issues(payload: dict[str, Any]) -> list[str]:
    """Issues when award supplier UDFs must be preserved but COM cannot write them."""
    if not isinstance(payload, dict):
        return ["payload is not a dict"]
    if COM_EXPOSES_AWARD_SUPPLIER_UDFS:
        return []
    issues: list[str] = []
    for idx, row in enumerate(payload.get("sdsdocdetail") or [], start=1):
        if not isinstance(row, dict):
            continue
        hits = _line_has_award_supplier_udf(row)
        if not hits:
            continue
        issues.append(
            f"Line {idx}: award field(s) {', '.join(hits)} cannot be written via PH_PQ COM "
            "(not in cdsDocDetail Fields/XMLFieldDefs). Refusing Sdk sync to avoid discarding awards. "
            "Rollback: SQL_ACCOUNTING_PR_WRITE_PROVIDER=Rest."
        )
    return issues


def assert_award_supplier_udfs_preservable(payload: dict[str, Any]) -> None:
    """Fail closed before any COM mutator when award supplier UDFs cannot be preserved."""
    issues = payload_award_supplier_udf_issues(payload)
    if issues:
        raise SqlAccountingApiError(
            "PH_PQ Sdk award sync blocked: " + "; ".join(issues),
            status_code=422,
        )


def collect_unresolved_mappings(payload: dict[str, Any]) -> list[str]:
    """Return unresolved REST→COM mapping issues (never silent)."""
    issues: list[str] = []
    if not isinstance(payload, dict):
        return ["payload is not a dict"]

    for key in _UNSUPPORTED_HEADER:
        if key in payload and _is_meaningful(payload.get(key)):
            # Blanked award-sync header noise is OK; only flag meaningful extras.
            if key == "companyname2" and not str(payload.get(key) or "").strip():
                continue
            issues.append(
                f"Unsupported header field '{key}' has a value but no COM FieldName on PH_PQ."
            )

    for idx, row in enumerate(payload.get("sdsdocdetail") or [], start=1):
        if not isinstance(row, dict):
            continue
        lower_keys = {str(k).lower() for k in row}
        for key in _UNSUPPORTED_DETAIL:
            if key not in lower_keys and key not in row:
                continue
            raw = row.get(key)
            if raw is None:
                raw = next((row[k] for k in row if str(k).lower() == key), None)
            if key in _AWARD_SUPPLIER_UDF_KEYS:
                # Handled by assert_award_supplier_udfs_preservable (stronger gate).
                continue
            if _is_meaningful(raw):
                issues.append(
                    f"Line {idx}: unsupported detail field '{key}' has no COM FieldName on PH_PQ."
                )
    return issues


def assert_purchase_request_mapping_supported(payload: dict[str, Any]) -> None:
    assert_award_supplier_udfs_preservable(payload)
    issues = collect_unresolved_mappings(payload)
    if issues:
        raise SqlAccountingApiError(
            "Unresolved PH_PQ COM mapping: " + "; ".join(issues),
            status_code=422,
        )


def _set_field(dataset: Any, name: str, value: Any) -> None:
    field = dataset.Fields.FindField(name)
    if field is None:
        raise SqlAccountingApiError(
            f"PH_PQ field '{name}' not found on COM dataset.",
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


def find_purchase_request_key_by_docno(biz: Any, doc_no: str) -> Any | None:
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


def _load_pq_persistence(app: Any, doc_no: str) -> dict[str, str] | None:
    safe = doc_no.replace("'", "''")
    return _query_first_row(
        app,
        "SELECT FIRST 1 DOCKEY, TRIM(DOCNO) AS DOCNO, TRIM(CODE) AS CODE, UPDATECOUNT "
        f"FROM PH_PQ WHERE TRIM(DOCNO) = '{safe}'",
    )


def probe_com_award_supplier_fields(detail_dataset: Any) -> dict[str, bool]:
    """Read-only FindField probe (no Open/New). Used by labs; default gate uses constant."""
    out: dict[str, bool] = {}
    for name in ("UDF_SUPCODE", "UDF_SUPNAME", "UDF_SupCode", "UDF_SupName"):
        try:
            out[name] = detail_dataset.Fields.FindField(name) is not None
        except Exception:
            out[name] = False
    return out


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
        if rest_key == "dockey" and not _is_present_key(value):
            continue
        _set_if(main, com_name, value)


def _clear_detail_rows(detail: Any) -> None:
    try:
        while int(detail.RecordCount) > 0:
            detail.Last()
            detail.Delete()
    except Exception:
        logger.debug("PH_PQ cdsDocDetail clear loop failed", exc_info=True)


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
        lower_row = {str(k).lower(): v for k, v in row.items()}
        for rest_key, com_name in _DETAIL_MAP.items():
            if rest_key in _SKIP_DETAIL_WRITE or rest_key in ("dtlkey", "dockey"):
                continue
            if rest_key not in lower_row and rest_key not in row:
                continue
            value = lower_row.get(rest_key, row.get(rest_key))
            if value is None:
                continue
            if rest_key in ("taxinclusive", "printable", "transferable", "changed") and isinstance(
                value, bool
            ):
                _set_field(detail, com_name, value)
            else:
                _set_if(detail, com_name, value)
        detail.Post()


def _save_close(biz: Any, action: str) -> None:
    try:
        biz.Save()
    except Exception as exc:
        try:
            biz.Close()
        except Exception:
            pass
        raise SqlAccountingApiError(
            f"PH_PQ {action} Save failed: {exc}",
            status_code=502,
        ) from exc
    try:
        biz.Close()
    except Exception:
        logger.debug("PH_PQ Close after Save failed", exc_info=True)


def create_purchase_request_via_com(app: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create-only PH_PQ write. Fails on duplicate DocNo. Lifecycle unproven until CUD lab."""
    assert_purchase_request_mapping_supported(payload)
    doc_no = str(payload.get("docno") or "").strip()
    if not doc_no:
        raise SqlAccountingApiError("DOCNO is required for SDK purchase request create.", status_code=400)
    lines = payload.get("sdsdocdetail") or []
    if not lines:
        raise SqlAccountingApiError(
            "sdsdocdetail is required for SDK purchase request create.",
            status_code=400,
        )

    biz = app.BizObjects.Find(_BIZ_PURCHASE_REQUEST)
    if find_purchase_request_key_by_docno(biz, doc_no) is not None:
        raise SqlAccountingApiError(
            f"Purchase request DOCNO '{doc_no}' already exists in PH_PQ (duplicate DocNo).",
            status_code=422,
        )

    main = biz.DataSets.Find(_MAIN)
    detail = biz.DataSets.Find(_DETAIL)
    biz.New()
    _set_field(main, "DOCKEY", -1)
    _apply_header(main, payload)
    _set_field(main, "DOCNO", doc_no)
    _set_field(main, "DOCKEY", -1)
    _append_detail_rows(detail, list(lines))
    _save_close(biz, "create")

    persisted = _load_pq_persistence(app, doc_no)
    if not persisted or not (persisted.get("DOCNO") or "").strip():
        raise SqlAccountingApiError(
            f"Save reported success but DOCNO '{doc_no}' was not found after Close.",
            status_code=502,
        )
    return {
        "dockey": int(float(persisted.get("DOCKEY") or 0)),
        "docno": persisted.get("DOCNO") or doc_no,
        "code": persisted.get("CODE") or payload.get("code"),
        "message": "Purchase request created successfully",
        "provider": "Sdk",
        "lifecycle": "create-unproven-until-cud-lab",
    }


def update_purchase_request_via_com(
    app: Any,
    payload: dict[str, Any],
    *,
    dockey: int,
) -> dict[str, Any]:
    """Update PH_PQ via FindKeyByRef → Params DocKey → Open → Edit → Save."""
    assert_purchase_request_mapping_supported(payload)
    doc_no = str(payload.get("docno") or "").strip()
    if not doc_no:
        raise SqlAccountingApiError("DOCNO is required for SDK purchase request update.", status_code=400)
    if dockey <= 0:
        raise SqlAccountingApiError("DOCKEY is required for SDK purchase request update.", status_code=400)
    lines = payload.get("sdsdocdetail") or []
    if not lines:
        raise SqlAccountingApiError(
            "sdsdocdetail is required for SDK purchase request update.",
            status_code=400,
        )

    biz = app.BizObjects.Find(_BIZ_PURCHASE_REQUEST)
    key = find_purchase_request_key_by_docno(biz, doc_no)
    if key is None:
        raise SqlAccountingApiError(
            f"Purchase request DOCNO '{doc_no}' not found for SDK update.",
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
                f"PH_PQ Params DocKey unavailable for update: {exc}",
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

    persisted = _load_pq_persistence(app, doc_no)
    if not persisted:
        raise SqlAccountingApiError(
            f"Update Save reported success but DOCNO '{doc_no}' was not found after Close.",
            status_code=502,
        )
    return {
        "dockey": int(float(persisted.get("DOCKEY") or dockey)),
        "docno": persisted.get("DOCNO") or doc_no,
        "code": persisted.get("CODE") or payload.get("code"),
        "message": "Purchase request updated successfully",
        "provider": "Sdk",
        "lifecycle": "update-unproven-until-cud-lab",
        "updatecount": persisted.get("UPDATECOUNT"),
    }
