"""Order and product utility functions."""
import re
from difflib import SequenceMatcher
from utils.text_utils import (
    normalize_intent_text,
    QUANTITY_FILLER_PATTERN, PRODUCT_EXTRACTION_KEYWORDS,
    PRODUCT_PREFIX_PATTERN, PRODUCT_EXTRACTION_VERBS,
    MIN_PRODUCT_NAME_LENGTH, MIN_PRODUCT_CODE_LENGTH,
    FUZZY_MATCH_THRESHOLD, SUBSTRING_MATCH_BONUS
)

PRICE_MATCH_THRESHOLD = 0.75


def set_order_config(price_match_threshold=0.75):
    """Set order configuration."""
    global PRICE_MATCH_THRESHOLD
    PRICE_MATCH_THRESHOLD = price_match_threshold


def resolve_numbered_reference(user_input, stock_items):
    """Resolve references like 'number 1', 'the first one', '#2' to actual product names."""
    from utils.text_utils import (
        NUMBERED_REFERENCE_PATTERNS, ORDINAL_WORD_MAP
    )
    
    lower_input = user_input.lower()
    index = None
    
    for pattern in NUMBERED_REFERENCE_PATTERNS:
        match = re.search(pattern, lower_input)
        if match:
            if match.group(1).isdigit():
                index = int(match.group(1)) - 1
            else:
                index = ORDINAL_WORD_MAP.get(match.group(1))
            break
    
    if index is not None and 0 <= index < len(stock_items):
        product = stock_items[index].get('DESCRIPTION')
        print(f"[DEBUG] Numbered reference: Resolved to index {index+1} -> '{product}'", flush=True)
        return product
    
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
    """Extract product name and quantity from user input with fuzzy matching."""
    lower_input = user_input.lower().strip()
    lower_input = re.sub(r'^(yeah|ok|okay|yes|yep|sure|please|so)\s+', '', lower_input, flags=re.IGNORECASE)
    
    # First check if user is referencing a numbered item
    referenced_product = resolve_numbered_reference(lower_input, stock_items)
    if referenced_product:
        qty_match = re.search(r'\b(\d+)\s+(?:units?|pcs?|pieces?)', lower_input)
        qty = int(qty_match.group(1)) if qty_match else 1
        
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
    
    # Extract number from input for quantity
    qty_match = re.search(r'\b(\d+)\b', lower_input)
    qty = int(qty_match.group(1)) if qty_match else 1
    
    # First pass: Exact match for product codes/descriptions
    for item in stock_items:
        item_desc = item.get('DESCRIPTION', '').lower()
        item_code = item.get('CODE', '').lower()
        
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
        product_text = user_input[qty_match.end():].strip()
        product_text = re.sub(fr'^\s*{QUANTITY_FILLER_PATTERN}\s+', '', product_text, flags=re.IGNORECASE)
        product_text = re.sub(fr'\s+{QUANTITY_FILLER_PATTERN}$', '', product_text, flags=re.IGNORECASE)
    else:
        for keyword in PRODUCT_EXTRACTION_KEYWORDS:
            if keyword in lower_input:
                parts = lower_input.split(keyword, 1)
                if len(parts) > 1:
                    product_text = parts[1].strip()
                    product_text = re.sub(PRODUCT_PREFIX_PATTERN, '', product_text, flags=re.IGNORECASE)
                    verbs_pattern = '|'.join(re.escape(verb) for verb in PRODUCT_EXTRACTION_VERBS)
                    product_text = re.sub(fr'^\s*({verbs_pattern})\s+', '', product_text, flags=re.IGNORECASE)
                    product_text = re.sub(fr'^({verbs_pattern})(?=[a-z])', '', product_text, flags=re.IGNORECASE)
                    break
    
    # If no product text but quantity, search chat history
    if (not product_text or len(product_text.strip()) < 2) and qty_match and chat_history:
        print(f"[DEBUG] No product name found, searching chat history...", flush=True)
        for msg in reversed(chat_history[-10:]):
            sender = (msg.get('SENDER') or '').strip().lower()
            text = (msg.get('MESSAGETEXT') or '').strip().lower()
            if sender == 'system':
                for item in stock_items:
                    item_desc = item.get('DESCRIPTION', '').lower()
                    if item_desc in text and len(item_desc) > 5:
                        print(f"[DEBUG] Found product in history: '{item_desc}'", flush=True)
                        return {
                            'description': item.get('DESCRIPTION'),
                            'code': item.get('CODE'),
                            'qty': qty,
                            'matched': True,
                            'from_history': True
                        }
    
    # Validate product_text
    from config.order_config import QUANTITY_FILLER_WORDS
    if not product_text or len(product_text.strip()) < 2 or product_text.strip().lower() in QUANTITY_FILLER_WORDS:
        print(f"[DEBUG] Extracted text too short or only filler: '{product_text}'", flush=True)
        return None
    
    # Fuzzy match extracted text
    product_lower = product_text.lower().strip()
    best_match = None
    best_ratio = 0.0
    
    print(f"[DEBUG] Extracted product text: '{product_lower}'", flush=True)
    
    for item in stock_items:
        item_desc = item.get('DESCRIPTION', '').lower()
        item_code = item.get('CODE', '').lower()
        
        desc_ratio = SequenceMatcher(None, product_lower, item_desc).ratio()
        code_ratio = SequenceMatcher(None, product_lower, item_code).ratio()
        
        if product_lower in item_desc:
           desc_ratio = SUBSTRING_MATCH_BONUS
        
        max_ratio = max(desc_ratio, code_ratio)
        
        if max_ratio > best_ratio:
            best_ratio = max_ratio
            best_match = item
        
        if max_ratio > 0.3:
            print(f"[DEBUG] Match: '{product_lower}' vs '{item_desc}' = {max_ratio:.2%}", flush=True)
    
    if best_match and best_ratio >= FUZZY_MATCH_THRESHOLD:
        print(f"[DEBUG] ✓ Matched: '{product_text}' -> '{best_match.get('DESCRIPTION')}' ({best_ratio:.2%})", flush=True)
        return {
            'description': best_match.get('DESCRIPTION'),
            'code': best_match.get('CODE') or best_match.get('DESCRIPTION'),
            'qty': qty,
            'matched': True,
            'confidence': best_ratio
        }
    
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
    """Get price for a product by matching CODE or DESCRIPTION."""
    description = product_info.get('description', '') if isinstance(product_info, dict) else product_info
    code = product_info.get('code', '') if isinstance(product_info, dict) else ''
    
    print(f"[DEBUG] Looking for price - Description: '{description}', Code: '{code}'", flush=True)
    print(f"[DEBUG] Checking {len(stock_prices)} price items...", flush=True)
    
    for price_item in stock_prices:
        price_desc = price_item.get('DESCRIPTION', '')
        price_code = price_item.get('CODE', '')
        
        if (description and price_desc.lower() == description.lower()) or \
           (code and price_code.lower() == code.lower()):
            print(f"[DEBUG] Found match! Price: {price_item.get('STOCKVALUE', 0)}", flush=True)
            return float(price_item.get('STOCKVALUE', 0))
    
    # Fuzzy matching on description
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
        
        if best_match and best_ratio >= PRICE_MATCH_THRESHOLD:
            print(f"[DEBUG] Fuzzy match found ({best_ratio:.2f}): {best_match.get('DESCRIPTION')} - Price: {best_match.get('STOCKVALUE')}", flush=True)
            return float(best_match.get('STOCKVALUE', 0))
        elif best_match:
            print(f"[DEBUG] Best match only {best_ratio:.2f}: {best_match.get('DESCRIPTION')}", flush=True)
    
    print(f"[DEBUG] No price found for '{description}' (code: '{code}')", flush=True)
    return None
