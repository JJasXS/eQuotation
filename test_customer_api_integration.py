"""Small integration tester for SQL Account customer API."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

import requests


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test /health and /customers endpoints for SQL Account COM middleware."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--code", default="", help="Customer code (auto-generated if empty)")
    parser.add_argument("--company-name", default="ABC Sdn Bhd", help="Company name")
    parser.add_argument("--credit-term", default="30", help="Credit term")
    parser.add_argument("--phone", default="0123456789", help="Phone number")
    parser.add_argument("--address1", default="Address line 1", help="Address line 1")
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip the /health request before posting customer.",
    )
    return parser


def pretty_print_response(title: str, response: requests.Response) -> None:
    print(f"\n=== {title} ===")
    print(f"HTTP {response.status_code}")
    print("Headers:")
    print(json.dumps(dict(response.headers), indent=2))

    print("Body:")
    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(response.text)


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    code = args.code or f"CUST{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return {
        "code": code,
        "company_name": args.company_name,
        "credit_term": args.credit_term,
        "phone": args.phone,
        "address1": args.address1,
    }


def main() -> int:
    args = build_parser().parse_args()
    base_url = args.base_url.rstrip("/")
    health_url = f"{base_url}/health"
    customer_url = f"{base_url}/customers"
    payload = build_payload(args)

    print("SQL Account COM Middleware Integration Test")
    print(f"Base URL: {base_url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")

    try:
        if not args.skip_health:
            health_resp = requests.get(health_url, timeout=15)
            pretty_print_response("GET /health", health_resp)

        create_resp = requests.post(customer_url, json=payload, timeout=30)
        pretty_print_response("POST /customers", create_resp)

        if create_resp.ok:
            print("\nResult: SUCCESS - Customer create request accepted.")
            return 0

        print("\nResult: FAILED - API returned an error status.")
        return 1
    except requests.RequestException as exc:
        print(f"\nRequest failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
