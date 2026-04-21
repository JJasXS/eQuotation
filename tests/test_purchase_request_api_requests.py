"""API smoke tests for create purchase request endpoint.

Usage:
    python tests/test_purchase_request_api_requests.py
"""
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("FLASK_BASE_URL", "http://localhost:5000")


def print_response(resp: requests.Response, label: str) -> None:
    print("\n" + "=" * 64)
    print(label)
    print("=" * 64)
    print("HTTP", resp.status_code)
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text)


def create_purchase_request() -> None:
    payload = {
        "requesterId": "U001",
        "departmentId": "IT",
        "costCenter": "IT-OPS",
        "supplierId": "SUP-001",
        "currency": "MYR",
        "requestDate": "2026-04-21",
        "requiredDate": "2026-04-29",
        "justification": "Quarterly hardware refresh",
        "deliveryLocation": "HQ Main Store",
        "notes": "High priority for onboarding",
        "status": "SUBMITTED",
        "totalAmount": 2180.0,
        "lineItems": [
            {
                "itemCode": "ITM-LAP-001",
                "itemName": "Business Laptop",
                "description": "14 inch business laptop",
                "quantity": 2,
                "unitPrice": 1000,
                "tax": 180,
                "amount": 2180,
            }
        ],
    }

    resp = requests.post(
        f"{BASE_URL}/api/admin/procurement/purchase-requests",
        json=payload,
        timeout=15,
    )
    print_response(resp, "POST /api/admin/procurement/purchase-requests")


if __name__ == "__main__":
    create_purchase_request()
