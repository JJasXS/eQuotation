"""Ambiguous quotation create timeouts must not POST /salesquotation twice."""
from __future__ import annotations

from api.clients.sql_accounting_client import SqlAccountingApiError
from utils.quotation_api import create_or_update_quotation

CUSTOMER = "300-C0001"
DOC = "QT-80001"
CREATE_URL = "https://api.example/salesquotation"


class _Settings:
    access_key = "test-key"
    secret_key = "test-secret"
    timeout_seconds = 12.0
    quotation_create_path = "/salesquotation"

    def resolved_quotation_create_url(self):
        return CREATE_URL

    def resolved_quotation_update_url(self, dockey):
        return f"{CREATE_URL}/{int(dockey)}"


def _data(**extra):
    payload = {
        "companyName": "Example Co",
        "items": [{"itemCode": "ITEM-1", "description": "Line", "quantity": 1, "unitPrice": 1}],
    }
    payload.update(extra)
    return payload


def _install(monkeypatch, client, *, sl_qt=None, draft=None, header=None):
    monkeypatch.setattr("utils.quotation_api.load_sql_accounting_api_settings", lambda: _Settings())
    monkeypatch.setattr("utils.quotation_api.SqlAccountingApiClient", lambda _settings: client)
    monkeypatch.setattr(
        "utils.quotation_api._build_salesquotation_payload",
        lambda customer_code, data, doc_no: {"sdsdocdetail": [{"itemcode": "ITEM-1"}], "docno": doc_no},
    )
    monkeypatch.setattr("utils.quotation_api._local_precheck_quotation", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "utils.quotation_api._read_qt_sequences_from_db",
        lambda limit=2000: (1, set(), None),
    )
    monkeypatch.setattr("utils.quotation_api._next_qt_docno_candidate", lambda *args, **kwargs: DOC)
    monkeypatch.setattr("utils.quotation_api._wait_for_sl_qt_docno", lambda docno: sl_qt)
    monkeypatch.setattr(
        "utils.quotation_api._find_sl_qt_by_docno",
        lambda docno: sl_qt,
    )
    monkeypatch.setattr(
        "utils.quotation_api.save_draft_quotation",
        lambda *args, **kwargs: draft or {"success": True, "dockey": 44},
    )
    if header is not None:
        monkeypatch.setattr(
            "utils.quotation_api._read_sl_qt_header_for_sales_api",
            lambda dockey: header,
        )


def test_successful_post_returns_document_number(monkeypatch):
    class Client:
        posts = []

        def post_json(self, url, payload, timeout_seconds=None):
            self.posts.append(url)
            return 200, {"dockey": 7, "docno": DOC, "message": "Quotation created successfully"}, "{}"

    client = Client()
    _install(monkeypatch, client)
    result = create_or_update_quotation("http://local", CUSTOMER, _data())
    assert result["success"] is True
    assert result["docno"] == DOC
    assert result["dockey"] == 7
    assert client.posts == [CREATE_URL]


def test_timeout_with_sl_qt_row_succeeds_without_second_post(monkeypatch):
    class Client:
        posts = []

        def post_json(self, url, payload, timeout_seconds=None):
            self.posts.append(url)
            raise SqlAccountingApiError("The read operation timed out")

    client = Client()
    _install(monkeypatch, client, sl_qt={"dockey": 8, "docno": DOC})
    result = create_or_update_quotation("http://local", CUSTOMER, _data())
    assert result["success"] is True
    assert result["docno"] == DOC
    assert result["dockey"] == 8
    assert len(client.posts) == 1


def test_timeout_without_sl_qt_row_is_unconfirmed_and_posts_once(monkeypatch):
    class Client:
        posts = []

        def post_json(self, url, payload, timeout_seconds=None):
            self.posts.append((url, payload.get("docno")))
            raise SqlAccountingApiError("read timed out")

    client = Client()
    _install(monkeypatch, client, sl_qt=None)
    result = create_or_update_quotation("http://local", CUSTOMER, _data())
    assert result["success"] is False
    assert result["errorCode"] == "SQL_API_TIMEOUT"
    assert DOC in result["error"]
    assert "unconfirmed" in result["error"].lower()
    assert result.get("draftDockey") == 44
    assert len(client.posts) == 1


def test_gateway_504_without_record_does_not_post_again(monkeypatch):
    class Client:
        posts = []

        def post_json(self, url, payload, timeout_seconds=None):
            self.posts.append(url)
            return 504, None, "<!DOCTYPE html><html>Request Timed Out</html>"

    client = Client()
    _install(monkeypatch, client, sl_qt=None)
    result = create_or_update_quotation("http://local", CUSTOMER, _data())
    assert result["success"] is False
    assert result["errorCode"] == "SQL_API_TIMEOUT"
    assert len(client.posts) == 1


def test_existing_quotation_update_timeout_uses_put_once(monkeypatch):
    class Client:
        posts = []
        puts = []

        def post_json(self, url, payload, timeout_seconds=None):
            self.posts.append(url)
            raise AssertionError("update must not POST")

        def put_json(self, url, payload, timeout_seconds=None):
            self.puts.append(url)
            raise SqlAccountingApiError("read timed out")

    client = Client()
    _install(
        monkeypatch,
        client,
        header={"docno": DOC, "code": CUSTOMER, "updatecount": 2},
    )
    result = create_or_update_quotation(
        "http://local",
        CUSTOMER,
        _data(dockey=15),
    )
    assert result["success"] is False
    assert result["errorCode"] == "SQL_API_TIMEOUT"
    assert DOC in result["error"]
    assert client.posts == []
    assert client.puts == [f"{CREATE_URL}/15"]


def test_duplicate_document_number_tries_the_next_number(monkeypatch):
    class Client:
        posts = []

        def post_json(self, url, payload, timeout_seconds=None):
            self.posts.append(payload.get("docno"))
            if len(self.posts) == 1:
                return 500, {"message": "duplicate value for document no"}, "duplicate value for document no"
            return 200, {"dockey": 9, "docno": "QT-80002"}, "{}"

    client = Client()
    _install(monkeypatch, client)
    numbers = iter([DOC, "QT-80002"])
    monkeypatch.setattr("utils.quotation_api._next_qt_docno_candidate", lambda *args, **kwargs: next(numbers))
    result = create_or_update_quotation("http://local", CUSTOMER, _data())
    assert result["success"] is True
    assert result["docno"] == "QT-80002"
    assert client.posts == [DOC, "QT-80002"]


def test_other_http_failure_posts_once(monkeypatch):
    class Client:
        posts = []

        def post_json(self, url, payload, timeout_seconds=None):
            self.posts.append(url)
            return 500, {"message": "Operation aborted"}, "Operation aborted"

    client = Client()
    _install(monkeypatch, client)
    result = create_or_update_quotation("http://local", CUSTOMER, _data())
    assert result["success"] is False
    assert "HTTP 500" in result["error"]
    assert len(client.posts) == 1
