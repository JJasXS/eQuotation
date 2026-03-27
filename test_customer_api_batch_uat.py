"""Batch UAT tester for /customers rejection and insert behavior."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

import requests


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run batch payload tests against SQL Account customer API."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument(
        "--only-valid",
        action="store_true",
        help="Run only the valid insert payload test.",
    )
    parser.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip GET /health before running batch tests.",
    )
    return parser


def print_response_block(case_name: str, payload: dict[str, Any], response: requests.Response) -> None:
    print(f"\n=== {case_name} ===")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    print(f"HTTP {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(response.text)


def make_test_cases() -> list[tuple[str, dict[str, Any], str]]:
    """
    Returns:
        list of (case_name, payload, expected_behavior)
    """
    code = f"UAT{datetime.now().strftime('%Y%m%d%H%M%S')}"
    valid = {
        "code": code,
        "company_name": "UAT Customer Sdn Bhd",
        "credit_term": "30",
        "phone": "0123456789",
        "address1": "Address line 1",
    }
    return [
        ("VALID_INSERT", valid, "Expect 201 if COM + DAL accepts"),
        (
            "MISSING_CODE",
            {k: v for k, v in valid.items() if k != "code"},
            "Expect 422 validation error",
        ),
        (
            "EMPTY_COMPANY_NAME",
            {**valid, "code": f"{code}A", "company_name": ""},
            "Expect 422 validation error",
        ),
        (
            "EMPTY_CREDIT_TERM",
            {**valid, "code": f"{code}B", "credit_term": ""},
            "Expect 422 validation error",
        ),
        (
            "MINIMAL_REQUIRED_ONLY",
            {
                "code": f"{code}C",
                "company_name": "Minimal Test",
                "credit_term": "30",
            },
            "Expect 201 or DAL rejection depending on SQL Account requirements",
        ),
    ]


def main() -> int:
    args = build_parser().parse_args()
    base_url = args.base_url.rstrip("/")
    health_url = f"{base_url}/health"
    customers_url = f"{base_url}/customers"

    print("Batch UAT: SQL Account COM customer API")
    print(f"Base URL: {base_url}")

    try:
        if not args.skip_health:
            print("\n=== HEALTH_CHECK ===")
            health_resp = requests.get(health_url, timeout=15)
            print(f"HTTP {health_resp.status_code}")
            try:
                print(json.dumps(health_resp.json(), indent=2, ensure_ascii=False))
            except ValueError:
                print(health_resp.text)
    except requests.RequestException as exc:
        print(f"\nHealth check failed: {exc}")
        return 2

    cases = make_test_cases()
    if args.only_valid:
        cases = [cases[0]]

    pass_count = 0
    fail_count = 0

    for case_name, payload, expected in cases:
        print(f"\nExpected: {expected}")
        try:
            resp = requests.post(customers_url, json=payload, timeout=30)
            print_response_block(case_name, payload, resp)
            if resp.status_code < 400:
                pass_count += 1
            else:
                fail_count += 1
        except requests.RequestException as exc:
            fail_count += 1
            print(f"\n=== {case_name} ===")
            print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
            print(f"Request failed: {exc}")

    print("\n=== BATCH SUMMARY ===")
    print(f"Success responses: {pass_count}")
    print(f"Error responses: {fail_count}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
