# FastAPI REST API Layer Documentation

## Overview

This document explains the new **FastAPI REST API layer** that has been added to your eQuotation project. This layer provides a clean, modern REST API interface alongside your existing Flask application.

## Architecture

```
api/
├── app.py                          # Main FastAPI application
├── routes/
│   ├── health.py                   # Health check endpoints
│   └── customers.py                # Customer management endpoints
├── models/
│   ├── response.py                 # Standard API response format
│   └── customer.py                 # Customer request/response models
├── services/
│   └── __init__.py                 # Business logic (CustomerService)
├── adapters/
│   └── __init__.py                 # SQL Account integration adapter
└── auth/
    └── __init__.py                 # API key authentication
```

## Setup Instructions

### 1. Install Dependencies

```bash
# If using venv
python -m pip install -r requirements.txt
```

The following packages were added:
- `fastapi==0.104.1` - Web framework
- `uvicorn[standard]==0.24.0` - ASGI server
- `pydantic==2.4.2` - Data validation

### 2. Configure Environment Variables

Edit your `.env` file and add the FastAPI configuration:

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true

# API Authentication Keys (CHANGE THESE IN PRODUCTION!)
API_ACCESS_KEY=your-secure-access-key
API_SECRET_KEY=your-secure-secret-key

# CORS Configuration
CORS_ORIGINS=http://localhost,http://localhost:3000,http://localhost:5000
```

Or copy the example file:
```bash
cat .env.example.api >> .env
```

### 3. Run the FastAPI Server

#### Option A: Using Python directly
```bash
python -m api.app
```

#### Option B: Using uvicorn directly
```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

#### Option C: Run alongside Flask
```bash
# Terminal 1 - Run Flask (port 5000)
python main.py

# Terminal 2 - Run FastAPI (port 8000)
python -m api.app
```

You should see output like:
```
Starting eQuotation API on 0.0.0.0:8000
API docs available at http://localhost:8000/api/docs
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## API Endpoints

### 1. Health Check

**GET** `/api/health`

Returns API status.

```bash
curl http://localhost:8000/api/health
```

Response:
```json
{
  "success": true,
  "message": "API is healthy",
  "data": {
    "status": "healthy",
    "version": "1.0.0"
  }
}
```

### 2. Create Customer

**POST** `/api/customers`

Create a new customer.

**Required Headers:**
- `X-Access-Key: your-access-key`
- `X-Secret-Key: your-secret-key`

**Request Body:**
```json
{
  "companyCode": "300-000",
  "companyName": "Acme Corporation",
  "phone1": "0123456789",
  "email": "contact@acme.com",
  "address1": "123 Main Street",
  "address2": "Suite 100",
  "postcode": "50000",
  "city": "Kuala Lumpur",
  "state": "Federal Territory",
  "country": "Malaysia"
}
```

**Example with curl:**
```bash
curl -X POST http://localhost:8000/api/customers \
  -H "X-Access-Key: your-access-key" \
  -H "X-Secret-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "companyName": "Acme Corp",
    "phone1": "0123456789",
    "email": "contact@acme.com",
    "address1": "123 Main St"
  }'
```

Response:
```json
{
  "success": true,
  "message": "Customer created successfully",
  "data": {
    "customerCode": "300-E0001",
    "companyName": "Acme Corporation",
    "phone1": "0123456789",
    "email": "contact@acme.com",
    "address1": "123 Main Street",
    ...
  }
}
```

### 3. Get Customer

**GET** `/api/customers/{customer_code}`

Retrieve customer details.

**Required Headers:**
- `X-Access-Key: your-access-key`
- `X-Secret-Key: your-secret-key`

**Example:**
```bash
curl http://localhost:8000/api/customers/300-E0001 \
  -H "X-Access-Key: your-access-key" \
  -H "X-Secret-Key: your-secret-key"
```

### 4. Update Customer

**PUT** `/api/customers/{customer_code}`

Update an existing customer.

**Required Headers:**
- `X-Access-Key: your-access-key`
- `X-Secret-Key: your-secret-key`

**Example:**
```bash
curl -X PUT http://localhost:8000/api/customers/300-E0001 \
  -H "X-Access-Key: your-access-key" \
  -H "X-Secret-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "companyName": "Updated Corp Name",
    "phone1": "0198765432",
    "email": "newemail@acme.com",
    "address1": "456 New Street"
  }'
```

### 5. Delete Customer

**DELETE** `/api/customers/{customer_code}`

Delete a customer.

**Required Headers:**
- `X-Access-Key: your-access-key`
- `X-Secret-Key: your-secret-key`

**Example:**
```bash
curl -X DELETE http://localhost:8000/api/customers/300-E0001 \
  -H "X-Access-Key: your-access-key" \
  -H "X-Secret-Key: your-secret-key"
```

## Testing with Postman

1. **Import the API** into Postman
2. **Set up Authentication:**
   - Go to the collection or request
   - Headers tab
   - Add `X-Access-Key: your-access-key`
   - Add `X-Secret-Key: your-secret-key`

3. **Test endpoints** using the examples above

## Interactive API Documentation

Once the FastAPI server is running, you can access:

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **OpenAPI Schema**: http://localhost:8000/api/openapi.json

## Standard Response Format

All API responses follow this format:

```json
{
  "success": true|false,
  "message": "Human-readable message",
  "data": { /* response data */ },
  "errors": [ /* error details if applicable */ ]
}
```

## Error Handling

### 401 Unauthorized
```json
{
  "detail": "Invalid API credentials"
}
```

### 400 Bad Request
```json
{
  "detail": "Company name is required"
}
```

### 404 Not Found
```json
{
  "detail": "Customer 300-E0001 not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Failed to create customer: [error details]"
}
```

## Code Structure

### Models (`api/models/`)
- **response.py**: `APIResponse` - Standard API response wrapper
- **customer.py**: `CustomerRequest`, `CustomerResponse` - Pydantic models for validation

### Services (`api/services/`)
- **CustomerService**: Business logic for customer operations
  - `create_customer()` - Validate and create customer
  - `get_customer()` - Retrieve customer by code
  - `update_customer()` - Update customer data
  - `delete_customer()` - Delete customer

### Adapters (`api/adapters/`)
- **SQLAccountAdapter**: Interface to SQL Account ERP
  - Currently placeholder methods
  - Ready for integration with `/php/` endpoints
  - Methods: `create_customer()`, `get_customer()`, `update_customer()`, `delete_customer()`

### Routes (`api/routes/`)
- **health.py**: Health check endpoints
- **customers.py**: Customer management endpoints

### Auth (`api/auth/`)
- **validate_api_key()**: Dependency injection for API key validation
- Validates `X-Access-Key` and `X-Secret-Key` headers

## Extending the API

### Adding a New Endpoint

1. Create new route file in `api/routes/`:
   ```python
   from fastapi import APIRouter
   from api.models import APIResponse
   
   router = APIRouter(prefix="/items", tags=["Items"])
   
   @router.get("", response_model=APIResponse)
   async def list_items():
       return APIResponse(success=True, message="Items", data=[])
   ```

2. Include router in `api/app.py`:
   ```python
   from api.routes import items
   app.include_router(items.router, prefix="/api")
   ```

### Integrating with SQL Account

The `SQLAccountAdapter` is ready for integration. To implement:

1. Edit `api/adapters/__init__.py`
2. Replace `NotImplementedError` stubs with actual API calls
3. Use existing `requests` library to call `/php/` endpoints
4. Map responses to `CustomerResponse` models

Example:
```python
def create_customer(self, customer_data: Dict[str, Any]) -> Dict[str, Any]:
    import requests
    response = requests.post(
        f"{self.base_url}/php/createSignInUser.php",
        json=customer_data,
        timeout=10
    )
    return response.json()
```

## Security Considerations

⚠️ **IMPORTANT:**

1. **API Keys in Environment**
   - Store API keys in `.env` file (not in code)
   - Never commit `.env` to version control
   - Rotate keys regularly in production

2. **HTTPS in Production**
   - Always use HTTPS for production APIs
   - Configure proper SSL certificates

3. **Better Authentication**
   - Consider upgrading to OAuth2 or JWT
   - Use FastAPI's `OAuth2PasswordBearer` for better security
   - Never store plaintext secrets

4. **CORS**
   - Restrict CORS origins to trusted domains
   - Use `CORS_ORIGINS` environment variable

5. **Rate Limiting**
   - Consider adding rate limiting middleware for production
   - Use packages like `slowapi` or `fastapi-limiter`

## Troubleshooting

### Port Already in Use
```bash
# Change port in .env or command line
uvicorn api.app:app --port 8001
```

### Import Errors
```bash
# Ensure all dependencies are installed
pip install -r requirements.txt

# Or reinstall FastAPI packages
pip install fastapi uvicorn pydantic
```

### Authentication Failures
- Check that `X-Access-Key` and `X-Secret-Key` headers are provided
- Verify they match values in `.env` file
- Headers are case-sensitive

### CORS Issues
- Update `CORS_ORIGINS` in `.env` to include your frontend URL
- Separate multiple origins with commas: `http://localhost,http://localhost:3000`

## Next Steps

1. **Implement SQL Account Integration**
   - Fill in `SQLAccountAdapter` methods
   - Test with actual PHP endpoints

2. **Add More Endpoints**
   - Orders management
   - Quotations management
   - Chat management

3. **Add Authentication**
   - Consider OAuth2/JWT instead of simple API keys
   - Implement role-based access control

4. **Add Database Models**
   - Create ORM models for your Firebird database
   - Use SQLAlchemy or similar for type safety

5. **Write Tests**
   - Add unit tests for services
   - Add integration tests for endpoints
   - Use pytest or similar

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Uvicorn Documentation](https://www.uvicorn.org/)
- [REST API Best Practices](https://restfulapi.net/)
