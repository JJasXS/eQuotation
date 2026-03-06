"""Text processing and NLP utility functions."""
import re
import os
from difflib import SequenceMatcher

# Configuration (will be set from main.py)
CREATE_ORDER_KEYWORDS = []
ADD_ORDER_KEYWORDS = []
COMPLETE_ORDER_KEYWORDS = []
REMOVE_ORDER_KEYWORDS = []
PRODUCT_EXTRACTION_KEYWORDS = []
QUANTITY_FILLER_PATTERN = ''
NUMBERED_REFERENCE_PATTERNS = []
ORDINAL_WORD_MAP = {}
MIN_PRODUCT_NAME_LENGTH = 2
MIN_PRODUCT_CODE_LENGTH = 1
PRODUCT_PREFIX_PATTERN = ''
PRODUCT_EXTRACTION_VERBS = []
FUZZY_MATCH_THRESHOLD = 0.75
SUBSTRING_MATCH_BONUS = 0.95


def set_text_config(**kwargs):
    """Set text processing configuration."""
    global CREATE_ORDER_KEYWORDS, ADD_ORDER_KEYWORDS, COMPLETE_ORDER_KEYWORDS
    global REMOVE_ORDER_KEYWORDS, PRODUCT_EXTRACTION_KEYWORDS, QUANTITY_FILLER_PATTERN
    global NUMBERED_REFERENCE_PATTERNS, ORDINAL_WORD_MAP, MIN_PRODUCT_NAME_LENGTH
    global MIN_PRODUCT_CODE_LENGTH, PRODUCT_PREFIX_PATTERN, PRODUCT_EXTRACTION_VERBS
    global FUZZY_MATCH_THRESHOLD, SUBSTRING_MATCH_BONUS
    
    CREATE_ORDER_KEYWORDS = kwargs.get('CREATE_ORDER_KEYWORDS', CREATE_ORDER_KEYWORDS)
    ADD_ORDER_KEYWORDS = kwargs.get('ADD_ORDER_KEYWORDS', ADD_ORDER_KEYWORDS)
    COMPLETE_ORDER_KEYWORDS = kwargs.get('COMPLETE_ORDER_KEYWORDS', COMPLETE_ORDER_KEYWORDS)
    REMOVE_ORDER_KEYWORDS = kwargs.get('REMOVE_ORDER_KEYWORDS', REMOVE_ORDER_KEYWORDS)
    PRODUCT_EXTRACTION_KEYWORDS = kwargs.get('PRODUCT_EXTRACTION_KEYWORDS', PRODUCT_EXTRACTION_KEYWORDS)
    QUANTITY_FILLER_PATTERN = kwargs.get('QUANTITY_FILLER_PATTERN', QUANTITY_FILLER_PATTERN)
    NUMBERED_REFERENCE_PATTERNS = kwargs.get('NUMBERED_REFERENCE_PATTERNS', NUMBERED_REFERENCE_PATTERNS)
    ORDINAL_WORD_MAP = kwargs.get('ORDINAL_WORD_MAP', ORDINAL_WORD_MAP)
    MIN_PRODUCT_NAME_LENGTH = kwargs.get('MIN_PRODUCT_NAME_LENGTH', MIN_PRODUCT_NAME_LENGTH)
    MIN_PRODUCT_CODE_LENGTH = kwargs.get('MIN_PRODUCT_CODE_LENGTH', MIN_PRODUCT_CODE_LENGTH)
    PRODUCT_PREFIX_PATTERN = kwargs.get('PRODUCT_PREFIX_PATTERN', PRODUCT_PREFIX_PATTERN)
    PRODUCT_EXTRACTION_VERBS = kwargs.get('PRODUCT_EXTRACTION_VERBS', PRODUCT_EXTRACTION_VERBS)
    FUZZY_MATCH_THRESHOLD = kwargs.get('FUZZY_MATCH_THRESHOLD', FUZZY_MATCH_THRESHOLD)
    SUBSTRING_MATCH_BONUS = kwargs.get('SUBSTRING_MATCH_BONUS', SUBSTRING_MATCH_BONUS)


_TYPO_MAP_CACHE = None


def load_typo_corrections():
    """Load typo corrections from file (cached)."""
    global _TYPO_MAP_CACHE
    if _TYPO_MAP_CACHE is not None:
        return _TYPO_MAP_CACHE
    
    typo_map = {}
    typo_file = os.path.join(os.path.dirname(__file__), '..', 'training', 'typo_corrections.txt')
    
    try:
        with open(typo_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '->' in line:
                    parts = line.split('->')
                    if len(parts) == 2:
                        typo = parts[0].strip()
                        correct = parts[1].strip()
                        if typo and correct:
                            typo_map[typo] = correct
    except FileNotFoundError:
        print(f"Warning: Typo corrections file not found. Using empty map.")
    except Exception as e:
        print(f"Warning: Error loading typo corrections: {e}. Using empty map.")
    
    _TYPO_MAP_CACHE = typo_map
    return typo_map


def normalize_intent_text(text):
    """Normalize text by fixing typos using external corrections file."""
    typo_map = load_typo_corrections()
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', text.lower())
    tokens = [token for token in cleaned.split() if token]
    normalized_tokens = [typo_map.get(token, token) for token in tokens]
    return ' '.join(normalized_tokens)


def contains_intent_phrase(normalized_input, phrases):
    """Check if any intent phrase is contained in normalized input."""
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


def parse_order_intent(user_input):
    """Detect if user is trying to create/manage order."""
    lower_input = user_input.lower()
    normalized_input = normalize_intent_text(lower_input)

    if 'remove all' in normalized_input or 'clear all' in normalized_input or 'delete all' in normalized_input:
        return 'remove_all'

    if 'update' in normalized_input or 'change' in normalized_input:
        return 'update'

    if contains_intent_phrase(normalized_input, ADD_ORDER_KEYWORDS):
        return 'add'

    if contains_intent_phrase(normalized_input, CREATE_ORDER_KEYWORDS):
        return 'create'
    elif contains_intent_phrase(normalized_input, COMPLETE_ORDER_KEYWORDS):
        return 'complete'
    elif contains_intent_phrase(normalized_input, REMOVE_ORDER_KEYWORDS):
        return 'remove'

    token_set = set(normalized_input.split())
    if token_set.intersection({'create', 'make', 'start', 'begin', 'open'}) and 'order' in token_set:
        return 'create'

    return None
