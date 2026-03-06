# Chatbot Application

Flask-based chatbot with OpenAI integration and Firebird database support.

## Quick Start

**Windows:**
```
run_chatbot.bat
```

The launcher will automatically:
- Find Python installation
- Install missing dependencies
- Start the server at http://localhost:5000

## Manual Setup

If you need to install dependencies separately:
```bash
python -m pip install -r requirements.txt
python main.py
```

## Requirements

- Python 3.12+ 
- Internet connection (for OpenAI API)
- Firebird database (optional, for chat history features)

## Configuration

Edit `main.py` to configure:
- OpenAI API key
- Firebird database path and credentials
- API endpoints

## Features

- Chat interface at `/`
- Stock item lookup from PHP endpoints
- Chat history storage (Firebird DB)
- OpenAI GPT-3.5 integration
