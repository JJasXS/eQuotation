"""APP=dev mid-session SY_USER role refresh and OTP gates."""
import os

from utils.app_mode import app_mode, is_dev_app, is_prod_app
from utils.sy_user_roles import mock_role_refresh_enabled, refresh_staff_session_roles


def _with_env(**kwargs):
    saved = {k: os.environ.get(k) for k in kwargs}
    try:
        for k, v in kwargs.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def _run_with_env(fn, **env):
    gen = _with_env(**env)
    next(gen)
    try:
        fn()
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_app_mode_defaults_to_prod():
    def _check():
        assert app_mode() == 'prod'
        assert is_prod_app() is True
        assert is_dev_app() is False

    _run_with_env(_check, APP=None, MOCK=None)


def test_app_mode_dev():
    def _check():
        assert app_mode() == 'dev'
        assert is_dev_app() is True
        assert mock_role_refresh_enabled() is True

    _run_with_env(_check, APP='dev', MOCK=None)


def test_app_mode_prod():
    def _check():
        assert app_mode() == 'prod'
        assert is_dev_app() is False
        assert mock_role_refresh_enabled() is False

    _run_with_env(_check, APP='prod', MOCK='true')


def test_refresh_skips_when_prod():
    def _check():
        session = {'user_email': 'a@b.com', 'user_type': 'admin', 'access_tier': 'full_admin'}
        assert refresh_staff_session_roles(session) is False

    _run_with_env(_check, APP='prod')


def test_refresh_skips_supplier_session():
    def _check():
        session = {'user_email': 'a@b.com', 'user_type': 'supplier', 'access_tier': 'supplier'}
        assert refresh_staff_session_roles(session) is False

    _run_with_env(_check, APP='dev')


def test_refresh_skips_customer_portal_session():
    """Customer tab login must not be overwritten by SY_USER admin flags in APP=dev."""
    def _check():
        session = {
            'user_email': 'customer@example.com',
            'user_type': 'user',
            'access_tier': 'customer',
            'customer_code': '300-Y0001',
        }
        assert refresh_staff_session_roles(session) is False
        assert session['access_tier'] == 'customer'
        assert session['user_type'] == 'user'

    _run_with_env(_check, APP='dev')
