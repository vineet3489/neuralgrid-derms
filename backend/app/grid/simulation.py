"""
Grid simulation engine — generates realistic real-time grid state.
Adapted and enhanced from the Varanasi prototype.
Supports multiple deployments with different topologies.

In production, this module would be replaced by ADMS/SCADA integrations
(GE ADMS, ABB Ellipse, etc.).  For demo purposes it synthesises a physically
plausible distribution-network state based on time-of-day patterns.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ── In-memory grid state cache (fast read, no DB hit per API call) ────────────
_grid_state: Dict[str, dict] = {}   # keyed by deployment_id


# ── Deployment topology definitions ──────────────────────────────────────────
DEPLOYMENT_TOPOLOGIES: Dict[str, dict] = {
    "ssen": {
        "timezone_offset": 0.0,
        "voltage_nominal": 230.0,
        "cmzs": [
            {
                "slug": "CMZ-ORKNEY",
                "name": "Orkney Islands",
                "topology": "ISLAND",
                "max_import_kw": 5000,
                "max_export_kw": 8000,
                "feeders": [
                    {
                        "id": "FDR-ORKNEY-1",
                        "name": "Kirkwall Main Feeder",
                        "voltage_kv": 11.0,
                        "rated_mva": 5.0,
                        "dts": [
                            {"id": "DT-ORK-001", "name": "Kirkwall Community",
                             "rated_kva": 500, "lat": 58.9833, "lng": -2.9600},
                            {"id": "DT-ORK-002", "name": "Stenness Rural",
                             "rated_kva": 200, "lat": 59.0042, "lng": -3.2197},
                        ],
                    },
                ],
            },
            {
                "slug": "CMZ-SHETLAND",
                "name": "Shetland Local Energy System (SLES)",
                "topology": "ISLAND",
                "max_import_kw": 8000,
                "max_export_kw": 12000,
                "feeders": [
                    {
                        "id": "FDR-SHET-1",
                        "name": "Lerwick North Feeder",
                        "voltage_kv": 11.0,
                        "rated_mva": 8.0,
                        "dts": [
                            {"id": "DT-SHET-001", "name": "SLES Community Hub DT",
                             "rated_kva": 630, "lat": 60.1533, "lng": -1.1450},
                            {"id": "DT-SHET-002", "name": "Brae Industrial Zone",
                             "rated_kva": 315, "lat": 60.3911, "lng": -1.3617},
                            {"id": "DT-SHET-003", "name": "Scalloway Residential",
                             "rated_kva": 200, "lat": 60.1336, "lng": -1.2736},
                        ],
                    },
                    {
                        "id": "FDR-SHET-2",
                        "name": "Lerwick South Feeder",
                        "voltage_kv": 11.0,
                        "rated_mva": 6.0,
                        "dts": [
                            {"id": "DT-SHET-004", "name": "Sandwick Wind Zone",
                             "rated_kva": 400, "lat": 59.9911, "lng": -1.3217},
                        ],
                    },
                ],
            },
        ],
    },
    "puvvnl": {
        "timezone_offset": 5.5,
        "voltage_nominal": 230.0,
        "cmzs": [
            {
                "slug": "CMZ-VARANASI-NORTH",
                "name": "Varanasi North Circle",
                "topology": "RADIAL",
                "max_import_kw": 2000,
                "max_export_kw": 500,
                "feeders": [
                    {
                        "id": "FDR-VAR-01",
                        "name": "Sarnath Feeder",
                        "voltage_kv": 33.0,
                        "rated_mva": 10.0,
                        "dts": [
                            {"id": "DT-VAR-001", "name": "Sarnath Main DT",
                             "rated_kva": 250, "lat": 25.3817, "lng": 83.0219},
                            {"id": "DT-VAR-002", "name": "BHU Campus DT",
                             "rated_kva": 500, "lat": 25.2677, "lng": 82.9913},
                        ],
                    },
                ],
            },
            {
                "slug": "CMZ-VARANASI-SOUTH",
                "name": "Varanasi South Circle",
                "topology": "RADIAL",
                "max_import_kw": 1500,
                "max_export_kw": 300,
                "feeders": [
                    {
                        "id": "FDR-VAR-02",
                        "name": "Assi Ghat Feeder",
                        "voltage_kv": 33.0,
                        "rated_mva": 8.0,
                        "dts": [
                            {"id": "DT-VAR-003", "name": "Assi Ghat DT",
                             "rated_kva": 200, "lat": 25.2822, "lng": 83.0152},
                            {"id": "DT-VAR-004", "name": "Lanka DT",
                             "rated_kva": 315, "lat": 25.2510, "lng": 82.9978},
                        ],
                    },
                ],
            },
        ],
    },
}


# ── Time helpers ──────────────────────────────────────────────────────────────

def get_local_hour(timezone_offset: float) -> float:
    """Return current local decimal hour (e.g. 14.5 = 2:30 PM)."""
    now = datetime.now(timezone.utc)
    utc_decimal = now.hour + now.minute / 60.0
    return (utc_decimal + timezone_offset) % 24.0


def solar_factor(local_hour: float, deployment_id: str) -> float:
    """
    Solar irradiance proxy in [0, 1].
    Bell-curve peaking at 12:30 local, active only 06:00-18:30.
    Includes +/-5% Gaussian cloud noise.
    """
    if local_hour < 6.0 or local_hour > 18.5:
        return 0.0
    peak_hour = 12.5
    width = 3.5
    factor = math.exp(-((local_hour - peak_hour) ** 2) / (2.0 * width ** 2))
    noise = random.gauss(0.0, 0.05)
    return max(0.0, min(1.0, factor + noise))


def load_factor(local_hour: float, deployment_id: str) -> float:
    """
    Demand profile factor in [0, 1].
    SSEN  - UK winter: morning (07-09) + evening (17-21) peaks.
    PUVVNL - India: midday AC peak (13-16) + evening peak (19-22).
    """
    if deployment_id == "ssen":
        if 7.0 <= local_hour < 9.0:
            return 0.65 + 0.15 * math.sin(math.pi * (local_hour - 7.0) / 2.0)
        if 17.0 <= local_hour < 21.0:
            return 0.75 + 0.20 * math.sin(math.pi * (local_hour - 17.0) / 4.0)
        if 0.0 <= local_hour < 6.0:
            return max(0.1, 0.30 + random.gauss(0.0, 0.02))
        return max(0.1, 0.45 + random.gauss(0.0, 0.03))
    else:  # puvvnl
        if 13.0 <= local_hour < 16.0:
            return 0.80 + 0.15 * math.sin(math.pi * (local_hour - 13.0) / 3.0)
        if 19.0 <= local_hour < 22.0:
            return 0.70 + 0.20 * math.sin(math.pi * (local_hour - 19.0) / 3.0)
        if 0.0 <= local_hour < 5.0:
            return max(0.1, 0.25 + random.gauss(0.0, 0.02))
        return max(0.1, 0.50 + random.gauss(0.0, 0.04))


# ── DB seeding ────────────────────────────────────────────────────────────────

async def seed_grid_topology(db) -> None:
    """
    Idempotently seed CMZs and GridNodes from DEPLOYMENT_TOPOLOGIES.
    Safe to call on every startup - skips existing records.
    """
    import uuid as _uuid
    from sqlalchemy import select
    from app.grid.models import CMZ, GridNode

    for deployment_id, topo in DEPLOYMENT_TOPOLOGIES.items():
        for cmz_def in topo["cmzs"]:
            existing = await db.execute(
                select(CMZ).where(
                    CMZ.slug == cmz_def["slug"],
                    CMZ.deployment_id == deployment_id,
                )
            )
            if not existing.scalar_one_or_none():
                feeder_ids = [f["id"] for f in cmz_def["feeders"]]
                cmz = CMZ(
                    id=str(_uuid.uuid4()),
                    deployment_id=deployment_id,
                    slug=cmz_def["slug"],
                    name=cmz_def["name"],
                    topology_type=cmz_def["topology"],
                    max_import_kw=cmz_def["max_import_kw"],
                    max_export_kw=cmz_def["max_export_kw"],
                    feeder_ids=json.dumps(feeder_ids),
                    created_at=datetime.now(timezone.utc),
                )
                db.add(cmz)

            for feeder_def in cmz_def["feeders"]:
                existing = await db.execute(
                    select(GridNode).where(GridNode.node_id == feeder_def["id"])
                )
                if not existing.scalar_one_or_none():
                    node = GridNode(
                        id=str(_uuid.uuid4()),
                        deployment_id=deployment_id,
                        node_id=feeder_def["id"],
                        cmz_id=cmz_def["slug"],
                        node_type="FEEDER",
                        name=feeder_def["name"],
                        voltage_kv=feeder_def["voltage_kv"],
                        rated_mva=feeder_def["rated_mva"],
                        hosting_capacity_kw=feeder_def["rated_mva"] * 1000.0 * 0.20,
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(node)

                for dt_def in feeder_def.get("dts", []):
                    existing = await db.execute(
                        select(GridNode).where(GridNode.node_id == dt_def["id"])
                    )
                    if not existing.scalar_one_or_none():
                        node = GridNode(
                            id=str(_uuid.uuid4()),
                            deployment_id=deployment_id,
                            node_id=dt_def["id"],
                            cmz_id=cmz_def["slug"],
                            node_type="DISTRIBUTION_TRANSFORMER",
                            name=dt_def["name"],
                            rated_kva=dt_def["rated_kva"],
                            hosting_capacity_kw=dt_def["rated_kva"] * 0.80,
                            lat=dt_def["lat"],
                            lng=dt_def["lng"],
                            created_at=datetime.now(timezone.utc),
                        )
                        db.add(node)

    await db.commit()


# ── State accessors ───────────────────────────────────────────────────────────

def get_grid_state(deployment_id: Optional[str] = None) -> dict:
    """
    Return current in-memory grid state.
    If deployment_id is given, return only that deployment's slice.
    """
    if deployment_id:
        return _grid_state.get(deployment_id, {})
    return _grid_state


# ── Alert deduplication helper ────────────────────────────────────────────────

async def _maybe_create_alert(
    db,
    deployment_id: str,
    node_id: Optional[str],
    asset_id: Optional[str],
    alert_type: str,
    severity: str,
    message: str,
) -> None:
    """Create a GridAlert only when no unresolved duplicate already exists."""
    from sqlalchemy import select
    from app.grid.models import GridAlert
    import uuid as _uuid

    existing = await db.execute(
        select(GridAlert).where(
            GridAlert.deployment_id == deployment_id,
            GridAlert.node_id == node_id,
            GridAlert.alert_type == alert_type,
            GridAlert.resolved_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        return

    alert = GridAlert(
        id=str(_uuid.uuid4()),
        deployment_id=deployment_id,
        node_id=node_id,
        asset_id=asset_id,
        alert_type=alert_type,
        severity=severity,
        message=message,
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert)


# ── Core simulation tick ──────────────────────────────────────────────────────

async def update_grid_state() -> None:
    """
    Single simulation tick: read DB assets, compute physics, update _grid_state,
    write telemetry back to DB, generate alerts for constraint violations.
    """
    from sqlalchemy import select
    from app.grid.models import GridNode

    try:
        from app.assets.models import DERAsset  # type: ignore[attr-defined]
        _has_assets = True
    except ImportError:
        _has_assets = False

    async with AsyncSessionLocal() as db:
        for deployment_id, topo in DEPLOYMENT_TOPOLOGIES.items():
            local_hour = get_local_hour(topo["timezone_offset"])
            sf = solar_factor(local_hour, deployment_id)
            lf = load_factor(local_hour, deployment_id)

            assets: List[Any] = []
            if _has_assets:
                assets_result = await db.execute(
                    select(DERAsset).where(
                        DERAsset.deployment_id == deployment_id,
                        DERAsset.deleted_at.is_(None),
                    )
                )
                assets = assets_result.scalars().all()

            feeder_gen: Dict[str, float] = {}
            feeder_load: Dict[str, float] = {}

            for asset in assets:
                if not asset.feeder_id:
                    continue
                fid: str = asset.feeder_id

                if asset.type == "PV":
                    current_kw = -(asset.capacity_kw * sf)
                elif asset.type == "BESS":
                    soc = asset.current_soc_pct or 50.0
                    if sf > 0.5 and soc < 90.0:
                        current_kw = asset.capacity_kw * 0.8
                    elif lf > 0.7 and soc > 20.0:
                        current_kw = -(asset.capacity_kw * 0.9)
                        asset.current_soc_pct = max(10.0, soc - 2.0)
                    else:
                        current_kw = 0.0
                elif asset.type in ("V1G", "V2G"):
                    if 18.0 <= local_hour < 23.0:
                        current_kw = asset.capacity_kw * lf * random.uniform(0.6, 1.0)
                    elif asset.type == "V2G" and lf > 0.75:
                        current_kw = -(asset.capacity_kw * 0.5)
                    else:
                        current_kw = asset.capacity_kw * 0.15 * random.uniform(0.0, 1.0)
                elif asset.type == "HEAT_PUMP":
                    if 6.0 <= local_hour < 9.0 or 17.0 <= local_hour < 21.0:
                        current_kw = asset.capacity_kw * lf * random.uniform(0.7, 1.0)
                    else:
                        current_kw = asset.capacity_kw * 0.2
                elif asset.type == "WIND":
                    wind_factor = random.gauss(0.45, 0.20)
                    current_kw = -(asset.capacity_kw * max(0.0, min(1.0, wind_factor)))
                elif asset.type in ("INDUSTRIAL_LOAD", "RESIDENTIAL_LOAD"):
                    current_kw = asset.capacity_kw * lf * random.uniform(0.8, 1.0)
                else:
                    current_kw = 0.0

                if asset.status == "CURTAILED":
                    current_kw = current_kw * 0.1

                if asset.doe_export_max_kw is not None and current_kw < 0.0:
                    current_kw = max(current_kw, -asset.doe_export_max_kw)
                if asset.doe_import_max_kw is not None and current_kw > 0.0:
                    current_kw = min(current_kw, asset.doe_import_max_kw)

                asset.current_kw = round(current_kw, 2)
                if asset.status not in ("CURTAILED", "FAULT", "MAINTENANCE", "DEREGISTERED"):
                    asset.status = "ONLINE"
                asset.last_telemetry_at = datetime.now(timezone.utc)

                if current_kw < 0.0:
                    feeder_gen[fid] = feeder_gen.get(fid, 0.0) + abs(current_kw)
                else:
                    feeder_load[fid] = feeder_load.get(fid, 0.0) + current_kw

            nodes_result = await db.execute(
                select(GridNode).where(GridNode.deployment_id == deployment_id)
            )
            nodes = nodes_result.scalars().all()
            deployment_nodes_list: List[dict] = []

            for node in nodes:
                if node.node_type == "FEEDER":
                    rated_kw = (node.rated_mva or 1.0) * 1000.0
                    net_load_kw = (
                        feeder_load.get(node.node_id, 0.0)
                        - feeder_gen.get(node.node_id, 0.0)
                    )
                    node.current_loading_pct = round(
                        min(100.0, max(0.0, (net_load_kw / rated_kw) * 100.0)), 1
                    )
                    node.used_capacity_kw = round(feeder_gen.get(node.node_id, 0.0), 1)

                    if node.current_loading_pct > settings.feeder_loading_warn:
                        await _maybe_create_alert(
                            db, deployment_id, node.node_id, None,
                            "OVERLOAD",
                            "CRITICAL" if node.current_loading_pct >= 100.0 else "WARNING",
                            f"Feeder {node.name} loading {node.current_loading_pct:.0f}% "
                            f"(warn at {settings.feeder_loading_warn:.0f}%)",
                        )

                elif node.node_type == "DISTRIBUTION_TRANSFORMER":
                    rated_kw = (node.rated_kva or 250.0) * 0.9
                    dt_gen = sum(
                        abs(a.current_kw)
                        for a in assets
                        if getattr(a, "dt_id", None) == node.node_id and a.current_kw < 0.0
                    )
                    dt_load = sum(
                        a.current_kw
                        for a in assets
                        if getattr(a, "dt_id", None) == node.node_id and a.current_kw > 0.0
                    )
                    node.current_loading_pct = round(
                        min(100.0, max(0.0, ((dt_load - dt_gen) / max(rated_kw, 1.0)) * 100.0)), 1
                    )
                    load_droop = (node.current_loading_pct / 100.0) * 0.03
                    solar_rise = (dt_gen / max(rated_kw, 1.0)) * 0.05
                    v_noise = random.gauss(0.0, 0.5)
                    v = 230.0 * (1.0 + solar_rise - load_droop) + v_noise
                    node.voltage_l1_v = round(v, 1)
                    node.voltage_l2_v = round(v + random.gauss(0.0, 0.3), 1)
                    node.voltage_l3_v = round(v + random.gauss(0.0, 0.3), 1)

                    v1 = node.voltage_l1_v or 230.0
                    if v1 > settings.voltage_high_warn:
                        await _maybe_create_alert(
                            db, deployment_id, node.node_id, None,
                            "OVERVOLTAGE",
                            "CRITICAL" if v1 > settings.voltage_high_trip else "WARNING",
                            f"Overvoltage at {node.name}: {v1:.1f} V "
                            f"(limit {settings.voltage_high_warn:.0f} V)",
                        )
                    elif v1 < settings.voltage_low_warn:
                        await _maybe_create_alert(
                            db, deployment_id, node.node_id, None,
                            "UNDERVOLTAGE",
                            "CRITICAL" if v1 < settings.voltage_low_trip else "WARNING",
                            f"Undervoltage at {node.name}: {v1:.1f} V "
                            f"(limit {settings.voltage_low_warn:.0f} V)",
                        )

                deployment_nodes_list.append({
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "name": node.name,
                    "cmz_id": node.cmz_id,
                    "current_loading_pct": node.current_loading_pct,
                    "voltage_l1_v": node.voltage_l1_v,
                    "voltage_l2_v": node.voltage_l2_v,
                    "voltage_l3_v": node.voltage_l3_v,
                    "hosting_capacity_kw": node.hosting_capacity_kw,
                    "used_capacity_kw": node.used_capacity_kw,
                    "lat": node.lat,
                    "lng": node.lng,
                })

            assets_list = [
                {
                    "id": a.id,
                    "asset_ref": a.asset_ref,
                    "name": a.name,
                    "type": a.type,
                    "status": a.status,
                    "feeder_id": a.feeder_id,
                    "dt_id": getattr(a, "dt_id", None),
                    "current_kw": a.current_kw,
                    "capacity_kw": a.capacity_kw,
                    "current_soc_pct": getattr(a, "current_soc_pct", None),
                    "lat": getattr(a, "lat", None),
                    "lng": getattr(a, "lng", None),
                    "doe_export_max_kw": getattr(a, "doe_export_max_kw", None),
                    "doe_import_max_kw": getattr(a, "doe_import_max_kw", None),
                }
                for a in assets
            ]

            total_gen_kw = sum(abs(a.current_kw) for a in assets if a.current_kw < 0.0)
            total_load_kw = sum(a.current_kw for a in assets if a.current_kw > 0.0)

            _grid_state[deployment_id] = {
                "deployment_id": deployment_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "local_hour": round(local_hour, 2),
                "solar_factor": round(sf, 3),
                "load_factor": round(lf, 3),
                "total_gen_kw": round(total_gen_kw, 1),
                "total_load_kw": round(total_load_kw, 1),
                "net_kw": round(total_load_kw - total_gen_kw, 1),
                "assets_online": sum(1 for a in assets if a.status == "ONLINE"),
                "assets_curtailed": sum(1 for a in assets if a.status == "CURTAILED"),
                "assets_offline": sum(1 for a in assets if a.status in ("OFFLINE", "FAULT")),
                "nodes": deployment_nodes_list,
                "assets": assets_list,
            }

        await db.commit()


# ── Background loop ───────────────────────────────────────────────────────────

async def grid_simulation_loop() -> None:
    """Main simulation background task — runs every aggregator_poll_interval seconds."""
    logger.info("Grid simulation loop started (interval=%ds)", settings.aggregator_poll_interval)
    await asyncio.sleep(5)

    while True:
        try:
            await update_grid_state()
        except Exception as exc:
            logger.error("Grid simulation error: %s", exc, exc_info=True)
        await asyncio.sleep(settings.aggregator_poll_interval)
