"""
SCADA Gateway background task.

Runs a periodic push cycle for every active SCADA endpoint across all
known deployments.  Errors are logged but never propagated so the loop
stays alive for the lifetime of the application.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# How often (seconds) the push loop wakes up and checks whether any
# endpoint is due for a push.  Individual endpoint push_interval_seconds
# values are not yet tracked here — the loop simply pushes all active
# endpoints every LOOP_INTERVAL seconds.  A future enhancement could
# track per-endpoint last-push timestamps and honour their individual
# intervals.
LOOP_INTERVAL = 30


async def scada_push_loop() -> None:
    """
    Background task: push LV DERMS data to all active SCADA endpoints.

    Iterates over all configured deployments and calls
    ``service.run_push_cycle`` for each one.  Runs every LOOP_INTERVAL
    seconds.  Logs errors but never raises so the task survives transient
    failures.
    """
    logger.info("scada_push_loop started (interval=%ds)", LOOP_INTERVAL)

    while True:
        await asyncio.sleep(LOOP_INTERVAL)

        try:
            from app.database import AsyncSessionLocal
            from app.scada_gateway import service

            # Determine deployments that have at least one active endpoint
            from sqlalchemy import select
            from app.scada_gateway.models import SCADAEndpoint

            async with AsyncSessionLocal() as db:
                deployment_rows = (
                    await db.execute(
                        select(SCADAEndpoint.deployment_id)
                        .where(SCADAEndpoint.is_active.is_(True))
                        .distinct()
                    )
                ).scalars().all()

            deployment_ids = list(deployment_rows)

            if not deployment_ids:
                logger.debug("scada_push_loop: no active endpoints found, sleeping.")
                continue

            for deployment_id in deployment_ids:
                try:
                    async with AsyncSessionLocal() as db:
                        results = await service.run_push_cycle(db, deployment_id)
                        await db.commit()

                    ok_count = sum(1 for r in results if r.get("status") in ("OK", "SIMULATED"))
                    fail_count = len(results) - ok_count
                    logger.debug(
                        "scada_push_loop: deployment=%s pushed=%d ok=%d fail=%d",
                        deployment_id,
                        len(results),
                        ok_count,
                        fail_count,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "scada_push_loop: run_push_cycle failed for deployment %s: %s",
                        deployment_id,
                        exc,
                    )

        except asyncio.CancelledError:
            logger.info("scada_push_loop cancelled, exiting.")
            return

        except Exception as exc:  # noqa: BLE001
            logger.error("scada_push_loop: unexpected error: %s", exc)
