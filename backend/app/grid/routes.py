"""Grid API endpoints — real-time state, CMZs, nodes, alerts, dashboard."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, select

from app.core.deps import CurrentUserDep, DBDep, DeploymentDep
from app.grid.models import CMZ, GridAlert, GridNode
from app.grid.schemas import (
    CMZRead,
    DashboardKPIs,
    DashboardResponse,
    GridAlertAcknowledge,
    GridAlertRead,
    GridNodeRead,
    HostingCapacitySummary,
)
from app.grid.simulation import DEPLOYMENT_TOPOLOGIES, get_grid_state

router = APIRouter(prefix="/api/v1/grid", tags=["grid"])


# ── Grid state ────────────────────────────────────────────────────────────────

@router.get("/state")
async def get_deployment_grid_state(
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Return the latest cached grid state for the current deployment."""
    state = get_grid_state(deployment_id)
    if not state:
        return {
            "deployment_id": deployment_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": "No grid state available yet — simulation may be starting.",
            "nodes": [],
            "assets": [],
        }
    return state


@router.get("/state/{dep_id}")
async def get_specific_deployment_state(
    dep_id: str,
    current_user: CurrentUserDep,
) -> dict:
    """Return grid state for a specific deployment (SUPER_ADMIN only)."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="SUPER_ADMIN access required")
    state = get_grid_state(dep_id.lower())
    if not state:
        raise HTTPException(status_code=404, detail=f"No state for deployment '{dep_id}'")
    return state


# ── CMZs ──────────────────────────────────────────────────────────────────────

@router.get("/cmzs", response_model=List[CMZRead])
async def list_cmzs(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> List[CMZ]:
    result = await db.execute(
        select(CMZ).where(CMZ.deployment_id == deployment_id).order_by(CMZ.name)
    )
    return result.scalars().all()


# ── GridNodes ─────────────────────────────────────────────────────────────────

@router.get("/nodes", response_model=List[GridNodeRead])
async def list_grid_nodes(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    node_type: Optional[str] = Query(None, description="Filter by FEEDER / DISTRIBUTION_TRANSFORMER"),
    cmz_id: Optional[str] = Query(None, description="Filter by CMZ slug"),
) -> List[GridNode]:
    stmt = select(GridNode).where(GridNode.deployment_id == deployment_id)
    if node_type:
        stmt = stmt.where(GridNode.node_type == node_type.upper())
    if cmz_id:
        stmt = stmt.where(GridNode.cmz_id == cmz_id)
    result = await db.execute(stmt.order_by(GridNode.node_type, GridNode.name))
    return result.scalars().all()


# ── Grid alerts ───────────────────────────────────────────────────────────────

@router.get("/alerts", response_model=List[GridAlertRead])
async def list_grid_alerts(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    unresolved_only: bool = Query(True),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> List[GridAlert]:
    stmt = select(GridAlert).where(GridAlert.deployment_id == deployment_id)
    if unresolved_only:
        stmt = stmt.where(GridAlert.resolved_at.is_(None))
    if severity:
        stmt = stmt.where(GridAlert.severity == severity.upper())
    stmt = stmt.order_by(desc(GridAlert.created_at)).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/alerts/{alert_id}/acknowledge", response_model=GridAlertRead)
async def acknowledge_alert(
    alert_id: str,
    body: GridAlertAcknowledge,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> GridAlert:
    """Acknowledge a grid alert (GRID_OPS or higher)."""
    result = await db.execute(
        select(GridAlert).where(
            GridAlert.id == alert_id,
            GridAlert.deployment_id == deployment_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.is_acknowledged:
        raise HTTPException(status_code=409, detail="Alert already acknowledged")

    alert.is_acknowledged = True
    alert.acknowledged_by = body.acknowledged_by or current_user.email
    alert.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(alert)
    return alert


# ── Hosting capacity ──────────────────────────────────────────────────────────

@router.get("/hosting-capacity")
async def hosting_capacity_summary(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> List[dict]:
    """Return hosting capacity summary per CMZ."""
    cmzs_result = await db.execute(
        select(CMZ).where(CMZ.deployment_id == deployment_id)
    )
    cmzs = cmzs_result.scalars().all()
    summaries = []

    for cmz in cmzs:
        nodes_result = await db.execute(
            select(GridNode).where(
                GridNode.deployment_id == deployment_id,
                GridNode.cmz_id == cmz.slug,
            )
        )
        nodes = nodes_result.scalars().all()
        total_cap = sum(n.hosting_capacity_kw for n in nodes)
        used_cap = sum(n.used_capacity_kw for n in nodes)
        util_pct = round((used_cap / total_cap * 100.0) if total_cap > 0 else 0.0, 1)

        summaries.append({
            "cmz_slug": cmz.slug,
            "cmz_name": cmz.name,
            "topology_type": cmz.topology_type,
            "max_import_kw": cmz.max_import_kw,
            "max_export_kw": cmz.max_export_kw,
            "total_hosting_capacity_kw": round(total_cap, 1),
            "used_capacity_kw": round(used_cap, 1),
            "available_kw": round(total_cap - used_cap, 1),
            "utilisation_pct": util_pct,
            "nodes": [
                {
                    "node_id": n.node_id,
                    "name": n.name,
                    "type": n.node_type,
                    "hosting_capacity_kw": n.hosting_capacity_kw,
                    "used_capacity_kw": n.used_capacity_kw,
                    "loading_pct": n.current_loading_pct,
                }
                for n in nodes
            ],
        })

    return summaries


# ── Topology (GIS export) ─────────────────────────────────────────────────────

@router.get("/topology")
async def get_topology(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Return full topology JSON for GIS visualisation."""
    cmzs_result = await db.execute(
        select(CMZ).where(CMZ.deployment_id == deployment_id)
    )
    cmzs = cmzs_result.scalars().all()

    nodes_result = await db.execute(
        select(GridNode).where(GridNode.deployment_id == deployment_id)
    )
    nodes = nodes_result.scalars().all()

    # Build feeder -> DT hierarchy
    feeders_map: dict = {}
    dts_map: dict = {}
    for n in nodes:
        if n.node_type == "FEEDER":
            feeders_map[n.node_id] = {
                "node_id": n.node_id,
                "name": n.name,
                "cmz_id": n.cmz_id,
                "voltage_kv": n.voltage_kv,
                "rated_mva": n.rated_mva,
                "current_loading_pct": n.current_loading_pct,
                "hosting_capacity_kw": n.hosting_capacity_kw,
                "dts": [],
            }
        elif n.node_type == "DISTRIBUTION_TRANSFORMER":
            dts_map[n.node_id] = {
                "node_id": n.node_id,
                "name": n.name,
                "cmz_id": n.cmz_id,
                "rated_kva": n.rated_kva,
                "current_loading_pct": n.current_loading_pct,
                "voltage_l1_v": n.voltage_l1_v,
                "hosting_capacity_kw": n.hosting_capacity_kw,
                "lat": n.lat,
                "lng": n.lng,
            }

    # Attach DTs to feeders from topology definition
    topo = DEPLOYMENT_TOPOLOGIES.get(deployment_id, {})
    for cmz_def in topo.get("cmzs", []):
        for feeder_def in cmz_def.get("feeders", []):
            fdr = feeders_map.get(feeder_def["id"])
            if fdr:
                for dt_def in feeder_def.get("dts", []):
                    dt = dts_map.get(dt_def["id"])
                    if dt:
                        fdr["dts"].append(dt)

    return {
        "deployment_id": deployment_id,
        "cmzs": [
            {
                "slug": c.slug,
                "name": c.name,
                "topology_type": c.topology_type,
                "max_import_kw": c.max_import_kw,
                "max_export_kw": c.max_export_kw,
                "feeder_ids": json.loads(c.feeder_ids) if c.feeder_ids else [],
                "feeders": [
                    feeders_map[fid]
                    for fid in (json.loads(c.feeder_ids) if c.feeder_ids else [])
                    if fid in feeders_map
                ],
            }
            for c in cmzs
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Aggregated dashboard: KPIs, grid state, active alerts, recent events, forecast."""
    grid_state = get_grid_state(deployment_id)

    # Active alerts
    alerts_result = await db.execute(
        select(GridAlert)
        .where(
            GridAlert.deployment_id == deployment_id,
            GridAlert.resolved_at.is_(None),
        )
        .order_by(desc(GridAlert.created_at))
        .limit(20)
    )
    alerts = alerts_result.scalars().all()

    # Recent flex events
    recent_events: List[dict] = []
    try:
        from app.dispatch.models import FlexEvent
        from sqlalchemy import desc as _desc

        events_result = await db.execute(
            select(FlexEvent)
            .where(FlexEvent.deployment_id == deployment_id)
            .order_by(_desc(FlexEvent.created_at))
            .limit(10)
        )
        recent_events = [
            {
                "id": e.id,
                "event_ref": e.event_ref,
                "event_type": e.event_type,
                "status": e.status,
                "target_kw": e.target_kw,
                "dispatched_kw": e.dispatched_kw,
                "start_time": e.start_time.isoformat() if e.start_time else None,
            }
            for e in events_result.scalars().all()
        ]
    except Exception:
        pass

    # 24 h forecast (first 24 h of solar + load)
    forecast_24h: dict = {}
    try:
        from app.forecasting.service import get_latest_forecast

        solar_fc = await get_latest_forecast(db, deployment_id, "SOLAR")
        load_fc = await get_latest_forecast(db, deployment_id, "LOAD")
        if solar_fc or load_fc:
            forecast_24h = {
                "solar": (solar_fc.get("values") or [])[:48],
                "load": (load_fc.get("values") or [])[:48],
            }
    except Exception:
        pass

    # KPIs
    alerts_list = [
        {
            "id": a.id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "message": a.message,
            "node_id": a.node_id,
            "is_acknowledged": a.is_acknowledged,
            "created_at": a.created_at.isoformat(),
        }
        for a in alerts
    ]

    total_gen = grid_state.get("total_gen_kw", 0.0)
    total_load = grid_state.get("total_load_kw", 0.0)
    renewable_pct = round((total_gen / total_load * 100.0) if total_load > 0 else 0.0, 1)

    kpis = {
        "total_gen_kw": total_gen,
        "total_load_kw": total_load,
        "net_kw": grid_state.get("net_kw", 0.0),
        "assets_online": grid_state.get("assets_online", 0),
        "assets_curtailed": grid_state.get("assets_curtailed", 0),
        "assets_offline": grid_state.get("assets_offline", 0),
        "alerts_active": len(alerts),
        "alerts_critical": sum(1 for a in alerts if a.severity == "CRITICAL"),
        "renewable_penetration_pct": renewable_pct,
    }

    return {
        "deployment_id": deployment_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kpis": kpis,
        "grid_state": grid_state,
        "active_alerts": alerts_list,
        "recent_events": recent_events,
        "forecast_24h": forecast_24h,
    }
