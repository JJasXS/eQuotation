"""FastAPI application entry point."""
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Load project-root .env (same pattern as main.py), regardless of current working directory
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)

_api_timing_logger = logging.getLogger("eq.api.timing")
_slow_route_ms = float((os.getenv("EQ_API_SLOW_MS") or "1000").strip() or "1000")
_log_all_routes = (os.getenv("EQ_API_LOG_ALL_MS", "") or "").strip().lower() in ("1", "true", "yes", "on")


class TimingMiddleware(BaseHTTPMiddleware):
    """Log request duration; warn when slower than EQ_API_SLOW_MS (default 1000)."""

    async def dispatch(self, request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - t0) * 1000.0
        path = request.url.path
        if _log_all_routes or ms >= _slow_route_ms:
            line = f"{request.method} {path} -> {getattr(response, 'status_code', '?')} in {ms:.0f}ms"
            if ms >= _slow_route_ms:
                _api_timing_logger.warning("slow %s", line)
            else:
                _api_timing_logger.info("%s", line)
        return response

# Import routes
from api.routes import health, customers, debug, local_customers, auth, dashboard, suppliers, purchase_requests

# Create FastAPI app
app = FastAPI(
    title="eQuotation API",
    description="Middleware API for SQL Accounting (SigV4 customer create) + optional COM reads",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost').split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TimingMiddleware)

# Include routes
app.include_router(health.router)
app.include_router(customers.router)
app.include_router(customers.compat_router)
app.include_router(debug.router)
app.include_router(local_customers.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(suppliers.router)
app.include_router(purchase_requests.router)

# Health check at root
@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "name": "eQuotation API",
        "version": "1.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    
    # Get configuration from environment
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', 8000))
    reload = os.getenv('API_RELOAD', 'true').lower() == 'true'
    
    print(f"Starting eQuotation API on {host}:{port}")
    print(f"API docs available at http://{host}:{port}/docs")
    
    uvicorn.run(
        "api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
