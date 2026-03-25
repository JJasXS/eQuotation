# 🚀 FastAPI Integration - Quick Start Guide

This guide helps you get the new FastAPI REST API layer up and running in 5 minutes.

## What Was Added?

✅ **FastAPI application** with clean REST API endpoints  
✅ **Pydantic models** for request/response validation  
✅ **API key authentication** using X-Access-Key and X-Secret-Key headers  
✅ **Modular architecture** ready for SQL Account integration  
✅ **Interactive API documentation** at `/api/docs`  
✅ **Postman collection** for easy testing  

## Prerequisites

- Python 3.8+
- Your existing eQuotation project
- FastAPI, uvicorn, and pydantic (will install via pip)

## Installation (60 seconds)

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

This installs:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `pydantic` - Data validation

### Step 2: Update .env File

Add these lines to your `.env` file:

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true

# API Authentication (CHANGE IN PRODUCTION!)
API_ACCESS_KEY=dev-access-key-change-this
API_SECRET_KEY=dev-secret-key-change-this

# CORS
CORS_ORIGINS=http://localhost,http://localhost:3000,http://localhost:5000
```

Or append the example file:
```bash
cat .env.example.api >> .env
```

## Running the API

### Quick Start (Single Command)
```bash
python -m api.app
```

You should see:
```
Starting eQuotation API on 0.0.0.0:8000
API docs available at http://localhost:8000/api/docs
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Alternative: Using uvicorn directly
```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Run with Existing Flask App
```bash
# Terminal 1 - Flask (port 5000)
python main.py

# Terminal 2 - FastAPI (port 8000)
python -m api.app
```

## Testing the API

### Option 1: Interactive Documentation ⭐ RECOMMENDED
Open your browser and visit:
```
http://localhost:8000/api/docs
```

This gives you an interactive Swagger UI where you can:
- See all endpoints
- Try requests directly in the browser
- View request/response examples

### Option 2: Using curl

**Health Check:**
```bash
curl http://localhost:8000/api/health
```

**Create Customer:**
```bash
curl -X POST http://localhost:8000/api/customers \
  -H "X-Access-Key: dev-access-key-change-this" \
  -H "X-Secret-Key: dev-secret-key-change-this" \
  -H "Content-Type: application/json" \
  -d '{
    "companyName": "Test Company",
    "phone1": "0123456789",
    "email": "test@example.com",
    "address1": "123 Main Street"
  }'
```

### Option 3: Using Python Script
```bash
python tests/test_api.py
```

This runs automated tests for all endpoints.

### Option 4: Using Postman

1. Open Postman
2. Import the collection: `docs/eQuotation_API.postman_collection.json`
3. Set variables:
   - `base_url`: `http://localhost:8000`
   - `api_access_key`: `dev-access-key-change-this`
   - `api_secret_key`: `dev-secret-key-change-this`
4. Test endpoints from the collection

## API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/` | API info |
| POST | `/api/customers` | Create customer |
| GET | `/api/customers/{code}` | Get customer |
| PUT | `/api/customers/{code}` | Update customer |
| DELETE | `/api/customers/{code}` | Delete customer |

## Example Requests & Responses

### Create Customer

**Request:**
```bash
POST http://localhost:8000/api/customers
Headers:
  X-Access-Key: dev-access-key-change-this
  X-Secret-Key: dev-secret-key-change-this
  Content-Type: application/json

Body:
{
  "companyName": "Acme Corp",
  "phone1": "0123456789",
  "email": "contact@acme.com",
  "address1": "123 Main Street",
  "postcode": "50000",
  "city": "Kuala Lumpur"
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "message": "Customer created successfully",
  "data": {
    "customerCode": "300-E0001",
    "companyName": "Acme Corp",
    "phone1": "0123456789",
    "email": "contact@acme.com",
    "address1": "123 Main Street",
    "postcode": "50000",
    "city": "Kuala Lumpur"
  }
}
```

## File Structure

```
api/                          ← NEW
├── app.py                     ← Main FastAPI app (entry point)
├── routes/
│   ├── health.py             ← Health check endpoints
│   └── customers.py          ← Customer endpoints
├── models/
│   ├── response.py           ← Standard response format
│   └── customer.py           ← Customer request/response models
├── services/
│   └── __init__.py           ← Business logic (CustomerService)
├── adapters/
│   └── __init__.py           ← SQL Account adapter (placeholder)
└── auth/
    └── __init__.py           ← API key authentication

docs/
├── FASTAPI_SETUP.md          ← Detailed documentation
└── eQuotation_API.postman_collection.json  ← Postman collection

tests/
└── test_api.py               ← Automated tests
```

## Next Steps

1. **Test the API** - Use the Swagger UI at `/api/docs`
2. **Integrate with SQL Account** - Fill in adapter methods
3. **Add More Endpoints** - Create routes for orders, quotations, etc.
4. **Deploy to Production** - Configure security and HTTPS
5. **Add Tests** - Write unit tests for your services

## Common Issues

### ❌ "Port 8000 is already in use"
Change port in .env:
```env
API_PORT=8001
```

### ❌ "Invalid API credentials"
Check headers match .env values:
- `X-Access-Key` 
- `X-Secret-Key`

### ❌ "Module not found"
Install dependencies:
```bash
pip install -r requirements.txt
```

### ❌ "CORS error in browser"
Add your frontend URL to CORS_ORIGINS in .env:
```env
CORS_ORIGINS=http://localhost,http://localhost:3000
```

## Documentation

For detailed documentation, see [FASTAPI_SETUP.md](./FASTAPI_SETUP.md)

## Security Notes ⚠️

The current API key implementation is for **development only**. For production:

1. ✅ Change API keys in .env
2. ✅ Use HTTPS instead of HTTP
3. ✅ Consider OAuth2 or JWT authentication
4. ✅ Add rate limiting
5. ✅ Add request logging and monitoring
6. ✅ Use environment variables for secrets
7. ✅ Implement proper CORS policies

## Support

- **API Docs**: http://localhost:8000/api/docs
- **Detailed Guide**: See `docs/FASTAPI_SETUP.md`
- **Test Script**: Run `python tests/test_api.py`
- **Postman Collection**: Import `docs/eQuotation_API.postman_collection.json`

---

**Ready?** Start the API with:
```bash
python -m api.app
```

Then visit http://localhost:8000/api/docs to explore! 🎉
