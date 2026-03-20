"""Business logic for DER Assets."""
from __future__ import annotations

import json
import random
from datetime import timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.core.utils import new_uuid, utcnow
from app.assets.models import (
    AssetStatus,
    AssetType,
    AssetTelemetry,
    CommCapability,
    DERAsset,
    DOEHistory,
    TelemetrySource,
)
from app.assets.schemas import DERAssetCreate, DERAssetUpdate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_json(obj) -> Optional[str]:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump())
    if isinstance(obj, (dict, list)):
        return json.dumps(obj)
    return str(obj)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def list_assets(
    db: AsyncSession,
    deployment_id: str,
    counterparty_id: Optional[str] = None,
    type_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> list[DERAsset]:
    stmt = select(DERAsset).where(
        DERAsset.deployment_id == deployment_id,
        DERAsset.deleted_at.is_(None),
    )
    if counterparty_id:
        stmt = stmt.where(DERAsset.counterparty_id == counterparty_id)
    if type_filter:
        stmt = stmt.where(DERAsset.type == type_filter)
    if status_filter:
        stmt = stmt.where(DERAsset.status == status_filter)
    stmt = stmt.order_by(DERAsset.asset_ref)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_asset(db: AsyncSession, asset_id: str, deployment_id: str) -> DERAsset:
    stmt = select(DERAsset).where(
        DERAsset.id == asset_id,
        DERAsset.deployment_id == deployment_id,
        DERAsset.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found.",
        )
    return asset


async def create_asset(
    db: AsyncSession,
    data: DERAssetCreate,
    deployment_id: str,
    user_id: str,
) -> DERAsset:
    type_val = data.type.value if hasattr(data.type, "value") else str(data.type)
    comm_val = data.comm_capability.value if hasattr(data.comm_capability, "value") else str(data.comm_capability)
    tel_val = data.telemetry_source.value if hasattr(data.telemetry_source, "value") else str(data.telemetry_source)

    asset = DERAsset(
        id=new_uuid(),
        deployment_id=deployment_id,
        counterparty_id=data.counterparty_id,
        asset_ref=data.asset_ref,
        name=data.name,
        type=type_val,
        status=AssetStatus.OFFLINE.value,
        is_digital_twin=data.is_digital_twin,
        connection_point_id=data.connection_point_id,
        feeder_id=data.feeder_id,
        dt_id=data.dt_id,
        phase=data.phase,
        capacity_kw=data.capacity_kw,
        capacity_kwh=data.capacity_kwh,
        comm_capability=comm_val,
        comm_endpoint=data.comm_endpoint,
        telemetry_source=tel_val,
        telemetry_topic=data.telemetry_topic,
        meter_id=data.meter_id,
        lat=data.lat,
        lng=data.lng,
        doe_import_max_kw=data.doe_import_max_kw,
        doe_export_max_kw=data.doe_export_max_kw,
        hosting_capacity_kw=data.hosting_capacity_kw,
        current_kw=0.0,
        created_by=user_id,
        created_at=utcnow(),
        updated_at=utcnow(),
        meta=_serialize_json(data.meta),
    )
    db.add(asset)
    await db.flush()
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="CREATE",
        resource_type="asset",
        resource_id=asset.id,
        user_id=user_id,
        diff={"asset_ref": asset.asset_ref, "type": asset.type},
    )
    return asset


async def update_asset(
    db: AsyncSession,
    asset_id: str,
    data: DERAssetUpdate,
    deployment_id: str,
    user_id: str,
) -> DERAsset:
    asset = await get_asset(db, asset_id, deployment_id)
    update_data = data.model_dump(exclude_unset=True)

    for enum_field in ("status", "comm_capability", "telemetry_source"):
        if enum_field in update_data:
            v = update_data[enum_field]
            update_data[enum_field] = v.value if hasattr(v, "value") else str(v)
    if "meta" in update_data:
        update_data["meta"] = _serialize_json(update_data["meta"])

    for key, value in update_data.items():
        setattr(asset, key, value)

    asset.updated_at = utcnow()
    await db.flush()
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="UPDATE",
        resource_type="asset",
        resource_id=asset.id,
        user_id=user_id,
        diff={"updated_fields": list(update_data.keys())},
    )
    return asset


async def delete_asset(
    db: AsyncSession,
    asset_id: str,
    deployment_id: str,
    user_id: str,
) -> bool:
    asset = await get_asset(db, asset_id, deployment_id)
    asset.status = AssetStatus.DEREGISTERED.value
    asset.deleted_at = utcnow()
    asset.updated_at = utcnow()
    await db.flush()
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="DELETE",
        resource_type="asset",
        resource_id=asset.id,
        user_id=user_id,
        diff={"asset_ref": asset.asset_ref},
    )
    return True


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

async def ingest_telemetry(
    db: AsyncSession,
    asset_id: str,
    deployment_id: str,
    power_kw: float,
    voltage_v: Optional[float] = None,
    current_a: Optional[float] = None,
    soc_pct: Optional[float] = None,
    frequency_hz: Optional[float] = None,
    temperature_c: Optional[float] = None,
    source: str = "IOT_GATEWAY",
) -> AssetTelemetry:
    """Ingest a telemetry reading: update asset live state and append time-series row."""
    # Update asset live fields
    stmt = select(DERAsset).where(
        DERAsset.id == asset_id,
        DERAsset.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    asset = result.scalar_one_or_none()
    if asset:
        asset.current_kw = power_kw
        if soc_pct is not None:
            asset.current_soc_pct = soc_pct
        now = utcnow()
        asset.last_telemetry_at = now
        # Auto-set ONLINE on first telemetry
        if asset.status == AssetStatus.OFFLINE.value:
            asset.status = AssetStatus.ONLINE.value
        asset.updated_at = now

    ts = AssetTelemetry(
        id=new_uuid(),
        asset_id=asset_id,
        deployment_id=deployment_id,
        timestamp=utcnow(),
        power_kw=power_kw,
        voltage_v=voltage_v,
        current_a=current_a,
        soc_pct=soc_pct,
        frequency_hz=frequency_hz,
        temperature_c=temperature_c,
        source=source,
    )
    db.add(ts)
    await db.flush()
    return ts


async def get_asset_telemetry_history(
    db: AsyncSession,
    asset_id: str,
    deployment_id: str,
    hours: int = 24,
) -> list[AssetTelemetry]:
    cutoff = utcnow() - timedelta(hours=hours)
    stmt = (
        select(AssetTelemetry)
        .where(
            AssetTelemetry.asset_id == asset_id,
            AssetTelemetry.timestamp >= cutoff,
        )
        .order_by(AssetTelemetry.timestamp.asc())
        .limit(2000)  # Safety cap
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Dynamic Operating Envelopes (DOE)
# ---------------------------------------------------------------------------

async def update_doe(
    db: AsyncSession,
    asset_id: str,
    deployment_id: str,
    import_max_kw: Optional[float],
    export_max_kw: Optional[float],
    event_id: Optional[str] = None,
    reason: Optional[str] = None,
    issued_by: Optional[str] = None,
    interval_start: Optional[object] = None,
    interval_end: Optional[object] = None,
) -> DERAsset:
    """Update an asset's DOE limits and record history."""
    asset = await get_asset(db, asset_id, deployment_id)
    now = utcnow()

    asset.doe_import_max_kw = import_max_kw
    asset.doe_export_max_kw = export_max_kw
    asset.doe_last_updated = now
    asset.updated_at = now

    # Default interval: now → now + 30 min
    i_start = interval_start or now
    i_end = interval_end or (now + timedelta(minutes=30))

    doe_hist = DOEHistory(
        id=new_uuid(),
        asset_id=asset_id,
        event_id=event_id,
        interval_start=i_start,
        interval_end=i_end,
        doe_import_max_kw=import_max_kw,
        doe_export_max_kw=export_max_kw,
        reason=reason,
        issued_by=issued_by,
        created_at=now,
    )
    db.add(doe_hist)
    await db.flush()
    return asset


async def get_doe_history(
    db: AsyncSession,
    asset_id: str,
    deployment_id: str,
    limit: int = 50,
) -> list[DOEHistory]:
    await get_asset(db, asset_id, deployment_id)
    stmt = (
        select(DOEHistory)
        .where(DOEHistory.asset_id == asset_id)
        .order_by(DOEHistory.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Demo asset seed
# ---------------------------------------------------------------------------

async def seed_demo_assets(db: AsyncSession, deployment_id: str) -> None:
    """
    Seed digital twin DER assets for a given deployment. Idempotent.

    SSEN: 15 assets across 3 CMZs.
    PUVVNL: 10 assets.
    """
    stmt = select(func.count(DERAsset.id)).where(
        DERAsset.deployment_id == deployment_id,
        DERAsset.created_by == "system",
        DERAsset.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    if (result.scalar_one() or 0) > 0:
        return  # Already seeded

    # We need to look up counterparty IDs seeded by seed_counterparties
    from app.counterparties.models import Counterparty  # noqa: PLC0415

    cp_stmt = select(Counterparty).where(
        Counterparty.deployment_id == deployment_id,
        Counterparty.deleted_at.is_(None),
    )
    cp_result = await db.execute(cp_stmt)
    counterparties = {cp.name: cp.id for cp in cp_result.scalars().all()}

    now = utcnow()

    if deployment_id == "ssen":
        # ---- SSEN: 15 assets across CMZ-ORKNEY, CMZ-SHETLAND, CMZ-HIGHLAND ----
        agg_id = counterparties.get("Alpha Flex Ltd", list(counterparties.values())[0] if counterparties else "unknown")
        wpr_id = counterparties.get("Western Power Renewables", agg_id)
        hhc_id = counterparties.get("Highland Homes Community", agg_id)

        assets = [
            # 5x V1G chargers (7kW each) — CMZ-ORKNEY
            _make_asset("AST-001", "Kirkwall EV Hub — Charger 1",       AssetType.V1G,       7.0,   None, agg_id, "ssen", "CMZ-ORKNEY",   "FDR-01", "DT-001", 58.981, -2.960),
            _make_asset("AST-002", "Kirkwall EV Hub — Charger 2",       AssetType.V1G,       7.0,   None, agg_id, "ssen", "CMZ-ORKNEY",   "FDR-01", "DT-001", 58.982, -2.961),
            _make_asset("AST-003", "St Ola Depot — EV Fleet Charger",   AssetType.V1G,       7.0,   None, agg_id, "ssen", "CMZ-ORKNEY",   "FDR-02", "DT-002", 58.957, -2.922),
            _make_asset("AST-004", "Stromness Quay — V1G Unit",         AssetType.V1G,       7.0,   None, agg_id, "ssen", "CMZ-ORKNEY",   "FDR-02", "DT-002", 58.963, -3.299),
            _make_asset("AST-005", "Finstown Car Park — EV Charger",    AssetType.V1G,       7.0,   None, agg_id, "ssen", "CMZ-ORKNEY",   "FDR-03", "DT-003", 59.021, -3.063),
            # 3x V2G (22kW) — CMZ-SHETLAND
            _make_asset("AST-006", "Lerwick Ferry Terminal — V2G",      AssetType.V2G,       22.0,  None, wpr_id, "ssen", "CMZ-SHETLAND", "FDR-04", "DT-004", 60.155, -1.148),
            _make_asset("AST-007", "Scalloway Harbour — V2G",           AssetType.V2G,       22.0,  None, wpr_id, "ssen", "CMZ-SHETLAND", "FDR-04", "DT-004", 60.134, -1.275),
            _make_asset("AST-008", "Brae Industrial — V2G Depot",       AssetType.V2G,       22.0,  None, wpr_id, "ssen", "CMZ-SHETLAND", "FDR-05", "DT-005", 60.389, -1.353),
            # 4x BESS (10kW / 20kWh) — split CMZ-ORKNEY + CMZ-SHETLAND
            _make_asset("AST-009", "Orkney Grid BESS Alpha",            AssetType.BESS,      10.0,  20.0, agg_id, "ssen", "CMZ-ORKNEY",   "FDR-01", "DT-006", 58.990, -2.975, soc=75.0),
            _make_asset("AST-010", "Orkney Grid BESS Beta",             AssetType.BESS,      10.0,  20.0, agg_id, "ssen", "CMZ-ORKNEY",   "FDR-03", "DT-007", 59.015, -3.100, soc=60.0),
            _make_asset("AST-011", "Shetland BESS East Lerwick",        AssetType.BESS,      10.0,  20.0, wpr_id, "ssen", "CMZ-SHETLAND", "FDR-04", "DT-008", 60.161, -1.140, soc=80.0),
            _make_asset("AST-012", "Shetland BESS Scalloway",           AssetType.BESS,      10.0,  20.0, wpr_id, "ssen", "CMZ-SHETLAND", "FDR-05", "DT-009", 60.138, -1.280, soc=55.0),
            # 2x Heat Pump (5kW) — CMZ-HIGHLAND
            _make_asset("AST-013", "Inverness Housing — Heat Pump A",   AssetType.HEAT_PUMP, 5.0,   None, hhc_id, "ssen", "CMZ-HIGHLAND", "FDR-06", "DT-010", 57.478, -4.225),
            _make_asset("AST-014", "Inverness Housing — Heat Pump B",   AssetType.HEAT_PUMP, 5.0,   None, hhc_id, "ssen", "CMZ-HIGHLAND", "FDR-06", "DT-010", 57.479, -4.227),
            # 1x Commercial PV (50kW)
            _make_asset("AST-015", "Inverness Retail Park — PV Array",  AssetType.PV,        50.0,  None, hhc_id, "ssen", "CMZ-HIGHLAND", "FDR-07", "DT-011", 57.475, -4.210),
        ]

    elif deployment_id == "puvvnl":
        # ---- PUVVNL: 10 assets ----
        gmr_id = counterparties.get("GMR Energy Services", list(counterparties.values())[0] if counterparties else "unknown")
        vsi_id = counterparties.get("Varanasi Smart Industries", gmr_id)
        psg_id = counterparties.get("PM Surya Ghar Group", gmr_id)

        assets = [
            # 7x PV rooftop (3-10kW)
            _make_asset("AST-101", "Shivpur Rooftop PV — 1",            AssetType.PV, 3.0,  None, psg_id, "puvvnl", "CMZ-VARANASI-NORTH", "FDR-11", "DT-101", 25.332, 82.973),
            _make_asset("AST-102", "Shivpur Rooftop PV — 2",            AssetType.PV, 3.0,  None, psg_id, "puvvnl", "CMZ-VARANASI-NORTH", "FDR-11", "DT-101", 25.334, 82.975),
            _make_asset("AST-103", "Sigra Colony PV Array",              AssetType.PV, 5.0,  None, psg_id, "puvvnl", "CMZ-VARANASI-NORTH", "FDR-12", "DT-102", 25.325, 82.978),
            _make_asset("AST-104", "Lanka Rooftop PV",                   AssetType.PV, 3.5,  None, psg_id, "puvvnl", "CMZ-VARANASI-SOUTH", "FDR-13", "DT-103", 25.270, 82.985),
            _make_asset("AST-105", "BHU Campus PV — Block A",            AssetType.PV, 10.0, None, gmr_id, "puvvnl", "CMZ-VARANASI-SOUTH", "FDR-14", "DT-104", 25.268, 82.988),
            _make_asset("AST-106", "BHU Campus PV — Block B",            AssetType.PV, 10.0, None, gmr_id, "puvvnl", "CMZ-VARANASI-SOUTH", "FDR-14", "DT-104", 25.267, 82.987),
            _make_asset("AST-107", "Sarnath Industrial PV",              AssetType.PV, 7.5,  None, vsi_id, "puvvnl", "CMZ-VARANASI-NORTH", "FDR-15", "DT-105", 25.381, 83.024),
            # 2x BESS (5kW / 10kWh)
            _make_asset("AST-108", "Shivpur Community BESS",             AssetType.BESS, 5.0, 10.0, gmr_id, "puvvnl", "CMZ-VARANASI-NORTH", "FDR-11", "DT-106", 25.335, 82.974, soc=70.0),
            _make_asset("AST-109", "Lanka BESS Unit",                    AssetType.BESS, 5.0, 10.0, gmr_id, "puvvnl", "CMZ-VARANASI-SOUTH", "FDR-13", "DT-107", 25.271, 82.984, soc=50.0),
            # 1x EV charger
            _make_asset("AST-110", "Varanasi Junction EV Charger",       AssetType.V1G,  7.4, None, vsi_id, "puvvnl", "CMZ-VARANASI-NORTH", "FDR-12", "DT-108", 25.318, 82.993),
        ]

    else:
        return  # Unknown deployment

    for asset_row in assets:
        asset_row.created_by = "system"
        asset_row.created_at = now
        asset_row.updated_at = now
        db.add(asset_row)

    await db.flush()


def _make_asset(
    ref: str,
    name: str,
    asset_type: AssetType,
    capacity_kw: float,
    capacity_kwh: Optional[float],
    counterparty_id: str,
    deployment_id: str,
    cmz: str,
    feeder_id: str,
    dt_id: str,
    lat: float,
    lng: float,
    soc: Optional[float] = None,
) -> DERAsset:
    """Factory helper for creating seeded DERAsset instances."""
    type_val = asset_type.value if hasattr(asset_type, "value") else str(asset_type)
    meter_id = f"MTR-{ref}"
    phase = "THREE_PHASE" if capacity_kw >= 22 else "PHASE_A"

    return DERAsset(
        id=new_uuid(),
        deployment_id=deployment_id,
        counterparty_id=counterparty_id,
        asset_ref=ref,
        name=name,
        type=type_val,
        status=AssetStatus.ONLINE.value,
        is_digital_twin=True,
        connection_point_id=f"CIM-{ref}",
        feeder_id=feeder_id,
        dt_id=dt_id,
        phase=phase,
        capacity_kw=capacity_kw,
        capacity_kwh=capacity_kwh,
        comm_capability=CommCapability.MQTT_GATEWAY.value,
        telemetry_source=TelemetrySource.IOT_GATEWAY.value,
        telemetry_topic=f"neuralgrid/{deployment_id}/{ref}/telemetry",
        meter_id=meter_id,
        lat=lat,
        lng=lng,
        doe_import_max_kw=capacity_kw,
        doe_export_max_kw=capacity_kw if asset_type in (AssetType.BESS, AssetType.V2G, AssetType.PV) else None,
        current_kw=round(random.uniform(0.1, capacity_kw * 0.6), 2),
        current_soc_pct=soc,
        last_telemetry_at=utcnow(),
        hosting_capacity_kw=capacity_kw,
        # created_by, created_at, updated_at set by caller
    )
