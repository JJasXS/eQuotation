"""Content-hash cache busting for static CSS (and reusable for other assets).

Templates should use ``css_url('css/foo.css')`` so every page gets the same
``?v=<hash>`` for a given file. The hash changes when file bytes change.
"""
from __future__ import annotations

import hashlib
import os
import threading
from typing import Callable

_LOCK = threading.Lock()
# path -> (mtime_ns, size, hash12)
_HASH_CACHE: dict[str, tuple[int, int, str]] = {}


def _static_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, '..', 'static'))


def clear_static_asset_hash_cache() -> None:
    with _LOCK:
        _HASH_CACHE.clear()


def static_file_content_hash(relative_path: str, *, static_root: str | None = None) -> str:
    """Return a short hex digest of the file contents (stable across processes)."""
    rel = str(relative_path or '').replace('\\', '/').lstrip('/')
    if rel.startswith('static/'):
        rel = rel[len('static/') :]
    root = os.path.normpath(static_root or _static_root())
    abs_path = os.path.normpath(os.path.join(root, rel.replace('/', os.sep)))
    try:
        if os.path.commonpath([root, abs_path]) != root:
            return 'missing'
    except ValueError:
        return 'missing'
    try:
        st = os.stat(abs_path)
    except OSError:
        return 'missing'

    key = abs_path
    with _LOCK:
        cached = _HASH_CACHE.get(key)
        if cached and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
            return cached[2]

    digest = hashlib.sha256()
    with open(abs_path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            digest.update(chunk)
    short = digest.hexdigest()[:12]

    with _LOCK:
        _HASH_CACHE[key] = (st.st_mtime_ns, st.st_size, short)
    return short


def versioned_static_url(relative_path: str, *, static_root: str | None = None) -> str:
    """Build ``/static/<path>?v=<content-hash>`` for cache busting."""
    rel = str(relative_path or '').replace('\\', '/').lstrip('/')
    if rel.startswith('static/'):
        rel = rel[len('static/') :]
    digest = static_file_content_hash(rel, static_root=static_root)
    return f'/static/{rel}?v={digest}'


def css_url(relative_path: str, *, static_root: str | None = None) -> str:
    """Jinja helper: versioned URL for a CSS file under ``static/``."""
    rel = str(relative_path or '').replace('\\', '/').lstrip('/')
    if rel.startswith('css/'):
        pass
    elif not rel.startswith('static/') and '/' not in rel:
        rel = f'css/{rel}'
    return versioned_static_url(rel, static_root=static_root)


def make_css_url_for_app(app_static_folder: str | None) -> Callable[[str], str]:
    root = app_static_folder or _static_root()

    def _css_url(relative_path: str) -> str:
        return css_url(relative_path, static_root=root)

    return _css_url


def register_css_url_helper(app) -> Callable[[str], str]:
    """Bind ``css_url`` as a Jinja global (+ return the callable for context processors).

    Globals are available for every ``render_template`` / include on this app,
    including blueprints, without relying only on request context processors.
    """
    helper = make_css_url_for_app(getattr(app, 'static_folder', None))
    # Ensure the env exists, then pin the helper where Jinja always looks it up.
    app.jinja_env.globals['css_url'] = helper
    return helper
