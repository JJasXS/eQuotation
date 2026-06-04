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
    assert suom == Decimal("0.6272")


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
    assert su == Decimal("1.2544")
    assert pricing == Decimal("2")


def test_wtp_fallback_when_no_dimensions():
    item = {"qty": 3}
    stock = {"udf_wtp": "0.5"}
    sq, su, _ = resolve_quotation_line_qty_pair(item, stock)
    assert sq == Decimal("3")
    assert su == Decimal("1.5")
