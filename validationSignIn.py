"""Validation functions for guest sign-in registration."""
import re


def validate_registration_fields(data):
    """
    Server-side validation for guest sign-in registration fields.
    
    Args:
        data: Dictionary containing form fields (BRN2, BRN, TIN, etc.)
    
    Returns:
        None if all fields are valid, error message string if validation fails.
    """
    brn2 = (data.get('BRN2') or '').strip()
    brn = (data.get('BRN') or '').strip()
    tin = (data.get('TIN') or '').strip()
    
    # Validate BRN2 (new reg num): exactly 12 numeric digits
    if not re.match(r'^\d{12}$', brn2):
        return 'Reg No. (new) must be exactly 12 numeric digits.'
    
    # Validate BRN (old): alphanumeric, not empty
    if not brn:
        return 'Reg No. (old) is required.'
    if not re.match(r'^[a-zA-Z0-9]+$', brn):
        return 'Reg No. (old) must contain only letters and numbers.'
    
    # Validate TIN: alphanumeric, not empty
    if not tin:
        return 'TIN No. is required.'
    if not re.match(r'^[a-zA-Z0-9]+$', tin):
        return 'TIN No. must contain only letters and numbers.'
    
    return None  # No validation errors
