"""SQTY / SUOMQTY resolution for sales quotation lines (create + SQL API submit)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from utils.stock_items_catalog import merge_item_and_stock_udf_fields_for_api, stock_item_udf_fields_from_row


def _as_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default).replace(",", "").strip())
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _positive_decimal(value: Any) -> Decimal | None:
    d = _as_decimal(value, "0")
    if d > 0:
        return d
    return None


def _scalar_from_sources(*sources: dict[str, Any] | None, keys: tuple[str, ...]) -> Any:
    for src in sources:
        if not isinstance(src, dict):
            continue
        lower = {str(k).lower(): v for k, v in src.items()}
        for key in keys:
            if key in src and src[key] is not None:
                return src[key]
            low = key.lower()
            if low in lower and lower[low] is not None:
                return lower[low]
    return None


def _pick_sales_density(merged_udfs: dict[str, Any]) -> Decimal | None:
    """Sales quotation weight uses UDF_DS (g/cm³) when set."""
    for key in ("udf_ds", "UDF_DS"):
        d = _positive_decimal(merged_udfs.get(key) if key in merged_udfs else merged_udfs.get(key.lower()))
        if d is not None:
            return d
    return None


def _pick_wtp(merged_udfs: dict[str, Any]) -> Decimal | None:
    for key in ("udf_wtp", "UDF_WTP", "udf_weight", "UDF_WEIGHT"):
        d = _positive_decimal(merged_udfs.get(key) if key in merged_udfs else merged_udfs.get(key.lower()))
        if d is not None:
            return d
    return None


def suomqty_from_dimensions_mm(
    *,
    thickness_mm: Decimal,
    width_mm: Decimal,
    length_mm: Decimal,
    density_g_cm3: Decimal,
    sqty: Decimal,
) -> Decimal:
    """
    Weight (KG) for sheet/coil style items.

    SUOMQTY = SQTY × (T_mm × W_mm × L_mm × density_g/cm³) / 1_000_000
    """
    per_unit = (thickness_mm * width_mm * length_mm * density_g_cm3) / Decimal("1000000")
    return (sqty * per_unit).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def resolve_quotation_line_qty_pair(
    item: dict[str, Any],
    stock: dict[str, Any] | None = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Return (sqty, suomqty, pricing_qty).

    pricing_qty follows procurement: SQTY when present, else SUOMQTY (unit price basis).
    """
    stock_row = dict(stock or {})
    for blob_key in ("stockDetail", "stockApi", "stockCatalog", "catalogRow"):
        blob = item.get(blob_key)
        if isinstance(blob, dict):
            stock_row.update(blob)

    merged_udfs = merge_item_and_stock_udf_fields_for_api(item, stock_row)
    stock_udfs = stock_item_udf_fields_from_row(stock_row)
    merged_udfs = {**stock_udfs, **merged_udfs}

    explicit_su = _scalar_from_sources(item, keys=("qtySuomqty", "suomqty", "SUOMQTY"))
    explicit_sq = _scalar_from_sources(item, keys=("qtySqty", "sqty", "SQTY"))

    sqty = _as_decimal(
        explicit_sq if explicit_sq is not None else (item.get("qty") or item.get("quantity") or 0),
        "0",
    )
    if sqty < 0:
        sqty = Decimal("0")

    suom: Decimal | None = None
    if explicit_su is not None:
        suom = _as_decimal(explicit_su, "0")

    if suom is None or suom <= 0:
        t = _positive_decimal(
            _scalar_from_sources(
                item,
                stock_row,
                keys=("udfThickness", "udf_thickness", "UDF_THICKNESS", "thickness"),
            )
        )
        w = _positive_decimal(
            _scalar_from_sources(
                item,
                stock_row,
                keys=("udfWidth", "udf_width", "UDF_WIDTH", "width"),
            )
        )
        l = _positive_decimal(
            _scalar_from_sources(
                item,
                stock_row,
                keys=("udfLength", "udf_length", "UDF_LENGTH", "length", "height", "udfHeight"),
            )
        )
        density = _pick_sales_density(merged_udfs)
        if t is not None and w is not None and l is not None and density is not None and sqty > 0:
            suom = suomqty_from_dimensions_mm(
                thickness_mm=t,
                width_mm=w,
                length_mm=l,
                density_g_cm3=density,
                sqty=sqty,
            )

    if (suom is None or suom <= 0) and sqty > 0:
        wtp = _pick_wtp(merged_udfs)
        if wtp is not None:
            suom = (sqty * wtp).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    if suom is None or suom < 0:
        suom = sqty

    if sqty > 0:
        pricing = sqty
    elif suom > 0:
        pricing = suom
    else:
        pricing = Decimal("0")

    return sqty, suom, pricing
