"""AI and chatbot utility functions."""
import os
import openai

# AI configuration (will be set from main.py via set_ai_config)
OPENAI_API_KEY = None
OPENAI_MODEL = 'gpt-3.5-turbo'


def set_ai_config(openai_api_key, openai_model):
    """Set AI configuration."""
    global OPENAI_API_KEY, OPENAI_MODEL
    OPENAI_API_KEY = openai_api_key
    OPENAI_MODEL = openai_model
    openai.api_key = OPENAI_API_KEY


def chat_with_gpt(messages):
    """Send messages to OpenAI ChatGPT and get response."""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages
    )
    return response.choices[0].message.content.strip()


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
