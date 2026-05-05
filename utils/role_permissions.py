"""
Role and UI permissions derived from SY_USER UDF_* flags (not SY_USER.CODE).

Canonical access tier (session['access_tier']) after login:
  - full_admin          UDF_MANAGEMENT
  - sales_management    UDF_SMANAGEMENT
  - purchasing_management UDF_PMANAGEMENT
  - sales_staff         UDF_SSTAFF or UDF_SUSER (same quotation-side limits as staff)
  - purchase_staff      UDF_PUSER
  - customer            AR customer / branch email match (quotation customer UI)
  - supplier            supplier email match
  - no_role             SY_USER row exists but no recognized role UDF is true (cannot use the app)

Legacy sessions without access_tier infer from user_type for backward compatibility.
"""
from __future__ import annotations

# SY_USER column -> canonical flag name (lowercase)
SY_USER_UDF_COLUMN_TO_FLAG = {
    'UDF_MANAGEMENT': 'management',
    'UDF_SMANAGEMENT': 'smanagement',
    'UDF_PMANAGEMENT': 'pmanagement',
    'UDF_SSTAFF': 'sstaff',
    'UDF_SUSER': 'suser',
    'UDF_PUSER': 'puser',
}

ACCESS_TIER_FULL_ADMIN = 'full_admin'
ACCESS_TIER_SALES_MGMT = 'sales_management'
ACCESS_TIER_PURCH_MGMT = 'purchasing_management'
ACCESS_TIER_SALES_STAFF = 'sales_staff'
ACCESS_TIER_PURCH_STAFF = 'purchase_staff'
ACCESS_TIER_CUSTOMER = 'customer'
ACCESS_TIER_SUPPLIER = 'supplier'
ACCESS_TIER_NO_ROLE = 'no_role'


def _truthy(val) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().upper()
    if not s:
        return False
    return s in ('1', 'Y', 'YES', 'T', 'TRUE', 'ON', '-1')


def staff_udf_from_sy_user_row(row: dict | None) -> dict:
    """Build {'management': bool, 'smanagement': bool, ...} from a SY_USER row dict (any casing)."""
    if not isinstance(row, dict):
        return {}
    norm = {}
    for k, v in row.items():
        if k is None:
            continue
        key = str(k).strip()
        norm[key.upper()] = v
    out = {}
    for col, flag in SY_USER_UDF_COLUMN_TO_FLAG.items():
        out[flag] = _truthy(norm.get(col))
    return out


def compute_access_tier(
    *,
    is_supplier: bool,
    is_customer: bool,
    staff_udf: dict | None,
    sy_user_row_present: bool,
) -> str:
    """Pick a single primary tier; priority respects management > sales mgmt > purch mgmt > staff > customer > supplier."""
    if is_supplier:
        return ACCESS_TIER_SUPPLIER
    udf = staff_udf or {}
    if udf.get('management'):
        return ACCESS_TIER_FULL_ADMIN
    if udf.get('smanagement'):
        return ACCESS_TIER_SALES_MGMT
    if udf.get('pmanagement'):
        return ACCESS_TIER_PURCH_MGMT
    # UDF_SUSER: limited sales-side staff (same tier as SSTAFF; not management).
    if udf.get('sstaff') or udf.get('suser'):
        return ACCESS_TIER_SALES_STAFF
    if udf.get('puser'):
        return ACCESS_TIER_PURCH_STAFF
    if is_customer:
        return ACCESS_TIER_CUSTOMER
    # SY_USER exists but no role UDF enabled — do not grant access (login is rejected in verify_otp).
    if sy_user_row_present:
        return ACCESS_TIER_NO_ROLE
    return ACCESS_TIER_CUSTOMER


def infer_access_tier_from_session(session) -> str:
    """Used when older sessions have no access_tier key."""
    explicit = session.get('access_tier')
    if explicit:
        return str(explicit).strip()
    ut = (session.get('user_type') or '').strip().lower()
    if ut == 'supplier':
        return ACCESS_TIER_SUPPLIER
    if ut == 'admin':
        return ACCESS_TIER_FULL_ADMIN
    return ACCESS_TIER_CUSTOMER


def staff_has_any_mapped_role_udf(staff_udf: dict | None) -> bool:
    """True if any role-driving SY_USER UDF we honor is set (excludes non-role UDF_* columns not in the map)."""
    udf = staff_udf or {}
    return any(
        udf.get(k)
        for k in ('management', 'smanagement', 'pmanagement', 'sstaff', 'suser', 'puser')
    )


def is_full_management_admin(session) -> bool:
    return infer_access_tier_from_session(session) == ACCESS_TIER_FULL_ADMIN


def can_update_pr_approvals_and_header_status(session) -> bool:
    """PH_PQ UDF_STATUS + PH_PQDTL UDF_PQAPPROVED updates: purchasing management or full admin only (not PSTAFF)."""
    t = infer_access_tier_from_session(session)
    return t in (ACCESS_TIER_FULL_ADMIN, ACCESS_TIER_PURCH_MGMT)


def can_patch_pr_workflow_status(session, current_status: str, target_status: str) -> bool:
    """
    PATCH /purchase-requests/<no>/status: who may request a transition to target_status from current_status.

    - APPROVED / REJECTED: purchasing management or full admin only (same as UDF approval APIs).
    - SUBMITTED from DRAFT: any purchase-menu role (incl. purchase staff).
    - CANCELLED from DRAFT: any purchase-menu role.
    - CANCELLED from SUBMITTED (or other non-draft): purchasing management or full admin only.
    - No-op (target equals current): any purchase-menu role.
    """
    if not can_access_purchase_menu(session):
        return False
    cur = (current_status or "").strip().upper()
    tgt = (target_status or "").strip().upper()
    if not tgt:
        return False
    if tgt == cur:
        return True
    if tgt in ("APPROVED", "REJECTED"):
        return can_update_pr_approvals_and_header_status(session)
    if tgt == "SUBMITTED" and cur == "DRAFT":
        return True
    if tgt == "CANCELLED":
        if cur == "DRAFT":
            return True
        return can_update_pr_approvals_and_header_status(session)
    return False


def hide_pr_approval_edits_for_pstaff(session) -> bool:
    """PSTAFF: read-only PR header UDF status + line approval checkboxes in View PR."""
    return infer_access_tier_from_session(session) == ACCESS_TIER_PURCH_STAFF


def can_access_admin_dashboard(session) -> bool:
    """Main /admin dashboard: full admin + sales management."""
    t = infer_access_tier_from_session(session)
    if t == ACCESS_TIER_NO_ROLE:
        return False
    return t in (ACCESS_TIER_FULL_ADMIN, ACCESS_TIER_SALES_MGMT)


def can_access_purchase_menu(session) -> bool:
    """Purchase submenu (procurement): full admin + purchasing roles + purchase staff."""
    t = infer_access_tier_from_session(session)
    if t == ACCESS_TIER_NO_ROLE:
        return False
    return t in (
        ACCESS_TIER_FULL_ADMIN,
        ACCESS_TIER_PURCH_MGMT,
        ACCESS_TIER_PURCH_STAFF,
    )


def can_access_pricing_priority_rules(session) -> bool:
    return infer_access_tier_from_session(session) == ACCESS_TIER_FULL_ADMIN


def can_access_create_quotation(session) -> bool:
    """Create quotation page: customers + sales roles; not full admin (use admin view-quotations); not supplier; not purchasing-only."""
    t = infer_access_tier_from_session(session)
    if t == ACCESS_TIER_NO_ROLE:
        return False
    if t == ACCESS_TIER_SUPPLIER:
        return False
    if t in (ACCESS_TIER_PURCH_MGMT, ACCESS_TIER_PURCH_STAFF):
        return False
    if t == ACCESS_TIER_FULL_ADMIN:
        return False
    return t in (
        ACCESS_TIER_CUSTOMER,
        ACCESS_TIER_SALES_MGMT,
        ACCESS_TIER_SALES_STAFF,
    )


def can_access_view_quotation_customer_ui(session) -> bool:
    """Customer /view-quotation + SSTAFF + sales + full admin."""
    t = infer_access_tier_from_session(session)
    if t == ACCESS_TIER_NO_ROLE:
        return False
    if t == ACCESS_TIER_SUPPLIER:
        return False
    if t in (ACCESS_TIER_PURCH_MGMT, ACCESS_TIER_PURCH_STAFF):
        return False
    return t in (
        ACCESS_TIER_CUSTOMER,
        ACCESS_TIER_SALES_STAFF,
        ACCESS_TIER_SALES_MGMT,
        ACCESS_TIER_FULL_ADMIN,
    )


def can_access_admin_view_quotations(session) -> bool:
    """Admin list all quotations."""
    t = infer_access_tier_from_session(session)
    if t == ACCESS_TIER_NO_ROLE:
        return False
    return t in (ACCESS_TIER_FULL_ADMIN, ACCESS_TIER_SALES_MGMT)


def can_access_pending_approvals_admin(session) -> bool:
    t = infer_access_tier_from_session(session)
    if t == ACCESS_TIER_NO_ROLE:
        return False
    return t in (ACCESS_TIER_FULL_ADMIN, ACCESS_TIER_PURCH_MGMT, ACCESS_TIER_PURCH_STAFF)


def hide_quotation_status_actions(session) -> bool:
    """SSTAFF: read-only on admin quotation list (no edit/activate/cancel/restore/bulk delete)."""
    return infer_access_tier_from_session(session) == ACCESS_TIER_SALES_STAFF


def hide_pr_transfer_for_pstaff(session) -> bool:
    """PSTAFF: hide transfer in view PR (UI flag for templates/JS)."""
    return infer_access_tier_from_session(session) == ACCESS_TIER_PURCH_STAFF


def template_permission_context(session) -> dict:
    """Keys for Jinja2 includes (hamburger, headers)."""
    tier = infer_access_tier_from_session(session)
    return {
        'access_tier': tier,
        'perm_full_admin': tier == ACCESS_TIER_FULL_ADMIN,
        'perm_sales_management': tier == ACCESS_TIER_SALES_MGMT,
        'perm_purchasing_management': tier == ACCESS_TIER_PURCH_MGMT,
        'perm_sales_staff': tier == ACCESS_TIER_SALES_STAFF,
        'perm_purchase_staff': tier == ACCESS_TIER_PURCH_STAFF,
        'perm_customer': tier == ACCESS_TIER_CUSTOMER,
        'perm_supplier': tier == ACCESS_TIER_SUPPLIER,
        'perm_no_role': tier == ACCESS_TIER_NO_ROLE,
        'perm_admin_dashboard': can_access_admin_dashboard(session),
        'perm_purchase_menu': can_access_purchase_menu(session),
        'perm_pricing_priority': can_access_pricing_priority_rules(session),
        'perm_create_quotation': can_access_create_quotation(session),
        'perm_view_quotation_ui': can_access_view_quotation_customer_ui(session),
        'perm_admin_view_quotations': can_access_admin_view_quotations(session),
        'perm_pending_approvals_admin': can_access_pending_approvals_admin(session),
        'perm_hide_quotation_status_actions': hide_quotation_status_actions(session),
        'perm_hide_pr_transfer': hide_pr_transfer_for_pstaff(session),
        'perm_hide_pr_approval_edits': hide_pr_approval_edits_for_pstaff(session),
    }


def user_type_for_session(access_tier: str) -> str:
    """
    Flask session user_type backward compatibility:
    - supplier
    - user: customer + sales_staff + no_role (no_role cannot complete login; if present, treat as non-admin)
    - admin: full admin + sales mgmt + purchasing mgmt + purchase staff (elevated /admin/* except where further gated)
    """
    if access_tier == ACCESS_TIER_SUPPLIER:
        return 'supplier'
    if access_tier in (ACCESS_TIER_CUSTOMER, ACCESS_TIER_SALES_STAFF, ACCESS_TIER_NO_ROLE):
        return 'user'
    if access_tier in (
        ACCESS_TIER_FULL_ADMIN,
        ACCESS_TIER_SALES_MGMT,
        ACCESS_TIER_PURCH_MGMT,
        ACCESS_TIER_PURCH_STAFF,
    ):
        return 'admin'
    return 'user'
