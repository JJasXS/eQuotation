"""Configurable pricing engine based on PricingPriorityRule settings."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from utils.db_utils import get_db_connection

logger = logging.getLogger(__name__)


@dataclass
class PricingResult:
    selected_price: float
    price_source: Optional[str]
    matched_rule_code: Optional[str]
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'SelectedPrice': self.selected_price,
            'PriceSource': self.price_source,
            'MatchedRuleCode': self.matched_rule_code,
            'Message': self.message,
        }


class PricingService:
    """Evaluate pricing rules in configured priority order and stop at the first valid match."""

    def __init__(self) -> None:
        self._table_exists_cache: Dict[str, bool] = {}
        self._column_exists_cache: Dict[Tuple[str, str], bool] = {}
        self._rule_handlers: Dict[str, Callable[..., Optional[PricingResult]]] = {
            'CUSTOMER_PRICE_TAG': self._evaluate_customer_price_tag,
            'REF_PRICE_BASED_ON_UOM': self._evaluate_ref_price_based_on_uom,
            'MIN_MAX_SELLING_PRICE': self._evaluate_min_max_selling_price,
            'LAST_QUOTATION_SELLING_PRICE': self._evaluate_last_quotation_selling_price,
            'LAST_SALES_ORDER_SELLING_PRICE': self._evaluate_last_sales_order_selling_price,
            'LAST_SALES_DELIVERY_ORDER_SELLING_PRICE': self._evaluate_last_sales_delivery_order_selling_price,
            'LAST_SALES_INVOICE_SELLING_PRICE': self._evaluate_last_sales_invoice_selling_price,
            'LAST_CASH_SALES_SELLING_PRICE': self._evaluate_last_cash_sales_selling_price,
            'LAST_SALES_INVOICE_CASH_SALES_SELLING_PRICE': self._evaluate_last_sales_invoice_cash_sales_selling_price,
        }

    def get_selling_price(self, customer_code: str, item_code: str, uom: Optional[str] = None) -> Dict[str, Any]:
        customer_code = (customer_code or '').strip()
        item_code = (item_code or '').strip()
        uom = (uom or '').strip() or None

        if not customer_code:
            raise ValueError('CustomerCode is required')
        if not item_code:
            raise ValueError('ItemCode is required')

        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            enabled_rules = self._load_enabled_rules(cursor)
            logger.debug('Evaluating %s pricing rules for customer=%s item=%s', len(enabled_rules), customer_code, item_code)

            for rule in enabled_rules:
                rule_code = rule['RuleCode']
                handler = self._rule_handlers.get(rule_code)
                if handler is None:
                    logger.debug('Skipping unsupported pricing rule %s', rule_code)
                    continue

                result = handler(cursor, customer_code, item_code, uom)
                if result is not None:
                    logger.info('Price selected from %s for customer=%s item=%s', rule_code, customer_code, item_code)
                    return result.to_dict()

            return PricingResult(
                selected_price=0.0,
                price_source=None,
                matched_rule_code=None,
                message='No enabled pricing rule returned a valid price'
            ).to_dict()
        finally:
            cursor.close()
            connection.close()

    def _load_enabled_rules(self, cursor) -> List[Dict[str, Any]]:
        cursor.execute(
            '''
            SELECT RuleCode, RuleName, PriorityNo, IsEnabled
            FROM PricingPriorityRule
            WHERE IsEnabled = 1
            ORDER BY PriorityNo ASC, PricingPriorityRuleId ASC
            '''
        )
        rules: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            rules.append({
                'RuleCode': str(row[0]).strip() if row[0] is not None else '',
                'RuleName': str(row[1]).strip() if row[1] is not None else '',
                'PriorityNo': int(row[2]) if row[2] is not None else 0,
                'IsEnabled': int(row[3]) if row[3] is not None else 0,
            })
        return rules

    def _evaluate_customer_price_tag(self, cursor, customer_code: str, item_code: str, uom: Optional[str]) -> Optional[PricingResult]:
        customer_tag = self._get_customer_price_tag(cursor, customer_code)

        if not self._table_exists(cursor, 'ST_ITEM_PRICE'):
            return None

        code_column = self._first_existing_column(cursor, 'ST_ITEM_PRICE', ['CODE', 'ITEMCODE'])
        price_column = self._first_existing_column(cursor, 'ST_ITEM_PRICE', ['STOCKVALUE', 'PRICE', 'UNITPRICE'])
        tag_column = self._first_existing_column(cursor, 'ST_ITEM_PRICE', ['TAGTYPE', 'PRICETAG', 'PRICETAGCODE', 'PRICECATEGORY', 'PRICELEVEL'])
        disc_column = self._first_existing_column(cursor, 'ST_ITEM_PRICE', ['DISCOUNT', 'DISC'])
        if not code_column or not price_column:
            return None

        select_cols = f'{price_column}' if not disc_column else f'{price_column}, {disc_column}'
        row = None

        # Try strict tag match first when both customer tag and tag column are available.
        if customer_tag and tag_column:
            query = (
                f'SELECT FIRST 1 {select_cols} '
                f'FROM ST_ITEM_PRICE '
                f'WHERE {code_column} = ? AND {tag_column} = ? AND {price_column} IS NOT NULL '
                f'ORDER BY {price_column} DESC'
            )
            cursor.execute(query, (item_code, customer_tag))
            row = cursor.fetchone()

        # If no tag match is found (or tag is not configured), fall back to item-only price.
        if not row:
            query = (
                f'SELECT FIRST 1 {select_cols} '
                f'FROM ST_ITEM_PRICE '
                f'WHERE {code_column} = ? AND {price_column} IS NOT NULL '
                f'ORDER BY {price_column} DESC'
            )
            cursor.execute(query, (item_code,))
            row = cursor.fetchone()

        if not row:
            return None
        price = self._coerce_float(row[0])
        net_price = self._apply_disc(price, row[1] if disc_column else None) if price is not None else None
        if net_price is None or net_price <= 0:
            return None

        source_label = f'Customer Price Tag ({customer_tag})' if customer_tag else 'Customer Price Tag (item fallback)'
        return PricingResult(
            selected_price=net_price,
            price_source=source_label,
            matched_rule_code='CUSTOMER_PRICE_TAG',
            message='Price selected from CUSTOMER_PRICE_TAG'
        )

    def _evaluate_ref_price_based_on_uom(self, cursor, customer_code: str, item_code: str, uom: Optional[str]) -> Optional[PricingResult]:
        if not self._table_exists(cursor, 'ST_ITEM_UOM'):
            return None

        code_column = self._first_existing_column(cursor, 'ST_ITEM_UOM', ['CODE', 'ITEMCODE'])
        price_column = self._first_existing_column(cursor, 'ST_ITEM_UOM', ['REFPRICE', 'PRICE', 'UNITPRICE'])
        uom_column = self._first_existing_column(cursor, 'ST_ITEM_UOM', ['UOM', 'UOMCODE', 'UNIT', 'BASEUOM'])
        if not code_column or not price_column:
            return None

        select_cols = f'{price_column}'
        if uom and uom_column:
            cursor.execute(
                f'SELECT FIRST 1 {select_cols} FROM ST_ITEM_UOM WHERE {code_column} = ? AND {uom_column} = ? AND {price_column} IS NOT NULL',
                (item_code, uom)
            )
        else:
            cursor.execute(
                f'SELECT FIRST 1 {select_cols} FROM ST_ITEM_UOM WHERE {code_column} = ? AND {price_column} IS NOT NULL',
                (item_code,)
            )

        row = cursor.fetchone()
        if not row:
            return None
        price = self._coerce_float(row[0])
        net_price = price if price is not None else None
        if net_price is None or net_price <= 0:
            return None

        source = 'Ref. Price of Item Based on UOM'
        if uom and uom_column:
            source = f'{source} ({uom})'

        return PricingResult(
            selected_price=net_price,
            price_source=source,
            matched_rule_code='REF_PRICE_BASED_ON_UOM',
            message='Price selected from REF_PRICE_BASED_ON_UOM'
        )

    def _evaluate_min_max_selling_price(self, cursor, customer_code: str, item_code: str, uom: Optional[str]) -> Optional[PricingResult]:
        if not self._table_exists(cursor, 'ST_ITEM'):
            return None

        code_column = self._first_existing_column(cursor, 'ST_ITEM', ['CODE', 'ITEMCODE'])
        min_column = self._first_existing_column(cursor, 'ST_ITEM', ['UDF_MINSELLINGPRICE', 'MINSELLINGPRICE', 'MINPRICE'])
        max_column = self._first_existing_column(cursor, 'ST_ITEM', ['UDF_MAXSELLINGPRICE', 'MAXSELLINGPRICE', 'MAXPRICE'])
        if not code_column or (not min_column and not max_column):
            return None

        columns = [column for column in [min_column, max_column] if column]
        cursor.execute(
            f'SELECT {", ".join(columns)} FROM ST_ITEM WHERE {code_column} = ?',
            (item_code,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        values = self._row_to_dict_from_columns(columns, row)
        min_price = self._coerce_float(values.get(min_column)) if min_column else None
        max_price = self._coerce_float(values.get(max_column)) if max_column else None

        reference_result = self._evaluate_ref_price_based_on_uom(cursor, customer_code, item_code, uom)
        if reference_result is None:
            return None

        adjusted_price = reference_result.selected_price
        if min_price is not None and adjusted_price < min_price:
            adjusted_price = min_price
        if max_price is not None and adjusted_price > max_price:
            adjusted_price = max_price

        return PricingResult(
            selected_price=adjusted_price,
            price_source='Min & Max Selling Price',
            matched_rule_code='MIN_MAX_SELLING_PRICE',
            message='Price selected from MIN_MAX_SELLING_PRICE'
        )

    def _evaluate_last_quotation_selling_price(self, cursor, customer_code: str, item_code: str, uom: Optional[str]) -> Optional[PricingResult]:
        return self._evaluate_recent_document_rule(
            cursor,
            customer_code,
            item_code,
            'LAST_QUOTATION_SELLING_PRICE',
            'Last Quotation Selling Price',
            [('SL_QT', 'SL_QTDTL')]
        )

    def _evaluate_last_sales_order_selling_price(self, cursor, customer_code: str, item_code: str, uom: Optional[str]) -> Optional[PricingResult]:
        return self._evaluate_recent_document_rule(
            cursor,
            customer_code,
            item_code,
            'LAST_SALES_ORDER_SELLING_PRICE',
            'Last Sales Order Selling Price',
            [('SL_SO', 'SL_SODTL')]
        )

    def _evaluate_last_sales_delivery_order_selling_price(self, cursor, customer_code: str, item_code: str, uom: Optional[str]) -> Optional[PricingResult]:
        return self._evaluate_recent_document_rule(
            cursor,
            customer_code,
            item_code,
            'LAST_SALES_DELIVERY_ORDER_SELLING_PRICE',
            'Last Sales Delivery Order Selling Price',
            [('SL_DO', 'SL_DODTL')]
        )

    def _evaluate_last_sales_invoice_selling_price(self, cursor, customer_code: str, item_code: str, uom: Optional[str]) -> Optional[PricingResult]:
        return self._evaluate_recent_document_rule(
            cursor,
            customer_code,
            item_code,
            'LAST_SALES_INVOICE_SELLING_PRICE',
            'Last Sales Invoice Selling Price',
            [('SL_IV', 'SL_IVDTL')]
        )

    def _evaluate_last_cash_sales_selling_price(self, cursor, customer_code: str, item_code: str, uom: Optional[str]) -> Optional[PricingResult]:
        return self._evaluate_recent_document_rule(
            cursor,
            customer_code,
            item_code,
            'LAST_CASH_SALES_SELLING_PRICE',
            'Last Cash Sales Selling Price',
            [('SL_CS', 'SL_CSDTL'), ('CS_CS', 'CS_CSDTL')]
        )

    def _evaluate_last_sales_invoice_cash_sales_selling_price(self, cursor, customer_code: str, item_code: str, uom: Optional[str]) -> Optional[PricingResult]:
        candidates = []
        invoice_result = self._recent_document_price(cursor, customer_code, item_code, [('SL_IV', 'SL_IVDTL')])
        if invoice_result:
            candidates.append(invoice_result)
        cash_result = self._recent_document_price(cursor, customer_code, item_code, [('SL_CS', 'SL_CSDTL'), ('CS_CS', 'CS_CSDTL')])
        if cash_result:
            candidates.append(cash_result)

        if not candidates:
            return None

        best = max(candidates, key=lambda row: row['doc_sort'])
        return PricingResult(
            selected_price=best['price'],
            price_source='Last Sales Invoice / Cash Sales Selling Price',
            matched_rule_code='LAST_SALES_INVOICE_CASH_SALES_SELLING_PRICE',
            message='Price selected from LAST_SALES_INVOICE_CASH_SALES_SELLING_PRICE'
        )

    def _evaluate_recent_document_rule(
        self,
        cursor,
        customer_code: str,
        item_code: str,
        rule_code: str,
        source_name: str,
        table_pairs: Sequence[Tuple[str, str]],
    ) -> Optional[PricingResult]:
        match = self._recent_document_price(cursor, customer_code, item_code, table_pairs)
        if not match:
            return None

        return PricingResult(
            selected_price=match['price'],
            price_source=source_name,
            matched_rule_code=rule_code,
            message=f'Price selected from {rule_code}'
        )

    def _recent_document_price(
        self,
        cursor,
        customer_code: str,
        item_code: str,
        table_pairs: Sequence[Tuple[str, str]],
    ) -> Optional[Dict[str, Any]]:
        for header_table, detail_table in table_pairs:
            if not (self._table_exists(cursor, header_table) and self._table_exists(cursor, detail_table)):
                continue

            header_customer_column = self._first_existing_column(cursor, header_table, ['CODE', 'CUSTOMERCODE'])
            header_key_column = self._first_existing_column(cursor, header_table, ['DOCKEY', 'DOCID'])
            header_date_column = self._first_existing_column(cursor, header_table, ['DOCDATE', 'DOC_DATE', 'CREATEDAT'])
            detail_key_column = self._first_existing_column(cursor, detail_table, ['DOCKEY', 'DOCID'])
            detail_item_column = self._first_existing_column(cursor, detail_table, ['ITEMCODE', 'CODE', 'STOCKCODE'])

            # Pin specific detail tables to UNITPRICE; fall back to generic priority for others.
            if detail_table.upper() in ('SL_QTDTL', 'SL_SODTL', 'SL_IVDTL') and self._column_exists(cursor, detail_table, 'UNITPRICE'):
                detail_price_column = 'UNITPRICE'
            else:
                detail_price_column = self._first_existing_column(cursor, detail_table, ['UNITPRICE', 'PRICE', 'STOCKVALUE'])
            detail_discount_column = self._first_existing_column(cursor, detail_table, ['DISC', 'DISCOUNT'])
            if not all([header_customer_column, header_key_column, header_date_column, detail_key_column, detail_item_column, detail_price_column]):
                continue

            use_raw_saved_price = False  # Always apply DISC for UNITPRICE-based columns.

            select_columns = [
                f'd.{detail_price_column} AS PRICE_VALUE',
                f'h.{header_date_column} AS DOC_DATE',
            ]
            if detail_discount_column:
                select_columns.append(f'd.{detail_discount_column} AS DISCOUNT_VALUE')

            query = (
                f'SELECT FIRST 1 {", ".join(select_columns)} '
                f'FROM {detail_table} d '
                f'JOIN {header_table} h ON h.{header_key_column} = d.{detail_key_column} '
                f'WHERE h.{header_customer_column} = ? AND d.{detail_item_column} = ? '
                f'ORDER BY h.{header_date_column} DESC, h.{header_key_column} DESC'
            )
            cursor.execute(query, (customer_code, item_code))
            row = cursor.fetchone()
            if not row:
                continue

            data = self._row_to_dict(cursor, row)
            price = self._coerce_float(data.get('PRICE_VALUE'))
            if price is None:
                continue

            net_price = price if use_raw_saved_price else self._apply_disc(price, data.get('DISCOUNT_VALUE'))
            if net_price <= 0:
                continue

            return {
                'price': net_price,
                'doc_sort': str(data.get('DOC_DATE') or ''),
            }

        return None

    def _get_customer_price_tag(self, cursor, customer_code: str) -> Optional[str]:
        if not self._table_exists(cursor, 'AR_CUSTOMER'):
            return None

        customer_code_column = self._first_existing_column(cursor, 'AR_CUSTOMER', ['CODE', 'CUSTOMERCODE'])
        tag_column = self._first_existing_column(cursor, 'AR_CUSTOMER', ['PRICETAG', 'PRICETAGCODE', 'PRICECATEGORY', 'PRICELEVEL'])
        if not customer_code_column or not tag_column:
            return None

        cursor.execute(
            f'SELECT FIRST 1 {tag_column} FROM AR_CUSTOMER WHERE {customer_code_column} = ?',
            (customer_code,)
        )
        row = cursor.fetchone()
        if not row or row[0] is None:
            return None
        return str(row[0]).strip() or None

    def _table_exists(self, cursor, table_name: str) -> bool:
        table_name = table_name.upper()
        if table_name not in self._table_exists_cache:
            cursor.execute(
                "SELECT COUNT(*) FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ? AND COALESCE(RDB$SYSTEM_FLAG, 0) = 0",
                (table_name,)
            )
            self._table_exists_cache[table_name] = bool(cursor.fetchone()[0])
        return self._table_exists_cache[table_name]

    def _column_exists(self, cursor, table_name: str, column_name: str) -> bool:
        key = (table_name.upper(), column_name.upper())
        if key not in self._column_exists_cache:
            cursor.execute(
                '''
                SELECT COUNT(*)
                FROM RDB$RELATION_FIELDS
                WHERE RDB$RELATION_NAME = ? AND RDB$FIELD_NAME = ?
                ''',
                key
            )
            self._column_exists_cache[key] = bool(cursor.fetchone()[0])
        return self._column_exists_cache[key]

    def _first_existing_column(self, cursor, table_name: str, candidates: Iterable[str]) -> Optional[str]:
        for candidate in candidates:
            if self._column_exists(cursor, table_name, candidate):
                return candidate
        return None

    @staticmethod
    def _row_to_dict(cursor, row: Sequence[Any]) -> Dict[str, Any]:
        return {
            (column[0].strip() if isinstance(column[0], str) else column[0]): value
            for column, value in zip(cursor.description, row)
        }

    @staticmethod
    def _row_to_dict_from_columns(columns: Sequence[str], row: Sequence[Any]) -> Dict[str, Any]:
        return {column: value for column, value in zip(columns, row)}

    @staticmethod
    def _apply_disc(unit_price: float, disc_raw: Any) -> float:
        """Apply DISC as a direct discount amount (not percentage).

        Example: UNITPRICE=500 and DISC='5' => 495.
        DISC is VARCHAR in Firebird; non-numeric compound strings (e.g. '5+3')
        are treated as unparseable and left unchanged.
        """
        if disc_raw is None:
            return unit_price
        disc_str = str(disc_raw).strip()
        if not disc_str:
            return unit_price
        try:
            discount_amount = float(disc_str)
            if discount_amount <= 0:
                return unit_price
            return max(0.0, unit_price - discount_amount)
        except (TypeError, ValueError):
            # Complex compound discount string (e.g. '5+3') — return price as-is
            return unit_price

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


_def_service = PricingService()


def get_selling_price(customer_code: str, item_code: str, uom: Optional[str] = None) -> Dict[str, Any]:
    """Convenience wrapper for callers that only need a single price evaluation."""
    return _def_service.get_selling_price(customer_code, item_code, uom=uom)
