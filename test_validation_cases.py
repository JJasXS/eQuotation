"""
Validation Test Cases for Guest Sign-In Registration
Tests both valid and invalid inputs for all 4 required fields
"""

from validationSignIn import validate_registration_fields
import json

# Test cases: (description, input_data, expected_pass)
test_cases = [
    # ============ VALID CASES ============
    (
        "Valid: All fields correct format",
        {
            'BRN2': '123456789012',           # 12 digits
            'BRN': 'ABC123',                   # alphanumeric
            'TIN': 'TIN123ABC',                # alphanumeric
            'CUSTOMERCODE': '300-E0888',       # XXX-X0000 format (optional)
        },
        True
    ),
    (
        "Valid: No customer code (auto-generate)",
        {
            'BRN2': '999888777666',
            'BRN': 'BRN001',
            'TIN': 'TIN001',
            'CUSTOMERCODE': '',                # Empty is OK (auto-generate in PHP)
        },
        True
    ),
    (
        "Valid: Customer code with numbers",
        {
            'BRN2': '111222333444',
            'BRN': 'XYZ789',
            'TIN': 'ABC456DEF',
            'CUSTOMERCODE': '500-A1234',       # Numbers in letters part OK
        },
        True
    ),
    (
        "Valid: Minimum valid customer code",
        {
            'BRN2': '000000000001',
            'BRN': 'A',                        # Single char OK for BRN
            'TIN': 'T',                        # Single char OK for TIN
            'CUSTOMERCODE': '100-Z9999',
        },
        True
    ),

    # ============ BRN2 VALIDATION FAILURES ============
    (
        "Invalid: BRN2 - less than 12 digits",
        {
            'BRN2': '12345678901',             # 11 digits (one short)
            'BRN': 'VALID001',
            'TIN': 'VALID001',
            'CUSTOMERCODE': '',
        },
        False
    ),
    (
        "Invalid: BRN2 - more than 12 digits",
        {
            'BRN2': '1234567890123',           # 13 digits (one too many)
            'BRN': 'VALID001',
            'TIN': 'VALID001',
            'CUSTOMERCODE': '',
        },
        False
    ),
    (
        "Invalid: BRN2 - contains letters",
        {
            'BRN2': '12345678901A',            # Contains letter
            'BRN': 'VALID001',
            'TIN': 'VALID001',
            'CUSTOMERCODE': '',
        },
        False
    ),
    (
        "Invalid: BRN2 - contains special chars",
        {
            'BRN2': '123456789-12',            # Contains dash
            'BRN': 'VALID001',
            'TIN': 'VALID001',
            'CUSTOMERCODE': '',
        },
        False
    ),
    (
        "Invalid: BRN2 - empty",
        {
            'BRN2': '',
            'BRN': 'VALID001',
            'TIN': 'VALID001',
            'CUSTOMERCODE': '',
        },
        False
    ),

    # ============ BRN VALIDATION FAILURES ============
    (
        "Invalid: BRN - empty",
        {
            'BRN2': '123456789012',
            'BRN': '',                         # Empty BRN
            'TIN': 'VALID001',
            'CUSTOMERCODE': '',
        },
        False
    ),
    (
        "Invalid: BRN - contains special chars",
        {
            'BRN2': '123456789012',
            'BRN': 'VALID-001',                # Contains dash
            'TIN': 'VALID001',
            'CUSTOMERCODE': '',
        },
        False
    ),
    (
        "Invalid: BRN - contains spaces",
        {
            'BRN2': '123456789012',
            'BRN': 'VALID 001',                # Contains space
            'TIN': 'VALID001',
            'CUSTOMERCODE': '',
        },
        False
    ),

    # ============ TIN VALIDATION FAILURES ============
    (
        "Invalid: TIN - empty",
        {
            'BRN2': '123456789012',
            'BRN': 'VALID001',
            'TIN': '',                         # Empty TIN
            'CUSTOMERCODE': '',
        },
        False
    ),
    (
        "Invalid: TIN - contains special chars",
        {
            'BRN2': '123456789012',
            'BRN': 'VALID001',
            'TIN': 'VALID@001',                # Contains @
            'CUSTOMERCODE': '',
        },
        False
    ),
    (
        "Invalid: TIN - contains spaces",
        {
            'BRN2': '123456789012',
            'BRN': 'VALID001',
            'TIN': 'VALID 001',                # Contains space
            'CUSTOMERCODE': '',
        },
        False
    ),

    # ============ CUSTOMERCODE VALIDATION FAILURES ============
    (
        "Invalid: CUSTOMERCODE - missing dash",
        {
            'BRN2': '123456789012',
            'BRN': 'VALID001',
            'TIN': 'VALID001',
            'CUSTOMERCODE': '300E0888',        # Missing dash
        },
        False
    ),
    (
        "Invalid: CUSTOMERCODE - too few prefix chars",
        {
            'BRN2': '123456789012',
            'BRN': 'VALID001',
            'TIN': 'VALID001',
            'CUSTOMERCODE': '30-E0888',        # Only 2 prefix chars (need 3)
        },
        False
    ),
    (
        "Invalid: CUSTOMERCODE - too many prefix chars",
        {
            'BRN2': '123456789012',
            'BRN': 'VALID001',
            'TIN': 'VALID001',
            'CUSTOMERCODE': '3000-E0888',      # 4 prefix chars (need 3)
        },
        False
    ),
    (
        "Invalid: CUSTOMERCODE - missing digit part",
        {
            'BRN2': '123456789012',
            'BRN': 'VALID001',
            'TIN': 'VALID001',
            'CUSTOMERCODE': '300-EABCD',       # Letters instead of digits
        },
        False
    ),
    (
        "Invalid: CUSTOMERCODE - too few digits",
        {
            'BRN2': '123456789012',
            'BRN': 'VALID001',
            'TIN': 'VALID001',
            'CUSTOMERCODE': '300-E088',        # Only 3 digits (need 4)
        },
        False
    ),
    (
        "Invalid: CUSTOMERCODE - missing letter (digit only)",
        {
            'BRN2': '123456789012',
            'BRN': 'VALID001',
            'TIN': 'VALID001',
            'CUSTOMERCODE': '300-10888',       # Digit in middle position (needs LETTER)
        },
        False
    ),
    (
        "Invalid: CUSTOMERCODE - invalid characters",
        {
            'BRN2': '123456789012',
            'BRN': 'VALID001',
            'TIN': 'VALID001',
            'CUSTOMERCODE': '300-@0888',       # Special char
        },
        False
    ),
]

def run_tests():
    """Run all validation tests and report results."""
    print("=" * 80)
    print("VALIDATION TEST SUITE - Guest Sign-In Registration")
    print("=" * 80)
    print()
    
    passed = 0
    failed = 0
    
    for i, (description, test_data, expected_pass) in enumerate(test_cases, 1):
        result = validate_registration_fields(test_data)
        is_valid = result is None
        
        # Determine if test passed
        test_passed = (is_valid == expected_pass)
        
        status = "✓ PASS" if test_passed else "✗ FAIL"
        if test_passed:
            passed += 1
        else:
            failed += 1
        
        print(f"Test {i:2d}: {status} | {description}")
        
        # Show validation status
        if is_valid:
            print(f"         Status: VALID ✓")
        else:
            print(f"         Status: INVALID ✗")
            print(f"         Error:  {result}")
        
        # Show test data
        print(f"         Data:")
        for key, value in test_data.items():
            if value:
                print(f"           {key}: {value}")
            else:
                print(f"           {key}: (empty)")
        print()
    
    # Summary
    print("=" * 80)
    print(f"SUMMARY: {passed} Passed, {failed} Failed (Total: {len(test_cases)} tests)")
    print("=" * 80)
    
    if failed == 0:
        print("✓ All tests passed!")
    else:
        print(f"✗ {failed} test(s) failed - review errors above")
    
    return failed == 0

if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
