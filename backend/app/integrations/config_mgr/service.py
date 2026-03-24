"""
Service layer for Integration Configuration Manager.

Provides CRUD operations, connection testing, and simulation parameter
management for each external system integration (ADMS, aggregators, MDMS, etc.).
"""
from __future__ import annotations

import base64
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.config_mgr.models import IntegrationConfig


# ---------------------------------------------------------------------------
# Default simulation parameters per integration type
# ---------------------------------------------------------------------------

DEFAULT_SIM_PARAMS: Dict[str, dict] = {
    "ADMS": {
        "solar_peak_factor": 1.0,
        "cloud_noise_factor": 0.05,
        "feeder_loading_warn_pct": 80.0,
        "feeder_loading_max_pct": 100.0,
        "voltage_nominal_v": 230.0,
        "voltage_high_warn_v": 244.0,
        "voltage_low_warn_v": 216.0,
        "voltage_high_trip_v": 253.0,
        "voltage_low_trip_v": 207.0,
        "adms_poll_interval_seconds": 30,
    },
    "DER_AGGREGATOR_IEEE2030_5": {
        "aggregator_poll_interval_seconds": 20,
        "oe_ack_timeout_seconds": 10,
        "default_response_time_seconds": 5,
    },
    "DER_AGGREGATOR_OPENADR": {
        "vtn_push_enabled": True,
        "event_lead_time_minutes": 10,
        "ven_registration_timeout_minutes": 5,
    },
    "MDMS": {
        "baseline_lookback_days": 10,
        "meter_read_interval_minutes": 15,
        "sftp_poll_interval_minutes": 15,
    },
    "WEATHER_API": {
        "provider": "simulated",
        "forecast_horizon_hours": 48,
    },
}


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def list_configs(db: AsyncSession, deployment_id: str) -> List[IntegrationConfig]:
    """Return all integration configs for a deployment."""
    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.deployment_id == deployment_id
        ).order_by(IntegrationConfig.integration_type)
    )
    return result.scalars().all()


async def get_config(
    db: AsyncSession, config_id: str, deployment_id: str
) -> Optional[IntegrationConfig]:
    """Fetch a single config by ID, scoped to the deployment."""
    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.id == config_id,
            IntegrationConfig.deployment_id == deployment_id,
        )
    )
    return result.scalar_one_or_none()


async def create_config(
    db: AsyncSession,
    data,
    deployment_id: str,
    user_email: str = "system",
) -> IntegrationConfig:
    """Create a new integration config with default sim_params for the type."""
    cfg = IntegrationConfig(
        id=str(uuid.uuid4()),
        deployment_id=deployment_id,
        integration_type=data.integration_type,
        name=data.name,
        description=getattr(data, "description", None),
        mode=getattr(data, "mode", "SIMULATION"),
        base_url=getattr(data, "base_url", None),
        auth_type=getattr(data, "auth_type", "NONE"),
        auth_config=(
            json.dumps(data.auth_config)
            if getattr(data, "auth_config", None)
            else None
        ),
        polling_interval_seconds=getattr(data, "polling_interval_seconds", 30),
        timeout_seconds=getattr(data, "timeout_seconds", 10),
        is_active=getattr(data, "is_active", True),
        sim_params=json.dumps(DEFAULT_SIM_PARAMS.get(data.integration_type, {})),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(cfg)
    await db.flush()
    return cfg


async def update_config(
    db: AsyncSession,
    config_id: str,
    data,
    deployment_id: str,
) -> Optional[IntegrationConfig]:
    """
    Apply partial updates to an existing config.

    sim_params are merged: existing keys are kept and incoming keys override.
    """
    cfg = await get_config(db, config_id, deployment_id)
    if not cfg:
        return None

    for field in [
        "name",
        "description",
        "mode",
        "base_url",
        "auth_type",
        "polling_interval_seconds",
        "timeout_seconds",
        "is_active",
    ]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(cfg, field, val)

    if getattr(data, "auth_config", None) is not None:
        cfg.auth_config = json.dumps(data.auth_config)

    if getattr(data, "sim_params", None) is not None:
        existing: dict = {}
        if cfg.sim_params:
            try:
                existing = json.loads(cfg.sim_params)
            except Exception:
                pass
        # Convert Pydantic model to dict if needed, stripping None values
        incoming = data.sim_params
        if hasattr(incoming, "model_dump"):
            incoming = {k: v for k, v in incoming.model_dump().items() if v is not None}
        existing.update(incoming)
        cfg.sim_params = json.dumps(existing)

    cfg.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return cfg


async def delete_config(
    db: AsyncSession, config_id: str, deployment_id: str
) -> bool:
    """Delete a config. Returns True if found and deleted, False if not found."""
    cfg = await get_config(db, config_id, deployment_id)
    if not cfg:
        return False
    await db.delete(cfg)
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

async def test_connection(
    db: AsyncSession, config_id: str, deployment_id: str
) -> dict:
    """
    Test connectivity to the configured endpoint.

    - SIMULATION mode: always returns OK immediately (no network call).
    - LIVE mode: makes an HTTP GET to base_url, applying auth headers.

    Updates last_test_at / last_test_status / last_test_message on the record.
    Returns a dict compatible with ConnectionTestResult schema.
    """
    cfg = await get_config(db, config_id, deployment_id)
    if not cfg:
        return {
            "status": "FAILED",
            "message": "Config not found",
            "latency_ms": None,
            "tested_at": datetime.now(timezone.utc).isoformat(),
        }

    # Simulation mode — always OK
    if cfg.mode == "SIMULATION":
        cfg.last_test_at = datetime.now(timezone.utc)
        cfg.last_test_status = "OK"
        cfg.last_test_message = "Simulation mode active — no live endpoint required"
        await db.flush()
        return {
            "status": "OK",
            "message": cfg.last_test_message,
            "latency_ms": 0,
            "tested_at": cfg.last_test_at.isoformat(),
        }

    # Live mode — require base_url
    if not cfg.base_url:
        cfg.last_test_at = datetime.now(timezone.utc)
        cfg.last_test_status = "FAILED"
        cfg.last_test_message = "No base_url configured for LIVE mode"
        await db.flush()
        return {
            "status": "FAILED",
            "message": cfg.last_test_message,
            "latency_ms": None,
            "tested_at": cfg.last_test_at.isoformat(),
        }

    # Build auth headers
    headers: dict = {}
    if cfg.auth_config:
        try:
            auth = json.loads(cfg.auth_config)
            if cfg.auth_type == "API_KEY":
                headers["X-API-Key"] = auth.get("api_key", "")
            elif cfg.auth_type == "BASIC":
                raw = f"{auth.get('username', '')}:{auth.get('password', '')}"
                encoded = base64.b64encode(raw.encode()).decode()
                headers["Authorization"] = f"Basic {encoded}"
        except Exception:
            pass

    t0 = time.time()
    try:
        async with httpx.AsyncClient(
            timeout=cfg.timeout_seconds, headers=headers
        ) as client:
            resp = await client.get(cfg.base_url)
        latency_ms = int((time.time() - t0) * 1000)
        if resp.status_code < 500:
            status = "OK"
            message = f"HTTP {resp.status_code} in {latency_ms}ms"
        else:
            status = "FAILED"
            message = f"HTTP {resp.status_code} — server error"
    except httpx.TimeoutException:
        latency_ms = int((time.time() - t0) * 1000)
        status = "TIMEOUT"
        message = f"Request timed out after {cfg.timeout_seconds}s"
    except Exception as exc:
        latency_ms = None
        status = "FAILED"
        message = str(exc)

    cfg.last_test_at = datetime.now(timezone.utc)
    cfg.last_test_status = status
    cfg.last_test_message = message
    await db.flush()

    return {
        "status": status,
        "message": message,
        "latency_ms": latency_ms,
        "tested_at": cfg.last_test_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Simulation parameters helpers
# ---------------------------------------------------------------------------

async def get_sim_params(
    db: AsyncSession, deployment_id: str, integration_type: str
) -> dict:
    """
    Return merged simulation parameters for a given integration type.

    Starts from DEFAULT_SIM_PARAMS, then overlays any overrides stored in the
    active IntegrationConfig record for that deployment + type.
    """
    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.deployment_id == deployment_id,
            IntegrationConfig.integration_type == integration_type,
            IntegrationConfig.is_active == True,  # noqa: E712
        )
    )
    cfg = result.scalar_one_or_none()
    defaults = DEFAULT_SIM_PARAMS.get(integration_type, {})

    if cfg and cfg.sim_params:
        try:
            overrides = json.loads(cfg.sim_params)
            return {**defaults, **overrides}
        except Exception:
            pass

    return dict(defaults)


async def update_sim_params(
    db: AsyncSession,
    config_id: str,
    deployment_id: str,
    params: dict,
) -> Optional[IntegrationConfig]:
    """
    Merge-update simulation parameters on a config record.

    Existing keys not present in `params` are preserved.
    """
    cfg = await get_config(db, config_id, deployment_id)
    if not cfg:
        return None

    existing: dict = {}
    if cfg.sim_params:
        try:
            existing = json.loads(cfg.sim_params)
        except Exception:
            pass

    existing.update({k: v for k, v in params.items() if v is not None})
    cfg.sim_params = json.dumps(existing)
    cfg.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return cfg


async def toggle_mode(
    db: AsyncSession, config_id: str, deployment_id: str
) -> Optional[IntegrationConfig]:
    """Switch the config mode between SIMULATION and LIVE."""
    cfg = await get_config(db, config_id, deployment_id)
    if not cfg:
        return None
    cfg.mode = "LIVE" if cfg.mode == "SIMULATION" else "SIMULATION"
    cfg.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return cfg


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

async def seed_integration_configs(db: AsyncSession) -> None:
    """
    Seed default integration configs for both SSEN and PUVVNL deployments.
    Idempotent — skips any (deployment_id, integration_type) pair that already exists.
    """
    DEFAULTS = [
        # SSEN
        (
            "ssen",
            "ADMS",
            "GE ADMS (Simulated)",
            "Simulated GE ADMS topology & SCADA state",
        ),
        (
            "ssen",
            "DER_AGGREGATOR_IEEE2030_5",
            "Alpha Flex IEEE 2030.5",
            "Alpha Flex Ltd aggregator — IEEE 2030.5 DER server",
        ),
        (
            "ssen",
            "DER_AGGREGATOR_OPENADR",
            "Alpha Flex OpenADR",
            "Alpha Flex Ltd aggregator — OpenADR 2.0b VTN",
        ),
        (
            "ssen",
            "MDMS",
            "SSEN AMR/MDMS",
            "Smart meter data ingestion — 15-min interval",
        ),
        (
            "ssen",
            "WEATHER_API",
            "Weather Forecast",
            "Solar irradiance & wind forecast feed",
        ),
        # PUVVNL
        (
            "puvvnl",
            "ADMS",
            "PUVVNL DMS (Simulated)",
            "Simulated distribution management system",
        ),
        (
            "puvvnl",
            "DER_AGGREGATOR_IEEE2030_5",
            "GMR AMISP IEEE 2030.5",
            "GMR Energy Services aggregator",
        ),
        (
            "puvvnl",
            "DER_AGGREGATOR_OPENADR",
            "GMR AMISP OpenADR",
            "GMR Energy Services — OpenADR 2.0b",
        ),
        (
            "puvvnl",
            "MDMS",
            "GMR MDMS",
            "GMR metering data management system",
        ),
        (
            "puvvnl",
            "WEATHER_API",
            "IMD Weather API",
            "India Meteorological Department solar forecast",
        ),
    ]

    existing_result = await db.execute(select(IntegrationConfig))
    existing = {
        (c.deployment_id, c.integration_type)
        for c in existing_result.scalars().all()
    }

    for dep, itype, name, desc in DEFAULTS:
        if (dep, itype) in existing:
            continue
        cfg = IntegrationConfig(
            id=str(uuid.uuid4()),
            deployment_id=dep,
            integration_type=itype,
            name=name,
            description=desc,
            mode="SIMULATION",
            is_active=True,
            sim_params=json.dumps(DEFAULT_SIM_PARAMS.get(itype, {})),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(cfg)

    await db.flush()
