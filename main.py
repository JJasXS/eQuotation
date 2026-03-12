# DEBUG: Confirm Flask main.py is running
print("[DEBUG] main.py loaded and Flask is starting...", flush=True)
import os
from functools import wraps
from datetime import datetime, timedelta
import threading
import re
import random
import string
from difflib import SequenceMatcher
import traceback

import fdb
import openai
import requests
from flask import Flask, render_template, request, jsonify, session, redirect
from dotenv import load_dotenv
from db_initializer import initialize_database

# Import utility modules
from utils import (
    get_db_connection, user_owns_chat, get_chat_history, update_chat_last_message,
    get_active_order, test_firebird_connection, set_db_config,
    fetch_data_from_api, format_rm, set_api_config,
    load_typo_corrections, normalize_intent_text, contains_intent_phrase,
    parse_order_intent, set_text_config,
    send_email, set_email_config,
    chat_with_gpt, detect_intent_hybrid, load_chatbot_instructions,
    set_ai_config, init_local_classifier,
    extract_product_and_quantity, get_product_price, set_order_config,
    resolve_numbered_reference, get_selling_price
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

# Import order management configuration
from config.order_config import (
    CREATE_ORDER_KEYWORDS,
    COMPLETE_ORDER_KEYWORDS,
    REMOVE_ORDER_KEYWORDS,
    ADD_ORDER_KEYWORDS,
    PRODUCT_EXTRACTION_KEYWORDS,
    MIN_PRODUCT_NAME_LENGTH,
    MIN_PRODUCT_CODE_LENGTH,
    QUANTITY_FILLER_WORDS,
    QUANTITY_FILLER_PATTERN,
    WELCOME_MESSAGE,
    SHOW_WELCOME_MESSAGE,
    HELP_MESSAGE,
    NUMBERED_REFERENCE_PATTERNS,
    ORDINAL_WORD_MAP,
    PRODUCT_PREFIX_PATTERN,
    FUZZY_MATCH_THRESHOLD,
    SUBSTRING_MATCH_BONUS,
    PRICE_MATCH_THRESHOLD,
    PRODUCT_EXTRACTION_VERBS
)

# Import OTP configuration
from config.otp_config import generate_otp, OTP_LENGTH, OTP_EXPIRY_SECONDS

# ============================================
# CONFIGURATION - Load from environment variables
# ============================================
BASE_API_URL = os.getenv('BASE_API_URL', 'http://localhost')
DB_PATH = os.getenv('DB_PATH')
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
set_db_config(DB_PATH, DB_USER, DB_PASSWORD)


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


def is_catalog_query(user_input):
    text = (user_input or '').lower().strip()
    if not text:
        return False

    catalog_phrases = [
        'what do you sell', 'what do u sell', 'what type', 'what types',
        'what category', 'what categories', 'what group', 'what groups',
        'show me', 'tell me', 'available', 'do you have', 'looking for'
    ]
    if any(phrase in text for phrase in catalog_phrases):
        return True

    return bool(extract_catalog_terms(text)) and len(text.split()) <= 8


def match_catalog_items(user_input, stockitems, price_lookup=None, limit=8):
    query = (user_input or '').lower().strip()
    terms = extract_catalog_terms(query)
    matches = []

    for item in stockitems:
        description = (item.get('DESCRIPTION') or '').strip()
        stock_group = (item.get('STOCKGROUP') or '').strip()
        if not description:
            continue

        description_lower = description.lower()
        stock_group_lower = stock_group.lower()
        normalized_desc_tokens = {normalize_catalog_token(token) for token in re.findall(r'[a-z0-9]+', description_lower)}
        normalized_group_tokens = {normalize_catalog_token(token) for token in re.findall(r'[a-z0-9]+', stock_group_lower)}

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

        if score <= 0:
            continue

        price = None
        if price_lookup:
            price = price_lookup.get(description_lower)

        matches.append((description, stock_group, score, price))

    matches.sort(key=lambda item: (-item[2], item[0]))

    seen = set()
    results = []
    for description, stock_group, _, price in matches:
        if description.lower() in seen:
            continue
        seen.add(description.lower())
        results.append((description, stock_group, price))
        if len(results) >= limit:
            break

    return results


def build_catalog_response(user_input, stockitems, stock_groups, price_lookup):
    if not is_catalog_query(user_input):
        return None

    text = (user_input or '').lower().strip()
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

    matches = match_catalog_items(user_input, stockitems, price_lookup=price_lookup, limit=8)
    priced_matches = [item for item in matches if item[2] is not None]
    display_matches = priced_matches or matches

    if display_matches:
        lines = ['Here are the matching items I found in our catalog:', '']
        for index, (description, _stock_group, price) in enumerate(display_matches, start=1):
            if price is not None:
                lines.append(f'{index}. {description} [PRODUCT: {description} | qty: 1]')
            else:
                lines.append(f'{index}. {description}')
        lines.extend(['', 'Let me know which item you want, or ask for a different keyword.'])
        return '\n'.join(lines)

    suggestions = build_product_suggestions(
        user_input,
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

# ============================================
# ROUTE: Delete Order Detail
# ============================================
@app.route('/php/deleteOrderDetail.php', methods=['POST'])
def proxy_delete_order_detail():
    """Proxy endpoint to delete order detail via XAMPP PHP."""
    auth_error = require_api_auth()
    if auth_error:
        return auth_error

    payload = request.get_json() or {}

    try:
        return proxy_json_request('POST', '/php/deleteOrderDetail.php', payload=payload)
    except Exception as e:
        print(f"Error proxying deleteOrderDetail to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to delete order detail'}), 500

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


@app.route('/api/create_signin_user', methods=['POST'])
def create_signin_user():
    """Forward guest sign-in payload to PHP endpoint for AR_CUSTOMER inserts."""
    data = request.get_json() or {}

    try:
        php_url = f"{BASE_API_URL}/php/createSignInUser.php"
        response = requests.post(php_url, json=data, timeout=10)
        response.raise_for_status()
        result = response.json()

        # After guest registration, send user to login page.
        if result.get('success'):
            result['redirect'] = '/login'

        return jsonify(result), response.status_code
    except requests.exceptions.HTTPError:
        try:
            return jsonify(response.json()), response.status_code
        except Exception:
            return jsonify({'success': False, 'error': 'PHP endpoint returned an invalid response'}), response.status_code
    except Exception as e:
        print(f"Error calling createSignInUser.php: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get_currency_symbols', methods=['GET'])
def get_currency_symbols():
    """Fetch currency symbols for guest sign-in dropdown."""
    try:
        php_url = f"{BASE_API_URL}/php/getCurrencySymbols.php"
        response = requests.get(php_url, timeout=10)
        response.raise_for_status()
        result = response.json()
        return jsonify(result), response.status_code
    except requests.exceptions.HTTPError:
        try:
            return jsonify(response.json()), response.status_code
        except Exception:
            return jsonify({'success': False, 'error': 'PHP endpoint returned an invalid response'}), response.status_code
    except Exception as e:
        print(f"Error calling getCurrencySymbols.php: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get_area_codes', methods=['GET'])
def get_area_codes():
    """Fetch AREA.CODE values for guest sign-in dropdown."""
    try:
        php_url = f"{BASE_API_URL}/php/getAreaCodes.php"
        response = requests.get(php_url, timeout=10)
        response.raise_for_status()
        result = response.json()
        return jsonify(result), response.status_code
    except requests.exceptions.HTTPError:
        try:
            return jsonify(response.json()), response.status_code
        except Exception:
            return jsonify({'success': False, 'error': 'PHP endpoint returned an invalid response'}), response.status_code
    except Exception as e:
        print(f"Error calling getAreaCodes.php: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
    """Show guest sign-in page (front-end only for now)."""
    return render_template('signInGuest.html')

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
        # Allow login only if email exists in admin or user master tables
        is_admin = False
        is_user = False

        try:
            admin_check = requests.get(
                f"{BASE_API_URL}{ENDPOINT_PATHS['getadminbyemail']}?email={email}",
                timeout=5
            )
            admin_data = admin_check.json()
            is_admin = bool(admin_data.get('success') and admin_data.get('data'))
        except Exception as e:
            print(f"[AUTH] Admin lookup during send_otp failed: {e}")

        try:
            user_check = requests.get(
                f"{BASE_API_URL}{ENDPOINT_PATHS['getuserbyemail']}?email={email}",
                timeout=5
            )
            user_data = user_check.json()
            is_user = bool(user_data.get('success') and user_data.get('data'))
        except Exception as e:
            print(f"[AUTH] User lookup during send_otp failed: {e}")

        # Check AR_CUSTOMER.EMAIL as additional fallback
        is_customer = False
        try:
            customer_check = requests.get(
                f"{BASE_API_URL}{ENDPOINT_PATHS['getcustomerbyemailfromcustomer']}?email={email}",
                timeout=5
            )
            customer_check.raise_for_status()
            customer_data = customer_check.json()
            is_customer = bool(customer_data.get('success') and customer_data.get('customerCode'))
        except Exception as e:
            print(f"[AUTH] AR_CUSTOMER lookup during send_otp failed: {e}")

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

        # Check if email is admin or regular user
        user_type = 'user'  # default
        redirect_url = '/create-quotation'
        
        # Check if email exists in SY_USER (Admin)
        try:
            admin_response = requests.get(
                f"{BASE_API_URL}{ENDPOINT_PATHS['getadminbyemail']}?email={email}",
                timeout=5
            )
            admin_data = admin_response.json()
            if admin_data.get('success') and admin_data.get('data'):
                user_type = 'admin'
                redirect_url = '/admin'
                print(f"[AUTH] Admin user detected: {email}")
        except Exception as e:
            print(f"[AUTH] Admin lookup failed (non-critical): {e}")
        
        # If not admin, check regular user via unified endpoint
        # (AR_CUSTOMERBRANCH.EMAIL first, fallback AR_CUSTOMER.UDF_EMAIL)
        if user_type == 'user':
            try:
                user_response = requests.get(
                    f"{BASE_API_URL}{ENDPOINT_PATHS['getuserbyemail']}?email={email}",
                    timeout=5
                )
                user_data = user_response.json()

                if user_data.get('success') and user_data.get('data'):
                    customer_code = user_data['data'].get('CODE')
                    user_type = 'user'
                    redirect_url = '/create-quotation'
                    print(f"[AUTH] Regular user detected: {email} → Customer: {customer_code}")
                else:
                    # Email not found in either branch EMAIL or customer UDF_EMAIL
                    return jsonify({
                        'success': False, 
                        'error': 'Email not found in customer records, please contact administrator'
                    }), 401
            except Exception as e:
                print(f"[AUTH] Customer lookup failed: {e}")
                return jsonify({
                    'success': False,
                    'error': 'Failed to verify customer credentials'
                }), 500
        else:
            customer_code = None  # Admins don't need customer code
        
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
    auth_error = require_api_auth(admin_only=True)
    if auth_error:
        return auth_error

    payload = request.get_json() or {}

    try:
        return proxy_json_request('POST', ENDPOINT_PATHS['updateorderstatus'], payload=payload)
    except Exception as e:
        print(f"Error proxying status update to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to update order status'}), 500
@app.route('/php/getOrderDetails.php')
def proxy_get_order_details():
    """Proxy endpoint to fetch order details via XAMPP PHP."""
    auth_error = require_api_auth()
    if auth_error:
        return auth_error

    orderid = request.args.get('orderid')
    if not orderid:
        return jsonify({'success': False, 'error': 'orderid parameter required'}), 400

    try:
        return proxy_json_request('GET', ENDPOINT_PATHS['getorderdetails'], params={'orderid': orderid})
    except Exception as e:
        print(f"Error proxying getOrderDetails to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch order details'}), 500


@app.route('/php/updateOrderDetail.php', methods=['POST'])
def proxy_update_order_detail():
    """Proxy endpoint to update order detail via XAMPP PHP."""
    auth_error = require_api_auth(admin_only=True)
    if auth_error:
        return auth_error

    payload = request.get_json() or {}

    try:
        return proxy_json_request('POST', ENDPOINT_PATHS['updateorderdetail'], payload=payload)
    except Exception as e:
        print(f"Error proxying updateOrderDetail to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to update order detail'}), 500


@app.route('/php/insertOrderDetail.php', methods=['POST'])
def proxy_insert_order_detail():
    """Proxy endpoint to insert order detail via XAMPP PHP."""
    auth_error = require_api_auth(admin_only=True)
    if auth_error:
        return auth_error

    payload = request.get_json() or {}

    try:
        return proxy_json_request('POST', ENDPOINT_PATHS['insertorderdetail'], payload=payload)
    except Exception as e:
        print(f"Error proxying insertOrderDetail to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to insert order detail'}), 500


@app.route('/php/requestOrderChange.php', methods=['POST'])
def proxy_request_order_change():
    """Proxy endpoint to submit order change request."""
    auth_error = require_api_auth()
    if auth_error:
        return auth_error

    payload = request.get_json() or {}

    try:
        return proxy_json_request('POST', '/php/requestOrderChange.php', payload=payload)
    except requests.exceptions.Timeout:
        print(f"Timeout connecting to XAMPP at {BASE_API_URL}")
        return jsonify({'success': False, 'error': 'Request timed out. Please check if XAMPP is running.'}), 500
    except requests.exceptions.ConnectionError:
        print(f"Connection error to XAMPP at {BASE_API_URL}")
        return jsonify({'success': False, 'error': 'Cannot connect to database server. Please ensure XAMPP is running.'}), 500
    except Exception as e:
        print(f"Error proxying change request to XAMPP: {e}")
        return jsonify({'success': False, 'error': f'Failed to submit change request: {str(e)}'}), 500


@app.route('/php/getOrderRemarks.php')
def proxy_get_order_remarks():
    """Proxy endpoint to get order remarks."""
    auth_error = require_api_auth()
    if auth_error:
        return auth_error
    
    orderid = request.args.get('orderid')
    if not orderid:
        return jsonify({'success': False, 'error': 'orderid parameter required'}), 400
    
    try:
        return proxy_json_request('GET', '/php/getOrderRemarks.php', params={'orderid': orderid})
    except Exception as e:
        print(f"Error proxying get remarks to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch remarks'}), 500

@app.route('/php/insertDraftQuotation.php', methods=['POST'])
def proxy_insert_draft_quotation():
    """Proxy endpoint to create draft quotation via XAMPP PHP."""
    auth_error = require_api_auth()
    if auth_error:
        return auth_error
    
    payload = request.get_json() or {}
    
    try:
        return proxy_json_request('POST', '/php/insertDraftQuotation.php', payload=payload)
    except Exception as e:
        print(f"Error proxying insertDraftQuotation to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to create draft quotation'}), 500

@app.route('/php/updateDraftQuotation.php', methods=['POST'])
def proxy_update_draft_quotation():
    """Proxy endpoint to update draft quotation via XAMPP PHP."""
    auth_error = require_api_auth()
    if auth_error:
        return auth_error
    
    payload = request.get_json() or {}
    
    try:
        return proxy_json_request('POST', '/php/updateDraftQuotation.php', payload=payload)
    except Exception as e:
        print(f"Error proxying updateDraftQuotation to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to update draft quotation'}), 500

@app.route('/admin')
def admin():
    """Display admin dashboard (requires authentication and admin role)"""
    page_error = require_page_access(require_admin=True)
    if page_error:
        return page_error
    return render_template('admin.html', user_email=session.get('user_email', ''))


@app.route('/admin/pending-approvals')
def admin_pending_approvals():
    """Display pending approvals page (admin only)."""
    page_error = require_page_access(require_admin=True)
    if page_error:
        return page_error
    return render_template('adminApproval.html', 
                         user_email=session.get('user_email', ''),
                         user_type='admin')




@app.route('/user/approvals')
def user_approvals():
    """Display user approvals page (regular users)."""
    page_error = require_page_access()
    if page_error:
        return page_error
    return render_template('userApproval.html', 
                         user_email=session.get('user_email', ''))


@app.route('/user/draft-orders')
def user_draft_orders():
    """Display draft orders page (regular users)."""
    page_error = require_page_access()
    if page_error:
        return page_error
    return render_template('draftOrders.html', 
                         user_email=session.get('user_email', ''))


@app.route('/create-order')
def create_order_page():
    """Display create order page (regular users)."""
    page_error = require_page_access(block_admin=True, admin_redirect='/admin')
    if page_error:
        return page_error
    return render_template('createOrder.html', 
                         user_email=session.get('user_email', ''))

@app.route('/create-quotation')
def create_quotation_page():
    """Display create quotation page (regular users)."""
    page_error = require_page_access(block_admin=True, admin_redirect='/admin')
    if page_error:
        return page_error
    dockey = request.args.get('dockey', '')
    return render_template('createQuotation.html', 
                         user_email=session.get('user_email', ''),
                         dockey=dockey)


@app.route('/view-quotation')
def view_quotation_page():
    """Display quotation listing page (regular users)."""
    page_error = require_page_access(block_admin=True, admin_redirect='/admin/view-quotations')
    if page_error:
        return page_error
    # Always render the user template for users
    return render_template('viewQuotation.html',
                         user_email=session.get('user_email', ''),
                         user_type=session.get('user_type', ''))

@app.route('/admin/view-quotations')
def admin_view_quotations():
    """Display all quotations page (admin only)."""
    page_error = require_page_access(require_admin=True)
    if page_error:
        return page_error
    # Always render the admin template for admins
    return render_template('adminViewQuotations.html', 
                         user_email=session.get('user_email', ''),
                         user_type=session.get('user_type', ''))


@app.route('/admin/pricing-priority-rules')
def admin_pricing_priority_rules():
    """Display pricing priority rule settings page (admin only)."""
    page_error = require_page_access(require_admin=True)
    if page_error:
        return page_error
    return render_template(
        'pricingPriorityRules.html',
        user_email=session.get('user_email', ''),
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
    page_error = require_page_access(require_admin=True)
    if page_error:
        return page_error
    return render_template('admin_edit_approval.html', user_email=session.get('user_email', ''), orderid=orderid)


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
            conn = fdb.connect(dsn=DB_PATH, user=DB_USER, password=DB_PASSWORD)
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
        catalog_response = build_catalog_response(user_input, stockitems, stock_groups, price_lookup_by_desc)

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
            # Truncate messages to 4000 characters for database field limit (after DbInitializer.py runs)
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
    try:
        stockitems = fetch_data_from_api("stockitem")
        return jsonify({'success': True, 'items': stockitems})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

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
        no_match_message = None

        # Fetch ST_ITEM.UDF_STDPRICE for Suggested Price field
        st_item_udf_stdprice = None
        if item_code:
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
    user_email = session.get('user_email')
    customer_code = session.get('customer_code')
    data = request.get_json() or {}
    dockey = data.get('dockey', None)  # If present, update existing quotation
    description = data.get('description', '').strip()
    valid_until = data.get('validUntil', '')
    items = data.get('items', [])
    currency_code = data.get('currencyCode', 'MYR')
    company_name = data.get('companyName', '')
    address1 = data.get('address1', '')
    address2 = data.get('address2', '')
    phone1 = data.get('phone1', '')
    
    # DEBUG: Log entry point and dockey value
    print(f"DEBUG [Flask api_create_quotation]: ENTERED - dockey={dockey}, companyName={company_name}", flush=True)
    
    if not items:
        print(f"DEBUG [Flask api_create_quotation]: No items provided", flush=True)
        return jsonify({'success': False, 'error': 'At least one item is required'}), 400
    
    try:
        # If dockey is provided, update the existing draft quotation
        if dockey:
            print(f"DEBUG [Flask]: UPDATING quotation - dockey={dockey}", flush=True)
            quotation_response = requests.post(
                f"{BASE_API_URL}/php/updateDraftQuotation.php",
                json={
                    "dockey": dockey,
                    "description": description,
                    "validUntil": valid_until,
                    "companyName": company_name,
                    "address1": address1,
                    "address2": address2,
                    "phone1": phone1,
                    "items": items
                },
                timeout=10
            )
        else:
            # Create new quotation in SL_QT
            print(f"DEBUG [Flask]: CREATING new quotation - companyName: {company_name}, address1: {address1}, address2: {address2}, phone1: {phone1}", flush=True)
            quotation_response = requests.post(
                f"{BASE_API_URL}/php/insertQuotationToAccounting.php",
                json={
                    "customerCode": customer_code,
                    "description": description,
                    "validUntil": valid_until,
                    "currencyCode": currency_code,
                    "companyName": company_name,
                    "address1": address1,
                    "address2": address2,
                    "phone1": phone1,
                    "items": items
                },
                timeout=10
            )
        
        quotation_data = quotation_response.json()
        
        if not quotation_data.get('success'):
            return jsonify({'success': False, 'error': quotation_data.get('error', 'Failed to create quotation')}), 500
        
        return jsonify({
            'success': True, 
            'dockey': quotation_data.get('dockey'),
            'docno': quotation_data.get('docno'),
            'message': quotation_data.get('message')
        })
    except Exception as e:
        print(f"Error creating/updating quotation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_my_quotations')
@api_login_required(unauth_message='Unauthorized')
def api_get_my_quotations():
    """Get quotations for current logged in user by customer code."""
    customer_code = session.get('customer_code')
    
    # If customer_code not in session, fetch it from AR_CUSTOMERBRANCH (for old sessions)
    if not customer_code:
        user_email = session.get('user_email')
        try:
            con = get_db_connection()
            cur = con.cursor()
            cur.execute('SELECT CODE FROM AR_CUSTOMERBRANCH WHERE EMAIL = ?', (user_email,))
            customer_row = cur.fetchone()
            cur.close()
            con.close()
            
            if customer_row:
                customer_code = customer_row[0]
                session['customer_code'] = customer_code  # Update session for next time
                print(f"[Session Fix] Retrieved customer_code for {user_email}: {customer_code}")
            else:
                return jsonify({'success': False, 'error': 'Customer code not found. Please logout and login again.'}), 400
        except Exception as e:
            print(f"[Error] Failed to fetch customer_code: {e}")
            return jsonify({'success': False, 'error': 'Failed to retrieve customer information'}), 500

    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute(
            '''
            SELECT q.DOCKEY, q.DOCNO, q.DOCDATE, q.DESCRIPTION, q.DOCAMT, q.VALIDITY, q.STATUS, q.TERMS, q.CANCELLED
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
            else:
                cancelled_value = str(cancelled_raw).strip().lower() in ('1', 'true', 't', 'yes', 'y')
            
            quotations.append({
                'DOCKEY': int(row[0]) if row[0] is not None else None,
                'DOCNO': row[1],
                'DOCDATE': str(row[2]) if row[2] is not None else None,
                'DESCRIPTION': row[3],
                'DOCAMT': float(row[4]) if row[4] is not None else 0,
                'VALIDITY': row[5],
                'STATUS': status_str,
                'CREDITTERM': str(row[7]) if row[7] is not None else 'N/A',
                'CANCELLED': cancelled_value
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
        response = requests.get(
            f"{BASE_API_URL}/php/getQuotationDetails.php",
            params={'dockey': dockey},
            timeout=10
        )
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/get_all_quotations')
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_get_all_quotations():
    """Get all quotations for admin view with optional status filter."""
    cancelled = request.args.get('cancelled')  # 'true' or 'false'
    print(f"[DEBUG] api_admin_get_all_quotations: cancelled param = {cancelled}", flush=True)

    try:
        php_url = f"{BASE_API_URL}{ENDPOINT_PATHS['getallquotations']}"
        params = {}
        if cancelled is not None:
            params['cancelled'] = cancelled
        print(f"[DEBUG] Calling PHP with params: {params}, full URL: {php_url}?cancelled={cancelled}", flush=True)
        response = requests.get(php_url, params=params, timeout=10)
        result = response.json()
        print(f"[DEBUG] PHP returned {result.get('count', 0)} quotations", flush=True)
        return jsonify(result)
    except Exception as e:
        print(f"[Error] Failed to fetch all quotations: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/get_quotation_detail')
@api_admin_required(unauth_message='Unauthorized', forbidden_message='Admin access required')
def api_admin_get_quotation_detail():
    """Get quotation details including line items (admin only)."""
    dockey = request.args.get('dockey')
    if not dockey:
        return jsonify({'success': False, 'error': 'dockey parameter required'}), 400

    try:
        response = requests.get(
            f"{BASE_API_URL}/php/getQuotationDetails.php",
            params={'dockey': dockey},
            timeout=10
        )
        result = response.json()
        
        # PHP returns: { success: true, data: { DOCKEY, DOCNO, items: [...] } }
        if result.get('success'):
            data = result.get('data', {})
            return jsonify({
                'success': True,
                'quotation': data,  # Contains DOCKEY, DOCNO, DOCDATE, CODE, COMPANYNAME, ADDRESS1, ADDRESS2, PHONE1, VALIDITY, TERMS, CREDITTERM
                'items': data.get('items', [])  # Array of items with DESCRIPTION, QTY, UNITPRICE
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')}), 400
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
    
    # Format data for PHP endpoint
    update_data = {
        'dockey': dockey,
        'validUntil': data.get('validUntil'),
        'items': items,
        'cancelled': False  # Set to active when updating
    }
    
    try:
        # Use the update draft quotation endpoint
        response = requests.post(
            f"{BASE_API_URL}/php/updateDraftQuotation.php",
            json=update_data,
            timeout=10
        )
        result = response.json()
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
    customer_code = session.get('customer_code')
    if not customer_code:
        print("[DEBUG] get_user_info: customer_code not in session", flush=True)
        return jsonify({'success': False, 'error': 'Customer code not found'}), 400

    try:
        # Proxy to PHP endpoint using BASE_API_URL and ENDPOINT_PATHS
        php_url = f"{BASE_API_URL}{ENDPOINT_PATHS['getuserinfo']}"
        print(f"[DEBUG] get_user_info: Calling PHP at {php_url}?customerCode={customer_code}", flush=True)
        response = requests.get(php_url, params={'customerCode': customer_code}, timeout=10)
        print(f"[DEBUG] get_user_info: PHP response status {response.status_code}", flush=True)
        return jsonify(response.json())
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
    initialize_database(DB_PATH, DB_USER, DB_PASSWORD)
    print("Starting Flask web server at http://localhost:5000 ...")
    app.run(debug=True, use_reloader=False)