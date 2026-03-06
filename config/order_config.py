# ORDER MANAGEMENT CONFIGURATION
# Customize these keywords to match your business language

# ============================================
# ORDER ACTION KEYWORDS
# ============================================

# Keywords that trigger ORDER CREATION
CREATE_ORDER_KEYWORDS = [
    'create order',
    'make order',
    'i want to make order',
    'i want to create order',
    'new order',
    'start order',
    'begin order',
    'open order',
    'order please'
]

# Keywords that trigger ORDER COMPLETION
COMPLETE_ORDER_KEYWORDS = [
    'complete order',
    'finish order',
    'done',
    'complete'
]

# Keywords that trigger ITEM REMOVAL
REMOVE_ORDER_KEYWORDS = [
    'remove',
    'delete',
    'clear',
    'cancel item'
]

# Keywords that trigger ITEM ADDITION
ADD_ORDER_KEYWORDS = [
    'add',
    'i want',
    'want to',
    'want',
    'give me',
    'quantity',
    'qty',
    'units of',
    'unit of'
]

# ============================================
# PRODUCT EXTRACTION SETTINGS
# ============================================

# Keywords used to extract product name after them
# Example: "I want to BUY apples" -> extracts "apples"
PRODUCT_EXTRACTION_KEYWORDS = [
    'want',
    'buy',
    'get',
    'purchase',
    'order',
    'need'
]

# Minimum length for product name/code to avoid false matches
# Example: Prevents "I" or "A" from matching as product codes
MIN_PRODUCT_NAME_LENGTH = 3

# Minimum length for product code to match
MIN_PRODUCT_CODE_LENGTH = 3

# ============================================
# QUANTITY FILLER WORDS
# ============================================

# Filler words that appear BEFORE or AFTER a quantity number
# These are automatically removed during product extraction
# Example: "5 units of apples" -> "apples", "give me 5 qty monitors" -> "monitors"
QUANTITY_FILLER_WORDS = [
    'units',
    'unit',
    'pcs',
    'pc',
    'pieces',
    'piece',
    'qty',
    'quantity',
    'of'
]

# Alternative: Regex pattern to match quantity filler words
# This is used in regex substitution for more precise control
QUANTITY_FILLER_PATTERN = r'(units?|pcs?|pieces?|qty|quantity|of)'

# ============================================
# GREETING & HELP MESSAGES
# ============================================

# Welcome message shown when user initiates order-related conversation
WELCOME_MESSAGE = """
Welcome to our ordering system! 🛒

How to use:
1️⃣ Ask about products (e.g., "What furniture do you have?")
2️⃣ Place items (e.g., "I want 5 monitors" or "Add 2 gaming chairs")
3️⃣ Complete order (e.g., "Complete my order")

Feel free to ask about specific items by name or reference by number if you'd like to add them to your order! 🛋️💡
"""

# Enable/disable welcome message display
SHOW_WELCOME_MESSAGE = True

# Help text for first-time users
HELP_MESSAGE = """
💡 **Quick Tips:**
- You can refer to products by name: "I want a gaming chair"
- Or by number from the list: "Add item #2"
- Specify quantity: "Give me 3 premium chairs"
- Ask "What's available?" to see current stock
"""

# ============================================
# PRODUCT EXTRACTION PATTERNS (Regex)
# ============================================

# Patterns for detecting numbered product references (e.g., "number 1", "#2", "the first one")
NUMBERED_REFERENCE_PATTERNS = [
    r'\b(?:number|no\.?|#)\s*(\d+)\b',               # "number 1", "no 2", "#3"
    r'\b(\d+)(?:st|nd|rd|th)?\s+(?:one|item|product|choice)\b',  # "1st item", "2nd product"
    r'\bthe\s+(?:(first|second|third|fourth|fifth))\s+(?:one|item|product|choice)\b'  # "the first item"
]

# Word-to-number mapping for ordinal words
ORDINAL_WORD_MAP = {
    'first': 0,
    'second': 1,
    'third': 2,
    'fourth': 3,
    'fifth': 4
}

# Pattern to remove "to buy", "to order" prefixes
PRODUCT_PREFIX_PATTERN = r'^\s*to\s+'

# ============================================
# FUZZY MATCHING THRESHOLDS
# ============================================

# Minimum confidence threshold for fuzzy matching product names
# Lower = More lenient matching (better for catching keywords like "lighting")
# Higher = More strict matching (fewer false positives)
FUZZY_MATCH_THRESHOLD = 0.50  # 50% match confidence

# Bonus confidence for substring matches (e.g., "lighting" in "Modern Ring Designer 3 Colour LED Pendant Lighting")
SUBSTRING_MATCH_BONUS = 0.95  # Near-perfect confidence for keyword found in product name

# Minimum acceptable fuzzy match ratio for price lookup (stricter than product name matching)
PRICE_MATCH_THRESHOLD = 0.85  # 85% match confidence for finding prices

# List of common verbs to remove after extraction keywords
# Example: "i want to buy monitors" -> extract "monitors" (remove "to" and "buy")
PRODUCT_EXTRACTION_VERBS = [
    'buy',
    'get',
    'purchase',
    'order',
    'sell',
    'pick',
    'choose',
    'add',
    'take'
]

# ============================================
# COMMON FILLER PHRASES
# ============================================

# Filler words/phrases that should be removed from the beginning of user input
# These don't contribute to product extraction
FILLER_PHRASES = [
    'yeah',
    'ok',
    'okay',
    'yes',
    'yep',
    'sure',
    'please',
    'so',
    'well',
    'umm',
    'uhh',
    'uh'
]
