#!/usr/bin/env python3
"""Capture eQuotation UI screenshots for the user guide.

Requires EQ_GUIDE_CAPTURE=1 on the server.

Env:
  EQ_GUIDE_BASE_URL=http://127.0.0.1:8881
  EQ_GUIDE_PR_ID=60                 (optional; default from seed)
  EQ_GUIDE_CUSTOMER_CODE=300-L0001
  EQ_GUIDE_SUPPLIER_CODE=400-J0001
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "images" / "user-guide"

CUSTOMER_CODE = (os.getenv("EQ_GUIDE_CUSTOMER_CODE") or "300-L0001").strip()
SUPPLIER_CODE = (os.getenv("EQ_GUIDE_SUPPLIER_CODE") or "400-J0001").strip()
PR_ID = (os.getenv("EQ_GUIDE_PR_ID") or "60").strip()

PUBLIC_SHOTS = [
    ("/login", "01-login.png"),
    ("/signInGuest", "02-guest-signin.png"),
]


def _seed_session(page, base: str, role: str, **extra) -> None:
    payload = {"role": role, "email": f"guide-{role}@local"}
    payload.update(extra)
    resp = page.request.post(
        f"{base}/api/guide_capture_login",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
    )
    if resp.status == 404:
        raise RuntimeError(
            "guide_capture_login returned 404. Start the app with EQ_GUIDE_CAPTURE=1."
        )
    if not resp.ok:
        raise RuntimeError(f"guide_capture_login failed ({resp.status}): {resp.text()[:300]}")
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"guide_capture_login unsuccessful: {body}")
    print(f"  Session seeded as {role} extras={extra} -> {body.get('redirect')}")


def _settle(page, ms: int = 1800) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass
    page.wait_for_timeout(ms)


def _click_first(page, selectors: list[str], wait_ms: int = 1200) -> bool:
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=5000)
                page.wait_for_timeout(wait_ms)
                return True
        except Exception:
            continue
    return False


def _capture(page, base: str, path: str, filename: str, created: list[str], after=None) -> None:
    url = f"{base}{path}"
    out = OUT_DIR / filename
    print(f"  Capturing {url} -> {filename}")
    page.goto(url, wait_until="domcontentloaded")
    _settle(page, 2000)
    if after:
        try:
            after(page)
            _settle(page, 1500)
        except Exception as exc:
            print(f"  WARNING: post-nav for {filename}: {exc}", file=sys.stderr)
    final = page.url
    if filename not in ("01-login.png", "02-guest-signin.png") and "/login" in final.split("?")[0]:
        print(f"  WARNING: still on login after navigating to {path}", file=sys.stderr)
    page.screenshot(path=str(out), full_page=True)
    created.append(filename)
    print(f"    saved {out.stat().st_size} bytes  url={final}")


def _after_customer_quotations(page) -> None:
    # Prefer auto-selected first card; otherwise click one.
    clicked = _click_first(
        page,
        [
            ".quotation-list-pane .quotation-card",
            ".quotation-list .quotation-card",
            "[data-dockey]",
            ".qt-list-item",
            ".list-card",
            ".quotation-card",
        ],
        wait_ms=2000,
    )
    if not clicked:
        page.wait_for_timeout(1500)


def _after_view_pr(page) -> None:
    # URL id= is often dropped by tab sync; force-select via page API.
    page.evaluate(
        """(prId) => {
          if (typeof selectViewPurchaseRequest === 'function') {
            selectViewPurchaseRequest(prId);
            return;
          }
          const el = document.querySelector(
            `.pr-view-pr-card[data-header-id="${prId}"] .pr-view-pr-card__main`
          );
          if (el) el.click();
        }""",
        PR_ID,
    )
    page.wait_for_timeout(500)
    try:
        page.locator("#view-pr-items-panel").wait_for(state="visible", timeout=10000)
        page.wait_for_function(
            """() => {
              const t = document.querySelector('#view-pr-items-panel');
              return t && !t.innerText.includes('No purchase request selected');
            }""",
            timeout=15000,
        )
    except Exception:
        pass
    page.wait_for_timeout(1500)


def _after_admin_bidding(page) -> None:
    _click_first(
        page,
        [
            f'[data-dockey="{PR_ID}"]',
            f'[data-request-id="{PR_ID}"]',
            ".bidding-pr-card",
            ".pr-bid-list-item",
            ".bid-pr-item",
            "button:has-text('PR-')",
            "div:has-text('PR-260600112')",
        ],
        wait_ms=2500,
    )
    # Expand comparison / bids section if collapsed
    _click_first(
        page,
        [
            "button:has-text('Compare')",
            "button:has-text('Bids')",
            "button:has-text('View bids')",
            ".bid-compare-tab",
        ],
        wait_ms=1500,
    )


def _after_supplier_bidding(page) -> None:
    _click_first(
        page,
        [
            f'[data-request-id="{PR_ID}"]',
            ".invite-card",
            ".invitation-card",
            ".supplier-invite-item",
            "button:has-text('PR-')",
            "div:has-text('PR-260600112')",
            ".invite-list-item",
        ],
        wait_ms=2500,
    )


def main() -> int:
    base = (os.getenv("EQ_GUIDE_BASE_URL") or "http://127.0.0.1:8881").rstrip("/")
    only = {
        x.strip()
        for x in (os.getenv("EQ_GUIDE_ONLY") or "").split(",")
        if x.strip()
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright is not installed.", file=sys.stderr)
        return 1

    print(f"Base URL: {base}")
    print(f"PR_ID={PR_ID} CUSTOMER={CUSTOMER_CODE} SUPPLIER={SUPPLIER_CODE}")
    print(f"Output:   {OUT_DIR}")
    if only:
        print(f"Only:     {sorted(only)}")
    else:
        for old in OUT_DIR.glob("*.png"):
            old.unlink()

    created: list[str] = []

    def want(name: str) -> bool:
        return (not only) or (name in only)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.set_default_timeout(60000)

        if want("01-login.png") or want("02-guest-signin.png"):
            for path, filename in PUBLIC_SHOTS:
                if want(filename):
                    try:
                        _capture(page, base, path, filename, created)
                    except Exception as exc:
                        print(f"  WARNING: failed {path}: {exc}", file=sys.stderr)

        # Admin shots
        admin_jobs = [
            ("/admin", "03-admin-dashboard.png", None),
            ("/admin/view-quotations", "06-admin-view-quotations.png", None),
            (f"/admin/procurement?tab=view&id={PR_ID}", "07-procurement-view-pr.png", _after_view_pr),
            ("/admin/procurement?tab=create", "08-procurement-create-pr.png", None),
            (
                f"/admin/procurement/bidding?id={PR_ID}&docno=PR-260600112",
                "09-admin-bidding.png",
                _after_admin_bidding,
            ),
            ("/admin/pending-approvals", "11-pending-approvals.png", None),
            ("/admin/invoice-aging", "12-invoice-aging.png", None),
        ]
        if any(want(fn) for _, fn, _ in admin_jobs):
            try:
                _seed_session(page, base, "admin")
                for path, filename, after in admin_jobs:
                    if want(filename):
                        try:
                            _capture(page, base, path, filename, created, after=after)
                        except Exception as exc:
                            print(f"  WARNING: failed {path}: {exc}", file=sys.stderr)
            except Exception as exc:
                print(f"  ERROR: admin session: {exc}", file=sys.stderr)

        # Customer shots
        customer_jobs = [
            ("/create-quotation", "04-create-quotation.png", None),
            ("/view-quotation", "05-my-quotations.png", _after_customer_quotations),
        ]
        if any(want(fn) for _, fn, _ in customer_jobs):
            try:
                _seed_session(page, base, "customer", customer_code=CUSTOMER_CODE)
                for path, filename, after in customer_jobs:
                    if want(filename):
                        try:
                            _capture(page, base, path, filename, created, after=after)
                        except Exception as exc:
                            print(f"  WARNING: failed {path}: {exc}", file=sys.stderr)
            except Exception as exc:
                print(f"  ERROR: customer session: {exc}", file=sys.stderr)

        # Supplier shots
        supplier_jobs = [
            (
                f"/supplier/bidding?request_id={PR_ID}",
                "10-supplier-bidding.png",
                _after_supplier_bidding,
            ),
        ]
        if any(want(fn) for _, fn, _ in supplier_jobs):
            try:
                _seed_session(page, base, "supplier", supplier_code=SUPPLIER_CODE)
                for path, filename, after in supplier_jobs:
                    if want(filename):
                        try:
                            _capture(page, base, path, filename, created, after=after)
                        except Exception as exc:
                            print(f"  WARNING: failed {path}: {exc}", file=sys.stderr)
            except Exception as exc:
                print(f"  ERROR: supplier session: {exc}", file=sys.stderr)

        browser.close()

    print(f"Created {len(created)} PNG(s):")
    for name in sorted(created):
        sz = (OUT_DIR / name).stat().st_size if (OUT_DIR / name).exists() else 0
        print(f"  - {name}  ({sz} bytes)")
    return 0 if created else 1


if __name__ == "__main__":
    raise SystemExit(main())
