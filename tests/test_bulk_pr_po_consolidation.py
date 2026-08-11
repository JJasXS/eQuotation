"""Unit tests for multi-PR consolidation into one PH_PO."""
import unittest
from unittest.mock import patch

from utils.procurement_purchase_order_transfer import (
    PurchaseOrderTransferValidationError,
    transfer_purchase_requests_to_single_po,
)


class _DummyConnection:
    def __init__(self):
        self._cursor = object()
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        return None


def _pr(dockey, docno, details):
    return {
        "dockey": dockey,
        "docno": docno,
        "docdate": "2026-08-11",
        "currencycode": "MYR",
        "currencyrate": "1",
        "businessunit": "PROC",
        "project": "----",
        "area": "----",
        "transferable": True,
        "udf_status": "APPROVED",
        "code": "400-S0001",
        "companyname": "ACME SUPPLIES",
        "sdsdocdetail": details,
    }


def _detail(dtlkey, itemcode, qty, unitprice=10):
    return {
        "dtlkey": dtlkey,
        "seq": dtlkey * 1000,
        "itemcode": itemcode,
        "location": "MAIN",
        "project": "----",
        "description": f"Item {itemcode}",
        "qty": str(qty),
        "uom": "UNIT",
        "rate": "1",
        "suomqty": "0",
        "unitprice": str(unitprice),
        "taxamt": "0",
        "taxinclusive": False,
        "amount": str(float(qty) * float(unitprice)),
        "printable": True,
        "transferable": True,
        "udf_pqapproved": True,
    }


class MultiPrConsolidationTransferTests(unittest.TestCase):
    def setUp(self):
        self.supplier = {
            "code": "400-S0001",
            "companyname": "ACME SUPPLIES",
            "address1": "1 Supply Road",
            "terms": "30 Days",
            "currencycode": "MYR",
            "currencyrate": 1,
        }
        self.table_columns = {
            "PH_PO": {
                "DOCKEY", "DOCNO", "DOCNOEX", "DOCDATE", "POSTDATE", "TAXDATE", "CODE", "COMPANYNAME",
                "ADDRESS1", "AREA", "AGENT", "PROJECT", "TERMS", "CURRENCYCODE", "CURRENCYRATE",
                "SHIPPER", "DESCRIPTION", "CANCELLED", "STATUS", "DOCAMT", "LOCALDOCAMT",
                "BUSINESSUNIT", "TRANSFERABLE", "UPDATECOUNT", "PRINTCOUNT", "LASTMODIFIED",
                "IDTYPE", "SUBMISSIONTYPE",
            },
            "PH_PODTL": {
                "DTLKEY", "DOCKEY", "SEQ", "ITEMCODE", "LOCATION", "PROJECT", "DESCRIPTION",
                "QTY", "UOM", "RATE", "SQTY", "SUOMQTY", "OFFSETQTY", "UNITPRICE", "DELIVERYDATE",
                "TAXAMT", "LOCALTAXAMT", "TAXINCLUSIVE", "AMOUNT", "LOCALAMOUNT", "PRINTABLE",
                "FROMDOCTYPE", "FROMDOCKEY", "FROMDTLKEY", "TRANSFERABLE",
            },
            "ST_XTRANS": {
                "DOCKEY", "CODE", "FROMDOCTYPE", "TODOCTYPE", "FROMDOCKEY", "TODOCKEY",
                "FROMDTLKEY", "TODTLKEY", "QTY", "SQTY", "TOSTATUS",
            },
        }

    def _run(self, request_groups, existing_maps=None):
        inserted = {"PH_PO": [], "PH_PODTL": [], "ST_XTRANS": []}
        next_keys = {
            "PH_PO": iter([501]),
            "PH_PODTL": iter([5001, 5002, 5003, 5004]),
            "ST_XTRANS": iter([9001, 9002, 9003, 9004]),
        }
        connection = _DummyConnection()
        existing_maps = existing_maps or {}

        def capture_insert(_cur, table_name, data, existing_columns):
            inserted[table_name].append({key: value for key, value in data.items() if key in existing_columns})

        def fake_existing(_cur, request_dockey, detail_ids, _cols):
            return existing_maps.get(int(request_dockey), {})

        with patch("utils.procurement_purchase_order_transfer._connect_db", return_value=connection), \
             patch("utils.procurement_purchase_order_transfer._get_table_columns", side_effect=lambda _cur, name: self.table_columns[name]), \
             patch("utils.procurement_purchase_order_transfer._get_string_column_lengths", return_value={}), \
             patch("utils.procurement_purchase_order_transfer._next_purchase_order_number", return_value="PO-20260811-0001"), \
             patch("utils.procurement_purchase_order_transfer._purchase_order_number_exists", return_value=False), \
             patch("utils.procurement_purchase_order_transfer._next_key", side_effect=lambda _cur, table_name, _key_col, _gens: next(next_keys[table_name])), \
             patch("utils.procurement_purchase_order_transfer._insert_dynamic", side_effect=capture_insert), \
             patch("utils.procurement_purchase_order_transfer._fetch_existing_transfer_qty_map", side_effect=fake_existing), \
             patch("utils.procurement_purchase_order_transfer._column_is_numeric", return_value=True):
            result = transfer_purchase_requests_to_single_po(
                request_groups,
                self.supplier,
                created_by="tester@example.com",
                transfer_date="2026-08-11",
            )
        return result, inserted, connection

    def test_one_po_with_distinct_fromdockey_values(self):
        pr_a = _pr(10, "PR-A", [_detail(101, "ITEM-A", 5, 12), _detail(102, "ITEM-B", 3, 8)])
        pr_b = _pr(20, "PR-B", [_detail(201, "ITEM-C", 4, 15)])
        result, inserted, connection = self._run(
            [
                {"purchase_request": pr_a, "transfer_lines": [{"detailId": 101, "quantity": 5}, {"detailId": 102, "quantity": 2}]},
                {"purchase_request": pr_b, "transfer_lines": [{"detailId": 201, "quantity": 4}]},
            ]
        )

        self.assertTrue(connection.committed)
        self.assertEqual(result["poDockey"], 501)
        self.assertEqual(result["poNumber"], "PO-20260811-0001")
        self.assertEqual(result["sourceRequestDockeys"], [10, 20])
        self.assertEqual(result["sourceRequestNumbers"], ["PR-A", "PR-B"])
        self.assertEqual(len(inserted["PH_PO"]), 1)
        self.assertEqual(len(inserted["PH_PODTL"]), 3)
        self.assertEqual(len(inserted["ST_XTRANS"]), 3)

        header = inserted["PH_PO"][0]
        self.assertEqual(header["CODE"], "400-S0001")
        self.assertIn("PR-A", header["DESCRIPTION"])
        self.assertIn("PR-B", header["DESCRIPTION"])

        from_dockeys = sorted({row["FROMDOCKEY"] for row in inserted["PH_PODTL"]})
        self.assertEqual(from_dockeys, [10, 20])

        lineage = {(row["FROMDOCKEY"], row["FROMDTLKEY"], row["QTY"]) for row in inserted["PH_PODTL"]}
        self.assertEqual(lineage, {(10, 101, 5.0), (10, 102, 2.0), (20, 201, 4.0)})

        x_lineage = {(row["FROMDOCKEY"], row["FROMDTLKEY"], row["TODOCKEY"], row["QTY"]) for row in inserted["ST_XTRANS"]}
        self.assertEqual(x_lineage, {(10, 101, 501, 5.0), (10, 102, 501, 2.0), (20, 201, 501, 4.0)})

    def test_rejects_duplicate_request_detail_pair(self):
        pr_a = _pr(10, "PR-A", [_detail(101, "ITEM-A", 5)])
        with self.assertRaises(PurchaseOrderTransferValidationError):
            self._run(
                [
                    {"purchase_request": pr_a, "transfer_lines": [{"detailId": 101, "quantity": 1}]},
                    {"purchase_request": pr_a, "transfer_lines": [{"detailId": 101, "quantity": 1}]},
                ]
            )

    def test_rejects_over_transfer_per_source_pr(self):
        pr_a = _pr(10, "PR-A", [_detail(101, "ITEM-A", 5)])
        pr_b = _pr(20, "PR-B", [_detail(201, "ITEM-C", 4)])
        with self.assertRaises(PurchaseOrderTransferValidationError):
            self._run(
                [
                    {"purchase_request": pr_a, "transfer_lines": [{"detailId": 101, "quantity": 3}]},
                    {"purchase_request": pr_b, "transfer_lines": [{"detailId": 201, "quantity": 4}]},
                ],
                existing_maps={10: {101: 3}},  # remaining on PR-A detail 101 is 2
            )


if __name__ == "__main__":
    unittest.main()
