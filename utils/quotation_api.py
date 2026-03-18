"""Quotation API orchestration helpers.

These functions encapsulate the request payload mapping and PHP endpoint calls
for quotation create/update and draft save flows.
"""

import requests


def create_or_update_quotation(base_api_url, customer_code, data):
    """Create or update a quotation via PHP endpoints.

    Returns the decoded JSON payload from the PHP endpoint.
    Raises exceptions from requests/json parsing to the caller.
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
        return response.json()

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
    return response.json()


def save_draft_quotation(base_api_url, customer_code, data):
    """Save a quotation draft via PHP endpoint.

    Returns the decoded JSON payload from the PHP endpoint.
    Raises exceptions from requests/json parsing to the caller.
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
    return response.json()
