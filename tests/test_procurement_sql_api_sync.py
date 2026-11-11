"""SQL API supplier overlay for purchase order / request PUT payloads."""
from utils.procurement_sql_api_sync import (
    _blank_header_supplier_fields,
    build_supplier_put_payload,
    merge_supplier_into_sql_api_document,
    sql_api_header_fields_from_supplier,
    sync_purchase_request_sql_api_after_awards,
)


def test_sql_api_header_fields_from_supplier():
    row = {
        "code": "400-J0001",
        "companyname": "JASON CORP",
        "creditterm": "30 Days",
        "currencycode": "----",
        "area": "----",
        "agent": "----",
    }
    hdr = sql_api_header_fields_from_supplier(row)
    assert hdr["code"] == "400-J0001"
    assert hdr["companyname"] == "JASON CORP"
    assert hdr["terms"] == "30 Days"
    assert hdr["currencycode"] == "----"


def test_merge_supplier_into_sql_api_document_preserves_lines():
    existing = {
        "dockey": 99,
        "docno": "PO-00099",
        "code": "----",
        "companyname": "",
        "sdsdocdetail": [{"dtlkey": 1, "itemcode": "A", "qty": "5"}],
    }
    supplier = {"code": "400-J0001", "companyname": "JASON CORP", "creditterm": "30 Days", "currencycode": "----"}
    merged = merge_supplier_into_sql_api_document(existing, supplier)
    assert merged["dockey"] == 99
    assert merged["code"] == "400-J0001"
    assert merged["companyname"] == "JASON CORP"
    assert merged["terms"] == "30 Days"
    assert len(merged["sdsdocdetail"]) == 1


def test_build_supplier_put_payload_maps_delivery_without_sdsbranch_on_pr():
    existing = {
        "dockey": 29,
        "docno": "PR-26060013",
        "changed": False,
        "updatecount": 3,
        "sdsdocdetail": [{"dtlkey": 1, "updatecount": 5, "itemcode": "X"}],
    }
    supplier = {
        "code": "400-U0001",
        "companyname": "UNION ALUMINIUM (SUZHOU) CO, LTD",
        "sdsbranch": [
            {
                "branchtype": "B",
                "branchname": "BILLING",
                "address1": "Add1",
                "postcode": "11500",
                "city": "Air Itam",
                "country": "CN",
            }
        ],
    }
    payload = build_supplier_put_payload(
        existing,
        supplier,
        include_lines=False,
        include_sdsbranch=False,
    )
    assert payload["daddress1"] == "Add1"
    assert payload["dcountry"] == "CN"
    assert payload["changed"] is False
    assert payload["updatecount"] == 3
    assert "sdsbranch" not in payload


def test_blank_header_supplier_fields_clears_vendor():
    doc = _blank_header_supplier_fields(
        {"dockey": 10, "code": "400-X", "companyname": "X", "companyname2": "Y"}
    )
    assert doc["code"] == "----"
    assert doc["companyname"] == ""
    assert doc["companyname2"] == ""
    assert doc["dockey"] == 10


def test_sync_after_awards_posts_when_missing(monkeypatch):
    local_body = {
        "dockey": 159,
        "docno": "PR-26060099",
        "docnoex": "PR-26060099",
        "code": "----",
        "companyname": "",
        "udf_status": "APPROVED",
        "docamt": "100.00",
        "sdsdocdetail": [
            {
                "dtlkey": 101,
                "itemcode": "A",
                "udf_supcode": "400-A",
                "udf_supname": "Supplier A",
            }
        ],
        "changed": False,
    }
    posts: list[dict] = []

    class _Settings:
        access_key = "ak"
        secret_key = "sk"
        timeout_seconds = 10.0
        host = "localhost"
        use_tls = False

    class _Client:
        def __init__(self, _settings):
            pass

        def post_json(self, _url, body, timeout_seconds=0):
            posts.append(dict(body))
            return 200, {"dockey": 159, "docno": "PR-26060099"}, "ok"

    monkeypatch.setattr(
        "utils.procurement_sql_api_sync.load_sql_accounting_api_settings",
        lambda: _Settings(),
    )
    monkeypatch.setattr("utils.procurement_sql_api_sync.SqlAccountingApiClient", _Client)
    monkeypatch.setattr(
        "utils.procurement_sql_api_sync._build_purchaserequest_body_from_local",
        lambda *_a, **_k: ("PR-26060099", local_body),
    )
    monkeypatch.setattr(
        "utils.procurement_sql_api_sync._get_document",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "utils.procurement_sql_api_sync._all_local_pqdtl_keys",
        lambda *_a, **_k: {101},
    )

    result = sync_purchase_request_sql_api_after_awards(159, keep_dtlkeys={101})
    assert result["synced"] is True
    assert result["mode"] == "post"
    assert result["dockey"] == 159
    assert result["docno"] == "PR-26060099"
    assert len(posts) == 1
    assert posts[0]["dockey"] == 159
    assert posts[0]["docno"] == "PR-26060099"
    assert posts[0]["code"] == "----"
    assert posts[0]["sdsdocdetail"][0]["udf_supcode"] == "400-A"


def test_sync_after_awards_puts_same_dockey_when_exists(monkeypatch):
    local_body = {
        "dockey": 159,
        "docno": "PR-26060099",
        "udf_status": "APPROVED",
        "docamt": "250.00",
        "sdsdocdetail": [],
        "changed": False,
    }
    existing = {
        "dockey": 159,
        "docno": "PR-26060099",
        "code": "----",
        "companyname": "",
        "sdsdocdetail": [{"dtlkey": 101, "itemcode": "A", "unitprice": "1"}],
        "changed": False,
    }
    puts: list[tuple[int, dict]] = []

    class _Settings:
        access_key = "ak"
        secret_key = "sk"
        timeout_seconds = 10.0
        host = "localhost"
        use_tls = False

    class _Client:
        def __init__(self, _settings):
            pass

    monkeypatch.setattr(
        "utils.procurement_sql_api_sync.load_sql_accounting_api_settings",
        lambda: _Settings(),
    )
    monkeypatch.setattr("utils.procurement_sql_api_sync.SqlAccountingApiClient", _Client)
    monkeypatch.setattr(
        "utils.procurement_sql_api_sync._build_purchaserequest_body_from_local",
        lambda *_a, **_k: ("PR-26060099", local_body),
    )
    monkeypatch.setattr(
        "utils.procurement_sql_api_sync._get_document",
        lambda *_a, **_k: dict(existing),
    )
    monkeypatch.setattr(
        "utils.procurement_sql_api_sync._merge_local_pqdtl_prices_into_document",
        lambda document, *_a, **_k: {
            **document,
            "sdsdocdetail": [
                {
                    "dtlkey": 101,
                    "itemcode": "A",
                    "unitprice": "10",
                    "udf_supcode": "400-A",
                    "udf_supname": "Supplier A",
                }
            ],
        },
    )

    def _put(_client, *, base_path, dockey, payload, timeout_seconds):
        puts.append((int(dockey), dict(payload)))
        return 200, "ok"

    monkeypatch.setattr("utils.procurement_sql_api_sync._put_document", _put)

    result = sync_purchase_request_sql_api_after_awards(159, keep_dtlkeys={101})
    assert result["synced"] is True
    assert result["mode"] == "put"
    assert result["dockey"] == 159
    assert result["docno"] == "PR-26060099"
    assert len(puts) == 1
    put_dockey, put_body = puts[0]
    assert put_dockey == 159
    assert put_body["docno"] == "PR-26060099"
    assert put_body["code"] == "----"
    assert put_body["companyname"] == ""
    assert put_body["sdsdocdetail"][0]["udf_supcode"] == "400-A"
