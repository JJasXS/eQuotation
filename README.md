# Chatbot Application

WhatsApp-style chatbot with order management system built with Flask and Firebird database.

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and update with your values:
```
DB_HOST=192.168.100.200
DB_PATH=C:\eStream\SQLAccounting\DB\ACC-EQUOTE.FDB
DB_USER=sysdba
DB_PASSWORD=masterkey
BASE_API_URL=http://localhost
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-3.5-turbo
```

### 3. Initialize Database (First Time Only)
Run the database initializer to expand message field sizes:
```bash
python DbInitializer.py
```

This will:
- Expand `CHAT_TPLDTL.MESSAGETEXT` from 255 to 4000 characters
- Expand `CHAT_TPL.LASTMESSAGE` from 255 to 4000 characters

### 4. Start the Application
```bash
python main.py
```

The application will be available at: **http://localhost:5000**

## Order Management Keywords

The chatbot recognizes these exact keywords (customizable in [config/order_config.py](config/order_config.py)):

- **Create Order**: `create order`, `new order`, `start order`, `begin order`
- **Add Items**: `i want`, `add`, `give me` (e.g., "I want 5 apples")
- **Complete Order**: `complete order`, `finish order`, `done`, `complete`
- **Remove Items**: `remove`, `delete`, `clear`, `cancel item`

**To customize keywords:** Edit [config/order_config.py](config/order_config.py) and add your own phrases.

## Project Structure

```
Chatbot/
├── main.py                     # Flask application
├── DbInitializer.py            # Database schema initialization
├── .env                        # Environment variables (not in git)
├── requirements.txt            # Python dependencies
├── config/                     # Configuration files
│   ├── order_config.py         # Order keywords & filters (customizable)
│   ├── chatbot_instructions.txt # GPT system prompt
│   └── endpoints_config.py     # API endpoint paths
├── php/                        # PHP API endpoints
│   ├── db_helper.php
│   ├── insertOrder.php
│   ├── insertOrderDetail.php
│   ├── completeOrder.php
│   └── ...
├── templates/                  # HTML templates
│   ├── chat.html
│   └── pages/
│       └── userApproval.html
└── static/                     # CSS/JS assets
    ├── css/
    │   ├── chat.css
    │   └── hamburger_menu.css
    └── js/
        ├── chat.js
        └── hamburger_menu.js
```

## Features

- WhatsApp-style dark theme UI
- OpenAI GPT-3.5 integration
- Order management system (ORDER_TPL, ORDER_TPLDTL)
- Product catalog with pricing
- Conversational order creation
- Multi-chat support
- Hamburger menu navigation
- Approvals page (Pending/Completed/Cancelled tabs)

## Database Tables

- **CHAT_TPL**: Chat sessions
- **CHAT_TPLDTL**: Chat messages
- **ORDER_TPL**: Order headers (DRAFT/PENDING/COMPLETED/CANCELLED status)
- **ORDER_TPLDTL**: Order line items
- **STOCKITEM**: Product catalog
- **STOCKVALUE**: Product pricing
