"""Shared pytest setup for eQuotation tests/."""
from __future__ import annotations

import os
import sys

import pytest
from dotenv import load_dotenv


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _is_production_env() -> bool:
    flask_env = (os.getenv("FLASK_ENV") or os.getenv("EQ_ENV") or "").strip().lower()
    return flask_env in ("production", "prod") or _truthy(os.getenv("EQ_REQUIRE_SECURE_COOKIES"))


# Isolated unit tests default to skipping live tenant bootstrap. Opt into live
# bootstrap with EQ_FORCE_TENANT_BOOTSTRAP=1. Production app code never reads this.
if not _truthy(os.getenv("EQ_FORCE_TENANT_BOOTSTRAP")) and "EQ_SKIP_TENANT_BOOTSTRAP" not in os.environ:
    os.environ["EQ_SKIP_TENANT_BOOTSTRAP"] = "1"


@pytest.fixture(scope="session", autouse=True)
def _equotation_tenant_env():
    """Load tenant + SQL API env before live API probes.

    Set EQ_SKIP_TENANT_BOOTSTRAP=1 for isolated unit tests only.
    This skip is refused when FLASK_ENV/EQ_ENV is production.
    """
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if root not in sys.path:
        sys.path.insert(0, root)

    if _truthy(os.getenv("EQ_SKIP_TENANT_BOOTSTRAP")):
        if _is_production_env():
            raise RuntimeError(
                "EQ_SKIP_TENANT_BOOTSTRAP cannot be used when FLASK_ENV/EQ_ENV is production. "
                "Tenant bootstrap must run in production."
            )
        # Still load non-secret local .env defaults when present; skip network bootstrap.
        load_dotenv(os.path.join(root, ".env"), override=False)
        yield
        return

    from utils.appsettings_env import apply_appsettings_to_environ
    from utils.tenant_bootstrap import apply_tenant_env_overrides

    apply_appsettings_to_environ()
    load_dotenv(os.path.join(root, ".env"), override=False)
    apply_tenant_env_overrides()
    yield
