"""
WebSocket connection manager and broadcast loop for the Neural Grid DERMS.
Pushes real-time grid state to all connected browser clients every 5 seconds.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages a set of active WebSocket connections and fan-out broadcast."""

    def __init__(self) -> None:
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await ws.accept()
        self.active.add(ws)
        logger.info("WebSocket connected. Active connections: %d", len(self.active))

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket from the active set."""
        self.active.discard(ws)
        logger.info("WebSocket disconnected. Active connections: %d", len(self.active))

    async def broadcast(self, data: dict) -> None:
        """Send a JSON payload to all connected clients, removing stale connections."""
        if not self.active:
            return

        payload = json.dumps(data, default=str)
        dead: Set[WebSocket] = set()

        for ws in list(self.active):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)

        for ws in dead:
            self.disconnect(ws)

    async def send_personal(self, ws: WebSocket, data: dict) -> None:
        """Send a JSON payload to a single WebSocket client."""
        try:
            await ws.send_text(json.dumps(data, default=str))
        except Exception:
            self.disconnect(ws)


# Singleton shared across the application
manager = ConnectionManager()


async def broadcast_loop(mgr: ConnectionManager) -> None:
    """
    Background task: broadcast real-time grid state to all WebSocket clients
    every 5 seconds.
    """
    while True:
        await asyncio.sleep(5)
        if not mgr.active:
            continue
        try:
            from app.grid.simulation import get_grid_state  # lazy to avoid circular import

            state = get_grid_state()
            await mgr.broadcast({"type": "grid_update", "data": state})
        except Exception as exc:
            logger.warning("broadcast_loop error: %s", exc)
