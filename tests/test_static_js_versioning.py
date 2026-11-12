"""Content-hash JS cache busting for templates."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from utils.static_assets import (
    clear_static_asset_hash_cache,
    js_url,
    static_file_content_hash,
    versioned_static_url,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'templates'
STATIC_JS = ROOT / 'static' / 'js'


def test_js_url_uses_content_hash():
    clear_static_asset_hash_cache()
    digest = static_file_content_hash('js/eq_core.js')
    assert re.fullmatch(r'[0-9a-f]{12}', digest)
    assert js_url('js/eq_core.js') == f'/static/js/eq_core.js?v={digest}'
    assert versioned_static_url('js/hamburger_menu.js').startswith(
        '/static/js/hamburger_menu.js?v='
    )


def test_js_url_changes_when_file_content_changes(tmp_path):
    clear_static_asset_hash_cache()
    js_dir = tmp_path / 'js'
    js_dir.mkdir()
    target = js_dir / 'probe.js'
    target.write_text('console.log(1)', encoding='utf-8')
    first = js_url('js/probe.js', static_root=str(tmp_path))
    target.write_text('console.log(2)', encoding='utf-8')
    clear_static_asset_hash_cache()
    second = js_url('js/probe.js', static_root=str(tmp_path))
    assert first != second
    assert first.startswith('/static/js/probe.js?v=')
    assert second.startswith('/static/js/probe.js?v=')


def test_shared_js_hash_is_stable_across_calls():
    clear_static_asset_hash_cache()
    a = js_url('js/adminViewQuotations.js')
    b = js_url('js/adminViewQuotations.js')
    assert a == b


def test_templates_use_js_url_helper_only():
    hard = re.compile(
        r'''src=["'](?:/static/js/|\{\{\s*url_for\(\s*['"]static['"])'''
        r'''|src=["'][^"']*\.js\?v='''
        r'''|script\.src\s*=\s*['"]/static/js/''',
        re.I,
    )
    helper = re.compile(r"""js_url\(\s*['"]js/[^'"]+\.js['"]\s*\)""")
    offenders = []
    helpers = 0
    for path in TEMPLATES.rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        if hard.search(text):
            offenders.append(str(path.relative_to(ROOT)))
        helpers += len(helper.findall(text))
    assert not offenders, f'hardcoded local JS src remain: {offenders}'
    assert helpers >= 20


def test_flask_registers_js_url_as_jinja_global(monkeypatch):
    monkeypatch.setenv('FLASK_SECRET_KEY', 'x' * 40)
    monkeypatch.setenv('EQ_REQUIRE_SECURE_COOKIES', '0')
    import main as main_mod

    assert 'js_url' in main_mod.app.jinja_env.globals
    assert callable(main_mod.app.jinja_env.globals['js_url'])


def test_flask_renders_versioned_js_on_login(monkeypatch):
    monkeypatch.setenv('FLASK_SECRET_KEY', 'x' * 40)
    monkeypatch.setenv('EQ_REQUIRE_SECURE_COOKIES', '0')
    import main as main_mod

    clear_static_asset_hash_cache()
    eq_digest = static_file_content_hash('js/eq_core.js')
    login_digest = static_file_content_hash('js/login.js')
    client = main_mod.app.test_client()
    resp = client.get('/login')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert f'/static/js/eq_core.js?v={eq_digest}' in html
    assert f'/static/js/login.js?v={login_digest}' in html
    assert 'js_url(' not in html
    assert not re.search(r'/static/js/[^\"\']+\.js\?v=20\d{6}_', html)


def test_view_quotations_renders_versioned_admin_js_and_css(monkeypatch):
    monkeypatch.setenv('FLASK_SECRET_KEY', 'x' * 40)
    monkeypatch.setenv('EQ_REQUIRE_SECURE_COOKIES', '0')
    import main as main_mod
    from flask import render_template

    clear_static_asset_hash_cache()
    js_digest = static_file_content_hash('js/adminViewQuotations.js')
    css_digest = static_file_content_hash('css/adminViewQuotations.css')
    icy_digest = static_file_content_hash('css/equotationIcyTheme.css')

    with main_mod.app.test_request_context('/'):
        admin_html = render_template(
            'adminViewQuotations.html',
            user_email='admin@example.com',
            customer_my_quotations_only=False,
        )
        customer_html = render_template(
            'adminViewQuotations.html',
            user_email='customer@example.com',
            customer_my_quotations_only=True,
            page_header_subtitle='Customer: customer@example.com',
        )

    for html in (admin_html, customer_html):
        assert f'/static/js/adminViewQuotations.js?v={js_digest}' in html
        assert f'/static/css/adminViewQuotations.css?v={css_digest}' in html
        assert f'/static/css/equotationIcyTheme.css?v={icy_digest}' in html
        assert 'js_url(' not in html
        assert 'css_url(' not in html
        assert not re.search(r'/static/js/adminViewQuotations\.js\?v=20\d{6}_', html)


@pytest.mark.parametrize(
    'name',
    [
        'eq_core.js',
        'hamburger_menu.js',
        'adminViewQuotations.js',
        'login.js',
        'orderQuotation.js',
    ],
)
def test_key_js_files_exist_for_hashing(name):
    assert (STATIC_JS / name).is_file()
