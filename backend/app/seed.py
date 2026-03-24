"""
Central seed orchestration for the L&T Neural Grid DERMS platform.

Calling ``await seed_all(db)`` is idempotent — every individual seed function
checks whether its records already exist before inserting.

Typical usage (from a startup hook or CLI):

    async with AsyncSessionLocal() as db:
        await seed_all(db)
        await db.commit()
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def seed_all(db: AsyncSession) -> None:
    """Seed all demo data for both SSEN and PUVVNL deployments. Idempotent."""
    logger.info("Starting seed_all...")

    # 1. Auth: deployments and default users
    try:
        from app.auth.service import seed_default_data  # noqa: PLC0415
        await seed_default_data(db)
        logger.info("  auth seeded")
    except Exception as exc:
        logger.warning("  auth seed failed: %s", exc)

    # 2. Counterparties (aggregators, industry, residential groups)
    try:
        from app.counterparties.service import seed_counterparties  # noqa: PLC0415
        await seed_counterparties(db)
        logger.info("  counterparties seeded")
    except Exception as exc:
        logger.warning("  counterparties seed failed: %s", exc)

    # 3. Grid topology (CMZs, feeders, substations)
    try:
        from app.grid.simulation import seed_grid_topology  # noqa: PLC0415
        await seed_grid_topology(db)
        logger.info("  grid topology seeded")
    except Exception as exc:
        logger.warning("  grid topology seed skipped (module not available): %s", exc)

    # 4. DER Assets — SSEN
    try:
        from app.assets.service import seed_demo_assets  # noqa: PLC0415
        await seed_demo_assets(db, "ssen")
        logger.info("  SSEN assets seeded")
    except Exception as exc:
        logger.warning("  SSEN assets seed failed: %s", exc)

    # 5. DER Assets — PUVVNL
    try:
        from app.assets.service import seed_demo_assets  # noqa: PLC0415
        await seed_demo_assets(db, "puvvnl")
        logger.info("  PUVVNL assets seeded")
    except Exception as exc:
        logger.warning("  PUVVNL assets seed failed: %s", exc)

    # 6. Flexibility Programs
    try:
        from app.programs.service import seed_demo_programs  # noqa: PLC0415
        await seed_demo_programs(db)
        logger.info("  programs seeded")
    except Exception as exc:
        logger.warning("  programs seed failed: %s", exc)

    # 7. Integration configs (simulation/live mode per external system)
    try:
        from app.integrations.config_mgr.service import seed_integration_configs  # noqa: PLC0415
        await seed_integration_configs(db)
        logger.info("  integration configs seeded")
    except Exception as exc:
        logger.warning("  integration configs seed failed: %s", exc)

    # 8. LV networks (synthetic behind DTs)
    try:
        from app.lv_network.service import seed_lv_networks  # noqa: PLC0415
        await seed_lv_networks(db)
        logger.info("  LV networks seeded")
    except Exception as exc:
        logger.warning("  LV networks seed skipped: %s", exc)

    # 9. SCADA gateway endpoints
    try:
        from app.scada_gateway.service import seed_scada_endpoints  # noqa: PLC0415
        await seed_scada_endpoints(db)
        logger.info("  SCADA endpoints seeded")
    except Exception as exc:
        logger.warning("  SCADA endpoints seed skipped: %s", exc)

    logger.info("seed_all complete.")
