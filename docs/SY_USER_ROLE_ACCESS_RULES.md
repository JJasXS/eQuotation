# SY_USER role access rules

**Status:** Wired for Purchase / View e-PR gate and primary tiers.  
**Date:** 2026-10-29  
**Source fields on `SY_USER`:**

| Column | Role |
|--------|------|
| `UDF_ISADMIN` | System admin — full access |
| `UDF_ISHOD` | Head of Department — Awaiting-focused; approval view-only |
| `UDF_ISPURMNG` | Purchasing manager — Pending/Approved actions; no Awaiting tab |
| `UDF_ISDIRECTOR` | Director — **gate only** (tab/action rules TBD) |

Truthy values (same as other UDF flags): `1`, `Y`, `YES`, `T`, `TRUE`, `ON`, `-1`.

**Legacy ignored (no longer grant Purchase / View e-PR or full admin):**  
`UDF_MANAGEMENT`, `UDF_PMANAGEMENT`, `UDF_PUSER`.

Sales roles unchanged: `UDF_SMANAGEMENT`, `UDF_SSTAFF`, `UDF_SUSER`.

---

## Gate: who can see View e-PR

**View e-PR / Purchase menu only if at least one of these four flags is true:**

- `UDF_ISADMIN`
- `UDF_ISHOD`
- `UDF_ISPURMNG`
- `UDF_ISDIRECTOR`

**If all four are false:**

- User **cannot see View e-PR** (hide Purchase menu).
- Direct URL / API list for View e-PR returns **403 / redirect**.
- They may still access Sales / other areas if sales UDFs allow it.

```text
can_see_view_pr =
  ISADMIN OR ISHOD OR ISPURMNG OR ISDIRECTOR
```

(`ISDIRECTOR` counts for the gate even while Director tab/action rules are still TBD.)

---

## Priority when multiple flags are set

1. `UDF_ISADMIN` → `full_admin`
2. `UDF_SMANAGEMENT` → `sales_management` (sales; no Purchase unless also a purchase flag)
3. `UDF_ISPURMNG` → `purchasing_management`
4. `UDF_ISHOD` → `hod`
5. `UDF_ISDIRECTOR` → `director`
6. `UDF_SSTAFF` / `UDF_SUSER` → `sales_staff`

Having **any** of the four purchase flags true is enough to **see** View e-PR; the priority list picks **which** tab/action rules apply.

---

## Role summaries

### 1. `UDF_ISADMIN` — full system access

- Admin dashboard, Sales, Purchase, Pricing rules, ApprovalPO, etc.
- View e-PR: all tabs.
- Location scope: unrestricted.

### 2. `UDF_ISHOD` — HOD

- Purchase menu; Awaiting Approval is primary.
- Pending / Approved: view only — no transfer, no line approval edits.
- May patch Awaiting → Pending.

### 3. `UDF_ISPURMNG` — purchasing manager

- Purchase menu; **Awaiting Approval tab hidden**.
- Pending / Approved: full purchasing access (approvals, transfer).

### 4. `UDF_ISDIRECTOR` — reserved

- Satisfies View e-PR gate; tab/action behaviour still TBD (transfer/approvals currently hidden like HOD until productized).

---

## Mapping in code (`utils/role_permissions.py`)

| Column | Tier / helper |
|--------|----------------|
| `UDF_ISADMIN` | `full_admin` |
| `UDF_ISPURMNG` | `purchasing_management` |
| `UDF_ISHOD` | `hod` |
| `UDF_ISDIRECTOR` | `director` |

Helpers: `can_see_view_pr`, `can_access_purchase_menu`, `hide_pr_awaiting_tab`, `hide_pr_transfer_for_pstaff`, `hide_pr_approval_edits_for_pstaff`.

---

## Change log

| Date | Note |
|------|------|
| 2026-10-29 | Initial draft from product rules. |
| 2026-10-29 | Gate: View e-PR only if any of the four flags is true. |
| 2026-10-29 | Cut over: drop legacy MANAGEMENT / PMANAGEMENT / PUSER; wire four Role Selection flags. |
