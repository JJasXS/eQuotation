"""
SY_USER role flag load and optional mid-session refresh in APP=dev.

APP=prod: roles stay frozen from OTP login.
APP=dev: re-read SY_USER into the session so Role Selection edits show on refresh.
"""
from __future__ import annotations

import time

from utils.app_mode import is_dev_app
from utils.db_utils import get_db_connection
from utils.role_permissions import (
    compute_access_tier,
    staff_locations_from_sy_user_row,
    staff_udf_from_sy_user_row,
    user_type_for_session,
)

_SESSION_REFRESH_AT_KEY = '_dev_role_refresh_at'
_DEFAULT_MIN_INTERVAL_SEC = 1.5


def mock_role_refresh_enabled() -> bool:
    """True when APP=dev (developer testing phase)."""
    return is_dev_app()


def fetch_sy_user_profile_with_udfs(cur, normalized_email: str):
    """
    Return (row_dict, staff_udf) for SY_USER row matching email, including UDF_* columns.
    row_dict is None when no SY_USER row.
    """
    cur.execute(
        """
        SELECT TRIM(RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS
        WHERE RDB$RELATION_NAME = 'SY_USER' AND RDB$FIELD_NAME STARTING WITH 'UDF_'
        """,
    )
    udf_cols = [str(r[0]).strip() for r in (cur.fetchall() or []) if r and r[0]]

    base_cols = ['CODE', 'NAME', 'EMAIL', 'ISACTIVE']
    select_cols = base_cols + [c for c in udf_cols if c.upper() not in {x.upper() for x in base_cols}]
    col_sql = ', '.join(select_cols)
    cur.execute(
        f"""
        SELECT {col_sql}
        FROM SY_USER
        WHERE UPPER(TRIM(EMAIL)) = UPPER(TRIM(?))
        """,
        [normalized_email],
    )
    row = cur.fetchone()
    if not row:
        return None, {}
    row_dict = {select_cols[i]: row[i] for i in range(len(select_cols))}
    return row_dict, staff_udf_from_sy_user_row(row_dict)


def refresh_staff_session_roles(session, *, min_interval_sec: float = _DEFAULT_MIN_INTERVAL_SEC) -> bool:
    """
    Re-load SY_USER Role Selection flags into ``session``.

    Returns True when access_tier / staff_udf / locations / user_type changed.
    No-op when APP is not dev, supplier sessions, or throttle window.
    """
    if not mock_role_refresh_enabled():
        return False
    if session is None or not session.get('user_email'):
        return False
    if (session.get('user_type') or '').strip().lower() == 'supplier':
        return False

    now = time.monotonic()
    last = session.get(_SESSION_REFRESH_AT_KEY)
    try:
        last_f = float(last) if last is not None else 0.0
    except (TypeError, ValueError):
        last_f = 0.0
    if min_interval_sec > 0 and (now - last_f) < min_interval_sec:
        return False

    email = str(session.get('user_email') or '').strip().lower()
    if not email:
        return False

    con = None
    cur = None
    try:
        con = get_db_connection()
        cur = con.cursor()
        row, staff_udf = fetch_sy_user_profile_with_udfs(cur, email)
    except Exception as exc:
        print(f'[DEV ROLE] SY_USER refresh failed for {email}: {exc}', flush=True)
        return False
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if con is not None:
            try:
                con.close()
            except Exception:
                pass

    session[_SESSION_REFRESH_AT_KEY] = now
    if not row:
        return False

    staff_locations = staff_locations_from_sy_user_row(row)
    access_tier = compute_access_tier(
        is_supplier=False,
        is_customer=False,
        staff_udf=staff_udf,
        sy_user_row_present=True,
    )
    user_type = user_type_for_session(access_tier)

    prev_tier = str(session.get('access_tier') or '')
    prev_udf = session.get('staff_udf') if isinstance(session.get('staff_udf'), dict) else {}
    prev_locs = session.get('staff_locations') if isinstance(session.get('staff_locations'), list) else []
    prev_type = str(session.get('user_type') or '')

    changed = (
        prev_tier != access_tier
        or prev_udf != staff_udf
        or prev_locs != staff_locations
        or (prev_type != 'supplier' and prev_type != user_type)
    )

    session['staff_udf'] = staff_udf
    session['staff_locations'] = staff_locations
    session['access_tier'] = access_tier
    if prev_type != 'supplier':
        session['user_type'] = user_type

    if changed:
        print(
            f'[DEV ROLE] refreshed {email} tier={access_tier} user_type={session.get("user_type")} '
            f'staff_udf={staff_udf}',
            flush=True,
        )
    return changed
