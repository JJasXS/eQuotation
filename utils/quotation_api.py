"""Quotation API orchestration helpers.

These functions encapsulate the request payload mapping and PHP endpoint calls
for quotation create/update and draft save flows.
"""

import json

import requests


def _decode_php_json_response(response, endpoint_path):
    """Parse JSON from PHP; return a dict or a failed-result dict if body is empty/HTML."""
    text = (response.text or "").strip()
    if not text:
        return {
            "success": False,
            "error": (
                f"Empty response from {endpoint_path} (HTTP {response.status_code}). "
                "Check that Apache/PHP is running and BASE_API_URL points at your web root."
            ),
        }
    try:
        return response.json()
    except json.JSONDecodeError:
        snippet = text[:400].replace("\n", " ")
        return {
            "success": False,
            "error": (
                f"Non-JSON response from {endpoint_path} (HTTP {response.status_code}): {snippet}"
            ),
        }


def create_or_update_quotation(base_api_url, customer_code, data):
    """Create or update a quotation via PHP endpoints.

    Returns a dict from the PHP JSON body, or ``{'success': False, 'error': ...}``
    if the response is empty or not valid JSON.
    """
    dockey = data.get('dockey')

    if dockey:
        response = requests.post(
            f"{base_api_url}/php/updateDraftQuotation.php",
            json={
                "dockey": dockey,
                "description": (data.get('description', '') or '').strip(),
                "validUntil": data.get('validUntil', ''),
                "companyName": data.get('companyName', ''),
                "address1": data.get('address1', ''),
                "address2": data.get('address2', ''),
                "phone1": data.get('phone1', ''),
                "items": data.get('items', []),
            },
            timeout=10,
        )
        return _decode_php_json_response(response, "updateDraftQuotation.php")

    response = requests.post(
        f"{base_api_url}/php/insertQuotationToAccounting.php",
        json={
            "customerCode": customer_code,
            "description": (data.get('description', '') or '').strip(),
            "validUntil": data.get('validUntil', ''),
            "currencyCode": data.get('currencyCode', 'MYR'),
            "companyName": data.get('companyName', ''),
            "address1": data.get('address1', ''),
            "address2": data.get('address2', ''),
            "phone1": data.get('phone1', ''),
            "draftDockey": data.get('draftDockey'),
            "items": data.get('items', []),
        },
        timeout=10,
    )
    return _decode_php_json_response(response, "insertQuotationToAccounting.php")


def save_draft_quotation(base_api_url, customer_code, data):
    """Save a quotation draft via PHP endpoint.

    Returns a dict from the PHP JSON body, or ``{'success': False, 'error': ...}``
    if the response is empty or not valid JSON.
    """
    payload = {
        "dockey": data.get('dockey'),
        "customerCode": customer_code,
        "description": (data.get('description', '') or '').strip() or 'Draft Quotation',
        "validUntil": data.get('validUntil', ''),
        "currencyCode": data.get('currencyCode', 'MYR'),
        "companyName": data.get('companyName', ''),
        "address1": data.get('address1', ''),
        "address2": data.get('address2', ''),
        "phone1": data.get('phone1', ''),
        "items": data.get('items', []),
    }

    response = requests.post(
        f"{base_api_url}/php/saveDraftQuotation.php",
        json=payload,
        timeout=10,
    )
    return _decode_php_json_response(response, "saveDraftQuotation.php")
