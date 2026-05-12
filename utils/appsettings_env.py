"""Load ``appsettings.json`` from the project root into ``os.environ`` via ``setdefault``.

Nested objects use ``__`` between segments (same as ``TenantBootstrap__AwsApiBaseUrl``).
Scalars at the root set env vars with that name. Keys starting with ``__`` are ignored.

Load order for minimal ``.env`` (e.g. only ``TENANT_CODE``):

1. ``apply_appsettings_to_environ()``
2. ``load_dotenv(..., override=False)`` so ``.env`` only fills gaps / adds tenant code
3. ``apply_tenant_env_overrides()`` for Dynamo + Secrets Manager

``EmailSettings`` (same shape as ProAccScanner ``appsettings.json``) is flattened to
``EmailSettings__SmtpHost``, etc., then copied into ``SMTP_SERVER`` / ``SMTP_PORT`` /
``SMTP_EMAIL`` / ``SMTP_PASSWORD`` / ``SMTP_SENDER_NAME`` when those are still empty
(legacy root ``SMTP_*`` keys still win if present).
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


def _apply_email_settings_to_smtp_env() -> None:
    """
    Map ProAccScanner-style ``EmailSettings`` section into ``SMTP_*`` used by ``main.py`` / ``email_utils``.

    Flattening produces ``EmailSettings__SmtpHost``, ``EmailSettings__SmtpUser``, etc.
    Only fills ``SMTP_*`` when the target is missing or blank so explicit env/root keys win.
    """
    host = (os.getenv("EmailSettings__SmtpHost") or "").strip()
    port = (os.getenv("EmailSettings__SmtpPort") or "").strip()
    user = (os.getenv("EmailSettings__SmtpUser") or "").strip()
    pass_raw = os.getenv("EmailSettings__SmtpPass")
    pass_str = "" if pass_raw is None else str(pass_raw).strip()
    sender = (os.getenv("EmailSettings__SenderName") or "").strip()

    if not (os.getenv("SMTP_SERVER") or "").strip() and host:
        os.environ["SMTP_SERVER"] = host
    if not (os.getenv("SMTP_PORT") or "").strip() and port:
        os.environ["SMTP_PORT"] = port
    if not (os.getenv("SMTP_EMAIL") or "").strip() and user:
        os.environ["SMTP_EMAIL"] = user
    if not (os.getenv("SMTP_PASSWORD") or "").strip() and pass_str:
        os.environ["SMTP_PASSWORD"] = pass_str
    if not (os.getenv("SMTP_SENDER_NAME") or "").strip() and sender:
        os.environ["SMTP_SENDER_NAME"] = sender


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
        _apply_email_settings_to_smtp_env()
        region = (os.getenv("AWS__Region") or "").strip()
        if region and not (os.getenv("AWS_REGION") or "").strip():
            os.environ.setdefault("AWS_REGION", region)

    return loaded
