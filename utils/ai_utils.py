"""AI and chatbot utility functions."""
import os
import openai

# AI configuration (will be set from main.py)
LOCAL_AI_ENABLED = False
OPENAI_API_KEY = None
OPENAI_MODEL = 'gpt-3.5-turbo'
local_intent_classifier = None


def set_ai_config(openai_api_key, openai_model):
    """Set AI configuration."""
    global OPENAI_API_KEY, OPENAI_MODEL
    OPENAI_API_KEY = openai_api_key
    OPENAI_MODEL = openai_model
    openai.api_key = OPENAI_API_KEY


def init_local_classifier(local_ai_enabled):
    """Initialize local intent classifier if enabled."""
    global local_intent_classifier, LOCAL_AI_ENABLED
    LOCAL_AI_ENABLED = local_ai_enabled
    
    if local_ai_enabled:
        try:
            from ai_models import IntentClassifier
            local_intent_classifier = IntentClassifier()
            print(f"✅ Intent classifier initialized: {local_intent_classifier.get_stats()}")
        except Exception as e:
            print(f"⚠️  Could not initialize intent classifier: {e}")
            local_intent_classifier = None


def chat_with_gpt(messages):
    """Send messages to OpenAI ChatGPT and get response."""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages
    )
    return response.choices[0].message.content.strip()


def detect_intent_hybrid(user_input):
    """
    Hybrid intent detection: Try local AI first, fallback to default if needed.
    
    Returns:
        dict: {
            'intent': str,  # 'create_order', 'add_item', etc. or 'unknown'
            'confidence': float,  # 0.0 - 1.0
            'source': str  # 'local' or 'fallback'
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
            print(f"🌐 [FALLBACK] Low confidence ({confidence:.2%}) or unknown intent")
    
    # Fallback: Return unknown intent
    return {
        'intent': 'unknown',
        'confidence': 0.0,
        'source': 'fallback'
    }


def load_chatbot_instructions():
    """Load chatbot instructions from config/chatbot_instructions.txt."""
    instructions_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'chatbot_instructions.txt')
    try:
        with open(instructions_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Warning: {instructions_path} not found. Using default instructions.")
        return "You are a helpful assistant."
    except Exception as e:
        print(f"Error loading instructions: {e}")
        return "You are a helpful assistant."
