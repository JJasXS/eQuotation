#!/usr/bin/env python3
"""Test script to verify dashboard API endpoints."""
import requests
import json
import sys

# Configuration
FLASK_BASE_URL = "http://127.0.0.1:5000"
FASTAPI_BASE_URL = "http://127.0.0.1:8000"

def test_fastapi_customers_endpoint():
    """Test FastAPI /local/customers/all endpoint."""
    print("\n" + "="*60)
    print("TEST 1: FastAPI /local/customers/all")
    print("="*60)
    
    url = f"{FASTAPI_BASE_URL}/local/customers/all"
    try:
        response = requests.get(url, timeout=5)
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        if response.status_code == 200 and data.get('success'):
            print("✓ FastAPI endpoint is working correctly")
            customers = data.get('data', [])
            print(f"✓ Retrieved {len(customers)} customers")
            if customers:
                print(f"  Sample: {customers[0]}")
            return True
        else:
            print("✗ FastAPI endpoint returned unexpected response")
            return False
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to FastAPI on port 8000")
        print("  Make sure FastAPI is running: python api/app.py")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_flask_customer_status_endpoint():
    """Test Flask /api/admin/customer_status_summary endpoint."""
    print("\n" + "="*60)
    print("TEST 2: Flask /api/admin/customer_status_summary")
    print("="*60)
    
    url = f"{FLASK_BASE_URL}/api/admin/customer_status_summary"
    try:
        response = requests.get(url, timeout=5)
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        if response.status_code == 200 and data.get('success'):
            print("✓ Flask endpoint is working correctly")
            items = data.get('data', {}).get('items', [])
            print(f"✓ Retrieved {len(items)} status groups")
            if items:
                print(f"  Sample: {items[0]}")
            return True
        else:
            print("✗ Flask endpoint returned unexpected response")
            return False
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to Flask on port 5000")
        print("  Make sure Flask is running: python main.py")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_flask_invoice_aging_endpoint():
    """Test Flask /api/admin/invoice_aging_summary endpoint."""
    print("\n" + "="*60)
    print("TEST 3: Flask /api/admin/invoice_aging_summary")
    print("="*60)
    
    url = f"{FLASK_BASE_URL}/api/admin/invoice_aging_summary"
    try:
        response = requests.get(url, timeout=5)
        print(f"Status: {response.status_code}")
        data = response.json()
        
        if response.status_code == 200 and data.get('success'):
            print("✓ Flask endpoint is working correctly")
            items = data.get('data', {}).get('items', [])
            print(f"✓ Retrieved {len(items)} invoice records")
            if items:
                print(f"  Sample: {items[0]}")
            return True
        else:
            print(f"✗ Error: {data.get('error', 'Unknown error')}")
            print(f"Response: {json.dumps(data, indent=2)}")
            return False
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to Flask on port 5000")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("DASHBOARD API TESTS")
    print("="*60)
    
    results = {
        "FastAPI /local/customers/all": test_fastapi_customers_endpoint(),
        "Flask /api/admin/customer_status_summary": test_flask_customer_status_endpoint(),
        "Flask /api/admin/invoice_aging_summary": test_flask_invoice_aging_endpoint(),
    }
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(results.values())
    print("\n" + ("="*60))
    if all_passed:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed. See above for details.")
    print("="*60 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
