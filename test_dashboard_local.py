#!/usr/bin/env python3
"""Test script to verify dashboard endpoints work without FastAPI."""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import app
import json

def test_customer_status_endpoint():
    """Test the customer status endpoint with Flask test client."""
    print("\n" + "="*60)
    print("TEST: Customer Status Endpoint (With Flask Session)")
    print("="*60)
    
    client = app.test_client()
    
    # Create a test session with admin user
    with client.session_transaction() as sess:
        sess['user_email'] = 'test@admin.com'
        sess['user_type'] = 'admin'
    
    try:
        response = client.get('/api/admin/customer_status_summary')
        print(f"Status: {response.status_code}")
        data = response.json
        print(f"Response: {json.dumps(data, indent=2)}")
        
        if response.status_code == 200 and data.get('success'):
            print("✓ Endpoint returned success")
            items = data.get('data', {}).get('items', [])
            print(f"✓ Retrieved {len(items)} status groups")
            if items:
                print(f"  Groups: {[item['label'] for item in items]}")
                print(f"  Counts: {[item['count'] for item in items]}")
            return True
        else:
            print(f"✗ Endpoint returned error: {data.get('error')}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_invoice_aging_endpoint():
    """Test the invoice aging endpoint with Flask test client."""
    print("\n" + "="*60)
    print("TEST: Invoice Aging Endpoint (With Flask Session)")
    print("="*60)
    
    client = app.test_client()
    
    # Create a test session with admin user
    with client.session_transaction() as sess:
        sess['user_email'] = 'test@admin.com'
        sess['user_type'] = 'admin'
    
    try:
        response = client.get('/api/admin/invoice_aging_summary')
        print(f"Status: {response.status_code}")
        data = response.json
        
        if response.status_code == 200 and data.get('success'):
            print("✓ Endpoint returned success")
            items = data.get('data', {}).get('items', [])
            total = data.get('data', {}).get('total_codes', 0)
            print(f"✓ Retrieved {total} customer records")
            if items:
                print(f"  Sample records:")
                for item in items[:3]:
                    print(f"    - {item['company_name']}: {item['days_ago_label']}")
            return True
        else:
            print(f"✗ Endpoint returned error: {data.get('error')}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("DASHBOARD ENDPOINT TESTS (LOCAL)")
    print("="*60)
    print("Note: These tests use Flask's test client and don't require")
    print("external services to be running.\n")
    
    results = {
        "Customer Status Endpoint": test_customer_status_endpoint(),
        "Invoice Aging Endpoint": test_invoice_aging_endpoint(),
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
        print("\nThe dashboard should now display correctly.")
    else:
        print("✗ Some tests failed. Check the database configuration.")
    print("="*60 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
