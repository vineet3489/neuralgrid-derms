"""
LV Network API routes.

Provides endpoints to:
  - Discover / build LV feeder topology for a distribution transformer
  - Run DistFlow power flow on an LV feeder
  - List LV feeders for a deployment
  - Query available GIS data providers
"""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.core.deps import CurrentUserDep, DBDep, DeploymentDep
from app.lv_network.models import LVBus, LVFeeder
from app.lv_network.schemas import LVBusRead, LVFeederRead
from app.lv_network.service import (
    fetch_area_lv_network,
    get_congested_dts,
    get_or_build_lv_network,
    run_lv_power_flow,
)

router = APIRouter(prefix="/api/v1/lv-network", tags=["lv-network"])


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDERS = [
    {
        "id": "overpass",
        "name": "OpenStreetMap (Overpass API)",
        "url": "https://overpass-api.de/api/interpreter",
        "is_default": True,
        "description": (
            "Queries the global OpenStreetMap Overpass API for mapped LV cables "
            "and overhead lines. Fallback to synthetic when no data is found."
        ),
    },
    {
        "id": "overpass_fr",
        "name": "OpenStreetMap (France mirror)",
        "url": "https://overpass.openstreetmap.fr/api/interpreter",
        "is_default": False,
        "description": (
            "Alternative Overpass mirror hosted in France. "
            "Use if the primary endpoint is rate-limited."
        ),
    },
    {
        "id": "synthetic",
        "name": "Synthetic (no internet required)",
        "url": "",
        "is_default": False,
        "description": (
            "Generates a synthetic radial LV feeder topology offline. "
            "Suitable for simulation, testing, and areas with no OSM coverage."
        ),
    },
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _feeder_geojson(feeder: LVFeeder, buses: list[LVBus]) -> dict:
    """Build a GeoJSON FeatureCollection from feeder + bus records for map display."""
    features = []

    # Feeder route as LineString (if available)
    if feeder.route_geojson:
        try:
            route_geo = json.loads(feeder.route_geojson) if isinstance(feeder.route_geojson, str) else feeder.route_geojson
            features.append({
                "type": "Feature",
                "geometry": route_geo,
                "properties": {
                    "feature_type": "feeder_route",
                    "feeder_id": feeder.id,
                    "name": feeder.name,
                    "voltage_v": feeder.voltage_v,
                    "length_m": feeder.length_m,
                },
            })
        except (json.JSONDecodeError, TypeError):
            pass

    # Bus nodes as Points
    for bus in buses:
        if bus.lat is not None and bus.lng is not None:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [bus.lng, bus.lat],
                },
                "properties": {
                    "feature_type": "lv_bus",
                    "bus_id": bus.id,
                    "bus_ref": bus.bus_ref,
                    "bus_type": bus.bus_type,
                    "phase": bus.phase,
                    "v_pu": bus.v_pu,
                    "v_v": bus.v_v,
                    "voltage_status": bus.voltage_status,
                    "p_kw": bus.p_kw,
                },
            })

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "feeder_id": feeder.id,
            "dt_node_id": feeder.dt_node_id,
            "deployment_id": feeder.deployment_id,
            "bus_count": len(buses),
        },
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/providers")
async def list_providers() -> dict:
    """List available GIS data providers for LV network discovery."""
    return {"providers": _PROVIDERS}


@router.get("/")
async def list_lv_feeders(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """List all LV feeders for the current deployment."""
    result = await db.execute(
        select(LVFeeder)
        .where(LVFeeder.deployment_id == deployment_id)
        .offset(offset)
        .limit(limit)
    )
    feeders = result.scalars().all()
    return {
        "items": [LVFeederRead.model_validate(f) for f in feeders],
        "total": len(feeders),
        "offset": offset,
    }


@router.get("/dt/{dt_node_id}")
async def get_lv_network_for_dt(
    dt_node_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    provider: str = Query("overpass", description="GIS provider: overpass / overpass_fr / synthetic"),
    force_rebuild: bool = Query(False, description="Force rebuild from source even if cached"),
) -> dict:
    """
    Get (or build) the LV feeder network behind a distribution transformer.

    On first call (or when force_rebuild=True) the feeder topology is fetched
    from the Overpass API or generated synthetically, then persisted to the DB.
    Subsequent calls return the cached topology instantly.

    Returns: feeder metadata, bus list, and a GeoJSON FeatureCollection for map display.
    """
    # Resolve DT location from GridNode
    dt_lat: Optional[float] = None
    dt_lng: Optional[float] = None

    try:
        from app.grid.models import GridNode
        from sqlalchemy import select as sa_select
        dt_result = await db.execute(
            sa_select(GridNode).where(
                GridNode.node_id == dt_node_id,
                GridNode.deployment_id == deployment_id,
                GridNode.node_type == "DISTRIBUTION_TRANSFORMER",
            ).limit(1)
        )
        dt_node = dt_result.scalar_one_or_none()
        if dt_node:
            dt_lat = dt_node.lat
            dt_lng = dt_node.lng
    except Exception:
        pass

    if dt_lat is None or dt_lng is None:
        # If no GridNode found, check for an existing feeder — may have centroid
        existing_result = await db.execute(
            select(LVFeeder).where(
                LVFeeder.dt_node_id == dt_node_id,
                LVFeeder.deployment_id == deployment_id,
            ).limit(1)
        )
        existing = existing_result.scalar_one_or_none()
        if existing and not force_rebuild:
            buses_result = await db.execute(
                select(LVBus).where(LVBus.lv_feeder_id == existing.id)
            )
            buses = list(buses_result.scalars().all())
            return {
                "feeder": LVFeederRead.model_validate(existing),
                "buses": [LVBusRead.model_validate(b) for b in buses],
                "geojson": _feeder_geojson(existing, buses),
            }
        # Default to (0, 0) — synthetic will still produce a valid topology
        dt_lat = 0.0
        dt_lng = 0.0

    try:
        feeder, buses = await get_or_build_lv_network(
            db=db,
            dt_node_id=dt_node_id,
            deployment_id=deployment_id,
            dt_lat=dt_lat,
            dt_lng=dt_lng,
            force_rebuild=force_rebuild,
            provider=provider,
        )
        await db.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to build LV network: {exc}")

    return {
        "feeder": LVFeederRead.model_validate(feeder),
        "buses": [LVBusRead.model_validate(b) for b in buses],
        "geojson": _feeder_geojson(feeder, buses),
    }


@router.post("/dt/{dt_node_id}/power-flow")
async def run_power_flow_for_dt(
    dt_node_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    Run DistFlow power flow on the LV network behind a distribution transformer.

    The LV feeder must already exist (call GET /dt/{dt_node_id} first to build it).
    Updates bus voltage results in the DB and caches the full power flow result
    on the feeder record.

    Returns the power flow result with feeder_id, dt_node_id, and source fields.
    """
    # Find the feeder for this DT
    feeder_result = await db.execute(
        select(LVFeeder).where(
            LVFeeder.dt_node_id == dt_node_id,
            LVFeeder.deployment_id == deployment_id,
        ).limit(1)
    )
    feeder = feeder_result.scalar_one_or_none()

    if not feeder:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No LV feeder found for DT '{dt_node_id}'. "
                "Call GET /api/v1/lv-network/dt/{dt_node_id} first to build the network."
            ),
        )

    try:
        result = await run_lv_power_flow(
            db=db,
            lv_feeder_id=feeder.id,
            deployment_id=deployment_id,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Power flow failed: {exc}")

    return result


@router.get("/congested-dts")
async def get_congested_dts_endpoint(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    threshold_pct: float = Query(75.0, ge=0, le=100, description="Branch loading threshold %"),
    limit: int = Query(20, ge=1, le=100, description="Maximum DTs to return"),
) -> list:
    """
    Return DTs ranked by congestion score (loading % + voltage violations).
    Used to identify which DTs to target for power flow and OSM fetch.
    Solar-heavy networks show VOLTAGE_HIGH as primary congestion type.
    """
    try:
        results = await get_congested_dts(
            db=db,
            deployment_id=deployment_id,
            threshold_loading_pct=threshold_pct,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Congestion analysis failed: {exc}")

    return results[:limit]


@router.get("/dynamic-oe/{cmz_id}")
async def get_dynamic_oe(
    cmz_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    horizon_hours: int = Query(48, ge=1, le=168),
    recalculate: bool = Query(False, description="Force recalculation even if cached"),
) -> dict:
    """
    Dynamic Operating Envelope for a CMZ derived from time-series DistFlow.

    Returns 30-min slots with physics-based export/import limits,
    voltage bounds, and branch loading. Falls back to arithmetic if
    DistFlow data not available.

    Set ?recalculate=true to trigger immediate recalculation (slow, ~2s per CMZ).
    """
    try:
        if recalculate:
            from app.lv_network.dynamic_oe import compute_cmz_dynamic_oe
            slots = await compute_cmz_dynamic_oe(db, cmz_id, deployment_id, horizon_hours)
            await db.commit()
        else:
            from app.forecasting.service import generate_oe_headroom_forecast
            slots = await generate_oe_headroom_forecast(db, cmz_id, deployment_id, horizon_hours)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Dynamic OE calculation failed: {exc}")

    return {
        "cmz_id": cmz_id,
        "deployment_id": deployment_id,
        "horizon_hours": horizon_hours,
        "interval_count": len(slots),
        "source": slots[0].get("source", "UNKNOWN") if slots else "NONE",
        "slots": slots,
    }


@router.get("/area")
async def get_area_lv_network(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    south: float = Query(..., description="Bounding box south latitude"),
    west: float = Query(..., description="Bounding box west longitude"),
    north: float = Query(..., description="Bounding box north latitude"),
    east: float = Query(..., description="Bounding box east longitude"),
    provider: str = Query("overpass", description="GIS provider: overpass | overpass_fr"),
) -> dict:
    """
    Fetch all LV electrical infrastructure within a geographic bounding box.
    Returns GeoJSON FeatureCollection with cables, lines, transformers, substations.
    Used by the GIS map area-selector to show the full LV network for a pilot zone.
    """
    try:
        geojson = await fetch_area_lv_network(
            south=south,
            west=west,
            north=north,
            east=east,
            deployment_id=deployment_id,
            provider=provider,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Area LV network fetch failed: {exc}")

    return geojson
