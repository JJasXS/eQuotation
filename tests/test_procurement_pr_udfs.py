"""Stock catalog UDFs must reach SQL Accounting purchase-request line payloads."""
from utils.procurement_pr_sql_api import build_sdsdocdetail_line
from utils.procurement_purchase_request import _apply_pqdtl_line_udf_columns
from utils.procurement_sql_api_sync import _overlay_pr_line_udfs_from_enriched
from utils.stock_items_catalog import enrich_pr_submit_line_item


def test_enrich_pr_line_sets_dimensional_udfs_from_stock_detail():
    item = {
        "itemCode": "AL 6061-T6 ANOZ PL: 12.0MM",
        "itemName": "AL 6061-T6 ANOZ PL: 12.0MM",
        "qtySqty": 2,
        "qtySuomqty": 0,
        "stockDetail": {
            "CODE": "AL 6061-T6 ANOZ PL: 12.0MM",
            "UDF_THICKNESS": "12",
            "UDF_WIDTH": "1200",
            "UDF_LENGTH": "2400",
            "UDF_DP": "2.7",
            "UDF_DFP": "1000000",
            "UDF_COSTKG": "15.5",
            "UDF_FORMULA": "W*L*T*DP/DFP",
            "UDF_MTYPE": "AL",
        },
    }
    out = enrich_pr_submit_line_item(item)
    assert out.get("udf_thickness") == "12"
    assert out.get("udf_width") == "1200"
    assert out.get("udf_length") == "2400"
    assert out.get("udf_dp") == "2.7"
    assert out.get("udf_costkg") == "15.5"
    assert out.get("udf_formula") == "W*L*T*DP/DFP"
    assert out.get("udf_mtype") == "AL"


def test_build_sdsdocdetail_line_includes_catalog_udfs(monkeypatch):
    def _fake_catalog(*, code="", description="", cached_items=None):
        return {"CODE": code, "DESCRIPTION": description}

    def _fake_detail(c):
        if str(c).strip().upper() == "AL 6061-T6 ANOZ PL: 10.0MM":
            return {
                "CODE": "AL 6061-T6 ANOZ PL: 10.0MM",
                "UDF_THICKNESS": "10",
                "UDF_WIDTH": "1000",
                "UDF_LENGTH": "2000",
                "UDF_DP": "2.7",
                "UDF_FORMULA": "W*L*T*DP/DFP",
                "UDF_MTYPE": "AL",
                "UDF_COSTKG": "14",
            }
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

    row = build_sdsdocdetail_line(
        {
            "itemCode": "AL 6061-T6 ANOZ PL: 10.0MM",
            "itemName": "AL 6061-T6 ANOZ PL: 10.0MM",
            "qtySqty": 2,
            "qtySuomqty": 0,
            "unitPrice": 0,
        },
        seq=1,
        header_project="----",
        default_delivery=None,
    )
    assert row.get("udf_thickness") == "10"
    assert row.get("udf_width") == "1000"
    assert row.get("udf_length") == "2000"
    assert row.get("udf_dp") == "2.7"
    assert row.get("udf_formula") == "W*L*T*DP/DFP"
    assert row.get("udf_mtype") == "AL"
    assert row.get("udf_costkg") == "14"


def test_apply_pqdtl_line_udf_columns_writes_firebird_keys():
    detail_values: dict = {}
    detail_cols = {
        "UDF_THICKNESS",
        "UDF_WIDTH",
        "UDF_LENGTH",
        "UDF_DP",
        "UDF_MTYPE",
        "UDF_FORMULA",
    }
    _apply_pqdtl_line_udf_columns(
        detail_values,
        detail_cols,
        {
            "itemCode": "AL 6061-T6 ANOZ PL: 12.0MM",
            "udf_thickness": "12",
            "udf_width": "1200",
            "udf_length": "2400",
            "udf_dp": "2.7",
            "udf_mtype": "AL",
            "udf_formula": "W*L*T*DP/DFP",
        },
    )
    assert detail_values["UDF_THICKNESS"] == "12"
    assert detail_values["UDF_WIDTH"] == "1200"
    assert detail_values["UDF_MTYPE"] == "AL"


def test_overlay_pr_line_udfs_preserves_dtlkey():
    existing = [{"dtlkey": 9, "seq": 1, "itemcode": "X", "udf_thickness": None}]
    enriched = [{"seq": 1, "itemcode": "X", "udf_thickness": "12", "udf_mtype": "AL"}]
    merged = _overlay_pr_line_udfs_from_enriched(existing, enriched)
    assert merged[0]["dtlkey"] == 9
    assert merged[0]["udf_thickness"] == "12"
    assert merged[0]["udf_mtype"] == "AL"
