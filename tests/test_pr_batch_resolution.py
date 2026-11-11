"""Stock batch resolution for Create e-PR dimensions (GET/POST /batch)."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

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


def test_parse_batch_code_dimensions():
    from utils.sql_api_batch import parse_batch_code_dimensions

    assert parse_batch_code_dimensions("12mm*100mm*500mm") == ("12", "100", "500")
    assert parse_batch_code_dimensions("12.5mm*100mm*500mm") == ("12.5", "100", "500")
    assert parse_batch_code_dimensions("") == ("", "", "")
    assert parse_batch_code_dimensions("junk") == ("", "", "")


def test_build_batch_code_missing_dimension():
    assert build_batch_code("", "100", "500") == ""
    assert build_batch_code("12", None, "500") == ""
    assert build_batch_code("12", "100", "0") == ""
    assert build_batch_code("0", "100", "500") == ""


def test_attach_reuses_existing_batch_without_post(monkeypatch):
    posts: list[dict] = []
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "false")

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
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Rest")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "false")

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
    monkeypatch.setattr(
        "utils.stock_items_catalog._firebird_stock_row_for_code",
        lambda _c, db_cur=None: {},
    )

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
    monkeypatch.setattr(
        "utils.stock_items_catalog._firebird_stock_row_for_code",
        lambda _c, db_cur=None: {},
    )

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


def test_fb_row_to_rest_maps_decimals_and_batchitem():
    from utils.sql_api_batch import _fb_row_to_rest

    mapped = _fb_row_to_rest(
        ["AUTOKEY", "CODE", "UDF_THICKNESS", "ISACTIVE"],
        (12, "12mm*100mm*500mm", Decimal("12"), True),
        batchitem=[{"itemcode": "AL-1"}],
    )
    assert mapped["autokey"] == 12
    assert mapped["code"] == "12mm*100mm*500mm"
    assert mapped["udf_thickness"] == "12"
    assert mapped["isactive"] is True
    assert mapped["batchitem"] == [{"itemcode": "AL-1"}]
    assert mapped["docnosetkey"] is None


def test_fetch_batches_routes_to_firebird_under_block(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    from utils import sql_api_batch as batch_mod

    batch_mod._invalidate_batch_cache()
    with patch(
        "utils.sql_api_batch.fetch_batches_from_firebird",
        return_value=[{"code": "9mm*9mm*9mm"}],
    ) as mock_fb:
        with patch("utils.sql_api_batch.SqlAccountingApiClient") as mock_client:
            rows = batch_mod.fetch_batches(force_refresh=True)
    assert rows[0]["code"] == "9mm*9mm*9mm"
    mock_fb.assert_called_once()
    mock_client.assert_not_called()


def test_create_batch_routes_to_firebird_under_block(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    from utils import sql_api_batch as batch_mod

    with patch(
        "utils.sql_api_batch.create_batch_in_firebird",
        return_value={"code": "9mm*9mm*9mm", "autokey": 99},
    ) as mock_create:
        with patch("utils.sql_api_batch.SqlAccountingApiClient") as mock_client:
            out = batch_mod.create_batch(
                "9mm*9mm*9mm",
                thickness="9",
                width="9",
                length="9",
                stock={"CODE": "AL-1", "DESCRIPTION": "AL-1"},
            )
    assert out["code"] == "9mm*9mm*9mm"
    mock_create.assert_called_once()
    mock_client.assert_not_called()


def test_attach_creates_via_firebird_when_missing(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    monkeypatch.setenv("SQL_API_ACCESS_KEY", "")
    monkeypatch.setenv("SQL_API_SECRET_KEY", "")

    posts: list[str] = []
    monkeypatch.setattr(
        "utils.sql_api_batch.fetch_batches",
        lambda force_refresh=False: [],
    )

    def _fake_create(code, *, thickness, width, length, stock):
        posts.append(code)
        return {"code": code}

    monkeypatch.setattr("utils.sql_api_batch.create_batch", _fake_create)

    lines = [
        {
            "itemCode": "AL-1",
            "udf_thickness": "12",
            "udf_width": "100",
            "udf_length": "500",
            "stockDetail": {"CODE": "AL-1", "DESCRIPTION": "AL-1"},
        }
    ]
    attach_batch_codes_to_lines(lines)
    assert lines[0]["batch"] == "12mm*100mm*500mm"
    assert posts == ["12mm*100mm*500mm"]


def test_create_batch_in_firebird_reuses_existing(monkeypatch):
    from utils.sql_api_batch import create_batch_in_firebird

    existing = {
        "autokey": 12,
        "code": "12mm*100mm*500mm",
        "batchitem": [],
        "docnosetkey": None,
    }
    con = MagicMock()
    cur = MagicMock()
    con.cursor.return_value = cur
    monkeypatch.setattr("utils.sql_api_batch._open_batch_connection", lambda: con)
    monkeypatch.setattr("utils.sql_api_batch._table_exists", lambda _c, _t: True)
    monkeypatch.setattr(
        "utils.sql_api_batch._fetch_st_batch_by_code",
        lambda _c, _code: existing,
    )

    out = create_batch_in_firebird(
        "12mm*100mm*500mm",
        thickness="12",
        width="100",
        length="500",
        stock={"CODE": "AL-1"},
    )
    assert out == existing
    cur.execute.assert_not_called()


def test_create_batch_in_firebird_rejects_overlong_code():
    from utils.sql_api_batch import SqlApiBatchError, create_batch_in_firebird

    with pytest.raises(SqlApiBatchError, match="length 30"):
        create_batch_in_firebird(
            "1234567890123456789012345678901",
            thickness="1",
            width="2",
            length="3",
            stock=None,
        )


def test_attach_fail_soft_on_fetch_error(monkeypatch):
    monkeypatch.setenv("SQL_ACCOUNTING_MASTER_READ_PROVIDER", "Firebird")
    monkeypatch.setenv("SQL_ACCOUNTING_BLOCK_REST_HTTP", "true")
    from utils.sql_api_batch import SqlApiBatchError

    monkeypatch.setattr(
        "utils.sql_api_batch.fetch_batches",
        lambda force_refresh=False: (_ for _ in ()).throw(SqlApiBatchError("boom")),
    )
    lines = [
        {
            "itemCode": "AL-1",
            "udf_thickness": "12",
            "udf_width": "100",
            "udf_length": "500",
        }
    ]
    out = attach_batch_codes_to_lines(lines)
    assert out[0].get("batch") in (None, "")
