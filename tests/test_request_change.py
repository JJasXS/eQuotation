import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

BASE_API_URL = os.getenv('BASE_API_URL', 'http://localhost')

def test_request_change():
    """Test the requestOrderChange endpoint with sample data"""
    print("Testing requestOrderChange endpoint")
    print("-" * 50)
    
    # Test with valid data
    test_data = {
        'orderid': 1,  # Using a test order ID
        'remark': 'This is a test change request',
        'requestedby': 'test@example.com'
    }
    
    url = f"{BASE_API_URL}/php/requestOrderChange.php"
    print(f"POST to: {url}")
    print(f"Data: {json.dumps(test_data, indent=2)}")
    print()
    
    try:
        response = requests.post(url, json=test_data, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Text: {response.text}")
        print()
        
        # Try to parse JSON
        try:
            json_response = response.json()
            print(f"JSON Response: {json.dumps(json_response, indent=2)}")
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}")
            print("Response is not valid JSON")
            
    except requests.exceptions.Timeout:
        print("✗ Request timed out")
    except requests.exceptions.ConnectionError:
        print("✗ Connection error")
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_request_change()
