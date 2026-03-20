"""
Entry point for running the Neural Grid DERMS backend.

Usage:
    python run.py              # Production (PORT env var or default 8080)
    DEBUG=true python run.py   # Development with auto-reload
"""
import uvicorn
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
