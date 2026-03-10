import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

BASE_API_URL = os.getenv('BASE_API_URL', 'http://localhost')

def test_php_extensions():
    """Test if PHP has the required extensions"""
    print("Testing PHP Extensions")
    print("=" * 60)
    
    # Create a test PHP file to check extensions
    test_php = """<?php
header('Content-Type: application/json');

$extensions = [
    'interbase' => extension_loaded('interbase'),
    'pdo_firebird' => extension_loaded('pdo_firebird'),
];

$functions = [
    'ibase_connect' => function_exists('ibase_connect'),
    'ibase_prepare' => function_exists('ibase_prepare'),
    'ibase_execute' => function_exists('ibase_execute'),
];

echo json_encode([
    'php_version' => phpversion(),
    'extensions' => $extensions,
    'functions' => $functions,
    'loaded_extensions' => get_loaded_extensions()
]);
?>"""
    
    # Check if we can write to htdocs
    test_file_path = r"C:\xampp\htdocs\php\test_extensions.php"
    
    try:
        with open(test_file_path, 'w') as f:
            f.write(test_php)
        print(f"✓ Created test file: {test_file_path}")
    except Exception as e:
        print(f"✗ Cannot create test file: {e}")
        print("\nManual check:")
        print("1. Create a file: C:\\xampp\\htdocs\\php\\test_extensions.php")
        print("2. Add this code:")
        print("<?php phpinfo(); ?>")
        print("3. Open: http://localhost/php/test_extensions.php")
        print("4. Search for 'interbase' in the page")
        return
    
    # Call the test endpoint
    try:
        url = f"{BASE_API_URL}/php/test_extensions.php"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"\nPHP Version: {data.get('php_version', 'Unknown')}")
                print("\nExtensions:")
                for ext, loaded in data.get('extensions', {}).items():
                    status = "✓ LOADED" if loaded else "✗ NOT LOADED"
                    print(f"  {ext}: {status}")
                
                print("\nFirebird Functions:")
                for func, exists in data.get('functions', {}).items():
                    status = "✓ AVAILABLE" if exists else "✗ NOT AVAILABLE"
                    print(f"  {func}(): {status}")
                
                # Check for Firebird-related extensions
                loaded_exts = data.get('loaded_extensions', [])
                firebird_exts = [e for e in loaded_exts if 'interbase' in e.lower() or 'firebird' in e.lower() or 'ibase' in e.lower()]
                
                print("\nFirebird-related extensions loaded:")
                if firebird_exts:
                    for ext in firebird_exts:
                        print(f"  - {ext}")
                else:
                    print("  None found")
                
                # Provide recommendations
                print("\n" + "=" * 60)
                if data.get('extensions', {}).get('interbase'):
                    print("✓ PHP InterBase extension is ENABLED")
                    print("  Your PHP is configured correctly for Firebird!")
                elif data.get('extensions', {}).get('pdo_firebird'):
                    print("⚠ Only PDO Firebird is available")
                    print("  You'll need to modify PHP code to use PDO instead of ibase_* functions")
                else:
                    print("✗ No Firebird extensions are enabled")
                    print("\nTO FIX:")
                    print("1. Edit C:\\xampp\\php\\php.ini")
                    print("2. Find and uncomment: extension=interbase")
                    print("3. Restart Apache in XAMPP")
                    print("4. Run this test again")
                    
            except Exception as e:
                print(f"✗ Error parsing response: {e}")
                print(f"Response text: {response.text[:500]}")
        else:
            print(f"✗ HTTP Error: {response.status_code}")
            
    except Exception as e:
        print(f"✗ Error calling test endpoint: {e}")
    
    # Cleanup
    try:
        os.remove(test_file_path)
        print(f"\n✓ Cleaned up test file")
    except:
        pass

if __name__ == "__main__":
    test_php_extensions()
