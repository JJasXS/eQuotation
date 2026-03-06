# DEBUG: Confirm Flask main.py is running
print("[DEBUG] main.py loaded and Flask is starting...", flush=True)
import os
from datetime import datetime, timedelta
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
    resolve_numbered_reference
)

# Load environment variables from .env file
load_dotenv()

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
DB_PATH = os.getenv('DB_PATH', r'C:\eStream\SQLAccounting\DB\ACC-0001.FDB')
DB_USER = os.getenv('DB_USER', 'sysdba')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'masterkey')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set. Please configure it in .env file.")

openai.api_key = OPENAI_API_KEY

# ============================================
# INITIALIZE UTILITY MODULES
# ============================================
# Configure database utils
set_db_config(DB_PATH, DB_USER, DB_PASSWORD)

# Configure API utils
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

# ============================================
# TYPO CORRECTION DICTIONARY
# ============================================
@app.route('/api/admin/update_quotation_cancelled', methods=['POST'])
def update_quotation_cancelled():
    """Forward CANCELLED status update to PHP endpoint (admin only)."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Insufficient permissions'}), 403

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
        return jsonify({'success': True, 'message': 'Quotation status updated'}), 200
    except Exception as e:
        print(f"Error updating quotation cancelled status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
_TYPO_MAP_CACHE = None

def load_typo_corrections():
    """Load typo corrections from file (cached)"""
    global _TYPO_MAP_CACHE
    if _TYPO_MAP_CACHE is not None:
        return _TYPO_MAP_CACHE
    
    typo_map = {}
    typo_file = os.path.join(os.path.dirname(__file__), 'training', 'typo_corrections.txt')
    
    try:
        with open(typo_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Parse "typo -> correct" format
                if '->' in line:
                    parts = line.split('->')
                    if len(parts) == 2:
                        typo = parts[0].strip()
                        correct = parts[1].strip()
                        if typo and correct:
                            typo_map[typo] = correct
    except FileNotFoundError:
        print(f"Warning: Typo corrections file not found at {typo_file}. Using empty map.")
    except Exception as e:
        print(f"Warning: Error loading typo corrections: {e}. Using empty map.")
    
    _TYPO_MAP_CACHE = typo_map
    return typo_map

# SMTP Configuration for Email
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_EMAIL = os.getenv('SMTP_EMAIL', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')

# Central config for API base URL and endpoint paths (inlined from endpoints_config.py)
ENDPOINT_PATHS = {
    "stockitem": "/php/getStockItem.php",
    "stockitemprice": "/php/getStockItemPrice.php",
    "stockitembydescription": "/php/getStockItemByDescription.php",
    "chats": "/php/getChats.php",
    "chatdetails": "/php/getChatDetails.php",
    "insertchatmessage": "/php/insertChatMessage.php",
    "chatbyid": "/php/getChatByID.php",
    "chattpldtl": "/php/getChatTPLDTL.php",
    "insertorder": "/php/insertOrder.php",
    "insertorderdetail": "/php/insertOrderDetail.php",
    "updateorderdetail": "/php/updateOrderDetail.php",
    "deleteorderdetail": "/php/deleteOrderDetail.php",
    "getorderdetails": "/php/getOrderDetails.php",
    "completeorder": "/php/completeOrder.php",
    "getordersbystatus": "/php/getOrdersByStatus.php",
    "updateorderstatus": "/php/updateOrderStatus.php",
    "getuserbyemail": "/php/getUserByEmail.php",
    "getadminbyemail": "/php/getAdminByEmail.php",
}
from config.endpoints_config import ENDPOINT_PATHS
MAX_HISTORY_MESSAGES = 50

# ============================================
# CHATBOT BUSINESS RULES / SYSTEM INSTRUCTIONS
# ============================================
# Load chatbot instructions from external file
def load_chatbot_instructions():
    """Load chatbot instructions from config/chatbot_instructions.txt"""
    instructions_path = os.path.join(os.path.dirname(__file__), 'config', 'chatbot_instructions.txt')
    try:
        with open(instructions_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Warning: {instructions_path} not found. Using default instructions.")
        return "You are a helpful assistant."
    except Exception as e:
        print(f"Error loading instructions: {e}")
        return "You are a helpful assistant."

CHATBOT_SYSTEM_INSTRUCTIONS = load_chatbot_instructions()


def fetch_data_from_api(endpoint_key):
    path = ENDPOINT_PATHS.get(endpoint_key)
    if not path:
        print(f"No path configured for endpoint: {endpoint_key}")
        return []
    url = f"{BASE_API_URL}{path}"
    try:
        response = requests.get(url)
        data = response.json()
        if data.get('success'):
            return data.get('data', [])
        else:
            print(f"API error for {endpoint_key}:", data.get('error'))
            return []
    except Exception as e:
        print(f"Failed to fetch from API {endpoint_key}:", e)
        return []


def get_db_connection():
    return fdb.connect(
        dsn=DB_PATH,
        user=DB_USER,
        password=DB_PASSWORD,
        charset='UTF8'
    )


def user_owns_chat(chatid, user_email):
    """Check whether a chat belongs to the logged-in user."""
    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute('SELECT CHATID FROM CHAT_TPL WHERE CHATID = ? AND OWNEREMAIL = ?', (chatid, user_email))
        return cur.fetchone() is not None
    except Exception as e:
        print(f"Failed to verify chat ownership: {e}")
        return False
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


def get_chat_history(chatid, user_email=None):
    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        if user_email:
            cur.execute(
                'SELECT d.MESSAGEID, d.CHATID, d.SENDER, d.MESSAGETEXT, d.SENTAT '
                'FROM CHAT_TPLDTL d '
                'JOIN CHAT_TPL c ON c.CHATID = d.CHATID '
                'WHERE d.CHATID = ? AND c.OWNEREMAIL = ? '
                'ORDER BY d.SENTAT ASC',
                (chatid, user_email)
            )
        else:
            cur.execute(
                'SELECT MESSAGEID, CHATID, SENDER, MESSAGETEXT, SENTAT '
                'FROM CHAT_TPLDTL WHERE CHATID = ? ORDER BY SENTAT ASC',
                (chatid,)
            )

        return [
            {
                'MESSAGEID': row[0],
                'CHATID': row[1],
                'SENDER': row[2],
                'MESSAGETEXT': row[3],
                'SENTAT': row[4].strftime('%Y-%m-%d %H:%M:%S') if row[4] else None
            }
            for row in cur.fetchall()
        ]
    except Exception as e:
        print(f"Failed to fetch chat history: {e}")
    finally:
        if cur:
            cur.close()
        if con:
            con.close()
    return []


def insert_chat_message(chatid, sender, messagetext):
    return requests.post(
        f"{BASE_API_URL}/php/insertChatMessage.php",
        json={"chatid": chatid, "sender": sender, "messagetext": messagetext}
    )


def update_chat_last_message(chatid, messagetext, user_email=None):
    con = get_db_connection()
    cur = con.cursor()
    if user_email:
        cur.execute(
            'UPDATE CHAT_TPL SET LASTMESSAGE = ? WHERE CHATID = ? AND OWNEREMAIL = ?',
            (messagetext, chatid, user_email)
        )
    else:
        cur.execute('UPDATE CHAT_TPL SET LASTMESSAGE = ? WHERE CHATID = ?', (messagetext, chatid))
    con.commit()
    cur.close()
    con.close()


def format_rm(value):
    if value is None:
        return "-"
    try:
        numeric_value = float(str(value).replace(',', '').strip())
        return f"RM {numeric_value:.2f}"
    except (ValueError, TypeError):
        raw_value = str(value).strip()
        return f"RM {raw_value}" if raw_value else "-"

# Function to test Firebird DB connection
def test_firebird_connection():
    try:
        con = get_db_connection()
        con.close()
        print("Firebird database connection successful.")
    except Exception as e:
        print("Firebird database connection failed:", e)

# ============================================
# ORDER MANAGEMENT FUNCTIONS
# ============================================
def get_active_order(chatid):
    """Get active DRAFT order for chat (only check, don't create)"""
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute('SELECT ORDERID FROM ORDER_TPL WHERE CHATID = ? AND STATUS = ?', (chatid, 'DRAFT'))
        result = cur.fetchone()
        cur.close()
        con.close()
        
        if result:
            return result[0]
        else:
            # Return None - order will be created only when user triggers order intent
            return None
    except Exception as e:
        print(f"Error getting active order: {e}")
    return None

def parse_order_intent(user_input):
    """Detect if user is trying to create/manage order"""
    lower_input = user_input.lower()
    normalized_input = normalize_intent_text(lower_input)

    # Check for 'remove all' intent
    if 'remove all' in normalized_input or 'clear all' in normalized_input or 'delete all' in normalized_input:
        return 'remove_all'

    # Check for update/change quantity intent
    if 'update' in normalized_input or 'change' in normalized_input:
        return 'update'

    # Check ADD first if there's a product reference (more specific)
    if contains_intent_phrase(normalized_input, ADD_ORDER_KEYWORDS):
        return 'add'

    if contains_intent_phrase(normalized_input, CREATE_ORDER_KEYWORDS):
        return 'create'
    elif contains_intent_phrase(normalized_input, COMPLETE_ORDER_KEYWORDS):
        return 'complete'
    elif contains_intent_phrase(normalized_input, REMOVE_ORDER_KEYWORDS):
        return 'remove'

    # Flexible fallback for natural phrases like "I awnt to make order"
    token_set = set(normalized_input.split())
    if token_set.intersection({'create', 'make', 'start', 'begin', 'open'}) and 'order' in token_set:
        return 'create'

    return None


def normalize_intent_text(text):
    """Normalize text by fixing typos using external corrections file"""
    typo_map = load_typo_corrections()
    
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', text.lower())
    tokens = [token for token in cleaned.split() if token]
    normalized_tokens = [typo_map.get(token, token) for token in tokens]
    return ' '.join(normalized_tokens)


def contains_intent_phrase(normalized_input, phrases):
    if not normalized_input:
        return False

    normalized_tokens = normalized_input.split()
    for phrase in phrases:
        normalized_phrase = normalize_intent_text(phrase)
        if normalized_phrase in normalized_input:
            return True

        phrase_tokens = normalized_phrase.split()
        if not phrase_tokens:
            continue

        # Fuzzy phrase match over token windows for minor typos/spelling noise
        # Skip fuzzy matching for very short phrases to avoid false positives (e.g., 'one' matching 'done')
        if len(normalized_phrase) < 5:
            continue
            
        window_size = len(phrase_tokens)
        if len(normalized_tokens) < window_size:
            continue

        for i in range(len(normalized_tokens) - window_size + 1):
            window = ' '.join(normalized_tokens[i:i + window_size])
            ratio = SequenceMatcher(None, window, normalized_phrase).ratio()
            if ratio >= 0.85:
                return True

    return False

def resolve_numbered_reference(user_input, stock_items):
    """Resolve references like 'number 1', 'the first one', '#2' to actual product names"""
    lower_input = user_input.lower()
    
    index = None
    # Use configurable patterns from order_config
    for pattern in NUMBERED_REFERENCE_PATTERNS:
        match = re.search(pattern, lower_input)
        if match:
            if match.group(1).isdigit():
                index = int(match.group(1)) - 1  # Convert to 0-based index
            else:
                # Word numbers (first, second, etc.) - use configured word map
                index = ORDINAL_WORD_MAP.get(match.group(1))
            break
    
    if index is not None and 0 <= index < len(stock_items):
        product = stock_items[index].get('DESCRIPTION')
        print(f"[DEBUG] Numbered reference: Resolved to index {index+1} -> '{product}'", flush=True)
        return product
    
    # Alternative: Check if input is "the first one" or similar without specific pattern match
    # This handles cases like "yeah the first item"
    ordinal_words = ['first', 'second', 'third', 'fourth', 'fifth']
    for word in ordinal_words:
        if word in lower_input:
            idx = ORDINAL_WORD_MAP.get(word)
            if idx is not None and idx < len(stock_items):
                product = stock_items[idx].get('DESCRIPTION')
                print(f"[DEBUG] Fallback: Found ordinal word '{word}' -> index {idx+1} -> '{product}'", flush=True)
                return product
    
    return None

def extract_product_and_quantity(user_input, stock_items, chat_history=None):
    """Extract product name and quantity from user input with fuzzy matching.
    
    Args:
        user_input: User's message
        stock_items: List of available products
        chat_history: Optional chat history to extract context from previous messages
    """
    lower_input = user_input.lower().strip()
    
    # Remove common filler phrases at the start (yeah, ok, yes, please, etc.)
    lower_input = re.sub(r'^(yeah|ok|okay|yes|yep|sure|please|so)\s+', '', lower_input, flags=re.IGNORECASE)
    
    # First check if user is referencing a numbered item from a list
    referenced_product = resolve_numbered_reference(lower_input, stock_items)
    if referenced_product:
        # Extract quantity separately
        qty_match = re.search(r'\b(\d+)\s+(?:units?|pcs?|pieces?)', lower_input)
        qty = int(qty_match.group(1)) if qty_match else 1
        
        # Find the product in stock_items to get full details
        for item in stock_items:
            if item.get('DESCRIPTION') == referenced_product:
                result = {
                    'description': item.get('DESCRIPTION'),
                    'code': item.get('CODE'),
                    'qty': qty,
                    'matched': True,
                    'from_reference': True
                }
                print(f"[DEBUG] Product info: Description='{result['description']}', Code='{result['code']}', Qty={qty}", flush=True)
                return result
    
    # Extract number from input (for quantity)
    qty_match = re.search(r'\b(\d+)\b', lower_input)
    qty = int(qty_match.group(1)) if qty_match else 1
    
    # First pass: Exact match for product codes/descriptions in stock
    for item in stock_items:
        item_desc = item.get('DESCRIPTION', '').lower()
        item_code = item.get('CODE', '').lower()
        
        # Check if product name/code appears in user input
        if (item_desc and len(item_desc) >= MIN_PRODUCT_NAME_LENGTH and item_desc in lower_input) or \
           (item_code and len(item_code) >= MIN_PRODUCT_CODE_LENGTH and item_code in lower_input):
            return {
                'description': item.get('DESCRIPTION'),
                'code': item.get('CODE'),
                'qty': qty,
                'matched': True
            }
    
    # Second pass: Extract product text and fuzzy match
    product_text = None
    
    if qty_match:
        # Get text after the quantity and clean up filler words
        product_text = user_input[qty_match.end():].strip()
        # Remove filler words from configuration (prefix)
        product_text = re.sub(fr'^\s*{QUANTITY_FILLER_PATTERN}\s+', '', product_text, flags=re.IGNORECASE)
        # Remove filler words from configuration (suffix)
        product_text = re.sub(fr'\s+{QUANTITY_FILLER_PATTERN}$', '', product_text, flags=re.IGNORECASE)
    else:
        # No quantity specified - extract after keywords
        for keyword in PRODUCT_EXTRACTION_KEYWORDS:
            if keyword in lower_input:
                parts = lower_input.split(keyword, 1)
                if len(parts) > 1:
                    product_text = parts[1].strip()
                    
                    # Remove configured prefix patterns like "to buy", "to order", etc.
                    product_text = re.sub(PRODUCT_PREFIX_PATTERN, '', product_text, flags=re.IGNORECASE)
                    
                    # Remove configured verbs - handle both with/without spaces
                    # First try: word boundaries (normal: "to buy lighting" -> "lighting")
                    verbs_pattern = '|'.join(re.escape(verb) for verb in PRODUCT_EXTRACTION_VERBS)
                    product_text = re.sub(fr'^\s*({verbs_pattern})\s+', '', product_text, flags=re.IGNORECASE)
                    
                    # Second try: handle concatenated verbs (e.g., "buyraw materials" -> "raw materials")
                    # This removes verbs even if not followed by space (for typos/concatenation)
                    product_text = re.sub(fr'^({verbs_pattern})(?=[a-z])', '', product_text, flags=re.IGNORECASE)
                    
                    break
    
    # If no product text extracted but we have a quantity, try to get product from chat history
    if (not product_text or len(product_text.strip()) < 2) and qty_match and chat_history:
        print(f"[DEBUG] No product name found, searching chat history for recently discussed product...", flush=True)
        # Look for product names mentioned in recent assistant messages
        for msg in reversed(chat_history[-10:]):  # Check last 10 messages
            sender = (msg.get('SENDER') or '').strip().lower()
            text = (msg.get('MESSAGETEXT') or '').strip().lower()
            if sender == 'system':  # Assistant messages
                # Look for product names in assistant's message
                for item in stock_items:
                    item_desc = item.get('DESCRIPTION', '').lower()
                    if item_desc in text and len(item_desc) > 5:  # Avoid matching tiny product names
                        print(f"[DEBUG] Found product in history: '{item_desc}'", flush=True)
                        return {
                            'description': item.get('DESCRIPTION'),
                            'code': item.get('CODE'),
                            'qty': qty,
                            'matched': True,
                            'from_history': True
                        }
    
    # Check if product_text is only a quantity filler word (like 'units', 'pcs', etc.)
    from config.order_config import QUANTITY_FILLER_WORDS
    if not product_text or len(product_text.strip()) < 2 or product_text.strip().lower() in QUANTITY_FILLER_WORDS:
        print(f"[DEBUG] Extracted text too short or only filler: '{product_text}'", flush=True)
        return None
    
    # Fuzzy match extracted text against stock items
    product_lower = product_text.lower().strip()
    best_match = None
    best_ratio = 0.0
    
    print(f"[DEBUG] Extracted product text: '{product_lower}'", flush=True)
    
    for item in stock_items:
        item_desc = item.get('DESCRIPTION', '').lower()
        item_code = item.get('CODE', '').lower()
        
        # Check both description and code with fuzzy matching
        # Also check substring matches for better keyword matching
        desc_ratio = SequenceMatcher(None, product_lower, item_desc).ratio()
        code_ratio = SequenceMatcher(None, product_lower, item_code).ratio()
        
        # Check if input is a substring of description (higher confidence)
        if product_lower in item_desc:
            desc_ratio = SUBSTRING_MATCH_BONUS  # High confidence for substring match
        
        max_ratio = max(desc_ratio, code_ratio)
        
        if max_ratio > best_ratio:
            best_ratio = max_ratio
            best_match = item
        
        if max_ratio > 0.3:  # Only log reasonable matches to reduce noise
            print(f"[DEBUG] Match: '{product_lower}' vs '{item_desc}' = {max_ratio:.2%}", flush=True)
    
    # If fuzzy match confidence is high enough (configured threshold), use it
    if best_match and best_ratio >= FUZZY_MATCH_THRESHOLD:
        print(f"[DEBUG] ✓ Matched: '{product_text}' -> '{best_match.get('DESCRIPTION')}' ({best_ratio:.2%})", flush=True)
        return {
            'description': best_match.get('DESCRIPTION'),
            'code': best_match.get('CODE') or best_match.get('DESCRIPTION'),
            'qty': qty,
            'matched': True,
            'confidence': best_ratio
        }
    
    # Return unmatched product text with suggestions
    print(f"[DEBUG] ✗ No match for '{product_text}' (best: {best_ratio:.2%})", flush=True)
    return {
        'description': product_text,
        'code': product_text,
        'qty': qty,
        'matched': False,
        'best_match': best_match,
        'best_ratio': best_ratio
    }

def get_product_price(product_info, stock_prices):
    """Get price for a product by matching CODE or DESCRIPTION"""
    # Extract description and code
    description = product_info.get('description', '') if isinstance(product_info, dict) else product_info
    code = product_info.get('code', '') if isinstance(product_info, dict) else ''
    
    print(f"[DEBUG] Looking for price - Description: '{description}', Code: '{code}'", flush=True)
    print(f"[DEBUG] Checking {len(stock_prices)} price items...", flush=True)
    
    for price_item in stock_prices:
        price_desc = price_item.get('DESCRIPTION', '')
        price_code = price_item.get('CODE', '')
        
        # Match by DESCRIPTION or CODE (case-insensitive)
        if (description and price_desc.lower() == description.lower()) or \
           (code and price_code.lower() == code.lower()):
            print(f"[DEBUG] Found match! Price: {price_item.get('STOCKVALUE', 0)}", flush=True)
            return float(price_item.get('STOCKVALUE', 0))
    
    # No exact match - try fuzzy matching on description
    if description:
        best_match = None
        best_ratio = 0.0
        for price_item in stock_prices:
            price_desc = price_item.get('DESCRIPTION', '')
            if price_desc:
                ratio = SequenceMatcher(None, description.lower(), price_desc.lower()).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = price_item
        
        # If fuzzy match is strong enough (configured threshold), use it
        if best_match and best_ratio >= PRICE_MATCH_THRESHOLD:
            print(f"[DEBUG] Fuzzy match found ({best_ratio:.2f}): {best_match.get('DESCRIPTION')} - Price: {best_match.get('STOCKVALUE')}", flush=True)
            return float(best_match.get('STOCKVALUE', 0))
        elif best_match:
            print(f"[DEBUG] Best match only {best_ratio:.2f}: {best_match.get('DESCRIPTION')}", flush=True)
    
    print(f"[DEBUG] No price found for '{description}' (code: '{code}')", flush=True)
    return None

def chat_with_gpt(messages):
    client = openai.OpenAI(api_key=openai.api_key)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages
    )
    return response.choices[0].message.content.strip()

# ============================================
# HYBRID AI: LOCAL + OPENAI
# ============================================
# Initialize local intent classifier (if available)
local_intent_classifier = None
if LOCAL_AI_ENABLED:
    try:
        local_intent_classifier = IntentClassifier()
        print(f"✅ Intent classifier initialized: {local_intent_classifier.get_stats()}")
    except Exception as e:
        print(f"⚠️  Could not initialize intent classifier: {e}")
        local_intent_classifier = None

def detect_intent_hybrid(user_input):
    """
    Hybrid intent detection: Try local AI first, fallback to OpenAI if needed.
    
    Returns:
        dict: {
            'intent': str,  # 'create_order', 'add_item', etc. or 'unknown'
            'confidence': float,  # 0.0 - 1.0
            'source': str  # 'local' or 'openai'
        }
    """
    user_input_lower = user_input.lower().strip()
    
    # Try local AI first if available
    if local_intent_classifier and local_intent_classifier.is_loaded:
        intent, confidence = local_intent_classifier.predict(user_input_lower)
        
        if local_intent_classifier.should_use_local(intent, confidence):
            print(f"🤖 [LOCAL AI] Intent: {intent} (confidence: {confidence:.2%})")
            return {
                'intent': intent,
                'confidence': confidence,
                'source': 'local'
            }
        else:
            print(f"🌐 [FALLBACK] Low confidence ({confidence:.2%}) or unknown intent, using OpenAI")
    
    # Fallback: Use existing keyword-based detection (fast) or return unknown
    # This will still trigger the existing parse_order_intent() logic
    return {
        'intent': 'unknown',
        'confidence': 0.0,
        'source': 'fallback'
    }

app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/static")

# Configure Flask session
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ============================================
# AUTHENTICATION FUNCTIONS
# ============================================
def send_email(to_email, subject, body):
    """Send email using SMTP (Gmail example)"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print("WARNING: SMTP_EMAIL or SMTP_PASSWORD not configured. Using console output for debugging.")
        print(f"Email would be sent to: {to_email}")
        print(f"Subject: {subject}")
        print(f"Body:\n{body}")
        return True
    
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

@app.route('/login')
def login():
    """Show login page"""
    if 'user_email' in session:
        if session.get('user_type') == 'admin':
            return redirect('/admin')
        return redirect('/chat')
    return render_template('login.html')

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

        if not is_admin and not is_user:
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
        
        send_email(email, subject, body)
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
        redirect_url = '/chat'
        
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
        
        # If not admin, check if email exists in AR_CUSTOMERBRANCH (Regular User)
        if user_type == 'user':
            try:
                # Look up customer code from AR_CUSTOMERBRANCH via EMAIL
                con = get_db_connection()
                cur = con.cursor()
                cur.execute('SELECT CODE FROM AR_CUSTOMERBRANCH WHERE EMAIL = ?', (email,))
                customer_row = cur.fetchone()
                cur.close()
                con.close()
                
                if customer_row:
                    customer_code = customer_row[0]
                    user_type = 'user'
                    redirect_url = '/chat'
                    print(f"[AUTH] Regular user detected: {email} → Customer: {customer_code}")
                else:
                    # Email not found in AR_CUSTOMERBRANCH
                    return jsonify({
                        'success': False, 
                        'error': 'Email not found in customer branch database, please contact administrator'
                    }), 401
            except Exception as e:
                print(f"[AUTH] Customer branch lookup failed: {e}")
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
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
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
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    payload = request.get_json() or {}

    try:
        url = f"{BASE_API_URL}{ENDPOINT_PATHS['updateorderstatus']}"
        response = requests.post(url, json=payload, timeout=10)
        return response.json(), response.status_code
    except Exception as e:
        print(f"Error proxying status update to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to update order status'}), 500
@app.route('/php/getOrderDetails.php')
def proxy_get_order_details():
    """Proxy endpoint to fetch order details via XAMPP PHP."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    orderid = request.args.get('orderid')
    if not orderid:
        return jsonify({'success': False, 'error': 'orderid parameter required'}), 400

    try:
        url = f"{BASE_API_URL}{ENDPOINT_PATHS['getorderdetails']}?orderid={orderid}"
        response = requests.get(url, timeout=10)
        return response.json(), response.status_code
    except Exception as e:
        print(f"Error proxying getOrderDetails to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch order details'}), 500


@app.route('/php/updateOrderDetail.php', methods=['POST'])
def proxy_update_order_detail():
    """Proxy endpoint to update order detail via XAMPP PHP."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    payload = request.get_json() or {}

    try:
        url = f"{BASE_API_URL}{ENDPOINT_PATHS['updateorderdetail']}"
        response = requests.post(url, json=payload, timeout=10)
        return response.json(), response.status_code
    except Exception as e:
        print(f"Error proxying updateOrderDetail to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to update order detail'}), 500


@app.route('/php/insertOrderDetail.php', methods=['POST'])
def proxy_insert_order_detail():
    """Proxy endpoint to insert order detail via XAMPP PHP."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    payload = request.get_json() or {}

    try:
        url = f"{BASE_API_URL}{ENDPOINT_PATHS['insertorderdetail']}"
        response = requests.post(url, json=payload, timeout=10)
        return response.json(), response.status_code
    except Exception as e:
        print(f"Error proxying insertOrderDetail to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to insert order detail'}), 500


@app.route('/php/requestOrderChange.php', methods=['POST'])
def proxy_request_order_change():
    """Proxy endpoint to submit order change request."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    payload = request.get_json() or {}

    try:
        url = f"{BASE_API_URL}/php/requestOrderChange.php"
        response = requests.post(url, json=payload, timeout=10)
        return response.json(), response.status_code
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
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    orderid = request.args.get('orderid')
    if not orderid:
        return jsonify({'success': False, 'error': 'orderid parameter required'}), 400
    
    try:
        url = f"{BASE_API_URL}/php/getOrderRemarks.php?orderid={orderid}"
        response = requests.get(url, timeout=10)
        return response.json(), response.status_code
    except Exception as e:
        print(f"Error proxying get remarks to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to fetch remarks'}), 500

@app.route('/php/insertDraftQuotation.php', methods=['POST'])
def proxy_insert_draft_quotation():
    """Proxy endpoint to create draft quotation via XAMPP PHP."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    payload = request.get_json() or {}
    
    try:
        url = f"{BASE_API_URL}/php/insertDraftQuotation.php"
        response = requests.post(url, json=payload, timeout=10)
        return response.json(), response.status_code
    except Exception as e:
        print(f"Error proxying insertDraftQuotation to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to create draft quotation'}), 500

@app.route('/php/updateDraftQuotation.php', methods=['POST'])
def proxy_update_draft_quotation():
    """Proxy endpoint to update draft quotation via XAMPP PHP."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    payload = request.get_json() or {}
    
    try:
        url = f"{BASE_API_URL}/php/updateDraftQuotation.php"
        response = requests.post(url, json=payload, timeout=10)
        return response.json(), response.status_code
    except Exception as e:
        print(f"Error proxying updateDraftQuotation to XAMPP: {e}")
        return jsonify({'success': False, 'error': 'Failed to update draft quotation'}), 500

@app.route('/admin')
def admin():
    """Display admin dashboard (requires authentication and admin role)"""
    if 'user_email' not in session:
        return redirect('/login')
    # Check if user is actually admin
    if session.get('user_type') != 'admin':
        return redirect('/chat')
    return render_template('admin.html', user_email=session.get('user_email', ''))


@app.route('/admin/pending-approvals')
def admin_pending_approvals():
    """Display pending approvals page (admin only)."""
    if 'user_email' not in session:
        return redirect('/login')
    if session.get('user_type') != 'admin':
        return redirect('/chat')
    return render_template('adminApproval.html', 
                         user_email=session.get('user_email', ''),
                         user_type='admin')


@app.route('/admin/view-quotations')
def admin_view_quotations():
    """Display all quotations page (admin only)."""
    if 'user_email' not in session:
        return redirect('/login')
    if session.get('user_type') != 'admin':
        return redirect('/chat')
    return render_template('adminViewQuotations.html', 
                         user_email=session.get('user_email', ''))


@app.route('/user/approvals')
def user_approvals():
    """Display user approvals page (regular users)."""
    if 'user_email' not in session:
        return redirect('/login')
    return render_template('userApproval.html', 
                         user_email=session.get('user_email', ''))


@app.route('/user/draft-orders')
def user_draft_orders():
    """Display draft orders page (regular users)."""
    if 'user_email' not in session:
        return redirect('/login')
    return render_template('draftOrders.html', 
                         user_email=session.get('user_email', ''))


@app.route('/create-order')
def create_order_page():
    """Display create order page (regular users)."""
    if 'user_email' not in session:
        return redirect('/login')
    # Redirect admin users to admin dashboard
    if session.get('user_type') == 'admin':
        return redirect('/admin')
    return render_template('createOrder.html', 
                         user_email=session.get('user_email', ''))

@app.route('/create-quotation')
def create_quotation_page():
    """Display create quotation page (regular users)."""
    if 'user_email' not in session:
        return redirect('/login')
    # Redirect admin users to admin dashboard
    if session.get('user_type') == 'admin':
        return redirect('/admin')
    dockey = request.args.get('dockey', '')
    return render_template('createQuotation.html', 
                         user_email=session.get('user_email', ''),
                         dockey=dockey)

@app.route('/view-quotation')
def view_quotation_page():
    """Display quotation listing page (regular users)."""
    if 'user_email' not in session:
        return redirect('/login')
    if session.get('user_type') == 'admin':
        return redirect('/admin')
    return render_template('viewQuotation.html',
                         user_email=session.get('user_email', ''))


@app.route('/admin/pending-approvals/edit/<int:orderid>')
def admin_edit_approval(orderid):
    """Display admin edit approval page."""
    if 'user_email' not in session:
        return redirect('/login')
    if session.get('user_type') != 'admin':
        return redirect('/chat')
    return render_template('admin_edit_approval.html', user_email=session.get('user_email', ''), orderid=orderid)


@app.route('/admin/api/update-order', methods=['POST'])
def admin_update_order():
    """Admin API endpoint to update order status and order detail rows."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Insufficient permissions'}), 403

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
        return redirect('/chat')
    return redirect('/login')

@app.route('/chat', methods=['GET'])
def chat():
    """Display chat page (requires authentication and must be regular user)"""
    if 'user_email' not in session:
        return redirect('/login')
    # Check if user is admin - if so, redirect to admin dashboard
    if session.get('user_type') == 'admin':
        return redirect('/admin')
    return render_template('chat.html', user_email=session.get('user_email', ''))

@app.route('/chat', methods=['POST'])
def chat_api():
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

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

    messages = []

    # Add business rules/system instructions first
    if CHATBOT_SYSTEM_INSTRUCTIONS.strip():
        messages.append({
            "role": "system",
            "content": CHATBOT_SYSTEM_INSTRUCTIONS.strip()
        })

    # Add stock data context
    stock_context_parts = []
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
                                order_response = f"✓ Added {product_info['qty']}x {product_info['description']} → {total}\n\nWant more items or type 'Complete Order'?"
                            else:
                                order_response = f"Error adding item: {data.get('error')}"
                        except Exception as e:
                            order_response = f"Error adding item: {str(e)}"
                    else:
                        # Product not found - provide suggestions with prices
                        searched_term = product_info['description']
                        suggestions = []
                        
                        # Get top 3 similar products with prices
                        matches = []
                        for item in stockitems:
                            desc = item.get('DESCRIPTION', '')
                            if desc:
                                ratio = SequenceMatcher(None, searched_term.lower(), desc.lower()).ratio()
                                # Look up price for this item
                                price = None
                                for price_item in stockitemprices:
                                    if price_item.get('DESCRIPTION', '').lower() == desc.lower():
                                        price = price_item.get('STOCKVALUE')
                                        break
                                matches.append((desc, ratio, price))
                        
                        matches.sort(key=lambda x: x[1], reverse=True)
                        suggestions = [(m[0], format_rm(m[2])) for m in matches[:3] if m[1] > 0.3 and m[2]]
                        
                        if suggestions:
                            suggestions_text = "\n- ".join([f"{desc} ({price})" for desc, price in suggestions])
                            order_response = f"Select which one:\n- {suggestions_text}"
                        else:
                            order_response = f"Product '{searched_term}' not found in our catalog."
                else:
                    order_response = "Could not understand the product and quantity. Try: 'I want 5 units of Product A'"
            else:
                order_response = "❌ Could not create order automatically. Please say 'Create Order' first."
        
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
                        order_response = f"✓ Order #{orderid} submitted for approval!\nGrand Total: {grand_total}\n\nYour order is now pending admin approval. Type 'Create Order' to start a new order."
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
                            order_response = f"✓ Added {product_info['qty']}x {product_info['description']} → {total}\n\nWant more items or type 'Complete Order'?"
                        else:
                            order_response = f"Error adding item: {data.get('error')}"
                    except Exception as e:
                        order_response = f"Error adding item: {str(e)}"
                else:
                    # Price not found - provide suggestions with verified prices
                    searched_term = product_info['description']
                    suggestions = []
                    
                    # Get top 3 similar products that actually have prices
                    matches = []
                    for item in stockitemprices:
                        desc = item.get('DESCRIPTION', '')
                        price = item.get('STOCKVALUE')
                        if desc and price:  # Only include items with valid prices
                            ratio = SequenceMatcher(None, searched_term.lower(), desc.lower()).ratio()
                            matches.append((desc, ratio, price))
                    
                    matches.sort(key=lambda x: x[1], reverse=True)
                    suggestions = [(m[0], format_rm(m[2])) for m in matches[:3] if m[1] > 0.3]
                    
                    if suggestions:
                        suggestions_text = "\n- ".join([f"{desc} ({price})" for desc, price in suggestions])
                        order_response = f"Select which one:\n- {suggestions_text}"
                    else:
                        order_response = f"Sorry, '{searched_term}' not available."
    
    # If order handling happened, use order response, otherwise use GPT
    if order_response:
        formatted_reply = order_response
    else:
        response = chat_with_gpt(messages)
        formatted_reply = response.strip()
    
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
def get_chats():
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
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
def api_get_active_order():
    """Get active DRAFT order for a chat"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
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
def api_admin_update_order_status():
    """Admin endpoint to update order status (e.g., COMPLETED / CANCELLED)."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

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
def api_insert_chat():
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
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
            "I can help you create orders and manage purchases.\n\n"
            "📦 Type 'Create Order' to start!\n"
            "📋 I'll guide you through the process.\n\n"
            "What would you like to do?"
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
def get_chat_details():
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
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
def check_draft_order():
    """Check if a chat has an active DRAFT order"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
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
def check_user_has_draft():
    """Check if the user has any DRAFT orders across all chats"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
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
def api_get_stock_items():
    """Get stock items for autocomplete in order/quotation forms"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    try:
        stockitems = fetch_data_from_api("stockitem")
        return jsonify({'success': True, 'items': stockitems})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_product_price')
def api_get_product_price():
    """Get product price by description"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    description = request.args.get('description', '').strip()
    if not description:
        return jsonify({'success': False, 'error': 'Description required'}), 400
    
    try:
        # Fetch stock prices from API
        stock_prices = fetch_data_from_api("stockitemprice")
        
        # Look for exact match first
        for price_item in stock_prices:
            price_desc = price_item.get('DESCRIPTION', '')
            price_code = price_item.get('CODE', '')
            
            # Match by DESCRIPTION or CODE (case-insensitive)
            if (description and price_desc.lower() == description.lower()) or \
               (description and price_code.lower() == description.lower()):
                return jsonify({'success': True, 'price': float(price_item.get('STOCKVALUE', 0))})
        
        # Try fuzzy matching if no exact match
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
        
        # If fuzzy match is strong enough (85%+), use it
        if best_match and best_ratio >= 0.85:
            return jsonify({'success': True, 'price': float(best_match.get('STOCKVALUE', 0))})
        
        return jsonify({'success': False, 'error': 'Price not found'}), 404
    except Exception as e:
        print(f"Error getting product price: {e}", flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create_order', methods=['POST'])
def api_create_order():
    """Create a new order from the order form"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
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
def api_create_quotation():
    """Create or update a quotation in the accounting system (SL_QT)"""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
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
def api_get_my_quotations():
    """Get quotations for current logged in user by customer code."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

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
            cancelled_bool = str(cancelled_raw).strip().lower() in ('1', 'true', 't', 'yes', 'y') if cancelled_raw is not None else False
            
            quotations.append({
                'DOCKEY': int(row[0]) if row[0] is not None else None,
                'DOCNO': row[1],
                'DOCDATE': str(row[2]) if row[2] is not None else None,
                'DESCRIPTION': row[3],
                'DOCAMT': float(row[4]) if row[4] is not None else 0,
                'VALIDITY': row[5],
                'STATUS': status_str,
                'CREDITTERM': str(row[7]) if row[7] is not None else 'N/A',
                'CANCELLED': cancelled_bool
            })

        return jsonify({'success': True, 'data': quotations})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_quotation_details')
def api_get_quotation_details():
    """Get quotation details including line items."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

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
def api_admin_get_all_quotations():
    """Get all quotations for admin view with optional status filter."""
    if 'user_email' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    # Check if user is admin
    if session.get('user_type') != 'admin':
        return jsonify({'success': False, 'error': 'Admin access required'}), 403

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

@app.route('/api/get_user_info')
def api_get_user_info():
    """Proxy to PHP getUserInfo.php for customer info."""
    if 'user_email' not in session:
        print("[DEBUG] get_user_info: user_email not in session", flush=True)
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

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