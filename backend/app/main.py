"""
L&T Neural Grid DERMS — FastAPI application entry point.

Handles:
  - Database initialisation and seed data
  - Router registration for all API modules
  - WebSocket real-time telemetry endpoint
  - React SPA static-file serving
  - Background asyncio tasks (grid simulation, dispatch, forecast, broadcast)
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.broadcast import broadcast_loop, manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def start_background_tasks() -> None:
    """Start all long-running asyncio background tasks."""
    from app.grid.simulation import grid_simulation_loop
    from app.dispatch.service import dispatch_loop
    from app.forecasting.service import forecast_loop

    asyncio.create_task(grid_simulation_loop(), name="grid_simulation")
    asyncio.create_task(dispatch_loop(), name="dispatch_loop")
    asyncio.create_task(forecast_loop(), name="forecast_loop")
    asyncio.create_task(broadcast_loop(manager), name="broadcast_loop")

    from app.scada_gateway.background import scada_push_loop
    asyncio.create_task(scada_push_loop(), name="scada_push_loop")

    from app.lv_network.background import dynamic_oe_loop
    asyncio.create_task(dynamic_oe_loop(), name="dynamic_oe_loop")

    from app.aggregator.kafka_transport import start_telemetry_consumer, kafka_enabled
    if kafka_enabled():
        from app.database import AsyncSessionLocal
        asyncio.create_task(
            start_telemetry_consumer(AsyncSessionLocal, "default"),
            name="kafka_consumer",
        )
        logger.info("Kafka telemetry consumer task started.")

    logger.info("All background tasks started.")


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run startup logic before the server begins accepting requests."""
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Starting %s v%s", settings.app_name, settings.version)

    # Initialise database (create tables)
    from app.database import init_db
    await init_db()
    logger.info("Database tables created / verified.")

    # Seed all demo data (idempotent)
    from app.database import AsyncSessionLocal
    from app.seed import seed_all
    async with AsyncSessionLocal() as db:
        await seed_all(db)
        await db.commit()
    logger.info("Seed data applied.")

    # Start background tasks
    await start_background_tasks()

    yield

    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "Distributed Energy Resource Management System — "
        "multi-deployment platform for SSEN South Scotland and PUVVNL Varanasi."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS — permissive for demo; tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers — core auth + platform modules
# ---------------------------------------------------------------------------

from app.auth.routes import router as auth_router  # noqa: E402

app.include_router(auth_router)

# Modules that exist with fully-prefixed routers
_optional_routers = [
    ("app.grid.routes", "router", None),
    ("app.dispatch.routes", "router", None),
    ("app.forecasting.routes", "router", None),
    ("app.optimization.routes", "router", None),
    ("app.settlement.routes", "router", None),
    ("app.admin.routes", "router", None),
    ("app.reporting.routes", "router", None),
    ("app.assets.routes", "router", None),
    ("app.counterparties.routes", "router", None),
    ("app.integrations.adms.simulator", "router", None),
    # Integration Configuration Manager — simulation/live mode per external system
    ("app.integrations.config_mgr.routes", "router", None),
    # DER Aggregator VTN Server — IEEE 2030.5 + OpenADR endpoints
    ("app.aggregator.routes", "router", None),
    # LV Network module — OSM/synthetic LV feeder topology + DistFlow power flow
    ("app.lv_network.routes", "router", None),
    # SCADA Gateway — outbound push to SCADA/ADMS/Historian + DaaS API key management
    ("app.scada_gateway.routes", "router", None),
]

# Modules that use short prefixes — we supply the API prefix at include time
_prefixed_routers = [
    ("app.programs.routes", "router", "/api/v1/programs"),
    ("app.contracts.routes", "router", "/api/v1/contracts"),
]

for module_path, attr, prefix in _optional_routers + _prefixed_routers:
    try:
        import importlib
        mod = importlib.import_module(module_path)
        router = getattr(mod, attr)
        if prefix:
            app.include_router(router, prefix=prefix)
        else:
            app.include_router(router)
        logger.debug("Registered router: %s", module_path)
    except (ModuleNotFoundError, AttributeError) as exc:
        logger.warning("Skipping router %s: %s", module_path, exc)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"])
async def health_check() -> JSONResponse:
    """Liveness probe — used by Render.com and load balancers."""
    return JSONResponse({"status": "ok", "version": settings.version})


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Real-time grid telemetry WebSocket."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; broadcast_loop pushes data
            data = await websocket.receive_text()
            # Echo ping/pong to maintain keep-alive from client
            if data == "ping":
                await manager.send_personal(websocket, {"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Static files — serve React SPA
# ---------------------------------------------------------------------------

_static_dir = settings.static_dir
if os.path.isdir(_static_dir):
    # Mount everything under /assets (Vite build output structure)
    _assets_path = os.path.join(_static_dir, "assets")
    if os.path.isdir(_assets_path):
        app.mount("/assets", StaticFiles(directory=_assets_path), name="spa-assets")

    _index_html = os.path.join(_static_dir, "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        """Catch-all route: serve index.html for SPA client-side routing."""
        # Serve exact file if it exists in the static dir
        candidate = os.path.join(_static_dir, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_index_html)

    logger.info("Serving React SPA from %s", _static_dir)
else:
    logger.info(
        "Static directory '%s' not found — running in API-only mode.", _static_dir
    )
