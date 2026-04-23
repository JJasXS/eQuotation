"""Unit tests for PR -> PO transfer mapping into PH_PO, PH_PODTL, and ST_XTRANS."""
import unittest
from unittest.mock import patch

from utils.procurement_purchase_order_transfer import (
    PurchaseOrderTransferValidationError,
    transfer_purchase_request_to_po,
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


class PurchaseRequestTransferServiceTests(unittest.TestCase):
    def setUp(self):
        self.purchase_request = {
            "dockey": 18,
            "docno": "PQ-00005",
            "docdate": "2025-06-11",
            "currencycode": "MYR",
            "currencyrate": "1",
            "businessunit": "PROC",
            "project": "----",
            "transferable": True,
            "daddress1": "1, Jalan Setia Dagang AK U13/AK,",
            "daddress2": "Setia Alam, 40170,",
            "daddress3": "Shah Alam, Selangor.",
            "dpostcode": "40170",
            "dcity": "Shah Alam",
            "dstate": "Selangor",
            "dcountry": "",
            "dphone1": "03-78901300",
            "sdsdocdetail": [
                {
                    "dtlkey": 19,
                    "seq": 1000,
                    "itemcode": "LD/Silver",
                    "location": "MAIN",
                    "project": "----",
                    "description": "Intelligent tracks lightcycle desk light (Silver)",
                    "description2": "Desk Light Silver",
                    "qty": "15",
                    "uom": "UNIT",
                    "rate": "1",
                    "suomqty": "0",
                    "unitprice": "650",
                    "deliverydate": "2025-06-14",
                    "disc": "",
                    "tax": "",
                    "taxrate": "",
                    "taxamt": "0.00",
                    "taxinclusive": False,
                    "amount": "9750",
                    "printable": True,
                    "transferable": True,
                    "udf_pqapproved": True,
                },
                {
                    "dtlkey": 20,
                    "seq": 2000,
                    "itemcode": "LD/White",
                    "location": "MAIN",
                    "project": "----",
                    "description": "Intelligent tracks lightcycle desk light (White)",
                    "description2": "Desk Light White",
                    "qty": "5",
                    "uom": "UNIT",
                    "rate": "1",
                    "suomqty": "0",
                    "unitprice": "650",
                    "deliverydate": "2025-06-14",
                    "disc": "",
                    "tax": "",
                    "taxrate": "",
                    "taxamt": "0.00",
                    "taxinclusive": False,
                    "amount": "3250",
                    "printable": True,
                    "transferable": True,
                    "udf_pqapproved": True,
                },
            ],
        }
        self.supplier = {
            "code": "400-I0001",
            "companyname": "ITALY BEDDING DESIGN & SUPPLY",
            "address1": "25, Brickfields,",
            "address2": "50470, KL",
            "country": "",
            "phone1": "012-5581200",
            "attention": "Ms. Rayshariz",
            "terms": "30 Days",
            "branchname": "BILLING",
        }
        self.table_columns = {
            "PH_PO": {
                "DOCKEY", "DOCNO", "DOCNOEX", "DOCDATE", "POSTDATE", "TAXDATE", "CODE", "COMPANYNAME",
                "ADDRESS1", "ADDRESS2", "COUNTRY", "PHONE1", "ATTENTION", "AREA", "AGENT", "PROJECT", "TERMS",
                "CURRENCYCODE", "CURRENCYRATE", "SHIPPER", "DESCRIPTION", "CANCELLED", "STATUS", "DOCAMT",
                "LOCALDOCAMT", "BRANCHNAME", "DADDRESS1", "DADDRESS2", "DADDRESS3", "DPOSTCODE", "DCITY",
                "DSTATE", "DCOUNTRY", "DPHONE1", "BUSINESSUNIT", "TRANSFERABLE", "UPDATECOUNT", "PRINTCOUNT",
                "LASTMODIFIED", "IDTYPE", "SUBMISSIONTYPE"
            },
            "PH_PODTL": {
                "DTLKEY", "DOCKEY", "SEQ", "ITEMCODE", "LOCATION", "PROJECT", "DESCRIPTION", "DESCRIPTION2",
                "QTY", "UOM", "RATE", "SQTY", "SUOMQTY", "OFFSETQTY", "UNITPRICE", "DELIVERYDATE", "DISC",
                "TAX", "TAXRATE", "TAXAMT", "LOCALTAXAMT", "TAXINCLUSIVE", "AMOUNT", "LOCALAMOUNT", "PRINTABLE",
                "FROMDOCTYPE", "FROMDOCKEY", "FROMDTLKEY", "TRANSFERABLE", "REMARK1", "REMARK2"
            },
            "ST_XTRANS": {
                "DOCKEY", "CODE", "FROMDOCTYPE", "TODOCTYPE", "FROMDOCKEY", "TODOCKEY", "FROMDTLKEY",
                "TODTLKEY", "QTY", "SQTY", "TOSTATUS"
            },
        }

    def _run_transfer(self, transfer_lines, existing_map=None):
        inserted = {"PH_PO": [], "PH_PODTL": [], "ST_XTRANS": []}
        next_keys = {
            "PH_PO": iter([101]),
            "PH_PODTL": iter([1001, 1002, 1003]),
            "ST_XTRANS": iter([9001, 9002, 9003]),
        }
        connection = _DummyConnection()

        def capture_insert(_cur, table_name, data, existing_columns):
            inserted[table_name].append({key: value for key, value in data.items() if key in existing_columns})

        with patch("utils.procurement_purchase_order_transfer._connect_db", return_value=connection), \
             patch("utils.procurement_purchase_order_transfer._get_table_columns", side_effect=lambda _cur, name: self.table_columns[name]), \
               patch("utils.procurement_purchase_order_transfer._get_string_column_lengths", return_value={}), \
             patch("utils.procurement_purchase_order_transfer._next_purchase_order_number", return_value="PO-20260423-0001"), \
             patch("utils.procurement_purchase_order_transfer._purchase_order_number_exists", return_value=False), \
             patch("utils.procurement_purchase_order_transfer._next_key", side_effect=lambda _cur, table_name, _key_col, _gens: next(next_keys[table_name])), \
             patch("utils.procurement_purchase_order_transfer._insert_dynamic", side_effect=capture_insert), \
             patch("utils.procurement_purchase_order_transfer._fetch_existing_transfer_qty_map", return_value=existing_map or {}), \
             patch("utils.procurement_purchase_order_transfer._column_is_numeric", return_value=True):
            result = transfer_purchase_request_to_po(
                self.purchase_request,
                transfer_lines,
                self.supplier,
                created_by="tester@example.com",
                transfer_date="2025-06-14",
            )

        return result, inserted, connection

    def test_transfer_inserts_po_header_details_and_xtrans(self):
        result, inserted, connection = self._run_transfer(
            [
                {"dtlkey": 19, "quantity": 7},
                {"dtlkey": 20, "quantity": 5},
            ]
        )

        self.assertTrue(connection.committed)
        self.assertEqual(result["poDockey"], 101)
        self.assertEqual(result["poNumber"], "PO-20260423-0001")
        self.assertEqual(len(inserted["PH_PO"]), 1)
        self.assertEqual(len(inserted["PH_PODTL"]), 2)
        self.assertEqual(len(inserted["ST_XTRANS"]), 2)

        header = inserted["PH_PO"][0]
        self.assertEqual(header["CODE"], "400-I0001")
        self.assertEqual(header["COMPANYNAME"], "ITALY BEDDING DESIGN & SUPPLY")
        self.assertEqual(header["DOCAMT"], 7800.0)

        first_detail = inserted["PH_PODTL"][0]
        self.assertEqual(first_detail["FROMDOCTYPE"], "PQ")
        self.assertEqual(first_detail["FROMDOCKEY"], 18)
        self.assertEqual(first_detail["FROMDTLKEY"], 19)
        self.assertEqual(first_detail["QTY"], 7.0)

        first_xtrans = inserted["ST_XTRANS"][0]
        self.assertEqual(first_xtrans["FROMDOCTYPE"], "PQ")
        self.assertEqual(first_xtrans["TODOCTYPE"], "PO")
        self.assertEqual(first_xtrans["FROMDOCKEY"], 18)
        self.assertEqual(first_xtrans["TODOCKEY"], 101)
        self.assertEqual(first_xtrans["FROMDTLKEY"], 19)
        self.assertEqual(first_xtrans["TODTLKEY"], 1001)
        self.assertEqual(first_xtrans["QTY"], 7.0)

    def test_transfer_allows_remaining_partial_quantity(self):
        result, inserted, connection = self._run_transfer(
            [{"dtlkey": 19, "quantity": 8}],
            existing_map={19: 7},
        )

        self.assertTrue(connection.committed)
        self.assertEqual(result["transferredQty"], 8.0)
        self.assertEqual(inserted["PH_PODTL"][0]["QTY"], 8.0)
        self.assertEqual(inserted["ST_XTRANS"][0]["QTY"], 8.0)

    def test_transfer_rejects_over_transfer_quantity(self):
        with self.assertRaises(PurchaseOrderTransferValidationError):
            self._run_transfer(
                [{"dtlkey": 19, "quantity": 9}],
                existing_map={19: 7},
            )


if __name__ == "__main__":
    unittest.main()