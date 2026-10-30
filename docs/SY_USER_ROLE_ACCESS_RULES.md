# SY_USER role access rules

**Status:** Wired for Purchase / View e-PR.  
**Date:** 2026-10-29  

## Principle

**ISADMIN / ISHOD / ISPURMGR / ISDIRECTOR all see the Purchase area** (menu, Create e-PR, View e-PR, etc.).

Limits are **only inside View e-PR status tabs** (which tabs show, and what you can do on that tab) — not whether Purchase itself is visible.

### When roles / OTP are applied (`APP`)

| Phase | `APP` | Behaviour |
|-------|-------|-----------|
| **Production (live)** | `prod` (default if unset) | Roles loaded **once at OTP login**. Changing SY_USER needs **log out → log in**. OTP is **emailed** (not shown on the page). |
| **Developer testing** | `dev` | Roles **re-read from SY_USER** on each request. OTP is **shown on the login page** and **not emailed**. |

```text
can_see_purchase =
  ISADMIN OR ISHOD OR ISPURMGR OR ISDIRECTOR
```

---

## Source fields on `SY_USER`

| Column | Role |
|--------|------|
| `UDF_ISADMIN` | System admin — full access |
| `UDF_ISHOD` | HOD — Awaiting-focused; Pending/Approved view-only |
| `UDF_ISPURMGR` | Purchasing manager — Pending/Approved full; no Awaiting tab (alias: `UDF_ISPURMNG`) |
| `UDF_ISDIRECTOR` | Director — sees Purchase; status-tab rules **TBD** (no extra hides yet) |
| `UDF_SSTAFF` | Sales staff only (quotations; **no** Purchase) |

Truthy: `1`, `Y`, `YES`, `T`, `TRUE`, `ON`, `-1`.

**Ignored (no access effect):** `UDF_MANAGEMENT`, `UDF_PMANAGEMENT`, `UDF_PUSER`, `UDF_SMANAGEMENT`, `UDF_SUSER`.

---

## View e-PR status tab limits

| Status tab | Admin | HOD | Purch Mgr | Director |
|------------|-------|-----|-----------|----------|
| Draft | Full | See / limited* | Full | TBD (all tabs shown for now) |
| Awaiting Approval | Full | **Primary** — can move → Pending | **Hidden** | TBD |
| Pending | Full | **View only** (no transfer / line approve) | **Full** | TBD |
| Approved | Full | View only (no transfer) | Full | TBD |
| Cancelled | Full | View | Per purch rules | TBD |

\*HOD on Draft: treat as view/limited unless product says otherwise.

### Actions (same idea — only inside those tabs)

| Action | Admin | HOD | Purch Mgr | Director |
|--------|-------|-----|-----------|----------|
| See Purchase menu | Yes | Yes | Yes | Yes |
| See Awaiting tab | Yes | Yes | **No** | Yes (until TBD) |
| Awaiting → Pending | Yes | **Yes** | N/A | TBD |
| Line approvals / transfer on Pending | Yes | **No** | Yes | TBD (allowed until defined) |

---

## Priority when multiple flags are set

1. `UDF_ISADMIN` → `full_admin`
2. `UDF_ISPURMGR` → `purchasing_management`
3. `UDF_ISHOD` → `hod`
4. `UDF_ISDIRECTOR` → `director`
5. `UDF_SSTAFF` → `sales_staff`

Any of the four purchase flags → Purchase visible; priority only picks which tab/action rules apply.

---

## Code (`utils/role_permissions.py`)

- Gate: `can_see_view_pr` / `can_access_purchase_menu`
- Tab: `hide_pr_awaiting_tab` (Purch Mgr only)
- Actions: `hide_pr_transfer_for_pstaff`, `hide_pr_approval_edits_for_pstaff` (HOD)

---

## Change log

| Date | Note |
|------|------|
| 2026-10-29 | Four Role Selection flags; legacy five UDFs ignored. |
| 2026-10-29 | Clarify: all four see Purchase; only View e-PR status tabs/actions are limited. |
