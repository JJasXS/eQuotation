"""Unit tests for purchase request validation and lifecycle service."""
import os
import tempfile
import unittest

from utils.procurement_purchase_request import (
    PurchaseRequestValidationError,
    create_purchase_request,
    ensure_purchase_request_schema,
    transition_purchase_request_status,
)


class PurchaseRequestServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        os.environ["PROCUREMENT_SQLITE_DB"] = self.tmp.name
        os.environ["PROCUREMENT_CREATE_DEFAULT_SUBMITTED"] = "false"
        os.environ.pop("PROCUREMENT_CREATE_PR_URL", None)
        ensure_purchase_request_schema()

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except Exception:
            pass

    def test_create_draft_success(self):
        payload = {
            "requesterId": "U001",
            "departmentId": "IT",
            "currency": "MYR",
            "requestDate": "2026-04-21",
            "requiredDate": "2026-04-23",
            "totalAmount": 110.0,
            "lineItems": [
                {
                    "itemCode": "I001",
                    "itemName": "Laptop",
                    "description": "Business laptop",
                    "quantity": 1,
                    "unitPrice": 100,
                    "tax": 10,
                    "amount": 110,
                }
            ],
        }
        result = create_purchase_request(payload, created_by="tester@example.com")
        self.assertEqual(result["status"], "DRAFT")
        self.assertTrue(result["requestNumber"].startswith("PR-"))

    def test_validation_rejects_invalid_dates(self):
        payload = {
            "requesterId": "U001",
            "departmentId": "IT",
            "requestDate": "2026-04-25",
            "requiredDate": "2026-04-24",
            "totalAmount": 10,
            "lineItems": [
                {
                    "itemCode": "I001",
                    "itemName": "Mouse",
                    "quantity": 1,
                    "unitPrice": 10,
                    "tax": 0,
                    "amount": 10,
                }
            ],
        }
        with self.assertRaises(PurchaseRequestValidationError):
            create_purchase_request(payload, created_by="tester@example.com")

    def test_status_transition_happy_path(self):
        payload = {
            "requesterId": "U002",
            "departmentId": "FIN",
            "requestDate": "2026-04-21",
            "requiredDate": "2026-04-25",
            "totalAmount": 20,
            "lineItems": [
                {
                    "itemCode": "I003",
                    "itemName": "Keyboard",
                    "quantity": 1,
                    "unitPrice": 20,
                    "tax": 0,
                    "amount": 20,
                }
            ],
        }
        created = create_purchase_request(payload, created_by="tester@example.com")
        request_number = created["requestNumber"]

        submitted = transition_purchase_request_status(request_number, "SUBMITTED", "approver@example.com")
        self.assertEqual(submitted["status"], "SUBMITTED")

        approved = transition_purchase_request_status(request_number, "APPROVED", "approver@example.com")
        self.assertEqual(approved["status"], "APPROVED")


if __name__ == "__main__":
    unittest.main()
