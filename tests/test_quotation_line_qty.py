"""Tests for quotation SQTY / SUOMQTY from dimensions (mm) and UDF_DS."""
from decimal import Decimal

from utils.quotation_line_qty import resolve_quotation_line_qty_pair, suomqty_from_dimensions_mm


def test_suom_from_dimensions_single_piece():
    suom = suomqty_from_dimensions_mm(
        thickness_mm=Decimal("0.7"),
        width_mm=Decimal("320"),
        length_mm=Decimal("1000"),
        density_g_cm3=Decimal("2.8"),
        sqty=Decimal("1"),
    )
    assert suom == Decimal("0.627")


def test_resolve_from_item_and_stock():
    item = {
        "qty": 2,
        "udfThickness": "0.7",
        "udfWidth": "320",
        "udfLength": "1000",
    }
    stock = {"udf_ds": "2.8"}
    sq, su, pricing = resolve_quotation_line_qty_pair(item, stock)
    assert sq == Decimal("2")
    assert su == Decimal("1.254")
    assert pricing == Decimal("2")


def test_sheet_style_dimensions_qt43143():
    """AL 6061 line: T×W×L (mm) × UDF_DS → udf_wts ≈ 1.968 for qty 1."""
    item = {
        "qty": 1,
        "udfThickness": "12",
        "udfWidth": "120",
        "udfLength": "488",
    }
    stock = {"udf_ds": "2.8", "UDF_DS": "2.8"}
    _, su, _ = resolve_quotation_line_qty_pair(item, stock)
    assert abs(su - Decimal("1.968")) < Decimal("0.001")


def test_preview_udf_wts_helper():
    from utils.quotation_line_qty import preview_udf_wts_for_quotation_line

    wts = preview_udf_wts_for_quotation_line(
        {"qty": 1, "udfThickness": "12", "udfWidth": "79", "udfLength": "309"},
        {"udf_ds": "2.8"},
    )
    assert abs(wts - 0.82) < 0.001


def test_no_wtp_fallback_when_dimensions_missing():
    item = {"qty": 3}
    stock = {"udf_wtp": "0.5"}
    sq, su, _ = resolve_quotation_line_qty_pair(item, stock)
    assert sq == Decimal("3")
    assert su == Decimal("0")


def test_strict_udf_wts_requires_line_dimensions():
    from utils.quotation_line_qty import preview_udf_wts_for_quotation_line

    assert preview_udf_wts_for_quotation_line({"qty": 1}, {"udf_ds": "2.8"}) is None
    assert preview_udf_wts_for_quotation_line(
        {"qty": 1, "udfThickness": "12", "udfWidth": "120", "udfLength": "488"},
        {"udf_ds": "2.8"},
    ) is not None
