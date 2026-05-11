"""SigV4-signed HTTP client for SQL Accounting API Gateway."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from api.config.sql_accounting_api import SqlAccountingApiSettings

logger = logging.getLogger(__name__)


def _is_read_timeout_transport_error(exc: BaseException) -> bool:
    """True when the failure is a read timeout (do not retry POST).

    urllib3 often surfaces read timeouts as ``ConnectionError`` with a message like
    ``Max retries exceeded ... (Caused by ReadTimeoutError(...))`` rather than
    ``requests.exceptions.ReadTimeout``, so the dedicated ``ReadTimeout`` handler
    alone is not enough.
    """
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return True
    cur: BaseException | None = exc
    for _ in range(8):
        if cur is None:
            break
        if isinstance(cur, requests.exceptions.ReadTimeout):
            return True
        if type(cur).__name__ == "ReadTimeoutError":
            return True
        cur = cur.__cause__ or cur.__context__
    msg = str(exc).lower()
    if "read timed out" in msg or "readtimeouterror" in msg:
        return True
    return False


class SqlAccountingApiError(Exception):
    """Raised when the SQL Accounting API returns an error or the request fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class SqlAccountingApiClient:
    """POST JSON payloads to API Gateway with AWS SigV4 (execute-api)."""

    def __init__(self, settings: SqlAccountingApiSettings) -> None:
        self._settings = settings
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        # Only retry on connection-level failures (not read timeouts).
        # A read timeout means the server received the request but didn't respond in time —
        # retrying a POST in that state can cause duplicate submissions.
        # status_forcelist covers transient gateway errors only.
        retries = Retry(
            total=self._settings.max_retries,
            connect=self._settings.max_retries,
            read=0,
            backoff_factor=0.3,
            status_forcelist=(429, 502, 503, 504),
            allowed_methods=frozenset({"POST"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _sign_and_post(
        self,
        url: str,
        body_bytes: bytes,
        *,
        timeout_seconds: float | None = None,
    ) -> requests.Response:
        creds = Credentials(self._settings.access_key, self._settings.secret_key)
        aws_request = AWSRequest(
            method="POST",
            url=url,
            data=body_bytes,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        SigV4Auth(creds, self._settings.service, self._settings.region).add_auth(aws_request)
        prepared = aws_request.prepare()
        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else self._settings.timeout_seconds
        )
        return self._session.post(
            prepared.url,
            data=prepared.body,
            headers=dict(prepared.headers),
            timeout=timeout,
        )

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> tuple[int, dict[str, Any] | None, str]:
        """
        Send a signed POST with JSON body.

        Returns:
            (http_status, parsed_json_or_none, raw_response_text)
        """
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        body_bytes = body.encode("utf-8")

        if self._settings.debug_payload:
            logger.info("SQL Accounting API request payload (debug): %s", body)

        last_exc: Exception | None = None
        attempts = self._settings.max_retries + 1
        for attempt in range(attempts):
            try:
                resp = self._sign_and_post(url, body_bytes, timeout_seconds=timeout_seconds)
                text = resp.text or ""
                parsed: dict[str, Any] | None = None
                if text:
                    try:
                        parsed_any: Any = json.loads(text)
                        if isinstance(parsed_any, dict):
                            parsed = parsed_any
                    except json.JSONDecodeError:
                        parsed = None
                return resp.status_code, parsed, text
            except requests.exceptions.ReadTimeout as exc:
                # Read timeout = server got the request but didn't respond in time.
                # Do NOT retry: the POST may already be processing on the remote side.
                last_exc = exc
                logger.warning("SQL Accounting API read timeout (%s) — not retrying POST", exc)
                break
            except requests.exceptions.ConnectionError as exc:
                # Same as ReadTimeout when urllib3 wraps it (see _is_read_timeout_transport_error).
                if _is_read_timeout_transport_error(exc):
                    last_exc = exc
                    logger.warning(
                        "SQL Accounting API read timeout (ConnectionError wrapper) — not retrying POST: %s",
                        exc,
                    )
                    break
                last_exc = exc
                if attempt >= attempts - 1:
                    break
                wait = 0.3 * (2 ** attempt)
                logger.warning(
                    "SQL Accounting API transport error (%s), retry %s/%s after %.1fs",
                    exc,
                    attempt + 1,
                    self._settings.max_retries,
                    wait,
                )
                time.sleep(wait)
            except requests.exceptions.Timeout as exc:
                # ConnectTimeout and other non-read timeouts (ReadTimeout handled above).
                last_exc = exc
                if attempt >= attempts - 1:
                    break
                wait = 0.3 * (2 ** attempt)
                logger.warning(
                    "SQL Accounting API transport error (%s), retry %s/%s after %.1fs",
                    exc,
                    attempt + 1,
                    self._settings.max_retries,
                    wait,
                )
                time.sleep(wait)

        assert last_exc is not None
        raise SqlAccountingApiError(
            f"SQL Accounting API request failed after retries: {last_exc}",
            status_code=None,
            response_body=None,
        ) from last_exc
