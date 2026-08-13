#!/usr/bin/env python3
"""Remove route handlers from main.py that now live in routes/* blueprints."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

TARGETS = [
    "login",
    "sign_in_guest",
    "logout",
    "proxy_delete_order_detail",
    "proxy_get_orders_by_status",
    "proxy_update_order_status",
    "proxy_get_order_details",
    "proxy_update_order_detail",
    "proxy_insert_order_detail",
    "proxy_request_order_change",
    "proxy_get_order_remarks",
    "admin_procurement_module",
    "admin_procurement_legacy_typo_redirect",
    "admin_procurement_bidding_page",
    "supplier_bidding_page",
]


def find_ranges(lines: list[str]) -> list[tuple[int, int, str]]:
    ranges: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for i, line in enumerate(lines):
        for name in TARGETS:
            if name in seen:
                continue
            if line.startswith(f"def {name}(") or line.startswith(f"def {name} ("):
                start = i
                j = i - 1
                while j >= 0 and (lines[j].startswith("@") or lines[j].strip() == ""):
                    if lines[j].startswith("@"):
                        start = j
                    j -= 1
                k = i + 1
                while k < len(lines):
                    if lines[k].startswith("def ") or lines[k].startswith("@"):
                        break
                    k += 1
                ranges.append((start, k, name))
                seen.add(name)
    ranges.sort(key=lambda r: r[0])
    return ranges


def main() -> None:
    lines = MAIN.read_text(encoding="utf-8").splitlines(keepends=True)
    ranges = find_ranges(lines)
    if len(ranges) < 10:
        raise SystemExit(f"Expected many targets, found {[r[2] for r in ranges]}")
    for start, end, name in ranges:
        print(f"remove {name}: L{start + 1}-L{end}")

    for start, end, _ in reversed(ranges):
        del lines[start:end]

    joined = "".join(lines)
    marker = "app.register_blueprint(quotation_approved_bp)\n"
    if "register_php_proxy_routes" not in joined:
        if marker not in joined:
            raise SystemExit("marker not found")
        registration = (
            "app.register_blueprint(quotation_approved_bp)\n"
            "\n"
            "from routes.php_proxy_routes import register_php_proxy_routes\n"
            "from routes.auth_routes import register_auth_routes\n"
            "from routes.procurement_routes import register_procurement_routes\n"
            "\n"
            "register_auth_routes(app)\n"
            "register_php_proxy_routes(\n"
            "    app,\n"
            "    proxy_post=proxy_post_with_auth,\n"
            "    proxy_get=proxy_get_with_auth,\n"
            "    http_request_json=http_request_json,\n"
            "    base_api_url=BASE_API_URL,\n"
            "    endpoint_paths=ENDPOINT_PATHS,\n"
            "    require_api_auth=require_api_auth,\n"
            ")\n"
            "register_procurement_routes(\n"
            "    app,\n"
            "    require_page_access=require_page_access,\n"
            "    render_protected_template=render_protected_template,\n"
            "    procurement_ui_path=PROCUREMENT_UI_PATH,\n"
            ")\n"
        )
        joined = joined.replace(marker, registration, 1)

    MAIN.write_text(joined, encoding="utf-8", newline="\n")
    print(f"main.py now {joined.count(chr(10)) + 1} lines")


if __name__ == "__main__":
    main()
