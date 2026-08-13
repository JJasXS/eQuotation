"""Stock batch resolution for Create e-PR dimensions (GET/POST /batch)."""
from __future__ import annotations

from utils.procurement_pr_sql_api import build_sdsdocdetail_line
from utils.sql_api_batch import (
    attach_batch_codes_to_lines,
    build_batch_code,
    build_create_batch_payload,
)


def test_build_batch_code_format():
    assert build_batch_code("12", "100", "500") == "12mm*100mm*500mm"
    assert build_batch_code(12, 100, 500) == "12mm*100mm*500mm"
    assert build_batch_code("12.0", "100.00", "500") == "12mm*100mm*500mm"
    assert build_batch_code("12.5", "100", "500") == "12.5mm*100mm*500mm"


def test_build_batch_code_missing_dimension():
    assert build_batch_code("", "100", "500") == ""
    assert build_batch_code("12", None, "500") == ""
    assert build_batch_code("12", "100", "0") == ""
    assert build_batch_code("0", "100", "500") == ""


def test_attach_reuses_existing_batch_without_post(monkeypatch):
    posts: list[dict] = []

    monkeypatch.setattr(
        "utils.sql_api_batch.load_sql_accounting_api_settings",
        lambda: type(
            "S",
            (),
            {"access_key": "ak", "secret_key": "sk"},
        )(),
    )
    monkeypatch.setattr("utils.sql_api_batch._batch_path", lambda: "/batch")
    monkeypatch.setattr(
        "utils.sql_api_batch.fetch_batches",
        lambda force_refresh=False: [
            {
                "autokey": 12,
                "code": "12mm*100mm*500mm",
                "udf_thickness": "12",
                "udf_width": "100",
                "udf_length": "500",
            }
        ],
    )
    monkeypatch.setattr(
        "utils.sql_api_batch.create_batch",
        lambda *a, **k: posts.append({"a": a, "k": k}) or {"code": "SHOULD_NOT"},
    )

    lines = [
        {
            "itemCode": "AL 6061-T6 ANOZ PL: 12.0MM",
            "udf_thickness": "12",
            "udf_width": "100",
            "udf_length": "500",
            "stockDetail": {
                "CODE": "AL 6061-T6 ANOZ PL: 12.0MM",
                "DESCRIPTION": "AL 6061-T6 ANOZ PL: 12.0MM",
            },
        }
    ]
    attach_batch_codes_to_lines(lines)
    assert lines[0]["batch"] == "12mm*100mm*500mm"
    assert posts == []


def test_attach_creates_missing_batch(monkeypatch):
    posts: list[dict] = []

    monkeypatch.setattr(
        "utils.sql_api_batch.load_sql_accounting_api_settings",
        lambda: type(
            "S",
            (),
            {"access_key": "ak", "secret_key": "sk"},
        )(),
    )
    monkeypatch.setattr("utils.sql_api_batch._batch_path", lambda: "/batch")
    monkeypatch.setattr("utils.sql_api_batch.fetch_batches", lambda force_refresh=False: [])

    def _fake_create(code, *, thickness, width, length, stock):
        payload = build_create_batch_payload(
            code, thickness=thickness, width=width, length=length, stock=stock
        )
        posts.append(payload)
        return payload

    monkeypatch.setattr("utils.sql_api_batch.create_batch", _fake_create)

    lines = [
        {
            "itemCode": "AL 6061-T6 ANOZ PL: 12.0MM",
            "udf_thickness": "12",
            "udf_width": "100",
            "udf_length": "500",
            "stockDetail": {
                "CODE": "AL 6061-T6 ANOZ PL: 12.0MM",
                "DESCRIPTION": "AL 6061-T6 ANOZ PL: 12.0MM",
                "udf_dp": "0.78",
                "udf_dfp": "1000000",
                "udf_wtp": "0.39",
            },
        }
    ]
    attach_batch_codes_to_lines(lines)
    assert lines[0]["batch"] == "12mm*100mm*500mm"
    assert len(posts) == 1
    body = posts[0]
    assert body["code"] == "12mm*100mm*500mm"
    assert body["udf_thickness"] == "12"
    assert body["udf_width"] == "100"
    assert body["udf_length"] == "500"
    assert body["batchitem"] == [{"itemcode": "AL 6061-T6 ANOZ PL: 12.0MM"}]
    assert body["docnosetkey"] is None
    assert body["description"] == "AL 6061-T6 ANOZ PL: 12.0MM"
    assert body["udf_dp"] == "0.78"
    assert body["udf_ds"] == "0.78"  # falls back to udf_dp
    assert body["udf_wtp"] == "0.39"


def test_build_sdsdocdetail_line_emits_batch(monkeypatch):
    monkeypatch.setattr(
        "utils.stock_items_catalog.find_catalog_stock_item_prefer_sql_api",
        lambda **kwargs: {"CODE": kwargs.get("code") or "", "DESCRIPTION": kwargs.get("description") or ""},
    )
    monkeypatch.setattr("utils.stock_items_catalog.fetch_stock_item_sql_api_by_code", lambda _c: None)
    monkeypatch.setattr("utils.stock_items_catalog._firebird_stock_row_for_code", lambda _c: {})

    row = build_sdsdocdetail_line(
        {
            "itemCode": "AL 6061-T6 ANOZ PL: 12.0MM",
            "itemName": "AL 6061-T6 ANOZ PL: 12.0MM",
            "qtySqty": 1,
            "qtySuomqty": 0,
            "unitPrice": 0,
            "batch": "12mm*100mm*500mm",
            "udf_thickness": "12",
            "udf_width": "100",
            "udf_length": "500",
        },
        seq=1,
        header_project="----",
        default_delivery=None,
    )
    assert row.get("batch") == "12mm*100mm*500mm"


def test_edited_thickness_beats_catalog_in_sdsdocdetail(monkeypatch):
    def _fake_detail(c):
        return {
            "CODE": c,
            "UDF_THICKNESS": "10",
            "UDF_WIDTH": "1000",
            "UDF_LENGTH": "2000",
        }

    monkeypatch.setattr(
        "utils.stock_items_catalog.find_catalog_stock_item_prefer_sql_api",
        lambda **kwargs: {"CODE": kwargs.get("code") or ""},
    )
    monkeypatch.setattr("utils.stock_items_catalog.fetch_stock_item_sql_api_by_code", _fake_detail)
    monkeypatch.setattr("utils.stock_items_catalog._firebird_stock_row_for_code", lambda _c: {})

    row = build_sdsdocdetail_line(
        {
            "itemCode": "AL 6061-T6 ANOZ PL: 10.0MM",
            "itemName": "AL 6061-T6 ANOZ PL: 10.0MM",
            "qtySqty": 1,
            "qtySuomqty": 0,
            "unitPrice": 0,
            "udf_thickness": "12",
            "udf_width": "100",
            "udf_length": "500",
            "batch": "12mm*100mm*500mm",
        },
        seq=1,
        header_project="----",
        default_delivery=None,
    )
    assert row.get("udf_thickness") == "12"
    assert row.get("udf_width") == "100"
    assert row.get("udf_length") == "500"
    assert row.get("batch") == "12mm*100mm*500mm"
