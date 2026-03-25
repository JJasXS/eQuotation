"""FastAPI application entry point."""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import routes
from api.routes import health, customers

# Create FastAPI app
app = FastAPI(
    title="eQuotation API",
    description="REST API layer for SQL Account integration",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost').split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(health.router, prefix="/api")
app.include_router(customers.router, prefix="/api")

# Health check at root
@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "name": "eQuotation API",
        "version": "1.0.0",
        "docs": "/api/docs"
    }


if __name__ == "__main__":
    import uvicorn
    
    # Get configuration from environment
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', 8000))
    reload = os.getenv('API_RELOAD', 'true').lower() == 'true'
    
    print(f"Starting eQuotation API on {host}:{port}")
    print(f"API docs available at http://{host}:{port}/api/docs")
    
    uvicorn.run(
        "api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
