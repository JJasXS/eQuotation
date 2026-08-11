"""Smoke tests proving bulk PR→PO transfer creates linked PO rows."""
import unittest
from unittest.mock import patch

from utils.procurement_purchase_order_transfer import (
    PurchaseOrderTransferValidationError,
    transfer_purchase_request_to_po,
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


def _pr(dockey, docno, details, supplier_code="400-S0001", supplier_name="ACME SUPPLIES", currency="MYR"):
    return {
        "dockey": dockey,
        "docno": docno,
        "docdate": "2026-08-11",
        "currencycode": currency,
        "currencyrate": "1",
        "businessunit": "PROC",
        "project": "----",
        "area": "----",
        "transferable": True,
        "udf_status": "APPROVED",
        "code": supplier_code,
        "companyname": supplier_name,
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


class BulkTransferSmokeTests(unittest.TestCase):
    def setUp(self):
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

    def _run(self, request_groups, supplier, po_number="PO-SMOKE-0001", po_dockey=701):
        inserted = {"PH_PO": [], "PH_PODTL": [], "ST_XTRANS": []}
        next_keys = {
            "PH_PO": iter([po_dockey]),
            "PH_PODTL": iter([8001 + i for i in range(20)]),
            "ST_XTRANS": iter([9001 + i for i in range(20)]),
        }
        connection = _DummyConnection()

        def capture_insert(_cur, table_name, data, existing_columns):
            inserted[table_name].append({key: value for key, value in data.items() if key in existing_columns})

        with patch("utils.procurement_purchase_order_transfer._connect_db", return_value=connection), \
             patch("utils.procurement_purchase_order_transfer._get_table_columns", side_effect=lambda _cur, name: self.table_columns[name]), \
             patch("utils.procurement_purchase_order_transfer._get_string_column_lengths", return_value={}), \
             patch("utils.procurement_purchase_order_transfer._next_purchase_order_number", return_value=po_number), \
             patch("utils.procurement_purchase_order_transfer._purchase_order_number_exists", return_value=False), \
             patch("utils.procurement_purchase_order_transfer._next_key", side_effect=lambda _cur, table_name, _key_col, _gens: next(next_keys[table_name])), \
             patch("utils.procurement_purchase_order_transfer._insert_dynamic", side_effect=capture_insert), \
             patch("utils.procurement_purchase_order_transfer._fetch_existing_transfer_qty_map", return_value={}), \
             patch("utils.procurement_purchase_order_transfer._column_is_numeric", return_value=True):
            result = transfer_purchase_requests_to_single_po(
                request_groups,
                supplier,
                created_by="smoke@test",
                transfer_date="2026-08-11",
            )
        return result, inserted, connection

    def test_single_pr_moves_lines_into_po(self):
        pr = _pr(11, "PR-SMOKE-1", [_detail(111, "ITEM-1", 6, 10)])
        supplier = {"code": "400-S0001", "companyname": "ACME SUPPLIES", "currencycode": "MYR", "currencyrate": 1}
        result, inserted, connection = self._run(
            [{"purchase_request": pr, "transfer_lines": [{"detailId": 111, "quantity": 4}]}],
            supplier,
        )

        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertEqual(result["poNumber"], "PO-SMOKE-0001")
        self.assertEqual(result["lineCount"], 1)
        self.assertEqual(result["transferredQty"], 4.0)
        self.assertEqual(result["sourceRequestNumbers"], ["PR-SMOKE-1"])

        self.assertEqual(len(inserted["PH_PO"]), 1)
        self.assertEqual(len(inserted["PH_PODTL"]), 1)
        self.assertEqual(len(inserted["ST_XTRANS"]), 1)

        po_line = inserted["PH_PODTL"][0]
        self.assertEqual(po_line["FROMDOCTYPE"], "PQ")
        self.assertEqual(po_line["FROMDOCKEY"], 11)
        self.assertEqual(po_line["FROMDTLKEY"], 111)
        self.assertEqual(po_line["QTY"], 4.0)

        x = inserted["ST_XTRANS"][0]
        self.assertEqual(x["FROMDOCTYPE"], "PQ")
        self.assertEqual(x["TODOCTYPE"], "PO")
        self.assertEqual(x["FROMDOCKEY"], 11)
        self.assertEqual(x["TODOCKEY"], 701)
        self.assertEqual(x["QTY"], 4.0)

    def test_bulk_two_suppliers_become_two_pos(self):
        """Mirrors API bucketing: one transfer call per supplier/currency."""
        pr_a = _pr(21, "PR-A", [_detail(211, "ITEM-A", 5)], "400-S0001", "ACME", "MYR")
        pr_b = _pr(22, "PR-B", [_detail(221, "ITEM-B", 3)], "400-S0002", "BETA", "MYR")

        supplier_a = {"code": "400-S0001", "companyname": "ACME", "currencycode": "MYR", "currencyrate": 1}
        supplier_b = {"code": "400-S0002", "companyname": "BETA", "currencycode": "MYR", "currencyrate": 1}

        result_a, inserted_a, _ = self._run(
            [{"purchase_request": pr_a, "transfer_lines": [{"detailId": 211, "quantity": 5}]}],
            supplier_a,
            po_number="PO-A-1",
            po_dockey=801,
        )
        result_b, inserted_b, _ = self._run(
            [{"purchase_request": pr_b, "transfer_lines": [{"detailId": 221, "quantity": 3}]}],
            supplier_b,
            po_number="PO-B-1",
            po_dockey=802,
        )

        self.assertEqual(result_a["poNumber"], "PO-A-1")
        self.assertEqual(result_b["poNumber"], "PO-B-1")
        self.assertEqual(inserted_a["PH_PO"][0]["CODE"], "400-S0001")
        self.assertEqual(inserted_b["PH_PO"][0]["CODE"], "400-S0002")
        self.assertEqual(inserted_a["PH_PODTL"][0]["FROMDOCKEY"], 21)
        self.assertEqual(inserted_b["PH_PODTL"][0]["FROMDOCKEY"], 22)

    def test_rejects_non_approved_pr(self):
        pr = _pr(31, "PR-DRAFT", [_detail(311, "ITEM-X", 2)])
        pr["udf_status"] = "PENDING"
        supplier = {"code": "400-S0001", "companyname": "ACME", "currencycode": "MYR", "currencyrate": 1}
        with self.assertRaises(PurchaseOrderTransferValidationError):
            self._run(
                [{"purchase_request": pr, "transfer_lines": [{"detailId": 311, "quantity": 1}]}],
                supplier,
            )

    def test_wrapper_single_pr_api_shape(self):
        pr = _pr(41, "PR-WRAP", [_detail(411, "ITEM-W", 2)])
        supplier = {"code": "400-S0001", "companyname": "ACME", "currencycode": "MYR", "currencyrate": 1}
        connection = _DummyConnection()
        inserted = {"PH_PO": [], "PH_PODTL": [], "ST_XTRANS": []}
        next_keys = {"PH_PO": iter([901]), "PH_PODTL": iter([9101]), "ST_XTRANS": iter([9201])}

        def capture_insert(_cur, table_name, data, existing_columns):
            inserted[table_name].append({key: value for key, value in data.items() if key in existing_columns})

        with patch("utils.procurement_purchase_order_transfer._connect_db", return_value=connection), \
             patch("utils.procurement_purchase_order_transfer._get_table_columns", side_effect=lambda _cur, name: self.table_columns[name]), \
             patch("utils.procurement_purchase_order_transfer._get_string_column_lengths", return_value={}), \
             patch("utils.procurement_purchase_order_transfer._next_purchase_order_number", return_value="PO-WRAP-1"), \
             patch("utils.procurement_purchase_order_transfer._purchase_order_number_exists", return_value=False), \
             patch("utils.procurement_purchase_order_transfer._next_key", side_effect=lambda _cur, table_name, _key_col, _gens: next(next_keys[table_name])), \
             patch("utils.procurement_purchase_order_transfer._insert_dynamic", side_effect=capture_insert), \
             patch("utils.procurement_purchase_order_transfer._fetch_existing_transfer_qty_map", return_value={}), \
             patch("utils.procurement_purchase_order_transfer._column_is_numeric", return_value=True):
            result = transfer_purchase_request_to_po(
                pr,
                [{"detailId": 411, "quantity": 2}],
                supplier=supplier,
            )

        self.assertEqual(result["poNumber"], "PO-WRAP-1")
        self.assertEqual(inserted["ST_XTRANS"][0]["FROMDOCTYPE"], "PQ")
        self.assertEqual(inserted["ST_XTRANS"][0]["TODOCTYPE"], "PO")


if __name__ == "__main__":
    unittest.main()
