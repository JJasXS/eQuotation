import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

BASE_API_URL = os.getenv('BASE_API_URL', 'http://localhost')

def test_connection():
    """Test connection to XAMPP server"""
    print(f"Testing connection to: {BASE_API_URL}")
    print("-" * 50)
    
    # Test 1: Basic connection to localhost
    try:
        response = requests.get(BASE_API_URL, timeout=5)
        print(f"✓ Successfully connected to {BASE_API_URL}")
        print(f"  Status code: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"✗ Cannot connect to {BASE_API_URL}")
        print("  Possible issues:")
        print("  1. XAMPP Apache server is not running")
        print("  2. Check XAMPP Control Panel and start Apache")
        return
    except Exception as e:
        print(f"✗ Error connecting: {e}")
        return
    
    # Test 2: Check if PHP files are accessible
    test_endpoints = [
        '/php/requestOrderChange.php',
        '/Chatbot/php/requestOrderChange.php'
    ]
    
    print("\nTesting PHP endpoints:")
    for endpoint in test_endpoints:
        try:
            url = f"{BASE_API_URL}{endpoint}"
            response = requests.get(url, timeout=5)
            print(f"✓ {url}")
            print(f"  Status: {response.status_code}")
        except Exception as e:
            print(f"✗ {url}")
            print(f"  Error: {type(e).__name__}")
    
    print("\n" + "=" * 50)
    print("CONFIGURATION REQUIREMENTS:")
    print("=" * 50)
    print("For XAMPP to work properly, you need:")
    print("1. XAMPP installed and Apache running")
    print("2. Chatbot folder in C:\\xampp\\htdocs\\")
    print("3. BASE_API_URL should be one of:")
    print("   - http://localhost/Chatbot (if in htdocs/Chatbot)")
    print("   - http://localhost (if in htdocs root)")
    print("\nCurrent BASE_API_URL: " + BASE_API_URL)
    print("\nTo fix:")
    print("1. Open XAMPP Control Panel")
    print("2. Start Apache")
    print("3. Copy Chatbot folder to C:\\xampp\\htdocs\\")
    print("4. Update .env file: BASE_API_URL=http://localhost/Chatbot")

if __name__ == "__main__":
    test_connection()
