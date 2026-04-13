"""
Quick test script for the FastAPI endpoints.

Usage:
    python tests/test_api.py

Make sure the FastAPI server is running first:
    python -m api.app
"""
import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')
ACCESS_KEY = os.getenv('API_ACCESS_KEY', 'equotation-access-key')
SECRET_KEY = os.getenv('API_SECRET_KEY', 'equotation-secret-key')

# Headers with authentication
HEADERS = {
    'Content-Type': 'application/json',
    'X-Access-Key': ACCESS_KEY,
    'X-Secret-Key': SECRET_KEY
}


def print_response(response, title="Response"):
    """Pretty print API response."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(f"Status Code: {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2))
    except:
        print(response.text)


def test_health():
    """Test health check endpoint."""
    print("\n📋 Testing Health Check Endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    print_response(response, "GET /health")
    assert response.status_code == 200
    print("✅ Health check passed!")


def test_create_customer():
    """Test create customer endpoint."""
    print("\n📋 Testing Create Customer Endpoint...")
    
    customer_data = {
        "code": "TEST123",
        "company_name": "Test Company ABC",
        "credit_term": "30",
        "phone1": "0123456789",
        "email": "test@example.com",
        "address1": "123 Main Street",
        "address2": "Suite 100",
        "postcode": "50000",
        "city": "Kuala Lumpur",
        "state": "Federal Territory",
        "country": "Malaysia"
    }
    
    response = requests.post(
        f"{BASE_URL}/customers",
        json=customer_data,
        headers=HEADERS
    )
    print_response(response, "POST /customers")
    
    if response.status_code == 201:
        print("✅ Customer created successfully!")
        return response.json().get('data', {}).get('customerCode')
    else:
        print("❌ Failed to create customer")
        return None


def test_get_customer(customer_code):
    """Test get customer endpoint."""
    if not customer_code:
        print("\n⚠️  Skipping get customer test (no customer code)")
        return
    
    print(f"\n📋 Testing Get Customer Endpoint...")
    response = requests.get(
        f"{BASE_URL}/customers/{customer_code}",
        headers=HEADERS
    )
    print_response(response, f"GET /customers/{customer_code}")
    
    if response.status_code == 200:
        print("✅ Customer retrieved successfully!")
    else:
        print("⚠️  Customer not found (expected if using placeholder service)")


def test_update_customer(customer_code):
    """Test update customer endpoint."""
    if not customer_code:
        print("\n⚠️  Skipping update customer test (no customer code)")
        return
    
    print(f"\n📋 Testing Update Customer Endpoint...")
    
    updated_data = {
        "companyName": "Updated Test Company",
        "phone1": "0198765432",
        "email": "updated@example.com",
        "address1": "456 New Avenue"
    }
    
    response = requests.put(
        f"{BASE_URL}/customers/{customer_code}",
        json=updated_data,
        headers=HEADERS
    )
    print_response(response, f"PUT /customers/{customer_code}")
    
    if response.status_code == 200:
        print("✅ Customer updated successfully!")
    else:
        print("⚠️  Update test failed")


def test_delete_customer(customer_code):
    """Test delete customer endpoint."""
    if not customer_code:
        print("\n⚠️  Skipping delete customer test (no customer code)")
        return
    
    print(f"\n📋 Testing Delete Customer Endpoint...")
    response = requests.delete(
        f"{BASE_URL}/customers/{customer_code}",
        headers=HEADERS
    )
    print_response(response, f"DELETE /customers/{customer_code}")
    
    if response.status_code == 200:
        print("✅ Customer deleted successfully!")
    else:
        print("⚠️  Delete test failed")


def test_invalid_auth():
    """Test that /customers rejects invalid API keys with 401."""
    print("\n📋 Testing Invalid Authentication on /customers...")
    
    bad_headers = {
        'Content-Type': 'application/json',
        'X-Access-Key': 'wrong-key',
        'X-Secret-Key': 'wrong-secret'
    }
    
    customer_data = {
        "code": "AUTHTEST",
        "company_name": "Auth Test",
        "credit_term": "30"
    }
    
    response = requests.post(
        f"{BASE_URL}/customers",
        json=customer_data,
        headers=bad_headers
    )
    print_response(response, "POST /customers (with invalid credentials)")
    
    if response.status_code == 401:
        print("✅ Authentication validation working correctly!")
    else:
        print("❌ Authentication validation failed")


def test_insert_customer_via_api():
    """Test inserting a customer via the /customers endpoint (remote API)."""
    print("\n📋 Testing Insert Customer via /customers API...")
    customer_data = {
        "code": "TEST789",
        "company_name": "Remote API Insert Test",
        "credit_term": "30",
        "phone1": "0191234567",
        "email": "remoteapitest@example.com",
        "address1": "789 Main Street",
        "address2": "Suite 300",
        "postcode": "70000",
        "city": "Shah Alam",
        "state": "Selangor",
        "country": "Malaysia"
    }
    response = requests.post(f"{BASE_URL}/customers", json=customer_data, headers=HEADERS)
    print_response(response, "POST /customers (remote API)")
    if response.status_code == 201:
        print("✅ Customer inserted via remote API!")
    else:
        print("❌ Failed to insert customer via remote API")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  🚀 FastAPI Integration Tests")
    print("="*60)
    print(f"Base URL: {BASE_URL}")
    
    try:
        # Test health check
        test_health()
        
        # Test authentication
        test_invalid_auth()
        
        # Test CRUD operations
        customer_code = test_create_customer()
        test_get_customer(customer_code)
        test_update_customer(customer_code)
        test_delete_customer(customer_code)
        test_insert_customer_via_api()
        
        print("\n" + "="*60)
        print("  ✅ All tests completed!")
        print("="*60 + "\n")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Could not connect to API server")
        print(f"   Make sure FastAPI is running at {BASE_URL}")
        print("   Run: python -m api.app")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")


if __name__ == "__main__":
    main()
