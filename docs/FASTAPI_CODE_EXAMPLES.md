# FastAPI Code Examples & Patterns

This document provides copy/paste examples for common FastAPI tasks.

## Table of Contents
1. [Adding Endpoints](#adding-endpoints)
2. [Creating Models](#creating-models)
3. [Error Handling](#error-handling)
4. [Authentication](#authentication)
5. [SQL Account Integration](#sql-account-integration)
6. [Testing](#testing)

---

## Adding Endpoints

### Example 1: Simple GET Endpoint

```python
# api/routes/inventory.py
from fastapi import APIRouter
from api.models import APIResponse

router = APIRouter(prefix="/inventory", tags=["Inventory"])

@router.get("/items", response_model=APIResponse)
async def list_items():
    """Get all inventory items."""
    items = [
        {"id": 1, "name": "Item 1", "qty": 100},
        {"id": 2, "name": "Item 2", "qty": 50}
    ]
    return APIResponse(
        success=True,
        message="Items retrieved successfully",
        data={"items": items}
    )
```

Add to `api/app.py`:
```python
from api.routes import inventory
app.include_router(inventory.router, prefix="/api")
```

### Example 2: POST Endpoint with Body Validation

```python
# api/routes/orders.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from api.models import APIResponse
from api.auth import validate_api_key

router = APIRouter(prefix="/orders", tags=["Orders"])

class OrderRequest(BaseModel):
    customer_code: str
    items: list
    total_amount: float

@router.post("/create", response_model=APIResponse)
async def create_order(
    order_data: OrderRequest,
    credentials: dict = Depends(validate_api_key)
):
    """Create a new order."""
    try:
        # Your business logic here
        return APIResponse(
            success=True,
            message="Order created successfully",
            data={"orderId": "ORD-001"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Example 3: GET with Path Parameter

```python
@router.get("/orders/{order_id}", response_model=APIResponse)
async def get_order(
    order_id: str,
    credentials: dict = Depends(validate_api_key)
):
    """Get order by ID."""
    order = {"orderId": order_id, "status": "pending"}
    return APIResponse(
        success=True,
        message="Order found",
        data=order
    )
```

### Example 4: Query Parameters

```python
@router.get("/orders/search", response_model=APIResponse)
async def search_orders(
    status: str = None,
    limit: int = 10,
    credentials: dict = Depends(validate_api_key)
):
    """Search orders with filters."""
    filters = {}
    if status:
        filters['status'] = status
    
    return APIResponse(
        success=True,
        message="Orders found",
        data={"count": 5, "filters": filters}
    )
```

---

## Creating Models

### Example 1: Request Model

```python
# api/models/order.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class OrderItemRequest(BaseModel):
    product_code: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    unit_price: float = Field(..., gt=0)

class OrderRequest(BaseModel):
    customer_code: str = Field(..., description="Customer code")
    items: list[OrderItemRequest] = Field(..., min_items=1)
    delivery_date: Optional[str] = None
    notes: Optional[str] = None

class Config:
    example = {
        "customer_code": "300-E0001",
        "items": [
            {"product_code": "ABC123", "quantity": 5, "unit_price": 100}
        ]
    }
```

### Example 2: Response Model

```python
from datetime import datetime
from typing import List

class OrderItemResponse(BaseModel):
    product_code: str
    quantity: int
    unit_price: float
    subtotal: float

class OrderResponse(BaseModel):
    order_id: str
    customer_code: str
    status: str
    items: List[OrderItemResponse]
    total_amount: float
    created_at: datetime
    updated_at: Optional[datetime] = None
```

### Example 3: Reusable Models

```python
# Create base models that extend from BaseModel
from pydantic import BaseModel

class BaseResponse(BaseModel):
    """Base response model."""
    id: str
    created_at: str
    updated_at: str

class ProductResponse(BaseResponse):
    name: str
    code: str
    price: float
    quantity: int
```

---

## Error Handling

### Example 1: Custom Error Response

```python
from fastapi import HTTPException

# Return 404 Not Found
if not customer:
    raise HTTPException(
        status_code=404,
        detail="Customer not found"
    )

# Return 400 Bad Request
if not data.validate():
    raise HTTPException(
        status_code=400,
        detail="Invalid input data"
    )

# Return 500 Internal Error
try:
    result = external_api_call()
except Exception as e:
    raise HTTPException(
        status_code=500,
        detail=f"External service error: {str(e)}"
    )
```

### Example 2: Try-Catch Pattern

```python
from fastapi import APIRouter, HTTPException

@router.post("/process", response_model=APIResponse)
async def process_data(data: Request):
    try:
        # Your logic
        result = complex_operation(data)
        return APIResponse(
            success=True,
            message="Operation completed",
            data=result
        )
    
    except ValueError as e:
        # Validation error
        raise HTTPException(status_code=400, detail=str(e))
    
    except KeyError as e:
        # Missing required field
        raise HTTPException(
            status_code=400, 
            detail=f"Missing field: {str(e)}"
        )
    
    except Exception as e:
        # Unexpected error
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
```

### Example 3: Error Response Model

```python
from typing import Optional, List
from pydantic import BaseModel

class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    errors: Optional[List[str]] = None

# Usage
raise HTTPException(
    status_code=422,
    detail="Validation failed"
)
```

---

## Authentication

### Example 1: Custom API Key Auth

```python
# api/auth/__init__.py
from fastapi import HTTPException, Header
from typing import Optional

def verify_api_key(
    x_api_key: Optional[str] = Header(None)
) -> dict:
    """Custom API key authentication."""
    import os
    
    valid_keys = os.getenv('API_KEYS', '').split(',')
    
    if not x_api_key or x_api_key not in valid_keys:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return {"api_key": x_api_key}

# Usage in endpoint
@router.get("/protected")
async def protected_route(auth: dict = Depends(verify_api_key)):
    return {"message": "You are authenticated"}
```

### Example 2: Bearer Token Auth

```python
from fastapi import HTTPException, Header
from typing import Optional

def verify_bearer_token(
    authorization: Optional[str] = Header(None)
) -> dict:
    """Verify JWT bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid token"
        )
    
    token = authorization.split(" ")[1]
    
    # Verify token (example only)
    if not is_valid_jwt(token):
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )
    
    return {"token": token}

# Usage
@router.get("/protected")
async def route(auth: dict = Depends(verify_bearer_token)):
    return {"authenticated": True}
```

---

## SQL Account Integration

### Example 1: Implement Adapter for Orders

```python
# api/adapters/__init__ (add to existing SQLAccountAdapter)
import requests
from typing import Dict, Any

class SQLAccountAdapter:
    def create_order(self, order_data: Dict) -> Dict:
        """Create order via PHP endpoint."""
        response = requests.post(
            f"{self.base_url}/php/insertOrder.php",
            json=order_data,
            timeout=10
        )
        result = response.json()
        
        if not result.get('success'):
            raise Exception(f"Failed to create order: {result.get('error')}")
        
        return result
    
    def get_order(self, order_id: str) -> Dict:
        """Get order details."""
        response = requests.get(
            f"{self.base_url}/php/getOrderDetails.php",
            params={'dockey': order_id},
            timeout=10
        )
        return response.json()
```

### Example 2: Service Layer for Orders

```python
# api/services/__init__ (add to existing file)
class OrderService:
    def __init__(self, adapter=None):
        from api.adapters import SQLAccountAdapter
        self.adapter = adapter or SQLAccountAdapter()
    
    def create_order(self, order_request):
        """Create order with validation."""
        # Validate
        if not order_request.customer_code:
            raise ValueError("Customer code required")
        
        if not order_request.items:
            raise ValueError("Order must have items")
        
        # Call adapter
        data = order_request.dict()
        result = self.adapter.create_order(data)
        
        return result
```

### Example 3: Route for Orders

```python
# api/routes/orders.py
from fastapi import APIRouter, Depends
from api.auth import validate_api_key
from api.models import APIResponse
from api.services import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])
order_service = OrderService()

@router.post("", response_model=APIResponse)
async def create_order(
    order_data: dict,
    credentials: dict = Depends(validate_api_key)
):
    """Create new order."""
    try:
        result = order_service.create_order(order_data)
        return APIResponse(
            success=True,
            message="Order created",
            data=result
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

---

## Testing

### Example 1: Test Endpoint

```python
# tests/test_customers.py
import pytest
from fastapi.testclient import TestClient
from api.app import app

client = TestClient(app)

@pytest.fixture
def auth_headers():
    return {
        "X-Access-Key": "test-key",
        "X-Secret-Key": "test-secret"
    }

def test_create_customer(auth_headers):
    response = client.post(
        "/api/customers",
        json={
            "companyName": "Test Corp",
            "phone1": "0123456789",
            "email": "test@example.com",
            "address1": "123 Test St"
        },
        headers=auth_headers
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["success"] == True
    assert "customerCode" in data["data"]
```

### Example 2: Test Error Handling

```python
def test_missing_required_field():
    response = client.post(
        "/api/customers",
        json={
            "companyName": "Test Corp"
            # Missing required fields
        },
        headers=auth_headers
    )
    
    assert response.status_code == 422  # Validation error

def test_invalid_auth():
    response = client.post(
        "/api/customers",
        json={"companyName": "Test Corp"},
        headers={"X-Access-Key": "wrong"}
    )
    
    assert response.status_code == 401
```

### Example 3: Test Helper Functions

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from api.app import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def valid_headers():
    return {
        "X-Access-Key": "test-key",
        "X-Secret-Key": "test-secret"
    }

@pytest.fixture
def sample_customer():
    return {
        "companyName": "Test Company",
        "phone1": "0123456789",
        "email": "test@example.com",
        "address1": "123 Main Street"
    }
```

---

## Advanced Patterns

### Example 1: Dependency Injection

```python
from typing import Callable
from fastapi import Depends

class DatabaseService:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
    
    def query(self, sql: str):
        # Execute query
        pass

def get_db_service() -> DatabaseService:
    return DatabaseService("firebird://...")

@router.get("/reports")
async def get_reports(db: DatabaseService = Depends(get_db_service)):
    results = db.query("SELECT * FROM reports")
    return APIResponse(success=True, data=results)
```

### Example 2: Background Tasks

```python
from fastapi import BackgroundTasks

@router.post("/process", response_model=APIResponse)
async def process_data(
    data: dict,
    background_tasks: BackgroundTasks,
    credentials: dict = Depends(validate_api_key)
):
    """Process data and send email in background."""
    
    # Process immediately
    result = process_order(data)
    
    # Send email in background
    background_tasks.add_task(send_email, result['id'])
    
    return APIResponse(
        success=True,
        message="Processing started",
        data={"id": result['id']}
    )

def send_email(order_id: str):
    # This runs in background
    pass
```

### Example 3: Middleware

```python
from fastapi.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import time

@app.middleware("http")
async def add_process_time_header(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response
```

---

Happy coding! 🚀
