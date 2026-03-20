"""
Forecasting module — pure Python implementation.

Uses time-of-day patterns, solar physics approximation, and EV charging
patterns to produce realistic 48-hour ahead forecasts at 30-minute intervals.

For production: replace the generation functions with proper ML model
inference (e.g. LightGBM, Prophet, or a neural net served via ONNX).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.config import settings
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


# ── Solar forecast ────────────────────────────────────────────────────────────

def generate_solar_forecast(deployment_id: str, horizon_hours: int = 48) -> List[dict]:
    """
    Generate 30-minute interval solar generation forecast.
    Bell-curve peaking at solar noon (12:30 local time).
    Confidence interval widens with forecast horizon.

    Returns list of {timestamp, value_kw, confidence_low, confidence_high}.
    """
    from app.grid.simulation import DEPLOYMENT_TOPOLOGIES

    topo = DEPLOYMENT_TOPOLOGIES.get(deployment_id, {})
    tz_offset = topo.get("timezone_offset", 0.0)

    # Total installed PV nameplate for this deployment (rough estimate)
    total_pv_kw = 150.0 if deployment_id == "ssen" else 45.0

    results: List[dict] = []
    base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    for i in range(horizon_hours * 2):  # 30-min intervals
        dt = base_time + timedelta(minutes=30 * i)
        local_hour = ((dt.hour + dt.minute / 60.0) + tz_offset) % 24.0

        if local_hour < 6.0 or local_hour > 18.5:
            sf = 0.0
        else:
            peak_hour = 12.5
            width = 3.2
            sf = math.exp(-((local_hour - peak_hour) ** 2) / (2.0 * width ** 2))

        forecast_kw = total_pv_kw * sf
        noise = random.gauss(0.0, forecast_kw * 0.08)
        forecast_kw = max(0.0, forecast_kw + noise)

        # Confidence interval widens with horizon
        horizon_factor = 1.0 + (i / (horizon_hours * 2)) * 0.15
        half_band = forecast_kw * 0.12 * horizon_factor

        results.append({
            "timestamp": dt.isoformat(),
            "value_kw": round(forecast_kw, 1),
            "confidence_low": round(max(0.0, forecast_kw - half_band), 1),
            "confidence_high": round(forecast_kw + half_band, 1),
        })

    return results


# ── Load forecast ─────────────────────────────────────────────────────────────

def generate_load_forecast(deployment_id: str, horizon_hours: int = 48) -> List[dict]:
    """
    Generate 30-minute interval demand forecast.
    Uses time-of-day load profile with day-of-week adjustment.

    Returns list of {timestamp, value_kw, confidence_low, confidence_high}.
    """
    from app.grid.simulation import DEPLOYMENT_TOPOLOGIES, load_factor

    topo = DEPLOYMENT_TOPOLOGIES.get(deployment_id, {})
    tz_offset = topo.get("timezone_offset", 0.0)

    total_load_kw = 800.0 if deployment_id == "ssen" else 350.0

    results: List[dict] = []
    base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    for i in range(horizon_hours * 2):
        dt = base_time + timedelta(minutes=30 * i)
        local_hour = ((dt.hour + dt.minute / 60.0) + tz_offset) % 24.0

        # Weekend factor (lower demand on weekends)
        weekday = dt.weekday()
        weekend_factor = 0.85 if weekday >= 5 else 1.0

        lf = load_factor(local_hour, deployment_id) * weekend_factor
        forecast_kw = total_load_kw * lf
        noise = random.gauss(0.0, forecast_kw * 0.04)
        forecast_kw = max(0.0, forecast_kw + noise)

        horizon_factor = 1.0 + (i / (horizon_hours * 2)) * 0.08
        band = forecast_kw * 0.07 * horizon_factor

        results.append({
            "timestamp": dt.isoformat(),
            "value_kw": round(forecast_kw, 1),
            "confidence_low": round(max(0.0, forecast_kw - band), 1),
            "confidence_high": round(forecast_kw + band, 1),
        })

    return results


# ── Flex availability forecast ────────────────────────────────────────────────

def generate_flex_availability_forecast(deployment_id: str, horizon_hours: int = 48) -> List[dict]:
    """
    Forecast available flex capacity (kW dispatchable at short notice).
    Based on: V2G/BESS SoC trajectory, EV charging patterns, HP flexibility.

    Returns list of {timestamp, value_kw, confidence_low, confidence_high}.
    """
    tz_offset = 5.5 if deployment_id == "puvvnl" else 0.0
    total_flex_kw = 120.0 if deployment_id == "ssen" else 30.0

    results: List[dict] = []
    base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    for i in range(horizon_hours * 2):
        dt = base_time + timedelta(minutes=30 * i)
        local_hour = ((dt.hour + dt.minute / 60.0) + tz_offset) % 24.0

        # EV availability pattern: parked at home evenings and overnight
        if local_hour >= 18.0 or local_hour < 7.0:
            ev_factor = 0.75
        elif 7.0 <= local_hour < 9.0:
            ev_factor = 0.45  # leaving for work
        elif 9.0 <= local_hour < 17.0:
            ev_factor = 0.20  # away during working hours
        else:
            ev_factor = 0.35  # returning home

        flex_kw = total_flex_kw * ev_factor * random.uniform(0.88, 1.05)
        flex_kw = max(0.0, flex_kw)

        horizon_factor = 1.0 + (i / (horizon_hours * 2)) * 0.20
        band = flex_kw * 0.15 * horizon_factor

        results.append({
            "timestamp": dt.isoformat(),
            "value_kw": round(flex_kw, 1),
            "confidence_low": round(max(0.0, flex_kw - band), 1),
            "confidence_high": round(flex_kw + band, 1),
        })

    return results


# ── DB persistence ────────────────────────────────────────────────────────────

async def run_forecast_update(db, deployment_id: str) -> dict:
    """Generate and persist all forecast types for a deployment."""
    from app.forecasting.models import ForecastRecord

    now = datetime.now(timezone.utc)

    solar_values = generate_solar_forecast(deployment_id, 48)
    solar_rec = ForecastRecord(
        id=str(uuid.uuid4()),
        deployment_id=deployment_id,
        forecast_type="SOLAR",
        generated_at=now,
        valid_from=now,
        valid_to=now + timedelta(hours=48),
        interval_minutes=30,
        values=json.dumps(solar_values),
        model_version="1.0-solar-physics",
    )
    db.add(solar_rec)

    load_values = generate_load_forecast(deployment_id, 48)
    load_rec = ForecastRecord(
        id=str(uuid.uuid4()),
        deployment_id=deployment_id,
        forecast_type="LOAD",
        generated_at=now,
        valid_from=now,
        valid_to=now + timedelta(hours=48),
        interval_minutes=30,
        values=json.dumps(load_values),
        model_version="1.0-pattern",
    )
    db.add(load_rec)

    flex_values = generate_flex_availability_forecast(deployment_id, 48)
    flex_rec = ForecastRecord(
        id=str(uuid.uuid4()),
        deployment_id=deployment_id,
        forecast_type="FLEX_AVAILABILITY",
        generated_at=now,
        valid_from=now,
        valid_to=now + timedelta(hours=48),
        interval_minutes=30,
        values=json.dumps(flex_values),
        model_version="1.0-ev-pattern",
    )
    db.add(flex_rec)

    await db.commit()

    return {
        "solar": solar_values[:8],
        "load": load_values[:8],
        "flex": flex_values[:8],
    }


async def get_latest_forecast(db, deployment_id: str, forecast_type: str) -> dict:
    """Return the most recent forecast record of the given type."""
    from sqlalchemy import desc, select
    from app.forecasting.models import ForecastRecord

    result = await db.execute(
        select(ForecastRecord)
        .where(
            ForecastRecord.deployment_id == deployment_id,
            ForecastRecord.forecast_type == forecast_type,
        )
        .order_by(desc(ForecastRecord.generated_at))
        .limit(1)
    )
    rec = result.scalar_one_or_none()
    if not rec:
        return {}
    return {
        "type": rec.forecast_type,
        "generated_at": rec.generated_at.isoformat(),
        "valid_from": rec.valid_from.isoformat(),
        "valid_to": rec.valid_to.isoformat(),
        "interval_minutes": rec.interval_minutes,
        "values": json.loads(rec.values),
        "model": rec.model_version,
    }


# ── Background loop ───────────────────────────────────────────────────────────

async def forecast_loop() -> None:
    """Background task: regenerate forecasts every forecast_update_interval seconds."""
    logger.info("Forecast loop started (interval=%ds)", settings.forecast_update_interval)
    await asyncio.sleep(30)  # let simulation warm up first

    while True:
        try:
            async with AsyncSessionLocal() as db:
                for dep in ["ssen", "puvvnl"]:
                    await run_forecast_update(db, dep)
            logger.debug("Forecasts refreshed for all deployments")
        except Exception as exc:
            logger.error("Forecast loop error: %s", exc, exc_info=True)
        await asyncio.sleep(settings.forecast_update_interval)
