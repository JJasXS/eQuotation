"""Utility modules for Chatbot application."""

from utils.db_utils import (
    get_db_connection, user_owns_chat, get_chat_history,
    update_chat_last_message, get_active_order, test_firebird_connection,
    set_db_config
)

from utils.api_utils import (
    fetch_data_from_api, format_rm
, set_api_config
)

from utils.text_utils import (
    load_typo_corrections, normalize_intent_text, contains_intent_phrase,
    parse_order_intent, set_text_config
)

from utils.email_utils import (
    send_email, set_email_config
)

from utils.ai_utils import (
    chat_with_gpt, detect_intent_hybrid, load_chatbot_instructions,
    set_ai_config, init_local_classifier
)

from utils.order_utils import (
    extract_product_and_quantity, get_product_price, set_order_config,
    resolve_numbered_reference
)

__all__ = [
    # DB utils
    'get_db_connection', 'user_owns_chat', 'get_chat_history',
    'update_chat_last_message', 'get_active_order', 'test_firebird_connection',
    'set_db_config',
    
    # API utils
    'fetch_data_from_api', 'format_rm', 'set_api_config',
    
    # Text utils
    'load_typo_corrections', 'normalize_intent_text', 'contains_intent_phrase',
    'parse_order_intent', 'set_text_config',
    
    # Email utils
    'send_email', 'set_email_config',
    
    # AI utils
    'chat_with_gpt', 'detect_intent_hybrid', 'load_chatbot_instructions',
    'set_ai_config', 'init_local_classifier',
    
    # Order utils
    'extract_product_and_quantity', 'get_product_price', 'set_order_config',
    'resolve_numbered_reference'
]
