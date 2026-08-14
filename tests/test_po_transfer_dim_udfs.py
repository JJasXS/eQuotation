"""PO transfer copies thickness/width/length UDFs (and batch fallback)."""
from decimal import Decimal

from utils.procurement_purchase_order_transfer import (
    _apply_podtl_source_udfs,
    _build_po_detail_and_xtrans,
)
from utils.sql_api_batch import build_batch_code, parse_batch_code_dimensions


def test_parse_batch_code_dimensions_roundtrip():
    code = build_batch_code("12", "100", "500")
    assert code == "12mm*100mm*500mm"
    assert parse_batch_code_dimensions(code) == ("12", "100", "500")
    assert parse_batch_code_dimensions("12.5mm*100mm*500mm") == ("12.5", "100", "500")
    assert parse_batch_code_dimensions("") == ("", "", "")
    assert parse_batch_code_dimensions("not-a-batch") == ("", "", "")


def test_apply_podtl_copies_dim_udfs_from_source():
    detail_cols = {
        "DTLKEY",
        "DOCKEY",
        "BATCH",
        "UDF_THICKNESS",
        "UDF_WIDTH",
        "UDF_LENGTH",
        "UDF_MTYPE",
    }
    detail_values = {"DTLKEY": 1, "DOCKEY": 2, "BATCH": ""}
    source = {
        "udf_thickness": "0.7",
        "udf_width": "320",
        "udf_length": "1000",
        "udf_mtype": "AL",
    }
    _apply_podtl_source_udfs(detail_values, detail_cols, source)
    assert detail_values["UDF_THICKNESS"] == "0.7"
    assert detail_values["UDF_WIDTH"] == "320"
    assert detail_values["UDF_LENGTH"] == "1000"
    assert detail_values["UDF_MTYPE"] == "AL"


def test_apply_podtl_batch_fallback_fills_missing_dims():
    detail_cols = {"DTLKEY", "BATCH", "UDF_THICKNESS", "UDF_WIDTH", "UDF_LENGTH"}
    detail_values = {"DTLKEY": 1, "BATCH": "12mm*100mm*500mm"}
    source = {"batch": "12mm*100mm*500mm"}
    _apply_podtl_source_udfs(detail_values, detail_cols, source)
    assert detail_values["UDF_THICKNESS"] == "12"
    assert detail_values["UDF_WIDTH"] == "100"
    assert detail_values["UDF_LENGTH"] == "500"


def test_apply_podtl_batch_fallback_does_not_override_existing():
    detail_cols = {"BATCH", "UDF_THICKNESS", "UDF_WIDTH", "UDF_LENGTH"}
    detail_values = {
        "BATCH": "12mm*100mm*500mm",
        "UDF_THICKNESS": "0.7",
    }
    source = {"batch": "12mm*100mm*500mm", "udf_thickness": "0.7"}
    _apply_podtl_source_udfs(detail_values, detail_cols, source)
    assert detail_values["UDF_THICKNESS"] == "0.7"
    assert detail_values["UDF_WIDTH"] == "100"
    assert detail_values["UDF_LENGTH"] == "500"


def test_apply_podtl_no_dims_no_batch_leaves_unset():
    detail_cols = {"BATCH", "UDF_THICKNESS", "UDF_WIDTH", "UDF_LENGTH"}
    detail_values = {"BATCH": ""}
    source = {"itemcode": "1050-H0 320MMx0.7MM", "batch": ""}
    _apply_podtl_source_udfs(detail_values, detail_cols, source)
    assert "UDF_THICKNESS" not in detail_values
    assert "UDF_WIDTH" not in detail_values
    assert "UDF_LENGTH" not in detail_values


def test_build_po_detail_includes_dim_udfs():
    po_detail_cols = {
        "DTLKEY",
        "DOCKEY",
        "SEQ",
        "ITEMCODE",
        "LOCATION",
        "BATCH",
        "PROJECT",
        "DESCRIPTION",
        "QTY",
        "UOM",
        "RATE",
        "SQTY",
        "SUOMQTY",
        "OFFSETQTY",
        "UNITPRICE",
        "DELIVERYDATE",
        "TAXAMT",
        "LOCALTAXAMT",
        "TAXINCLUSIVE",
        "AMOUNT",
        "LOCALAMOUNT",
        "PRINTABLE",
        "FROMDOCTYPE",
        "FROMDOCKEY",
        "FROMDTLKEY",
        "TRANSFERABLE",
        "UDF_THICKNESS",
        "UDF_WIDTH",
        "UDF_LENGTH",
    }
    source = {
        "qty": "10",
        "unitprice": "222",
        "taxamt": "0",
        "itemcode": "1050-H0",
        "location": "----",
        "batch": "",
        "description": "AL plate",
        "uom": "UNIT",
        "rate": "1",
        "suomqty": "0.49",
        "transferable": True,
        "udf_thickness": "0.7",
        "udf_width": "320",
        "udf_length": "1000",
    }
    detail_values, _xtrans, amount = _build_po_detail_and_xtrans(
        source=source,
        purchase_request={"udf_status": "APPROVED", "project": "----"},
        request_dockey=89,
        detail_id=1,
        quantity=Decimal("10"),
        already_transferred=Decimal("0"),
        transferable_override=True,
        line_index=1,
        effective_date="2026-08-14",
        po_dockey=10,
        po_detail_key=20,
        po_detail_key_col="DTLKEY",
        po_detail_fk_col="DOCKEY",
        xtrans_key=30,
        xtrans_key_col="DOCKEY",
        xtrans_cols={"DOCKEY", "QTY", "SQTY"},
        supplier_code="400-J0001",
        po_status_value=0,
        po_detail_cols=po_detail_cols,
    )
    assert amount == Decimal("2220.00") or float(amount) == 2220.0
    assert detail_values["UDF_THICKNESS"] == "0.7"
    assert detail_values["UDF_WIDTH"] == "320"
    assert detail_values["UDF_LENGTH"] == "1000"


def test_build_po_detail_batch_fallback():
    po_detail_cols = {
        "DTLKEY",
        "DOCKEY",
        "SEQ",
        "ITEMCODE",
        "LOCATION",
        "BATCH",
        "PROJECT",
        "DESCRIPTION",
        "QTY",
        "UOM",
        "RATE",
        "SQTY",
        "SUOMQTY",
        "OFFSETQTY",
        "UNITPRICE",
        "DELIVERYDATE",
        "TAXAMT",
        "LOCALTAXAMT",
        "TAXINCLUSIVE",
        "AMOUNT",
        "LOCALAMOUNT",
        "PRINTABLE",
        "FROMDOCTYPE",
        "FROMDOCKEY",
        "FROMDTLKEY",
        "TRANSFERABLE",
        "UDF_THICKNESS",
        "UDF_WIDTH",
        "UDF_LENGTH",
    }
    source = {
        "qty": "2",
        "unitprice": "300",
        "taxamt": "0",
        "itemcode": "AL 6061",
        "location": "----",
        "batch": "12mm*100mm*500mm",
        "description": "plate",
        "uom": "UNIT",
        "transferable": True,
    }
    detail_values, _xtrans, _amount = _build_po_detail_and_xtrans(
        source=source,
        purchase_request={"udf_status": "APPROVED"},
        request_dockey=6,
        detail_id=13,
        quantity=Decimal("2"),
        already_transferred=Decimal("0"),
        transferable_override=True,
        line_index=1,
        effective_date="2026-06-02",
        po_dockey=1,
        po_detail_key=1,
        po_detail_key_col="DTLKEY",
        po_detail_fk_col="DOCKEY",
        xtrans_key=1,
        xtrans_key_col="DOCKEY",
        xtrans_cols={"DOCKEY", "QTY"},
        supplier_code="400-J0001",
        po_status_value=0,
        po_detail_cols=po_detail_cols,
    )
    assert detail_values["BATCH"] == "12mm*100mm*500mm"
    assert detail_values["UDF_THICKNESS"] == "12"
    assert detail_values["UDF_WIDTH"] == "100"
    assert detail_values["UDF_LENGTH"] == "500"
