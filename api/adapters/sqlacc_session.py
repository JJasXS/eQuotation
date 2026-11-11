"""SQLAcc.BizApp Login/Logout session with STA-safe serialized execution."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, TypeVar

from api.adapters.sta_work_queue import StaWorkQueue
from api.config.sql_acc_sdk import SqlAccSdkSettings, load_sql_acc_sdk_settings, redact_sdk_settings_for_log

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SqlAccSessionError(Exception):
    """Raised when COM session Login/Logout or dispatch fails."""


class SqlAccSessionManager:
    """
    One BizApp instance, STA-marshalled, gated for concurrency.

    When ``logout_after_use`` is false, Login is reused until idle timeout or company
    identity changes. When true, Logout runs after every action (legacy seat-freeing).
    """

    def __init__(
        self,
        settings: SqlAccSdkSettings | None = None,
        *,
        sta_queue: StaWorkQueue | None = None,
        dispatch_factory: Callable[[str], Any] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self._settings = settings if settings is not None else load_sql_acc_sdk_settings()
        self._sta = sta_queue
        self._owns_sta = sta_queue is None
        self._dispatch_factory = dispatch_factory
        self._gate = threading.Lock()
        self._app: Any | None = None
        self._logged_in = False
        self._logged_in_company_key: str | None = None
        self._last_used_monotonic: float | None = None
        self._clock = monotonic_clock or time.monotonic
        self.login_count = 0
        self.logout_count = 0

    @property
    def settings(self) -> SqlAccSdkSettings:
        return self._settings

    def _ensure_sta(self) -> StaWorkQueue:
        if self._sta is None:
            self._sta = StaWorkQueue()
        return self._sta

    def _default_dispatch(self, prog_id: str) -> Any:
        try:
            import win32com.client
        except ImportError as exc:
            raise SqlAccSessionError(
                "pywin32 is not available. Install with 'pip install pywin32'."
            ) from exc
        try:
            return win32com.client.Dispatch(prog_id)
        except Exception as exc:
            raise SqlAccSessionError(
                f"Unable to Dispatch COM object '{prog_id}': {exc}"
            ) from exc

    def _coerce_is_login(self, app: Any) -> bool:
        try:
            raw = app.IsLogin
        except Exception:
            return False
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        text = str(raw).strip().lower()
        return text in ("1", "true", "yes", "-1")

    def _idle_expired(self) -> bool:
        idle = float(self._settings.session_idle_seconds or 0.0)
        if idle <= 0 or self._last_used_monotonic is None:
            return False
        return (self._clock() - self._last_used_monotonic) > idle

    def _session_reusable(self) -> bool:
        if self._app is None or not self._logged_in:
            return False
        if not self._coerce_is_login(self._app):
            return False
        if self._logged_in_company_key != self._settings.company_identity_key:
            return False
        if self._idle_expired():
            return False
        return True

    def _ensure_login_on_sta(self) -> Any:
        settings = self._settings
        if not settings.allow_live_com:
            raise SqlAccSessionError(
                "SQLACC_SDK_ALLOW_LIVE_COM is false; refusing live SQLAcc.BizApp Login."
            )
        missing = settings.missing_login_fields()
        if missing:
            raise SqlAccSessionError(
                "SDK Login configuration incomplete: " + ", ".join(missing)
            )

        if self._session_reusable():
            return self._app

        # Drop stale / cross-company / idle session before Login.
        if self._app is not None and self._coerce_is_login(self._app):
            self._logout_on_sta()

        factory = self._dispatch_factory or self._default_dispatch
        if self._app is None:
            logger.info(
                "Creating SQLAcc COM instance prog_id=%s settings=%s",
                settings.prog_id,
                redact_sdk_settings_for_log(settings),
            )
            self._app = factory(settings.prog_id)

        app = self._app
        try:
            if self._coerce_is_login(app):
                try:
                    app.Logout()
                    self.logout_count += 1
                except Exception:
                    logger.debug("Pre-login Logout failed", exc_info=True)
            app.Login(
                settings.username,
                settings.password,
                settings.dcf_path,
                settings.database_file,
            )
            self.login_count += 1
        except SqlAccSessionError:
            raise
        except Exception as exc:
            self._logged_in = False
            self._logged_in_company_key = None
            raise SqlAccSessionError(f"SQLAcc.BizApp Login failed: {exc}") from exc

        if not self._coerce_is_login(app):
            self._logged_in = False
            self._logged_in_company_key = None
            raise SqlAccSessionError(
                "SQLAcc.BizApp Login completed but IsLogin is false "
                f"(dcf configured; database_file={settings.database_file!r})."
            )
        self._logged_in = True
        self._logged_in_company_key = settings.company_identity_key
        self._last_used_monotonic = self._clock()
        return app

    def _logout_on_sta(self) -> None:
        app = self._app
        if app is None:
            self._logged_in = False
            self._logged_in_company_key = None
            return
        try:
            if self._coerce_is_login(app):
                app.Logout()
                self.logout_count += 1
        except Exception:
            logger.warning("SQLAcc.BizApp Logout failed", exc_info=True)
        finally:
            self._logged_in = False
            self._logged_in_company_key = None

    def run(self, action: Callable[[Any], T], *, timeout_seconds: float | None = None) -> T:
        """Run ``action(biz_app)`` on the STA thread while logged into the configured company."""
        if action is None:
            raise ValueError("action is required")
        timeout = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else float(self._settings.login_timeout_seconds)
        )

        with self._gate:
            sta = self._ensure_sta()

            def _work() -> T:
                app = self._ensure_login_on_sta()
                try:
                    result = action(app)
                    self._last_used_monotonic = self._clock()
                    return result
                except Exception:
                    # Uncertain COM state — drop session; never auto-retry the write here.
                    try:
                        self._logout_on_sta()
                    except Exception:
                        logger.debug("Logout after failed action failed", exc_info=True)
                    raise
                finally:
                    if self._settings.logout_after_use:
                        self._logout_on_sta()

            return sta.run(_work, timeout_seconds=timeout)

    def close(self) -> None:
        with self._gate:
            try:
                if self._sta is not None and self._app is not None:

                    def _shutdown() -> None:
                        self._logout_on_sta()
                        self._app = None

                    try:
                        self._sta.run(_shutdown, timeout_seconds=15)
                    except Exception:
                        logger.debug("SDK session shutdown on STA failed", exc_info=True)
                        self._app = None
                        self._logged_in = False
                        self._logged_in_company_key = None
            finally:
                if self._owns_sta and self._sta is not None:
                    self._sta.close()
                self._sta = None if self._owns_sta else self._sta


_session_singleton: SqlAccSessionManager | None = None
_session_lock = threading.Lock()


def get_sqlacc_session_manager() -> SqlAccSessionManager:
    """Process-wide session manager (lazy). Tests should inject via CustomerService."""
    global _session_singleton
    with _session_lock:
        if _session_singleton is None:
            _session_singleton = SqlAccSessionManager()
        else:
            # Keep singleton company identity aligned with current env settings.
            fresh = load_sql_acc_sdk_settings()
            if (
                _session_singleton.settings.company_identity_key
                != fresh.company_identity_key
            ):
                try:
                    _session_singleton.close()
                except Exception:
                    pass
                _session_singleton = SqlAccSessionManager(fresh)
            else:
                # Refresh non-identity flags (idle / logout policy) without dropping COM mid-flight.
                _session_singleton._settings = fresh
        return _session_singleton


def reset_sqlacc_session_manager_for_tests() -> None:
    """Drop the singleton (unit tests only)."""
    global _session_singleton
    with _session_lock:
        if _session_singleton is not None:
            try:
                _session_singleton.close()
            except Exception:
                pass
            _session_singleton = None
