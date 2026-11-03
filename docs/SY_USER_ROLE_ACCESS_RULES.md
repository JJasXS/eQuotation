# SY_USER role access rules

**Status:** Wired for Purchase / View e-PR.  
**Date:** 2026-11-03  

## Principle

**Roles = visibility.** Any of these open Purchase (menu, Create e-PR, View e-PR, all status tabs):

| Column | Tier |
|--------|------|
| `UDF_ISADMIN` | `full_admin` |
| `UDF_ISPURHOD` | `hod` |
| `UDF_ISPURMGR` (alias `UDF_ISPURMNG`) | `purchasing_management` |
| `UDF_ISPURUSER` | `purchase_user` |
| `UDF_ISDIRECTOR` | `director` |

**Approval UDFs = actions** (inside Purchase). Role alone does **not** grant approve / transfer.

| Column | Action |
|--------|--------|
| `UDF_APPROVEPQ` | Approve Purchase Requisition (Awaiting→Pending, line approvals) |
| `UDF_APPROVEPO` | Transfer to PO / PO approval |
| `UDF_APPROVEPR` | Returned (no screen yet — unused) |
| `UDF_APPROVEGR` / `UDF_APPROVEPI` | Unused (no GR / PI screens yet) |

`UDF_ISADMIN` bypasses approval UDFs (full actions).

### When roles / OTP are applied (`APP`)

| Phase | `APP` | Behaviour |
|-------|-------|-----------|
| **Production (live)** | `prod` (default if unset) | Roles loaded **once at OTP login**. Changing SY_USER needs **log out → log in**. OTP is **emailed** (not shown on the page). |
| **Developer testing** | `dev` | Roles **re-read from SY_USER** on each request. OTP is **shown on the login page** and **not emailed**. |

```text
can_see_purchase =
  ISADMIN OR ISPURHOD OR ISPURMGR OR ISPURUSER OR ISDIRECTOR

can_approve_requisition = ISADMIN OR APPROVEPQ
can_transfer_to_po      = ISADMIN OR APPROVEPO
```

---

## Source fields on `SY_USER`

Truthy: `1`, `Y`, `YES`, `T`, `TRUE`, `ON`, `-1`.

**Ignored for Purchase visibility:** other dept roles (sales/prod/store/QA/finance/tech), plus legacy `UDF_MANAGEMENT`, `UDF_PMANAGEMENT`, `UDF_PUSER`, `UDF_SMANAGEMENT`, `UDF_SUSER`.

`UDF_SSTAFF` = sales staff only (quotations; **no** Purchase).

---

## View e-PR

| Status tab | All purchase roles |
|------------|--------------------|
| Draft / Awaiting / Pending / Approved / Cancelled | **Visible** (no role-based tab hide) |

| Action | Who |
|--------|-----|
| See Purchase menu | Any purchase role |
| Draft → Submit / Cancel draft | Any purchase role |
| Awaiting → Pending / line approve | `UDF_APPROVEPQ` or admin |
| Transfer to PO | `UDF_APPROVEPO` or admin |

---

## Priority when multiple role flags are set

1. `UDF_ISADMIN` → `full_admin`
2. `UDF_ISPURMGR` → `purchasing_management`
3. `UDF_ISPURHOD` → `hod`
4. `UDF_ISDIRECTOR` → `director`
5. `UDF_ISPURUSER` → `purchase_user`
6. `UDF_SSTAFF` → `sales_staff`

Any purchase role → Purchase visible; approval UDFs gate actions.

---

## Code (`utils/role_permissions.py`)

- Visibility: `can_see_view_pr` / `can_access_purchase_menu`
- Actions: `can_approve_purchase_requisition` (`APPROVEPQ`), `can_transfer_pr_to_po` (`APPROVEPO`)
- UI hides: `hide_pr_awaiting_tab` always false; transfer/approval edits hide when approval UDF missing

---

## Change log

| Date | Note |
|------|------|
| 2026-10-29 | Four Role Selection flags; legacy five UDFs ignored. |
| 2026-10-29 | Clarify: all four see Purchase; only View e-PR status tabs/actions are limited. |
| 2026-10-30 | Purchase HOD uses `UDF_ISPURHOD` (not generic `UDF_ISHOD`); other dept HODs ignored. |
| 2026-11-03 | Roles = visibility only (incl. `ISPURUSER`); actions gated by `APPROVEPQ` / `APPROVEPO`; no role-based Awaiting tab hide. |
