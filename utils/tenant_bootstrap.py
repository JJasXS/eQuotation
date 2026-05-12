"""
Load Firebird + SQL Accounting API settings from the ProAcc tenant HTTP API (Dynamo-backed),
same contract as ProAccScanner ``TenantBootstrap:AwsApiBaseUrl`` + ``?tenantCode=``.

When ``TENANT_CODE`` (or ``TenantBootstrap__TenantCode``) is set, this module fetches the
tenant JSON and writes into ``os.environ`` so the rest of the app can keep using
``DB_*`` and ``SQL_API_*`` as today.

Optional env (defaults match ProAccScanner ``appsettings.json``):
  TENANT_BOOTSTRAP_API_URL / TenantBootstrap__AwsApiBaseUrl
  TENANT_BOOTSTRAP_API_KEY / TenantBootstrap__AwsApiKey  (x-api-key if required)

Skip fetch: TENANT_BOOTSTRAP_SKIP=1

Dynamo / JSON sections (case-insensitive names, Dynamo ``M`` / ``S`` / ``N`` unwrapped):
  ``database``: dbHost, dbPath (required for DB). Optional: dbUser, dbPassword.
  ``sqlApi``: Inline keys and/or ``sqlApiCredentialsSecretRef`` (JSON in Secrets Manager with
    accessKey/secretKey or SQL_API_* style). Also ``sqlApiHost``, ``sqlApiRegion``, ``sqlApiService``.
  ``openai``: Prefer ``openaiApiKeySecretRef`` (or ``openaiCredentialsSecretRef``). When the secret is JSON,
    it must include both an API key (``openaiApiKey`` / ``apiKey`` / …) and a model (``openaiModel`` / ``model`` / …).
    Dynamo ``openaiModel`` is ignored in that case so a single secret is the source of truth. Plaintext secrets
    may still pair with Dynamo ``openaiModel`` for the model only.
  ``email``: ``smtpHost``, ``smtpPort``, ``smtpSenderEmail`` → ``SMTP_SERVER``, ``SMTP_PORT``, ``SMTP_EMAIL``;
    ``smtpAppPasswordSecretRef`` → ``SMTP_PASSWORD`` (plaintext or JSON with ``password`` / ``smtpPassword`` / …).

Secrets Manager region: ``AWS_REGION``, ``TENANT_BOOTSTRAP_SECRETS_REGION``, or tenant ``sqlApiRegion`` /
``openaiRegion``. Skip all SM calls: ``TENANT_BOOTSTRAP_SKIP_SECRETS=1`` (then supply keys via
``appsettings.Local.json`` or environment).

If Dynamo references a secret but this process has **no AWS credentials** (``NoCredentialsError``),
bootstrap **continues** when the needed values are **already** in the environment (e.g. from
``appsettings.Local.json``). Otherwise startup still fails until you run ``aws configure sso`` /
``aws sso login``, set ``AWS_PROFILE``, use an instance role, or add ``appsettings.Local.json``.

Non-secret defaults: load ``appsettings.json`` before ``.env`` (see ``utils.appsettings_env``).
"""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Mapping
from urllib.parse import urlencode

import requests
from botocore.exceptions import NoCredentialsError
from botocore.session import Session as BotocoreSession

# Same default invoke URL as ProAccScanner ``TenantBootstrap:AwsApiBaseUrl``.
DEFAULT_TENANT_API_BASE_URL = (
    "https://v2wwsho311.execute-api.ap-southeast-1.amazonaws.com/default/proacc-tenant-config-api"
)


def _truthy_env(name: str) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _tenant_code() -> str:
    return (
        (os.getenv("TENANT_CODE") or os.getenv("TenantBootstrap__TenantCode") or "").strip()
    )


def _api_base_url() -> str:
    return (
        os.getenv("TENANT_BOOTSTRAP_API_URL")
        or os.getenv("TenantBootstrap__AwsApiBaseUrl")
        or DEFAULT_TENANT_API_BASE_URL
    ).strip()


def _api_key() -> str:
    return (os.getenv("TENANT_BOOTSTRAP_API_KEY") or os.getenv("TenantBootstrap__AwsApiKey") or "").strip()


def _secrets_manager_region(sql_api_region_hint: str | None = None, openai_region_hint: str | None = None) -> str:
    for name in (
        "TENANT_BOOTSTRAP_SECRETS_REGION",
        "AWS_REGION",
        "AWS__Region",
    ):
        v = (os.getenv(name) or "").strip()
        if v:
            return v
    for hint in (openai_region_hint, sql_api_region_hint):
        if hint and hint.strip():
            return hint.strip()
    return "ap-southeast-1"


def _fetch_secret_string(secret_id: str, region: str) -> str:
    """Return raw SecretString from AWS Secrets Manager (plain text or JSON string)."""
    sid = (secret_id or "").strip()
    if not sid:
        return ""
    sess = BotocoreSession()
    client = sess.create_client("secretsmanager", region_name=region)
    resp = client.get_secret_value(SecretId=sid)
    s = resp.get("SecretString")
    if isinstance(s, str) and s.strip():
        return s.strip()
    blob = resp.get("SecretBinary")
    if blob is not None:
        try:
            return base64.b64decode(blob).decode("utf-8")
        except Exception:
            return ""
    return ""


def _sm_error_message(*, secret_ref: str, tenant_code: str, exc: Exception) -> str:
    if isinstance(exc, NoCredentialsError):
        return (
            f"Cannot read Secrets Manager secret {secret_ref!r} for tenant {tenant_code!r}: no AWS credentials. "
            "Use an IAM role/instance profile, set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, or set "
            "TENANT_BOOTSTRAP_SKIP_SECRETS=1 and put SQL_API_* / OPENAI_* in appsettings.Local.json for local dev."
        )
    return f"Failed to read secret {secret_ref!r} for tenant {tenant_code!r}: {exc}"


def _first_scalar_in_dict(data: dict[str, Any], names: list[str]) -> str | None:
    lower_map = {str(k).lower(): k for k in data}
    for n in names:
        k = lower_map.get(n.lower())
        if k is None:
            continue
        s = _coerce_scalar(data.get(k))
        if s and str(s).strip():
            return str(s).strip()
    return None


def _apply_sql_credentials_secret(secret_text: str) -> None:
    """Merge accessKey/secretKey from JSON or tolerate plain secret (not recommended)."""
    text = (secret_text or "").strip()
    if not text:
        return
    data: dict[str, Any]
    try:
        parsed = json.loads(text)
        data = parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        if not (os.getenv("SQL_API_ACCESS_KEY") or "").strip():
            os.environ["SQL_API_ACCESS_KEY"] = text
        return

    ak = _first_scalar_in_dict(
        data,
        ["accessKey", "sqlApiAccessKey", "SQL_API_ACCESS_KEY", "access_key", "keyId"],
    )
    sk = _first_scalar_in_dict(
        data,
        ["secretKey", "sqlApiSecretKey", "SQL_API_SECRET_KEY", "secret", "secretAccessKey"],
    )
    if ak:
        os.environ["SQL_API_ACCESS_KEY"] = ak
    if sk:
        os.environ["SQL_API_SECRET_KEY"] = sk


def _apply_openai_secret(secret_text: str) -> tuple[str | None, str | None]:
    """Return (api_key, model) from JSON or plain text (plain → api key only)."""
    text = (secret_text or "").strip()
    if not text:
        return None, None
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return text, None
    except json.JSONDecodeError:
        return text, None

    ak = _first_scalar_in_dict(
        parsed,
        [
            "openaiApiKey",
            "OPENAI_API_KEY",
            "apiKey",
            "api_key",
            "key",
        ],
    )
    model = _first_scalar_in_dict(
        parsed,
        ["openaiModel", "OPENAI_MODEL", "model", "chatModel", "deployment"],
    )
    return ak, model


def _apply_smtp_password_secret(secret_text: str) -> str | None:
    """Return SMTP app password from plaintext or JSON secret."""
    text = (secret_text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            pw = _first_scalar_in_dict(
                parsed,
                ["smtpAppPassword", "smtpPassword", "appPassword", "password", "SMTP_PASSWORD"],
            )
            return pw.strip() if pw else None
    except json.JSONDecodeError:
        pass
    return text


def _unwrap_dynamo_map(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict) and isinstance(obj.get("M"), dict):
        return dict(obj["M"])
    if isinstance(obj, dict):
        return obj
    return {}


def _coerce_scalar(el: Any) -> str | None:
    if el is None:
        return None
    if isinstance(el, str):
        return el
    if isinstance(el, bool):
        return "true" if el else "false"
    if isinstance(el, (int, float)):
        return str(el)
    if not isinstance(el, dict):
        return None
    if "S" in el:
        v = el["S"]
        return str(v) if v is not None else ""
    if "N" in el:
        v = el["N"]
        return str(v) if v is not None else ""
    if "BOOL" in el:
        b = el["BOOL"]
        if isinstance(b, bool):
            return "true" if b else "false"
        return "true" if str(b).lower() in ("1", "true", "yes") else "false"
    return None


def _get_ci(obj: Mapping[str, Any], key: str) -> Any | None:
    lk = key.lower()
    for k, v in obj.items():
        if isinstance(k, str) and k.lower() == lk:
            return v
    return None


def _get_scalar_map(m: Mapping[str, Any], name: str) -> str | None:
    el = _get_ci(m, name)
    if el is None:
        return None
    s = _coerce_scalar(el)
    return s.strip() if s else None


def _find_section_recursive(obj: Any, section: str, depth: int = 0, max_depth: int = 8) -> dict[str, Any] | None:
    if depth > max_depth or not isinstance(obj, dict):
        return None
    sec = _get_ci(obj, section)
    if sec is not None:
        un = _unwrap_dynamo_map(sec)
        return un if isinstance(un, dict) else None
    for _k, v in obj.items():
        if isinstance(v, dict):
            hit = _find_section_recursive(v, section, depth + 1, max_depth)
            if hit is not None:
                return hit
        elif isinstance(v, str):
            t = v.strip()
            if t.startswith("{"):
                try:
                    nested = json.loads(t)
                except json.JSONDecodeError:
                    continue
                hit = _find_section_recursive(nested, section, depth + 1, max_depth)
                if hit is not None:
                    return hit
    return None


def _maybe_decode_gateway_body(envelope: Mapping[str, Any], body_text: str) -> str:
    b = envelope.get("isBase64Encoded")
    if b is not True and str(b).lower() != "true":
        return body_text
    try:
        return base64.b64decode(body_text).decode("utf-8")
    except Exception:
        return body_text


def _resolve_tenant_payload(root: Any) -> dict[str, Any]:
    if not isinstance(root, dict):
        return {}

    body = root.get("body")
    if isinstance(body, str) and body.strip():
        text = _maybe_decode_gateway_body(root, body.strip())
        try:
            inner = json.loads(text)
        except json.JSONDecodeError:
            inner = {}
        if isinstance(inner, dict):
            root = inner
    elif isinstance(body, dict):
        root = body

    if isinstance(root.get("Item"), dict):
        root = dict(root["Item"])

    data = root.get("data")
    if isinstance(data, str) and data.strip():
        try:
            inner = json.loads(data.strip())
        except json.JSONDecodeError:
            inner = {}
        if isinstance(inner, dict):
            root = inner
    elif isinstance(data, dict):
        root = data

    return root if isinstance(root, dict) else {}


def _fetch_tenant_json(tenant_code: str) -> dict[str, Any]:
    base = _api_base_url().rstrip("/")
    if not base:
        raise RuntimeError("Tenant API base URL is empty. Set TENANT_BOOTSTRAP_API_URL.")
    q = urlencode({"tenantCode": tenant_code})
    url = f"{base}?{q}" if "?" not in base else f"{base}&{q}"
    headers: dict[str, str] = {}
    key = _api_key()
    if key:
        headers["x-api-key"] = key
    r = requests.get(url, headers=headers, timeout=30)
    text = (r.text or "").strip()
    if text.startswith("\ufeff"):
        text = text[1:]
    if not r.ok:
        raise RuntimeError(
            f"Tenant AWS HTTP {r.status_code} for tenantCode={tenant_code!r}: {text[:1200]}"
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Tenant response is not JSON: {e}; prefix={text[:400]!r}") from e


def _looks_like_health_only(raw: str, root: Mapping[str, Any]) -> bool:
    if re.search(r'"database"', raw, re.I):
        return False
    if not root:
        return False
    return "status" in {k.lower() for k in root} and "service" in {k.lower() for k in root}


def apply_tenant_env_overrides() -> bool:
    """
    If ``TENANT_CODE`` is set and bootstrap is not skipped, fetch tenant and set ``os.environ``.

    Returns True when a tenant was applied, False when this was a no-op.
    """
    if _truthy_env("TENANT_BOOTSTRAP_SKIP"):
        return False
    code = _tenant_code()
    if not code:
        return False

    envelope = _fetch_tenant_json(code)
    raw_preview = json.dumps(envelope)[:2000]
    root = _resolve_tenant_payload(envelope)
    if _looks_like_health_only(raw_preview, root):
        raise RuntimeError(
            "Tenant URL returned a health-style JSON (status/service) instead of a tenant record. "
            "Point TENANT_BOOTSTRAP_API_URL at the invoke URL that returns the Dynamo tenant payload."
        )

    db = _find_section_recursive(root, "database")
    if not db:
        raise RuntimeError(
            f"Tenant JSON has no 'database' section (tenant {code!r}). "
            f"Ensure Dynamo includes database.dbHost, database.dbPath, etc. Raw prefix: {raw_preview[:900]}"
        )

    db_path = _get_scalar_map(db, "dbPath")
    db_host = _get_scalar_map(db, "dbHost")
    if not db_path or not db_host:
        raise RuntimeError(
            f"Tenant database section missing dbPath or dbHost (tenant {code!r})."
        )

    os.environ["DB_HOST"] = db_host.strip()
    os.environ["DB_PATH"] = db_path.strip()

    db_user = _get_scalar_map(db, "dbUser")
    db_password = _get_scalar_map(db, "dbPassword")
    if db_user:
        os.environ["DB_USER"] = db_user.strip()
    if db_password:
        os.environ["DB_PASSWORD"] = db_password.strip()

    sql_region: str | None = None
    oi_region: str | None = None

    sql = _find_section_recursive(root, "sqlApi")
    if not sql:
        sql = _find_section_recursive(root, "sqlapi")

    if isinstance(sql, dict) and sql:
        # Support both camelCase API names (sqlApiHost) and shorter names (host).
        mapping = [
            ("accessKey", "SQL_API_ACCESS_KEY"),
            ("secretKey", "SQL_API_SECRET_KEY"),
            ("host", "SQL_API_HOST"),
            ("sqlApiHost", "SQL_API_HOST"),
            ("region", "SQL_API_REGION"),
            ("sqlApiRegion", "SQL_API_REGION"),
            ("service", "SQL_API_SERVICE"),
            ("sqlApiService", "SQL_API_SERVICE"),
            ("customerCreatePath", "SQL_API_CUSTOMER_CREATE_PATH"),
            ("salesQuotationPath", "SQL_API_SALES_QUOTATION_PATH"),
            ("stockItemListPath", "SQL_API_STOCK_ITEM_LIST_PATH"),
        ]
        for json_name, env_name in mapping:
            val = _get_scalar_map(sql, json_name)
            if val:
                os.environ[env_name] = val

        use_tls = _get_scalar_map(sql, "useTls") or _get_scalar_map(sql, "sqlApiUseTls")
        if use_tls is not None:
            os.environ["SQL_API_USE_TLS"] = (
                "true" if use_tls.lower() in ("1", "true", "yes", "on") else "false"
            )

        sql_region = (
            _get_scalar_map(sql, "sqlApiRegion")
            or _get_scalar_map(sql, "region")
            or (os.getenv("SQL_API_REGION") or "").strip()
            or None
        )

        secret_ref = _get_scalar_map(sql, "sqlApiCredentialsSecretRef")
        if secret_ref and not _truthy_env("TENANT_BOOTSTRAP_SKIP_SECRETS"):
            try:
                raw_sec = _fetch_secret_string(secret_ref, _secrets_manager_region(sql_region))
                _apply_sql_credentials_secret(raw_sec)
            except NoCredentialsError as exc:
                if (os.getenv("SQL_API_ACCESS_KEY") or "").strip() and (os.getenv("SQL_API_SECRET_KEY") or "").strip():
                    print(
                        f"[tenant_bootstrap] No AWS credentials; skipping SQL secret {secret_ref!r} — "
                        "using SQL_API_* already in environment (e.g. appsettings.Local.json).",
                        flush=True,
                    )
                else:
                    raise RuntimeError(_sm_error_message(secret_ref=secret_ref, tenant_code=code, exc=exc)) from exc
            except Exception as exc:
                raise RuntimeError(_sm_error_message(secret_ref=secret_ref, tenant_code=code, exc=exc)) from exc

        ak = (os.getenv("SQL_API_ACCESS_KEY") or "").strip()
        sk = (os.getenv("SQL_API_SECRET_KEY") or "").strip()
        if ak and sk:
            if not (os.getenv("API_ACCESS_KEY") or "").strip():
                os.environ["API_ACCESS_KEY"] = ak
            if not (os.getenv("API_SECRET_KEY") or "").strip():
                os.environ["API_SECRET_KEY"] = sk

    oi = _find_section_recursive(root, "openai")
    if isinstance(oi, dict) and oi:
        oi_region = _get_scalar_map(oi, "openaiRegion") or _get_scalar_map(oi, "region")

        oa_ref = (
            _get_scalar_map(oi, "openaiApiKeySecretRef")
            or _get_scalar_map(oi, "openaiCredentialsSecretRef")
            or _get_scalar_map(oi, "openaiSecretRef")
        )

        if oa_ref and not _truthy_env("TENANT_BOOTSTRAP_SKIP_SECRETS"):
            raw_oai: str | None = None
            try:
                raw_oai = _fetch_secret_string(oa_ref, _secrets_manager_region(None, oi_region))
            except NoCredentialsError as exc:
                if (os.getenv("OPENAI_API_KEY") or "").strip() and (os.getenv("OPENAI_MODEL") or "").strip():
                    print(
                        f"[tenant_bootstrap] No AWS credentials; skipping OpenAI secret {oa_ref!r} — "
                        "using OPENAI_* already in environment (e.g. appsettings.Local.json).",
                        flush=True,
                    )
                else:
                    raise RuntimeError(_sm_error_message(secret_ref=oa_ref, tenant_code=code, exc=exc)) from exc
            except Exception as exc:
                raise RuntimeError(_sm_error_message(secret_ref=oa_ref, tenant_code=code, exc=exc)) from exc

            if raw_oai is not None and (raw_oai or "").strip():
                raw_stripped = (raw_oai or "").strip()
                is_json_obj = False
                try:
                    parsed_oai = json.loads(raw_stripped)
                    is_json_obj = isinstance(parsed_oai, dict)
                except json.JSONDecodeError:
                    pass

                api_k, model_sec = _apply_openai_secret(raw_oai)
                if not api_k:
                    raise RuntimeError(
                        f"OpenAI secret {oa_ref!r} (tenant {code!r}) must include an API key in JSON "
                        f'(e.g. "openaiApiKey" or "apiKey") or as a plaintext secret string.'
                    )
                os.environ["OPENAI_API_KEY"] = api_k

                if model_sec:
                    os.environ["OPENAI_MODEL"] = model_sec.strip()
                elif is_json_obj:
                    raise RuntimeError(
                        f"OpenAI secret {oa_ref!r} (tenant {code!r}) is JSON but has no model field. "
                        'Put both in the same JSON, e.g. {"openaiApiKey":"sk-...","openaiModel":"gpt-4o-mini"}.'
                    )
                else:
                    model_fb = _get_scalar_map(oi, "openaiModel") or _get_scalar_map(oi, "model")
                    if model_fb:
                        os.environ["OPENAI_MODEL"] = model_fb.strip()
            else:
                model_inline = _get_scalar_map(oi, "openaiModel") or _get_scalar_map(oi, "model")
                if model_inline and not (os.getenv("OPENAI_MODEL") or "").strip():
                    os.environ["OPENAI_MODEL"] = model_inline.strip()
        elif oa_ref and _truthy_env("TENANT_BOOTSTRAP_SKIP_SECRETS"):
            print(
                f"[tenant_bootstrap] Skipping OpenAI secret {oa_ref!r} (TENANT_BOOTSTRAP_SKIP_SECRETS).",
                flush=True,
            )
        else:
            model_inline = _get_scalar_map(oi, "openaiModel") or _get_scalar_map(oi, "model")
            if model_inline:
                os.environ["OPENAI_MODEL"] = model_inline.strip()

    em = _find_section_recursive(root, "email")
    if isinstance(em, dict) and em:
        smtp_host = _get_scalar_map(em, "smtpHost")
        smtp_port = _get_scalar_map(em, "smtpPort")
        smtp_sender = _get_scalar_map(em, "smtpSenderEmail")
        if smtp_host:
            os.environ["SMTP_SERVER"] = smtp_host.strip()
        if smtp_port:
            os.environ["SMTP_PORT"] = smtp_port.strip()
        if smtp_sender:
            os.environ["SMTP_EMAIL"] = smtp_sender.strip()
        pwd_ref = _get_scalar_map(em, "smtpAppPasswordSecretRef")
        if pwd_ref and not _truthy_env("TENANT_BOOTSTRAP_SKIP_SECRETS"):
            try:
                raw_pw = _fetch_secret_string(pwd_ref, _secrets_manager_region(sql_region, oi_region))
                pw = _apply_smtp_password_secret(raw_pw)
                if pw:
                    os.environ["SMTP_PASSWORD"] = pw
            except NoCredentialsError as exc:
                if (os.getenv("SMTP_PASSWORD") or "").strip():
                    print(
                        f"[tenant_bootstrap] No AWS credentials; skipping SMTP secret {pwd_ref!r} — "
                        "using SMTP_PASSWORD already in environment.",
                        flush=True,
                    )
                else:
                    raise RuntimeError(_sm_error_message(secret_ref=pwd_ref, tenant_code=code, exc=exc)) from exc
            except Exception as exc:
                raise RuntimeError(_sm_error_message(secret_ref=pwd_ref, tenant_code=code, exc=exc)) from exc

    has_openai = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    print(
        f"[tenant_bootstrap] Applied tenant {code!r}: DB_HOST={os.environ['DB_HOST']!r} "
        f"DB_PATH={os.environ['DB_PATH']!r} has_sql_keys="
        f"{bool((os.getenv('SQL_API_ACCESS_KEY') or '').strip() and (os.getenv('SQL_API_SECRET_KEY') or '').strip())} "
        f"has_openai_key={has_openai}",
        flush=True,
    )
    return True
