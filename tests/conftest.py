"""Shared pytest setup for eQuotation tests/."""
from __future__ import annotations

import os
import sys

import pytest
from dotenv import load_dotenv


@pytest.fixture(scope="session", autouse=True)
def _equotation_tenant_env():
    """Load tenant + SQL API env before any test in this package (live API probes)."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    from utils.appsettings_env import apply_appsettings_to_environ
    from utils.tenant_bootstrap import apply_tenant_env_overrides

    apply_appsettings_to_environ()
    load_dotenv(os.path.join(root, ".env"), override=False)
    apply_tenant_env_overrides()
    yield
