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


# ── LV Feeder forecast ────────────────────────────────────────────────────────

async def generate_lv_feeder_forecast(
    db,
    lv_feeder_id: str,
    deployment_id: str,
    horizon_hours: int = 48,
) -> List[dict]:
    """
    Generate load / generation forecast for an LV feeder behind a DT.

    - Fetches linked DERAssets from LVBus records
    - Aggregates solar forecast for PV assets
    - Aggregates load forecast for demand assets
    - Adds EV charging forecast (evening ramp pattern)
    - Returns 30-min interval forecast with confidence bands

    Returns list of:
      {timestamp, load_kw, solar_kw, ev_kw, net_kw, confidence_low, confidence_high}
    """
    from sqlalchemy import select

    # Load LVBuses to find linked asset IDs
    asset_ids: List[str] = []
    asset_types: dict = {}

    try:
        from app.lv_network.models import LVBus
        buses_result = await db.execute(
            select(LVBus).where(
                LVBus.lv_feeder_id == lv_feeder_id,
                LVBus.deployment_id == deployment_id,
            )
        )
        lv_buses = buses_result.scalars().all()
        asset_ids = [b.asset_id for b in lv_buses if b.asset_id]
    except Exception:
        pass

    # Load asset types for linked assets
    total_pv_kw = 0.0
    total_load_kw = 0.0
    ev_asset_count = 0

    if asset_ids:
        try:
            from app.assets.models import DERAsset
            assets_result = await db.execute(
                select(DERAsset).where(DERAsset.id.in_(asset_ids))
            )
            for asset in assets_result.scalars().all():
                asset_types[asset.id] = asset.type
                if asset.type in ("PV", "WIND"):
                    total_pv_kw += asset.capacity_kw or 0.0
                elif asset.type in ("V1G", "V2G"):
                    ev_asset_count += 1
                    total_load_kw += (asset.capacity_kw or 0.0) * 0.5  # assume 50% avg demand
                else:
                    total_load_kw += (asset.capacity_kw or 0.0) * 0.4  # typical load factor
        except Exception:
            pass

    # Default LV feeder sizing if no assets found
    if total_pv_kw == 0.0 and total_load_kw == 0.0:
        total_pv_kw = 15.0       # typical small feeder PV
        total_load_kw = 40.0     # typical 10-house feeder

    ev_kw_capacity = ev_asset_count * 7.4  # 7.4kW per EV charger (32A single-phase)
    if ev_kw_capacity == 0.0:
        ev_kw_capacity = 10.0   # assume some EV demand even if not modelled

    results: List[dict] = []
    base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    for i in range(horizon_hours * 2):
        dt = base_time + timedelta(minutes=30 * i)
        local_hour = (dt.hour + dt.minute / 60.0) % 24.0

        # ── Solar component (bell curve 06:00–18:30) ──────────────────────────
        if 6.0 <= local_hour <= 18.5:
            peak_hour = 12.5
            width = 3.2
            sf = math.exp(-((local_hour - peak_hour) ** 2) / (2.0 * width ** 2))
        else:
            sf = 0.0

        solar_kw = total_pv_kw * sf
        solar_noise = random.gauss(0.0, solar_kw * 0.06)
        solar_kw = max(0.0, solar_kw + solar_noise)

        # ── Load component (residential profile) ──────────────────────────────
        # Morning peak ~08:00, evening peak ~19:30, overnight low
        if 7.0 <= local_hour < 9.0:
            lf = 0.70 + 0.20 * math.sin(math.pi * (local_hour - 7.0) / 2.0)
        elif 17.0 <= local_hour < 21.0:
            lf = 0.75 + 0.25 * math.sin(math.pi * (local_hour - 17.0) / 4.0)
        elif 9.0 <= local_hour < 17.0:
            lf = 0.35 + 0.10 * math.sin(math.pi * (local_hour - 9.0) / 8.0)
        elif 21.0 <= local_hour < 23.0:
            lf = 0.55 - 0.15 * (local_hour - 21.0) / 2.0
        else:
            lf = 0.25  # overnight

        # Weekend adjustment
        if dt.weekday() >= 5:
            lf *= 0.90

        load_kw = total_load_kw * lf
        load_noise = random.gauss(0.0, load_kw * 0.05)
        load_kw = max(0.0, load_kw + load_noise)

        # ── EV charging component (evening ramp 17:00–23:00) ─────────────────
        if 17.0 <= local_hour < 23.0:
            # Peak EV demand at ~19:00, tapering off by 23:00
            ev_ramp = math.sin(math.pi * (local_hour - 17.0) / 6.0)
            ev_kw = ev_kw_capacity * ev_ramp * 0.80
        elif 23.0 <= local_hour or local_hour < 2.0:
            # Some overnight trickle charging
            ev_kw = ev_kw_capacity * 0.30
        else:
            ev_kw = 0.0

        ev_noise = random.gauss(0.0, ev_kw * 0.08)
        ev_kw = max(0.0, ev_kw + ev_noise)

        # ── Net power at feeder head (positive = import from grid) ─────────────
        net_kw = load_kw + ev_kw - solar_kw

        # ── Confidence interval: widens with horizon ──────────────────────────
        horizon_factor = 1.0 + (i / (horizon_hours * 2)) * 0.20
        base_uncertainty = abs(net_kw) * 0.10 * horizon_factor + 1.0  # min 1 kW band
        conf_low = net_kw - base_uncertainty
        conf_high = net_kw + base_uncertainty

        results.append({
            "timestamp": dt.isoformat(),
            "load_kw": round(load_kw, 1),
            "solar_kw": round(solar_kw, 1),
            "ev_kw": round(ev_kw, 1),
            "net_kw": round(net_kw, 1),
            "confidence_low": round(conf_low, 1),
            "confidence_high": round(conf_high, 1),
        })

    return results


# ── Asset-level forecast ───────────────────────────────────────────────────────

async def generate_asset_level_forecast(
    db,
    asset_id: str,
    deployment_id: str,
    horizon_hours: int = 48,
) -> List[dict]:
    """
    Asset-specific generation or consumption forecast.

    - PV:                solar bell-curve × asset capacity_kw
    - BESS:              flat zero (dispatch-driven, not forecastable)
    - V1G / V2G:         EV arrival/departure probability curve
    - HEAT_PUMP:         temperature-correlated load profile
    - INDUSTRIAL_LOAD:   weekday/weekend load profile
    - Others:            generic residential load profile

    Returns list of:
      {timestamp, value_kw, confidence_low, confidence_high, asset_type}
    """
    from sqlalchemy import select

    # Load asset record
    asset_type = "RESIDENTIAL_LOAD"
    capacity_kw = 5.0

    try:
        from app.assets.models import DERAsset
        asset_result = await db.execute(
            select(DERAsset).where(
                DERAsset.id == asset_id,
                DERAsset.deployment_id == deployment_id,
            )
        )
        asset = asset_result.scalar_one_or_none()
        if asset:
            asset_type = asset.type
            capacity_kw = asset.capacity_kw or 5.0
    except Exception:
        pass

    results: List[dict] = []
    base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    for i in range(horizon_hours * 2):
        dt = base_time + timedelta(minutes=30 * i)
        local_hour = (dt.hour + dt.minute / 60.0) % 24.0
        is_weekend = dt.weekday() >= 5

        horizon_factor = 1.0 + (i / (horizon_hours * 2)) * 0.20

        if asset_type in ("PV", "WIND"):
            # ── PV / Wind: solar bell-curve ───────────────────────────────────
            if asset_type == "PV":
                if 6.0 <= local_hour <= 18.5:
                    peak_hour = 12.5
                    width = 3.2
                    cf = math.exp(-((local_hour - peak_hour) ** 2) / (2.0 * width ** 2))
                else:
                    cf = 0.0
            else:
                # Wind: higher at night and morning, reduced midday
                cf = 0.30 + 0.15 * math.cos(math.pi * local_hour / 12.0) + 0.05
                cf = max(0.0, min(1.0, cf))

            value_kw = capacity_kw * cf
            noise = random.gauss(0.0, value_kw * 0.08)
            value_kw = max(0.0, value_kw + noise)
            # Generation is negative (export) in load convention
            value_kw = -value_kw
            band = abs(value_kw) * 0.12 * horizon_factor

        elif asset_type == "BESS":
            # ── BESS: zero forecast (dispatch-driven) ─────────────────────────
            value_kw = 0.0
            band = capacity_kw * 0.05  # small uncertainty band

        elif asset_type in ("V1G", "V2G"):
            # ── EV: arrival/departure probability curve ────────────────────────
            # Most EVs parked at home 19:00–07:00, away during working hours
            if local_hour >= 19.0 or local_hour < 7.0:
                # Home and plugged in — charging demand
                if 19.0 <= local_hour < 22.0:
                    cf = 0.60 + 0.30 * math.sin(math.pi * (local_hour - 19.0) / 3.0)
                elif 22.0 <= local_hour or local_hour < 3.0:
                    cf = 0.25  # trickle charge overnight
                else:
                    cf = 0.10  # pre-departure top-up
            elif 7.0 <= local_hour < 9.0:
                cf = 0.10 * (1.0 - (local_hour - 7.0) / 2.0)  # departing
            elif 9.0 <= local_hour < 17.0:
                cf = 0.05  # away — minimal workplace charging
            else:
                cf = 0.15 + 0.10 * (local_hour - 17.0) / 2.0  # returning

            if is_weekend:
                cf = min(1.0, cf * 1.20)  # more EV at home on weekends

            value_kw = capacity_kw * cf
            noise = random.gauss(0.0, value_kw * 0.12)
            value_kw = max(0.0, value_kw + noise)
            band = value_kw * 0.18 * horizon_factor

        elif asset_type == "HEAT_PUMP":
            # ── Heat pump: temperature-correlated (higher in morning/evening) ──
            # Simplified: morning heat-up and evening warmth peaks
            if 6.0 <= local_hour < 9.0:
                cf = 0.80 + 0.15 * math.sin(math.pi * (local_hour - 6.0) / 3.0)
            elif 16.0 <= local_hour < 22.0:
                cf = 0.70 + 0.20 * math.sin(math.pi * (local_hour - 16.0) / 6.0)
            elif 9.0 <= local_hour < 16.0:
                cf = 0.30  # setback during day
            else:
                cf = 0.40  # overnight low
            # Seasonal adjustment — assume winter load is higher
            # (no numpy: use deterministic seasonal offset)
            day_of_year = dt.timetuple().tm_yday
            seasonal_boost = 0.15 * math.cos(2.0 * math.pi * (day_of_year - 15) / 365.0)
            cf = max(0.0, min(1.0, cf + seasonal_boost))
            value_kw = capacity_kw * cf
            noise = random.gauss(0.0, value_kw * 0.07)
            value_kw = max(0.0, value_kw + noise)
            band = value_kw * 0.12 * horizon_factor

        elif asset_type == "INDUSTRIAL_LOAD":
            # ── Industrial: weekday/weekend profile ───────────────────────────
            if is_weekend:
                cf = 0.15  # skeleton weekend crew
            elif 6.0 <= local_hour < 22.0:
                # Two-shift operation with midday peak
                if 6.0 <= local_hour < 8.0:
                    cf = 0.40 + 0.40 * (local_hour - 6.0) / 2.0
                elif 8.0 <= local_hour < 12.0:
                    cf = 0.85 + 0.10 * math.sin(math.pi * (local_hour - 8.0) / 4.0)
                elif 12.0 <= local_hour < 13.0:
                    cf = 0.60  # lunch break dip
                elif 13.0 <= local_hour < 18.0:
                    cf = 0.90
                elif 18.0 <= local_hour < 22.0:
                    cf = 0.70 - 0.20 * (local_hour - 18.0) / 4.0
                else:
                    cf = 0.50
            else:
                cf = 0.15  # night minimum

            value_kw = capacity_kw * cf
            noise = random.gauss(0.0, value_kw * 0.04)
            value_kw = max(0.0, value_kw + noise)
            band = value_kw * 0.08 * horizon_factor

        else:
            # ── Default residential load profile ──────────────────────────────
            if 7.0 <= local_hour < 9.0:
                cf = 0.55 + 0.20 * math.sin(math.pi * (local_hour - 7.0) / 2.0)
            elif 17.0 <= local_hour < 21.0:
                cf = 0.60 + 0.25 * math.sin(math.pi * (local_hour - 17.0) / 4.0)
            elif 9.0 <= local_hour < 17.0:
                cf = 0.25
            else:
                cf = 0.20  # overnight

            if is_weekend:
                cf = max(0.20, cf * 0.95)

            value_kw = capacity_kw * cf
            noise = random.gauss(0.0, value_kw * 0.06)
            value_kw = max(0.0, value_kw + noise)
            band = value_kw * 0.10 * horizon_factor

        conf_low = value_kw - band
        conf_high = value_kw + band

        results.append({
            "timestamp": dt.isoformat(),
            "value_kw": round(value_kw, 2),
            "confidence_low": round(conf_low, 2),
            "confidence_high": round(conf_high, 2),
            "asset_type": asset_type,
        })

    return results


# ── OE Headroom forecast ───────────────────────────────────────────────────────

async def generate_oe_headroom_forecast(
    db,
    cmz_id: str,
    deployment_id: str,
    horizon_hours: int = 24,
) -> List[dict]:
    """
    OE headroom forecast for a CMZ.

    Priority:
    1. DynamicOESlot records (physics-based DistFlow) — if available for future slots
    2. Arithmetic fallback: rated_capacity - forecast_load + forecast_generation

    Returns list of 30-min interval dicts with:
    {slot_start, slot_end, export_max_kw, import_max_kw, headroom_kw,
     source: DISTFLOW|ARITHMETIC, min_voltage_pu, max_voltage_pu}
    """
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    horizon_end = now + timedelta(hours=horizon_hours)
    required_slots = horizon_hours * 2

    # ── Priority 1: Try DynamicOESlot records (physics-based) ─────────────────
    distflow_slots: List[dict] = []
    try:
        from app.lv_network.models import DynamicOESlot
        oe_result = await db.execute(
            select(DynamicOESlot)
            .where(
                DynamicOESlot.cmz_id == cmz_id,
                DynamicOESlot.deployment_id == deployment_id,
                DynamicOESlot.slot_start >= now,
                DynamicOESlot.slot_start <= horizon_end,
            )
            .order_by(DynamicOESlot.slot_start)
        )
        oe_records = oe_result.scalars().all()

        for rec in oe_records:
            distflow_slots.append({
                "slot_start": rec.slot_start.isoformat(),
                "slot_end": rec.slot_end.isoformat(),
                "export_max_kw": rec.export_max_kw,
                "import_max_kw": rec.import_max_kw,
                "headroom_kw": rec.headroom_kw or min(rec.export_max_kw, rec.import_max_kw),
                "min_voltage_pu": rec.min_voltage_pu,
                "max_voltage_pu": rec.max_voltage_pu,
                "max_branch_loading_pct": rec.max_branch_loading_pct,
                "forecast_load_kw": rec.forecast_load_kw,
                "forecast_gen_kw": rec.forecast_gen_kw,
                "source": rec.source,
                "pf_converged": rec.pf_converged,
                "cmz_id": cmz_id,
            })
    except Exception as exc:
        logger.debug("Could not query DynamicOESlot: %s", exc)

    # If we have sufficient DISTFLOW coverage, return it directly
    if len(distflow_slots) >= required_slots:
        return distflow_slots[:required_slots]

    # ── Priority 2: Arithmetic fallback ───────────────────────────────────────
    # Load CMZ rated limits
    max_import_kw = 2000.0   # default if CMZ not found
    max_export_kw = 2000.0
    cmz_slug = cmz_id

    try:
        from app.grid.models import CMZ
        cmz_result = await db.execute(
            select(CMZ).where(
                CMZ.deployment_id == deployment_id,
                CMZ.slug == cmz_id,
            ).limit(1)
        )
        cmz = cmz_result.scalar_one_or_none()
        if cmz is None:
            # Try matching by id
            cmz_result2 = await db.execute(
                select(CMZ).where(
                    CMZ.deployment_id == deployment_id,
                    CMZ.id == cmz_id,
                ).limit(1)
            )
            cmz = cmz_result2.scalar_one_or_none()
        if cmz:
            max_import_kw = cmz.max_import_kw or max_import_kw
            max_export_kw = cmz.max_export_kw or max_export_kw
            cmz_slug = cmz.slug
    except Exception:
        pass

    # Generate load and generation forecasts at deployment level
    # Scale down to CMZ level (assume CMZ is ~25% of deployment load)
    cmz_scale = 0.25
    dep_load_forecast = generate_load_forecast(deployment_id, horizon_hours)
    dep_solar_forecast = generate_solar_forecast(deployment_id, horizon_hours)

    # Load BESS capacity in CMZ for generation headroom
    bess_capacity_kw = 0.0
    try:
        from app.assets.models import DERAsset
        bess_result = await db.execute(
            select(DERAsset).where(
                DERAsset.deployment_id == deployment_id,
                DERAsset.type == "BESS",
                DERAsset.status.in_(["ONLINE", "CURTAILED"]),
            )
        )
        for bess in bess_result.scalars().all():
            bess_capacity_kw += bess.capacity_kw or 0.0
    except Exception:
        bess_capacity_kw = 50.0  # default if assets unavailable

    arithmetic_slots: List[dict] = []
    base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    for i in range(horizon_hours * 2):
        dt = base_time + timedelta(minutes=30 * i)
        local_hour = (dt.hour + dt.minute / 60.0) % 24.0
        slot_end = dt + timedelta(minutes=30)

        # Scale deployment forecasts to CMZ level
        load_entry = dep_load_forecast[i] if i < len(dep_load_forecast) else {}
        solar_entry = dep_solar_forecast[i] if i < len(dep_solar_forecast) else {}

        forecast_load_kw = (load_entry.get("value_kw", 0.0)) * cmz_scale

        # Solar generation for this CMZ
        forecast_solar_kw = (solar_entry.get("value_kw", 0.0)) * cmz_scale

        # BESS availability: assume 60% of capacity available for dispatch
        # BESS is typically charging during solar peak, discharging in evenings
        if 10.0 <= local_hour < 16.0:
            bess_gen_kw = 0.0    # charging from solar — not available for export
        elif 17.0 <= local_hour < 22.0:
            bess_gen_kw = bess_capacity_kw * 0.70  # discharging
        else:
            bess_gen_kw = bess_capacity_kw * 0.30  # partial availability

        forecast_gen_kw = forecast_solar_kw + bess_gen_kw

        # Available headroom calculations
        # Import headroom = how much more load can be absorbed before hitting limit
        import_headroom_kw = max(0.0, max_import_kw - forecast_load_kw + forecast_gen_kw)

        # Export headroom = how much generation can be added before hitting export limit
        export_headroom_kw = max(0.0, max_export_kw - forecast_gen_kw + forecast_load_kw)

        # OE limit = the tighter of the two (conservative envelope for safety)
        available_headroom_kw = min(import_headroom_kw, export_headroom_kw)
        oe_limit_kw = max_export_kw * 0.90  # 90% of rated as OE limit (10% margin)

        arithmetic_slots.append({
            "slot_start": dt.isoformat(),
            "slot_end": slot_end.isoformat(),
            "export_max_kw": round(export_headroom_kw, 1),
            "import_max_kw": round(import_headroom_kw, 1),
            "headroom_kw": round(available_headroom_kw, 1),
            "min_voltage_pu": None,
            "max_voltage_pu": None,
            "max_branch_loading_pct": None,
            "forecast_load_kw": round(forecast_load_kw, 1),
            "forecast_gen_kw": round(forecast_gen_kw, 1),
            "forecast_solar_kw": round(forecast_solar_kw, 1),
            "forecast_bess_kw": round(bess_gen_kw, 1),
            "available_headroom_kw": round(available_headroom_kw, 1),
            "import_headroom_kw": round(import_headroom_kw, 1),
            "export_headroom_kw": round(export_headroom_kw, 1),
            "oe_limit_kw": round(oe_limit_kw, 1),
            "source": "ARITHMETIC",
            "pf_converged": None,
            "cmz_id": cmz_slug,
        })

    # ── Merge: use DISTFLOW slots where available, ARITHMETIC for the rest ────
    if not distflow_slots:
        return arithmetic_slots

    # Build a lookup of distflow slots by their slot_start ISO string
    distflow_by_start: dict[str, dict] = {s["slot_start"]: s for s in distflow_slots}

    merged: List[dict] = []
    for arith_slot in arithmetic_slots:
        ts = arith_slot["slot_start"]
        if ts in distflow_by_start:
            merged.append(distflow_by_start[ts])
        else:
            merged.append(arith_slot)

    return merged


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
