# SY_USER role access rules (draft)

**Status:** Draft for implementation — not fully wired yet.  
**Date:** 2026-10-29  
**Source fields on `SY_USER`:**

| Column | Intended role |
|--------|----------------|
| `UDF_ISADMIN` | System admin — full access |
| `UDF_ISHOD` | Head of Department — admin login + Awaiting-focused workflow; approval view-only |
| `UDF_ISPURMNG` | Purchasing manager — Pending/Approved actions; no Awaiting tab |
| `UDF_ISDIRECTOR` | Director — **leave for later** (no rules yet) |

Truthy values (same as other UDF flags): `1`, `Y`, `YES`, `T`, `TRUE`, `ON`, `-1`.

---

## Gate: who can see View e-PR

**View e-PR is only available if at least one of these four flags is true:**

- `UDF_ISADMIN`
- `UDF_ISHOD`
- `UDF_ISPURMNG`
- `UDF_ISDIRECTOR`

**If all four are false:**

- User **cannot see View e-PR** (hide menu entry / Purchase → View e-PR).
- Direct URL / API list for View e-PR should **403 / redirect** (same gate server-side).
- They may still access other parts of the system only if other roles allow it — but **not** View e-PR.

```text
can_see_view_pr =
  ISADMIN OR ISHOD OR ISPURMNG OR ISDIRECTOR
```

(`ISDIRECTOR` counts for the gate even while Director tab/action rules are still TBD.)

---

## Priority when multiple flags are set

If a user has more than one of these flags, resolve **one primary role** in this order:

1. `UDF_ISADMIN`
2. `UDF_ISPURMNG`
3. `UDF_ISHOD`
4. `UDF_ISDIRECTOR` (future)

Do not grant a weaker role’s limits when a higher flag is on.

Having **any** of the four true is enough to **see** View e-PR; the priority list only picks **which** tab/action rules apply.

---

## Role summaries

### 1. `UDF_ISADMIN` — full system access

- Login as **admin** (admin carousel / staff path).
- **Full access** to the whole eQuotation admin surface:
  - Admin dashboard, Sales, Purchase, Pricing rules, ApprovalPO links, reports, etc.
- **View e-PR:** all tabs — Draft, Awaiting Approval, Pending, Approved, Cancelled.
- May create / edit drafts (per existing draft rules), move Awaiting → Pending, approve/reject lines, cancel (where product allows), transfer to PO, bulk actions — **no UI hide flags**.
- Location scope: unrestricted (bypass `UDF_LOCATION` limits), same as today’s full admin.

### 2. `UDF_ISHOD` — HOD (Awaiting owner; approval is view-only)

- Login as **admin**; can open the **whole admin login area** (menus / pages that staff admins see), but **Purchase approval actions are restricted**.
- **Main job:** View e-PR **Awaiting Approval**
  - Update header status on Awaiting rows (e.g. Awaiting → Pending, and other HOD-allowed status updates on that tab).
  - This is the tab HOD is in charge of.
- **Pending / Approved / Cancelled (and any “approval” surfaces):**
  - **View only** — may open PR detail and read bids / lines.
  - **Cannot** transfer to PO.
  - **Cannot** cancel (from Pending / post-submit paths that purchasing uses).
  - **Cannot** change line approvals / award decisions / bulk approve.
- May still see other admin modules as read/navigate unless a later pass narrows the hamburger (out of scope for this draft unless product says otherwise).
- Suggested UI flags (map into existing template context later):
  - Show **Awaiting Approval** tab (primary).
  - `perm_hide_pr_transfer = true`
  - `perm_hide_pr_approval_edits = true` (no line approve / Pending bulk edit)
  - Allow status patch only for transitions HOD owns (Awaiting → Pending; refine list in implementation).

### 3. `UDF_ISPURMNG` — purchasing manager (approval owner)

- Login as **admin**; Purchase menu available.
- **Do not show** View e-PR tab **Awaiting Approval** (HOD owns that queue).
- **Pending (and Approved as today):** **full purchasing access**
  - Line selection / approvals, header status updates on Pending, cancel where allowed, transfer to PO, bulk transfer / bulk approve as today’s purchasing management.
- Draft / Cancelled: follow same rules as current purchasing management unless product tightens later.
- Suggested UI flags:
  - Hide Awaiting tab in filter tabs + server `view_status=AWAITING` list denied or empty for this role.
  - `perm_hide_pr_transfer = false`
  - `perm_hide_pr_approval_edits = false`

### 4. `UDF_ISDIRECTOR` — reserved (still part of View e-PR gate)

- **Tab/action behaviour:** not defined yet — leave product rules for later.
- **Gate only:** once Director is productized, `UDF_ISDIRECTOR = true` alone should satisfy `can_see_view_pr` (see gate above). Until Director UX exists, prefer not relying on this flag alone in production data.

---

## View e-PR tab matrix (target)

| Tab | Admin (`ISADMIN`) | HOD (`ISHOD`) | Purch Mng (`ISPURMNG`) | Director |
|-----|-------------------|---------------|-------------------------|----------|
| Draft | Full | View / limited* | Full (purchasing) | TBD |
| Awaiting Approval | Full | **Primary — status update** | **Hidden** | TBD |
| Pending | Full | **View only** (no transfer / cancel / approve) | **Full** | TBD |
| Approved | Full | View only (no transfer) | Full | TBD |
| Cancelled | Full | View | View / full per purch rules | TBD |

\*HOD on Draft: confirm later (view vs edit). Default suggestion: view-only unless HOD also creates PRs.

---

## Action matrix (Purchase / View e-PR)

| Action | Admin | HOD | Purch Mng | Director |
|--------|-------|-----|-----------|----------|
| Open admin UI / Purchase menu | Yes | Yes | Yes | TBD |
| See Awaiting Approval tab | Yes | Yes | **No** | TBD |
| Change status Awaiting → Pending | Yes | **Yes** | No (tab hidden) | TBD |
| Edit line approvals / awards on Pending | Yes | **No** | Yes | TBD |
| Cancel PR (non-draft) | Yes | **No** | Yes | TBD |
| Transfer / bulk transfer to PO | Yes | **No** | Yes | TBD |
| Create e-PR / edit true Draft | Yes | TBD | Yes | TBD |
| Pricing priority / full Sales admin | Yes | TBD (likely no) | No | TBD |

---

## Mapping to current code (today vs target)

Today (`utils/role_permissions.py`) still keys off **legacy** SY_USER flags:

| Legacy column | Current tier |
|---------------|--------------|
| `UDF_MANAGEMENT` | `full_admin` |
| `UDF_PMANAGEMENT` | `purchasing_management` |
| `UDF_PUSER` | `purchase_staff` |
| … sales UDFs | sales tiers |

**Target columns** for this doc:

| New column | Suggested new / mapped tier |
|------------|-----------------------------|
| `UDF_ISADMIN` | `full_admin` (replace or alias `UDF_MANAGEMENT`) |
| `UDF_ISPURMNG` | `purchasing_management` (replace or alias `UDF_PMANAGEMENT`) |
| `UDF_ISHOD` | **New** tier e.g. `hod` / `purchasing_hod` — not present yet |
| `UDF_ISDIRECTOR` | Deferred |

Existing helpers to extend later:

- `compute_access_tier` / `SY_USER_UDF_COLUMN_TO_FLAG`
- `template_permission_context` → `perm_hide_pr_transfer`, `perm_hide_pr_approval_edits`
- View e-PR tabs in `templates/precurement/precurement.html` + `precurement_app.js` filter tabs
- API gates: `can_update_pr_approvals_and_header_status`, `can_patch_pr_workflow_status`, transfer endpoints

---

## Implementation checklist (when we build this)

1. Add `UDF_ISADMIN` / `UDF_ISHOD` / `UDF_ISPURMNG` / `UDF_ISDIRECTOR` to SY_USER flag map and login identity.
2. **`can_see_view_pr`:** `ISADMIN | ISHOD | ISPURMNG | ISDIRECTOR` — hide View e-PR menu + block page/API when all false.
3. Introduce `ACCESS_TIER_HOD` (or equivalent) with menu access like purch staff/admin but approval read-only.
4. Hide Awaiting tab + block `view_status=AWAITING` for `ISPURMNG`.
5. HOD: allow Awaiting status transitions only; force hide transfer + approval edits on Pending/Approved.
6. Align Admin hamburger: confirm whether HOD sees Sales / Pricing (draft assumes yes for “whole admin login”; tighten if needed).
7. Tests: all-four-false cannot open View e-PR; login tier resolution; tab visibility; transfer/cancel/approve API 403 for HOD; Awaiting forbidden for Purch Mng.
8. Director: add tab/action rules here when defined — do not invent behaviour beyond the gate.

---

## Open questions

1. May HOD **create / edit Draft** PRs, or only process Awaiting?
2. Should HOD see **Sales / quotations / pricing**, or Purchase only inside admin?
3. When both `ISHOD` and `ISPURMNG` are true, confirm priority (this draft: Purch Mng wins after Admin).
4. Exact Awaiting status transitions HOD may set (only → Pending, or also Cancelled?).
5. How `UDF_ISDIRECTOR` differs from Admin / HOD / Purch Mng (beyond being enough to see View e-PR).
6. If all four are false but legacy `UDF_PMANAGEMENT` / `UDF_PUSER` is true — cut over fully to the four flags, or keep a temporary legacy alias?

---

## Change log

| Date | Note |
|------|------|
| 2026-10-29 | Initial draft from product rules (Admin / HOD / Purch Mng / Director deferred). |
| 2026-10-29 | Gate: View e-PR only if any of the four flags is true; all false → no View e-PR. |
