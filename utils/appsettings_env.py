"""Load ``appsettings.json`` from the project root into ``os.environ`` via ``setdefault``.

Nested objects use ``__`` between segments (same as ``TenantBootstrap__AwsApiBaseUrl``).
Scalars at the root set env vars with that name. Keys starting with ``__`` are ignored.

Load order for minimal ``.env`` (e.g. only ``TENANT_CODE``):

1. ``apply_appsettings_to_environ()``
2. ``load_dotenv(..., override=False)`` so ``.env`` only fills gaps / adds tenant code
3. ``apply_tenant_env_overrides()`` for Dynamo + Secrets Manager
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _flatten_to_setdefault(prefix: str, node: Any) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if not isinstance(k, str) or k.startswith("__"):
                continue
            name = f"{prefix}__{k}" if prefix else k
            _flatten_to_setdefault(name, v)
    elif isinstance(node, list):
        return
    elif node is not None and prefix:
        os.environ.setdefault(prefix, str(node))


def _flatten_to_override(prefix: str, node: Any) -> None:
    """Same as setdefault path but overwrites existing env (for appsettings.Local.json)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if not isinstance(k, str) or k.startswith("__"):
                continue
            name = f"{prefix}__{k}" if prefix else k
            _flatten_to_override(name, v)
    elif isinstance(node, list):
        return
    elif node is not None and prefix:
        os.environ[prefix] = str(node)


def apply_appsettings_to_environ(*, project_root: Path | None = None) -> bool:
    """
    Merge ``appsettings.json`` (and optional ``appsettings.Local.json``) into the environment.

    ``appsettings.json`` uses ``setdefault`` so the process environment or a later ``.env`` can
    supply values first. ``appsettings.Local.json`` is merged **after** and **overwrites** keys
    so you can keep machine-specific overrides (e.g. SQL API keys) out of git.
    """
    root = project_root or Path(__file__).resolve().parents[1]
    loaded = False
    path = root / "appsettings.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc
        if isinstance(data, dict):
            _flatten_to_setdefault("", data)
            loaded = True

    local = root / "appsettings.Local.json"
    if local.is_file():
        try:
            ldata = json.loads(local.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in {local}: {exc}") from exc
        if isinstance(ldata, dict):
            _flatten_to_override("", ldata)
            loaded = True

    if loaded:
        region = (os.getenv("AWS__Region") or "").strip()
        if region and not (os.getenv("AWS_REGION") or "").strip():
            os.environ.setdefault("AWS_REGION", region)

    return loaded
