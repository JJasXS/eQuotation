"""SDK login fields filled from sdkConnections Secrets Manager JSON."""
from __future__ import annotations

import json
import os
from unittest.mock import patch

from utils.tenant_bootstrap import (
    _apply_sdk_connections_from_secrets,
    _fdb_basename,
    _pick_sdk_company,
)


def test_fdb_basename():
    assert _fdb_basename(r"C:\eStream\SQLAccounting\DB\ACC-ANOZ.FDB") == "ACC-ANOZ.FDB"
    assert _fdb_basename("ACC-ANOZ.FDB") == "ACC-ANOZ.FDB"


def test_pick_sdk_company_matches_basename():
    companies = [
        {"name": "OTHER", "database": "ACC-OTHER.FDB", "password": "x"},
        {"name": "ANOZ", "database": "ACC-ANOZ.FDB", "password": "y", "dcfPath": r"\\s\Share\SQLACC.DCF"},
    ]
    pick = _pick_sdk_company(companies, r"C:/eStream/SQLAccounting/DB/ACC-ANOZ.FDB")
    assert pick is not None
    assert pick["name"] == "ANOZ"


def test_apply_sdk_connections_fills_empty_env(monkeypatch):
    for key in (
        "SQLACC_SDK_DCF_PATH",
        "SQLACC_SDK_DATABASE_FILE",
        "SQLACC_SDK_USER",
        "SQLACC_SDK_PASSWORD",
        "SQLACC_SDK_SECRET_ID",
        "TENANT_BOOTSTRAP_SKIP_SECRETS",
    ):
        monkeypatch.delenv(key, raising=False)

    payload = {
        "companies": [
            {
                "name": "ANOZ",
                "dcfPath": r"\\192.168.100.201\Share\SQLACC.DCF",
                "database": "ACC-ANOZ.FDB",
                "username": "ADMIN",
                "password": "secret-admin",
            }
        ]
    }
    with patch(
        "utils.tenant_bootstrap._fetch_secret_string",
        return_value=json.dumps(payload),
    ):
        _apply_sdk_connections_from_secrets({}, tenant_code="TNT10004", db_path=r"D:\ACC\ACC-ANOZ.FDB")

    assert os.environ["SQLACC_SDK_DCF_PATH"] == r"\\192.168.100.201\Share\SQLACC.DCF"
    assert os.environ["SQLACC_SDK_DATABASE_FILE"] == "ACC-ANOZ.FDB"
    assert os.environ["SQLACC_SDK_USER"] == "ADMIN"
    assert os.environ["SQLACC_SDK_PASSWORD"] == "secret-admin"


def test_apply_sdk_connections_does_not_overwrite_env(monkeypatch):
    monkeypatch.setenv("SQLACC_SDK_PASSWORD", "keep-me")
    monkeypatch.setenv("SQLACC_SDK_USER", "LOCAL")
    monkeypatch.delenv("TENANT_BOOTSTRAP_SKIP_SECRETS", raising=False)

    payload = {
        "companies": [
            {
                "name": "ANOZ",
                "dcfPath": r"\\s\Share\SQLACC.DCF",
                "database": "ACC-ANOZ.FDB",
                "username": "ADMIN",
                "password": "from-aws",
            }
        ]
    }
    with patch(
        "utils.tenant_bootstrap._fetch_secret_string",
        return_value=json.dumps(payload),
    ):
        _apply_sdk_connections_from_secrets({}, tenant_code="TNT10004", db_path="ACC-ANOZ.FDB")

    assert os.environ["SQLACC_SDK_PASSWORD"] == "keep-me"
    assert os.environ["SQLACC_SDK_USER"] == "LOCAL"
