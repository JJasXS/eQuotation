"""Gateway timeout responses from SQL Accounting stay structured JSON errors."""
from utils.quotation_api import _is_gateway_timeout, _timeout_failure


def test_html_504_is_gateway_timeout():
    raw = "<!DOCTYPE html><html><body>Request Timed Out</body></html>"
    assert _is_gateway_timeout(504, raw) is True


def test_html_timeout_page_without_504_is_gateway_timeout():
    raw = "<!DOCTYPE html><html><body>Request Timed Out</body></html>"
    assert _is_gateway_timeout(500, raw) is True


def test_json_error_is_not_treated_as_gateway_html():
    assert _is_gateway_timeout(500, '{"error":"nope"}') is False


def test_timeout_failure_is_json_safe_and_not_html():
    result = _timeout_failure("QT-80001", updating=False)
    assert result["success"] is False
    assert result["errorCode"] == "SQL_API_TIMEOUT"
    assert "<!DOCTYPE" not in result["error"]
    assert "QT-80001" in result["error"]
