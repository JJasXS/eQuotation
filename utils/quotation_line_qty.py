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
    """Sales quotation weight uses UDF_DS (g/cm³) from stock master only."""
    for key in ("udf_ds", "UDF_DS"):
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

    SUOMQTY = SQTY × (T_mm × W_mm × L_mm × UDF_DS) / UDF_DFS

    SQL Accounting stock items for sheet/coil (e.g. formula ``ZF/004``) use
    ``UDF_DFS = 1_000_000`` with ``UDF_DS`` in g/cm³. Result is weight in KG
    (same as ``suomqty`` / ``udf_wts`` on ``/salesquotation`` lines).
    """
    per_unit = (thickness_mm * width_mm * length_mm * density_g_cm3) / Decimal("1000000")
    return (sqty * per_unit).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def resolve_udf_wts_strict(
    item: dict[str, Any],
    stock: dict[str, Any] | None = None,
) -> Decimal | None:
    """
    ``udf_wts`` only when all inputs are present: line qty + line T/W/L + stock UDF_DS.

    No WTP fallback, no copying sqty into suom, no catalog/stock default dimensions.
    """
    stock_row: dict[str, Any] = {}
    for blob_key in ("stockDetail", "stockApi", "stockCatalog", "catalogRow"):
        blob = item.get(blob_key)
        if isinstance(blob, dict):
            stock_row.update(blob)
    if isinstance(stock, dict):
        stock_row.update(stock)

    merged_udfs = merge_item_and_stock_udf_fields_for_api({}, stock_row)
    stock_udfs = stock_item_udf_fields_from_row(stock_row)
    merged_udfs = {**stock_udfs, **merged_udfs}

    sqty = _as_decimal(item.get("qty") or item.get("quantity") or 0, "0")
    if sqty <= 0:
        return None

    t = _positive_decimal(
        _scalar_from_sources(item, keys=("udfThickness", "udf_thickness", "UDF_THICKNESS", "thickness"))
    )
    w = _positive_decimal(
        _scalar_from_sources(item, keys=("udfWidth", "udf_width", "UDF_WIDTH", "width"))
    )
    l = _positive_decimal(
        _scalar_from_sources(
            item,
            keys=("udfLength", "udf_length", "UDF_LENGTH", "length", "height", "udfHeight"),
        )
    )
    density = _pick_sales_density(merged_udfs)
    if t is None or w is None or l is None or density is None:
        return None

    return suomqty_from_dimensions_mm(
        thickness_mm=t,
        width_mm=w,
        length_mm=l,
        density_g_cm3=density,
        sqty=sqty,
    )


def resolve_quotation_line_qty_pair(
    item: dict[str, Any],
    stock: dict[str, Any] | None = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Return (sqty, suomqty, pricing_qty).

    ``suomqty`` is strict dimension weight only (or zero). ``pricing_qty`` uses order qty (sqty).
    """
    explicit_sq = _scalar_from_sources(item, keys=("qtySqty", "sqty", "SQTY"))
    sqty = _as_decimal(
        explicit_sq if explicit_sq is not None else (item.get("qty") or item.get("quantity") or 0),
        "0",
    )
    if sqty < 0:
        sqty = Decimal("0")

    suom = resolve_udf_wts_strict(item, stock)
    if suom is None:
        suom = Decimal("0")

    pricing = sqty if sqty > 0 else Decimal("0")
    return sqty, suom, pricing


def preview_udf_wts_for_quotation_line(
    item: dict[str, Any],
    stock: dict[str, Any] | None = None,
) -> float | None:
    """Preview ``udf_wts`` for create-quotation — dimension formula only, no fallbacks."""
    suom = resolve_udf_wts_strict(item, stock)
    if suom is None or suom <= 0:
        return None
    return float(suom)
