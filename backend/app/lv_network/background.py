"""
Background task: dynamic OE recalculation every 30 minutes.

Runs compute_cmz_dynamic_oe() for every CMZ in every active deployment.
Results stored in DynamicOESlot table and used by:
  - forecasting/service.py:generate_oe_headroom_forecast()
  - dispatch/ssen_messages.py (48h OE time series)
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def dynamic_oe_loop() -> None:
    """
    Async background loop. Runs every 30 minutes.
    Calculates dynamic OE for all CMZs using time-series DistFlow.
    """
    logger.info("dynamic_oe_loop started (interval=30min)")
    await asyncio.sleep(30)  # initial delay — let DB seed complete first
    while True:
        try:
            from app.database import AsyncSessionLocal
            from app.lv_network.dynamic_oe import compute_cmz_dynamic_oe

            async with AsyncSessionLocal() as db:
                # Get all distinct deployment_id + cmz_id combinations from GridNode
                try:
                    from sqlalchemy import select, distinct
                    from app.grid.models import GridNode
                    result = await db.execute(
                        select(distinct(GridNode.deployment_id), GridNode.cmz_id)
                        .where(GridNode.cmz_id.isnot(None))
                    )
                    pairs = result.all()
                except Exception:
                    pairs = [("ssen", "CMZ-EDINBURGH-NORTH"), ("puvvnl", "CMZ-VARANASI-CENTRAL")]

                for deployment_id, cmz_id in pairs:
                    if not cmz_id:
                        continue
                    try:
                        slots = await compute_cmz_dynamic_oe(db, cmz_id, deployment_id)
                        await db.commit()
                        logger.info(
                            "Dynamic OE computed: deployment=%s cmz=%s slots=%d",
                            deployment_id, cmz_id, len(slots)
                        )
                    except Exception as exc:
                        logger.warning("Dynamic OE failed for %s/%s: %s", deployment_id, cmz_id, exc)
                        await db.rollback()
        except Exception as exc:
            logger.error("dynamic_oe_loop error: %s", exc)

        await asyncio.sleep(30 * 60)  # 30 minutes
