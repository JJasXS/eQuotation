"""Start a localhost-only eQuotation instance for performance benchmarks.

Binds 127.0.0.1:8881, enables EQ_GUIDE_CAPTURE, disables tenant refresh worker,
skips database DDL initialization. Does not touch the live :8880 service.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PERF_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PERF_DIR) not in sys.path:
    sys.path.insert(0, str(PERF_DIR))

from bench_common import (  # noqa: E402
    DEFAULT_PORT,
    RESULTS_DIR,
    ensure_dirs,
    load_bench_env,
    pid_path,
)


def main() -> int:
    ensure_dirs()
    load_bench_env()

    # Import AFTER env overrides so main.py bootstrap sees the right values.
    import main as eq_main  # noqa: WPS433

    flask_host = "127.0.0.1"
    flask_port = int(os.getenv("FLASK_PORT", str(DEFAULT_PORT)))
    mount = getattr(eq_main, "EQ_SQL_API_MOUNT_PATH", "/eq-sql-api")

    # Keep FastAPI base URL pointed at this instance.
    eq_main.FASTAPI_BASE_URL = f"http://127.0.0.1:{flask_port}{mount}".rstrip("/")

    from asgiref.wsgi import WsgiToAsgi
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles
    import uvicorn
    from api.app import app as fastapi_app

    flask_asgi = WsgiToAsgi(eq_main.app)
    static_dir = REPO_ROOT / "static"
    routes = [Mount(mount, fastapi_app)]
    if static_dir.is_dir():
        routes.append(Mount("/static", StaticFiles(directory=str(static_dir)), name="eq_static"))
    routes.append(Mount("/", flask_asgi))
    unified = Starlette(routes=routes)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    pid_path().write_text(str(os.getpid()), encoding="utf-8")
    print(
        f"[perf] bench instance pid={os.getpid()} http://{flask_host}:{flask_port} "
        f"(guide_capture=on, tenant_refresh=off, ddl=skipped)",
        flush=True,
    )
    uvicorn.run(
        unified,
        host=flask_host,
        port=flask_port,
        log_level="warning",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
