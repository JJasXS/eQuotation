"""udf_mtype must flow from stock catalog into salesquotation line payload."""
from utils.stock_items_catalog import enrich_quotation_submit_line_item, merge_item_and_stock_udf_fields_for_api


def test_build_salesquotation_payload_includes_udf_mtype_after_itemcode(monkeypatch):
    """Enrich runs after item code resolution so catalog UDF_MTYPE reaches sdsdocdetail."""
    from utils import quotation_api as qa

    monkeypatch.setattr(qa, "_resolve_item_code_from_local_db", lambda _desc: "1050-H0 320MMx0.7MM")
    monkeypatch.setattr(qa, "_quotation_fallback_item_code", lambda: "")
    monkeypatch.setattr(qa, "_lookup_st_item_uom_irbm", lambda _code, _memo: ("", ""))
    monkeypatch.setattr(qa, "_resolve_tenant_default_uom", lambda: "UNIT")
    monkeypatch.setattr(qa, "_resolve_quotation_currency_code", lambda _data, _cust: "MYR")

    def _fake_catalog(*, code="", description="", cached_items=None):
        return {
            "CODE": code or "1050-H0 320MMx0.7MM",
            "DESCRIPTION": description or "AL sheet",
            "UDF_MTYPE": "AL",
        }

    monkeypatch.setattr(
        "utils.stock_items_catalog.find_catalog_stock_item_prefer_sql_api",
        _fake_catalog,
    )

    payload = qa._build_salesquotation_payload(
        "TEST-CUST",
        {
            "items": [
                {
                    "product": "AL sheet 1050",
                    "qty": 2,
                    "price": 10,
                }
            ]
        },
        doc_no="EQ-TEST-MTYPE",
    )
    rows = payload.get("sdsdocdetail") or []
    assert len(rows) == 1
    assert rows[0].get("udf_mtype") == "AL"
    assert rows[0].get("itemcode") == "1050-H0 320MMx0.7MM"


def test_enrich_line_item_sets_udf_mtype_from_stock_detail():
    item = {
        "product": "AL sheet",
        "qty": 1,
        "price": 10,
        "itemCode": "1050-H0 320MMx0.7MM",
        "stockDetail": {"code": "1050-H0 320MMx0.7MM", "udf_mtype": "AL"},
    }
    out = enrich_quotation_submit_line_item(item)
    assert out.get("udf_mtype") == "AL"
    assert out.get("udfMtype") == "AL"


def test_enrich_fetches_mtype_from_sql_api_detail(monkeypatch):
    def _fake_catalog(*, code="", description="", cached_items=None):
        return {"CODE": code or "1060-H24", "DESCRIPTION": description or "AL 1060-H24"}

    def _fake_detail(c):
        if str(c).strip().upper() == "1060-H24":
            return {"CODE": "1060-H24", "UDF_MTYPE": "AL"}
        return None

    monkeypatch.setattr(
        "utils.stock_items_catalog.find_catalog_stock_item_prefer_sql_api",
        _fake_catalog,
    )
    monkeypatch.setattr(
        "utils.stock_items_catalog.fetch_stock_item_sql_api_by_code",
        _fake_detail,
    )
    monkeypatch.setattr(
        "utils.stock_items_catalog._firebird_stock_row_for_code",
        lambda _c: {},
    )
    out = enrich_quotation_submit_line_item(
        {"product": "AL 1060-H24 CQ/P", "itemCode": "1060-H24", "qty": 1}
    )
    assert out.get("udf_mtype") == "AL"


def test_enrich_fills_mtype_from_catalog_by_description(monkeypatch):
    def _fake_catalog(*, code="", description="", cached_items=None):
        if "AL sheet" in (description or ""):
            return {"CODE": "1050-H0", "UDF_MTYPE": "AL"}
        return None

    monkeypatch.setattr(
        "utils.stock_items_catalog.find_catalog_stock_item_prefer_sql_api",
        _fake_catalog,
    )
    monkeypatch.setattr(
        "utils.stock_items_catalog._firebird_stock_row_for_code",
        lambda _c: {},
    )
    out = enrich_quotation_submit_line_item(
        {"product": "AL sheet 1050", "itemCode": "1050-H0", "qty": 1}
    )
    assert out.get("udf_mtype") == "AL"


def test_merge_prefers_stock_mtype():
    merged = merge_item_and_stock_udf_fields_for_api(
        {"itemCode": "X"},
        {"UDF_MTYPE": "AL"},
    )
    assert merged.get("udf_mtype") == "AL"
