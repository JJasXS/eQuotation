"""Content-hash CSS cache busting for templates."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from utils.static_assets import (
    clear_static_asset_hash_cache,
    css_url,
    static_file_content_hash,
    versioned_static_url,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'templates'
STATIC_CSS = ROOT / 'static' / 'css'


def test_css_url_uses_content_hash():
    clear_static_asset_hash_cache()
    digest = static_file_content_hash('css/equotationIcyTheme.css')
    assert re.fullmatch(r'[0-9a-f]{12}', digest)
    assert css_url('css/equotationIcyTheme.css') == (
        f'/static/css/equotationIcyTheme.css?v={digest}'
    )
    assert versioned_static_url('css/hamburger_menu.css').startswith(
        '/static/css/hamburger_menu.css?v='
    )


def test_css_url_changes_when_file_content_changes(tmp_path):
    clear_static_asset_hash_cache()
    css_dir = tmp_path / 'css'
    css_dir.mkdir()
    target = css_dir / 'probe.css'
    target.write_text('body{color:red}', encoding='utf-8')
    first = css_url('css/probe.css', static_root=str(tmp_path))
    target.write_text('body{color:blue}', encoding='utf-8')
    clear_static_asset_hash_cache()
    second = css_url('css/probe.css', static_root=str(tmp_path))
    assert first != second
    assert first.startswith('/static/css/probe.css?v=')
    assert second.startswith('/static/css/probe.css?v=')


def test_shared_css_hash_is_stable_across_calls():
    clear_static_asset_hash_cache()
    a = css_url('css/adminViewQuotations.css')
    b = css_url('css/adminViewQuotations.css')
    assert a == b


def test_templates_use_css_url_helper_only():
    hard = re.compile(
        r'''href=["'](?:/static/css/|\{\{\s*url_for\(\s*['"]static['"])'''
        r'''|href=["'][^"']*\.css\?v=''',
        re.I,
    )
    helper = re.compile(r"""css_url\(\s*['"]css/[^'"]+\.css['"]\s*\)""")
    offenders = []
    helpers = 0
    for path in TEMPLATES.rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        if hard.search(text):
            offenders.append(str(path.relative_to(ROOT)))
        helpers += len(helper.findall(text))
    assert not offenders, f'hardcoded CSS hrefs remain: {offenders}'
    assert helpers >= 20


def test_flask_registers_css_url_as_jinja_global(monkeypatch):
    monkeypatch.setenv('FLASK_SECRET_KEY', 'x' * 40)
    monkeypatch.setenv('EQ_REQUIRE_SECURE_COOKIES', '0')
    import main as main_mod

    assert 'css_url' in main_mod.app.jinja_env.globals
    assert callable(main_mod.app.jinja_env.globals['css_url'])


def test_flask_renders_versioned_css_on_login(monkeypatch):
    monkeypatch.setenv('FLASK_SECRET_KEY', 'x' * 40)
    monkeypatch.setenv('EQ_REQUIRE_SECURE_COOKIES', '0')
    # Import after env so app config accepts local secret.
    import main as main_mod

    clear_static_asset_hash_cache()
    digest = static_file_content_hash('css/login.css')
    client = main_mod.app.test_client()
    resp = client.get('/login')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert f'/static/css/login.css?v={digest}' in html
    assert f'/static/css/equotationIcyTheme.css?v=' in html
    # Helper fully evaluated — raw token must not leak into HTML.
    assert 'css_url(' not in html
    # No manual date tags left on CSS links.
    assert not re.search(r'/static/css/[^\"\']+\.css\?v=20\d{6}_', html)


def test_key_pages_render_without_undefined_css_url(monkeypatch):
    monkeypatch.setenv('FLASK_SECRET_KEY', 'x' * 40)
    monkeypatch.setenv('EQ_REQUIRE_SECURE_COOKIES', '0')
    import main as main_mod
    from flask import render_template

    client = main_mod.app.test_client()
    for path in ('/login', '/signInGuest'):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 200, path
        body = resp.get_data(as_text=True)
        assert 'css_url(' not in body, path
        assert '/static/css/' in body and '?v=' in body, path

    # Shared role templates (Customer / Supplier / Admin shells) via Jinja global.
    templates = (
        'createQuotation.html',
        'supplierBidding.html',
        'admin.html',
        'access_denied.html',
        'login.html',
    )
    with main_mod.app.test_request_context('/'):
        for name in templates:
            html = render_template(name)
            assert 'css_url(' not in html, name
            assert 'UndefinedError' not in html, name
            assert '?v=' in html, name


@pytest.mark.parametrize(
    'name',
    [
        'equotationIcyTheme.css',
        'adminViewQuotations.css',
        'hamburger_menu.css',
        'app_page_header.css',
        'login.css',
    ],
)
def test_key_css_files_exist_for_hashing(name):
    assert (STATIC_CSS / name).is_file()
