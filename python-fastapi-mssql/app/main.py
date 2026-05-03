"""
MSSQL FastAPI Deployment Service
Main application entry point
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from fastapi.responses import JSONResponse
import logging
from pathlib import Path

# Import routers
from app.routes import deploy, health, logs
from app.config import settings

# Logging configuration
Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler(Path(settings.LOG_DIR) / "app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="MSSQL Deployment API",
    description="FastAPI service for MSSQL deployment automation using native Python SSH",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Include routers
app.include_router(deploy.router, prefix="/api/v1/deploy", tags=["deployment"])
app.include_router(health.router, prefix="/api/v1/health", tags=["health"])
app.include_router(logs.router, prefix="/api/v1/logs", tags=["logs"])


@app.get("/", tags=["root"])
async def root():
    """Root endpoint - API information"""
    return {
        "service": "MSSQL Deployment API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/api/docs",
        "endpoints": {
            "deploy": "/api/v1/deploy",
            "health": "/api/v1/health",
            "logs": "/api/v1/logs",
        }
    }


@app.get("/api/v1/", tags=["api"])
async def api_root():
    """API v1 root"""
    return {
        "version": "1.0.0",
        "endpoints": {
            "deploy": "/api/v1/deploy",
            "health": "/api/v1/health",
            "logs": "/api/v1/logs",
        }
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
