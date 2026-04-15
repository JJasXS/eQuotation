# DEBUG: Confirm Flask main.py is running
print("[DEBUG] main.py loaded and Flask is starting...", flush=True)
import csv
import json
import os
import math
from functools import wraps
from datetime import datetime, timedelta
import threading
import re
import random
import string
from difflib import SequenceMatcher
import traceback
from urllib.parse import quote

import fdb
import openai
import requests
from flask import Flask, render_template, request, jsonify, session, redirect
from dotenv import load_dotenv
from db_initializer import initialize_database
from api.services.local_customer_sync import LocalCustomerSyncRequest, sync_local_customer_fields

# Import utility modules
from utils import (
    get_db_connection, user_owns_chat, get_chat_history, update_chat_last_message,
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

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# Import local AI models (optional - graceful fallback if not available)
# Note: This import can be slow on first run due to transformers/sklearn/scipy loading
try:
    from ai_models import IntentClassifier
    LOCAL_AI_ENABLED = True
    print("✅ Local AI intent classifier enabled")
except (ImportError, Exception) as e:
    LOCAL_AI_ENABLED = False
    print("⚠️  Local AI not available - using OpenAI only")
    if isinstance(e, ImportError):
        print("   Run: python training/train_intent_model.py to enable local AI")
    else:
        print(f"   Error loading AI models: {type(e).__name__}")
except KeyboardInterrupt:
    LOCAL_AI_ENABLED = False
    print("⚠️  AI model import interrupted - using OpenAI only")
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
FASTAPI_ACCESS_KEY = (os.getenv('API_ACCESS_KEY') or '').strip()
FASTAPI_SECRET_KEY = (os.getenv('API_SECRET_KEY') or '').strip()
GUEST_SIGNIN_ALLOW_LOCAL_FALLBACK = (os.getenv('GUEST_SIGNIN_ALLOW_LOCAL_FALLBACK', 'true').strip().lower() in ('1', 'true', 'yes', 'on'))
DB_PATH = os.getenv('DB_PATH')
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
# In-memory OTP storage: {email: {'otp': code, 'expiry': datetime}}
OTP_STORAGE = {}

# Helper configuration
from config.endpoints_config import ENDPOINT_PATHS
MAX_HISTORY_MESSAGES = 50
CHATBOT_SYSTEM_INSTRUCTIONS = load_chatbot_instructions()

# Helper function for chat messaging
def insert_chat_message(chatid, sender, messagetext):
    return requests.post(
        f"{BASE_API_URL}/php/insertChatMessage.php",
        json={"chatid": chatid, "sender": sender, "messagetext": messagetext}
    )


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


def require_page_access(require_admin=False, block_admin=False, admin_redirect='/admin'):
    """Return redirect response for unauthorized page access, or None if access is allowed."""
    if 'user_email' not in session:
        return redirect('/login')

    user_type = session.get('user_type')
    if require_admin and user_type != 'admin':
        return redirect('/chat')
    if block_admin and user_type == 'admin':
        return redirect(admin_redirect)
    return None


def render_protected_template(template_name, *, require_admin=False, block_admin=False, admin_redirect='/admin', **context):
    """Render a template after applying shared page access checks and default session context."""
    page_error = require_page_access(
        require_admin=require_admin,
        block_admin=block_admin,
        admin_redirect=admin_redirect,
    )
    if page_error:
        return page_error

    template_context = {'user_email': session.get('user_email', '')}
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
        'show me', 'tell me', 'available', 'do you have', 'looking for'
    ]
    if any(phrase in text for phrase in catalog_phrases):
        return True

    return bool(extract_catalog_terms(text)) and len(text.split()) <= 8


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


@app.route('/api/admin/customer_status_summary', methods=['GET'])
@api_admin_required(unauth_message='Not authenticated', forbidden_message='Insufficient permissions')
def customer_status_summary():
    """Return AR_CUSTOMER status distribution for the admin dashboard."""
    status_order = ['A', 'I', 'S', 'P', 'N']
    status_labels = {
        'A': 'Active',
        'I': 'Inactive',
        'S': 'Suspend',
        'P': 'Prospect',
        'N': 'Pending',
    }
    counts = {code: 0 for code in status_order}

    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute('SELECT STATUS, COUNT(*) FROM AR_CUSTOMER GROUP BY STATUS')

        for raw_status, raw_count in cur.fetchall():
            normalized_status = (str(raw_status).strip().upper() if raw_status is not None else '')[:1]
            if normalized_status in counts:
                counts[normalized_status] = int(raw_count or 0)

        items = [
            {
                'code': code,
                'label': status_labels[code],
                'count': counts[code],
            }
            for code in status_order
        ]

        return jsonify({
            'success': True,
            'data': {
                'items': items,
                'total_customers': sum(counts.values()),
            }
        }), 200
    except Exception as exc:
        print(f'Error loading customer status summary: {exc}')
        return jsonify({'success': False, 'error': 'Failed to load customer status summary'}), 500
    finally:
        if cur:
            cur.close()
        if con:
            con.close()

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

@app.route('/api/send_otp', methods=['POST'])
def api_send_otp():
    """Send OTP to email"""
    data = request.get_json()
    email = data.get('email', '').strip()
    print(f"[DEBUG OTP] send_otp requested for: {email}", flush=True)
    
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
                params={"email": email},
                timeout=5,
            )
            identity_resp.raise_for_status()
            identity = identity_resp.json()
            is_admin = bool(identity.get('is_admin'))
            is_user = bool(identity.get('is_user'))
            is_customer = bool(identity.get('is_customer'))
        except Exception as e:
            print(f"[AUTH] FastAPI email lookup during send_otp failed: {e}")
            return jsonify({'success': False, 'error': 'Authentication lookup service unavailable'}), 500

        if not (is_admin or is_user or is_customer):
            print(f"[DEBUG OTP] rejected (email not found): {email}", flush=True)
            return jsonify({
                'success': False,
                'error': 'Email not found, please contact administrator'
            }), 401

        # Generate OTP
        otp = generate_otp(OTP_LENGTH)
        print(f"[DEBUG OTP] {email} -> {otp}", flush=True)
        expiry = datetime.now() + timedelta(seconds=OTP_EXPIRY_SECONDS)
        
        # Store OTP temporarily
        OTP_STORAGE[email] = {
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
    data = request.get_json()
    email = data.get('email', '').strip()
    otp = data.get('otp', '').strip()
    
    if not email or not otp:
        return jsonify({'success': False, 'error': 'Email and OTP are required'}), 400
    
    try:
        # OTP validation (1-minute expiry + one-time use)
        if email not in OTP_STORAGE:
            return jsonify({'success': False, 'error': 'OTP not found. Request a new one.'}), 400

        stored_data = OTP_STORAGE[email]

        if datetime.now() > stored_data['expiry']:
            del OTP_STORAGE[email]
            return jsonify({'success': False, 'error': 'OTP has expired. Request a new one.'}), 400

        if otp != stored_data['otp']:
            return jsonify({'success': False, 'error': 'Invalid OTP. Please try again.'}), 400

        # One-time use: consume OTP immediately after successful verification
        del OTP_STORAGE[email]

        # Check identity via FastAPI so login checks stay on port 8000.
        try:
            identity_response = requests.get(
                f"{FASTAPI_BASE_URL}/auth/email-lookup",
                params={"email": email},
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

        if identity.get('is_admin'):
            user_type = 'admin'
            redirect_url = '/admin'
            customer_code = None
            print(f"[AUTH] Admin user detected: {email}")
        elif identity.get('is_user') or identity.get('is_customer'):
            user_type = 'user'
            redirect_url = '/create-quotation'
            customer_code = identity.get('customer_code')
            print(f"[AUTH] Regular user detected: {email} -> Customer: {customer_code}")
        else:
            return jsonify({
                'success': False,
                'error': 'Email not found in customer records, please contact administrator'
            }), 401
        
        # OTP is valid - create session
        session['user_email'] = email
        session['user_type'] = user_type
        session['customer_code'] = customer_code  # Store customer code in session
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
    """Display admin dashboard (requires authentication and admin role)"""
    return render_protected_template('admin.html', require_admin=True)


@app.route('/admin/pending-approvals')
def admin_pending_approvals():
    """Display pending approvals page (admin only)."""
    return render_protected_template('adminApproval.html', require_admin=True, user_type='admin')




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
    """Display create quotation page (regular users)."""
    dockey = request.args.get('dockey', '')
    draft_dockey = request.args.get('draftDockey', '')
    return render_protected_template(
        'createQuotation.html',
        block_admin=True,
        admin_redirect='/admin',
        dockey=dockey,
        draft_dockey=draft_dockey,
        php_base_url=BASE_API_URL,
    )


@app.route('/view-quotation')
def view_quotation_page():
    """Display quotation listing page (regular users)."""
    return render_protected_template(
        'viewQuotation.html',
        block_admin=True,
        admin_redirect='/admin/view-quotations',
        user_type=session.get('user_type', ''),
    )

@app.route('/admin/view-quotations')
def admin_view_quotations():
    """Display all quotations page (admin only)."""
    return render_protected_template(
        'adminViewQuotations.html',
        require_admin=True,
        user_type=session.get('user_type', ''),
    )


@app.route('/admin/delete-quotations')
def admin_delete_quotations():
    """Display delete quotations page (admin only)."""
    return render_protected_template(
        'deleteQuotations.html',
        require_admin=True,
        user_type=session.get('user_type', ''),
    )


@app.route('/admin/pricing-priority-rules')
def admin_pricing_priority_rules():
    """Display pricing priority rule settings page (admin only)."""
    return render_protected_template(
        'pricingPriorityRules.html',
        require_admin=True,
        user_type=session.get('user_type', 'admin')
    )


@app.route('/admin/update-quotation')
def admin_update_quotation():
    """Display update quotation page (admin only)."""
    page_error = require_page_access(require_admin=True)
    if page_error:
        return page_error
    dockey = request.args.get('dockey', '')
    if not dockey:
        return "Missing dockey parameter", 400
    return render_template('updateQuotation.html',
                         user_email=session.get('user_email', ''),
                         dockey=dockey)


@app.route('/admin/pending-approvals/edit/<int:orderid>')
def admin_edit_approval(orderid):
    """Display admin edit approval page."""
    return render_protected_template('admin_edit_approval.html', require_admin=True, orderid=orderid)


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
        # Check user type and redirect accordingly
        user_type = session.get('user_type', 'user')
        if user_type == 'admin':
            return redirect('/admin')
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
    user_email = session.get('user_email')
    user_input = request.json.get('message')
    chatid = request.json.get('chatid')

    if not chatid:
        return jsonify({'success': False, 'error': 'chatid required'}), 400

    if not user_owns_chat(chatid, user_email):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    
    # Fetch chat history if chatid provided
    chat_history = []
    if chatid:
        chat_history = get_chat_history(chatid, user_email)
    
    # Always include PHP endpoint data in the prompt
    stockitems = fetch_data_from_api("stockitem")
    stockitemprices = fetch_data_from_api("stockitemprice")
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
        response = chat_with_gpt(messages)
        # Apply formatting to ensure proper line breaks in lists
        formatted_reply = format_chatbot_response(response.strip())
        print(f"[DEBUG] Original response length: {len(response)}, Formatted length: {len(formatted_reply)}", flush=True)
    
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
        user_email = session.get('user_email')
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
        cur.execute('SELECT ORDERID FROM ORDER_TPL WHERE CHATID = ? AND STATUS = ?', (chatid, 'DRAFT'))
        result = cur.fetchone()
        cur.close()
        con.close()
        
        if result:
            return jsonify({'success': True, 'hasDraft': True, 'orderid': result[0]})
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
        # Check if user has any draft orders
        cur.execute('''
            SELECT COUNT(*) FROM ORDER_TPL o
            INNER JOIN CHAT_TPL c ON o.CHATID = c.CHATID
            WHERE c.USEREMAIL = ? AND o.STATUS = ? AND o.CUSTOMERCODE = ?
        ''', (user_email, 'DRAFT', customer_code))
        count = cur.fetchone()[0]
        cur.close()
        con.close()
        
        return jsonify({'success': True, 'hasDraft': count > 0})
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

        wanted_columns = [
            'CODE',
            'DESCRIPTION',
            'STOCKGROUP',
            'REMARK1',
            'REMARK2',
            'UDF_STDPRICE',
            'UDF_MOQ',
            'UDF_DLEADTIME',
            'UDF_BUNDLE',
        ]

        cur.execute(
            """
            SELECT TRIM(RF.RDB$FIELD_NAME)
            FROM RDB$RELATION_FIELDS RF
            WHERE RF.RDB$RELATION_NAME = 'ST_ITEM'
            """
        )
        existing_columns = {str(row[0]).strip() for row in cur.fetchall() if row and row[0]}
        selected_columns = [col for col in wanted_columns if col in existing_columns]

        if not selected_columns:
            return jsonify({'success': False, 'error': 'No expected columns found in ST_ITEM', 'items': []}), 500

        sql = f"SELECT {', '.join(selected_columns)} FROM ST_ITEM"
        cur.execute(sql)
        rows = cur.fetchall() or []

        items = []
        for row in rows:
            item = {}
            for idx, col in enumerate(selected_columns):
                val = row[idx]
                item[col] = str(val).strip() if isinstance(val, str) else val
            items.append(item)

        return jsonify({'success': True, 'items': items})
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
                cur.execute('SELECT FIRST 1 CODE FROM AR_CUSTOMERBRANCH WHERE EMAIL = ?', (user_email,))
                row = cur.fetchone()
                if row and row[0]:
                    customer_code = str(row[0]).strip()
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

        # Fetch ST_ITEM.UDF_STDPRICE for Suggested Price field when not provided.
        st_item_udf_stdprice = None
        if local_st_item_price is not None:
            try:
                st_item_udf_stdprice = float(local_st_item_price)
            except Exception:
                st_item_udf_stdprice = None
        elif item_code:
            con = None
            cur = None
            try:
                con = get_db_connection()
                cur = con.cursor()
                cur.execute('SELECT UDF_STDPRICE FROM ST_ITEM WHERE CODE = ?', (item_code,))
                row = cur.fetchone()
                if row and row[0] is not None:
                    st_item_udf_stdprice = float(row[0])
            except Exception as st_item_error:
                print(f"[PRICING WARNING] Failed to fetch ST_ITEM.UDF_STDPRICE for {item_code}: {st_item_error}", flush=True)
            finally:
                if cur:
                    cur.close()
                if con:
                    con.close()

        if customer_code and item_code:
            try:
                pricing_result = get_selling_price(customer_code, item_code)
                selected_price = float(pricing_result.get('SelectedPrice') or 0)
                if selected_price > 0:
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
                    })
                no_match_message = pricing_result.get('Message')
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
        })

    try:
        # First preference: resolve directly from ST_ITEM (dropdown source) and use UDF_STDPRICE.
        con = None
        cur = None
        try:
            con = get_db_connection()
            cur = con.cursor()

            cur.execute(
                '''
                SELECT FIRST 1 CODE, DESCRIPTION, UDF_STDPRICE
                FROM ST_ITEM
                WHERE UPPER(TRIM(DESCRIPTION)) = UPPER(?)
                ''',
                (description,)
            )
            row = cur.fetchone()

            if not row and len(description) <= 30:
                cur.execute(
                    '''
                    SELECT FIRST 1 CODE, DESCRIPTION, UDF_STDPRICE
                    FROM ST_ITEM
                    WHERE UPPER(TRIM(CODE)) = UPPER(?)
                    ''',
                    (description,)
                )
                row = cur.fetchone()

            if row:
                local_item = {
                    'CODE': (row[0] or '').strip() if row[0] else '',
                    'DESCRIPTION': (row[1] or '').strip() if row[1] else '',
                    'UDF_STDPRICE': row[2],
                    'STOCKVALUE': row[2] if row[2] is not None else 0,
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

@app.route('/api/create_quotation', methods=['POST'])
@api_login_required(unauth_message='Session expired. Please log in again.')
def api_create_quotation():
    """Create or update a quotation in the accounting system (SL_QT)"""
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
    customer_code = get_current_customer_code(resolve_missing=True)
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
            SELECT q.DOCKEY, q.DOCNO, q.DOCDATE, q.DESCRIPTION, q.DOCAMT, q.VALIDITY, q.STATUS, q.TERMS, q.CANCELLED, q.UPDATECOUNT, q.COMPANYNAME
            FROM SL_QT q
            WHERE q.CODE = ?
            ORDER BY q.DOCDATE DESC, q.DOCKEY DESC
            ''',
            (customer_code,)
        )
        rows = cur.fetchall()
        cur.close()
        con.close()

        quotations = []
        for row in rows:
            # Convert integer status to readable string (0=DRAFT, 1=COMPLETED)
            status_int = row[6] if row[6] is not None else 0
            status_str = 'COMPLETED' if status_int == 1 else 'DRAFT'
            cancelled_raw = row[8]
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
            updatecount_raw = row[9]
            updatecount_value = int(updatecount_raw) if updatecount_raw is not None else None
            
            quotations.append({
                'DOCKEY': int(row[0]) if row[0] is not None else None,
                'DOCNO': row[1],
                'DOCDATE': str(row[2]) if row[2] is not None else None,
                'DESCRIPTION': row[3],
                'DOCAMT': float(row[4]) if row[4] is not None else 0,
                'VALIDITY': row[5],
                'STATUS': status_str,
                'CREDITTERM': str(row[7]) if row[7] is not None else 'N/A',
                'CANCELLED': cancelled_value,
                'UPDATECOUNT': updatecount_value,
                'COMPANYNAME': row[10] or 'N/A'
            })

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
                SELECT DOCKEY, DOCNO, DOCDATE, CODE, DESCRIPTION, DOCAMT,
                       CURRENCYCODE, VALIDITY, STATUS, TERMS,
                       COMPANYNAME, ADDRESS1, ADDRESS2, ADDRESS3, ADDRESS4, PHONE1
                FROM SL_QT
                WHERE DOCKEY = ? AND CODE = ?
                ''',
                (dockey_int, customer_code)
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

            data = {
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


@app.route('/api/get_user_info')
@api_login_required(unauth_message='Unauthorized')
def api_get_user_info():
    """Proxy to PHP getUserInfo.php for customer info."""
    customer_code = get_current_customer_code(resolve_missing=True)
    if not customer_code:
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
            return pick_from(first_address, first_address_map, *keys, default=default)

        return {
            'CODE': pick('CODE', 'code', default=customer_code),
            'COMPANYNAME': pick('COMPANYNAME', 'companyName', 'companyname', default='N/A'),
            'CREDITTERM': pick('CREDITTERM', 'creditTerm', 'creditterm', default='N/A'),
            'ADDRESS1': pick('ADDRESS1', 'address1', 'addr1', 'line1', 'street1', default='N/A'),
            'ADDRESS2': pick('ADDRESS2', 'address2', 'addr2', 'line2', 'street2', default='N/A'),
            'ADDRESS3': pick('ADDRESS3', 'address3', 'addr3', 'line3', 'city', default=''),
            'ADDRESS4': pick('ADDRESS4', 'address4', 'addr4', 'line4', 'state', 'country', default=''),
            'PHONE1': pick('PHONE1', 'phone', 'phone1', 'tel', 'telephone', default='N/A'),
        }

    def _has_meaningful_customer_data(info):
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

    def _has_meaningful_address_or_phone(info):
        if not isinstance(info, dict):
            return False
        addr1 = str(info.get('ADDRESS1', '')).strip().upper()
        addr2 = str(info.get('ADDRESS2', '')).strip().upper()
        addr3 = str(info.get('ADDRESS3', '')).strip().upper()
        addr4 = str(info.get('ADDRESS4', '')).strip().upper()
        phone1 = str(info.get('PHONE1', '')).strip().upper()
        return any([
            addr1 not in ('', 'N/A'),
            addr2 not in ('', 'N/A'),
            addr3 not in ('', 'N/A'),
            addr4 not in ('', 'N/A'),
            phone1 not in ('', 'N/A'),
        ])

    def _merge_missing_customer_fields(primary, fallback):
        if not isinstance(primary, dict):
            return fallback if isinstance(fallback, dict) else primary
        if not isinstance(fallback, dict):
            return primary

        merged = dict(primary)
        for key in ('ADDRESS1', 'ADDRESS2', 'ADDRESS3', 'ADDRESS4', 'PHONE1', 'CREDITTERM', 'COMPANYNAME'):
            current = str(merged.get(key, '')).strip()
            fallback_value = str(fallback.get(key, '')).strip()
            if (not current or current.upper() == 'N/A') and fallback_value:
                merged[key] = fallback_value
        return merged

    def _load_customer_from_local_db():
        con = None
        cur = None
        try:
            con = get_db_connection()
            cur = con.cursor()
            cur.execute(
                '''
                SELECT
                    c.CODE,
                    c.COMPANYNAME,
                    c.CREDITTERM,
                    cb.ADDRESS1,
                    cb.ADDRESS2,
                    cb.ADDRESS3,
                    cb.ADDRESS4,
                    cb.PHONE1
                FROM AR_CUSTOMER c
                LEFT JOIN AR_CUSTOMERBRANCH cb
                  ON cb.CODE = c.CODE
                 AND cb.DTLKEY = (
                     SELECT MIN(b.DTLKEY)
                     FROM AR_CUSTOMERBRANCH b
                     WHERE b.CODE = c.CODE
                 )
                WHERE c.CODE = ?
                ''',
                (customer_code,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return {
                'CODE': (str(row[0]).strip() if row[0] is not None else customer_code),
                'COMPANYNAME': (str(row[1]).strip() if row[1] else 'N/A'),
                'CREDITTERM': (str(row[2]).strip() if row[2] else 'N/A'),
                'ADDRESS1': (str(row[3]).strip() if row[3] else 'N/A'),
                'ADDRESS2': (str(row[4]).strip() if row[4] else 'N/A'),
                'ADDRESS3': (str(row[5]).strip() if row[5] else ''),
                'ADDRESS4': (str(row[6]).strip() if row[6] else ''),
                'PHONE1': (str(row[7]).strip() if row[7] else 'N/A'),
            }
        except Exception as db_err:
            print(f"[DEBUG] get_user_info: Local DB fallback failed: {db_err}", flush=True)
            return None
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
            # '/customer/*' in docs is a route template; call concrete path without literal '*'.
            sql_detail_path = sql_detail_path.replace('*', '').strip()
            if not sql_detail_path:
                sql_detail_path = '/customer'
            if not sql_detail_path.startswith('/'):
                sql_detail_path = '/' + sql_detail_path
            sql_detail_path = sql_detail_path.rstrip('/') or '/customer'

            scheme = 'https' if sql_use_tls else 'http'
            sql_url = f"{scheme}://{sql_host.rstrip('/')}{quote(sql_detail_path, safe='/:?&=%')}?code={quote(str(customer_code), safe='')}"
            print(f"[DEBUG] get_user_info: Calling SQL API at {sql_url}", flush=True)

            sql_headers = {'Accept': 'application/json'}
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
                print(f"[DEBUG] get_user_info: SQL API response preview: {(sql_response.text or '')[:260]}", flush=True)

            if sql_response.ok:
                try:
                    sql_json = sql_response.json()
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
                    if normalized and _has_meaningful_customer_data(normalized):
                        if _has_meaningful_address_or_phone(normalized):
                            _debug_log_user_info_payload('sql_api', normalized)
                            return jsonify({'success': True, 'data': normalized, 'source': 'sql_api'})

                        print('[DEBUG] get_user_info: SQL response missing address/phone, enriching from local DB', flush=True)
                        local_data = _load_customer_from_local_db()
                        if local_data:
                            merged = _merge_missing_customer_fields(normalized, local_data)
                            _debug_log_user_info_payload('sql_api+local_db', merged)
                            return jsonify({'success': True, 'data': merged, 'source': 'sql_api+local_db'})

                        _debug_log_user_info_payload('sql_api', normalized)
                        return jsonify({'success': True, 'data': normalized, 'source': 'sql_api'})

                    print('[DEBUG] get_user_info: SQL response had no meaningful customer data, trying local DB fallback', flush=True)
                except Exception as parse_err:
                    print(f"[DEBUG] get_user_info: SQL API JSON parse failed: {parse_err}", flush=True)

        # 2) Local DB fallback by customer code
        local_data = _load_customer_from_local_db()
        if local_data and _has_meaningful_customer_data(local_data):
            _debug_log_user_info_payload('local_db', local_data)
            return jsonify({'success': True, 'data': local_data, 'source': 'local_db'})

        # 3) Final fallback path: PHP endpoint using BASE_API_URL and ENDPOINT_PATHS
        php_url = f"{BASE_API_URL}{ENDPOINT_PATHS['getuserinfo']}"
        print(f"[DEBUG] get_user_info: Falling back to PHP {php_url}?customerCode={customer_code}", flush=True)
        response = requests.get(php_url, params={'customerCode': customer_code}, timeout=10)
        print(f"[DEBUG] get_user_info: PHP response status {response.status_code}", flush=True)
        if not response.ok:
            return jsonify({
                'success': False,
                'error': f'PHP fallback returned HTTP {response.status_code}',
                'preview': (response.text or '')[:260],
            }), 502
        try:
            return jsonify(response.json())
        except Exception as json_err:
            return jsonify({
                'success': False,
                'error': f'PHP fallback returned non-JSON response: {json_err}',
                'preview': (response.text or '')[:260],
            }), 502
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
    print("Starting Flask web server at http://localhost:5000 ...")
    app.run(debug=True, use_reloader=False)