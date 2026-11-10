"""Static checks for Create e-PR form message clear behavior (no DB / API writes)."""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "static" / "js" / "procurement" / "precurement_app.js"


def test_clear_purchase_request_message_helper_and_call_sites():
    src = SRC.read_text(encoding="utf-8")
    assert re.search(r"function clearPurchaseRequestMessage\s*\(", src)
    assert re.search(r"el\.style\.display\s*=\s*['\"]none['\"]", src)
    assert re.search(
        r"kind\s*===\s*['\"]error['\"][\s\S]{0,160}?clearPurchaseRequestMessage\s*\(\s*\)",
        src,
    )
    assert re.search(
        r"function initPurchaseRequestForm\s*\([\s\S]*?clearPurchaseRequestMessage\s*\(\s*\)",
        src,
    )
    assert re.search(
        r"selected\s*===\s*['\"]create['\"][\s\S]{0,240}?clearPurchaseRequestMessage\s*\(\s*\)",
        src,
    )
    assert re.search(
        r"clearPurchaseRequestMessage\s*\(\s*\)[\s\S]{0,240}?Failed to update purchase request",
        src,
    )
    assert re.search(
        r"clearPurchaseRequestMessage\s*\(\s*\)[\s\S]{0,240}?Failed to submit purchase request",
        src,
    )
    assert "Saving changes and submitting purchase request..." in src
    assert "Submitting purchase request..." in src
    assert "Saving draft purchase request..." in src
