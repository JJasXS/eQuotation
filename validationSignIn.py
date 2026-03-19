"""Validation functions for guest sign-in registration."""
import re


_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
_BRN_OLD_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-/]*$')   # allow dash/slash
_TIN_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-/]*$')       # allow dash/slash
_PHONE_RE = re.compile(r'^[0-9+()\-\s]{6,30}$')             # permissive, human-entered
_POSTCODE_RE = re.compile(r'^\d{5}$')
_ALPHA2_RE = re.compile(r'^[A-Za-z]{2}$')


def _get(data, key):
    return (data.get(key) or '').strip()


def validate_registration_fields(data):
    """
    Server-side validation for guest sign-in registration fields.

    Returns:
        None if all fields are valid, error message string if validation fails.
    """
    # Required fields (basic presence)
    required_keys = [
        ('COMPANYNAME', 'Company Name'),
        ('UDF_EMAIL', 'Email'),
        ('AREA', 'Area'),
        ('CURRENCYCODE', 'Currency'),
        ('BRN', 'Reg No. (old)'),
        ('BRN2', 'Reg No. (new)'),
        ('TIN', 'TIN No.'),
        ('ATTENTION', 'Attention'),
        ('ADDRESS1', 'Address 1'),
        ('POSTCODE', 'Postcode'),
        ('PHONE1', 'Phone Number'),
        ('COUNTRY', 'Country'),
    ]
    for key, label in required_keys:
        if not _get(data, key):
            return f'{label} is required.'

    # Email format
    email = _get(data, 'UDF_EMAIL')
    if len(email) > 255:
        return 'Email is too long.'
    if not _EMAIL_RE.match(email):
        return 'Email format is invalid.'

    # Postcode: Malaysia dataset is 5-digit
    postcode = _get(data, 'POSTCODE')
    if not _POSTCODE_RE.match(postcode):
        return 'Postcode must be exactly 5 digits.'

    # City/State should be filled (auto-fill from postcode on backend)
    city = _get(data, 'CITY')
    state = _get(data, 'STATE')
    if not city:
        return 'City is required (enter a valid postcode).'
    if not state:
        return 'State is required (enter a valid postcode).'
    if len(city) > 200:
        return 'City is too long.'
    if len(state) > 200:
        return 'State is too long.'

    # Country: prefer alpha-2
    country = _get(data, 'COUNTRY')
    if not _ALPHA2_RE.match(country):
        return 'Country must be a 2-letter code (e.g. MY).'

    # BRN2: exactly 12 digits
    brn2 = _get(data, 'BRN2')
    if not re.match(r'^\d{12}$', brn2):
        return 'Reg No. (new) must be exactly 12 numeric digits.'

    # BRN old: allow dash/slash, but must be alphanumeric-ish
    brn = _get(data, 'BRN')
    if not _BRN_OLD_RE.match(brn):
        return 'Reg No. (old) may contain only letters, numbers, "-" or "/".'

    # TIN: allow dash/slash
    tin = _get(data, 'TIN')
    if not _TIN_RE.match(tin):
        return 'TIN No. may contain only letters, numbers, "-" or "/".'

    # Phone
    phone1 = _get(data, 'PHONE1')
    if not _PHONE_RE.match(phone1):
        return 'Phone Number format is invalid.'

    # Basic length limits to avoid DB truncation surprises
    company = _get(data, 'COMPANYNAME')
    if len(company) > 400:
        return 'Company Name is too long.'
    attention = _get(data, 'ATTENTION')
    if len(attention) > 280:
        return 'Attention is too long.'
    address1 = _get(data, 'ADDRESS1')
    if len(address1) > 240:
        return 'Address 1 is too long.'
    address2 = _get(data, 'ADDRESS2')
    address3 = _get(data, 'ADDRESS3')
    address4 = _get(data, 'ADDRESS4')
    if len(address2) > 240 or len(address3) > 240 or len(address4) > 240:
        return 'Address line is too long.'

    return None
