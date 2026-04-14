"""Check whether dropdown stock items can resolve a price.

This script mirrors the matching behavior used by /api/get_product_price:
- Exact match by DESCRIPTION (case-insensitive)
- Exact match by CODE (case-insensitive)
- Fuzzy fallback on DESCRIPTION (default threshold: 0.85)

Usage:
    python check_dropdown_item_prices.py
    python check_dropdown_item_prices.py --threshold 0.9 --limit 50
"""

import argparse
import csv
import os
from difflib import SequenceMatcher

from dotenv import load_dotenv
import fdb
import requests

from config.endpoints_config import BASE_API_URL as DEFAULT_BASE_API_URL
from config.endpoints_config import ENDPOINT_PATHS


def build_firebird_dsn(db_path, db_host=None):
    if not db_path:
        raise ValueError("DB_PATH is not configured.")

    cleaned_path = db_path.strip()
    cleaned_host = (db_host or "").strip()
    if not cleaned_host:
        return cleaned_path
    normalized_path = cleaned_path.replace("\\", "/")
    return f"{cleaned_host}:{normalized_path}"


def get_db_connection(db_path, db_user, db_password, db_host=""):
    return fdb.connect(
        dsn=build_firebird_dsn(db_path, db_host),
        user=db_user,
        password=db_password,
        charset="UTF8",
    )


def fetch_data_from_api(base_api_url, endpoint_paths, endpoint_key):
    path = endpoint_paths.get(endpoint_key)
    if not path:
        print(f"No path configured for endpoint: {endpoint_key}")
        return []

    url = f"{base_api_url}{path}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code >= 400:
            preview = (response.text or "").strip().replace("\n", " ")[:240]
            print(f"API HTTP error for {endpoint_key}: {response.status_code} | {preview}")
            return []

        data = response.json()
        if data.get("success"):
            return data.get("data", [])

        print(f"API error for {endpoint_key}: {data.get('error')}")
        return []
    except Exception as exc:
        print(f"Failed to fetch from API {endpoint_key}: {exc}")
        return []


def normalize_text(value):
    if value is None:
        return ""
    return str(value).strip()


def get_dropdown_items(db_path, db_user, db_password, db_host):
    con = None
    cur = None
    items = []
    try:
        con = get_db_connection(db_path, db_user, db_password, db_host)
        cur = con.cursor()
        cur.execute(
            """
            SELECT TRIM(RF.RDB$FIELD_NAME)
            FROM RDB$RELATION_FIELDS RF
            WHERE RF.RDB$RELATION_NAME = 'ST_ITEM'
            """
        )
        existing_columns = {normalize_text(r[0]) for r in (cur.fetchall() or []) if r and r[0]}

        selected_columns = ["CODE", "DESCRIPTION"]
        include_stdprice = "UDF_STDPRICE" in existing_columns
        if include_stdprice:
            selected_columns.append("UDF_STDPRICE")

        cur.execute(f"SELECT {', '.join(selected_columns)} FROM ST_ITEM")
        rows = cur.fetchall() or []
        for row in rows:
            code = normalize_text(row[0])
            desc = normalize_text(row[1])
            std_price = row[2] if include_stdprice and len(row) > 2 else None
            items.append({"CODE": code, "DESCRIPTION": desc, "UDF_STDPRICE": std_price})
    finally:
        if cur:
            cur.close()
        if con:
            con.close()
    return items


def find_price_match(item, stock_prices, desc_lookup, code_lookup, threshold):
    item_code = normalize_text(item.get("CODE"))
    item_desc = normalize_text(item.get("DESCRIPTION"))

    desc_key = item_desc.lower()
    code_key = item_code.lower()

    if desc_key and desc_key in desc_lookup:
        return "exact_description", desc_lookup[desc_key], 1.0

    if code_key and code_key in code_lookup:
        return "exact_code", code_lookup[code_key], 1.0

    if not item_desc:
        return "no_description", None, 0.0

    best_ratio = 0.0
    best_item = None
    for candidate in stock_prices:
        candidate_desc = normalize_text(candidate.get("DESCRIPTION"))
        if not candidate_desc:
            continue
        ratio = SequenceMatcher(None, item_desc.lower(), candidate_desc.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_item = candidate

    if best_item is not None and best_ratio >= threshold:
        return "fuzzy", best_item, best_ratio

    return "not_found", None, best_ratio


def build_lookup(stock_prices):
    desc_lookup = {}
    code_lookup = {}

    for entry in stock_prices:
        desc = normalize_text(entry.get("DESCRIPTION")).lower()
        code = normalize_text(entry.get("CODE")).lower()
        if desc and desc not in desc_lookup:
            desc_lookup[desc] = entry
        if code and code not in code_lookup:
            code_lookup[code] = entry

    return desc_lookup, code_lookup


def main():
    parser = argparse.ArgumentParser(description="Validate dropdown items against stock price source.")
    parser.add_argument("--threshold", type=float, default=0.85, help="Fuzzy match threshold (default: 0.85)")
    parser.add_argument("--limit", type=int, default=30, help="How many missing rows to print (default: 30)")
    parser.add_argument("--csv", default="reports/dropdown_price_check.csv", help="CSV output path")
    args = parser.parse_args()

    load_dotenv()

    base_api_url = os.getenv("BASE_API_URL", DEFAULT_BASE_API_URL).rstrip("/")
    db_path = os.getenv("DB_PATH")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST", "")

    if not db_path or not db_user or not db_password:
        raise RuntimeError("Missing DB env vars. Required: DB_PATH, DB_USER, DB_PASSWORD")

    dropdown_items = get_dropdown_items(db_path, db_user, db_password, db_host)
    stock_prices = fetch_data_from_api(base_api_url, ENDPOINT_PATHS, "stockitemprice")

    print(f"Loaded dropdown items: {len(dropdown_items)}")
    print(f"Loaded stock price entries: {len(stock_prices)}")

    if not dropdown_items:
        print("No dropdown items found in ST_ITEM.")
        return

    if not stock_prices:
        print("No stock prices loaded from API endpoint 'stockitemprice'.")
        local_with_price = [
            i for i in dropdown_items
            if i.get("UDF_STDPRICE") is not None and str(i.get("UDF_STDPRICE")).strip() not in ("", "0", "0.0")
        ]
        local_missing_price = [i for i in dropdown_items if i not in local_with_price]
        print(f"Local ST_ITEM.UDF_STDPRICE present: {len(local_with_price)}")
        print(f"Local ST_ITEM.UDF_STDPRICE missing/zero: {len(local_missing_price)}")
        for item in local_missing_price[: max(0, args.limit)]:
            print(f"- CODE={normalize_text(item.get('CODE'))} | DESCRIPTION={normalize_text(item.get('DESCRIPTION'))}")
        return

    desc_lookup, code_lookup = build_lookup(stock_prices)

    rows = []
    counts = {
        "exact_description": 0,
        "exact_code": 0,
        "fuzzy": 0,
        "no_description": 0,
        "not_found": 0,
    }

    for item in dropdown_items:
        match_type, matched_price, ratio = find_price_match(
            item, stock_prices, desc_lookup, code_lookup, args.threshold
        )
        counts[match_type] = counts.get(match_type, 0) + 1

        rows.append(
            {
                "item_code": normalize_text(item.get("CODE")),
                "item_description": normalize_text(item.get("DESCRIPTION")),
                "match_type": match_type,
                "match_ratio": f"{ratio:.4f}",
                "matched_code": normalize_text(matched_price.get("CODE")) if matched_price else "",
                "matched_description": normalize_text(matched_price.get("DESCRIPTION")) if matched_price else "",
                "stock_value": normalize_text(matched_price.get("STOCKVALUE")) if matched_price else "",
            }
        )

    os.makedirs(os.path.dirname(args.csv), exist_ok=True)
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "item_code",
                "item_description",
                "match_type",
                "match_ratio",
                "matched_code",
                "matched_description",
                "stock_value",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print("\nSummary")
    print("-------")
    for key in ["exact_description", "exact_code", "fuzzy", "no_description", "not_found"]:
        print(f"{key}: {counts.get(key, 0)}")

    missing = [r for r in rows if r["match_type"] in ("no_description", "not_found")]
    print(f"\nMissing price matches: {len(missing)}")
    for row in missing[: max(0, args.limit)]:
        print(f"- CODE={row['item_code']} | DESCRIPTION={row['item_description']} | match={row['match_type']}")

    print(f"\nCSV report written to: {args.csv}")


if __name__ == "__main__":
    main()
