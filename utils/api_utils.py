"""API utility functions for external API calls."""
import requests

# API configuration (will be set from main.py)
BASE_API_URL = None
ENDPOINT_PATHS = {}


def set_api_config(base_url, endpoint_paths):
    """Set API configuration."""
    global BASE_API_URL, ENDPOINT_PATHS
    BASE_API_URL = base_url
    ENDPOINT_PATHS = endpoint_paths


def fetch_data_from_api(endpoint_key):
    """Fetch data from a configured API endpoint."""
    path = ENDPOINT_PATHS.get(endpoint_key)
    if not path:
        print(f"No path configured for endpoint: {endpoint_key}")
        return []
    url = f"{BASE_API_URL}{path}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code >= 400:
            preview = (response.text or '').strip().replace('\n', ' ')[:240]
            print(f"API HTTP error for {endpoint_key}: {response.status_code} | {preview}")
            return []
        try:
            data = response.json()
        except ValueError:
            preview = (response.text or '').strip().replace('\n', ' ')[:240]
            print(f"API non-JSON response for {endpoint_key}: {preview}")
            return []
        if data.get('success'):
            return data.get('data', [])
        else:
            print(f"API error for {endpoint_key}:", data.get('error'))
            return []
    except Exception as e:
        print(f"Failed to fetch from API {endpoint_key}:", e)
        return []


def format_rm(value):
    """Format value as Malaysian Ringgit (RM)."""
    if value is None:
        return "-"
    try:
        numeric_value = float(str(value).replace(',', '').strip())
        return f"RM {numeric_value:.2f}"
    except (ValueError, TypeError):
        raw_value = str(value).strip()
        return f"RM {raw_value}" if raw_value else "-"
