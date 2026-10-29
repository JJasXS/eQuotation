"""
Role and UI permissions derived from SY_USER UDF_* flags (not SY_USER.CODE).

Canonical access tier (session['access_tier']) after login:
  - full_admin            UDF_ISADMIN
  - purchasing_management UDF_ISPURMGR (alias UDF_ISPURMNG)
  - hod                   UDF_ISHOD
  - director              UDF_ISDIRECTOR (gate only; tab/action rules TBD)
  - sales_staff           UDF_SSTAFF
  - customer              AR customer / branch email match (quotation customer UI)
  - supplier              supplier email match
  - no_role               SY_USER row exists but no recognized role UDF is true

Purchase / View e-PR requires at least one of:
  UDF_ISADMIN | UDF_ISHOD | UDF_ISPURMGR/UDF_ISPURMNG | UDF_ISDIRECTOR

Ignored (not mapped — no access effect):
  UDF_MANAGEMENT, UDF_PMANAGEMENT, UDF_PUSER, UDF_SMANAGEMENT, UDF_SUSER.

Legacy sessions without access_tier infer from user_type for backward compatibility.
"""
from __future__ import annotations

import os

# SY_USER column -> canonical flag name (lowercase).
# ACC-UAMAT uses UDF_ISPURMGR; docs/UI may still say UDF_ISPURMNG — map both.
SY_USER_UDF_COLUMN_TO_FLAG = {
    'UDF_ISADMIN': 'isadmin',
    'UDF_ISHOD': 'ishod',
    'UDF_ISPURMGR': 'ispurmng',
    'UDF_ISPURMNG': 'ispurmng',
    'UDF_ISDIRECTOR': 'isdirector',
    'UDF_SSTAFF': 'sstaff',
}

# Non-boolean location scope column (ST_LOCATION codes; comma / semicolon / pipe separated).
SY_USER_LOCATION_UDF_COLUMN = 'UDF_LOCATION'

ACCESS_TIER_FULL_ADMIN = 'full_admin'
ACCESS_TIER_SALES_MGMT = 'sales_management'
ACCESS_TIER_PURCH_MGMT = 'purchasing_management'
ACCESS_TIER_HOD = 'hod'
ACCESS_TIER_DIRECTOR = 'director'
ACCESS_TIER_SALES_STAFF = 'sales_staff'
# Kept for older sessions / tests; no longer assigned from SY_USER login.
ACCESS_TIER_PURCH_STAFF = 'purchase_staff'
ACCESS_TIER_CUSTOMER = 'customer'
ACCESS_TIER_SUPPLIER = 'supplier'
ACCESS_TIER_NO_ROLE = 'no_role'

_VIEW_PR_TIERS = (
    ACCESS_TIER_FULL_ADMIN,
    ACCESS_TIER_PURCH_MGMT,
    ACCESS_TIER_HOD,
    ACCESS_TIER_DIRECTOR,
)

_ROLE_UDF_FLAGS = (
    'isadmin',
    'ishod',
    'ispurmng',
    'isdirector',
    'sstaff',
)


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
    """Build {'isadmin': bool, 'ishod': bool, ...} from a SY_USER row dict (any casing)."""
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
        # Multiple columns may map to one flag (e.g. ISPURMGR / ISPURMNG) — OR them.
        out[flag] = bool(out.get(flag)) or _truthy(norm.get(col))
    return out


def staff_locations_from_sy_user_row(row: dict | None) -> list[str]:
    """
    Parse SY_USER.UDF_LOCATION into uppercased ST_LOCATION codes.

    Accepts comma / semicolon / pipe separators. Drops blanks only.
    ``----`` is a real location code (not null) and is kept.
    """
    if not isinstance(row, dict):
        return []
    raw = None
    for k, v in row.items():
        if k is None:
            continue
        if str(k).strip().upper() == SY_USER_LOCATION_UDF_COLUMN:
            raw = v
            break
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    for sep in (',', ';', '|'):
        text = text.replace(sep, ',')
    out: list[str] = []
    seen: set[str] = set()
    for part in text.split(','):
        code = part.strip().upper()
        if not code:
            continue
        if code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def session_location_scope(session) -> list[str] | None:
    """
    Location codes the current user may see, or ``None`` for unrestricted.

    Full admin and purchasing management always bypass. An empty / missing
    ``session['staff_locations']`` also means unrestricted (blank UDF_LOCATION).
    ``----`` is a valid location code and restricts the user to that location.
    """
    tier = infer_access_tier_from_session(session)
    if tier in (ACCESS_TIER_FULL_ADMIN, ACCESS_TIER_PURCH_MGMT):
        return None
    raw = session.get('staff_locations') if session is not None else None
    if not isinstance(raw, (list, tuple)):
        return None
    codes: list[str] = []
    seen: set[str] = set()
    for item in raw:
        code = str(item or '').strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes or None


def location_in_scope(scope: list[str] | None, code) -> bool:
    """
    True when ``scope`` is unrestricted (None), or the line location matches a
    scoped code (case-insensitive). Blank location is out of scope for
    restricted users. ``----`` is a real location code and matches normally.
    """
    if scope is None:
        return True
    loc = str(code or '').strip().upper()
    if not loc:
        return False
    allowed = {str(c).strip().upper() for c in scope if str(c or '').strip()}
    return loc in allowed


def compute_access_tier(
    *,
    is_supplier: bool,
    is_customer: bool,
    staff_udf: dict | None,
    sy_user_row_present: bool,
) -> str:
    """
    Pick a single primary tier.

    Priority: ISADMIN > ISPURMGR > ISHOD > ISDIRECTOR > SSTAFF.
    """
    if is_supplier:
        return ACCESS_TIER_SUPPLIER
    udf = staff_udf or {}
    if udf.get('isadmin'):
        return ACCESS_TIER_FULL_ADMIN
    if udf.get('ispurmng'):
        return ACCESS_TIER_PURCH_MGMT
    if udf.get('ishod'):
        return ACCESS_TIER_HOD
    if udf.get('isdirector'):
        return ACCESS_TIER_DIRECTOR
    if udf.get('sstaff'):
        return ACCESS_TIER_SALES_STAFF
    if is_customer:
        return ACCESS_TIER_CUSTOMER
    if sy_user_row_present:
        return ACCESS_TIER_NO_ROLE
    return ACCESS_TIER_CUSTOMER


def _staff_udf_from_session(session) -> dict:
    raw = session.get('staff_udf') if session is not None else None
    return raw if isinstance(raw, dict) else {}


def staff_has_view_pr_role_flag(staff_udf: dict | None) -> bool:
    """True when any Purchase Role Selection flag is set on SY_USER."""
    udf = staff_udf or {}
    return bool(
        udf.get('isadmin')
        or udf.get('ishod')
        or udf.get('ispurmng')
        or udf.get('isdirector')
    )


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
    """True if any role-driving SY_USER UDF we honor is set."""
    udf = staff_udf or {}
    return any(udf.get(k) for k in _ROLE_UDF_FLAGS)


def is_full_management_admin(session) -> bool:
    return infer_access_tier_from_session(session) == ACCESS_TIER_FULL_ADMIN


def can_see_view_pr(session) -> bool:
    """View e-PR / Purchase menu: ISADMIN | ISHOD | ISPURMGR | ISDIRECTOR."""
    t = infer_access_tier_from_session(session)
    if t in _VIEW_PR_TIERS:
        return True
    # Also honor session staff_udf so a sales_* primary tier cannot hide Purchase
    # when any of the four Role Selection flags is true.
    return staff_has_view_pr_role_flag(_staff_udf_from_session(session))


def can_update_pr_approvals_and_header_status(session) -> bool:
    """PH_PQ UDF_STATUS + PH_PQDTL UDF_PQAPPROVED: full admin or purchasing manager (not HOD)."""
    t = infer_access_tier_from_session(session)
    return t in (ACCESS_TIER_FULL_ADMIN, ACCESS_TIER_PURCH_MGMT)


def can_patch_pr_workflow_status(session, current_status: str, target_status: str) -> bool:
    """
    PATCH /purchase-requests/<no>/status: who may request a transition to target_status from current_status.

    - APPROVED / REJECTED: purchasing management or full admin only.
    - SUBMITTED from DRAFT: any purchase-menu role.
    - CANCELLED from DRAFT: any purchase-menu role.
    - CANCELLED from SUBMITTED (or other non-draft): purchasing management or full admin only.
    - HOD: AWAITING → PENDING (and draft submit/cancel); not APPROVED/REJECTED or non-draft cancel.
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
    tier = infer_access_tier_from_session(session)
    if tier == ACCESS_TIER_HOD:
        if tgt == "PENDING" and cur in ("AWAITING", "AWAITING APPROVAL", "SUBMITTED"):
            return True
        if tgt == "SUBMITTED" and cur == "DRAFT":
            return True
        if tgt == "CANCELLED" and cur == "DRAFT":
            return True
        return False
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
    """HOD (and legacy purchase_staff sessions): read-only PR approval checkboxes in View PR."""
    return infer_access_tier_from_session(session) in (
        ACCESS_TIER_HOD,
        ACCESS_TIER_PURCH_STAFF,
    )


def can_access_admin_dashboard(session) -> bool:
    """Main /admin dashboard: full admin + sales management + HOD (admin area)."""
    t = infer_access_tier_from_session(session)
    if t == ACCESS_TIER_NO_ROLE:
        return False
    return t in (ACCESS_TIER_FULL_ADMIN, ACCESS_TIER_SALES_MGMT, ACCESS_TIER_HOD)


def can_access_purchase_menu(session) -> bool:
    """Purchase submenu (procurement) — same gate as View e-PR."""
    return can_see_view_pr(session)


def can_access_pricing_priority_rules(session) -> bool:
    return infer_access_tier_from_session(session) == ACCESS_TIER_FULL_ADMIN


def can_access_create_quotation(session) -> bool:
    """Create quotation page: customers + sales roles; not full admin; not supplier; not purchase roles."""
    t = infer_access_tier_from_session(session)
    if t == ACCESS_TIER_NO_ROLE:
        return False
    if t == ACCESS_TIER_SUPPLIER:
        return False
    if t in (
        ACCESS_TIER_PURCH_MGMT,
        ACCESS_TIER_PURCH_STAFF,
        ACCESS_TIER_HOD,
        ACCESS_TIER_DIRECTOR,
    ):
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
    if t in (
        ACCESS_TIER_PURCH_MGMT,
        ACCESS_TIER_PURCH_STAFF,
        ACCESS_TIER_HOD,
        ACCESS_TIER_DIRECTOR,
    ):
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
    return t in _VIEW_PR_TIERS


def hide_quotation_status_actions(session) -> bool:
    """SSTAFF: read-only on admin quotation list (no edit/activate/cancel/restore/bulk delete)."""
    return infer_access_tier_from_session(session) == ACCESS_TIER_SALES_STAFF


def hide_pr_transfer_for_pstaff(session) -> bool:
    """Hide Transfer to PO for HOD (and legacy purchase_staff sessions)."""
    return infer_access_tier_from_session(session) in (
        ACCESS_TIER_HOD,
        ACCESS_TIER_PURCH_STAFF,
    )


def hide_pr_awaiting_tab(session) -> bool:
    """Purchasing manager: hide Awaiting Approval status tab (HOD owns that queue)."""
    return infer_access_tier_from_session(session) == ACCESS_TIER_PURCH_MGMT


def approval_po_base_url() -> str:
    """Base URL for ApprovalPO (purchase/sales order approval app)."""
    return (os.getenv("APPROVAL_PO_BASE_URL") or "http://localhost:2095").strip().rstrip("/")


def can_access_approval_po_menu(session) -> bool:
    """ApprovalPO links (View PO / Create PO): admin dashboard + purchasing roles."""
    t = infer_access_tier_from_session(session)
    if t == ACCESS_TIER_NO_ROLE:
        return False
    return t in (
        ACCESS_TIER_FULL_ADMIN,
        ACCESS_TIER_SALES_MGMT,
        ACCESS_TIER_PURCH_MGMT,
        ACCESS_TIER_HOD,
        ACCESS_TIER_DIRECTOR,
    )


def can_access_sales_menu(session) -> bool:
    """Sales submenu (quotations): any role that can create or view quotations."""
    return can_access_create_quotation(session) or can_access_view_quotation_customer_ui(session)


def template_permission_context(session) -> dict:
    """Keys for Jinja2 includes (hamburger, headers)."""
    tier = infer_access_tier_from_session(session)
    return {
        'access_tier': tier,
        'perm_full_admin': tier == ACCESS_TIER_FULL_ADMIN,
        'perm_sales_management': tier == ACCESS_TIER_SALES_MGMT,
        'perm_purchasing_management': tier == ACCESS_TIER_PURCH_MGMT,
        'perm_hod': tier == ACCESS_TIER_HOD,
        'perm_director': tier == ACCESS_TIER_DIRECTOR,
        'perm_sales_staff': tier == ACCESS_TIER_SALES_STAFF,
        'perm_purchase_staff': tier == ACCESS_TIER_PURCH_STAFF,
        'perm_customer': tier == ACCESS_TIER_CUSTOMER,
        'perm_supplier': tier == ACCESS_TIER_SUPPLIER,
        'perm_no_role': tier == ACCESS_TIER_NO_ROLE,
        'perm_admin_dashboard': can_access_admin_dashboard(session),
        'perm_purchase_menu': can_access_purchase_menu(session),
        'perm_view_pr': can_see_view_pr(session),
        'perm_pricing_priority': can_access_pricing_priority_rules(session),
        'perm_create_quotation': can_access_create_quotation(session),
        'perm_view_quotation_ui': can_access_view_quotation_customer_ui(session),
        'perm_admin_view_quotations': can_access_admin_view_quotations(session),
        'perm_pending_approvals_admin': can_access_pending_approvals_admin(session),
        'perm_hide_quotation_status_actions': hide_quotation_status_actions(session),
        'perm_hide_pr_transfer': hide_pr_transfer_for_pstaff(session),
        'perm_hide_pr_approval_edits': hide_pr_approval_edits_for_pstaff(session),
        'perm_hide_pr_awaiting_tab': hide_pr_awaiting_tab(session),
        'perm_sales_menu': can_access_sales_menu(session),
        'perm_approval_po_menu': can_access_approval_po_menu(session),
        'approval_po_base_url': approval_po_base_url(),
    }


def user_type_for_session(access_tier: str) -> str:
    """
    Flask session user_type backward compatibility:
    - supplier
    - user: customer + sales_staff + no_role
    - admin: full admin + sales mgmt + purchasing roles (HOD / purch mng / director)
    """
    if access_tier == ACCESS_TIER_SUPPLIER:
        return 'supplier'
    if access_tier in (ACCESS_TIER_CUSTOMER, ACCESS_TIER_SALES_STAFF, ACCESS_TIER_NO_ROLE):
        return 'user'
    if access_tier in (
        ACCESS_TIER_FULL_ADMIN,
        ACCESS_TIER_SALES_MGMT,
        ACCESS_TIER_PURCH_MGMT,
        ACCESS_TIER_HOD,
        ACCESS_TIER_DIRECTOR,
        ACCESS_TIER_PURCH_STAFF,
    ):
        return 'admin'
    return 'user'
