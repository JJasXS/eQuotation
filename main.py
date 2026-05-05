# DEBUG: Confirm Flask main.py is running
print("[DEBUG] main.py loaded and Flask is starting...", flush=True)
import csv
import json
import os
import math
import time
from functools import wraps
from datetime import datetime, timedelta
import threading
import re
import random
import string
from difflib import SequenceMatcher
import traceback
from urllib.parse import quote
from flask import Flask, render_template, request, jsonify, session, redirect
import fdb
import openai
import requests
from dotenv import load_dotenv
from db_initializer import initialize_database, sync_st_xtrans_suomqty_from_st_tr_udf
from api.services.local_customer_sync import LocalCustomerSyncRequest, sync_local_customer_fields

# Import utility modules
from utils import (
    get_db_connection, user_owns_chat, get_chat_history, update_chat_last_message, insert_chat_message_local,
    get_active_order, test_firebird_connection, set_db_config, build_firebird_dsn,
    fetch_data_from_api, format_rm, set_api_config,
    load_typo_corrections, normalize_intent_text, contains_intent_phrase,
    parse_order_intent, set_text_config,
    send_email, set_email_config,
    chat_with_gpt, detect_intent_hybrid, load_chatbot_instructions,
    set_ai_config, init_local_classifier,
    extract_product_and_quantity, get_product_price, set_order_config,
    resolve_numbered_reference, get_selling_price,
    create_or_update_quotation, save_draft_quotation
)
from utils.procurement_stock_card_queries import (
    fetch_procurement_metric_breakdown,
    fetch_procurement_stock_card_data,
    fetch_st_tr_udf_suomqty_summary,
)
from utils.procurement_purchase_request import (
    PurchaseRequestValidationError,
    create_purchase_request,
    normalize_purchase_request_status_input,
    peek_purchase_request_status_by_request_number,
    preview_purchase_request_number,
    transition_purchase_request_status,
    update_purchase_request,
)
from utils.procurement_purchase_order_transfer import (
    PurchaseOrderTransferValidationError,
    transfer_purchase_request_to_po,
)
from utils.procurement_bidding import (
    apply_awarded_lines_to_request,
    BiddingValidationError,
    _normalize_supplier_rows,
    approve_bid,
    create_bid_invitations,
    get_supplier_bid_snapshot,
    get_transfer_gate_state,
    list_bids_for_request,
    list_supplier_invitations,
    map_approved_bid_suppliers_by_request_ids,
    map_awarded_suppliers_by_request_ids,
    reject_bid,
    save_line_awards,
    submit_supplier_bid,
    supplier_has_active_bid_invitation,
    validate_transfer_against_line_awards,
)
from utils.role_permissions import (
    ACCESS_TIER_FULL_ADMIN,
    ACCESS_TIER_NO_ROLE,
    ACCESS_TIER_PURCH_MGMT,
    ACCESS_TIER_PURCH_STAFF,
    ACCESS_TIER_SALES_MGMT,
    ACCESS_TIER_SALES_STAFF,
    ACCESS_TIER_SUPPLIER,
    can_access_admin_dashboard,
    can_access_admin_view_quotations,
    can_access_create_quotation,
    can_access_pending_approvals_admin,
    can_access_purchase_menu,
    can_access_view_quotation_customer_ui,
    can_patch_pr_workflow_status,
    can_update_pr_approvals_and_header_status,
    infer_access_tier_from_session,
    is_full_management_admin,
    template_permission_context,
)
from utils.sql_query_helpers import (
    fetch_stock_item_prices_for_chat,
    fetch_stock_items,
    find_customer_code_by_email,
    find_draft_order_id_by_chatid,
    find_price_seed_item,
    get_st_item_quotation_display_fields,
    get_st_item_udf_stdprice,
    has_user_draft_orders,
)

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# Import local AI models (optional - graceful fallback if not available)
# Note: This import can be slow on first run due to transformers/sklearn/scipy loading
try:
    from ai_models import IntentClassifier
    LOCAL_AI_ENABLED = True
    print("Local AI intent classifier enabled")
except (ImportError, Exception) as e:
    LOCAL_AI_ENABLED = False
    print("Local AI not available - using OpenAI only")
    if isinstance(e, ImportError):
        print("   Run: python training/train_intent_model.py to enable local AI")
    else:
        print(f"   Error loading AI models: {type(e).__name__}")
except KeyboardInterrupt:
    LOCAL_AI_ENABLED = False
    print("AI model import interrupted - using OpenAI only")
    print("   To disable AI models, rename/move the ai_models folder")

# Import validation functions
from validationSignIn import validate_registration_fields

# Import order management configuration
from config.order_config import (
    CREATE_ORDER_KEYWORDS, COMPLETE_ORDER_KEYWORDS, REMOVE_ORDER_KEYWORDS, ADD_ORDER_KEYWORDS, PRODUCT_EXTRACTION_KEYWORDS, MIN_PRODUCT_NAME_LENGTH, MIN_PRODUCT_CODE_LENGTH,
    QUANTITY_FILLER_WORDS, QUANTITY_FILLER_PATTERN, WELCOME_MESSAGE, SHOW_WELCOME_MESSAGE, HELP_MESSAGE, NUMBERED_REFERENCE_PATTERNS, ORDINAL_WORD_MAP,
    PRODUCT_PREFIX_PATTERN, FUZZY_MATCH_THRESHOLD, SUBSTRING_MATCH_BONUS, PRICE_MATCH_THRESHOLD,PRODUCT_EXTRACTION_VERBS
)

# Import OTP configuration
from config.otp_config import generate_otp, OTP_LENGTH, OTP_EXPIRY_SECONDS

# ============================================
# CONFIGURATION - Load from environment variables
# ============================================
BASE_API_URL = os.getenv('BASE_API_URL', 'http://localhost:8080').rstrip('/')
FASTAPI_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000').rstrip('/')

# Canonical procurement SPA URL (legacy typo /admin/precurement/precurement redirects here).
PROCUREMENT_UI_PATH = '/admin/procurement'
PROJECT_API_BASE_URL = os.getenv('PROJECT_API_BASE_URL', '').strip().rstrip('/')
FASTAPI_ACCESS_KEY = (os.getenv('API_ACCESS_KEY') or '').strip()
FASTAPI_SECRET_KEY = (os.getenv('API_SECRET_KEY') or '').strip()
GUEST_SIGNIN_ALLOW_LOCAL_FALLBACK = (os.getenv('GUEST_SIGNIN_ALLOW_LOCAL_FALLBACK', 'true').strip().lower() in ('1', 'true', 'yes', 'on'))
DB_PATH = os.getenv('DB_PATH')

# Runtime hints to avoid re-trying slow/invalid upstream variants on every request.
PURCHASE_REQUEST_LIST_ENDPOINT_HINT = None
PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT = None
PURCHASE_REQUEST_LIST_CACHE = {}
PURCHASE_REQUEST_LIST_CACHE_LOCK = threading.Lock()
PURCHASE_REQUEST_LIST_CACHE_TTL_SEC = 15.0
ADMIN_DASHBOARD_API_CACHE = {}
ADMIN_DASHBOARD_API_CACHE_LOCK = threading.Lock()
ADMIN_DASHBOARD_API_CACHE_TTL_SEC = 60.0
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER', 'sysdba')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'masterkey')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')

if not DB_PATH:
    raise ValueError("DB_PATH environment variable is not set. Please configure it in .env file.")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set. Please configure it in .env file.")

openai.api_key = OPENAI_API_KEY

# ============================================
# INITIALIZE UTILITY MODULES
# ============================================
# Configure database utils
DB_DSN = build_firebird_dsn(DB_PATH, DB_HOST)
set_db_config(DB_PATH, DB_USER, DB_PASSWORD, DB_HOST)


# Helper configuration (moved up to ensure ENDPOINT_PATHS is defined before use)
from config.endpoints_config import ENDPOINT_PATHS
set_api_config(BASE_API_URL, ENDPOINT_PATHS)


def _dashboard_cache_get(key):
    with ADMIN_DASHBOARD_API_CACHE_LOCK:
        cached = ADMIN_DASHBOARD_API_CACHE.get(key)
    if not cached:
        return None
    cached_at, payload = cached
    if (time.perf_counter() - cached_at) > ADMIN_DASHBOARD_API_CACHE_TTL_SEC:
        with ADMIN_DASHBOARD_API_CACHE_LOCK:
            ADMIN_DASHBOARD_API_CACHE.pop(key, None)
        return None
    out = json.loads(json.dumps(payload, default=str))
    out.setdefault('perf', {})['cacheHit'] = True
    out['perf']['cacheAgeMs'] = round((time.perf_counter() - cached_at) * 1000, 1)
    return out


def _dashboard_cache_set(key, payload):
    with ADMIN_DASHBOARD_API_CACHE_LOCK:
        if len(ADMIN_DASHBOARD_API_CACHE) >= 12:
            oldest_key = min(ADMIN_DASHBOARD_API_CACHE, key=lambda k: ADMIN_DASHBOARD_API_CACHE[k][0])
            ADMIN_DASHBOARD_API_CACHE.pop(oldest_key, None)
        ADMIN_DASHBOARD_API_CACHE[key] = (time.perf_counter(), payload)


# Configure email utils
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_EMAIL = os.getenv('SMTP_EMAIL', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
set_email_config(SMTP_SERVER, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD)

# Configure AI utils
set_ai_config(OPENAI_API_KEY, OPENAI_MODEL)
init_local_classifier(LOCAL_AI_ENABLED)

# ============================================
# OTP STORAGE & CONFIGURATION
# ============================================
# In-memory OTP storage: { "email|login_mode": {'otp': code, 'expiry': datetime} }
OTP_STORAGE = {}

# Helper configuration
from config.endpoints_config import ENDPOINT_PATHS
MAX_HISTORY_MESSAGES = 50
CHATBOT_SYSTEM_INSTRUCTIONS = load_chatbot_instructions()

# Helper function for chat messaging (Firebird — must match get_chat_history for pagination)
def insert_chat_message(chatid, sender, messagetext):
    insert_chat_message_local(chatid, sender, messagetext)


def require_api_auth(admin_only=False, unauth_message='Not authenticated', forbidden_message='Forbidden'):
    """Return a Flask error response tuple when auth/role checks fail; otherwise return None."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': unauth_message}), 401
    if admin_only and session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': forbidden_message}), 403
    return None


def api_login_required(unauth_message='Unauthorized'):
    """Decorator for API endpoints that require a logged-in user."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            auth_error = require_api_auth(unauth_message=unauth_message)
            if auth_error:
                return auth_error
            return func(*args, **kwargs)
        return wrapper
    return decorator


def api_admin_required(unauth_message='Unauthorized', forbidden_message='Forbidden'):
    """Decorator for API endpoints that require admin privileges."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            auth_error = require_api_auth(
                admin_only=True,
                unauth_message=unauth_message,
                forbidden_message=forbidden_message
            )
            if auth_error:
                return auth_error
            return func(*args, **kwargs)
        return wrapper
    return decorator


def proxy_json_request(method, path, payload=None, params=None, timeout=10):
    """Forward a request to a PHP endpoint and return JSON body/status."""
    url = f"{BASE_API_URL}{path}"
    response = requests.request(method=method, url=url, json=payload, params=params, timeout=timeout)
    return response.json(), response.status_code


def proxy_post_with_auth(
    path,
    *,
    admin_only=False,
    error_message='Failed to process request',
    log_context='request',
    timeout_message=None,
    connection_message=None,
    include_exception_detail=False,
):
    """Proxy authenticated POST requests with consistent payload handling and errors."""
    auth_error = require_api_auth(admin_only=admin_only)
    if auth_error:
        return auth_error

    payload = request.get_json() or {}
    try:
        return proxy_json_request('POST', path, payload=payload)
    except requests.exceptions.Timeout:
        print(f"Timeout connecting to XAMPP at {BASE_API_URL}")
        return jsonify({'success': False, 'error': timeout_message or error_message}), 500
    except requests.exceptions.ConnectionError:
        print(f"Connection error to XAMPP at {BASE_API_URL}")
        return jsonify({'success': False, 'error': connection_message or error_message}), 500
    except Exception as e:
        print(f"Error proxying {log_context} to XAMPP: {e}")
        final_error = f'{error_message}: {str(e)}' if include_exception_detail else error_message
        return jsonify({'success': False, 'error': final_error}), 500


def proxy_get_with_auth(path, *, params=None, admin_only=False, error_message='Failed to fetch data', log_context='request'):
    """Proxy authenticated GET requests with consistent error handling."""
    auth_error = require_api_auth(admin_only=admin_only)
    if auth_error:
        return auth_error

    try:
        return proxy_json_request('GET', path, params=params)
    except Exception as e:
        print(f"Error proxying {log_context} to XAMPP: {e}")
        return jsonify({'success': False, 'error': error_message}), 500


def run_firebird_sql_script(sql_file_path, db_path, db_user, db_password):
    """Execute a Firebird SQL script file at startup with safe ignore handling."""
    if not os.path.exists(sql_file_path):
        print(f"[SQL STARTUP] Script not found: {sql_file_path}")
        return

    try:
        with open(sql_file_path, 'r', encoding='utf-8') as handle:
            raw_sql = handle.read()
    except Exception as exc:
        print(f"[SQL STARTUP] Failed to read script {sql_file_path}: {exc}")
        return

    # Remove block comments and split by semicolon for statement execution.
    sql_without_comments = re.sub(r'/\*.*?\*/', '', raw_sql, flags=re.DOTALL)
    statements = [statement.strip() for statement in sql_without_comments.split(';') if statement.strip()]

    ignored_error_tokens = [
        'already exists', 'name in use', 'attempt to store duplicate value',
        'violation of primary or unique key constraint', 'unsuccessful metadata update'
    ]

    executed = 0
    ignored = 0
    failed = 0
    conn = None
    cur = None

    try:
        conn = fdb.connect(dsn=db_path, user=db_user, password=db_password, charset='UTF8')
        cur = conn.cursor()

        for statement in statements:
            normalized = re.sub(r'\s+', ' ', statement).strip().upper()

            if normalized.startswith('SET SQL DIALECT'):
                continue
            if normalized == 'COMMIT':
                conn.commit()
                continue

            try:
                cur.execute(statement)
                executed += 1
            except Exception as exc:
                error_text = str(exc).lower()
                if any(token in error_text for token in ignored_error_tokens):
                    ignored += 1
                    continue
                failed += 1
                print(f"[SQL STARTUP] Statement failed: {exc}")

        conn.commit()
        print(f"[SQL STARTUP] Applied {sql_file_path} (executed={executed}, ignored={ignored}, failed={failed})")
    except Exception as exc:
        print(f"[SQL STARTUP] Could not run script {sql_file_path}: {exc}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def require_page_access(
    require_admin=False,
    require_full_management_admin=False,
    block_admin=False,
    admin_redirect='/admin',
):
    """Return redirect response for unauthorized page access, or None if access is allowed."""
    if 'user_email' not in session:
        return redirect('/login')

    if infer_access_tier_from_session(session) == ACCESS_TIER_NO_ROLE:
        return redirect('/login')

    user_type = session.get('user_type')
    if require_full_management_admin:
        if not is_full_management_admin(session):
            return redirect('/admin')
        return None
    if require_admin and user_type != 'admin':
        return redirect('/chat')
    if block_admin and user_type == 'admin':
        return redirect(admin_redirect)
    return None


def _redirect_purchasing_roles_from_sales_analytics_pages():
    """Purchasing roles use procurement; block analytics/sales-only admin pages."""
    tier = session.get('access_tier')
    if tier in (ACCESS_TIER_PURCH_MGMT, ACCESS_TIER_PURCH_STAFF):
        return redirect(f'{PROCUREMENT_UI_PATH}?tab=view')
    return None


def render_protected_template(
    template_name,
    *,
    require_admin=False,
    require_full_management_admin=False,
    block_admin=False,
    admin_redirect='/admin',
    **context,
):
    """Render a template after applying shared page access checks and default session context."""
    page_error = require_page_access(
        require_admin=require_admin,
        require_full_management_admin=require_full_management_admin,
        block_admin=block_admin,
        admin_redirect=admin_redirect,
    )
    if page_error:
        return page_error

    template_context = {
        'user_email': session.get('user_email', ''),
        'user_type': session.get('user_type', ''),
    }
    template_context.update(template_permission_context(session))
    template_context.update(context)
    return render_template(template_name, **template_context)


def get_current_customer_code(*, resolve_missing=False):
    """Return current session customer code, optionally resolving it from AR_CUSTOMERBRANCH by user email."""
    customer_code = session.get('customer_code')
    if customer_code or not resolve_missing:
        return customer_code

    user_email = session.get('user_email')
    if not user_email:
        return None

    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute('SELECT CODE FROM AR_CUSTOMERBRANCH WHERE EMAIL = ?', (user_email,))
        row = cur.fetchone()
        if row and row[0]:
            customer_code = row[0]
            session['customer_code'] = customer_code
            return customer_code
        return None
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


def build_product_suggestions(search_term, candidates, price_lookup=None, require_price=True, threshold=0.3, limit=3):
    """Return top-N similar product suggestions as (description, formatted_price)."""
    matches = []
    term = (search_term or '').lower()
    for item in candidates:
        desc = item.get('DESCRIPTION', '')
        if not desc:
            continue

        desc_lower = desc.lower()
        ratio = SequenceMatcher(None, term, desc_lower).ratio()
        price = None
        if price_lookup:
            price = price_lookup.get(desc_lower)
        else:
            price = item.get('STOCKVALUE')

        matches.append((desc, ratio, price))

    matches.sort(key=lambda x: x[1], reverse=True)
    filtered = [m for m in matches if m[1] > threshold and (m[2] if require_price else True)]
    top_matches = filtered[:limit]
    return [(desc, format_rm(price)) for desc, _, price in top_matches]


CATALOG_QUERY_STOP_WORDS = {
    'a', 'an', 'and', 'any', 'are', 'available', 'can', 'category', 'categories',
    'do', 'for', 'give', 'have', 'i', 'in', 'is', 'items', 'list', 'me', 'of',
    'product', 'products', 'sell', 'show', 'stock', 'tell', 'the', 'there', 'type',
    'types', 'what', 'which', 'with', 'you', 'your'
}

GREETING_ONLY_TERMS = {
    'hi', 'hello', 'hey', 'yo', 'sup', 'morning', 'afternoon', 'evening',
    'goodmorning', 'goodafternoon', 'goodevening'
}

CATALOG_PAGE_SIZE = 8
SHOW_MORE_REQUEST_PHRASES = {
    'more', 'show more', 'more results', 'show more results', 'next', 'next page',
    'show next', 'show next page', 'see more', 'continue'
}
CATALOG_PAGE_REQUEST_PATTERN = re.compile(r'^(?:show\s+)?(?:go\s+to\s+)?page\s+(\d+)$')


def normalize_catalog_token(token):
    token = re.sub(r'[^a-z0-9]+', '', (token or '').lower())
    if len(token) > 4 and token.endswith('ies'):
        return token[:-3] + 'y'
    if len(token) > 4 and token.endswith('es'):
        return token[:-2]
    if len(token) > 3 and token.endswith('s'):
        return token[:-1]
    return token


def extract_catalog_terms(user_input):
    raw_terms = re.findall(r'[a-z0-9]+', (user_input or '').lower())
    terms = []
    for raw_term in raw_terms:
        if raw_term in CATALOG_QUERY_STOP_WORDS:
            continue
        normalized = normalize_catalog_token(raw_term)
        if len(normalized) < 2:
            continue
        terms.append(normalized)
    return terms


def is_greeting_only_message(user_input):
    tokens = [normalize_catalog_token(token) for token in re.findall(r'[a-z0-9]+', (user_input or '').lower())]
    tokens = [token for token in tokens if token]
    if not tokens:
        return False

    return all(token in GREETING_ONLY_TERMS for token in tokens)


def is_show_more_request(user_input):
    text = re.sub(r'\s+', ' ', (user_input or '').lower()).strip()
    return text in SHOW_MORE_REQUEST_PHRASES


def parse_catalog_page_request(user_input):
    text = re.sub(r'\s+', ' ', (user_input or '').lower()).strip()
    match = CATALOG_PAGE_REQUEST_PATTERN.match(text)
    if not match:
        return None

    page_number = int(match.group(1))
    return max(1, page_number)


def is_catalog_query(user_input):
    text = (user_input or '').lower().strip()
    if not text:
        return False

    if is_greeting_only_message(text):
        return False

    if is_show_more_request(text):
        return True

    if parse_catalog_page_request(text) is not None:
        return True

    catalog_phrases = [
        'what do you sell', 'what do u sell', 'what type', 'what types',
        'what category', 'what categories', 'what group', 'what groups',
        'show me', 'tell me', 'available', 'do you have', 'looking for',
        'search for', 'search the', 'look for', 'find ', 'lookup', 'look up',
        'item table', 'in the catalog', 'from the catalog',
    ]
    if any(phrase in text for phrase in catalog_phrases):
        return True

    return bool(extract_catalog_terms(text)) and len(text.split()) <= 16


def resolve_catalog_query_context(user_input, chat_history=None):
    requested_page = parse_catalog_page_request(user_input)
    if not is_show_more_request(user_input) and requested_page is None:
        return (user_input or '').strip(), 0, False

    history = chat_history or []
    latest_query = None
    latest_query_index = -1

    for index, msg in enumerate(history):
        sender = (msg.get('SENDER') or '').strip().lower()
        text = (msg.get('MESSAGETEXT') or '').strip()
        if sender != 'user' or not text:
            continue
        if is_show_more_request(text) or parse_catalog_page_request(text) is not None or not is_catalog_query(text):
            continue
        latest_query = text
        latest_query_index = index

    if latest_query is None:
        return None, 0, True

    if requested_page is not None:
        return latest_query, (requested_page - 1) * CATALOG_PAGE_SIZE, requested_page > 1

    prior_show_more_requests = 0
    for msg in history[latest_query_index + 1:]:
        sender = (msg.get('SENDER') or '').strip().lower()
        text = (msg.get('MESSAGETEXT') or '').strip()
        if sender == 'user' and is_show_more_request(text):
            prior_show_more_requests += 1

    return latest_query, (prior_show_more_requests + 1) * CATALOG_PAGE_SIZE, True


def match_catalog_items(user_input, stockitems, price_lookup=None, limit=None, offset=0):
    query = (user_input or '').lower().strip()
    terms = extract_catalog_terms(query)
    normalized_query = re.sub(r'\s+', ' ', query)
    matches = []

    for item in stockitems:
        description = (item.get('DESCRIPTION') or '').strip()
        stock_group = (item.get('STOCKGROUP') or '').strip()
        if not description:
            continue

        description_lower = description.lower()
        stock_group_lower = stock_group.lower()
        normalized_description = re.sub(r'\s+', ' ', description_lower)
        normalized_stock_group = re.sub(r'\s+', ' ', stock_group_lower)
        normalized_desc_tokens = {normalize_catalog_token(token) for token in re.findall(r'[a-z0-9]+', description_lower)}
        normalized_group_tokens = {normalize_catalog_token(token) for token in re.findall(r'[a-z0-9]+', stock_group_lower)}
        exact_description_match = bool(normalized_query) and normalized_description == normalized_query
        exact_group_match = bool(normalized_query) and normalized_stock_group == normalized_query
        starts_with_description = bool(normalized_query) and normalized_description.startswith(normalized_query)
        starts_with_group = bool(normalized_query) and normalized_stock_group.startswith(normalized_query)
        all_terms_in_description = bool(terms) and all(
            term in normalized_desc_tokens or term in description_lower for term in terms
        )
        all_terms_in_group = bool(terms) and all(
            term in normalized_group_tokens or term in stock_group_lower for term in terms
        )

        score = 0
        if query and query in description_lower:
            score += 8
        if query and query in stock_group_lower:
            score += 10
        if stock_group_lower and stock_group_lower in query:
            score += 6

        for term in terms:
            if term in normalized_group_tokens:
                score += 5
            elif term in normalized_desc_tokens:
                score += 4
            elif term in stock_group_lower:
                score += 3
            elif term in description_lower:
                score += 2

        if terms and all(term in (normalized_desc_tokens | normalized_group_tokens) or term in description_lower or term in stock_group_lower for term in terms):
            score += 4

        if exact_description_match:
            score += 20
        elif exact_group_match:
            score += 16
        elif starts_with_description:
            score += 8
        elif starts_with_group:
            score += 6

        if score <= 0:
            continue

        price = None
        if price_lookup:
            price = price_lookup.get(description_lower)

        matches.append((
            description,
            stock_group,
            score,
            price,
            exact_description_match,
            exact_group_match,
            starts_with_description,
            starts_with_group,
            all_terms_in_description,
            all_terms_in_group,
        ))

    matches.sort(key=lambda item: (
        -int(item[4]),
        -int(item[5]),
        -int(item[6]),
        -int(item[7]),
        -int(item[8]),
        -int(item[9]),
        -item[2],
        item[0]
    ))

    seen = set()
    deduped_results = []
    for description, stock_group, _, price, *_ in matches:
        if description.lower() in seen:
            continue
        seen.add(description.lower())
        deduped_results.append((description, stock_group, price))

    if offset:
        deduped_results = deduped_results[offset:]
    if limit is not None:
        deduped_results = deduped_results[:limit]

    return deduped_results


def build_catalog_response(user_input, stockitems, stock_groups, price_lookup, chat_history=None):
    if not is_catalog_query(user_input):
        return None

    resolved_query, offset, is_follow_up = resolve_catalog_query_context(user_input, chat_history)
    if resolved_query is None:
        return "I can show more results after a catalog search. Search for a product first, then use the arrow buttons under the result list."

    text = resolved_query.lower().strip()
    generic_group_request = any(phrase in text for phrase in [
        'what do you sell', 'what type', 'what types', 'what category',
        'what categories', 'what group', 'what groups'
    ])

    if generic_group_request:
        if not stock_groups:
            return 'No items found in the catalog right now.'

        lines = ['These are our available stock groups:', '']
        for index, stock_group in enumerate(stock_groups, start=1):
            lines.append(f'{index}. {stock_group}')
        lines.extend(['', 'Tell me a stock group or product keyword and I will show matching items.'])
        return '\n'.join(lines)

    all_matches = match_catalog_items(resolved_query, stockitems, price_lookup=price_lookup, limit=None, offset=0)
    visible_matches = [item for item in all_matches if item[2] is not None] or all_matches
    matches = visible_matches[offset:offset + CATALOG_PAGE_SIZE]
    display_matches = matches

    if display_matches:
        start_index = offset + 1
        end_index = offset + len(display_matches)
        total_matches = len(visible_matches)
        current_page = (offset // CATALOG_PAGE_SIZE) + 1
        heading = 'Here are more matching items I found in our catalog:' if is_follow_up else 'Here are the matching items I found in our catalog:'

        lines = [heading, '']
        for index, (description, _stock_group, price) in enumerate(display_matches, start=start_index):
            if price is not None:
                lines.append(f'{index}. {description} [PRODUCT: {description} | qty: 1]')
            else:
                lines.append(f'{index}. {description}')

        lines.extend(['', f'Showing {start_index}-{end_index} of {total_matches} matches.'])
        navigation_tags = []
        if current_page > 1:
            navigation_tags.append(f'[PAGE: {current_page - 1} | label: ⬅️]')
        if end_index < total_matches:
            navigation_tags.append(f'[PAGE: {current_page + 1} | label: ➡️]')
        else:
            lines.append('That is the end of the matching results for this search.')
        if navigation_tags:
            lines.append('Use the arrows below: ➡️ for next page, ⬅️ for previous page.')
            lines.extend(['', ' '.join(navigation_tags)])
        lines.extend(['', 'Let me know which item you want, or ask for a different keyword.'])
        return '\n'.join(lines)

    if is_follow_up and visible_matches:
        total_matches = len(visible_matches)
        total_pages = max(1, math.ceil(total_matches / CATALOG_PAGE_SIZE))
        return f"That page is out of range for this search. I found {total_matches} matching items across {total_pages} pages."

    suggestions = build_product_suggestions(
        resolved_query,
        stockitems,
        price_lookup=price_lookup,
        require_price=True,
        threshold=0.2,
        limit=5
    )
    if suggestions:
        lines = ['No item found for that search.', '', 'Here are some close matches from our catalog:', '']
        for index, (description, price) in enumerate(suggestions, start=1):
            lines.append(f'{index}. {description} [PRODUCT: {description} | qty: 1]')
        lines.extend(['', 'Try one of these or give me another keyword.'])
        return '\n'.join(lines)

    return 'No item found for that search in our catalog. Please try another product name or stock group.'


def add_order_item(orderid, product_info, unitprice):
    """Insert one order item and return a user-facing status message."""
    try:
        response = requests.post(
            f"{BASE_API_URL}/php/insertOrderDetail.php",
            json={
                "orderid": orderid,
                "description": product_info['description'],
                "qty": product_info['qty'],
                "unitprice": unitprice,
                "discount": 0
            }
        )
        data = response.json()
        if data.get('success'):
            total = format_rm(data.get('total'))
            return f"✓ Added {product_info['qty']}x {product_info['description']} → {total}\n\nWant more items or type 'Complete Order'?"
        return f"Error adding item: {data.get('error')}"
    except Exception as e:
        return f"Error adding item: {str(e)}"


def should_include_stock_context(user_input):
    """Only inject stock catalog context when a message is product/order related."""
    text = (user_input or '').lower()
    stock_terms = [
        'stock', 'price', 'pricing', 'product', 'item', 'catalog', 'available',
        'order', 'quotation', 'quote', 'buy', 'purchase', 'add', 'qty', 'quantity',
        'type', 'types', 'category', 'categories', 'group', 'groups', 'sell'
    ]
    return any(term in text for term in stock_terms)


def format_chatbot_response(text):
    """
    Format chatbot response to ensure proper line breaks in lists.
    Adds line breaks before numbered items (e.g., '7. Item') and bullet points.
    """
    import re
    
    # Handle intro line before numbered lists (e.g., "available: 1." -> "available:\n\n1.")
    text = re.sub(r'(:\s*)(\d+\.\s+[A-Z])', r'\1\n\n\2', text)
    
    # Most important: catch prices followed by numbered items
    # Pattern: "RM 250.00 2. Item" -> "RM 250.00\n2. Item"
    text = re.sub(r'(\d+\.\d+)\s+(\d+\.\s+)', r'\1\n\2', text)
    
    # Catch any remaining inline numbered items after non-whitespace
    # Pattern: "Lighting - RM 450.00" followed by "3. Item"
    text = re.sub(r'(\S)\s+(\d+\.\s+[A-Z])', r'\1\n\2', text)
    
    # Also catch after closing parens
    text = re.sub(r'(\))\s+(\d+\.\s+)', r'\1\n\2', text)
    
    # Ensure bullet points have line breaks
    text = re.sub(r'([^\n])\s+(-\s+[A-Z])', r'\1\n\2', text)
    
    # Clean up excessive line breaks (more than 2 in a row)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text

app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/static")

# Configure Flask session
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Register blueprints
from routes.quotation_routes import quotation_bp
from routes.quotation_routes_approved import quotation_approved_bp
app.register_blueprint(quotation_bp)
app.register_blueprint(quotation_approved_bp)

@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def _build_sql_api_auth_headers():
    """Build optional SQL API auth headers when keys are configured."""
    access_key = (os.getenv('SQL_API_ACCESS_KEY') or os.getenv('API_ACCESS_KEY') or '').strip()
    secret_key = (os.getenv('SQL_API_SECRET_KEY') or os.getenv('API_SECRET_KEY') or '').strip()
    if access_key and secret_key:
        return {
            'X-Access-Key': access_key,
            'X-Secret-Key': secret_key,
        }
    return {}


def _fetch_all_customers_from_sql_api():
    """Fetch all customers from SQL API /customer with pagination."""
    api_url = f"{FASTAPI_BASE_URL}/customer"
    headers = _build_sql_api_auth_headers()
    offset = 0
    limit = 200
    all_customers = []

    while True:
        response = requests.get(
            api_url,
            params={'offset': offset, 'limit': limit},
            headers=headers if headers else None,
            timeout=8,
        )
        if not response.ok:
            raise RuntimeError(f'SQL API returned {response.status_code} for /customer')

        payload = response.json()
        rows = payload.get('data') if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError('Unexpected SQL API format: missing data[]')

        for customer in rows:
            code = (str(customer.get('code')).strip() if customer.get('code') is not None else '')
            if not code:
                continue
            company_name = (
                customer.get('companyname')
                or customer.get('company_name')
                or code
            )
            raw_status = customer.get('status')
            status = (str(raw_status).strip().upper() if raw_status is not None else '')[:1]
            all_customers.append({
                'code': code,
                'company_name': str(company_name).strip() if company_name is not None else code,
                'status': status,
            })

        if not rows:
            break

        pagination = payload.get('pagination') if isinstance(payload, dict) else None
        page_count = pagination.get('count') if isinstance(pagination, dict) else len(rows)
        if not isinstance(page_count, int) or page_count <= 0:
            page_count = len(rows)

        offset += page_count
        if page_count < limit:
            break

    return all_customers


@app.route('/api/admin/customer_status_summary', methods=['GET'])
@api_admin_required(unauth_message='Not authenticated', forbidden_message='Insufficient permissions')
def customer_status_summary():
    """Return customer status distribution from SQL API /customer endpoint."""
    cached = _dashboard_cache_get('customer_status_summary')
    if cached:
        return jsonify(cached), 200
    status_order = ['A', 'AWO', 'I', 'S', 'P', 'N']
    status_labels = {
        'A': 'Active',
        'AWO': 'Active w/o invoice',
        'I': 'Inactive',
        'S': 'Suspend',
        'P': 'Prospect',
        'N': 'Pending',
    }
    counts = {code: 0 for code in status_order}

    try:
        customers = _fetch_all_customers_from_sql_api()
        # Get invoice aging info for all customers
        invoice_aging = requests.get(request.host_url.rstrip('/') + '/api/admin/invoice_aging_summary', headers=request.headers, timeout=30)
        invoice_aging_items = invoice_aging.json().get('data', {}).get('items', []) if invoice_aging.ok else []
        invoice_map = {item['code']: item for item in invoice_aging_items}

        for customer in customers:
            status = customer.get('status', '')
            code = customer.get('code', '')
            # Only split 'Active' into two groups
            if status == 'A':
                inv = invoice_map.get(code)
                if inv and inv.get('days_ago_label') != 'No invoice':
                    counts['A'] += 1
                else:
                    counts['AWO'] += 1
            elif status in counts:
                counts[status] += 1

        items = [
            {
                'code': code,
                'label': status_labels[code],
                'count': counts[code],
            }
            for code in status_order
            if counts[code] > 0
        ]

        payload_out = {
            'success': True,
            'data': {
                'items': items,
                'total_customers': sum(counts.values()),
                'processed_customers': len(customers),
                'customers': customers,
            }
        }
        _dashboard_cache_set('customer_status_summary', payload_out)
        return jsonify(payload_out), 200
    except requests.exceptions.RequestException as exc:
        return jsonify({'success': False, 'error': f'Failed to reach SQL API /customer: {exc}'}), 502
    except RuntimeError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 502
    except Exception as exc:
        print(f'Error loading customer status summary: {exc}')
        return jsonify({'success': False, 'error': 'Failed to load customer status summary'}), 500



@app.route('/api/admin/invoice_aging_summary', methods=['GET'])
@api_admin_required(unauth_message='Not authenticated', forbidden_message='Insufficient permissions')
def invoice_aging_summary():
    """Return invoice aging, using SQL API customer list + local invoice dates, with pagination."""
    con = None
    cur = None
    try:
        today = datetime.now().date()
        con = get_db_connection()
        cur = con.cursor()

        # Pagination params
        try:
            offset = int(request.args.get('offset', 0))
            limit = int(request.args.get('limit', 10))
            if limit > 100:
                limit = 100
            if offset < 0:
                offset = 0
        except Exception:
            offset = 0
            limit = 10

        customers = {
            customer['code']: customer['company_name']
            for customer in _fetch_all_customers_from_sql_api()
        }

        # Fetch invoice dates from database
        cur.execute("""
            SELECT CODE, MAX(DOCDATE) AS LATEST_DOCDATE
            FROM SL_IV
            WHERE DOCDATE IS NOT NULL
              AND CODE IS NOT NULL
              AND TRIM(CODE) <> ''
            GROUP BY CODE
        """)

        invoice_dates = {}
        for code, docdate in cur.fetchall() or []:
            if code:
                invoice_dates[code] = docdate

        latest_by_code = []

        # Build list with all customers
        for code, company_name in customers.items():
            if not code:
                continue

            raw_docdate = invoice_dates.get(code)
            if raw_docdate is not None:
                docdate = raw_docdate if not isinstance(raw_docdate, datetime) else raw_docdate.date()
                days_ago = max(0, (today - docdate).days)
                day_suffix = 'day' if days_ago == 1 else 'days'
                docdate_str = docdate.isoformat()
                days_ago_label = f'{days_ago} {day_suffix} ago'
            else:
                docdate_str = None
                days_ago = None
                days_ago_label = 'No invoice'

            latest_by_code.append({
                'code': code,
                'company_name': company_name,
                'docdate': docdate_str,
                'days_ago': days_ago,
                'days_ago_label': days_ago_label,
            })

        # Sort: invoices first by days_ago, then no-invoice at the end by company name
        latest_by_code.sort(key=lambda item: (item['days_ago'] if item['days_ago'] is not None else 99999, item['company_name'].lower(), item['code']))

        # Pagination
        total_codes = len(latest_by_code)
        paged_items = latest_by_code[offset:offset+limit]

        latest_days_ago = paged_items[0]['days_ago_label'] if paged_items else None
        latest_company_name = paged_items[0]['company_name'] if paged_items else None

        return jsonify({
            'success': True,
            'data': {
                'items': paged_items,
                'total_codes': total_codes,
                'offset': offset,
                'limit': limit,
                'has_more': offset + limit < total_codes,
                'latest_invoice_age': latest_days_ago,
                'latest_invoice_company': latest_company_name,
                'today': today.isoformat(),
            }
        }), 200
    except requests.exceptions.RequestException as exc:
        return jsonify({'success': False, 'error': f'Failed to reach SQL API /customer: {exc}'}), 502
    except RuntimeError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 502
    except Exception as exc:
        print(f'Error loading invoice aging summary: {exc}')
        return jsonify({'success': False, 'error': 'Failed to load invoice aging summary'}), 500
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


@app.route('/api/admin/sales_cycle_summary', methods=['GET'])
@api_admin_required(unauth_message='Not authenticated', forbidden_message='Insufficient permissions')
def sales_cycle_summary():
    """Return sales cycle metrics from FastAPI dashboard endpoint."""
    headers = _build_sql_api_auth_headers()
    try:
        response = requests.get(
            f"{FASTAPI_BASE_URL}/dashboard/sales-cycle-metrics",
            headers=headers if headers else None,
            timeout=20,
        )
        payload = response.json()
    except requests.exceptions.RequestException as exc:
        return jsonify({'success': False, 'error': f'Failed to reach FastAPI sales cycle endpoint: {exc}'}), 502
    except ValueError:
        return jsonify({'success': False, 'error': 'FastAPI sales cycle endpoint returned invalid JSON'}), 502

    if not response.ok:
        detail = payload.get('detail') if isinstance(payload, dict) else None
        return jsonify({'success': False, 'error': detail or 'Failed to load sales cycle metrics'}), response.status_code

    if not isinstance(payload, dict):
        return jsonify({'success': False, 'error': 'Unexpected sales cycle response format'}), 502

    return jsonify({'success': True, 'data': payload}), 200


@app.route('/api/admin/sales_cycle_details', methods=['GET'])
@api_admin_required(unauth_message='Not authenticated', forbidden_message='Insufficient permissions')
def sales_cycle_details():
    """Return detailed sales cycle rows from FastAPI dashboard endpoint."""
    cached = _dashboard_cache_get('sales_cycle_details')
    if cached:
        return jsonify(cached), 200
    headers = _build_sql_api_auth_headers()
    try:
        response = requests.get(
            f"{FASTAPI_BASE_URL}/dashboard/sales-cycle-details",
            headers=headers if headers else None,
            timeout=25,
        )
        payload = response.json()
    except requests.exceptions.RequestException as exc:
        return jsonify({'success': False, 'error': f'Failed to reach FastAPI sales cycle detail endpoint: {exc}'}), 502
    except ValueError:
        return jsonify({'success': False, 'error': 'FastAPI sales cycle detail endpoint returned invalid JSON'}), 502

    if not response.ok:
        detail = payload.get('detail') if isinstance(payload, dict) else None
        return jsonify({'success': False, 'error': detail or 'Failed to load sales cycle details'}), response.status_code

    if not isinstance(payload, dict):
        return jsonify({'success': False, 'error': 'Unexpected sales cycle details response format'}), 502

    payload_out = {'success': True, 'data': payload}
    _dashboard_cache_set('sales_cycle_details', payload_out)
    return jsonify(payload_out), 200


@app.route('/api/admin/qt_iv_conversion_report', methods=['GET'])
@app.route('/api/admin/qt_iv_conversion_report/', methods=['GET'])
@app.route('/api/admin/qt-iv-conversion-report', methods=['GET'])
@api_admin_required(unauth_message='Not authenticated', forbidden_message='Insufficient permissions')
def qt_iv_conversion_report():
    """Return QT->IV conversion report from FastAPI dashboard endpoint."""
    cached = _dashboard_cache_get('qt_iv_conversion_report')
    if cached:
        return jsonify(cached), 200
    headers = _build_sql_api_auth_headers()
    try:
        response = requests.get(
            f"{FASTAPI_BASE_URL}/dashboard/qt-iv-conversion-report",
            headers=headers if headers else None,
            timeout=30,
        )
        payload = response.json()
    except requests.exceptions.RequestException as exc:
        return jsonify({'success': False, 'error': f'Failed to reach FastAPI QT->IV report endpoint: {exc}'}), 502
    except ValueError:
        return jsonify({'success': False, 'error': 'FastAPI QT->IV report endpoint returned invalid JSON'}), 502

    if not response.ok:
        detail = payload.get('detail') if isinstance(payload, dict) else None
        return jsonify({'success': False, 'error': detail or 'Failed to load QT->IV conversion report'}), response.status_code

    if not isinstance(payload, dict):
        return jsonify({'success': False, 'error': 'Unexpected QT->IV report response format'}), 502

    payload_out = {'success': True, 'data': payload}
    _dashboard_cache_set('qt_iv_conversion_report', payload_out)
    return jsonify(payload_out), 200

# ============================================
# ROUTE: Delete Order Detail
# ============================================
@app.route('/php/deleteOrderDetail.php', methods=['POST'])
def proxy_delete_order_detail():
    """Proxy endpoint to delete order detail via XAMPP PHP."""
    return proxy_post_with_auth(
        '/php/deleteOrderDetail.php',
        error_message='Failed to delete order detail',
        log_context='deleteOrderDetail'
    )

# ============================================
# ROUTE: Update Quotation Cancelled Status
# ============================================
@app.route('/api/admin/update_quotation_cancelled', methods=['POST'])
@api_admin_required(unauth_message='Not authenticated', forbidden_message='Insufficient permissions')
def update_quotation_cancelled():
    """Forward CANCELLED status update to PHP endpoint (admin only)."""
    data = request.get_json() or {}
    dockey = data.get('dockey')
    cancelled = data.get('cancelled')

    if not dockey or cancelled is None:
        return jsonify({'success': False, 'error': 'Missing dockey or cancelled'}), 400

    try:
        php_url = f"{BASE_API_URL}/php/updateQuotationCancelled.php"
        response = requests.post(
            php_url,
            json={'dockey': dockey, 'cancelled': cancelled},
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Failed to update quotation')}), 500
        
        # If activating quotation (cancelled: false), send email to customer
        if cancelled is False:
            print(f"[ACTIVATE DEBUG] Attempting to send email for DOCKEY {dockey}")
            try:
                # Fetch quotation details
                print(f"[ACTIVATE DEBUG] Fetching quotation details from {BASE_API_URL}/php/getQuotationDetails.php")
                qt_response = requests.get(
                    f"{BASE_API_URL}/php/getQuotationDetails.php",
                    params={'dockey': dockey},
                    timeout=10
                )
                qt_data = qt_response.json()
                print(f"[ACTIVATE DEBUG] Quotation details response success: {qt_data.get('success')}, has data: {bool(qt_data.get('data'))}")
                
                if qt_data.get('success') and qt_data.get('data'):
                    quotation = qt_data['data']
                    customer_email = quotation.get('UDF_EMAIL', '').strip()
                    print(f"[ACTIVATE DEBUG] Customer email: '{customer_email}'")
                    
                    if customer_email:
                        # Send email notification
                        email_data = {
                            'customerEmail': customer_email,
                            'docno': quotation.get('DOCNO', 'N/A'),
                            'dockey': dockey,
                            'totalAmount': quotation.get('DOCAMT', 0),
                            'items': quotation.get('items', []),
                            'companyName': quotation.get('COMPANYNAME', 'Valued Customer')
                        }
                        print(f"[ACTIVATE DEBUG] Sending email to {customer_email}")
                        
                        email_response = requests.post(
                            f"http://localhost:{request.environ.get('SERVER_PORT', '5000')}/api/send_quotation_ready_email",
                            json=email_data,
                            timeout=10
                        )
                        
                        if email_response.json().get('success'):
                            print(f"[EMAIL] Quotation activation email sent for DOCKEY {dockey}")
                        else:
                            print(f"[EMAIL WARNING] Failed to send activation email for DOCKEY {dockey}")
                    else:
                        print(f"[ACTIVATE DEBUG] No customer email found")
                else:
                    print(f"[ACTIVATE DEBUG] Failed to get quotation details")
            except Exception as email_error:
                # Don't fail the activation if email fails
                print(f"[EMAIL ERROR] Failed to send activation email: {email_error}")
        
        return jsonify({'success': True, 'message': 'Quotation status updated'}), 200
    except Exception as e:
        print(f"Error updating quotation cancelled status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/cancel_single_quotation', methods=['POST'])
@api_admin_required(unauth_message='Not authenticated', forbidden_message='Insufficient permissions')
def cancel_single_quotation():
    """Cancel a single quotation (admin only)."""
    data = request.get_json() or {}
    dockey = data.get('dockey')
    
    print(f"[CANCEL SINGLE] Received request for DOCKEY: {dockey}", flush=True)

    if not dockey:
        print(f"[CANCEL SINGLE] Missing dockey parameter", flush=True)
        return jsonify({'success': False, 'error': 'dockey parameter required'}), 400

    try:
        # Call PHP endpoint to update database
        php_url = f"{BASE_API_URL}/php/updateQuotationCancelled.php"
        payload = {'dockey': dockey, 'cancelled': True}
        
        print(f"[CANCEL SINGLE] Calling PHP: {php_url}", flush=True)
        print(f"[CANCEL SINGLE] Payload: {payload}", flush=True)
        
        response = requests.post(
            php_url,
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"[CANCEL SINGLE] PHP Response: {result}", flush=True)
        
        if result.get('success'):
            print(f"[CANCEL SINGLE] Successfully cancelled DOCKEY {dockey}", flush=True)
            return jsonify({
                'success': True,
                'message': f'Quotation {dockey} cancelled successfully'
            }), 200
        else:
            error_msg = result.get('error', 'Unknown error')
            print(f"[CANCEL SINGLE] Failed: {error_msg}", flush=True)
            return jsonify({
                'success': False,
                'error': error_msg
            }), 500
    
    except Exception as e:
        print(f"[CANCEL SINGLE] Exception: {str(e)}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/delete_quotations', methods=['POST'])
@api_admin_required(unauth_message='Not authenticated', forbidden_message='Insufficient permissions')
def delete_quotations():
    """Delete (cancel) multiple quotations - main deletion API."""
    data = request.get_json() or {}
    dockey_list = data.get('dockeyList', [])

    print(f"\n[DELETE QUOTATIONS] ========== START ==========", flush=True)
    print(f"[DELETE QUOTATIONS] Received request with {len(dockey_list)} quotations to delete", flush=True)
    print(f"[DELETE QUOTATIONS] DOCKEYs: {dockey_list}", flush=True)

    if not dockey_list or not isinstance(dockey_list, list):
        print(f"[DELETE QUOTATIONS] ERROR: Invalid dockeyList format", flush=True)
        return jsonify({'success': False, 'error': 'Invalid dockeyList - must be an array'}), 400

    try:
        deleted_count = 0
        failed_count = 0
        failed_details = []
        
        php_url = f"{BASE_API_URL}/php/updateQuotationCancelled.php"
        
        for dockey in dockey_list:
            print(f"\n[DELETE QUOTATIONS] Processing DOCKEY: {dockey}", flush=True)
            
            try:
                # Prepare payload
                payload = {
                    'dockey': int(dockey),
                    'cancelled': True
                }
                print(f"[DELETE QUOTATIONS] Sending to PHP: {payload}", flush=True)
                
                # Call PHP endpoint
                response = requests.post(
                    php_url,
                    json=payload,
                    timeout=10
                )
                
                print(f"[DELETE QUOTATIONS] PHP response status: {response.status_code}", flush=True)
                
                if response.status_code != 200:
                    print(f"[DELETE QUOTATIONS] ERROR: Bad status code: {response.text[:500]}", flush=True)
                    failed_count += 1
                    failed_details.append(f"DOCKEY {dockey}: HTTP {response.status_code}")
                    continue
                
                result = response.json()
                print(f"[DELETE QUOTATIONS] PHP result: {result}", flush=True)
                
                if result.get('success'):
                    deleted_count += 1
                    print(f"[DELETE QUOTATIONS] ✓ DOCKEY {dockey} deleted successfully", flush=True)
                else:
                    failed_count += 1
                    error_msg = result.get('error', 'Unknown error')
                    failed_details.append(f"DOCKEY {dockey}: {error_msg}")
                    print(f"[DELETE QUOTATIONS] ✗ DOCKEY {dockey} failed: {error_msg}", flush=True)
                    
            except Exception as e:
                failed_count += 1
                failed_details.append(f"DOCKEY {dockey}: {str(e)}")
                print(f"[DELETE QUOTATIONS] ✗ EXCEPTION for DOCKEY {dockey}: {str(e)}", flush=True)
        
        print(f"\n[DELETE QUOTATIONS] Summary: deleted={deleted_count}, failed={failed_count}", flush=True)
        print(f"[DELETE QUOTATIONS] ========== END ==========\n", flush=True)
        
        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'failed_count': failed_count,
            'failed_details': failed_details if failed_details else None,
            'message': f'Deleted {deleted_count} quotation(s)' + (f' ({failed_count} failed)' if failed_count > 0 else '')
        }), 200

    except Exception as e:
        print(f"[DELETE QUOTATIONS] CRITICAL ERROR: {str(e)}", flush=True)
        print(f"[DELETE QUOTATIONS] ========== END (ERROR) ==========\n", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/bulk_cancel_quotations', methods=['POST'])
@api_admin_required(unauth_message='Not authenticated', forbidden_message='Insufficient permissions')
def bulk_cancel_quotations():
    """Deprecated: Use /api/admin/delete_quotations instead. This endpoint now forwards to it."""
    # Forward to the new endpoint
    return delete_quotations()


@app.route('/api/create_signin_user', methods=['POST'])
def create_signin_user():
    """Create guest customer via FastAPI /customers endpoint (API path, no direct DB write in Flask)."""
    data = request.form.to_dict() if (request.content_type and 'multipart/form-data' in request.content_type) else (request.get_json() or {})
    files = request.files if (request.content_type and 'multipart/form-data' in request.content_type) else {}

    # Customer code is generated for guest sign-in when not supplied.
    generated_code = f"G{datetime.now().strftime('%d%H%M%S')}{random.randint(10, 99)}"  # 10 chars total
    customer_code = ((data.get('CUSTOMERCODE') or '').strip() or generated_code)[:10]
    data['CUSTOMERCODE'] = customer_code

    # Normalize country to alpha-2 when possible.
    if 'COUNTRY' in data:
        data['COUNTRY'] = _normalize_country_alpha2(data.get('COUNTRY'))

    # Ensure CITY/STATE are populated from postcode when possible.
    try:
        postcode = (data.get('POSTCODE') or '').strip()
        city = (data.get('CITY') or '').strip()
        state = (data.get('STATE') or '').strip()
        if postcode and (not city or not state):
            hit = _lookup_postcode(postcode)
            if hit:
                data['CITY'] = hit.get('city') or data.get('CITY') or ''
                data['STATE'] = hit.get('state') or data.get('STATE') or ''
    except Exception as e:
        print(f"[WARN] Failed to auto-fill CITY/STATE from postcode during sign-in: {e}")

    validation_error = validate_registration_fields(data)
    if validation_error:
        return jsonify({'success': False, 'error': validation_error}), 400

    attachment_names = []
    for _key, file in files.items():
        if file and file.filename:
            attachment_names.append(file.filename)

    # Map legacy guest form fields (UPPERCASE) to FastAPI customer request schema.
    customer_payload = {
        'code': customer_code,
        'company_name': data.get('COMPANYNAME'),
        'credit_term': str(data.get('CREDITTERM') or '30'),
        'area': data.get('AREA') or None,
        'currency_code': data.get('CURRENCYCODE') or None,
        'brn': data.get('BRN') or None,
        'brn2': data.get('BRN2') or None,
        'tin': data.get('TIN') or None,
        'sales_tax_no': data.get('SALESTAXNO') or None,
        'service_tax_no': data.get('SERVICETAXNO') or None,
        'tax_exempt_no': data.get('TAXEXEMPTNO') or None,
        'tax_exp_date': data.get('TAXEXPDATE') or None,
        'udf_email': data.get('UDF_EMAIL') or None,
        'email': data.get('UDF_EMAIL') or None,
        'phone': data.get('PHONE1') or None,
        'attention': data.get('ATTENTION') or None,
        'address1': data.get('ADDRESS1') or None,
        'address2': data.get('ADDRESS2') or None,
        'address3': data.get('ADDRESS3') or None,
        'address4': data.get('ADDRESS4') or None,
        'postcode': data.get('POSTCODE') or None,
        'city': data.get('CITY') or None,
        'state': data.get('STATE') or None,
        'country': data.get('COUNTRY') or None,
        'attachments': ', '.join(attachment_names) if attachment_names else None,
        'idtype': 1,
    }

    api_headers = {'Content-Type': 'application/json'}
    if FASTAPI_ACCESS_KEY and FASTAPI_SECRET_KEY:
        api_headers['X-Access-Key'] = FASTAPI_ACCESS_KEY
        api_headers['X-Secret-Key'] = FASTAPI_SECRET_KEY

    api_url = f"{FASTAPI_BASE_URL}/customers"
    local_api_url = f"{FASTAPI_BASE_URL}/local/customers"

    # Fallback payload for local API path (direct local Firebird insert behind FastAPI).
    local_customer_payload = {
        'code': customer_code,
        'company_name': data.get('COMPANYNAME'),
        'credit_term': str(data.get('CREDITTERM') or '30'),
        'phone1': data.get('PHONE1') or None,
        'email': data.get('UDF_EMAIL') or None,
        'address1': data.get('ADDRESS1') or None,
        'address2': data.get('ADDRESS2') or None,
        'postcode': data.get('POSTCODE') or None,
        'city': data.get('CITY') or None,
        'state': data.get('STATE') or None,
        'country': data.get('COUNTRY') or None,
    }

    try:
        response = requests.post(api_url, json=customer_payload, headers=api_headers, timeout=20)
    except Exception as e:
        print(f"Error calling FastAPI /customers: {e}")
        if not GUEST_SIGNIN_ALLOW_LOCAL_FALLBACK:
            return jsonify({'success': False, 'error': f'Remote customer API required and unreachable: {str(e)}'}), 502
        try:
            local_response = requests.post(local_api_url, json=local_customer_payload, headers=api_headers, timeout=20)
            local_result = local_response.json()
            if local_response.status_code < 400 and isinstance(local_result, dict) and local_result.get('success'):
                local_data = local_result.get('data') or {}
                return jsonify({
                    'success': True,
                    'message': 'Guest user created successfully (local fallback)',
                    'customerCode': local_data.get('code', customer_code),
                    'redirect': '/login',
                    'data': {'customer': local_data, 'source': 'local-fallback'},
                }), 201

            local_error = (local_result.get('detail') or local_result.get('error')) if isinstance(local_result, dict) else 'local fallback failed'
            return jsonify({'success': False, 'error': f'Cannot connect to customer API: {str(e)} | local fallback failed: {local_error}'}), 500
        except Exception as local_exc:
            return jsonify({'success': False, 'error': f'Cannot connect to customer API: {str(e)} | local fallback failed: {str(local_exc)}'}), 500

    try:
        result = response.json()
    except Exception:
        result = {'error': 'Customer API returned an invalid response'}

    if response.status_code >= 400:
        detail = result.get('detail') if isinstance(result, dict) else None
        if isinstance(detail, list):
            detail = '; '.join(str(item.get('msg', item)) for item in detail)
        primary_error = detail or (result.get('error') if isinstance(result, dict) else None) or 'Customer API request failed'

        if not GUEST_SIGNIN_ALLOW_LOCAL_FALLBACK:
            return jsonify({'success': False, 'error': f'Remote customer API required and failed: {primary_error}'}), response.status_code

        # Fallback: if upstream-backed /customers fails, try local FastAPI path.
        try:
            local_response = requests.post(local_api_url, json=local_customer_payload, headers=api_headers, timeout=20)
            local_result = local_response.json()
        except Exception as local_exc:
            return jsonify({'success': False, 'error': f'{primary_error} | local fallback failed: {str(local_exc)}'}), response.status_code

        if local_response.status_code >= 400 or not isinstance(local_result, dict) or not local_result.get('success'):
            local_error = (local_result.get('detail') or local_result.get('error')) if isinstance(local_result, dict) else 'local fallback failed'
            return jsonify({'success': False, 'error': f'{primary_error} | local fallback failed: {local_error}'}), response.status_code

        local_data = local_result.get('data') or {}
        return jsonify({
            'success': True,
            'message': 'Guest user created successfully (local fallback)',
            'customerCode': local_data.get('code', customer_code),
            'redirect': '/login',
            'data': {'customer': local_data, 'source': 'local-fallback'},
        }), 201

    # Keep frontend contract backward-compatible.
    customer_data = ((result.get('data') or {}).get('customer') or {}) if isinstance(result, dict) else {}
    return jsonify({
        'success': True,
        'message': result.get('message', 'Guest user created successfully'),
        'customerCode': customer_data.get('code', customer_code),
        'redirect': '/login',
        'data': {'source': 'remote-api', **(result.get('data') or {})},
    }), response.status_code


@app.route('/api/create_signin_user_minimal', methods=['POST'])
def create_signin_user_minimal():
    """Create guest customer with minimal fields only: companyname (code auto-generated)."""
    data = request.get_json() or {}

    provided_code = str(data.get('code') or data.get('CODE') or '').strip()[:10]
    company_name = str(
        data.get('companyname') or data.get('company_name') or data.get('companyName') or data.get('COMPANYNAME') or ''
    ).strip()
    area = str(data.get('area') or data.get('AREA') or '').strip()
    currencycode = str(data.get('currencycode') or data.get('CURRENCYCODE') or '').strip()
    tin = str(data.get('tin') or data.get('TIN') or '').strip()
    brn = str(data.get('brn') or data.get('BRN') or '').strip()
    brn2 = str(data.get('brn2') or data.get('BRN2') or '').strip()
    salestaxno = str(data.get('salestaxno') or data.get('SALESTAXNO') or '').strip()
    servicetaxno = str(data.get('servicetaxno') or data.get('SERVICETAXNO') or '').strip()
    taxexemptno = str(data.get('taxexemptno') or data.get('TAXEXEMPTNO') or '').strip()
    taxexpdate = str(data.get('taxexpdate') or data.get('TAXEXPDATE') or '').strip()
    idtype_raw = data.get('idtype') if data.get('idtype') is not None else data.get('IDTYPE')
    attention = str(data.get('attention') or data.get('ATTENTION') or '').strip()
    address1 = str(data.get('address1') or data.get('ADDRESS1') or '').strip()
    address2 = str(data.get('address2') or data.get('ADDRESS2') or '').strip()
    address3 = str(data.get('address3') or data.get('ADDRESS3') or '').strip()
    address4 = str(data.get('address4') or data.get('ADDRESS4') or '').strip()
    postcode = str(data.get('postcode') or data.get('POSTCODE') or '').strip()
    city = str(data.get('city') or data.get('CITY') or '').strip()
    state = str(data.get('state') or data.get('STATE') or '').strip()
    country = str(data.get('country') or data.get('COUNTRY') or '').strip()
    phone1 = str(data.get('phone1') or data.get('phone') or data.get('PHONE1') or '').strip()
    email = str(data.get('email') or data.get('EMAIL') or data.get('udf_email') or data.get('UDF_EMAIL') or '').strip()

    if not company_name:
        return jsonify({'success': False, 'error': 'companyname is required'}), 400

    customer_payload = {
        'company_name': company_name,
    }
    if provided_code:
        customer_payload['code'] = provided_code
    else:
        customer_payload['code'] = _generate_next_guest_customer_code(company_name)
    if area:
        customer_payload['area'] = area
    if currencycode:
        customer_payload['currencycode'] = currencycode
    if tin:
        customer_payload['tin'] = tin
    if brn:
        customer_payload['brn'] = brn
    if brn2:
        customer_payload['brn2'] = brn2
    if salestaxno:
        customer_payload['salestaxno'] = salestaxno
    if servicetaxno:
        customer_payload['servicetaxno'] = servicetaxno
    if taxexemptno:
        customer_payload['taxexemptno'] = taxexemptno
    if taxexpdate:
        customer_payload['taxexpdate'] = taxexpdate
    # Always set idtype=1 for guest sign-in if not provided
    if idtype_raw not in (None, ''):
        try:
            customer_payload['idtype'] = int(idtype_raw)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'idtype must be an integer'}), 400
    else:
        customer_payload['idtype'] = 1
    if attention:
        customer_payload['attention'] = attention
    if address1:
        customer_payload['address1'] = address1
    if address2:
        customer_payload['address2'] = address2
    if address3:
        customer_payload['address3'] = address3
    if address4:
        customer_payload['address4'] = address4
    if postcode:
        customer_payload['postcode'] = postcode
    if city:
        customer_payload['city'] = city
    if state:
        customer_payload['state'] = state
    if country:
        customer_payload['country'] = country
    if phone1:
        customer_payload['phone'] = phone1
    if email:
        customer_payload['email'] = email
        customer_payload['udf_email'] = email

    api_headers = {'Content-Type': 'application/json'}
    if FASTAPI_ACCESS_KEY and FASTAPI_SECRET_KEY:
        api_headers['X-Access-Key'] = FASTAPI_ACCESS_KEY
        api_headers['X-Secret-Key'] = FASTAPI_SECRET_KEY

    api_url = f"{FASTAPI_BASE_URL}/customers"
    response = None
    result = None
    max_attempts = 1 if provided_code else 5

    for attempt_idx in range(max_attempts):
        try:
            response = requests.post(api_url, json=customer_payload, headers=api_headers, timeout=20)
        except Exception as e:
            return jsonify({'success': False, 'error': f'Cannot connect to customer API: {str(e)}'}), 502

        try:
            result = response.json()
        except Exception:
            return jsonify({'success': False, 'error': 'Customer API returned an invalid response'}), 502

        if response.status_code < 400:
            break

        detail = result.get('detail') if isinstance(result, dict) else None
        if isinstance(detail, list):
            detail = '; '.join(str(item.get('msg', item)) for item in detail)
        reason = str(detail or (result.get('error') if isinstance(result, dict) else None) or 'Customer API request failed')

        # Auto-retry duplicate code collisions only for auto-generated codes.
        if not provided_code and _is_duplicate_customer_code_error(reason) and attempt_idx < (max_attempts - 1):
            current_code = str(customer_payload.get('code') or '')
            customer_payload['code'] = _increment_guest_customer_code(current_code)
            continue

        return jsonify({'success': False, 'error': reason, 'upstream': result}), response.status_code

    customer_data = ((result.get('data') or {}).get('customer') or {}) if isinstance(result, dict) else {}
    customer_code = customer_data.get('code')

    local_db_snapshot = None
    if customer_code:
        try:
            local_db_snapshot = sync_local_customer_fields(
                LocalCustomerSyncRequest(
                    code=customer_code,
                    area=area or None,
                    currency_code=currencycode or None,
                    tin=tin or None,
                    brn=brn or None,
                    brn2=brn2 or None,
                    sales_tax_no=salestaxno or None,
                    service_tax_no=servicetaxno or None,
                    tax_exp_date=taxexpdate or None,
                    tax_exempt_no=taxexemptno or None,
                    idtype=int(idtype_raw) if idtype_raw not in (None, '') else None,
                    attention=attention or None,
                    address1=address1 or None,
                    address2=address2 or None,
                    address3=address3 or None,
                    address4=address4 or None,
                    postcode=postcode or None,
                    city=city or None,
                    state=state or None,
                    country=country or None,
                    phone1=phone1 or None,
                    email=email or None,
                )
            )
        except Exception as sync_exc:
            print(f"[WARN] Post-create local sync failed for {customer_code}: {sync_exc}")

    response_data = {'source': 'remote-api', **(result.get('data') or {})}
    if isinstance(response_data.get('customer'), dict) and local_db_snapshot:
        response_data['customer']['local_db_snapshot'] = local_db_snapshot

    return jsonify({
        'success': True,
        'message': result.get('message', 'Guest user created successfully'),
        'customerCode': customer_code,
        'redirect': '/login',
        'data': response_data,
    }), response.status_code


def _is_duplicate_customer_code_error(reason: str) -> bool:
    text = (reason or '').upper()
    return 'GL_ACC_CODE' in text and 'PROBLEMATIC KEY VALUE' in text and '"CODE"' in text


def _increment_guest_customer_code(code: str) -> str:
    match = re.match(r'^300-([A-Z])(\d{4})$', (code or '').strip().upper())
    if not match:
        return code

    prefix = match.group(1)
    number = int(match.group(2))
    if number >= 9999:
        return f"300-{prefix}9999"
    return f"300-{prefix}{number + 1:04d}"


def _generate_next_guest_customer_code(company_name: str) -> str:
    normalized = re.sub(r'[^A-Z0-9]', '', (company_name or '').upper())
    prefix = normalized[0] if normalized else 'X'
    pattern = re.compile(rf'^300-{re.escape(prefix)}(\d{{4}})$')

    con = None
    cur = None
    max_number = 0
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute('SELECT CODE FROM AR_CUSTOMER WHERE CODE STARTING WITH ?', [f'300-{prefix}'])
        rows = cur.fetchall() or []
        for row in rows:
            code = str((row[0] if row else '') or '').strip().upper()
            m = pattern.match(code)
            if m:
                max_number = max(max_number, int(m.group(1)))
    except Exception as e:
        print(f"[WARN] Failed to query AR_CUSTOMER for next guest code: {e}")
    finally:
        if cur:
            cur.close()
        if con:
            con.close()

    next_number = max_number + 1
    if next_number > 9999:
        next_number = 9999
    return f"300-{prefix}{next_number:04d}"


def _fetch_code_list_from_firebird(table_name):
    """Read CODE values from Firebird master tables used by guest sign-in dropdowns."""
    allowed_tables = {'AREA', 'CURRENCY'}
    normalized = (table_name or '').strip().upper()
    if normalized not in allowed_tables:
        raise ValueError(f'Unsupported lookup table: {table_name}')

    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute(f'SELECT CODE FROM {normalized} ORDER BY CODE')
        rows = cur.fetchall() or []

        values = []
        for row in rows:
            code = str((row[0] if row else '') or '').strip()
            if code:
                values.append(code)
        return values
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


@app.route('/api/get_currency_symbols', methods=['GET'])
def get_currency_symbols():
    """Fetch currency symbols for guest sign-in dropdown."""
    try:
        php_url = f"{BASE_API_URL}/php/getCurrencySymbols.php"
        response = requests.get(php_url, timeout=10)
        if response.status_code < 400:
            result = response.json()
            if isinstance(result, dict) and result.get('success') and isinstance(result.get('data'), list):
                return jsonify(result), response.status_code
            raise ValueError('PHP endpoint returned unexpected payload shape')
        raise requests.exceptions.HTTPError(f"HTTP {response.status_code}")
    except Exception as e:
        print(f"Error calling getCurrencySymbols.php: {e}")
        try:
            values = _fetch_code_list_from_firebird('CURRENCY')
            return jsonify({'success': True, 'data': values, 'source': 'firebird-fallback'}), 200
        except Exception as fb_error:
            return jsonify({'success': False, 'error': f'{str(e)} | fallback failed: {str(fb_error)}'}), 500


@app.route('/api/get_area_codes', methods=['GET'])
def get_area_codes():
    """Fetch AREA.CODE values for guest sign-in dropdown."""
    try:
        php_url = f"{BASE_API_URL}/php/getAreaCodes.php"
        response = requests.get(php_url, timeout=10)
        if response.status_code < 400:
            result = response.json()
            if isinstance(result, dict) and result.get('success') and isinstance(result.get('data'), list):
                return jsonify(result), response.status_code
            raise ValueError('PHP endpoint returned unexpected payload shape')
        raise requests.exceptions.HTTPError(f"HTTP {response.status_code}")
    except Exception as e:
        print(f"Error calling getAreaCodes.php: {e}")
        try:
            values = _fetch_code_list_from_firebird('AREA')
            return jsonify({'success': True, 'data': values, 'source': 'firebird-fallback'}), 200
        except Exception as fb_error:
            return jsonify({'success': False, 'error': f'{str(e)} | fallback failed: {str(fb_error)}'}), 500

# ============================================
# AUTHENTICATION FUNCTIONS
# ============================================

@app.route('/login')
def login():
    """Show login page"""
    if 'user_email' in session:
        if session.get('user_type') == 'admin':
            return redirect('/admin')
        return redirect('/create-quotation')
    return render_template('login.html')


@app.route('/signInGuest')
def sign_in_guest():
    """Show minimal guest sign-in page (code + companyname)."""
    countries = []
    try:
        csv_path = os.path.join(os.path.dirname(__file__), 'csv', 'CountryCodeWNames.csv')
        with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            seen = set()
            for row in reader:
                name = (row.get('name') or '').strip()
                alpha2 = (row.get('alpha-2') or '').strip().upper()
                if not name or not alpha2 or name in seen:
                    continue
                seen.add(name)
                countries.append({'name': name, 'alpha2': alpha2})
    except Exception as e:
        print(f"[WARN] Failed to load countries CSV for signInGuest: {e}")

    return render_template('newSignInGuest.html', countries=countries)


_POSTCODE_LOOKUP_CACHE = None
_COUNTRY_ALPHA2_CACHE = None


def _build_postcode_lookup():
    """
    Build a lookup structure from json/all.json.
    Supports both explicit postcode lists and postcode ranges expressed as ["NNNNN","MMMMM"].
    """
    json_path = os.path.join(os.path.dirname(__file__), 'json', 'all.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    exact = {}
    ranges = []

    for state_obj in (data.get('state') or []):
        state_name = (state_obj.get('name') or '').strip()
        for city_obj in (state_obj.get('city') or []):
            city_name = (city_obj.get('name') or '').strip()
            postcodes = city_obj.get('postcode') or []

            # Normalize to list
            if isinstance(postcodes, str):
                postcodes = [postcodes]

            # Range encoding appears in the dataset as ["86900","86999"]
            if (
                isinstance(postcodes, list)
                and len(postcodes) == 2
                and all(isinstance(p, str) for p in postcodes)
                and all(p.strip().isdigit() for p in postcodes)
            ):
                a = int(postcodes[0].strip())
                b = int(postcodes[1].strip())
                if b > a + 1:
                    ranges.append((a, b, city_name, state_name))
                    continue

            for p in postcodes:
                if not isinstance(p, str):
                    continue
                code = p.strip()
                if not code:
                    continue
                # Some entries might not be 5 digits; still map exact string.
                exact.setdefault(code, (city_name, state_name))

    return {"exact": exact, "ranges": ranges}


def _lookup_postcode(postcode: str):
    global _POSTCODE_LOOKUP_CACHE
    if _POSTCODE_LOOKUP_CACHE is None:
        _POSTCODE_LOOKUP_CACHE = _build_postcode_lookup()

    code = (postcode or '').strip()
    if not code:
        return None

    exact = _POSTCODE_LOOKUP_CACHE["exact"]
    hit = exact.get(code)
    if hit:
        city, state = hit
        return {"postcode": code, "city": city, "state": state}

    if code.isdigit():
        n = int(code)
        for a, b, city, state in _POSTCODE_LOOKUP_CACHE["ranges"]:
            if a <= n <= b:
                return {"postcode": code, "city": city, "state": state}

    return None


def _load_country_alpha2_map():
    csv_path = os.path.join(os.path.dirname(__file__), 'csv', 'CountryCodeWNames.csv')
    name_to_alpha2 = {}
    with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get('name') or '').strip()
            alpha2 = (row.get('alpha-2') or '').strip()
            if name and alpha2:
                name_to_alpha2[name.lower()] = alpha2.upper()
    return name_to_alpha2


def _normalize_country_alpha2(value: str):
    """
    AR_CUSTOMERBRANCH.COUNTRY is commonly CHAR(2) in Firebird.
    Accept alpha-2 codes, or map full country names to alpha-2.
    """
    global _COUNTRY_ALPHA2_CACHE
    v = (value or '').strip()
    if not v:
        return ''
    if len(v) == 2:
        return v.upper()
    try:
        if _COUNTRY_ALPHA2_CACHE is None:
            _COUNTRY_ALPHA2_CACHE = _load_country_alpha2_map()
        return _COUNTRY_ALPHA2_CACHE.get(v.lower(), v)
    except Exception:
        return v


@app.route('/api/lookup_postcode', methods=['GET'])
def api_lookup_postcode():
    postcode = request.args.get('postcode', '').strip()
    if not postcode:
        return jsonify({'success': False, 'error': 'postcode is required'}), 400

    try:
        result = _lookup_postcode(postcode)
        if not result:
            return jsonify({'success': True, 'found': False, 'data': None})
        return jsonify({'success': True, 'found': True, 'data': result})
    except Exception as e:
        print(f"[ERROR] lookup_postcode failed: {e}")
        return jsonify({'success': False, 'error': 'Failed to lookup postcode'}), 500

def _login_otp_storage_key(email: str, login_mode: str) -> str:
    """OTP is scoped by login tab (customer / admin / supplier) so the same inbox can use different codes."""
    e = (email or '').strip().lower()
    m = (login_mode or 'customer').strip().lower()
    if m not in ('customer', 'admin', 'supplier'):
        m = 'customer'
    return f'{e}|{m}'


@app.route('/api/send_otp', methods=['POST'])
def api_send_otp():
    """Send OTP to email"""
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    login_mode = (data.get('login_mode') or 'customer').strip().lower()
    if login_mode not in ('customer', 'admin', 'supplier'):
        login_mode = 'customer'
    otp_key = _login_otp_storage_key(email, login_mode)
    print(f"[DEBUG OTP] send_otp requested for: {email} mode={login_mode}", flush=True)
    
    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400
    
    # ============================================
    # VALIDATION DISABLED FOR TESTING
    # Uncomment below to enable email validation
    # ============================================
    # import re
    # email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    # if not re.match(email_pattern, email):
    #     return jsonify({'success': False, 'error': 'Invalid email format'}), 400
    
    try:
        # Use FastAPI identity lookup so auth flow stays on API port (default: 8000).
        is_admin = False
        is_user = False
        is_customer = False
        try:
            identity_resp = requests.get(
                f"{FASTAPI_BASE_URL}/auth/email-lookup",
                params={"email": email, "login_mode": login_mode},
                timeout=5,
            )
            identity_resp.raise_for_status()
            identity = identity_resp.json()
            is_admin = bool(identity.get('is_admin'))
            is_user = bool(identity.get('is_user'))
            is_customer = bool(identity.get('is_customer'))
            is_supplier = bool(identity.get('is_supplier'))
        except Exception as e:
            print(f"[AUTH] FastAPI email lookup during send_otp failed: {e}")
            return jsonify({'success': False, 'error': 'Authentication lookup service unavailable'}), 500

        if not (is_admin or is_user or is_customer or is_supplier):
            print(f"[DEBUG OTP] rejected (email not found): {email}", flush=True)
            return jsonify({
                'success': False,
                'error': 'Email not found, please contact administrator'
            }), 401

        # Generate OTP
        otp = generate_otp(OTP_LENGTH)
        print(f"[DEBUG OTP] {email} -> {otp}", flush=True)
        expiry = datetime.now() + timedelta(seconds=OTP_EXPIRY_SECONDS)
        
        # Store OTP temporarily (keyed by email + login tab)
        OTP_STORAGE[otp_key] = {
            'otp': otp,
            'expiry': expiry
        }
        
        # Send OTP via email
        subject = "Your Login OTP Code"
        body = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <div style="background-color: #1a1f2e; color: #fff; padding: 20px; border-radius: 8px; max-width: 500px; margin: 0 auto;">
                    <h2>Login Verification</h2>
                    <p>Your OTP code is:</p>
                    <h1 style="background-color: #2d3440; padding: 15px; text-align: center; letter-spacing: 5px; font-weight: bold; border-radius: 4px;">
                        {otp}
                    </h1>
                    <p>This code expires in 1 minute.</p>
                    <p style="color: #888; font-size: 12px;">If you did not request this code, please ignore this email.</p>
                </div>
            </body>
        </html>
        """
        
        # Send email in background so OTP screen can render immediately.
        def send_otp_email_async(target_email, target_subject, target_body):
            try:
                send_email(target_email, target_subject, target_body)
            except Exception as mail_err:
                print(f"[DEBUG OTP] async send_email failed for {target_email}: {mail_err}", flush=True)

        threading.Thread(
            target=send_otp_email_async,
            args=(email, subject, body),
            daemon=True
        ).start()

        response_payload = {
            'success': True,
            'message': f'OTP sent to {email}',
            'expiry': OTP_EXPIRY_SECONDS
        }

        if app.debug:
            response_payload['debug_otp'] = otp

        return jsonify(response_payload), 200
    
    except Exception as e:
        print(f"[DEBUG OTP] send_otp error for {email}: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/verify_otp', methods=['POST'])
def api_verify_otp():
    """Verify OTP and create session, redirect based on user type"""
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    otp = data.get('otp', '').strip()
    login_mode = (data.get('login_mode') or 'customer').strip().lower()
    if login_mode not in ('customer', 'admin', 'supplier'):
        login_mode = 'customer'
    otp_key = _login_otp_storage_key(email, login_mode)
    
    if not email or not otp:
        return jsonify({'success': False, 'error': 'Email and OTP are required'}), 400
    
    try:
        # OTP validation (1-minute expiry + one-time use)
        if otp_key not in OTP_STORAGE:
            return jsonify({'success': False, 'error': 'OTP not found. Request a new one.'}), 400

        stored_data = OTP_STORAGE[otp_key]

        if datetime.now() > stored_data['expiry']:
            del OTP_STORAGE[otp_key]
            return jsonify({'success': False, 'error': 'OTP has expired. Request a new one.'}), 400

        if otp != stored_data['otp']:
            return jsonify({'success': False, 'error': 'Invalid OTP. Please try again.'}), 400

        # One-time use: consume OTP immediately after successful verification
        del OTP_STORAGE[otp_key]

        # Check identity via FastAPI so login checks stay on port 8000.
        try:
            identity_response = requests.get(
                f"{FASTAPI_BASE_URL}/auth/email-lookup",
                params={"email": email, "login_mode": login_mode},
                timeout=5,
            )
            identity_response.raise_for_status()
            identity = identity_response.json()
        except Exception as e:
            print(f"[AUTH] FastAPI identity lookup failed: {e}")
            return jsonify({
                'success': False,
                'error': 'Failed to verify customer credentials'
            }), 500

        access_tier = str(identity.get('access_tier') or '').strip()
        staff_udf = identity.get('staff_udf') if isinstance(identity.get('staff_udf'), dict) else {}
        user_type_hint = str(identity.get('user_type_hint') or 'user').strip()

        if identity.get('is_supplier'):
            user_type = 'supplier'
            redirect_url = '/supplier/bidding'
            customer_code = identity.get('supplier_code')
            print(f"[AUTH] Supplier user detected: {email} -> Supplier: {customer_code}")
        elif identity.get('is_user') or identity.get('is_customer'):
            customer_code = identity.get('customer_code')
            user_type = user_type_hint if user_type_hint in ('admin', 'user') else 'user'
            if access_tier == ACCESS_TIER_SALES_STAFF:
                user_type = 'user'
            if user_type == 'admin' and access_tier in (ACCESS_TIER_FULL_ADMIN, ACCESS_TIER_SALES_MGMT):
                redirect_url = '/admin'
            elif user_type == 'admin':
                redirect_url = f'{PROCUREMENT_UI_PATH}?tab=view'
            else:
                redirect_url = '/create-quotation'
            print(f"[AUTH] Customer path: {email} tier={access_tier} user_type={user_type}")
        elif identity.get('is_admin'):
            if access_tier == ACCESS_TIER_NO_ROLE:
                return jsonify({
                    'success': False,
                    'error': (
                        'No role is assigned for this account. '
                        'Ask an administrator to set one of UDF_MANAGEMENT, UDF_SMANAGEMENT, UDF_PMANAGEMENT, '
                        'UDF_SSTAFF, UDF_SUSER, or UDF_PUSER on SY_USER.'
                    ),
                }), 403
            customer_code = identity.get('customer_code')
            user_type = user_type_hint if user_type_hint in ('admin', 'user') else 'admin'
            if access_tier == ACCESS_TIER_SALES_STAFF:
                user_type = 'user'
                redirect_url = '/create-quotation'
            elif access_tier in (ACCESS_TIER_FULL_ADMIN, ACCESS_TIER_SALES_MGMT):
                user_type = 'admin'
                redirect_url = '/admin'
            elif access_tier in (ACCESS_TIER_PURCH_MGMT, ACCESS_TIER_PURCH_STAFF):
                user_type = 'admin'
                redirect_url = f'{PROCUREMENT_UI_PATH}?tab=view'
            else:
                return jsonify({
                    'success': False,
                    'error': 'Unrecognized access profile for this account. Contact an administrator.',
                }), 403
            print(f"[AUTH] SY_USER-only path: {email} tier={access_tier} user_type={user_type}")
        else:
            return jsonify({
                'success': False,
                'error': 'Email not found in customer or supplier records, please contact administrator'
            }), 401

        # OTP is valid - create session
        session['user_email'] = email
        session['access_tier'] = access_tier or ('supplier' if user_type == 'supplier' else 'customer')
        session['staff_udf'] = staff_udf
        session['user_type'] = user_type
        session['customer_code'] = customer_code  # Store customer/supplier code in session
        if user_type == 'supplier':
            session['supplier_code'] = customer_code
        session.permanent = True
        
        print(f"[SESSION] user_email: {email}")
        print(f"[SESSION] user_type: {user_type}")
        print(f"[SESSION] customer_code: {customer_code}")
        print(f"Login successful for {user_type}: {email} (Customer: {customer_code})")
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'redirect': redirect_url,
            'user_type': user_type
        }), 200
    
    except Exception as e:
        print(f"Error verifying OTP: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return redirect('/login')

@app.route('/php/getOrdersByStatus.php')
def proxy_get_orders_by_status():
    """Proxy endpoint to forward requests to XAMPP PHP with customer code filtering for non-admin users"""
    auth_error = require_api_auth()
    if auth_error:
        return auth_error
    
    status = request.args.get('status')
    if not status:
        return jsonify({'success': False, 'error': 'status parameter required'}), 400
    
    try:
        # Build URL with status
        url = f"{BASE_API_URL}{ENDPOINT_PATHS['getordersbystatus']}?status={status}"
        
        # For non-admin users, enforce customer code filtering server-side
        user_type = session.get('user_type', 'user')
        if user_type != 'admin':
            customer_code = session.get('customer_code')
            if customer_code:
                url += f"&customerCode={customer_code}"
        
        response = requests.get(url, timeout=10)
        return response.json(), response.status_code
    except Exception as e:
        print(f"Error proxying to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch orders from database'}), 500


@app.route('/php/updateOrderStatus.php', methods=['POST'])
def proxy_update_order_status():
    """Proxy endpoint to update order status via XAMPP PHP."""
    return proxy_post_with_auth(
        ENDPOINT_PATHS['updateorderstatus'],
        admin_only=True,
        error_message='Failed to update order status',
        log_context='status update'
    )


@app.route('/php/getOrderDetails.php')
def proxy_get_order_details():
    """Proxy endpoint to fetch order details via XAMPP PHP."""
    orderid = request.args.get('orderid')
    if not orderid:
        return jsonify({'success': False, 'error': 'orderid parameter required'}), 400

    return proxy_get_with_auth(
        ENDPOINT_PATHS['getorderdetails'],
        params={'orderid': orderid},
        error_message='Failed to fetch order details',
        log_context='getOrderDetails'
    )


@app.route('/php/updateOrderDetail.php', methods=['POST'])
def proxy_update_order_detail():
    """Proxy endpoint to update order detail via XAMPP PHP."""
    return proxy_post_with_auth(
        ENDPOINT_PATHS['updateorderdetail'],
        admin_only=True,
        error_message='Failed to update order detail',
        log_context='updateOrderDetail'
    )


@app.route('/php/insertOrderDetail.php', methods=['POST'])
def proxy_insert_order_detail():
    """Proxy endpoint to insert order detail via XAMPP PHP."""
    return proxy_post_with_auth(
        ENDPOINT_PATHS['insertorderdetail'],
        admin_only=True,
        error_message='Failed to insert order detail',
        log_context='insertOrderDetail'
    )


@app.route('/php/requestOrderChange.php', methods=['POST'])
def proxy_request_order_change():
    """Proxy endpoint to submit order change request."""
    return proxy_post_with_auth(
        '/php/requestOrderChange.php',
        error_message='Failed to submit change request',
        log_context='change request',
        timeout_message='Request timed out. Please check if XAMPP is running.',
        connection_message='Cannot connect to database server. Please ensure XAMPP is running.',
        include_exception_detail=True,
    )


@app.route('/php/getOrderRemarks.php')
def proxy_get_order_remarks():
    """Proxy endpoint to get order remarks."""
    orderid = request.args.get('orderid')
    if not orderid:
        return jsonify({'success': False, 'error': 'orderid parameter required'}), 400

    return proxy_get_with_auth(
        '/php/getOrderRemarks.php',
        params={'orderid': orderid},
        error_message='Failed to fetch remarks',
        log_context='getOrderRemarks'
    )

@app.route('/php/insertDraftQuotation.php', methods=['POST'])
def proxy_insert_draft_quotation():
    """Proxy endpoint to create draft quotation via XAMPP PHP."""
    return proxy_post_with_auth(
        '/php/insertDraftQuotation.php',
        error_message='Failed to create draft quotation',
        log_context='insertDraftQuotation'
    )

@app.route('/php/updateDraftQuotation.php', methods=['POST'])
def proxy_update_draft_quotation():
    """Proxy endpoint to update draft quotation via XAMPP PHP."""
    return proxy_post_with_auth(
        '/php/updateDraftQuotation.php',
        error_message='Failed to update draft quotation',
        log_context='updateDraftQuotation'
    )

@app.route('/admin')
def admin():
    """Display admin dashboard (full admin + sales management only)."""
    page_error = require_page_access()
    if page_error:
        return page_error
    if not can_access_admin_dashboard(session):
        if can_access_purchase_menu(session):
            return redirect(f'{PROCUREMENT_UI_PATH}?tab=view')
        return redirect('/chat')
    return render_protected_template('admin.html', require_admin=False)


@app.route('/admin/pending-approvals')
def admin_pending_approvals():
    """Pending approvals (full admin + purchasing roles)."""
    page_error = require_page_access(require_admin=True)
    if page_error:
        return page_error
    if not can_access_pending_approvals_admin(session):
        return redirect('/admin')
    return render_protected_template('adminApproval.html', require_admin=False, user_type='admin')




@app.route('/user/approvals')
def user_approvals():
    """Display user approvals page (regular users)."""
    return render_protected_template('userApproval.html')


@app.route('/user/draft-orders')
def user_draft_orders():
    """Display draft orders page (regular users)."""
    return render_protected_template('draftOrders.html')


@app.route('/create-order')
def create_order_page():
    """Display create order page (regular users)."""
    return render_protected_template('createOrder.html', block_admin=True, admin_redirect='/admin')

@app.route('/create-quotation')
def create_quotation_page():
    """Create quotation (customers + sales-capable staff + full admin; not supplier / purchasing-only)."""
    page_error = require_page_access()
    if page_error:
        return page_error
    if not can_access_create_quotation(session):
        if session.get('user_type') == 'supplier':
            return redirect('/supplier/bidding')
        if can_access_purchase_menu(session):
            return redirect(f'{PROCUREMENT_UI_PATH}?tab=view')
        return redirect('/chat')
    dockey = request.args.get('dockey', '')
    draft_dockey = request.args.get('draftDockey', '')
    return render_protected_template(
        'createQuotation.html',
        dockey=dockey,
        draft_dockey=draft_dockey,
        php_base_url=BASE_API_URL,
        require_admin=False,
    )


@app.route('/view-quotation')
def view_quotation_page():
    """Customer quotation list (not purchasing-only roles)."""
    page_error = require_page_access()
    if page_error:
        return page_error
    if session.get('user_type') == 'admin':
        return redirect('/admin/view-quotations')
    if not can_access_view_quotation_customer_ui(session):
        if can_access_purchase_menu(session):
            return redirect(f'{PROCUREMENT_UI_PATH}?tab=view')
        return redirect('/chat')
    return render_protected_template(
        'viewQuotation.html',
        require_admin=False,
        user_type=session.get('user_type', ''),
    )

@app.route('/admin/view-quotations')
def admin_view_quotations():
    """List all quotations (full admin + sales management)."""
    page_error = require_page_access(require_admin=True)
    if page_error:
        return page_error
    if not can_access_admin_view_quotations(session):
        return redirect('/admin')
    return render_protected_template(
        'adminViewQuotations.html',
        require_admin=False,
        user_type=session.get('user_type', ''),
    )


@app.route('/admin/delete-quotations')
def admin_delete_quotations():
    """Delete quotations UI (full admin + sales management)."""
    page_error = require_page_access(require_admin=True)
    if page_error:
        return page_error
    if not can_access_admin_view_quotations(session):
        return redirect('/admin')
    return render_protected_template(
        'deleteQuotations.html',
        require_admin=False,
        user_type=session.get('user_type', ''),
    )


@app.route('/admin/pricing-priority-rules')
def admin_pricing_priority_rules():
    """Pricing priority rules (UDF_MANAGEMENT full admin only)."""
    return render_protected_template(
        'pricingPriorityRules.html',
        require_admin=True,
        require_full_management_admin=True,
        user_type=session.get('user_type', 'admin')
    )

@app.route('/admin/procurement')
def admin_procurement_module():
    """Procurement module — canonical URL (tab=report|create|view)."""
    page_error = require_page_access()
    if page_error:
        return page_error
    if not can_access_purchase_menu(session):
        return redirect('/admin' if can_access_admin_dashboard(session) else '/chat')
    ctx = {'user_type': session.get('user_type', ''), 'user_email': session.get('user_email', '')}
    ctx.update(template_permission_context(session))
    return render_template('precurement/precurement.html', **ctx)


@app.route('/admin/precurement/precurement')
def admin_procurement_legacy_typo_redirect():
    """Permanent redirect from legacy typo URL to /admin/procurement."""
    page_error = require_page_access()
    if page_error:
        return page_error
    if not can_access_purchase_menu(session):
        return redirect('/admin' if can_access_admin_dashboard(session) else '/chat')
    tab = request.args.get('tab') or 'report'
    return redirect(f'{PROCUREMENT_UI_PATH}?tab={quote(str(tab), safe="")}', code=308)
@app.route('/admin/procurement/bidding')
def admin_procurement_bidding_page():
    """Display admin supplier bidding management page."""
    page_error = require_page_access(require_admin=True)
    if page_error:
        return page_error
    if not can_access_purchase_menu(session) and not can_access_admin_dashboard(session):
        return redirect('/chat')
    return render_protected_template(
        'adminBidding.html',
        require_admin=False,
        user_type=session.get('user_type', 'admin'),
        user_name=session.get('user_email', ''),
    )


@app.route('/supplier/bidding')
def supplier_bidding_page():
    """Supplier RFQ bidding portal (supplier tier only)."""
    page_error = require_page_access()
    if page_error:
        return page_error
    if infer_access_tier_from_session(session) != ACCESS_TIER_SUPPLIER:
        if can_access_purchase_menu(session):
            return redirect(f'{PROCUREMENT_UI_PATH}?tab=view')
        return redirect('/chat')
    return render_protected_template(
        'supplierBidding.html',
        block_admin=True,
        admin_redirect=PROCUREMENT_UI_PATH,
        user_type=session.get('user_type', 'user'),
        supplier_code=session.get('supplier_code') or session.get('customer_code', ''),
        user_name=session.get('user_email', ''),
    )


@app.route('/admin/invoice-aging')
def admin_invoice_aging():
    """Display invoice aging analytics page (admin only)."""
    r = _redirect_purchasing_roles_from_sales_analytics_pages()
    if r:
        return r
    return render_protected_template(
        'adminInvoiceAging.html',
        require_admin=True,
        user_type=session.get('user_type', 'admin')
    )


@app.route('/admin/sales-cycle')
def admin_sales_cycle():
    """Display sales cycle analytics page (admin only)."""
    r = _redirect_purchasing_roles_from_sales_analytics_pages()
    if r:
        return r
    return render_protected_template(
        'adminSalesCycle.html',
        require_admin=True,
        user_type=session.get('user_type', 'admin')
    )


@app.route('/admin/conversion-rate')
def admin_conversion_rate():
    """Display quotation-to-invoice conversion rate analytics page (admin only)."""
    r = _redirect_purchasing_roles_from_sales_analytics_pages()
    if r:
        return r
    return render_protected_template(
        'adminConversionRate.html',
        require_admin=True,
        user_type=session.get('user_type', 'admin')
    )


@app.route('/admin/update-quotation')
def admin_update_quotation():
    """Display update quotation page (admin only)."""
    r = _redirect_purchasing_roles_from_sales_analytics_pages()
    if r:
        return r
    dockey = request.args.get('dockey', '')
    if not dockey:
        return "Missing dockey parameter", 400
    return render_protected_template(
        'updateQuotation.html',
        require_admin=True,
        dockey=dockey,
    )


@app.route('/admin/pending-approvals/edit/<int:orderid>')
def admin_edit_approval(orderid):
    """Display admin edit approval page."""
    page_error = require_page_access(require_admin=True)
    if page_error:
        return page_error
    if not can_access_pending_approvals_admin(session):
        return redirect('/admin')
    return render_protected_template('admin_edit_approval.html', require_admin=False, orderid=orderid)


@app.route('/admin/api/update-order', methods=['POST'])
@api_admin_required(unauth_message='Not authenticated', forbidden_message='Insufficient permissions')
def admin_update_order():
    """Admin API endpoint to update order status and order detail rows."""
    data = request.get_json() or {}
    orderid = data.get('orderid')
    status = data.get('status')
    items = data.get('items', [])

    if not orderid or not status:
        return jsonify({'success': False, 'error': 'Missing orderid or status'}), 400

    def parse_backend_json(response, endpoint_name):
        try:
            return response.json()
        except ValueError:
            body_preview = (response.text or '').strip().replace('\n', ' ')[:300]
            raise ValueError(
                f"{endpoint_name} returned non-JSON response (HTTP {response.status_code}): {body_preview or 'empty body'}"
            )

    try:
        status_response = requests.post(
            f"{BASE_API_URL}{ENDPOINT_PATHS['updateorderstatus']}",
            json={'orderid': orderid, 'status': status},
            timeout=10
        )
        status_response.raise_for_status()
        status_data = parse_backend_json(status_response, ENDPOINT_PATHS['updateorderstatus'])

        if not status_data.get('success'):
            return jsonify({'success': False, 'error': status_data.get('error', 'Failed to update order status')}), 500

        for item in items:
            item_payload = {
                'orderid': item.get('orderid', orderid),
                'description': item.get('description', ''),
                'qty': item.get('qty', 0),
                'unitprice': item.get('unitprice', 0),
                'discount': item.get('discount', 0)
            }

            item_orderdtlid = int(item.get('orderdtlid') or 0)

            if item_orderdtlid > 0:
                item_payload['orderdtlid'] = item_orderdtlid
                endpoint_path = ENDPOINT_PATHS['updateorderdetail']
                item_response = requests.post(
                    f"{BASE_API_URL}{endpoint_path}",
                    json=item_payload,
                    timeout=10
                )
            else:
                endpoint_path = ENDPOINT_PATHS['insertorderdetail']
                item_response = requests.post(
                    f"{BASE_API_URL}{endpoint_path}",
                    json=item_payload,
                    timeout=10
                )

            item_response.raise_for_status()
            item_data = parse_backend_json(item_response, endpoint_path)
            if not item_data.get('success'):
                return jsonify({'success': False, 'error': item_data.get('error', 'Failed to update order item')}), 500

        return jsonify({'success': True, 'message': 'Order updated successfully'}), 200
    except requests.exceptions.RequestException as e:
        print(f"Error updating order from admin API: {e}")
        return jsonify({'success': False, 'error': f'Failed to update order: {str(e)}'}), 500
    except Exception as e:
        print(f"Unexpected error updating order from admin API: {e}")
        return jsonify({'success': False, 'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/order/proof/<int:orderid>')
def view_order_proof(orderid):
    """Display order proof/receipt (requires authentication)"""
    if 'user_email' not in session:
        return redirect('/login')
    
    user_email = session.get('user_email')
    user_type = session.get('user_type', 'user')
    
    try:
        # Fetch order from PHP endpoint
        order_response = requests.get(
            f"{BASE_API_URL}/php/getOrderDetails.php?orderid={orderid}",
            timeout=10
        )
        order_response.raise_for_status()
        order_data = order_response.json()
        
        if not order_data.get('success') or not order_data.get('data'):
            return jsonify({'error': 'Order not found'}), 404
        
        order = order_data['data']
        
        # Verify ownership for regular users
        if user_type == 'user':
            conn = fdb.connect(dsn=DB_DSN, user=DB_USER, password=DB_PASSWORD)
            cur = conn.cursor()
            cur.execute('''
                SELECT OWNEREMAIL FROM CHAT_TPL WHERE CHATID = ? 
            ''', (order['CHATID'],))
            result = cur.fetchone()
            cur.close()
            conn.close()
            
            if not result or result[0] != user_email:
                return jsonify({'error': 'Forbidden'}), 403
        
        # Calculate totals
        subtotal = 0
        total_discount = 0
        
        if order.get('items'):
            for item in order['items']:
                item_qty = item.get('QTY', 0)
                item_price = item.get('UNITPRICE', 0)
                item_discount = item.get('DISCOUNT', 0)
                subtotal += (item_qty * item_price)
                total_discount += item_discount
        grand_total = subtotal - total_discount
        
        # Format date
        created_date = order['CREATEDAT']
        if isinstance(created_date, str):
            created_date = datetime.fromisoformat(created_date.replace('Z', '+00:00')).strftime('%d %b %Y, %H:%M:%S')
        else:
            created_date = created_date.strftime('%d %b %Y, %H:%M:%S')
        
        return render_template(
            'orderReceipt.html',
            order=order,
            customer_email=user_email,
            subtotal=subtotal,
            total_discount=total_discount,
            grand_total=grand_total,
            created_date=created_date,
            current_date=datetime.now().strftime('%d %b %Y, %H:%M:%S')
        )
    
    except Exception as e:
        print(f'Error fetching order proof: {e}')
        return jsonify({'error': 'Error fetching order proof'}), 500

@app.route('/')
def index():
    if 'user_email' in session:
        user_type = session.get('user_type', 'user')
        if user_type == 'supplier':
            return redirect('/supplier/bidding')
        if user_type == 'admin':
            if can_access_admin_dashboard(session):
                return redirect('/admin')
            if can_access_purchase_menu(session):
                return redirect(f'{PROCUREMENT_UI_PATH}?tab=view')
            return redirect('/chat')
        return redirect('/create-quotation')
    return redirect('/login')

@app.route('/chat', methods=['GET'])
def chat():
    """Display chat page (requires authentication and must be regular user)"""
    page_error = require_page_access(block_admin=True, admin_redirect='/admin')
    if page_error:
        return page_error
    return render_template('chat.html', user_email=session.get('user_email', ''))

@app.route('/chat', methods=['POST'])
@api_login_required(unauth_message='Unauthorized')
def chat_api():
    user_email = (session.get('user_email') or session.get('user_name') or '').strip()
    user_input = request.json.get('message')
    chatid = request.json.get('chatid')

    if not chatid:
        return jsonify({'success': False, 'error': 'chatid required'}), 400

    if not user_email:
        return jsonify({'success': False, 'error': 'User identity required for chat'}), 400

    if not user_owns_chat(chatid, user_email):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    
    # Fetch chat history if chatid provided
    chat_history = []
    if chatid:
        chat_history = get_chat_history(chatid, user_email)
    
    # Stock catalog: PHP bridge (BASE_API_URL) when available; else same Firebird as /api/get_stock_items
    stockitems = fetch_data_from_api("stockitem")
    stockitemprices = fetch_data_from_api("stockitemprice")
    if not stockitems or not stockitemprices:
        con_fb = None
        cur_fb = None
        try:
            con_fb = get_db_connection()
            cur_fb = con_fb.cursor()
            if not stockitems:
                stockitems = fetch_stock_items(cur_fb)
            if not stockitemprices:
                stockitemprices = fetch_stock_item_prices_for_chat(cur_fb)
        except Exception as e:
            print(f"[chat] stock data DB fallback: {e}", flush=True)
        finally:
            try:
                if cur_fb:
                    cur_fb.close()
            except Exception:
                pass
            try:
                if con_fb:
                    con_fb.close()
            except Exception:
                pass

    price_lookup_by_desc = {
        (item.get('DESCRIPTION', '') or '').lower(): item.get('STOCKVALUE')
        for item in stockitemprices
        if item.get('DESCRIPTION')
    }
    formatted_stockitemprices = []
    for item in stockitemprices:
        formatted_item = dict(item)
        formatted_item['STOCKVALUE'] = format_rm(item.get('STOCKVALUE'))
        formatted_stockitemprices.append(formatted_item)

    def format_section(items, fields=None, numbered=False):
        if not items:
            return ""
        lines = []
        for i, item in enumerate(items):
            if fields:
                vals = [str(item.get(f, '-')) for f in fields]
                line = (f"{i+1}. " if numbered else "- ") + " | ".join(vals)
            else:
                line = (f"{i+1}. " if numbered else "- ") + str(item)
            lines.append(line)
        return "\n".join(lines)

    stock_items_block = format_section(stockitems, ['DESCRIPTION', 'STOCKGROUP'], numbered=True)
    stock_prices_block = format_section(formatted_stockitemprices, ['CODE', 'STOCKVALUE'])
    stock_groups = sorted({
        str(item.get('STOCKGROUP', '') or '').strip()
        for item in stockitems
        if str(item.get('STOCKGROUP', '') or '').strip()
    })

    messages = []

    # Add business rules/system instructions first
    if CHATBOT_SYSTEM_INSTRUCTIONS.strip():
        messages.append({
            "role": "system",
            "content": CHATBOT_SYSTEM_INSTRUCTIONS.strip()
        })

    # Add stock data context only when relevant to avoid repetitive/static replies.
    stock_context_parts = []
    if should_include_stock_context(user_input):
        if stock_groups:
            stock_context_parts.append(
                "Available Stock Groups (use these as the product categories when the user asks what types/categories/groups you sell):\n"
                + "\n".join(f"- {stock_group}" for stock_group in stock_groups)
            )
        if stock_items_block:
            stock_context_parts.append(f"Available Stock Items:\n{stock_items_block}")
        if stock_prices_block:
            stock_context_parts.append(f"Stock Item Prices:\n{stock_prices_block}")
    if stock_context_parts:
        messages.append({
            "role": "system",
            "content": "\n\n".join(stock_context_parts)
        })

    limited_chat_history = chat_history[-MAX_HISTORY_MESSAGES:]

    for msg in limited_chat_history:
        sender = (msg.get('SENDER') or '').strip().lower()
        text = (msg.get('MESSAGETEXT') or '').strip()
        if not text:
            continue
        role = "assistant" if sender == "system" else "user"
        messages.append({"role": role, "content": text})

    messages.append({"role": "user", "content": user_input})
    
    # ============================================
    # ORDER MANAGEMENT LOGIC
    # ============================================
    order_action = parse_order_intent(user_input)
    order_response = None
    orderid = None
    
    # Debug: Log detected intent
    if order_action:
        print(f"[DEBUG] Detected order intent: '{order_action}' for input: '{user_input[:50]}...'", flush=True)
    
    if order_action:
        if order_action == 'create':
            # Create new order only when user explicitly requests it
            try:
                response = requests.post(
                    f"{BASE_API_URL}/php/insertOrder.php",
                    json={"chatid": chatid}
                )
                data = response.json()
                if data.get('success'):
                    orderid = data.get('orderid')
                    order_response = f"✓ Order #{orderid} created. What items would you like to add?"
                else:
                    order_response = f"❌ Could not create order: {data.get('error')}"
            except Exception as e:
                order_response = f"❌ Error creating order: {str(e)}"
        
        elif order_action == 'add':
            # Add item to order (create order if none exists for this chat)
            orderid = get_active_order(chatid)
            if not orderid:
                # No active order - create one automatically when adding items
                try:
                    response = requests.post(
                        f"{BASE_API_URL}/php/insertOrder.php",
                        json={"chatid": chatid}
                    )
                    data = response.json()
                    if data.get('success'):
                        orderid = data.get('orderid')
                    else:
                        order_response = f"❌ Could not create order: {data.get('error')}"
                except Exception as e:
                    order_response = f"❌ Error creating order: {str(e)}"
            
            if orderid:
                product_info = extract_product_and_quantity(user_input, stockitems, chat_history)
                if product_info:
                    unitprice = get_product_price(product_info, stockitemprices)
                    if unitprice:
                        order_response = add_order_item(orderid, product_info, unitprice)
                    else:
                        # Product not found - provide suggestions with prices
                        searched_term = product_info['description']
                        suggestions = build_product_suggestions(
                            searched_term,
                            stockitems,
                            price_lookup=price_lookup_by_desc,
                            require_price=True
                        )
                        
                        if suggestions:
                            suggestions_text = "\n- ".join([f"{desc} ({price})" for desc, price in suggestions])
                            order_response = f"Select which one:\n- {suggestions_text}"
                        else:
                            order_response = f"Product '{searched_term}' not found in our catalog."
                else:
                    order_response = "Could not understand the product and quantity. Try: 'I want 5 units of Product A'"
            else:
                order_response = "No active order found. Please start a new order first."
        
        elif order_action == 'update':
            # Update item quantity logic
            orderid = get_active_order(chatid)
            if orderid:
                product_info = extract_product_and_quantity(user_input, stockitems, chat_history)
                if product_info and product_info.get('description'):
                    # Find the order detail ID for this product
                    details_resp = requests.get(f"{BASE_API_URL}/php/getOrderDetails.php?orderid={orderid}")
                    details = details_resp.json().get('data', [])
                    detail_id = None
                    for d in details:
                        if d.get('DESCRIPTION', '').lower() == product_info['description'].lower():
                            detail_id = d.get('ID') or d.get('DETAILID') or d.get('id')
                            break
                    if detail_id:
                        try:
                            response = requests.post(
                                f"{BASE_API_URL}/php/updateOrderDetail.php",
                                json={
                                    "detailid": detail_id,
                                    "qty": product_info['qty']
                                }
                            )
                            data = response.json()
                            if data.get('success'):
                                order_response = f"✓ Updated {product_info['description']} to {product_info['qty']}x."
                            else:
                                order_response = f"Error updating item: {data.get('error')}"
                        except Exception as e:
                            order_response = f"Error updating item: {str(e)}"
                    else:
                        order_response = f"Could not find item '{product_info['description']}' in your order."
                else:
                    order_response = "Could not understand which item to update. Try: 'Update 3 units of Product A'"
            else:
                order_response = "No active order to update. Please create an order first."

        elif order_action == 'remove_all':
            # Remove all items from order logic
            orderid = get_active_order(chatid)
            if orderid:
                try:
                    details_resp = requests.get(f"{BASE_API_URL}/php/getOrderDetails.php?orderid={orderid}")
                    details = details_resp.json().get('data', [])
                    removed = 0
                    for d in details:
                        detail_id = d.get('ID') or d.get('DETAILID') or d.get('id')
                        if detail_id:
                            try:
                                requests.post(
                                    f"{BASE_API_URL}/php/deleteOrderDetail.php",
                                    json={"detailid": detail_id}
                                )
                                removed += 1
                            except Exception:
                                pass
                    order_response = f"✓ Removed all items from your order."
                except Exception as e:
                    order_response = f"Error removing all items: {str(e)}"
            else:
                order_response = "No active order to clear. Please create an order first."
        elif order_action == 'remove':
            # Remove single item logic
            orderid = get_active_order(chatid)
            if orderid:
                product_info = extract_product_and_quantity(user_input, stockitems, chat_history)
                if product_info and product_info.get('description'):
                    details_resp = requests.get(f"{BASE_API_URL}/php/getOrderDetails.php?orderid={orderid}")
                    details = details_resp.json().get('data', [])
                    detail_id = None
                    for d in details:
                        if d.get('DESCRIPTION', '').lower() == product_info['description'].lower():
                            detail_id = d.get('ID') or d.get('DETAILID') or d.get('id')
                            break
                    if detail_id:
                        try:
                            response = requests.post(
                                f"{BASE_API_URL}/php/deleteOrderDetail.php",
                                json={"detailid": detail_id}
                            )
                            data = response.json()
                            if data.get('success'):
                                order_response = f"✓ Removed {product_info['description']} from your order."
                            else:
                                order_response = f"Error removing item: {data.get('error')}"
                        except Exception as e:
                            order_response = f"Error removing item: {str(e)}"
                    else:
                        order_response = f"Could not find item '{product_info['description']}' in your order."
                else:
                    order_response = "Could not understand which item to remove. Try: 'Remove Product A'"
            else:
                order_response = "No active order to remove items from. Please create an order first."
        
        elif order_action == 'complete':
            # Complete order
            orderid = get_active_order(chatid)
            if orderid:
                try:
                    response = requests.post(
                        f"{BASE_API_URL}/php/completeOrder.php",
                        json={"orderid": orderid}
                    )
                    data = response.json()
                    if data.get('success'):
                        grand_total = format_rm(data.get('grandTotal'))
                        order_response = f"✓ Order #{orderid} submitted for approval!\nGrand Total: {grand_total}\n\nYour order is now pending admin approval."
                    else:
                        order_response = f"Error completing order: {data.get('error')}"
                except Exception as e:
                    order_response = f"Error completing order: {str(e)}"
    
    # ============================================
    # FALLBACK: Direct Product Mention with Active Order
    # ============================================
    # If no order action detected but there's an active draft order,
    # check if user mentioned a product (implicit add)
    if not order_response:
        orderid = get_active_order(chatid)
        if orderid:
            print(f"[DEBUG] No intent detected, but active order exists. Checking for product mention...", flush=True)
            product_info = extract_product_and_quantity(user_input, stockitems, chat_history)
            if product_info and product_info.get('matched'):
                # User mentioned a product with active order - treat as 'add'
                print(f"[DEBUG] Product mention detected! Auto-adding: {product_info['description']}", flush=True)
                unitprice = get_product_price(product_info, stockitemprices)
                if unitprice:
                    order_response = add_order_item(orderid, product_info, unitprice)
                else:
                    # Price not found - provide suggestions with verified prices
                    searched_term = product_info['description']
                    suggestions = build_product_suggestions(
                        searched_term,
                        stockitemprices,
                        price_lookup=None,
                        require_price=True
                    )
                    
                    if suggestions:
                        suggestions_text = "\n- ".join([f"{desc} ({price})" for desc, price in suggestions])
                        order_response = f"Select which one:\n- {suggestions_text}"
                    else:
                        order_response = f"Sorry, '{searched_term}' not available."
    
    catalog_response = None
    if not order_response:
        catalog_response = build_catalog_response(user_input, stockitems, stock_groups, price_lookup_by_desc, chat_history=chat_history)

    # If order handling happened, use order response, otherwise use catalog response or GPT
    if order_response:
        formatted_reply = order_response
    elif catalog_response:
        formatted_reply = catalog_response
    else:
        try:
            response = chat_with_gpt(messages)
            formatted_reply = format_chatbot_response(response.strip())
            print(
                f"[DEBUG] Original response length: {len(response)}, Formatted length: {len(formatted_reply)}",
                flush=True,
            )
        except openai.RateLimitError as e:
            print(f"[ERROR] OpenAI rate limit / quota: {e}", flush=True)
            formatted_reply = (
                "The AI assistant cannot respond: your OpenAI account has no usable quota "
                "(for example billing limit or credits exhausted). "
                "Update billing at https://platform.openai.com/account/billing , then try again."
            )
        except openai.AuthenticationError as e:
            print(f"[ERROR] OpenAI authentication: {e}", flush=True)
            formatted_reply = (
                "The AI assistant cannot respond: the OpenAI API key is invalid or revoked. "
                "Check OPENAI_API_KEY in your server configuration."
            )
        except openai.APIError as e:
            print(f"[ERROR] OpenAI API error: {e}", flush=True)
            formatted_reply = (
                "The AI assistant hit an error talking to OpenAI. Please try again in a moment."
            )
        except Exception as e:
            print(f"[ERROR] chat_with_gpt unexpected: {e}", flush=True)
            formatted_reply = (
                "Sorry, the AI assistant encountered an unexpected error. Please try again later."
            )
    
    # Save messages if chatid provided
    if chatid:
        try:
            # Truncate messages to 4000 characters for database field limit (after db_initializer.py runs)
            user_msg = user_input[:4000] if len(user_input) > 4000 else user_input
            system_msg = formatted_reply[:4000] if len(formatted_reply) > 4000 else formatted_reply
            
            # Save user message
            insert_chat_message(chatid, "User", user_msg)
            # Save system response
            insert_chat_message(chatid, "System", system_msg)

            # Ensure chat preview shows latest system reply
            update_chat_last_message(chatid, system_msg, user_email)
        except Exception as e:
            print(f"Failed to save messages: {e}")
    
    return jsonify({'reply': formatted_reply})

# Endpoint to list all PHP API endpoints in the php folder
@app.route('/api/list_php_endpoints', methods=['GET'])
def list_php_endpoints():
    php_dir = os.path.join(os.path.dirname(__file__), 'php')
    endpoints = []
    for fname in os.listdir(php_dir):
        if fname.endswith('.php') and not fname.startswith('db_helper'):
            endpoints.append(f'/php/{fname}')
    return jsonify({'endpoints': endpoints})

@app.route('/get_chats')
@api_login_required(unauth_message='Unauthorized')
def get_chats():
    customer_code = session.get('customer_code')
    if not customer_code:
        return jsonify({'success': False, 'error': 'Customer code not found'}), 400
    
    try:
        # Call PHP endpoint to get chats
        response = requests.get(f"{BASE_API_URL}/php/getChats.php?customerCode={customer_code}")
        data = response.json()
        
        if data.get('success'):
            return jsonify({'success': True, 'chats': data.get('chats', [])})
        else:
            return jsonify({'success': False, 'error': data.get('error', 'Failed to fetch chats')}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_active_order')
@api_login_required(unauth_message='Unauthorized')
def api_get_active_order():
    """Get active DRAFT order for a chat"""
    chatid = request.args.get('chatid')
    if not chatid:
        return jsonify({'success': False, 'error': 'chatid required'}), 400

    if not user_owns_chat(chatid, session.get('user_email')):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    
    try:
        orderid = get_active_order(chatid)
        if orderid:
            # Fetch order details
            response = requests.get(f"{BASE_API_URL}/php/getOrderDetails.php?orderid={orderid}")
            order_data = response.json()
            return jsonify({'success': True, 'orderid': orderid, 'order': order_data})
        else:
            return jsonify({'success': True, 'orderid': None, 'order': None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/update_order_status', methods=['POST'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Forbidden')
def api_admin_update_order_status():
    """Admin endpoint to update order status (e.g., COMPLETED / CANCELLED)."""
    data = request.get_json() or {}
    orderid = data.get('orderid')
    status = (data.get('status') or '').upper().strip()

    if not orderid or not status:
        return jsonify({'success': False, 'error': 'orderid and status are required'}), 400

    valid_statuses = {'PENDING', 'COMPLETED', 'CANCELLED'}
    if status not in valid_statuses:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400

    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute('UPDATE ORDER_TPL SET STATUS = ? WHERE ORDERID = ?', (status, orderid))
        con.commit()
        updated = cur.rowcount
        cur.close()
        con.close()

        if not updated:
            return jsonify({'success': False, 'error': 'Order not found'}), 404

        return jsonify({'success': True, 'orderid': orderid, 'status': status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/insert_chat', methods=['POST'])
@api_login_required(unauth_message='Unauthorized')
def api_insert_chat():
    data = request.get_json()
    chat_name = data.get('chatname', '').strip()
    if not chat_name:
        return jsonify({'success': False, 'error': 'Chat name required'}), 400
    try:
        con = get_db_connection()
        cur = con.cursor()
        created_at = datetime.now()
        user_email = (session.get('user_email') or session.get('user_name') or '').strip()
        if not user_email:
            return jsonify({'success': False, 'error': 'User identity required for chat (missing session email)'}), 400
        customer_code = session.get('customer_code')  # Get customer code from session
        
        cur.execute('SELECT COALESCE(MAX(CHATID), 0) + 1 FROM CHAT_TPL')
        chatid = cur.fetchone()[0]
        
        # Welcome message for new chat (must be under 255 characters)
        welcome_message = (
            "👋 Hello! I'm your ordering assistant.\n\n"
            "I'm here to help you with any questions about products and orders.\n\n"
            "What would you like to know?"
        )
        
        cur.execute(
            'INSERT INTO CHAT_TPL (CHATID, CHATNAME, CREATEDAT, LASTMESSAGE, OWNEREMAIL, CUSTOMERCODE) VALUES (?, ?, ?, ?, ?, ?)',
            (chatid, chat_name, created_at, welcome_message, user_email, customer_code)
        )
        
        # Insert welcome message into chat history
        cur.execute('SELECT COALESCE(MAX(MESSAGEID), 0) + 1 FROM CHAT_TPLDTL')
        messageid_result = cur.fetchone()
        messageid = messageid_result[0] if messageid_result else 1
        
        cur.execute(
            'INSERT INTO CHAT_TPLDTL (MESSAGEID, CHATID, SENDER, MESSAGETEXT, SENTAT) VALUES (?, ?, ?, ?, ?)',
            (messageid, chatid, 'System', welcome_message, created_at)
        )
        
        con.commit()
        cur.close()
        con.close()
        
        print(f"[INFO] Chat {chatid} created successfully with welcome message")
        
        return jsonify({'success': True, 'chat': {
            'CHATID': chatid,
            'CHATNAME': chat_name,
            'CREATEDAT': created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'LASTMESSAGE': welcome_message,
            'OWNEREMAIL': user_email
        }})
    except Exception as e:
        print(f"[ERROR] Failed to create chat: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get_chat_details')
@api_login_required(unauth_message='Unauthorized')
def get_chat_details():
    chatid = request.args.get('chatid')
    if not chatid:
        return jsonify({'success': False, 'error': 'chatid required'}), 400

    user_email = session.get('user_email')

    if not user_owns_chat(chatid, user_email):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    try:
        details = get_chat_history(chatid, user_email)
        return jsonify({'success': True, 'details': details})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/check_draft_order')
@api_login_required(unauth_message='Unauthorized')
def check_draft_order():
    """Check if a chat has an active DRAFT order"""
    chatid = request.args.get('chatid')
    if not chatid:
        return jsonify({'success': False, 'error': 'chatid required'}), 400

    if not user_owns_chat(chatid, session.get('user_email')):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    
    try:
        con = get_db_connection()
        cur = con.cursor()
        order_id = find_draft_order_id_by_chatid(cur, chatid)
        cur.close()
        con.close()
        
        if order_id is not None:
            return jsonify({'success': True, 'hasDraft': True, 'orderid': order_id})
        else:
            return jsonify({'success': True, 'hasDraft': False})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/check_user_has_draft')
@api_login_required(unauth_message='Unauthorized')
def check_user_has_draft():
    """Check if the user has any DRAFT orders across all chats"""
    user_email = session.get('user_email')
    customer_code = session.get('customer_code')
    
    try:
        con = get_db_connection()
        cur = con.cursor()
        has_draft = has_user_draft_orders(cur, user_email, customer_code)
        cur.close()
        con.close()
        
        return jsonify({'success': True, 'hasDraft': has_draft})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_stock_items')
@api_login_required(unauth_message='Unauthorized')
def api_get_stock_items():
    """Get stock items for autocomplete in order/quotation forms"""
    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        items = fetch_stock_items(cur)

        return jsonify({'success': True, 'items': items})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e), 'items': []}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if con:
                con.close()
        except Exception:
            pass


@app.route('/api/admin/procurement/locations')
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_procurement_locations():
    """Return warehouse/stock location codes for purchase request line dropdowns."""
    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute("SELECT TRIM(CODE) FROM ST_LOCATION ORDER BY CODE")
        locations = []
        for row in cur.fetchall() or []:
            if not row or row[0] is None:
                continue
            code = str(row[0]).strip()
            if code:
                locations.append(code)
        return jsonify({'success': True, 'locations': locations})
    except Exception as e:
        print(f"[PROCUREMENT LOCATIONS] DB error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e), 'locations': []}), 500
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


@app.route('/api/admin/procurement/stock-card')
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_procurement_stock_card():
    """Return stock card table rows for procurement overall report."""
    raw_from_date = (request.args.get('from_date') or '').strip()
    raw_to_date = (request.args.get('to_date') or '').strip()
    qty_mode = (request.args.get('qty_mode') or 'SQTY').strip().upper()
    if qty_mode not in ('SQTY', 'SUOMQTY'):
        qty_mode = 'SQTY'

    from_date = None
    to_date = None
    try:
        if raw_from_date:
            from_date = datetime.fromisoformat(raw_from_date).date()
        if raw_to_date:
            to_date = datetime.fromisoformat(raw_to_date).date()
    except ValueError:
        return jsonify({'success': False, 'error': 'from_date and to_date must be YYYY-MM-DD'}), 400

    if from_date and to_date and from_date > to_date:
        return jsonify({'success': False, 'error': 'from_date cannot be after to_date'}), 400

    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        locations, data = fetch_procurement_stock_card_data(
            cur, from_date=from_date, to_date=to_date, qty_mode=qty_mode
        )
        st_tr_udf_suomqty = fetch_st_tr_udf_suomqty_summary(cur)

        return jsonify({
            'success': True,
            'count': len(data),
            'filters': {
                'from_date': from_date.isoformat() if from_date else None,
                'to_date': to_date.isoformat() if to_date else None,
                'qty_mode': qty_mode,
            },
            'locations': locations,
            'data': data,
            'st_tr_udf_suomqty': st_tr_udf_suomqty,
        })
    except Exception as e:
        print(f"[PROCUREMENT STOCK CARD] DB error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


@app.route('/api/admin/procurement/sync-st-xtrans-suomqty', methods=['POST'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_procurement_sync_st_xtrans_suomqty():
    """Re-apply ST_TR.UDF_SUOMQTY → ST_XTRANS.SUOMQTY overlay (same as db init backfill)."""
    con = None
    try:
        con = get_db_connection()
        ok = sync_st_xtrans_suomqty_from_st_tr_udf(con)
        if not ok:
            return jsonify({
                'success': False,
                'error': 'Sync skipped or failed (check server log for ST_TR/ST_XTRANS column warnings).',
            }), 500
        return jsonify({'success': True, 'message': 'ST_XTRANS.SUOMQTY refreshed from ST_TR.UDF_SUOMQTY.'})
    except Exception as e:
        print(f"[PROCUREMENT SYNC SUOMQTY] {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if con:
            con.close()


@app.route('/api/admin/procurement/stock-card-breakdown')
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_procurement_stock_card_breakdown():
    """Return the transaction or source breakdown for a clicked procurement stock-card cell."""
    item_code = (request.args.get('item_code') or '').strip()
    location = (request.args.get('location') or '').strip()
    metric = (request.args.get('metric') or '').strip()
    raw_from = (request.args.get('from_date') or '').strip()
    raw_to = (request.args.get('to_date') or '').strip()
    qty_mode = (request.args.get('qty_mode') or 'SQTY').strip().upper()
    if qty_mode not in ('SQTY', 'SUOMQTY'):
        qty_mode = 'SQTY'

    if not item_code or not location or not metric:
        return jsonify({'success': False, 'error': 'item_code, location, and metric are required'}), 400

    from_date = None
    to_date = None
    try:
        if raw_from:
            from_date = datetime.fromisoformat(raw_from).date()
        if raw_to:
            to_date = datetime.fromisoformat(raw_to).date()
    except ValueError:
        return jsonify({'success': False, 'error': 'from_date and to_date must be YYYY-MM-DD'}), 400

    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        payload = fetch_procurement_metric_breakdown(
            cur,
            metric,
            item_code,
            location,
            from_date=from_date,
            to_date=to_date,
            qty_mode=qty_mode,
        )
        return jsonify({'success': True, **payload})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        print(f"[PROCUREMENT STOCK CARD BREAKDOWN] DB error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


@app.route('/api/admin/procurement/suppliers')
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_procurement_suppliers():
    """Proxy full supplier list from the external accounting API, enriched with local UDF_EMAIL."""
    try:
        headers = _build_sql_api_auth_headers()
        all_suppliers = []
        offset = 0
        limit = 100
        while True:
            resp = requests.get(
                f"{FASTAPI_BASE_URL}/supplier",
                params={'offset': offset, 'limit': limit},
                headers=headers or None,
                timeout=10,
            )
            if not resp.ok:
                return jsonify({'success': False, 'error': f'Supplier API returned {resp.status_code}'}), 502
            payload = resp.json()
            rows = payload.get('data', []) if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                break
            all_suppliers.extend(rows)
            pagination = payload.get('pagination', {})
            total_count = pagination.get('count', len(rows)) if isinstance(pagination, dict) else len(rows)
            offset += limit
            if offset >= total_count or not rows:
                break

        # Enrich with UDF_EMAIL — already returned by the external API in the udf_email field
        return jsonify({'success': True, 'data': all_suppliers})
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Supplier list request timed out'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach accounting API for supplier list'}), 503
    except Exception as exc:
        print(f"[PROCUREMENT SUPPLIERS] Error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


def _load_projects_from_firebird_fallback():
    """Load project list directly from Firebird when upstream project API is unavailable."""
    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()

        cur.execute(
            """
            SELECT DISTINCT TRIM(RF.RDB$RELATION_NAME)
            FROM RDB$RELATION_FIELDS RF
            WHERE RF.RDB$FIELD_NAME = 'CODE'
              AND RF.RDB$RELATION_NAME CONTAINING 'PROJECT'
            ORDER BY 1
            """
        )
        candidate_tables = [str(row[0]).strip() for row in (cur.fetchall() or []) if row and row[0]]

        # Add common names even if metadata query misses them.
        for table_name in ["PROJECT", "ST_PROJECT", "AR_PROJECT", "PJ_PROJECT"]:
            if table_name not in candidate_tables:
                candidate_tables.append(table_name)

        projects = []
        seen_codes = set()

        for table_name in candidate_tables:
            try:
                cur.execute(
                    """
                    SELECT TRIM(RF.RDB$FIELD_NAME)
                    FROM RDB$RELATION_FIELDS RF
                    WHERE RF.RDB$RELATION_NAME = ?
                    """,
                    [table_name],
                )
                cols = {str(row[0]).strip().upper() for row in (cur.fetchall() or []) if row and row[0]}
                if "CODE" not in cols:
                    continue

                desc_col = "DESCRIPTION" if "DESCRIPTION" in cols else ("DESCRIPTION2" if "DESCRIPTION2" in cols else "")
                isactive_col = "ISACTIVE" if "ISACTIVE" in cols else ""

                select_cols = ["CODE"]
                select_cols.append(desc_col if desc_col else "NULL")
                select_cols.append(isactive_col if isactive_col else "NULL")
                cur.execute(f"SELECT {', '.join(select_cols)} FROM {table_name} ORDER BY CODE")
                rows = cur.fetchall() or []

                for row in rows:
                    code = str((row[0] if len(row) > 0 else "") or "").strip()
                    if not code or code in seen_codes:
                        continue
                    seen_codes.add(code)
                    description = str((row[1] if len(row) > 1 else "") or "").strip()
                    isactive_val = row[2] if len(row) > 2 else True
                    projects.append({
                        "code": code,
                        "description": description,
                        "isactive": bool(isactive_val if isactive_val is not None else True),
                    })
            except Exception:
                continue

        # Last-resort fallback from existing transactional records.
        if not projects:
            for table_name, col_name in [("PH_PQDTL", "PROJECT"), ("PH_PQ", "PROJECT")]:
                try:
                    cur.execute(f"SELECT DISTINCT {col_name} FROM {table_name} WHERE {col_name} IS NOT NULL ORDER BY {col_name}")
                    for row in (cur.fetchall() or []):
                        code = str((row[0] if row else "") or "").strip()
                        if not code or code in seen_codes:
                            continue
                        seen_codes.add(code)
                        projects.append({"code": code, "description": code, "isactive": True})
                except Exception:
                    continue

        return projects
    except Exception as exc:
        print(f"[PROCUREMENT PROJECTS] Firebird fallback error: {exc}", flush=True)
        return []
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


def _load_projects_from_env_fallback():
    """Fast fallback project list to avoid blocking UI when upstream project API is unavailable."""
    raw = (os.getenv('PROJECT_CODE_FALLBACK') or '').strip()
    if not raw:
        raw = "----,P1,P2,P3,P4,P5"
    codes = []
    seen = set()
    for part in raw.split(','):
        code = str(part or '').strip()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return [{'code': code, 'description': code, 'isactive': True} for code in codes]


@app.route('/api/admin/procurement/projects')
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_procurement_projects():
    """Proxy active project codes from SQL API /project for PR dropdown."""
    try:
        # Deterministic fast fallback so dropdown is always populated.
        # Configure PROJECT_CODE_FALLBACK in .env if needed (e.g. "----,P1,P2,P3,P4,P5").
        fallback_rows = _load_projects_from_env_fallback()
        if fallback_rows:
            return jsonify({'success': True, 'data': fallback_rows, 'source': 'env-fallback'})

        headers = _build_sql_api_auth_headers()
        rows: list[dict] = []
        seen_codes = set()
        page_limit = 50
        max_pages = 100
        endpoint_candidates = ["/project", "/project/*", "/projects"]
        last_status = None
        base_candidates = []
        # Restrict to SQL API hosts; BASE_API_URL is PHP service and can hang for these paths.
        for base in [PROJECT_API_BASE_URL, FASTAPI_BASE_URL]:
            base_text = (base or '').strip().rstrip('/')
            if base_text and base_text not in base_candidates:
                base_candidates.append(base_text)

        def _safe_get(url, params=None, use_headers=False):
            try:
                return requests.get(
                    url,
                    params=params,
                    headers=(headers or None) if use_headers else None,
                    timeout=(2, 4),
                )
            except requests.exceptions.RequestException:
                return None

        # Avoid spending too long on unreachable base URLs.
        selected_endpoint = None
        selected_base = None
        for base_url in base_candidates:
            base_has_network_error = False
            for endpoint in endpoint_candidates:
                probe_params = {'offset': 0} if endpoint != "/project/*" else None
                probe = _safe_get(f"{base_url}{endpoint}", params=probe_params, use_headers=True)
                if not probe or not probe.ok:
                    probe = _safe_get(f"{base_url}{endpoint}", params=probe_params, use_headers=False)
                if probe is None:
                    base_has_network_error = True
                    break
                if probe is not None:
                    last_status = probe.status_code
                if probe and probe.ok:
                    selected_base = base_url
                    selected_endpoint = endpoint
                    break
            if base_has_network_error and selected_endpoint is None:
                continue
            if selected_endpoint:
                break

        if not selected_endpoint:
            fallback_rows = _load_projects_from_env_fallback()
            return jsonify({'success': True, 'data': fallback_rows, 'source': 'firebird-fallback'})

        # Non-paginated wildcard endpoint.
        if selected_endpoint == "/project/*":
            resp = _safe_get(f"{selected_base}{selected_endpoint}", use_headers=True)
            if not resp or not resp.ok:
                resp = _safe_get(f"{selected_base}{selected_endpoint}", use_headers=False)
            if resp and resp.ok:
                payload = resp.json() if resp.text else {}
                page_rows = payload.get('data', []) if isinstance(payload, dict) else []
                if isinstance(page_rows, list):
                    for row in page_rows:
                        if not isinstance(row, dict):
                            continue
                        code = str(row.get('code') or '').strip()
                        if not code or code in seen_codes:
                            continue
                        seen_codes.add(code)
                        rows.append(row)
        else:
            offset = 0
            for _ in range(max_pages):
                params = {'offset': offset}
                resp = _safe_get(f"{selected_base}{selected_endpoint}", params=params, use_headers=True)
                # Some environments reject custom SQL headers; retry once without headers.
                if not resp or not resp.ok:
                    resp = _safe_get(f"{selected_base}{selected_endpoint}", params=params, use_headers=False)
                if not resp or not resp.ok:
                    if resp is not None:
                        last_status = resp.status_code
                    break

                payload = resp.json() if resp.text else {}
                page_rows = payload.get('data', []) if isinstance(payload, dict) else []
                if not isinstance(page_rows, list):
                    break
                if not page_rows:
                    break

                added_this_page = 0
                for row in page_rows:
                    if not isinstance(row, dict):
                        continue
                    code = str(row.get('code') or '').strip()
                    if not code or code in seen_codes:
                        continue
                    seen_codes.add(code)
                    rows.append(row)
                    added_this_page += 1

                pagination = payload.get('pagination', {}) if isinstance(payload, dict) else {}
                total_count = 0
                reported_limit = page_limit
                if isinstance(pagination, dict):
                    try:
                        total_count = int(pagination.get('count') or 0)
                    except Exception:
                        total_count = 0
                    try:
                        reported_limit = int(pagination.get('limit') or page_limit)
                    except Exception:
                        reported_limit = page_limit
                    if reported_limit <= 0:
                        reported_limit = page_limit

                # Stop when we've reached the reported total.
                if total_count > 0 and len(seen_codes) >= total_count:
                    break

                # If no new code appeared, avoid infinite loops.
                if added_this_page == 0:
                    break

                # Advance by reported page size (or current payload size fallback).
                step = reported_limit if reported_limit > 0 else len(page_rows)
                offset += max(1, step)

        normalized = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get('code') or '').strip()
            if not code or code in seen:
                continue
            seen.add(code)
            normalized.append({
                'code': code,
                'description': str(row.get('description') or '').strip(),
                'isactive': bool(row.get('isactive') if row.get('isactive') is not None else True),
            })

        active_rows = [row for row in normalized if row.get('isactive')]
        if not active_rows:
            fallback_rows = _load_projects_from_env_fallback()
            return jsonify({'success': True, 'data': fallback_rows, 'source': 'firebird-fallback'})
        return jsonify({'success': True, 'data': active_rows})
    except Exception as exc:
        print(f"[PROCUREMENT PROJECTS] Error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


def _normalize_selected_suppliers(raw_suppliers):
    normalized = []
    seen_codes = set()
    for raw in raw_suppliers if isinstance(raw_suppliers, list) else []:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get('code') or raw.get('supplierCode') or raw.get('supplierId') or '').strip()
        if not code:
            continue
        if code in seen_codes:
            continue
        seen_codes.add(code)
        normalized.append({
            'code': code,
            'name': str(raw.get('name') or raw.get('companyname') or raw.get('supplierName') or '').strip(),
            'email': str(raw.get('email') or raw.get('udf_email') or '').strip(),
        })
    return normalized


def _save_selected_suppliers(request_dockey, request_no, raw_suppliers, actor):
    """Persist selected suppliers for a purchase request (used by draft and edit flows)."""
    try:
        request_id = int(request_dockey)
    except Exception:
        return

    if request_id <= 0:
        return

    suppliers = _normalize_selected_suppliers(raw_suppliers)
    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()

        cur.execute('DELETE FROM PR_SELECTED_SUPPLIER WHERE REQUEST_DOCKEY = ?', (request_id,))

        if suppliers:
            cur.execute('SELECT COALESCE(MAX(ID), 0) FROM PR_SELECTED_SUPPLIER')
            row = cur.fetchone()
            next_id = int(row[0] or 0) + 1 if row else 1
            now_sql = datetime.utcnow().replace(microsecond=0)

            for supplier in suppliers:
                cur.execute(
                    '''
                    INSERT INTO PR_SELECTED_SUPPLIER (
                        ID, REQUEST_DOCKEY, REQUEST_NO, SUPPLIER_CODE, SUPPLIER_NAME,
                        SUPPLIER_EMAIL, CREATED_BY, CREATED_AT, UPDATED_AT
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        next_id,
                        request_id,
                        str(request_no or '').strip(),
                        supplier['code'],
                        supplier['name'],
                        supplier['email'],
                        str(actor or 'admin').strip() or 'admin',
                        now_sql,
                        now_sql,
                    ),
                )
                next_id += 1

        con.commit()
    except Exception as exc:
        if con:
            con.rollback()
        print(f"[PROCUREMENT SELECTED SUPPLIERS] save warning: {exc}", flush=True)
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


def _list_selected_suppliers(request_dockey):
    try:
        request_id = int(request_dockey)
    except Exception:
        return []

    if request_id <= 0:
        return []

    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute(
            '''
            SELECT SUPPLIER_CODE, SUPPLIER_NAME, SUPPLIER_EMAIL
            FROM PR_SELECTED_SUPPLIER
            WHERE REQUEST_DOCKEY = ?
            ORDER BY ID ASC
            ''',
            (request_id,),
        )
        rows = cur.fetchall() or []
        result = []
        for row in rows:
            code = str((row[0] if len(row) > 0 else '') or '').strip()
            if not code:
                continue
            result.append({
                'code': code,
                'name': str((row[1] if len(row) > 1 else '') or '').strip(),
                'email': str((row[2] if len(row) > 2 else '') or '').strip(),
            })
        codes = [row.get('code') or '' for row in result]
        master = _fetch_supplier_master_from_sql_api(codes)
        for row in result:
            hit = master.get(str(row.get('code') or '').strip().upper())
            if not isinstance(hit, dict):
                continue
            company_name = str(hit.get('companyname') or '').strip()
            udf_email = str(hit.get('udf_email') or '').strip()
            if company_name:
                row['name'] = company_name
            if udf_email:
                row['email'] = udf_email
        return result
    except Exception as exc:
        print(f"[PROCUREMENT SELECTED SUPPLIERS] list warning: {exc}", flush=True)
        return []
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


@app.route('/api/admin/procurement/purchase-requests', methods=['POST'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_create_purchase_request():
    """Create eProcurement purchase request with validation, persistence, and optional upstream submit."""
    payload = request.get_json(silent=True) or {}
    # requiredDate is no longer user-facing; canonicalize to requestDate/requestedDate.
    requested_date = str(payload.get('requestedDate') or payload.get('requestDate') or '').strip()
    if requested_date:
        payload['requestDate'] = requested_date
        payload['requestedDate'] = requested_date
    payload.pop('requiredDate', None)

    requested_status = str(payload.get('status') or 'DRAFT').strip().upper()
    if requested_status in {'0', 'DRAFT'}:
        payload['status'] = 'DRAFT'
    elif requested_status in {'1', 'SUBMITTED'}:
        payload['status'] = 'SUBMITTED'
    else:
        return jsonify({'success': False, 'error': 'status must be DRAFT or SUBMITTED'}), 400
    actor = (session.get('user_email') or session.get('user_name') or 'admin').strip()
    auth_header = (request.headers.get('Authorization') or '').strip() or None

    try:
        result = create_purchase_request(payload, created_by=actor, auth_header=auth_header)

        suppliers = payload.get('suppliers') or []
        _save_selected_suppliers(result.get('id'), result.get('requestNumber'), suppliers, actor)

        # Draft-first create does not trigger bid invitations.
        is_submitted = str(result.get('status') or '').strip().upper() == 'SUBMITTED'
        if is_submitted and suppliers and isinstance(suppliers, list) and result.get('id') and result.get('requestNumber'):
            try:
                from utils.procurement_bidding import create_bid_invitations
                create_bid_invitations(
                    request_dockey=result['id'],
                    request_no=result['requestNumber'],
                    suppliers=suppliers,
                    created_by=actor,
                )
                result['bidInvitationsSent'] = len(suppliers)
                print(f"[PROCUREMENT] Created bid invitations for {len(suppliers)} supplier(s) on PR {result['requestNumber']}", flush=True)

                if is_submitted:
                    targets = []
                    for raw in suppliers:
                        if not isinstance(raw, dict):
                            continue
                        email = str(raw.get('email') or raw.get('udf_email') or '').strip()
                        if not email:
                            continue
                        targets.append({
                            'email': email,
                            'code': str(raw.get('code') or '').strip(),
                            'name': str(raw.get('name') or raw.get('companyname') or '').strip(),
                        })

                    if targets:
                        request_number = str(result.get('requestNumber') or '').strip()
                        # Supplier-facing: treat required date as requested date (DOCDATE).
                        required_date = str(payload.get('requestDate') or payload.get('requiredDate') or '').strip()
                        line_items = payload.get('lineItems') if isinstance(payload.get('lineItems'), list) else []

                        threading.Thread(
                            target=_send_rfq_invitation_emails_background,
                            args=(targets, request_number, required_date, line_items),
                            daemon=True,
                        ).start()
                        result['bidInvitationEmailsQueued'] = len(targets)
                    else:
                        result['bidInvitationEmailsQueued'] = 0
            except Exception as bid_exc:
                print(f"[PROCUREMENT] Bid invitation creation failed (non-fatal): {bid_exc}", flush=True)
                result['bidInvitationsSent'] = 0
                result['bidInvitationEmailsQueued'] = 0

        return jsonify({
            'success': True,
            'message': 'Purchase request created successfully',
            'data': result,
        }), 201
    except PurchaseRequestValidationError as exc:
        print(f"[PROCUREMENT CREATE PR] validation error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        print(f"[PROCUREMENT CREATE PR] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


def _fetch_supplier_master_from_sql_api(codes: list[str]) -> dict[str, dict[str, str]]:
    """Map supplier CODE (upper) -> companyname, udf_email from GET {FASTAPI_BASE_URL}/supplier list."""
    remaining = {str(c).strip().upper() for c in codes if str(c).strip()}
    if not remaining:
        return {}

    out: dict[str, dict[str, str]] = {}
    headers = _build_sql_api_auth_headers()
    offset = 0
    limit = 100
    try:
        while remaining:
            resp = requests.get(
                f"{FASTAPI_BASE_URL}/supplier",
                params={'offset': offset, 'limit': limit},
                headers=headers or None,
                timeout=12,
            )
            if not resp.ok:
                print(f"[PROCUREMENT LIST PR] SQL API supplier list HTTP {resp.status_code}", flush=True)
                break

            payload = resp.json() if resp.text else {}
            rows = payload.get('data', []) if isinstance(payload, dict) else []
            if not isinstance(rows, list) or not rows:
                break

            for row in rows:
                if not isinstance(row, dict):
                    continue
                code = str(row.get('code') or '').strip()
                if not code:
                    continue
                key_u = code.upper()
                if key_u not in remaining:
                    continue
                out[key_u] = {
                    'companyname': str(row.get('companyname') or row.get('companyName') or '').strip(),
                    'udf_email': str(
                        row.get('udf_email')
                        or row.get('udfEmail')
                        or row.get('UDF_EMAIL')
                        or ''
                    ).strip(),
                }
                remaining.discard(key_u)
                if not remaining:
                    return out

            pagination = payload.get('pagination', {}) if isinstance(payload, dict) else {}
            total_count = pagination.get('count', len(rows)) if isinstance(pagination, dict) else len(rows)
            offset += limit
            if offset >= total_count:
                break
    except Exception as exc:
        print(f"[PROCUREMENT LIST PR] SQL API supplier master lookup warning: {exc}", flush=True)

    return out


def _fetch_supplier_emails_by_codes(codes: list[str]) -> dict[str, str]:
    """Return supplier CODE.upper() -> email using AR_SUPPLIER / AP_SUPPLIER (UDF_EMAIL, then EMAIL)."""
    uniq: list[str] = []
    seen: set[str] = set()
    for c in codes:
        t = str(c or '').strip()
        if not t:
            continue
        k = t.upper()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(t)
    if not uniq:
        return {}

    out: dict[str, str] = {}
    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        placeholders = ', '.join(['?'] * len(uniq))
        params = tuple(uniq)
        for table in ('AR_SUPPLIER', 'AP_SUPPLIER'):
            try:
                cur.execute(
                    'SELECT COUNT(*) FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ?',
                    (table.upper(),),
                )
                chk = cur.fetchone()
                if not chk or int(chk[0] or 0) <= 0:
                    continue
            except Exception:
                continue
            for email_col in ('UDF_EMAIL', 'EMAIL'):
                try:
                    cur.execute(
                        f"""
                        SELECT TRIM(CODE), TRIM({email_col})
                        FROM {table}
                        WHERE TRIM(CODE) IN ({placeholders})
                        """,
                        params,
                    )
                    for row in cur.fetchall() or []:
                        if not row:
                            continue
                        code_raw = str(row[0] or '').strip()
                        em = str(row[1] or '').strip()
                        key_u = code_raw.upper()
                        if em and key_u and key_u not in out:
                            out[key_u] = em
                except Exception:
                    continue
        return out
    except Exception as exc:
        print(f"[PROCUREMENT LIST PR] supplier email lookup error: {exc}", flush=True)
        return {}
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if con:
                con.close()
        except Exception:
            pass


def _parse_additional_email_recipients(raw) -> list[str]:
    """Split optional textarea input into validated-looking email addresses."""
    if raw is None:
        return []
    s = str(raw).strip()
    if not s:
        return []
    parts = re.split(r'[\s,;]+', s)
    out: list[str] = []
    for p in parts:
        em = p.strip()
        if not em or '@' not in em:
            continue
        domain = em.split('@', 1)[-1]
        if '.' not in domain:
            continue
        out.append(em)
    return out


def _rfq_invite_safe_html(value) -> str:
    return (
        str(value or '')
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&#39;')
    )


def _send_rfq_invitation_emails_background(invite_targets, req_no, req_required_date, req_lines):
    """Send RFQ HTML emails (async worker). invite_targets: list of dict with email, name, code."""
    item_rows = ''
    for idx, line in enumerate(req_lines or [], start=1):
        if not isinstance(line, dict):
            continue
        item_name = _rfq_invite_safe_html(
            line.get('itemName') or line.get('description') or line.get('itemCode') or f'Item {idx}'
        )
        qty = _rfq_invite_safe_html(line.get('quantity') or 0)
        item_rows += (
            f"<tr>"
            f"<td style='padding:8px;border:1px solid #dbe4ee;'>{idx}</td>"
            f"<td style='padding:8px;border:1px solid #dbe4ee;'>{item_name}</td>"
            f"<td style='padding:8px;border:1px solid #dbe4ee;text-align:right;'>{qty}</td>"
            f"</tr>"
        )

    if not item_rows:
        item_rows = (
            "<tr><td colspan='3' style='padding:8px;border:1px solid #dbe4ee;color:#64748b;'>"
            "No line items were included in this notification."
            "</td></tr>"
        )

    for target in invite_targets:
        to_email = str(target.get('email') or '').strip()
        if not to_email:
            continue

        supplier_name = _rfq_invite_safe_html(target.get('name') or target.get('code') or 'Supplier')
        subject = f"RFQ Invitation - Purchase Request {req_no}"
        body = f"""
        <html>
            <body style='font-family: Arial, sans-serif; color: #1f2937;'>
                <div style='max-width: 700px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;'>
                    <div style='background: #1a1f2e; color: #fff; padding: 14px 18px; font-size: 18px; font-weight: 600;'>Request for Quotation Invitation</div>
                    <div style='padding: 18px;'>
                        <p>Dear {supplier_name},</p>
                        <p>You are invited to quote for Purchase Request <strong>{_rfq_invite_safe_html(req_no)}</strong>.</p>
                        <p><strong>Requested Date:</strong> {_rfq_invite_safe_html(req_required_date or '-')}</p>
                        <table style='width:100%;border-collapse:collapse;margin-top:14px;'>
                            <thead>
                                <tr style='background:#f8fafc;'>
                                    <th style='padding:8px;border:1px solid #dbe4ee;text-align:left;'>#</th>
                                    <th style='padding:8px;border:1px solid #dbe4ee;text-align:left;'>Item</th>
                                    <th style='padding:8px;border:1px solid #dbe4ee;text-align:right;'>Qty</th>
                                </tr>
                            </thead>
                            <tbody>{item_rows}</tbody>
                        </table>
                        <p style='margin-top:14px;'>Please submit your quotation in the supplier bidding portal.</p>
                    </div>
                </div>
            </body>
        </html>
        """

        try:
            ok = send_email(to_email, subject, body)
            if ok:
                print(f"[PROCUREMENT] RFQ invite email sent to {to_email} for PR {req_no}", flush=True)
            else:
                print(f"[PROCUREMENT] RFQ invite email failed to {to_email} for PR {req_no}", flush=True)
        except Exception as mail_exc:
            print(f"[PROCUREMENT] RFQ invite email exception for {to_email}: {mail_exc}", flush=True)


def _resolve_invitation_email_targets(normalized_suppliers: list[dict]) -> list[dict]:
    """Resolve udf_email / Firebird email for each supplier row."""
    if not normalized_suppliers:
        return []
    codes = [s.get('code') or '' for s in normalized_suppliers]
    master = _fetch_supplier_master_from_sql_api(codes)
    fb_map = _fetch_supplier_emails_by_codes(codes)
    targets: list[dict] = []
    for s in normalized_suppliers:
        code = str(s.get('code') or '').strip()
        if not code:
            continue
        key_u = code.upper()
        email = ''
        m = master.get(key_u)
        if m:
            email = str(m.get('udf_email') or '').strip()
        if not email:
            email = str(fb_map.get(key_u) or '').strip()
        if email:
            targets.append({
                'email': email,
                'code': code,
                'name': str(s.get('name') or '').strip(),
            })
    return targets


def _local_pr_lines_for_rfq_email(request_dockey: int, request_no: str) -> tuple[list[dict], str]:
    """Load PR lines + doc date from local PH_PQ/PH_PQDTL for RFQ email body."""
    local = _resolve_local_purchase_request_header(str(request_dockey), str(request_no or '').strip())
    if not local:
        return [], '-'
    req_date = str(local.get('docDate') or '-').strip() or '-'
    lines: list[dict] = []
    for idx, row in enumerate(local.get('sdsdocdetail') or [], start=1):
        if not isinstance(row, dict):
            continue
        lines.append({
            'itemName': row.get('itemName') or row.get('description') or row.get('itemCode') or f'Item {idx}',
            'description': row.get('description'),
            'itemCode': row.get('itemCode'),
            'quantity': row.get('quantity'),
        })
    return lines, req_date


def _dedupe_invitation_targets_by_email(targets: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for t in targets:
        em = str(t.get('email') or '').strip().lower()
        if not em or em in seen:
            continue
        seen.add(em)
        out.append(t)
    return out


@app.route('/api/admin/procurement/purchase-requests/next-number', methods=['GET'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_next_purchase_request_number():
    """Preview the next auto-generated eProcurement purchase request number."""
    try:
        return jsonify({
            'success': True,
            'data': {
                'requestNumber': preview_purchase_request_number(),
            },
        })
    except Exception as exc:
        print(f"[PROCUREMENT NEXT PR NO] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/admin/procurement/purchase-requests', methods=['GET'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_list_purchase_requests():
    """List eProcurement purchase request headers from SQL API."""
    started_total = time.perf_counter()
    raw_offset = (request.args.get('offset') or '').strip()
    raw_limit = (request.args.get('limit') or '').strip()
    raw_fast = request.args.get('fast')
    raw_include_qty = request.args.get('include_qty')
    raw_debug_suppliers = request.args.get('debug_suppliers')
    raw_include_total = request.args.get('include_total')
    raw_no_cache = request.args.get('no_cache')
    include_total_upstream = str(raw_include_total or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    no_cache = str(raw_no_cache or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    debug_suppliers = str(raw_debug_suppliers or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    include_qty = str(raw_include_qty or '').strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    if raw_fast is None:
        # Default to fast mode for better UI responsiveness.
        fast_mode = True
    else:
        fast_mode = str(raw_fast).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    try:
        offset = int(raw_offset) if raw_offset else 0
        limit = int(raw_limit) if raw_limit else 200
    except ValueError:
        return jsonify({'success': False, 'error': 'offset and limit must be integers'}), 400

    offset = max(0, offset)
    # SQL API pagination typically expects smaller pages; keep this conservative.
    limit = max(1, min(limit, 50))

    def _status_text(raw_status):
        text = str(raw_status).strip().upper() if raw_status is not None else ''
        if text in {'DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'CANCELLED'}:
            return text
        try:
            status_num = int(raw_status)
        except Exception:
            return text or 'DRAFT'
        return {
            0: 'DRAFT',
            1: 'SUBMITTED',
            2: 'APPROVED',
            3: 'REJECTED',
            4: 'CANCELLED',
        }.get(status_num, str(status_num))

    def _num(value):
        if value is None:
            return 0.0
        try:
            return float(str(value).replace(',', '').strip() or 0)
        except Exception:
            return 0.0

    def _fetch_pr_balance_qty_map(request_ids):
        if not request_ids:
            return {}

        con = None
        cur = None
        try:
            con = get_db_connection()
            cur = con.cursor()
            placeholders = ', '.join(['?'] * len(request_ids))
            params = tuple([*request_ids, *request_ids])
            cur.execute(
                f"""
                SELECT D.DOCKEY,
                       CAST(SUM(CAST(COALESCE(D.QTY, 0) AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TOTAL_QTY,
                       CAST(COALESCE(T.TRANSFERRED_QTY, 0) AS DOUBLE PRECISION) AS TRANSFERRED_QTY
                FROM PH_PQDTL D
                LEFT JOIN (
                    SELECT FROMDOCKEY,
                           CAST(SUM(CAST(COALESCE(SQTY, QTY, 0) AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TRANSFERRED_QTY
                    FROM ST_XTRANS
                    WHERE TRIM(UPPER(COALESCE(FROMDOCTYPE, ''))) IN ('PQ', 'PH_PQ')
                      AND FROMDOCKEY IN ({placeholders})
                    GROUP BY FROMDOCKEY
                ) T ON T.FROMDOCKEY = D.DOCKEY
                WHERE D.DOCKEY IN ({placeholders})
                GROUP BY D.DOCKEY, T.TRANSFERRED_QTY
                """,
                params,
            )
            rows = cur.fetchall() or []
            result = {}
            for row in rows:
                if not row:
                    continue
                try:
                    request_id = int(row[0])
                except Exception:
                    continue
                total_qty = _num(row[1])
                transferred_qty = _num(row[2])
                result[request_id] = {
                    'totalQty': total_qty,
                    'transferredQty': transferred_qty,
                    'balanceQty': max(0.0, total_qty - transferred_qty),
                }
            return result
        except Exception as exc:
            print(f"[PROCUREMENT LIST PR] balance qty lookup error: {exc}", flush=True)
            return {}
        finally:
            try:
                if cur:
                    cur.close()
            except Exception:
                pass
            try:
                if con:
                    con.close()
            except Exception:
                pass

    cache_key = (offset, limit, int(fast_mode), int(include_qty), int(include_total_upstream), int(debug_suppliers))
    if not no_cache:
        with PURCHASE_REQUEST_LIST_CACHE_LOCK:
            cached = PURCHASE_REQUEST_LIST_CACHE.get(cache_key)
        if cached:
            cached_at, cached_payload = cached
            age_ms = round((time.perf_counter() - cached_at) * 1000, 1)
            if age_ms <= PURCHASE_REQUEST_LIST_CACHE_TTL_SEC * 1000:
                response_payload = json.loads(json.dumps(cached_payload, default=str))
                perf = response_payload.setdefault('perf', {})
                perf['cacheHit'] = True
                perf['cacheAgeMs'] = age_ms
                perf['totalMs'] = round((time.perf_counter() - started_total) * 1000, 1)
                perf['upstreamMs'] = 0.0
                print(
                    f"[PROCUREMENT LIST PR PERF] cache_hit=1 total_ms={perf['totalMs']} age_ms={age_ms} "
                    f"rows={len(response_payload.get('data') or [])}",
                    flush=True
                )
                return jsonify(response_payload)
            with PURCHASE_REQUEST_LIST_CACHE_LOCK:
                current = PURCHASE_REQUEST_LIST_CACHE.get(cache_key)
                if current and current[0] == cached_at:
                    PURCHASE_REQUEST_LIST_CACHE.pop(cache_key, None)

    try:
        headers = _build_sql_api_auth_headers()
        global PURCHASE_REQUEST_LIST_ENDPOINT_HINT
        candidates = [
            f"{FASTAPI_BASE_URL}/purchaserequest",
            f"{FASTAPI_BASE_URL}/purchase-request",
            f"{FASTAPI_BASE_URL}/purchaserequests",
            f"{FASTAPI_BASE_URL}/purchase-requests",
        ]
        if PURCHASE_REQUEST_LIST_ENDPOINT_HINT in candidates:
            candidates.remove(PURCHASE_REQUEST_LIST_ENDPOINT_HINT)
            candidates.insert(0, PURCHASE_REQUEST_LIST_ENDPOINT_HINT)
        payload = {}
        last_status = None
        tried = []

        list_params = {
            'offset': offset,
            'limit': limit,
            # Fast list: skip full-table COUNT in SQL API; optional exact total via ?include_total=1
            'include_total': '1' if include_total_upstream else '0',
            'fields': 'minimal',
        }
        upstream_started = time.perf_counter()
        for url in candidates:
            resp = requests.get(
                url,
                params=list_params,
                headers=headers or None,
                timeout=8,
            )
            last_status = resp.status_code
            tried.append(f"{url} -> {resp.status_code}")
            if not resp.ok:
                continue
            payload = resp.json() if resp.text else {}
            PURCHASE_REQUEST_LIST_ENDPOINT_HINT = url
            break
        upstream_ms = round((time.perf_counter() - upstream_started) * 1000, 1)

        if not payload:
            detail = '; '.join(tried) if tried else 'No upstream attempts were made'
            return jsonify({'success': False, 'error': f'SQL API list failed ({detail})'}), 502

        rows = payload.get('data', []) if isinstance(payload, dict) else []
        pagination = payload.get('pagination', {}) if isinstance(payload, dict) else {}
        sql_api_perf = payload.get('perf') if isinstance(payload.get('perf'), dict) else {}
        if not isinstance(rows, list):
            return jsonify({'success': False, 'error': f'Unexpected SQL API format: missing data[] (last status: {last_status})'}), 502

        header_ids = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                header_ids.append(int(row.get('dockey')))
            except Exception:
                continue
        qty_started = time.perf_counter()
        should_load_qty = (not fast_mode) or include_qty
        balance_qty_map = _fetch_pr_balance_qty_map(header_ids) if should_load_qty else {}
        qty_ms = round((time.perf_counter() - qty_started) * 1000, 1)

        map_started = time.perf_counter()
        records = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            dockey = row.get('dockey')
            try:
                row_id = int(dockey)
            except Exception:
                row_id = 0

            qty_summary = balance_qty_map.get(row_id, {})

            records.append({
                'id': row_id,
                'requestNumber': str(row.get('docno') or '').strip(),
                'requestDate': row.get('docdate'),
                'requiredDate': row.get('postdate'),
                'requesterId': str(row.get('code') or row.get('companyname') or '').strip(),
                'departmentId': str(row.get('businessunit') or row.get('area') or '').strip(),
                'costCenter': str(row.get('businessunit') or '').strip(),
                'project': str(row.get('project') or '').strip() or '----',
                'supplierId': '',
                'supplierName': '',
                'supplierEmail': '',
                'currency': str(row.get('currencycode') or '').strip(),
                'description': str(row.get('description') or '').strip(),
                'udfReason': str(row.get('udf_reason') or '').strip(),
                'deliveryLocation': str(row.get('deliverylocation') or row.get('daddress1') or '').strip(),
                'totalAmount': _num(row.get('docamt')),
                'status': _status_text(row.get('status')),
                'udfStatus': str(row.get('udf_status') or '').strip(),
                'transferable': bool(row.get('transferable') if row.get('transferable') is not None else True),
                'totalQty': _num(qty_summary.get('totalQty')),
                'transferredQty': _num(qty_summary.get('transferredQty')),
                'balanceQty': _num(qty_summary.get('balanceQty')),
                'details': None,
            })
        records_map_ms = round((time.perf_counter() - map_started) * 1000, 1)

        supplier_started = time.perf_counter()
        try:
            awarded_suppliers = map_awarded_suppliers_by_request_ids([int(r['id']) for r in records if r.get('id')])
        except Exception as awarded_exc:
            print(f"[PROCUREMENT LIST PR] awarded supplier lookup warning: {awarded_exc}", flush=True)
            awarded_suppliers = {}
        debug_supplier_rows = []
        for rec in records:
            rid = rec.get('id')
            if not rid:
                continue
            try:
                key = int(rid)
            except Exception:
                continue
            hit = awarded_suppliers.get(key)
            if not isinstance(hit, dict):
                if debug_suppliers:
                    debug_supplier_rows.append({
                        'requestId': key,
                        'awardedSupplierCode': '',
                        'awardedSupplierName': '',
                    })
                continue
            rec['supplierId'] = str(hit.get('supplierCode') or '').strip()
            rec['supplierName'] = str(hit.get('supplierName') or '').strip()
            if debug_suppliers:
                debug_supplier_rows.append({
                    'requestId': key,
                    'awardedSupplierCode': rec['supplierId'],
                    'awardedSupplierName': rec['supplierName'],
                })
        supplier_ms = round((time.perf_counter() - supplier_started) * 1000, 1)

        if not fast_mode:
            try:
                bid_suppliers = map_approved_bid_suppliers_by_request_ids([int(r['id']) for r in records if r.get('id')])
            except Exception as bid_exc:
                print(f"[PROCUREMENT LIST PR] approved bid supplier lookup warning: {bid_exc}", flush=True)
                bid_suppliers = {}

            for rec in records:
                rid = rec.get('id')
                if not rid:
                    continue
                try:
                    key = int(rid)
                except Exception:
                    continue
                info = bid_suppliers.get(key)
                if not isinstance(info, dict):
                    continue
                code = str(info.get('supplierCode') or '').strip()
                name = str(info.get('supplierName') or '').strip()
                if code and not rec.get('supplierId'):
                    rec['supplierId'] = code
                if name and not rec.get('supplierName'):
                    rec['supplierName'] = name
                elif code and not rec.get('supplierName'):
                    rec['supplierName'] = code

            try:
                supplier_codes = list(
                    {str(r.get('supplierId') or '').strip() for r in records if str(r.get('supplierId') or '').strip()}
                )
                api_master = _fetch_supplier_master_from_sql_api(supplier_codes)
                for rec in records:
                    cid = str(rec.get('supplierId') or '').strip()
                    if not cid:
                        continue
                    master = api_master.get(cid.upper())
                    if isinstance(master, dict):
                        cn = str(master.get('companyname') or '').strip()
                        em = str(master.get('udf_email') or '').strip()
                        if cn:
                            rec['supplierName'] = cn
                        if em:
                            rec['supplierEmail'] = em

                email_by_code = _fetch_supplier_emails_by_codes(supplier_codes)
                for rec in records:
                    cid = str(rec.get('supplierId') or '').strip()
                    existing = str(rec.get('supplierEmail') or '').strip()
                    if cid and not existing:
                        rec['supplierEmail'] = email_by_code.get(cid.upper()) or ''
                    elif not existing:
                        rec['supplierEmail'] = ''
            except Exception as em_exc:
                print(f"[PROCUREMENT LIST PR] supplier master/email enrichment warning: {em_exc}", flush=True)

        if fast_mode:
            try:
                supplier_codes = list(
                    {str(r.get('supplierId') or '').strip() for r in records if str(r.get('supplierId') or '').strip()}
                )
                api_master = _fetch_supplier_master_from_sql_api(supplier_codes)
                for rec in records:
                    cid = str(rec.get('supplierId') or '').strip()
                    if not cid:
                        continue
                    master = api_master.get(cid.upper())
                    if isinstance(master, dict):
                        company_name = str(master.get('companyname') or '').strip()
                        udf_email = str(master.get('udf_email') or '').strip()
                        if company_name:
                            rec['supplierName'] = company_name
                        if udf_email:
                            rec['supplierEmail'] = udf_email
            except Exception as em_exc:
                print(f"[PROCUREMENT LIST PR] supplier master/email enrichment warning: {em_exc}", flush=True)

        if debug_suppliers:
            try:
                preview = debug_supplier_rows[:20]
                print(f"[PROCUREMENT LIST PR DEBUG] supplier mapping preview: {preview}", flush=True)
            except Exception:
                pass

        total_ms = round((time.perf_counter() - started_total) * 1000, 1)
        print(
            f"[PROCUREMENT LIST PR PERF] total_ms={total_ms} upstream_ms={upstream_ms} "
            f"sql_api_data_ms={sql_api_perf.get('dataQueryMs')} sql_api_count_ms={sql_api_perf.get('countQueryMs')} "
            f"qty_ms={qty_ms} supplier_ms={supplier_ms} map_ms={records_map_ms} "
            f"rows={len(records)} fast_mode={int(fast_mode)} include_qty={int(should_load_qty)}",
            flush=True
        )

        pg_out = dict(pagination) if isinstance(pagination, dict) else {'offset': offset, 'limit': limit, 'count': len(records)}

        response_payload = {
            'success': True,
            'data': records,
            'count': len(records),
            'pagination': pg_out,
            'perf': {
                'totalMs': total_ms,
                'upstreamMs': upstream_ms,
                'qtyMs': qty_ms,
                'supplierMs': supplier_ms,
                'includeQty': bool(should_load_qty),
                'fastMode': bool(fast_mode),
                'rowCount': len(records),
                'recordsMapMs': records_map_ms,
                'sqlApi': sql_api_perf,
            },
        }
        if debug_suppliers:
            response_payload['debugSuppliers'] = {
                'fastMode': bool(fast_mode),
                'rows': debug_supplier_rows,
                'awardedCount': len(awarded_suppliers) if isinstance(awarded_suppliers, dict) else 0,
            }
        if not no_cache:
            with PURCHASE_REQUEST_LIST_CACHE_LOCK:
                if len(PURCHASE_REQUEST_LIST_CACHE) >= 16:
                    oldest_key = min(PURCHASE_REQUEST_LIST_CACHE, key=lambda k: PURCHASE_REQUEST_LIST_CACHE[k][0])
                    PURCHASE_REQUEST_LIST_CACHE.pop(oldest_key, None)
                PURCHASE_REQUEST_LIST_CACHE[cache_key] = (time.perf_counter(), response_payload)
        return jsonify(response_payload)
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Purchase request list request timed out'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach SQL API for purchase request list'}), 503
    except Exception as exc:
        print(f"[PROCUREMENT LIST PR] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/admin/procurement/purchase-requests/<int:request_id>', methods=['GET'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_purchase_request_details(request_id):
    """Get one eProcurement purchase request detail rows from SQL API."""

    def _num(value):
        if value is None:
            return 0.0
        try:
            return float(str(value).replace(',', '').strip() or 0)
        except Exception:
            return 0.0

    try:
        headers = _build_sql_api_auth_headers()
        resp = requests.get(
            f"{FASTAPI_BASE_URL}/purchaserequest/{int(request_id)}",
            headers=headers or None,
            timeout=12,
        )
        if not resp.ok:
            return jsonify({'success': False, 'error': f'SQL API returned {resp.status_code}'}), 502

        payload = resp.json() if resp.text else {}
        records = payload.get('data', []) if isinstance(payload, dict) else []
        if not isinstance(records, list) or not records:
            return jsonify({'success': False, 'error': 'Purchase request not found'}), 404

        header = records[0] if isinstance(records[0], dict) else {}
        detail_rows = header.get('sdsdocdetail', []) if isinstance(header, dict) else []
        if not isinstance(detail_rows, list):
            detail_rows = []

        details = []
        for idx, row in enumerate(detail_rows, start=1):
            if not isinstance(row, dict):
                continue
            details.append({
                'id': row.get('dtlkey'),
                'seq': row.get('seq') if row.get('seq') is not None else idx,
                'itemCode': str(row.get('itemcode') or '').strip(),
                'itemName': str(row.get('itemname') or row.get('description2') or row.get('description') or '').strip(),
                'description': str(row.get('description3') or row.get('description') or '').strip(),
                'locationCode': str(row.get('location') or '').strip(),
                'quantity': _num(row.get('qty')),
                'unitPrice': _num(row.get('unitprice')),
                'tax': _num(row.get('taxamt')),
                'amount': _num(row.get('amount')),
                'deliveryDate': row.get('deliverydate'),
                'udfPqApproved': row.get('udf_pqapproved'),
            })

        return jsonify({'success': True, 'id': int(request_id), 'details': details, 'count': len(details)})
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Purchase request detail request timed out'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach SQL API for purchase request detail'}), 503
    except Exception as exc:
        print(f"[PROCUREMENT PR DETAIL] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/admin/procurement/purchase-requests/details', methods=['GET'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_purchase_request_details_fallback():
    """Get eProcurement purchase request detail rows using resilient SQL API lookup patterns."""
    started_total = time.perf_counter()
    raw_request_id = (request.args.get('request_id') or '').strip()
    request_no = (request.args.get('request_no') or '').strip()

    if not raw_request_id and not request_no:
        return jsonify({'success': False, 'error': 'request_id or request_no is required'}), 400

    def _num(value):
        if value is None:
            return 0.0
        try:
            return float(str(value).replace(',', '').strip() or 0)
        except Exception:
            return 0.0

    def _fetch_transferred_qty_map(request_id, detail_ids):
        if not request_id or not detail_ids:
            return {}

        con = None
        cur = None
        try:
            con = get_db_connection()
            cur = con.cursor()
            from utils.procurement_purchase_request import _get_table_columns, _pick_existing

            xtrans_cols = _get_table_columns(cur, "ST_XTRANS")
            qty_col = _pick_existing(xtrans_cols, "QTY")
            sqty_col = _pick_existing(xtrans_cols, "SQTY")
            suom_col = _pick_existing(xtrans_cols, "SUOMQTY")
            if suom_col and sqty_col and qty_col:
                quantity_expr = (
                    f"COALESCE(NULLIF({suom_col}, 0), NULLIF({sqty_col}, 0), COALESCE({qty_col}, 0), 0)"
                )
            elif sqty_col and qty_col:
                quantity_expr = f"COALESCE(NULLIF({sqty_col}, 0), COALESCE({qty_col}, 0), 0)"
            else:
                quantity_expr = suom_col or sqty_col or qty_col or "0"
            placeholders = ', '.join(['?'] * len(detail_ids))
            cur.execute(
                f"""
                SELECT FROMDTLKEY,
                       CAST(SUM(CAST({quantity_expr} AS DOUBLE PRECISION)) AS DOUBLE PRECISION) AS TRANSFERRED_QTY
                FROM ST_XTRANS
                WHERE TRIM(UPPER(COALESCE(FROMDOCTYPE, ''))) IN ('PQ', 'PH_PQ')
                  AND FROMDOCKEY = ?
                  AND FROMDTLKEY IN ({placeholders})
                GROUP BY FROMDTLKEY
                """,
                tuple([int(request_id), *[int(x) for x in detail_ids]]),
            )
            rows = cur.fetchall() or []
            transferred = {}
            for row in rows:
                if not row:
                    continue
                try:
                    transferred[int(row[0])] = _num(row[1])
                except Exception:
                    continue
            return transferred
        except Exception as exc:
            print(f"[PROCUREMENT PR DETAIL] warning: failed to read ST_XTRANS qty map: {exc}", flush=True)
            return {}
        finally:
            if cur:
                cur.close()
            if con:
                con.close()

    def _extract_details(payload_obj):
        records = payload_obj.get('data', []) if isinstance(payload_obj, dict) else []
        if not isinstance(records, list) or not records:
            return None
        header = records[0] if isinstance(records[0], dict) else {}
        request_id = header.get('dockey')
        request_number = str(header.get('docno') or request_no or '').strip()
        detail_rows = header.get('sdsdocdetail', []) if isinstance(header, dict) else []
        if not isinstance(detail_rows, list):
            detail_rows = []

        detail_ids = []
        for row in detail_rows:
            if not isinstance(row, dict):
                continue
            try:
                detail_ids.append(int(row.get('dtlkey')))
            except Exception:
                continue

        transferred_qty_map = _fetch_transferred_qty_map(request_id, detail_ids)

        details = []
        for idx, row in enumerate(detail_rows, start=1):
            if not isinstance(row, dict):
                continue
            detail_id = row.get('dtlkey')
            quantity = _num(row.get('qty'))
            try:
                transferred_qty = _num(transferred_qty_map.get(int(detail_id), 0))
            except Exception:
                transferred_qty = 0.0
            remaining_qty = max(0.0, quantity - transferred_qty)
            sqty_v = _num(row.get('sqty'))
            suom_v = _num(row.get('suomqty'))
            basis = str(row.get('stockQtyUom') or '').strip().upper()
            if basis not in ('SQTY', 'SUOMQTY'):
                if suom_v > 0 and sqty_v == 0:
                    basis = 'SUOMQTY'
                elif sqty_v > 0 and suom_v == 0:
                    basis = 'SQTY'
                else:
                    basis = 'SUOMQTY'
            details.append({
                'id': detail_id,
                'seq': row.get('seq') if row.get('seq') is not None else idx,
                'itemCode': str(row.get('itemcode') or '').strip(),
                'itemName': str(row.get('itemname') or row.get('description2') or row.get('description') or '').strip(),
                'description': str(row.get('description3') or row.get('description') or '').strip(),
                'project': str(row.get('project') or '').strip() or '----',
                'locationCode': str(row.get('location') or '').strip(),
                'quantity': quantity,
                'unitPrice': _num(row.get('unitprice')),
                'tax': _num(row.get('taxamt')),
                'amount': _num(row.get('amount')),
                'deliveryDate': row.get('deliverydate'),
                'udfPqApproved': row.get('udf_pqapproved'),
                'udfReason': str(row.get('udf_reason') or '').strip(),
                'transferredQty': transferred_qty,
                'remainingQty': remaining_qty,
                'isFinalChosenPrice': False,
                'stockQtyUom': basis,
                'sqty': sqty_v,
                'suomqty': suom_v,
            })
        try:
            resolved_request_id = int(request_id)
        except Exception:
            resolved_request_id = int(raw_request_id) if raw_request_id.isdigit() else None

        gate_ms = 0.0
        if resolved_request_id and details:
            try:
                gate_started = time.perf_counter()
                gate = get_transfer_gate_state(resolved_request_id)
                approved_line_map = {}

                # Preferred: mixed line awards (different supplier per item).
                line_awards = gate.get('lineAwards') if isinstance(gate, dict) else []
                if isinstance(line_awards, list) and line_awards:
                    for line in line_awards:
                        if not isinstance(line, dict):
                            continue
                        try:
                            approved_line_map[int(line.get('detailId'))] = line
                        except Exception:
                            continue
                    print(
                        f"[PROCUREMENT PR DETAIL DEBUG] request_id={resolved_request_id} pricing_source=line_awards lines={len(approved_line_map)}",
                        flush=True
                    )
                else:
                    # Fallback: legacy single approved bid flow.
                    approved_bid = gate.get('approvedBid') if isinstance(gate, dict) else None
                    approved_lines = approved_bid.get('lines') if isinstance(approved_bid, dict) else []
                    for line in approved_lines if isinstance(approved_lines, list) else []:
                        if not isinstance(line, dict):
                            continue
                        try:
                            approved_line_map[int(line.get('detailId'))] = line
                        except Exception:
                            continue
                    if approved_line_map:
                        print(
                            f"[PROCUREMENT PR DETAIL DEBUG] request_id={resolved_request_id} pricing_source=approved_bid lines={len(approved_line_map)}",
                            flush=True
                        )

                for detail in details:
                    try:
                        detail_id = int(detail.get('id'))
                    except Exception:
                        continue
                    hit = approved_line_map.get(detail_id)
                    if not hit:
                        continue

                    qty = _num(detail.get('quantity'))
                    approved_price = _num(hit.get('unitPrice'))
                    approved_tax = _num(hit.get('tax'))
                    detail['unitPrice'] = approved_price
                    detail['tax'] = approved_tax
                    detail['amount'] = _num(hit.get('amount')) or max(0.0, (qty * approved_price) + approved_tax)
                    detail['isFinalChosenPrice'] = True
                    detail['finalPriceSource'] = 'APPROVED_BID'
            except Exception as exc:
                print(f"[PROCUREMENT PR DETAIL] warning: failed to apply awarded pricing: {exc}", flush=True)
            finally:
                gate_ms = round((time.perf_counter() - gate_started) * 1000, 1)

        total_amount = 0.0
        for row in details:
            if not isinstance(row, dict):
                continue
            total_amount += _num(row.get('amount'))

        return {
            'id': resolved_request_id,
            'requestNumber': request_number or None,
            'udfReason': str(header.get('udf_reason') or '').strip(),
            'details': details,
            'totalAmount': total_amount,
            '_perfGateMs': gate_ms,
        }

    try:
        headers = _build_sql_api_auth_headers()
        global PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT
        candidates = []

        if raw_request_id:
            try:
                request_id_int = int(raw_request_id)
                candidates.append((f"{FASTAPI_BASE_URL}/purchaserequest/{request_id_int}", None))
                candidates.append((f"{FASTAPI_BASE_URL}/purchaserequest", {'dockey': request_id_int}))
                candidates.append((f"{FASTAPI_BASE_URL}/purchaserequest", {'id': request_id_int}))
            except ValueError:
                pass

        if request_no:
            candidates.append((f"{FASTAPI_BASE_URL}/purchaserequest/{request_no}", None))
            candidates.append((f"{FASTAPI_BASE_URL}/purchaserequest", {'docno': request_no}))
            candidates.append((f"{FASTAPI_BASE_URL}/purchaserequest", {'requestno': request_no}))

        if PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT and PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT in [u for u, _ in candidates]:
            hinted = [pair for pair in candidates if pair[0] == PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT]
            others = [pair for pair in candidates if pair[0] != PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT]
            candidates = hinted + others

        last_status = 404
        upstream_started = time.perf_counter()
        for url, params in candidates:
            resp = requests.get(
                url,
                params=params,
                headers=headers or None,
                timeout=8,
            )
            last_status = resp.status_code
            if not resp.ok:
                continue

            payload = resp.json() if resp.text else {}
            extracted = _extract_details(payload)
            if extracted is None:
                continue
            PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT = url

            selected_suppliers = _list_selected_suppliers(extracted.get('id'))
            total_ms = round((time.perf_counter() - started_total) * 1000, 1)
            upstream_ms = round((time.perf_counter() - upstream_started) * 1000, 1)
            detail_count = len(extracted.get('details') or [])
            print(
                f"[PROCUREMENT PR DETAIL PERF] request_id={extracted.get('id')} total_ms={total_ms} upstream_ms={upstream_ms} "
                f"gate_ms={_num(extracted.get('_perfGateMs')):.1f} detail_count={detail_count}",
                flush=True
            )

            return jsonify({
                'success': True,
                'id': extracted.get('id'),
                'requestNumber': extracted.get('requestNumber'),
                'udfReason': extracted.get('udfReason'),
                'details': extracted.get('details') or [],
                'totalAmount': _num(extracted.get('totalAmount')),
                'suppliers': selected_suppliers,
                'count': len(extracted.get('details') or []),
            })

        if last_status == 404:
            return jsonify({'success': True, 'details': [], 'count': 0, 'message': 'No details found for this request'}), 200
        return jsonify({'success': False, 'error': f'SQL API returned {last_status}'}), 502
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Purchase request detail request timed out'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach SQL API for purchase request detail'}), 503
    except Exception as exc:
        print(f"[PROCUREMENT PR DETAIL FALLBACK] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


def _resolve_purchase_request_header(raw_request_id, request_no, headers, timeout=12):
    """Resolve one purchase request header via resilient SQL API lookup patterns."""
    def _extract_header(payload):
        if isinstance(payload, dict):
            data_rows = payload.get('data')
            if isinstance(data_rows, list) and data_rows:
                first = data_rows[0]
                if isinstance(first, dict):
                    return first
            if isinstance(data_rows, dict):
                return data_rows
            if any(key in payload for key in ('dockey', 'docno', 'requestno', 'sdsdocdetail')):
                return payload
            return None

        if isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, dict):
                return first

        return None

    candidates = []

    if raw_request_id:
        try:
            request_id_int = int(raw_request_id)
            candidates.append((f"{FASTAPI_BASE_URL}/purchaserequest/{request_id_int}", None))
            candidates.append((f"{FASTAPI_BASE_URL}/purchaserequest", {'dockey': request_id_int}))
            candidates.append((f"{FASTAPI_BASE_URL}/purchaserequest", {'id': request_id_int}))
        except ValueError:
            pass

    if request_no:
        candidates.append((f"{FASTAPI_BASE_URL}/purchaserequest/{request_no}", None))
        candidates.append((f"{FASTAPI_BASE_URL}/purchaserequest", {'docno': request_no}))
        candidates.append((f"{FASTAPI_BASE_URL}/purchaserequest", {'requestno': request_no}))

    global PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT
    if PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT and PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT in [u for u, _ in candidates]:
        hinted = [pair for pair in candidates if pair[0] == PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT]
        others = [pair for pair in candidates if pair[0] != PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT]
        candidates = hinted + others

    request_header = None
    last_status = 404

    for url, params in candidates:
        resp = requests.get(url, params=params, headers=headers or None, timeout=timeout)
        last_status = resp.status_code
        if not resp.ok:
            continue

        payload = resp.json() if resp.text else {}
        request_header = _extract_header(payload)
        if request_header:
            PURCHASE_REQUEST_DETAIL_ENDPOINT_HINT = url
            break

    return request_header, last_status


def _resolve_local_purchase_request_header(raw_request_id, request_no):
    """Fallback: resolve one purchase request from local PH_PQ/PH_PQDTL tables."""
    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()

        header_row = None
        header_cols = []
        request_id = int(raw_request_id) if str(raw_request_id or '').strip().isdigit() else None
        request_no_clean = str(request_no or '').strip()

        if request_id is not None:
            cur.execute('SELECT FIRST 1 * FROM PH_PQ WHERE DOCKEY = ?', (request_id,))
            header_row = cur.fetchone()
            header_cols = [str(col[0] or '').strip().lower() for col in (cur.description or [])]

            if not header_row:
                try:
                    cur.execute('SELECT FIRST 1 * FROM PH_PQ WHERE PQKEY = ?', (request_id,))
                    header_row = cur.fetchone()
                    header_cols = [str(col[0] or '').strip().lower() for col in (cur.description or [])]
                except Exception:
                    pass

            if not header_row:
                try:
                    cur.execute('SELECT FIRST 1 * FROM PH_PQ WHERE ID = ?', (request_id,))
                    header_row = cur.fetchone()
                    header_cols = [str(col[0] or '').strip().lower() for col in (cur.description or [])]
                except Exception:
                    pass

        if not header_row and request_no_clean:
            cur.execute(
                'SELECT FIRST 1 * FROM PH_PQ WHERE TRIM(UPPER(DOCNO)) = TRIM(UPPER(?))',
                (request_no_clean,),
            )
            header_row = cur.fetchone()
            header_cols = [str(col[0] or '').strip().lower() for col in (cur.description or [])]

        if not header_row:
            return None

        header = {header_cols[i]: header_row[i] for i in range(min(len(header_cols), len(header_row)))}
        resolved_dockey = header.get('dockey') or header.get('pqkey') or header.get('id')
        try:
            resolved_dockey = int(resolved_dockey)
        except Exception:
            return None

        cur.execute('SELECT * FROM PH_PQDTL WHERE DOCKEY = ?', (resolved_dockey,))
        detail_rows = cur.fetchall() or []
        detail_cols = [str(col[0] or '').strip().lower() for col in (cur.description or [])]

        mapped_details = []
        for idx, row in enumerate(detail_rows, start=1):
            detail = {detail_cols[i]: row[i] for i in range(min(len(detail_cols), len(row)))}
            mapped_details.append({
                'id': detail.get('dtlkey') or detail.get('pqdtlkey') or detail.get('id') or idx,
                'seq': detail.get('seq') or detail.get('lineno') or detail.get('line_no') or idx,
                'itemCode': str(detail.get('itemcode') or '').strip(),
                'itemName': str(detail.get('itemname') or detail.get('description2') or detail.get('description') or '').strip(),
                'description': str(detail.get('description3') or detail.get('description') or '').strip(),
                'locationCode': str(detail.get('location') or detail.get('loc') or detail.get('stocklocation') or detail.get('storelocation') or '').strip(),
                'deliverydate': detail.get('deliverydate') or detail.get('delivery_date'),
                'quantity': float(detail.get('qty') or detail.get('quantity') or 0),
                'unitPrice': float(detail.get('unitprice') or 0),
                'tax': float(detail.get('taxamt') or detail.get('tax') or 0),
            })

        doc_date_raw = header.get('docdate') or header.get('requestdate')
        doc_date_str = '-'
        if doc_date_raw is not None:
            try:
                if hasattr(doc_date_raw, 'strftime'):
                    doc_date_str = doc_date_raw.strftime('%Y-%m-%d')
                elif hasattr(doc_date_raw, 'isoformat'):
                    doc_date_str = str(doc_date_raw.isoformat())[:10]
                else:
                    doc_date_str = str(doc_date_raw).strip() or '-'
            except Exception:
                doc_date_str = str(doc_date_raw).strip() or '-'

        return {
            'dockey': resolved_dockey,
            'docno': str(header.get('docno') or request_no_clean or '').strip(),
            'code': str(header.get('code') or header.get('supplierid') or '').strip(),
            'docDate': doc_date_str,
            'sdsdocdetail': mapped_details,
            '_localFallback': True,
        }
    except Exception as exc:
        print(f"[PROCUREMENT LOCAL PR LOOKUP] warning: {exc}", flush=True)
        return None
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


@app.route('/api/admin/procurement/bidding/invitations', methods=['POST'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_create_bidding_invitations():
    """Invite multiple suppliers to submit bids for one purchase request."""
    payload = request.get_json(silent=True) or {}
    raw_request_id = str(payload.get('requestId') or '').strip()
    request_no = str(payload.get('requestNumber') or '').strip()
    suppliers = payload.get('suppliers') if isinstance(payload.get('suppliers'), list) else []
    extra_raw = str(payload.get('additionalEmails') or payload.get('extraEmails') or '').strip()
    actor = (session.get('user_email') or session.get('user_name') or 'admin').strip()

    if not raw_request_id and not request_no:
        return jsonify({'success': False, 'error': 'requestId or requestNumber is required'}), 400
    if not suppliers and not extra_raw:
        return jsonify({'success': False, 'error': 'Select supplier(s) or provide additionalEmails'}), 400

    try:
        headers = _build_sql_api_auth_headers()
        request_header, last_status = _resolve_purchase_request_header(raw_request_id, request_no, headers, timeout=12)
        if not request_header:
            request_header = _resolve_local_purchase_request_header(raw_request_id, request_no)

        if not request_header:
            print(
                f"[SUPPLIER BIDDING PR DETAIL] not found request_id={raw_request_id or '-'} request_no={request_no or '-'} last_status={last_status}",
                flush=True,
            )
            if last_status in (200, 404):
                return jsonify({'success': False, 'error': 'Purchase request not found'}), 404
            return jsonify({'success': False, 'error': f'SQL API returned {last_status} while loading purchase request'}), 502

        request_dockey = int(request_header.get('dockey'))
        request_docno = str(request_header.get('docno') or request_no or '').strip()
        if suppliers:
            result = create_bid_invitations(request_dockey, request_docno, suppliers, actor)
        else:
            result = {
                'requestDockey': request_dockey,
                'requestNumber': request_docno,
                'invitedCount': 0,
                'inserted': 0,
                'updated': 0,
            }
        try:
            normalized = _normalize_supplier_rows(suppliers) if suppliers else []
            email_targets = _resolve_invitation_email_targets(normalized)
            for em in _parse_additional_email_recipients(extra_raw):
                email_targets.append({'email': em, 'code': '', 'name': 'Colleague'})
            email_targets = _dedupe_invitation_targets_by_email(email_targets)
            lines, req_date = _local_pr_lines_for_rfq_email(request_dockey, request_docno)
            if email_targets:
                threading.Thread(
                    target=_send_rfq_invitation_emails_background,
                    args=(email_targets, request_docno, req_date, lines),
                    daemon=True,
                ).start()
                result['rfqEmailsQueued'] = len(email_targets)
            else:
                result['rfqEmailsQueued'] = 0
                result['rfqEmailNote'] = (
                    'No supplier emails on file; invitations are saved for portal access. '
                    'Add UDF email in accounting or use “Additional notify emails” below.'
                )
        except Exception as mail_exc:
            print(f"[PROCUREMENT BIDDING INVITE] RFQ email queue error: {mail_exc}", flush=True)
            result['rfqEmailsQueued'] = 0
            result['rfqEmailWarning'] = str(mail_exc)

        gate = get_transfer_gate_state(request_dockey)
        return jsonify({'success': True, 'message': 'Bidding invitations saved', 'data': result, 'gate': gate})
    except BiddingValidationError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Purchase request lookup timed out'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach SQL API for purchase request lookup'}), 503
    except Exception as exc:
        print(f"[PROCUREMENT BIDDING INVITE] error: {exc}", flush=True)
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/procurement/bidding/my-invitations', methods=['GET'])
@api_login_required(unauth_message='Unauthorized')
def api_supplier_bidding_invitations():
    """List current user's bidding invitations."""
    if infer_access_tier_from_session(session) != ACCESS_TIER_SUPPLIER:
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    supplier_code = (session.get('supplier_code') or session.get('customer_code') or '').strip()
    if not supplier_code:
        return jsonify({'success': False, 'error': 'supplier code is not available in session'}), 400

    try:
        rows = list_supplier_invitations(supplier_code)
        return jsonify({'success': True, 'data': rows, 'count': len(rows), 'supplierCode': supplier_code})
    except BiddingValidationError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        print(f"[SUPPLIER BIDDING INVITES] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/procurement/bidding/purchase-request-details', methods=['GET'])
@api_login_required(unauth_message='Unauthorized')
def api_supplier_bidding_request_details():
    """Get one purchase request with details for invited supplier bidding."""
    raw_request_id = str(request.args.get('request_id') or '').strip()
    request_no = str(request.args.get('request_no') or '').strip()

    if not raw_request_id and not request_no:
        return jsonify({'success': False, 'error': 'request_id or request_no is required'}), 400

    if infer_access_tier_from_session(session) != ACCESS_TIER_SUPPLIER:
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    supplier_session_code = (session.get('supplier_code') or session.get('customer_code') or '').strip()
    if not supplier_session_code:
        return jsonify({'success': False, 'error': 'Supplier code is not available in session'}), 400

    try:
        def _lookup_detail_delivery_dates(request_dockey: int, detail_ids: list[int]) -> dict[int, str]:
            if not request_dockey or not detail_ids:
                return {}
            con = None
            cur = None
            try:
                from utils.procurement_purchase_request import _get_table_columns, _pick_existing

                con = get_db_connection()
                cur = con.cursor()
                detail_cols = _get_table_columns(cur, "PH_PQDTL")
                dtl_key_col = _pick_existing(detail_cols, "DTLKEY", "PQDTLKEY", "ID")
                fk_col = _pick_existing(detail_cols, "DOCKEY", "PQKEY", "REQUEST_ID", "HEADER_ID")
                del_col = _pick_existing(detail_cols, "DELIVERYDATE", "DELIVERY_DATE", "REQUIREDDATE")
                if not dtl_key_col or not fk_col or not del_col:
                    return {}
                placeholders = ', '.join(['?'] * len(detail_ids))
                cur.execute(
                    f"""
                    SELECT {dtl_key_col}, {del_col}
                    FROM PH_PQDTL
                    WHERE {fk_col} = ?
                      AND {dtl_key_col} IN ({placeholders})
                    """,
                    tuple([int(request_dockey), *[int(x) for x in detail_ids]]),
                )
                result = {}
                for row in (cur.fetchall() or []):
                    if not row:
                        continue
                    try:
                        key = int(row[0])
                    except Exception:
                        continue
                    value = row[1]
                    if value is None:
                        continue
                    if hasattr(value, 'isoformat'):
                        result[key] = value.isoformat()
                    else:
                        result[key] = str(value)
                return result
            except Exception:
                return {}
            finally:
                if cur:
                    cur.close()
                if con:
                    con.close()

        def _lookup_ph_pq_header_delivery(request_dockey: int):
            out = {}
            if not request_dockey:
                return out
            con = None
            cur = None
            try:
                from utils.procurement_purchase_request import _get_table_columns, _pick_existing

                con = get_db_connection()
                cur = con.cursor()
                header_cols = _get_table_columns(cur, "PH_PQ")
                key_col = _pick_existing(header_cols, "DOCKEY", "PQKEY", "ID")
                req_col = _pick_existing(header_cols, "REQUIREDDATE", "DELIVERYDATE")
                doc_col = _pick_existing(header_cols, "DOCDATE", "POSTDATE", "REQUESTDATE")
                if not key_col:
                    return out
                pieces: list[str] = []
                if req_col:
                    pieces.append(req_col)
                if doc_col:
                    pieces.append(doc_col)
                if not pieces:
                    return out
                cur.execute(
                    f"SELECT FIRST 1 {', '.join(pieces)} FROM PH_PQ WHERE {key_col} = ?",
                    (int(request_dockey),),
                )
                row = cur.fetchone()
                if not row:
                    return out
                idx = 0
                if req_col:
                    v = row[idx]
                    if v is not None:
                        out['requiredDeliveryDate'] = v.isoformat() if hasattr(v, 'isoformat') else str(v)
                    idx += 1
                if doc_col:
                    v = row[idx]
                    if v is not None:
                        out['documentDate'] = v.isoformat() if hasattr(v, 'isoformat') else str(v)
                return out
            except Exception:
                return out
            finally:
                if cur:
                    cur.close()
                if con:
                    con.close()

        headers = _build_sql_api_auth_headers()
        request_header, last_status = _resolve_purchase_request_header(raw_request_id, request_no, headers, timeout=12)
        if not request_header:
            request_header = _resolve_local_purchase_request_header(raw_request_id, request_no)

        if not request_header:
            if last_status in (200, 404):
                return jsonify({'success': False, 'error': 'Purchase request not found'}), 404
            return jsonify({'success': False, 'error': f'SQL API returned {last_status} while loading purchase request'}), 502

        details = []
        header_delivery_fallback = (
            request_header.get('postdate')
            or request_header.get('requiredDate')
            or request_header.get('requestdate')
            or request_header.get('docdate')
        )
        request_dockey_value = request_header.get('dockey')
        try:
            request_dockey_int = int(request_dockey_value)
        except Exception:
            request_dockey_int = 0

        if not request_dockey_int or not supplier_has_active_bid_invitation(
            request_dockey_int, supplier_session_code
        ):
            return jsonify({'success': False, 'error': 'Forbidden'}), 403

        pq_meta = _lookup_ph_pq_header_delivery(request_dockey_int)

        raw_rows = request_header.get('sdsdocdetail') or []
        detail_ids_for_lookup: list[int] = []
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            if row.get('deliverydate') or row.get('deliveryDate'):
                continue
            try:
                detail_ids_for_lookup.append(int(row.get('dtlkey') or row.get('id')))
            except Exception:
                continue
        delivery_lookup = _lookup_detail_delivery_dates(request_dockey_int, detail_ids_for_lookup)
        for idx, row in enumerate(raw_rows, start=1):
            if not isinstance(row, dict):
                continue
            detail_id_raw = row.get('dtlkey') or row.get('id')
            try:
                detail_id_int = int(detail_id_raw)
            except Exception:
                detail_id_int = 0
            row_delivery = row.get('deliverydate') or row.get('deliveryDate')
            lookup_delivery = delivery_lookup.get(detail_id_int)
            resolved_delivery = (
                row_delivery
                or lookup_delivery
                or pq_meta.get('requiredDeliveryDate')
                or header_delivery_fallback
            )
            delivery_source = (
                'row'
                if row_delivery
                else ('db_lookup' if lookup_delivery else ('header_fallback' if header_delivery_fallback else 'missing'))
            )
            if os.getenv('PROCUREMENT_DEBUG_DELIVERYDATES', '').strip().lower() in ('1', 'true', 'yes', 'on'):
                print(
                    f"[SUPPLIER BIDDING DELIVERYDATE] request={request_header.get('dockey')} "
                    f"detail={detail_id_int or detail_id_raw} source={delivery_source} value={resolved_delivery}",
                    flush=True,
                )
            details.append({
                'id': row.get('dtlkey') or row.get('id'),
                'seq': row.get('seq') if row.get('seq') is not None else idx,
                'itemCode': str(row.get('itemcode') or row.get('itemCode') or '').strip(),
                'itemName': str(row.get('itemname') or row.get('itemName') or row.get('description2') or row.get('description') or '').strip(),
                'description': str(row.get('description3') or row.get('description') or '').strip(),
                'locationCode': str(row.get('location') or row.get('locationCode') or '').strip(),
                'deliveryDate': resolved_delivery,
                'quantity': float(row.get('qty') or row.get('quantity') or 0),
                'unitPrice': float(row.get('unitprice') or row.get('unitPrice') or 0),
                'tax': float(row.get('taxamt') or row.get('tax') or 0),
            })

        api_required = (
            request_header.get('requireddate')
            or request_header.get('requiredDate')
            or request_header.get('deliverydate')
        )
        required_for_pr = pq_meta.get('requiredDeliveryDate') or api_required or header_delivery_fallback

        my_bid = None
        if request_dockey_int:
            my_bid = get_supplier_bid_snapshot(request_dockey_int, supplier_session_code)

        return jsonify({
            'success': True,
            'requestId': request_header.get('dockey'),
            'requestNumber': str(request_header.get('docno') or '').strip(),
            'supplierCode': str(request_header.get('code') or '').strip(),
            'details': details,
            'count': len(details),
            'requiredDeliveryDate': required_for_pr,
            'documentDate': pq_meta.get('documentDate'),
            'myBid': my_bid,
        })
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Purchase request lookup timed out'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach SQL API for purchase request lookup'}), 503
    except Exception as exc:
        print(f"[SUPPLIER BIDDING PR DETAIL] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/procurement/bidding/submit', methods=['POST'])
@api_login_required(unauth_message='Unauthorized')
def api_supplier_submit_bid():
    """Submit supplier bid lines for an invited purchase request."""
    if infer_access_tier_from_session(session) != ACCESS_TIER_SUPPLIER:
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    raw_request_id = str(payload.get('requestId') or '').strip()
    request_no = str(payload.get('requestNumber') or '').strip()
    bid_lines = payload.get('bidLines') if isinstance(payload.get('bidLines'), list) else []
    remarks = str(payload.get('remarks') or '').strip()

    supplier_code = (session.get('supplier_code') or session.get('customer_code') or '').strip()
    supplier_name = str(payload.get('supplierName') or session.get('user_email') or '').strip()
    actor = (session.get('user_email') or supplier_code or 'supplier').strip()

    if not raw_request_id and not request_no:
        return jsonify({'success': False, 'error': 'requestId or requestNumber is required'}), 400
    if not supplier_code:
        return jsonify({'success': False, 'error': 'supplierCode is required'}), 400
    if not bid_lines:
        return jsonify({'success': False, 'error': 'bidLines[] is required'}), 400

    try:
        headers = _build_sql_api_auth_headers()
        request_header, last_status = _resolve_purchase_request_header(raw_request_id, request_no, headers, timeout=12)
        if not request_header:
            request_header = _resolve_local_purchase_request_header(raw_request_id, request_no)

        if not request_header:
            if last_status in (200, 404):
                return jsonify({'success': False, 'error': 'Purchase request not found'}), 404
            return jsonify({'success': False, 'error': f'SQL API returned {last_status} while loading purchase request'}), 502

        request_dockey = int(request_header.get('dockey'))
        request_docno = str(request_header.get('docno') or '').strip()
        result = submit_supplier_bid(
            request_dockey=request_dockey,
            request_no=request_docno,
            supplier_code=supplier_code,
            supplier_name=supplier_name,
            bid_lines=bid_lines,
            remarks=remarks,
            created_by=actor,
        )
        return jsonify({'success': True, 'message': 'Bid submitted successfully', 'data': result})
    except BiddingValidationError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Purchase request lookup timed out'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach SQL API for purchase request lookup'}), 503
    except Exception as exc:
        print(f"[SUPPLIER BIDDING SUBMIT] error: {exc}", flush=True)
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/admin/procurement/purchase-requests/<int:request_id>/bids', methods=['GET'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_list_request_bids(request_id):
    """List supplier bids and transfer gate state for one purchase request."""
    try:
        bids = list_bids_for_request(request_id)
        gate = get_transfer_gate_state(request_id)
        return jsonify({'success': True, 'data': bids, 'count': len(bids), 'gate': gate})
    except Exception as exc:
        print(f"[PROCUREMENT BIDDING LIST] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/admin/procurement/purchase-requests/<int:request_id>/bids/line-awards', methods=['POST'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_save_bid_line_awards(request_id):
    """Save per-item awarded supplier selections for one purchase request."""
    payload = request.get_json(silent=True) or {}
    awards = payload.get('awards') if isinstance(payload.get('awards'), list) else []
    udf_reason = str(payload.get('udfReason') or payload.get('reason') or '').strip()
    actor = (session.get('user_email') or session.get('user_name') or 'admin').strip()
    try:
        result = save_line_awards(request_id, awards, actor, udf_reason)
        gate = get_transfer_gate_state(request_id)
        return jsonify({'success': True, 'message': 'Line awards saved', 'data': result, 'gate': gate})
    except BiddingValidationError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        print(f"[PROCUREMENT BIDDING LINE AWARD] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/admin/procurement/purchase-requests/<int:request_id>/bids/<int:bid_id>/approve', methods=['POST'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_approve_bid(request_id, bid_id):
    """Approve one supplier bid for a purchase request."""
    payload = request.get_json(silent=True) or {}
    udf_reason = str(payload.get('udfReason') or payload.get('reason') or '').strip()
    actor = (session.get('user_email') or session.get('user_name') or 'admin').strip()
    try:
        result = approve_bid(request_id, bid_id, actor, udf_reason)
        gate = get_transfer_gate_state(request_id)
        return jsonify({'success': True, 'message': 'Bid approved', 'data': result, 'gate': gate})
    except BiddingValidationError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        print(f"[PROCUREMENT BIDDING APPROVE] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/admin/procurement/purchase-requests/<int:request_id>/bids/<int:bid_id>/reject', methods=['POST'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_reject_bid(request_id, bid_id):
    """Reject one supplier bid for a purchase request."""
    payload = request.get_json(silent=True) or {}
    actor = (session.get('user_email') or session.get('user_name') or 'admin').strip()
    udf_reason = str(payload.get('udfReason') or payload.get('reason') or payload.get('remarks') or '').strip()
    try:
        result = reject_bid(request_id, bid_id, actor, udf_reason)
        gate = get_transfer_gate_state(request_id)
        return jsonify({'success': True, 'message': 'Bid rejected', 'data': result, 'gate': gate})
    except BiddingValidationError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        print(f"[PROCUREMENT BIDDING REJECT] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/admin/procurement/purchase-requests/transfer-to-po', methods=['POST'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_transfer_purchase_request_to_po():
    """Transfer approved purchase request detail quantities into PH_PO/PH_PODTL and ST_XTRANS."""
    payload = request.get_json(silent=True) or {}
    raw_request_id = str(payload.get('requestId') or '').strip()
    request_no = str(payload.get('requestNumber') or '').strip()
    transfer_lines = payload.get('transferLines') if isinstance(payload.get('transferLines'), list) else []
    supplier = payload.get('supplier') if isinstance(payload.get('supplier'), dict) else {}
    transfer_date = payload.get('transferDate')
    actor = (session.get('user_email') or session.get('user_name') or 'admin').strip()

    if not raw_request_id and not request_no:
        return jsonify({'success': False, 'error': 'requestId or requestNumber is required'}), 400
    if not transfer_lines:
        return jsonify({'success': False, 'error': 'transferLines[] is required'}), 400

    try:
        headers = _build_sql_api_auth_headers()
        request_header, last_status = _resolve_purchase_request_header(raw_request_id, request_no, headers, timeout=12)

        if not request_header:
            request_header = _resolve_local_purchase_request_header(raw_request_id, request_no)

        if not request_header:
            if last_status in (200, 404):
                return jsonify({'success': False, 'error': 'Purchase request not found'}), 404
            return jsonify({'success': False, 'error': f'SQL API returned {last_status} while loading purchase request'}), 502

        request_dockey = int(request_header.get('dockey'))

        udf_status_text = str(
            request_header.get('udf_status')
            or request_header.get('udfStatus')
            or request_header.get('UDF_STATUS')
            or ''
        ).strip().upper()
        if udf_status_text == 'ACTIVE':
            udf_status_text = 'APPROVED'
        elif udf_status_text == 'INACTIVE':
            udf_status_text = 'CANCELLED'
        if udf_status_text != 'APPROVED':
            return jsonify({'success': False, 'error': 'Transfer is allowed only when purchase request UDF status is APPROVED'}), 400

        awarded_lines = validate_transfer_against_line_awards(request_dockey, transfer_lines)
        request_for_transfer = apply_awarded_lines_to_request(request_header, awarded_lines)

        # Resolve supplier master data (especially currency) from SQL supplier API by selected supplier code.
        def _resolve_supplier_master(selected_code: str, fallback_name: str = ''):
            code = str(selected_code or '').strip()
            if not code:
                return {}
            hit_supplier = {}
            offset = 0
            limit = 100
            while True:
                resp = requests.get(
                    f"{FASTAPI_BASE_URL}/supplier",
                    params={'offset': offset, 'limit': limit},
                    headers=headers or None,
                    timeout=10,
                )
                if not resp.ok:
                    break

                supplier_payload = resp.json() if resp.text else {}
                supplier_rows = supplier_payload.get('data', []) if isinstance(supplier_payload, dict) else []
                if not isinstance(supplier_rows, list) or not supplier_rows:
                    break

                for row in supplier_rows:
                    if not isinstance(row, dict):
                        continue
                    if str(row.get('code') or '').strip() == code:
                        hit_supplier = row
                        break
                if hit_supplier:
                    break

                pagination = supplier_payload.get('pagination', {}) if isinstance(supplier_payload, dict) else {}
                total_count = pagination.get('count', len(supplier_rows)) if isinstance(pagination, dict) else len(supplier_rows)
                offset += limit
                if offset >= total_count:
                    break

            if not hit_supplier:
                hit_supplier = {}
            if not hit_supplier.get('code'):
                hit_supplier['code'] = code
            if not hit_supplier.get('companyname'):
                hit_supplier['companyname'] = str(fallback_name or '').strip()
            return hit_supplier

        supplier_groups: dict[str, dict[str, object]] = {}
        if awarded_lines:
            award_by_detail = {
                int(line.get('detailId')): line
                for line in awarded_lines
                if isinstance(line, dict) and str(line.get('detailId') or '').strip()
            }
            for row in transfer_lines:
                if not isinstance(row, dict):
                    continue
                raw_detail_id = row.get('fromdtlkey', row.get('dtlkey', row.get('detailId')))
                try:
                    detail_id = int(raw_detail_id)
                except Exception:
                    continue
                award = award_by_detail.get(detail_id)
                if not award:
                    continue
                supplier_code = str(award.get('supplierCode') or '').strip()
                supplier_name = str(award.get('supplierName') or '').strip()
                if not supplier_code:
                    return jsonify({'success': False, 'error': f'No supplier code found for awarded detail {detail_id}'}), 400
                bucket = supplier_groups.setdefault(
                    supplier_code,
                    {'supplierName': supplier_name, 'lines': []},
                )
                bucket['lines'].append(row)
        else:
            supplier_code = str(supplier.get('code') or request_for_transfer.get('code') or '').strip()
            supplier_name = str(supplier.get('companyname') or request_for_transfer.get('companyname') or '').strip()
            if not supplier_code:
                return jsonify({'success': False, 'error': 'Supplier code is required for transfer'}), 400
            supplier_groups[supplier_code] = {'supplierName': supplier_name, 'lines': transfer_lines}

        if not supplier_groups:
            return jsonify({'success': False, 'error': 'No transferable awarded lines found'}), 400

        transfer_results = []
        total_transferred_qty = 0.0
        total_line_count = 0
        for supplier_code, info in supplier_groups.items():
            supplier_name = str(info.get('supplierName') or '').strip()
            group_lines = info.get('lines') if isinstance(info.get('lines'), list) else []
            if not group_lines:
                continue
            supplier_master = _resolve_supplier_master(supplier_code, supplier_name)
            result = transfer_purchase_request_to_po(
                purchase_request=request_for_transfer,
                transfer_lines=group_lines,
                supplier=supplier_master,
                created_by=actor,
                transfer_date=transfer_date,
            )
            transfer_results.append(result)
            total_transferred_qty += float(result.get('transferredQty') or 0.0)
            total_line_count += int(result.get('lineCount') or 0)

        if not transfer_results:
            return jsonify({'success': False, 'error': 'No purchase order created from selected lines'}), 400

        return jsonify({
            'success': True,
            'message': 'Purchase request transferred to purchase order successfully',
            'data': {
                'poNumber': transfer_results[0].get('poNumber'),
                'poDockey': transfer_results[0].get('poDockey'),
                'poNumbers': [str(r.get('poNumber') or '').strip() for r in transfer_results if str(r.get('poNumber') or '').strip()],
                'results': transfer_results,
                'lineCount': total_line_count,
                'transferredQty': total_transferred_qty,
            },
        })
    except BiddingValidationError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except PurchaseOrderTransferValidationError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Purchase request lookup timed out'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach SQL API for purchase request lookup'}), 503
    except Exception as exc:
        print(f"[PROCUREMENT PR TRANSFER] error: {exc}", flush=True)
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/admin/procurement/purchase-requests/<request_number>/status', methods=['PATCH'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_update_purchase_request_status(request_number):
    """Update purchase request status across workflow states."""
    if not can_access_purchase_menu(session):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    raw_target_status = payload.get('status')
    target_status = '' if raw_target_status is None else str(raw_target_status).strip()
    actor = (session.get('user_email') or session.get('user_name') or 'admin').strip()

    target_norm = normalize_purchase_request_status_input(raw_target_status)
    if not target_norm:
        return jsonify({'success': False, 'error': 'status is required'}), 400

    try:
        current_status = peek_purchase_request_status_by_request_number(request_number)
    except PurchaseRequestValidationError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    if not can_patch_pr_workflow_status(session, current_status, target_norm):
        return jsonify({'success': False, 'error': 'Insufficient permissions for this status change'}), 403

    try:
        result = transition_purchase_request_status(request_number, target_status, actor)
        return jsonify({'success': True, 'message': 'Status updated', 'data': result})
    except PurchaseRequestValidationError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        print(f"[PROCUREMENT PR STATUS] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/get_product_price')
@api_login_required(unauth_message='Unauthorized')
def api_get_product_price():
    """Get product price by description using configurable pricing priority rules when possible."""
    description = request.args.get('description', '').strip()
    if not description:
        return jsonify({'success': False, 'error': 'Description required'}), 400

    customer_code = session.get('customer_code')
    if not customer_code:
        # Backfill customer code for legacy sessions so pricing priority rules can run.
        user_email = session.get('user_email')
        if user_email:
            con = None
            cur = None
            try:
                con = get_db_connection()
                cur = con.cursor()
                customer_code = find_customer_code_by_email(cur, user_email)
                if customer_code:
                    session['customer_code'] = customer_code
            except Exception as backfill_error:
                print(f"[PRICING WARNING] Failed to backfill customer_code for {user_email}: {backfill_error}", flush=True)
            finally:
                if cur:
                    cur.close()
                if con:
                    con.close()

    def build_price_response(price_item, match_type):
        fallback_price = float(price_item.get('STOCKVALUE', 0) or 0)
        item_code = (price_item.get('CODE') or '').strip()
        local_st_item_price = price_item.get('UDF_STDPRICE', None)
        no_match_message = None

        st_item_extras = {'udfMoq': '', 'udfDleadtime': '', 'udfBundle': ''}

        # Fetch ST_ITEM.UDF_STDPRICE for Suggested Price field when not provided; always load MOQ / lead / bundle when CODE known.
        st_item_udf_stdprice = None
        if local_st_item_price is not None:
            try:
                st_item_udf_stdprice = float(local_st_item_price)
            except Exception:
                st_item_udf_stdprice = None

        if item_code:
            con = None
            cur = None
            try:
                con = get_db_connection()
                cur = con.cursor()
                st_item_extras = get_st_item_quotation_display_fields(cur, item_code)
                if st_item_udf_stdprice is None:
                    st_item_udf_stdprice = get_st_item_udf_stdprice(cur, item_code)
            except Exception as st_item_error:
                print(f"[PRICING WARNING] Failed to fetch ST_ITEM fields for {item_code}: {st_item_error}", flush=True)
            finally:
                if cur:
                    cur.close()
                if con:
                    con.close()

        if customer_code and item_code:
            try:
                pricing_result = get_selling_price(customer_code, item_code)
                selected_price = float(pricing_result.get('SelectedPrice') or 0)
                # Honor priority engine result even when 0 (no rules enabled, no match, or rule yields zero).
                return jsonify({
                    'success': True,
                    'price': selected_price,
                    'stItemPrice': st_item_udf_stdprice if st_item_udf_stdprice is not None else 0,
                    'suggestedPrice': selected_price,
                    'suggestedSource': pricing_result.get('PriceSource'),
                    'suggestedMatchedRuleCode': pricing_result.get('MatchedRuleCode'),
                    'source': pricing_result.get('PriceSource'),
                    'matchedRuleCode': pricing_result.get('MatchedRuleCode'),
                    'message': pricing_result.get('Message'),
                    'itemCode': item_code,
                    'matchType': match_type,
                    'udfMoq': st_item_extras.get('udfMoq', ''),
                    'udfDleadtime': st_item_extras.get('udfDleadtime', ''),
                    'udfBundle': st_item_extras.get('udfBundle', ''),
                })
            except Exception as pricing_error:
                print(f"[PRICING WARNING] Falling back to stock price for {item_code}: {pricing_error}", flush=True)
                no_match_message = f'Pricing rule evaluation failed: {pricing_error}'

        if st_item_udf_stdprice is not None and st_item_udf_stdprice > 0:
            fallback_price = st_item_udf_stdprice

        return jsonify({
            'success': True,
            'price': fallback_price,
            'stItemPrice': st_item_udf_stdprice if st_item_udf_stdprice is not None else 0,
            'suggestedPrice': None,
            'suggestedSource': None,
            'suggestedMatchedRuleCode': None,
            'source': 'Fallback Stock Price',
            'matchedRuleCode': None,
            'message': 'Price selected from fallback stock price',
            'suggestedReason': no_match_message or 'No prioritized price found for current customer/item',
            'itemCode': item_code,
            'matchType': match_type,
            'udfMoq': st_item_extras.get('udfMoq', ''),
            'udfDleadtime': st_item_extras.get('udfDleadtime', ''),
            'udfBundle': st_item_extras.get('udfBundle', ''),
        })

    try:
        # First preference: resolve directly from ST_ITEM (dropdown source) and use UDF_STDPRICE.
        con = None
        cur = None
        try:
            con = get_db_connection()
            cur = con.cursor()

            seed_item = find_price_seed_item(cur, description)

            if seed_item:
                local_item = {
                    'CODE': seed_item.get('CODE', ''),
                    'DESCRIPTION': seed_item.get('DESCRIPTION', ''),
                    'UDF_STDPRICE': seed_item.get('UDF_STDPRICE'),
                    'STOCKVALUE': seed_item.get('UDF_STDPRICE') if seed_item.get('UDF_STDPRICE') is not None else 0,
                }
                return build_price_response(local_item, 'st_item_exact')

            # Fuzzy fallback against ST_ITEM descriptions.
            cur.execute('SELECT CODE, DESCRIPTION, UDF_STDPRICE FROM ST_ITEM')
            st_rows = cur.fetchall() or []
            from difflib import SequenceMatcher
            best_row = None
            best_ratio = 0.0
            lowered_description = description.lower()
            for st_row in st_rows:
                st_desc = (st_row[1] or '').strip() if st_row and len(st_row) > 1 and st_row[1] else ''
                if not st_desc:
                    continue
                ratio = SequenceMatcher(None, lowered_description, st_desc.lower()).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_row = st_row

            if best_row and best_ratio >= 0.85:
                local_item = {
                    'CODE': (best_row[0] or '').strip() if best_row[0] else '',
                    'DESCRIPTION': (best_row[1] or '').strip() if best_row[1] else '',
                    'UDF_STDPRICE': best_row[2],
                    'STOCKVALUE': best_row[2] if best_row[2] is not None else 0,
                }
                return build_price_response(local_item, 'st_item_fuzzy')
        except Exception as st_item_lookup_error:
            print(f"[PRICING WARNING] ST_ITEM lookup failed for '{description}': {st_item_lookup_error}", flush=True)
        finally:
            if cur:
                cur.close()
            if con:
                con.close()

        # Legacy fallback path: stockitemprice API.
        stock_prices = fetch_data_from_api("stockitemprice")

        for price_item in stock_prices:
            price_desc = price_item.get('DESCRIPTION', '')
            price_code = price_item.get('CODE', '')
            if (description and price_desc.lower() == description.lower()) or \
               (description and price_code.lower() == description.lower()):
                return build_price_response(price_item, 'exact')

        from difflib import SequenceMatcher
        best_match = None
        best_ratio = 0.0
        for price_item in stock_prices:
            price_desc = price_item.get('DESCRIPTION', '')
            if price_desc:
                ratio = SequenceMatcher(None, description.lower(), price_desc.lower()).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = price_item

        if best_match and best_ratio >= 0.85:
            return build_price_response(best_match, 'fuzzy')

        return jsonify({'success': False, 'error': 'Price not found'}), 404
    except Exception as e:
        print(f"Error getting product price: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/procurement/purchase-requests/<int:request_id>/edit', methods=['PATCH'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_edit_purchase_request(request_id):
    """Edit draft purchase request header/detail values from View PR."""
    payload = request.get_json(silent=True) or {}
    actor = (session.get('user_email') or session.get('user_name') or 'admin').strip()

    try:
        result = update_purchase_request(request_id, payload, actor)
        if isinstance(payload.get('suppliers'), list):
            _save_selected_suppliers(request_id, result.get('requestNumber'), payload.get('suppliers') or [], actor)
        return jsonify({'success': True, 'message': 'Purchase request updated', 'data': result})
    except PurchaseRequestValidationError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        print(f"[PROCUREMENT PR EDIT] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/admin/procurement/purchase-requests/details/approval', methods=['POST'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_purchase_request_detail_approval_update():
    """Update UDF_PQAPPROVED for purchase request detail rows."""
    if not can_update_pr_approvals_and_header_status(session):
        return jsonify({'success': False, 'error': 'Insufficient permissions to update PR line approvals'}), 403
    payload = request.get_json(silent=True) or {}

    try:
        headers = _build_sql_api_auth_headers()
        resp = requests.post(
            f"{FASTAPI_BASE_URL}/purchaserequest/detail-approval",
            json=payload,
            headers=headers or None,
            timeout=12,
        )

        if not resp.ok:
            message = ''
            try:
                body = resp.json()
                message = body.get('detail') if isinstance(body, dict) else ''
            except Exception:
                message = (resp.text or '').strip()
            err = f"SQL API returned {resp.status_code}" + (f": {message}" if message else '')
            return jsonify({'success': False, 'error': err}), 502

        body = resp.json() if resp.text else {}
        return jsonify({'success': True, 'data': body})
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Approval update request timed out'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach SQL API for approval update'}), 503
    except Exception as exc:
        print(f"[PROCUREMENT PR APPROVAL UPDATE] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500

@app.route('/api/create_order', methods=['POST'])
@api_login_required(unauth_message='Unauthorized')
def api_create_order():
    """Create a new order from the order form"""
    user_email = session.get('user_email')
    customer_code = session.get('customer_code')
    data = request.get_json() or {}
    description = data.get('description', '').strip()
    items = data.get('items', [])
    
    if not items:
        return jsonify({'success': False, 'error': 'At least one item is required'}), 400
    
    try:
        # Call PHP endpoint to create order
        order_response = requests.post(
            f"{BASE_API_URL}/php/insertOrderByManual.php",
            json={
                "ownerEmail": user_email,
                "customerCode": customer_code,
                "orderName": description,
                "items": items
            },
            timeout=10
        )
        
        order_data = order_response.json()
        
        if not order_data.get('success'):
            return jsonify({'success': False, 'error': order_data.get('error', 'Failed to create order')}), 500
        
        return jsonify({'success': True, 'orderid': order_data.get('orderid')})
    except Exception as e:
        print(f"Error creating order: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/procurement/purchase-requests/header-status', methods=['POST'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_purchase_request_header_status_update():
    """Update UDF_STATUS for purchase request headers."""
    if not can_update_pr_approvals_and_header_status(session):
        return jsonify({'success': False, 'error': 'Insufficient permissions to update PR header status'}), 403
    payload = request.get_json(silent=True) or {}

    try:
        headers = _build_sql_api_auth_headers()
        resp = requests.post(
            f"{FASTAPI_BASE_URL}/purchaserequest/header-status",
            json=payload,
            headers=headers or None,
            timeout=12,
        )

        if not resp.ok:
            message = ''
            try:
                body = resp.json()
                message = body.get('detail') if isinstance(body, dict) else ''
            except Exception:
                message = (resp.text or '').strip()
            err = f"SQL API returned {resp.status_code}" + (f": {message}" if message else '')
            return jsonify({'success': False, 'error': err}), 502

        body = resp.json() if resp.text else {}
        return jsonify({'success': True, 'data': body})
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Header status update request timed out'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'Cannot reach SQL API for header status update'}), 503
    except Exception as exc:
        print(f"[PROCUREMENT PR HEADER STATUS UPDATE] error: {exc}", flush=True)
        return jsonify({'success': False, 'error': str(exc)}), 500

@app.route('/api/create_quotation', methods=['POST'])
@api_login_required(unauth_message='Session expired. Please log in again.')
def api_create_quotation():
    """Create or update a quotation in the accounting system (SL_QT)"""
    if not can_access_create_quotation(session):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    customer_code = session.get('customer_code')
    data = request.get_json() or {}
    dockey = data.get('dockey', None)  # If present, update existing quotation
    draft_dockey = data.get('draftDockey', None)
    items = data.get('items', [])
    company_name = data.get('companyName', '')
    
    # DEBUG: Log entry point and dockey value
    print(f"DEBUG [Flask api_create_quotation]: ENTERED - dockey={dockey}, companyName={company_name}", flush=True)
    
    if not items:
        print(f"DEBUG [Flask api_create_quotation]: No items provided", flush=True)
        return jsonify({'success': False, 'error': 'At least one item is required'}), 400
    
    try:
        if dockey:
            print(f"DEBUG [Flask]: UPDATING quotation - dockey={dockey}", flush=True)
        else:
            print(f"DEBUG [Flask]: CREATING new quotation - companyName: {company_name}", flush=True)

        quotation_data = create_or_update_quotation(BASE_API_URL, customer_code, data)
        
        if not quotation_data.get('success'):
            return jsonify({'success': False, 'error': quotation_data.get('error', 'Failed to create quotation')}), 500

        if draft_dockey:
            try:
                con = get_db_connection()
                cur = con.cursor()
                cur.execute('DELETE FROM SL_QTDTLDRAFT WHERE DOCKEY = ?', (draft_dockey,))
                cur.execute('DELETE FROM SL_QTDRAFT WHERE DOCKEY = ? AND CODE = ?', (draft_dockey, customer_code))
                con.commit()
                cur.close()
                con.close()
                print(f"DEBUG [Flask api_create_quotation]: Deleted draft DOCKEY={draft_dockey} after successful submission", flush=True)
            except Exception as cleanup_error:
                print(f"WARNING [Flask api_create_quotation]: Failed to delete draft DOCKEY={draft_dockey}: {cleanup_error}", flush=True)
        
        return jsonify({
            'success': True, 
            'dockey': quotation_data.get('dockey'),
            'docno': quotation_data.get('docno'),
            'message': quotation_data.get('message')
        })
    except Exception as e:
        print(f"Error creating/updating quotation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/save_draft_quotation', methods=['POST'])
@api_login_required(unauth_message='Session expired. Please log in again.')
def api_save_draft_quotation():
    """Save quotation draft into SL_QTDRAFT/SL_QTDTLDRAFT."""
    if not can_access_create_quotation(session):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    customer_code = get_current_customer_code(resolve_missing=False)
    data = request.get_json() or {}

    if not customer_code:
        return jsonify({'success': False, 'error': 'Customer code not found in session'}), 400

    try:
        result = save_draft_quotation(BASE_API_URL, customer_code, data)
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Failed to save draft quotation')}), 500

        return jsonify({
            'success': True,
            'dockey': result.get('dockey'),
            'docno': result.get('docno'),
            'message': result.get('message', 'Draft saved')
        })
    except Exception as e:
        print(f"Error saving draft quotation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_my_draft_quotations')
@api_login_required(unauth_message='Unauthorized')
def api_get_my_draft_quotations():
    """Get saved drafts from SL_QTDRAFT for the current user."""
    try:
        customer_code = get_current_customer_code(resolve_missing=True)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    if not customer_code:
        return jsonify({'success': False, 'error': 'Customer code not found'}), 400

    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute(
            '''
            SELECT DOCKEY, DOCNO, DOCDATE, DESCRIPTION, DOCAMT, VALIDITY, TERMS
            FROM SL_QTDRAFT
            WHERE CODE = ?
            ORDER BY DOCDATE DESC, DOCKEY DESC
            ''',
            (customer_code,)
        )
        rows = cur.fetchall()
        cur.close()
        con.close()
        drafts = []
        for row in rows:
            drafts.append({
                'DOCKEY': int(row[0]) if row[0] is not None else None,
                'DOCNO': row[1],
                'DOCDATE': str(row[2]) if row[2] is not None else None,
                'DESCRIPTION': row[3],
                'DOCAMT': float(row[4]) if row[4] is not None else 0,
                'VALIDITY': str(row[5]) if row[5] is not None else None,
                'CREDITTERM': str(row[6]) if row[6] is not None else 'N/A',
            })
        return jsonify({'success': True, 'data': drafts})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get_draft_quotation_details')
@api_login_required(unauth_message='Unauthorized')
def api_get_draft_quotation_details():
    """Get SL_QTDRAFT header + SL_QTDTLDRAFT line items."""
    dockey = request.args.get('dockey')
    if not dockey:
        return jsonify({'success': False, 'error': 'dockey parameter required'}), 400
    customer_code = session.get('customer_code')
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute(
            'SELECT DOCKEY, DOCNO, DOCDATE, DESCRIPTION, DOCAMT, VALIDITY, TERMS, COMPANYNAME, ADDRESS1, ADDRESS2, PHONE1 FROM SL_QTDRAFT WHERE DOCKEY = ?',
            (int(dockey),)
        )
        hdr = cur.fetchone()
        if not hdr:
            cur.close()
            con.close()
            return jsonify({'success': False, 'error': 'Draft not found'}), 404
        cur.execute(
            'SELECT DTLKEY, SEQ, ITEMCODE, DESCRIPTION, QTY, UNITPRICE, DISC, AMOUNT, UDF_STDPRICE, DELIVERYDATE FROM SL_QTDTLDRAFT WHERE DOCKEY = ? ORDER BY SEQ',
            (int(dockey),)
        )
        item_rows = cur.fetchall()
        cur.close()
        con.close()
        items = []
        for r in item_rows:
            items.append({
                'DTLKEY': r[0], 'SEQ': r[1], 'ITEMCODE': r[2], 'DESCRIPTION': r[3],
                'QTY': float(r[4]) if r[4] is not None else 0,
                'UNITPRICE': float(r[5]) if r[5] is not None else 0,
                'DISC': str(r[6]) if r[6] is not None else '0',
                'AMOUNT': float(r[7]) if r[7] is not None else 0,
                'UDF_STDPRICE': float(r[8]) if r[8] is not None else 0,
                'DELIVERYDATE': str(r[9]) if r[9] is not None else None,
            })
        data = {
            'DOCKEY': int(hdr[0]), 'DOCNO': hdr[1],
            'DOCDATE': str(hdr[2]) if hdr[2] is not None else None,
            'DESCRIPTION': hdr[3],
            'DOCAMT': float(hdr[4]) if hdr[4] is not None else 0,
            'VALIDITY': str(hdr[5]) if hdr[5] is not None else None,
            'TERMS': hdr[6], 'COMPANYNAME': hdr[7],
            'ADDRESS1': hdr[8], 'ADDRESS2': hdr[9], 'PHONE1': hdr[10],
            'items': items
        }
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get_my_quotations')
@api_login_required(unauth_message='Unauthorized')
def api_get_my_quotations():
    """Get quotations for current logged in user by customer code."""
    try:
        customer_code = get_current_customer_code(resolve_missing=True)
    except Exception as e:
        print(f"[Error] Failed to fetch customer_code: {e}")
        return jsonify({'success': False, 'error': 'Failed to retrieve customer information'}), 500

    if not customer_code:
        return jsonify({'success': False, 'error': 'Customer code not found. Please logout and login again.'}), 400

    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute(
            '''
            SELECT TRIM(RF.RDB$FIELD_NAME)
            FROM RDB$RELATION_FIELDS RF
            WHERE RF.RDB$RELATION_NAME = 'SL_QT'
            '''
        )
        sl_qt_cols = {str(r[0]).strip() for r in (cur.fetchall() or []) if r and r[0]}

        fields = [
            'DOCKEY', 'DOCNO', 'DOCDATE', 'DESCRIPTION', 'DOCAMT', 'VALIDITY',
            'STATUS', 'TERMS', 'CANCELLED', 'UPDATECOUNT',
        ]
        if 'UDF_STATUS' in sl_qt_cols:
            fields.append('UDF_STATUS')
        fields.append('COMPANYNAME')

        select_sql = f'''
            SELECT {', '.join('q.' + f for f in fields)}
            FROM SL_QT q
            WHERE q.CODE = ?
            ORDER BY q.DOCDATE DESC, q.DOCKEY DESC
        '''
        cur.execute(select_sql, (customer_code,))
        rows = cur.fetchall()
        cur.close()
        con.close()

        quotations = []
        for row in rows:
            row_map = dict(zip(fields, row))
            # Convert integer status to readable string (0=DRAFT, 1=COMPLETED) when numeric
            raw_st = row_map.get('STATUS')
            if isinstance(raw_st, (int, float)):
                status_str = 'COMPLETED' if int(raw_st) == 1 else 'DRAFT'
            else:
                status_str = str(raw_st).strip() if raw_st is not None else 'DRAFT'

            cancelled_raw = row_map.get('CANCELLED')
            if cancelled_raw is None:
                cancelled_value = None
            elif isinstance(cancelled_raw, bool):
                cancelled_value = cancelled_raw
            elif isinstance(cancelled_raw, (int, float)):
                cancelled_value = int(cancelled_raw) != 0
            else:
                cancelled_value = str(cancelled_raw).strip().lower() in (
                    '1', 'true', 't', 'yes', 'y'
                )
            updatecount_raw = row_map.get('UPDATECOUNT')
            updatecount_value = int(updatecount_raw) if updatecount_raw is not None else None

            udf_status_val = None
            if 'UDF_STATUS' in row_map and row_map.get('UDF_STATUS') is not None:
                udf_status_val = str(row_map.get('UDF_STATUS')).strip()

            rec = {
                'DOCKEY': int(row_map['DOCKEY']) if row_map.get('DOCKEY') is not None else None,
                'DOCNO': row_map.get('DOCNO'),
                'DOCDATE': str(row_map['DOCDATE']) if row_map.get('DOCDATE') is not None else None,
                'DESCRIPTION': row_map.get('DESCRIPTION'),
                'DOCAMT': float(row_map['DOCAMT']) if row_map.get('DOCAMT') is not None else 0,
                'VALIDITY': row_map.get('VALIDITY'),
                'STATUS': status_str,
                'CREDITTERM': str(row_map.get('TERMS')) if row_map.get('TERMS') is not None else 'N/A',
                'CANCELLED': cancelled_value,
                'UPDATECOUNT': updatecount_value,
                'COMPANYNAME': row_map.get('COMPANYNAME') or 'N/A',
            }
            if udf_status_val is not None:
                rec['UDF_STATUS'] = udf_status_val
            quotations.append(rec)

        return jsonify({'success': True, 'data': quotations})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_quotation_details')
@api_login_required(unauth_message='Unauthorized')
def api_get_quotation_details():
    """Get quotation details including line items."""
    dockey = request.args.get('dockey')
    if not dockey:
        return jsonify({'success': False, 'error': 'dockey parameter required'}), 400

    try:
        dockey_int = int(dockey)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid dockey parameter'}), 400

    requested_customer_code = (request.args.get('customer_code') or '').strip()
    session_customer_code = (session.get('customer_code') or '').strip()
    user_type = (session.get('user_type') or '').strip().lower()
    customer_code = requested_customer_code or session_customer_code

    def _safe_float(value, default=0.0):
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(',', '')
        if not text:
            return default
        try:
            return float(text)
        except Exception:
            return default

    try:
        con = None
        cur = None
        try:
            con = get_db_connection()
            cur = con.cursor()

            if not customer_code and user_type == 'admin':
                cur.execute(
                    '''
                    SELECT CODE
                    FROM SL_QT
                    WHERE DOCKEY = ?
                    ''',
                    (dockey_int,)
                )
                admin_row = cur.fetchone()
                if not admin_row or not admin_row[0]:
                    return jsonify({'success': False, 'error': 'Quotation not found'}), 404
                customer_code = str(admin_row[0]).strip()

            if not customer_code:
                return jsonify({'success': False, 'error': 'Customer code not found in session'}), 400

            cur.execute(
                '''
                SELECT TRIM(RF.RDB$FIELD_NAME)
                FROM RDB$RELATION_FIELDS RF
                WHERE RF.RDB$RELATION_NAME = 'SL_QT'
                '''
            )
            sl_qt_cols = {str(r[0]).strip() for r in (cur.fetchall() or []) if r and r[0]}

            header_fields = [
                'DOCKEY', 'DOCNO', 'DOCDATE', 'CODE', 'DESCRIPTION', 'DOCAMT',
                'CURRENCYCODE', 'VALIDITY', 'STATUS', 'TERMS',
                'COMPANYNAME', 'ADDRESS1', 'ADDRESS2', 'ADDRESS3', 'ADDRESS4', 'PHONE1',
            ]
            for opt in ('CANCELLED', 'UPDATECOUNT', 'UDF_STATUS'):
                if opt in sl_qt_cols:
                    header_fields.append(opt)

            cur.execute(
                f'''
                SELECT {', '.join(header_fields)}
                FROM SL_QT
                WHERE DOCKEY = ? AND CODE = ?
                ''',
                (dockey_int, customer_code)
            )
            header = cur.fetchone()

            if not header:
                return jsonify({'success': False, 'error': 'Quotation not found'}), 404

            header_map = dict(zip(header_fields, header))

            cur.execute(
                '''
                SELECT TRIM(RF.RDB$FIELD_NAME)
                FROM RDB$RELATION_FIELDS RF
                WHERE RF.RDB$RELATION_NAME = 'SL_QTDTL'
                '''
            )
            dtl_columns = {str(r[0]).strip() for r in (cur.fetchall() or []) if r and r[0]}

            item_fields = ['DTLKEY', 'DOCKEY', 'SEQ', 'ITEMCODE', 'DESCRIPTION', 'QTY', 'UNITPRICE', 'DISC', 'AMOUNT']
            if 'UDF_STDPRICE' in dtl_columns:
                item_fields.append('UDF_STDPRICE')
            if 'DELIVERYDATE' in dtl_columns:
                item_fields.append('DELIVERYDATE')

            cur.execute(
                f"SELECT {', '.join(item_fields)} FROM SL_QTDTL WHERE DOCKEY = ? ORDER BY SEQ ASC",
                (dockey_int,)
            )
            item_rows = cur.fetchall() or []

            items = []
            for row in item_rows:
                row_map = {item_fields[idx]: row[idx] for idx in range(len(item_fields))}
                items.append({
                    'DTLKEY': int(row_map.get('DTLKEY')) if row_map.get('DTLKEY') is not None else None,
                    'SEQ': int(row_map.get('SEQ')) if row_map.get('SEQ') is not None else 0,
                    'ITEMCODE': row_map.get('ITEMCODE'),
                    'DESCRIPTION': row_map.get('DESCRIPTION'),
                    'QTY': _safe_float(row_map.get('QTY')),
                    'UNITPRICE': _safe_float(row_map.get('UNITPRICE')),
                    'DISC': _safe_float(row_map.get('DISC')),
                    'AMOUNT': _safe_float(row_map.get('AMOUNT')),
                    'UDF_STDPRICE': _safe_float(row_map.get('UDF_STDPRICE')),
                    'DELIVERYDATE': str(row_map.get('DELIVERYDATE')) if row_map.get('DELIVERYDATE') is not None else None,
                })

            raw_st = header_map.get('STATUS')
            if isinstance(raw_st, (int, float)):
                status_display = 'COMPLETED' if int(raw_st) == 1 else 'DRAFT'
            else:
                status_display = str(raw_st).strip() if raw_st is not None else ''

            data = {
                'DOCKEY': int(header_map['DOCKEY']) if header_map.get('DOCKEY') is not None else None,
                'DOCNO': header_map.get('DOCNO'),
                'DOCDATE': str(header_map['DOCDATE']) if header_map.get('DOCDATE') is not None else None,
                'CODE': header_map.get('CODE'),
                'DESCRIPTION': header_map.get('DESCRIPTION'),
                'DOCAMT': _safe_float(header_map.get('DOCAMT')),
                'CURRENCYCODE': header_map.get('CURRENCYCODE'),
                'VALIDITY': str(header_map['VALIDITY']) if header_map.get('VALIDITY') is not None else None,
                'STATUS': status_display,
                'TERMS': header_map.get('TERMS'),
                'CREDITTERM': str(header_map.get('TERMS')) if header_map.get('TERMS') is not None else 'N/A',
                'COMPANYNAME': header_map.get('COMPANYNAME') or 'N/A',
                'ADDRESS1': header_map.get('ADDRESS1') or 'N/A',
                'ADDRESS2': header_map.get('ADDRESS2') or 'N/A',
                'ADDRESS3': header_map.get('ADDRESS3') or '',
                'ADDRESS4': header_map.get('ADDRESS4') or '',
                'PHONE1': header_map.get('PHONE1') or 'N/A',
                'items': items,
            }
            if 'CANCELLED' in header_map:
                cr = header_map.get('CANCELLED')
                if cr is None:
                    data['CANCELLED'] = None
                elif isinstance(cr, bool):
                    data['CANCELLED'] = cr
                elif isinstance(cr, (int, float)):
                    data['CANCELLED'] = int(cr) != 0
                else:
                    data['CANCELLED'] = str(cr).strip().lower() in ('1', 'true', 't', 'yes', 'y')
            if 'UPDATECOUNT' in header_map and header_map.get('UPDATECOUNT') is not None:
                try:
                    data['UPDATECOUNT'] = int(header_map.get('UPDATECOUNT'))
                except (TypeError, ValueError):
                    data['UPDATECOUNT'] = None
            if 'UDF_STATUS' in header_map and header_map.get('UDF_STATUS') is not None:
                data['UDF_STATUS'] = str(header_map.get('UDF_STATUS')).strip()

            return jsonify({'success': True, 'data': data})
        finally:
            if cur:
                cur.close()
            if con:
                con.close()
    except Exception as e:
        import logging
        logging.exception("Error in get_quotation_details")
        return jsonify({
            'success': False,
            'error': str(e),
            'dockey': dockey,
            'customer_code': customer_code,
            'session': dict(session)
        }), 500

@app.route('/api/admin/get_all_quotations')
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_get_all_quotations():
    """Get all quotations for admin view with optional cancelled filter."""
    cancelled = request.args.get('cancelled')

    def _safe_float(value, default=0.0):
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(',', '')
        if not text:
            return default
        try:
            return float(text)
        except Exception:
            return default

    def _to_bool_or_none(value):
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return int(value) != 0
        return str(value).strip().lower() in ('1', 'true', 't', 'yes', 'y')

    try:
        con = None
        cur = None
        try:
            con = get_db_connection()
            cur = con.cursor()
            cur.execute(
                '''
                SELECT DOCKEY, DOCNO, DOCDATE, CODE, DESCRIPTION, DOCAMT,
                       VALIDITY, STATUS, TERMS, CANCELLED, UPDATECOUNT, COMPANYNAME
                FROM SL_QT
                ORDER BY DOCDATE DESC, DOCKEY DESC
                '''
            )
            rows = cur.fetchall() or []
        finally:
            if cur:
                cur.close()
            if con:
                con.close()

        quotations = []
        for row in rows:
            status_int = row[7] if row[7] is not None else 0
            status_str = 'COMPLETED' if status_int == 1 else 'DRAFT'
            cancelled_value = _to_bool_or_none(row[9])
            updatecount_value = int(row[10]) if row[10] is not None else None

            quotations.append({
                'DOCKEY': int(row[0]) if row[0] is not None else None,
                'DOCNO': row[1],
                'DOCDATE': str(row[2]) if row[2] is not None else None,
                'CODE': row[3] or '',
                'DESCRIPTION': row[4],
                'DOCAMT': _safe_float(row[5]),
                'VALIDITY': str(row[6]) if row[6] is not None else None,
                'STATUS': status_str,
                'CREDITTERM': str(row[8]) if row[8] is not None else 'N/A',
                'CANCELLED': cancelled_value,
                'UPDATECOUNT': updatecount_value,
                'COMPANYNAME': row[11] or 'N/A',
            })

        if cancelled is not None:
            cancelled_norm = str(cancelled).strip().lower() in ('1', 'true', 't', 'yes', 'y')
            quotations = [q for q in quotations if q.get('CANCELLED') is cancelled_norm]

        return jsonify({'success': True, 'count': len(quotations), 'data': quotations})
    except Exception as e:
        print(f"[GET ALL QUOTATIONS] DB error: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/get_quotation_detail')
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_get_quotation_detail():
    """Get quotation details including line items (admin only)."""
    dockey = request.args.get('dockey')
    if not dockey:
        return jsonify({'success': False, 'error': 'dockey parameter required'}), 400

    def _safe_float(value, default=0.0):
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(',', '')
        if not text:
            return default
        try:
            return float(text)
        except Exception:
            return default

    try:
        con = None
        cur = None
        try:
            con = get_db_connection()
            cur = con.cursor()

            cur.execute(
                '''
                SELECT DOCKEY, DOCNO, DOCDATE, CODE, DESCRIPTION, DOCAMT,
                       CURRENCYCODE, VALIDITY, STATUS, TERMS,
                       COMPANYNAME, ADDRESS1, ADDRESS2, ADDRESS3, ADDRESS4, PHONE1
                FROM SL_QT
                WHERE DOCKEY = ?
                ''',
                (int(dockey),)
            )
            header = cur.fetchone()

            if not header:
                return jsonify({'success': False, 'error': 'Quotation not found'}), 404

            cur.execute(
                '''
                SELECT TRIM(RF.RDB$FIELD_NAME)
                FROM RDB$RELATION_FIELDS RF
                WHERE RF.RDB$RELATION_NAME = 'SL_QTDTL'
                '''
            )
            dtl_columns = {str(r[0]).strip() for r in (cur.fetchall() or []) if r and r[0]}

            item_fields = ['DTLKEY', 'DOCKEY', 'SEQ', 'ITEMCODE', 'DESCRIPTION', 'QTY', 'UNITPRICE', 'DISC', 'AMOUNT']
            if 'UDF_STDPRICE' in dtl_columns:
                item_fields.append('UDF_STDPRICE')
            if 'DELIVERYDATE' in dtl_columns:
                item_fields.append('DELIVERYDATE')

            cur.execute(
                f"SELECT {', '.join(item_fields)} FROM SL_QTDTL WHERE DOCKEY = ? ORDER BY SEQ ASC",
                (int(dockey),)
            )
            item_rows = cur.fetchall() or []

            items = []
            for row in item_rows:
                row_map = {item_fields[idx]: row[idx] for idx in range(len(item_fields))}
                items.append({
                    'DTLKEY': int(row_map.get('DTLKEY')) if row_map.get('DTLKEY') is not None else None,
                    'SEQ': int(row_map.get('SEQ')) if row_map.get('SEQ') is not None else 0,
                    'ITEMCODE': row_map.get('ITEMCODE'),
                    'DESCRIPTION': row_map.get('DESCRIPTION'),
                    'QTY': _safe_float(row_map.get('QTY')),
                    'UNITPRICE': _safe_float(row_map.get('UNITPRICE')),
                    'DISC': _safe_float(row_map.get('DISC')),
                    'AMOUNT': _safe_float(row_map.get('AMOUNT')),
                    'UDF_STDPRICE': _safe_float(row_map.get('UDF_STDPRICE')),
                    'DELIVERYDATE': str(row_map.get('DELIVERYDATE')) if row_map.get('DELIVERYDATE') is not None else None,
                })

            quotation = {
                'DOCKEY': int(header[0]) if header[0] is not None else None,
                'DOCNO': header[1],
                'DOCDATE': str(header[2]) if header[2] is not None else None,
                'CODE': header[3],
                'DESCRIPTION': header[4],
                'DOCAMT': _safe_float(header[5]),
                'CURRENCYCODE': header[6],
                'VALIDITY': str(header[7]) if header[7] is not None else None,
                'STATUS': str(header[8]) if header[8] is not None else '',
                'TERMS': header[9],
                'CREDITTERM': str(header[9]) if header[9] is not None else 'N/A',
                'COMPANYNAME': header[10] or 'N/A',
                'ADDRESS1': header[11] or 'N/A',
                'ADDRESS2': header[12] or 'N/A',
                'ADDRESS3': header[13] or '',
                'ADDRESS4': header[14] or '',
                'PHONE1': header[15] or 'N/A',
                'items': items,
            }

            return jsonify({'success': True, 'quotation': quotation, 'items': items})
        finally:
            if cur:
                cur.close()
            if con:
                con.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/pricing-priority-rules', methods=['GET'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_get_pricing_priority_rules():
    """Fetch pricing priority rules directly from the local database (admin only)."""
    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute(
            '''
            SELECT PricingPriorityRuleId, RuleCode, RuleName, PriorityNo, IsEnabled
            FROM PricingPriorityRule
            ORDER BY PriorityNo ASC, PricingPriorityRuleId ASC
            '''
        )

        rules = []
        for row in cur.fetchall():
            rules.append({
                'PricingPriorityRuleId': int(row[0]),
                'RuleCode': str(row[1]).strip() if row[1] is not None else '',
                'RuleName': str(row[2]).strip() if row[2] is not None else '',
                'PriorityNo': int(row[3]) if row[3] is not None else 0,
                'IsEnabled': int(row[4]) if row[4] is not None else 0,
            })

        return jsonify({
            'success': True,
            'status': 'success',
            'message': 'Pricing priority rules loaded successfully',
            'data': rules,
        }), 200
    except Exception as e:
        print(f"Error fetching pricing priority rules: {e}")
        return jsonify({'success': False, 'status': 'error', 'error': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


@app.route('/api/admin/pricing-priority-rules/save', methods=['POST'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_save_pricing_priority_rules():
    """Save pricing priority rule ordering and enabled flags to the local database (admin only)."""
    payload = request.get_json() or {}
    rules = payload.get('rules') if isinstance(payload, dict) else payload
    if not isinstance(rules, list) or not rules:
        return jsonify({
            'success': False,
            'status': 'error',
            'error': 'A non-empty rules array is required'
        }), 400

    con = None
    cur = None
    try:
        rule_ids = []
        for rule in rules:
            rule_id = int(rule.get('PricingPriorityRuleId', 0))
            if rule_id <= 0:
                return jsonify({'success': False, 'status': 'error', 'error': 'Each rule must include a valid PricingPriorityRuleId'}), 400
            if rule_id in rule_ids:
                return jsonify({'success': False, 'status': 'error', 'error': 'Duplicate PricingPriorityRuleId found in payload'}), 400
            rule_ids.append(rule_id)

        con = get_db_connection()
        cur = con.cursor()

        placeholders = ','.join(['?'] * len(rule_ids))
        cur.execute(
            f'SELECT COUNT(*) FROM PricingPriorityRule WHERE PricingPriorityRuleId IN ({placeholders})',
            tuple(rule_ids)
        )
        matched_count = int(cur.fetchone()[0])
        if matched_count != len(rule_ids):
            return jsonify({'success': False, 'status': 'error', 'error': 'One or more pricing priority rules do not exist'}), 400

        for index, rule in enumerate(rules, start=1):
            cur.execute(
                '''
                UPDATE PricingPriorityRule
                SET PriorityNo = ?,
                    IsEnabled = ?,
                    EditDate = CURRENT_TIMESTAMP
                WHERE PricingPriorityRuleId = ?
                ''',
                (
                    index,
                    1 if int(rule.get('IsEnabled', 0)) else 0,
                    int(rule['PricingPriorityRuleId'])
                )
            )

        con.commit()
        return jsonify({
            'success': True,
            'status': 'success',
            'message': 'Pricing priority rules saved successfully',
            'savedCount': len(rules)
        }), 200
    except Exception as e:
        if con:
            con.rollback()
        print(f"Error saving pricing priority rules: {e}")
        return jsonify({'success': False, 'status': 'error', 'error': str(e)}), 500
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


@app.route('/api/admin/update_quotation', methods=['POST'])
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_update_quotation():
    """Update quotation (admin only)."""
    data = request.get_json() or {}
    dockey = data.get('dockey')
    
    if not dockey:
        return jsonify({'success': False, 'error': 'Missing dockey'}), 400
    
    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'error': 'At least one item is required'}), 400
    
    # Format data for PHP endpoint (must match updateDraftQuotation.php fields)
    update_data = {
        'dockey': dockey,
        'description': (data.get('description') or 'Quotation').strip(),
        'validUntil': data.get('validUntil'),
        'companyName': data.get('companyName'),
        'address1': data.get('address1'),
        'address2': data.get('address2'),
        'address3': data.get('address3'),
        'address4': data.get('address4'),
        'phone1': data.get('phone1'),
        'items': items,
    }

    try:
        # Use the update draft quotation endpoint
        response = requests.post(
            f"{BASE_API_URL}/php/updateDraftQuotation.php",
            json=update_data,
            timeout=10
        )
        try:
            result = response.json()
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid response from quotation service',
            }), 502
        print(f"[EDIT DEBUG] UpdateDraftQuotation response success: {result.get('success')}")
        
        # If update successful, send email to customer
        if result.get('success'):
            print(f"[EDIT DEBUG] Attempting to send email for DOCKEY {dockey}")
            try:
                # Fetch quotation details
                print(f"[EDIT DEBUG] Fetching quotation details")
                qt_response = requests.get(
                    f"{BASE_API_URL}/php/getQuotationDetails.php",
                    params={'dockey': dockey},
                    timeout=10
                )
                qt_data = qt_response.json()
                print(f"[EDIT DEBUG] Quotation details response success: {qt_data.get('success')}, has data: {bool(qt_data.get('data'))}")
                
                if qt_data.get('success') and qt_data.get('data'):
                    quotation = qt_data['data']
                    customer_email = quotation.get('UDF_EMAIL', '').strip()
                    print(f"[EDIT DEBUG] Customer email: '{customer_email}'")
                    
                    if customer_email:
                        # Send email notification
                        email_data = {
                            'customerEmail': customer_email,
                            'docno': quotation.get('DOCNO', 'N/A'),
                            'dockey': dockey,
                            'totalAmount': quotation.get('DOCAMT', 0),
                            'items': quotation.get('items', []),
                            'companyName': quotation.get('COMPANYNAME', 'Valued Customer')
                        }
                        print(f"[EDIT DEBUG] Sending email to {customer_email}")
                        
                        email_response = requests.post(
                            f"http://localhost:{request.environ.get('SERVER_PORT', '5000')}/api/send_quotation_ready_email",
                            json=email_data,
                            timeout=10
                        )
                        
                        if email_response.json().get('success'):
                            print(f"[EMAIL] Quotation update email sent for DOCKEY {dockey}")
                        else:
                            print(f"[EMAIL WARNING] Failed to send update email for DOCKEY {dockey}")
                    else:
                        print(f"[EMAIL] No customer email found for DOCKEY {dockey}")
            except Exception as email_error:
                # Don't fail the update if email fails
                print(f"[EMAIL ERROR] Failed to send update email: {email_error}")
        
        return jsonify(result)
    except Exception as e:
        print(f"Error updating quotation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _customer_info_has_meaningful_data(info):
    """True if at least one of company / address / phone is non-empty and not a placeholder."""
    if not isinstance(info, dict):
        return False
    company = str(info.get('COMPANYNAME', '')).strip().upper()
    addr1 = str(info.get('ADDRESS1', '')).strip().upper()
    phone1 = str(info.get('PHONE1', '')).strip().upper()
    return any([
        company not in ('', 'N/A'),
        addr1 not in ('', 'N/A'),
        phone1 not in ('', 'N/A'),
    ])


def _fetch_customer_info_from_local_ar(customer_code):
    """
    Load customer profile from local Firebird AR_CUSTOMER + AR_CUSTOMERBRANCH
    (same tables used at sign-in). Used when SQL API is down, misconfigured, or returns no usable fields.
    """
    if not customer_code:
        return None
    code = str(customer_code).strip()
    if not code:
        return None
    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()

        company = ''
        credit = ''
        phone_master = ''
        udf_email = ''
        row = None
        try:
            cur.execute(
                """
                SELECT FIRST 1 COMPANYNAME, CREDITTERM, PHONE1, UDF_EMAIL
                FROM AR_CUSTOMER
                WHERE CODE = ?
                """,
                (code,),
            )
            row = cur.fetchone()
        except Exception:
            try:
                cur.execute(
                    """
                    SELECT FIRST 1 COMPANYNAME, CREDITTERM
                    FROM AR_CUSTOMER
                    WHERE CODE = ?
                    """,
                    (code,),
                )
                row = cur.fetchone()
            except Exception as cust_err:
                print(f"[DEBUG] get_user_info local: AR_CUSTOMER read failed: {cust_err}", flush=True)
                return None
        if row:
            company = str(row[0] or '').strip()
            credit = str(row[1] or '').strip()
            if len(row) > 2 and row[2] is not None:
                phone_master = str(row[2] or '').strip()
            if len(row) > 3 and row[3] is not None:
                udf_email = str(row[3] or '').strip()

        branch_row = None
        try:
            cur.execute(
                """
                SELECT FIRST 1 ADDRESS1, ADDRESS2, ADDRESS3, ADDRESS4, PHONE1, EMAIL
                FROM AR_CUSTOMERBRANCH
                WHERE CODE = ? AND TRIM(BRANCHTYPE) = 'B'
                ORDER BY DTLKEY
                """,
                (code,),
            )
            branch_row = cur.fetchone()
        except Exception as branch_err:
            print(f"[DEBUG] get_user_info local: billing branch query failed ({branch_err}); trying any branch", flush=True)

        if not branch_row:
            cur.execute(
                """
                SELECT FIRST 1 ADDRESS1, ADDRESS2, ADDRESS3, ADDRESS4, PHONE1, EMAIL
                FROM AR_CUSTOMERBRANCH
                WHERE CODE = ?
                ORDER BY DTLKEY
                """,
                (code,),
            )
            branch_row = cur.fetchone()

        a1 = a2 = a3 = a4 = ''
        phone_branch = ''
        branch_email = ''
        if branch_row:
            a1 = str(branch_row[0] or '').strip()
            a2 = str(branch_row[1] or '').strip()
            a3 = str(branch_row[2] or '').strip()
            a4 = str(branch_row[3] or '').strip()
            phone_branch = str(branch_row[4] or '').strip()
            branch_email = str(branch_row[5] or '').strip()

        phone = phone_branch or phone_master
        if not udf_email and branch_email:
            udf_email = branch_email
        if not udf_email:
            udf_email = str(session.get('user_email') or '').strip()

        def nz(val, placeholder='N/A'):
            s = str(val or '').strip()
            return s if s else placeholder

        payload = {
            'CODE': code,
            'COMPANYNAME': nz(company),
            'CREDITTERM': nz(credit),
            'ADDRESS1': nz(a1),
            'ADDRESS2': nz(a2),
            'ADDRESS3': a3,
            'ADDRESS4': a4,
            'PHONE1': nz(phone),
            'UDF_EMAIL': udf_email,
        }
        return payload if _customer_info_has_meaningful_data(payload) else None
    except Exception as exc:
        print(f"[DEBUG] get_user_info: local AR_CUSTOMER lookup failed: {exc}", flush=True)
        return None
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


@app.route('/api/get_user_info')
@api_login_required(unauth_message='Unauthorized')
def api_get_user_info():
    """Return customer info for create-quotation: SQL API when configured, else local Firebird AR_* tables."""
    customer_code = get_current_customer_code(resolve_missing=True)
    if not customer_code:
        if can_access_create_quotation(session) and session.get('user_type') == 'admin':
            em = str(session.get('user_email') or '').strip()
            label = (em.split('@')[0] or 'Staff').replace('.', ' ').title()
            placeholder = {
                'CODE': '',
                'COMPANYNAME': label or 'Internal',
                'CREDITTERM': 'N/A',
                'ADDRESS1': 'N/A',
                'ADDRESS2': 'N/A',
                'ADDRESS3': '',
                'ADDRESS4': '',
                'PHONE1': 'N/A',
                'UDF_EMAIL': em,
            }
            return jsonify({'success': True, 'data': placeholder, 'source': 'internal_staff_placeholder'})
        print("[DEBUG] get_user_info: customer_code not in session", flush=True)
        return jsonify({'success': False, 'error': 'Customer code not found'}), 400

    def _normalize_customer_info(payload):
        if isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, dict):
                payload = first
        if not isinstance(payload, dict):
            return None

        source = payload
        if isinstance(payload.get('data'), dict):
            source = payload.get('data')
        elif isinstance(payload.get('data'), list) and payload.get('data'):
            first = payload.get('data')[0]
            if isinstance(first, dict):
                source = first
        elif isinstance(payload.get('result'), dict):
            source = payload.get('result')
        elif isinstance(payload.get('customer'), dict):
            source = payload.get('customer')

        if not isinstance(source, dict):
            return None

        address_obj = source.get('address') if isinstance(source.get('address'), dict) else None
        first_address = None
        if isinstance(source.get('addresses'), list) and source.get('addresses'):
            candidate = source.get('addresses')[0]
            if isinstance(candidate, dict):
                first_address = candidate

        # SQL API sample uses sdsbranch[] with address/phone/email fields.
        branch_obj = None
        if isinstance(source.get('sdsbranch'), list) and source.get('sdsbranch'):
            billing_branch = next(
                (
                    b for b in source.get('sdsbranch', [])
                    if isinstance(b, dict) and str(b.get('branchtype', '')).strip().upper() == 'B'
                ),
                None,
            )
            if isinstance(billing_branch, dict):
                branch_obj = billing_branch
            else:
                first_branch = source.get('sdsbranch')[0]
                if isinstance(first_branch, dict):
                    branch_obj = first_branch

        def normalize_key(key):
            return ''.join(ch.lower() for ch in str(key) if ch.isalnum())

        def build_normalized_map(obj):
            if not isinstance(obj, dict):
                return {}
            normalized = {}
            for k, v in obj.items():
                normalized[normalize_key(k)] = v
            return normalized

        source_map = build_normalized_map(source)
        address_map = build_normalized_map(address_obj)
        first_address_map = build_normalized_map(first_address)
        branch_map = build_normalized_map(branch_obj)

        def pick_from(obj, obj_map, *keys, default=''):
            if not isinstance(obj, dict):
                return default
            for key in keys:
                value = obj.get(key)
                if value is None:
                    value = obj_map.get(normalize_key(key))
                if value is None:
                    continue
                value_str = str(value).strip()
                if value_str:
                    return value_str
            return default

        def pick(*keys, default=''):
            value = pick_from(source, source_map, *keys, default='')
            if value:
                return value
            value = pick_from(address_obj, address_map, *keys, default='')
            if value:
                return value
            value = pick_from(first_address, first_address_map, *keys, default='')
            if value:
                return value
            return pick_from(branch_obj, branch_map, *keys, default=default)

        return {
            'CODE': pick('CODE', 'code', default=customer_code),
            'COMPANYNAME': pick(
                'COMPANYNAME', 'companyName', 'companyname', 'DESCRIPTION', 'description',
                'CompanyName', 'custname', 'CUSTNAME', default='N/A',
            ),
            'CREDITTERM': pick(
                'CREDITTERM', 'creditTerm', 'creditterm', 'TERMS', 'terms', 'CnTerms', 'CNTERMS',
                default='N/A',
            ),
            'ADDRESS1': pick('ADDRESS1', 'address1', 'addr1', 'line1', 'street1', default='N/A'),
            'ADDRESS2': pick('ADDRESS2', 'address2', 'addr2', 'line2', 'street2', default='N/A'),
            'ADDRESS3': pick('ADDRESS3', 'address3', 'addr3', 'line3', 'city', default=''),
            'ADDRESS4': pick('ADDRESS4', 'address4', 'addr4', 'line4', 'state', 'country', default=''),
            'PHONE1': pick(
                'PHONE1', 'phone', 'phone1', 'tel', 'telephone', 'TEL', 'MOBILE', 'mobile',
                'FAX1', 'fax1', default='N/A',
            ),
            'UDF_EMAIL': pick('UDF_EMAIL', 'udf_email', 'EMAIL', 'email', default=''),
        }

    def _debug_log_user_info_payload(source, payload):
        if not isinstance(payload, dict):
            print(f"[DEBUG] get_user_info: Final payload source={source} is not a dict", flush=True)
            return
        summary = {
            'CODE': payload.get('CODE'),
            'COMPANYNAME': payload.get('COMPANYNAME'),
            'ADDRESS1': payload.get('ADDRESS1'),
            'ADDRESS2': payload.get('ADDRESS2'),
            'ADDRESS3': payload.get('ADDRESS3'),
            'ADDRESS4': payload.get('ADDRESS4'),
            'PHONE1': payload.get('PHONE1'),
            'CREDITTERM': payload.get('CREDITTERM'),
            'UDF_EMAIL': payload.get('UDF_EMAIL'),
        }
        print(f"[DEBUG] get_user_info: Final payload source={source} summary={summary}", flush=True)

    try:
        # 1) Preferred path: SQL API customer details endpoint (example: /customer/*?code=...)
        sql_access_key = (os.getenv('SQL_API_ACCESS_KEY') or '').strip()
        sql_secret_key = (os.getenv('SQL_API_SECRET_KEY') or '').strip()
        sql_host = (os.getenv('SQL_API_HOST') or '').strip()
        sql_region = (os.getenv('SQL_API_REGION') or 'ap-southeast-5').strip()
        sql_service = (os.getenv('SQL_API_SERVICE') or 'sqlaccount').strip()
        sql_detail_path = (os.getenv('SQL_API_CUSTOMER_DETAIL_PATH') or '/customer/*').strip()
        sql_use_tls = (os.getenv('SQL_API_USE_TLS', 'true').strip().lower() in ('1', 'true', 'yes', 'on'))

        if sql_access_key and sql_secret_key and sql_host:
            raw_path = (sql_detail_path or '/customer/*').strip()
            if not raw_path.startswith('/'):
                raw_path = '/' + raw_path
            trimmed_path = raw_path.replace('*', '').rstrip('/') or '/customer'
            code_str = quote(str(customer_code), safe='')
            scheme = 'https' if sql_use_tls else 'http'

            # Try multiple path shapes because some SQL API deployments only return branch
            # fields for wildcard/path-parameter variants.
            candidate_urls = [
                f"{scheme}://{sql_host.rstrip('/')}{quote(trimmed_path, safe='/:?&=%')}?code={code_str}",
                f"{scheme}://{sql_host.rstrip('/')}{quote(raw_path, safe='/:?&=%')}?code={code_str}",
                f"{scheme}://{sql_host.rstrip('/')}{quote(trimmed_path.rstrip('/') + '/' + str(customer_code), safe='/:?&=%')}",
            ]

            # Preserve order but deduplicate identical URLs.
            unique_urls = []
            for url in candidate_urls:
                if url not in unique_urls:
                    unique_urls.append(url)

            sql_headers = {'Accept': 'application/json'}
            best_normalized = None
            best_source = None
            last_sql_status = None
            last_upstream_error_message = None

            for idx, sql_url in enumerate(unique_urls, start=1):
                print(f"[DEBUG] get_user_info: Calling SQL API variant {idx}/{len(unique_urls)} at {sql_url}", flush=True)

                try:
                    # Prefer SigV4 signing if botocore is available in this Flask runtime.
                    from botocore.auth import SigV4Auth
                    from botocore.awsrequest import AWSRequest
                    from botocore.credentials import Credentials

                    creds = Credentials(sql_access_key, sql_secret_key)
                    aws_request = AWSRequest(method='GET', url=sql_url, headers=sql_headers)
                    SigV4Auth(creds, sql_service, sql_region).add_auth(aws_request)
                    prepared = aws_request.prepare()

                    sql_response = requests.get(
                        prepared.url,
                        headers=dict(prepared.headers),
                        timeout=10,
                    )
                except Exception as sigv4_error:
                    # Fallback for environments where upstream accepts key headers.
                    print(f"[DEBUG] get_user_info: SigV4 unavailable/failed ({sigv4_error}); trying header auth", flush=True)
                    sql_response = requests.get(
                        sql_url,
                        headers={
                            **sql_headers,
                            'X-Access-Key': sql_access_key,
                            'X-Secret-Key': sql_secret_key,
                            'X-Region': sql_region,
                            'X-Service': sql_service,
                        },
                        timeout=10,
                    )

                print(f"[DEBUG] get_user_info: SQL API response status {sql_response.status_code}", flush=True)
                if not sql_response.ok:
                    last_sql_status = sql_response.status_code
                    try:
                        err_json = sql_response.json()
                        if isinstance(err_json, dict):
                            err_obj = err_json.get('error')
                            if isinstance(err_obj, dict) and err_obj.get('message'):
                                last_upstream_error_message = str(err_obj.get('message')).strip()
                            elif err_json.get('message'):
                                last_upstream_error_message = str(err_json.get('message')).strip()
                    except Exception:
                        pass
                    print(f"[DEBUG] get_user_info: SQL API response preview: {(sql_response.text or '')[:260]}", flush=True)
                    continue

                try:
                    sql_json = sql_response.json()
                except Exception as parse_err:
                    print(f"[DEBUG] get_user_info: SQL API JSON parse failed: {parse_err}", flush=True)
                    continue

                if isinstance(sql_json, dict):
                    print(f"[DEBUG] get_user_info: SQL JSON top-level keys: {list(sql_json.keys())}", flush=True)
                    sql_data = sql_json.get('data')
                    if isinstance(sql_data, list):
                        print(f"[DEBUG] get_user_info: SQL JSON data list length: {len(sql_data)}", flush=True)
                        if sql_data and isinstance(sql_data[0], dict):
                            print(f"[DEBUG] get_user_info: SQL first data keys: {list(sql_data[0].keys())}", flush=True)
                    elif isinstance(sql_data, dict):
                        print(f"[DEBUG] get_user_info: SQL data keys: {list(sql_data.keys())}", flush=True)
                elif isinstance(sql_json, list):
                    print(f"[DEBUG] get_user_info: SQL JSON list length: {len(sql_json)}", flush=True)

                normalized = _normalize_customer_info(sql_json)
                if not normalized or not _customer_info_has_meaningful_data(normalized):
                    continue

                # Keep first valid result as baseline, but prefer one that has address/phone.
                if best_normalized is None:
                    best_normalized = normalized
                    best_source = f'sql_api_variant_{idx}'

                addr1 = str(normalized.get('ADDRESS1', '')).strip().upper()
                phone1 = str(normalized.get('PHONE1', '')).strip().upper()
                if addr1 not in ('', 'N/A') or phone1 not in ('', 'N/A'):
                    _debug_log_user_info_payload(f'sql_api_variant_{idx}', normalized)
                    return jsonify({'success': True, 'data': normalized, 'source': f'sql_api_variant_{idx}'})

            if best_normalized is not None:
                _debug_log_user_info_payload(best_source or 'sql_api', best_normalized)
                return jsonify({'success': True, 'data': best_normalized, 'source': best_source or 'sql_api'})

            local_payload = _fetch_customer_info_from_local_ar(customer_code)
            if local_payload:
                _debug_log_user_info_payload('local_firebird_ar', local_payload)
                return jsonify({'success': True, 'data': local_payload, 'source': 'local_firebird_ar'})

            # Upstream errors (e.g. 500 "Regenerate views are required") are not "not found"; use 502 for 5xx.
            fail_status = 502 if (last_sql_status and last_sql_status >= 500) else 404
            err_msg = 'No SQL API customer data returned'
            if last_upstream_error_message:
                err_msg = f'SQL API: {last_upstream_error_message}'
            elif last_sql_status:
                err_msg = f'No SQL API customer data returned (upstream HTTP {last_sql_status})'
            fail_body = {'success': False, 'error': err_msg}
            if last_sql_status is not None:
                fail_body['upstream_http_status'] = last_sql_status
            return jsonify(fail_body), fail_status

        local_only = _fetch_customer_info_from_local_ar(customer_code)
        if local_only:
            _debug_log_user_info_payload('local_firebird_ar', local_only)
            return jsonify({'success': True, 'data': local_only, 'source': 'local_firebird_ar'})
        return jsonify({'success': False, 'error': 'No customer data from SQL API or local database'}), 404
    except Exception as e:
        print(f"[DEBUG] get_user_info: Exception occurred: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_company_names')
def api_get_company_names():
    """Get all unique company names from AR_CUSTOMER table."""
    try:
        print("[DEBUG] api_get_company_names: Fetching company names", flush=True)
        php_url = f"{BASE_API_URL}{ENDPOINT_PATHS['getcompanynames']}"
        print(f"[DEBUG] Calling PHP at {php_url}", flush=True)
        response = requests.get(php_url, timeout=10)
        result = response.json()
        print(f"[DEBUG] PHP returned {result.get('count', 0)} companies", flush=True)
        return jsonify(result)
    except Exception as e:
        print(f"[Error] Failed to fetch company names: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == "__main__":
    initialize_database(DB_DSN, DB_USER, DB_PASSWORD)
    pricing_sql_path = os.path.join(os.path.dirname(__file__), 'sql', 'pricing_priority_rule_firebird.sql')
    run_firebird_sql_script(pricing_sql_path, DB_DSN, DB_USER, DB_PASSWORD)

    # Start FastAPI (SQL API) on port 8000 in the background
    import subprocess
    import sys
    api_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    def _pipe_api_output(proc):
        for line in proc.stdout:
            print("[API]", line.decode(errors="replace"), end="", flush=True)
    threading.Thread(target=_pipe_api_output, args=(api_proc,), daemon=True).start()
    print("Starting FastAPI SQL API at http://localhost:8000 ...")

    print("Starting Flask web server at http://localhost:5000 ...")
    try:
        app.run(debug=True, use_reloader=False)
    finally:
        api_proc.terminate()