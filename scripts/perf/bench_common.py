"""Shared helpers for eQuotation performance benchmarks.

Secrets are loaded into the process environment but never printed.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "perf" / "results"
INVESTIGATION_DIR = REPO_ROOT / "perf" / "investigation"
DEPLOYED_ENV = Path(r"C:\Apps\eQuotation\.env")

DEFAULT_BASE = "http://127.0.0.1:8881"
DEFAULT_PORT = 8881

PAGE_SPECS = [
    {"id": "login", "path": "/login", "role": None},
    {"id": "admin", "path": "/admin", "role": "admin"},
    {"id": "create_quotation", "path": "/create-quotation", "role": "customer"},
    {"id": "view_quotation", "path": "/view-quotation", "role": "customer"},
    {"id": "admin_view_quotations", "path": "/admin/view-quotations", "role": "admin"},
    {"id": "procurement_report", "path": "/admin/procurement?tab=report", "role": "admin"},
    {"id": "procurement_view", "path": "/admin/procurement?tab=view", "role": "admin"},
    # Isolate create after report/view so stock-card work does not inflate TTFB.
    {"id": "procurement_create", "path": "/admin/procurement?tab=create", "role": "admin", "settle_before_sec": 3.0},
    {"id": "invoice_aging", "path": "/admin/invoice-aging", "role": "admin"},
    {"id": "supplier_bidding", "path": "/supplier/bidding", "role": "supplier"},
]

# Mixed read-only GETs for concurrency (pages + APIs + static).
READONLY_API_PATHS = [
    "/login",
    "/admin",
    "/admin/procurement",
    "/api/admin/procurement/stock-card",
    "/api/admin/procurement/locations",
    "/api/admin/procurement/suppliers",
    "/static/css/admin.css",
    "/static/js/admin_helpers.js",
]

# API-only concurrency slice (no HTML/static dilution). Admin session.
READONLY_API_ONLY_PATHS = [
    "/api/admin/procurement/stock-card",
    "/api/admin/procurement/locations",
    "/api/admin/procurement/suppliers",
    "/api/admin/procurement/purchase-requests",
    "/api/admin/get_all_quotations",
]


def ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    INVESTIGATION_DIR.mkdir(parents=True, exist_ok=True)


def load_bench_env() -> None:
    """Load deployed then repo .env without printing values. Force bench overrides."""
    if DEPLOYED_ENV.is_file():
        load_dotenv(dotenv_path=str(DEPLOYED_ENV), override=True)
    repo_env = REPO_ROOT / ".env"
    if repo_env.is_file():
        load_dotenv(dotenv_path=str(repo_env), override=False)
    os.environ["FLASK_HOST"] = "127.0.0.1"
    os.environ["FLASK_PORT"] = str(DEFAULT_PORT)
    os.environ["EQ_GUIDE_CAPTURE"] = "1"
    os.environ["TENANT_BOOTSTRAP_REFRESH_SECONDS"] = "0"
    os.environ["TenantBootstrap__ConfigRefreshSeconds"] = "0"


def base_url() -> str:
    return (os.getenv("EQ_PERF_BASE") or DEFAULT_BASE).rstrip("/")


def pid_path() -> Path:
    return RESULTS_DIR / "bench.pid"


def read_bench_pid() -> int | None:
    p = pid_path()
    if not p.is_file():
        return None
    try:
        return int(p.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def sample_process(pid: int | None) -> dict[str, Any]:
    """Sample Windows process memory/handles/threads via PowerShell (no psutil)."""
    if not pid:
        return {"status": "NOT RUN", "blocker": "no bench pid"}
    try:
        import subprocess

        # Build JSON in PowerShell without nested @{{ }} escaping issues.
        ps = (
            f"$p = Get-Process -Id {int(pid)} -ErrorAction Stop; "
            "$o = New-Object psobject -Property @{ "
            "WorkingSetMB = [math]::Round($p.WorkingSet64/1MB, 2); "
            "PrivateMB = [math]::Round($p.PrivateMemorySize64/1MB, 2); "
            "Handles = $p.HandleCount; "
            "Threads = $p.Threads.Count; "
            "CPU = $p.CPU "
            "}; $o | ConvertTo-Json -Compress"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            timeout=15,
        )
        data = json.loads(out)
        data["pid"] = pid
        data["status"] = "ok"
        return data
    except Exception as exc:
        return {"status": "NOT RUN", "blocker": str(exc)[:200], "pid": pid}


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    k = (len(ordered) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return float(ordered[f])
    return float(ordered[f] + (ordered[c] - ordered[f]) * (k - f))


def summarize_ms(samples: list[float]) -> dict[str, Any]:
    if not samples:
        return {"n": 0, "median": None, "p95": None, "min": None, "max": None, "mean": None}
    return {
        "n": len(samples),
        "median": round(statistics.median(samples), 2),
        "p95": round(percentile(samples, 95) or 0, 2),
        "min": round(min(samples), 2),
        "max": round(max(samples), 2),
        "mean": round(statistics.mean(samples), 2),
    }


def seed_session(client: httpx.Client, role: str) -> dict[str, Any]:
    """POST /api/guide_capture_login and keep cookies on the client."""
    payload = {"role": role}
    if role == "customer":
        code = (os.getenv("EQ_PERF_CUSTOMER_CODE") or "").strip()
        if code:
            payload["customer_code"] = code
    r = client.post("/api/guide_capture_login", json=payload, timeout=15.0)
    if r.status_code != 200:
        raise RuntimeError(f"guide_capture_login failed: HTTP {r.status_code} {r.text[:200]}")
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"guide_capture_login rejected: {data}")
    return data


def wait_for_server(url: str, timeout_sec: float = 90.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            r = httpx.get(f"{url.rstrip('/')}/login", timeout=3.0)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    # PowerShell Set-Content may write UTF-8 BOM.
    return json.loads(path.read_text(encoding="utf-8-sig"))
