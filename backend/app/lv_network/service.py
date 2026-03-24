"""
LV Network service layer.

Handles:
  - Building LV feeder + bus records from OSM or synthetic topology
  - Running DistFlow power flow on LV feeders
  - Seeding synthetic LV networks behind all DTs in the grid topology
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import new_uuid, utcnow
from app.lv_network.models import LVBus, LVFeeder
from app.lv_network.osm_client import (
    build_synthetic_lv_network,
    fetch_lv_network_around_dt,
    fetch_lv_network_in_bbox,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Voltage thresholds (per-unit, LV base 230 V)
# ---------------------------------------------------------------------------

_V_HIGH_PU = 1.06
_V_LOW_PU = 0.94
_V_CRITICAL_LOW_PU = 0.90
_V_CRITICAL_HIGH_PU = 1.10


def _voltage_status(v_pu: float) -> str:
    if v_pu >= _V_CRITICAL_HIGH_PU or v_pu <= _V_CRITICAL_LOW_PU:
        return "CRITICAL"
    if v_pu > _V_HIGH_PU:
        return "HIGH"
    if v_pu < _V_LOW_PU:
        return "LOW"
    return "NORMAL"


# ---------------------------------------------------------------------------
# GeoJSON → LVFeeder + LVBus parsing
# ---------------------------------------------------------------------------

def _geojson_to_feeder_and_buses(
    geojson: dict,
    dt_node_id: str,
    deployment_id: str,
    feeder_name: str,
) -> tuple[LVFeeder, list[LVBus]]:
    """
    Parse a GeoJSON FeatureCollection (from OSM or synthetic) into an
    LVFeeder record and its associated LVBus records.
    """
    features: list[dict] = geojson.get("features", [])
    props = geojson.get("properties", {})

    dt_lat: Optional[float] = props.get("dt_lat")
    dt_lng: Optional[float] = props.get("dt_lng")

    # Separate features by geometry type
    ways = [f for f in features if f["geometry"]["type"] == "LineString"]
    nodes = [f for f in features if f["geometry"]["type"] == "Point"]

    # Compute total cable length from way features
    total_length_m = sum(f["properties"].get("length_m", 0.0) for f in ways)

    # Collect all way IDs and build route GeoJSON
    osm_way_ids: list = [
        f["properties"].get("osm_id")
        for f in ways
        if f["properties"].get("osm_id") is not None
    ]

    # Build a merged route GeoJSON (LineString from first way, or MultiLineString)
    if ways:
        if len(ways) == 1:
            route_geojson = json.dumps(ways[0]["geometry"])
        else:
            route_geojson = json.dumps({
                "type": "MultiLineString",
                "coordinates": [w["geometry"]["coordinates"] for w in ways],
            })
    else:
        route_geojson = None

    # Compute centroid from all node coordinates + way endpoints
    all_lats: list[float] = []
    all_lngs: list[float] = []

    for node in nodes:
        coords = node["geometry"]["coordinates"]
        all_lngs.append(coords[0])
        all_lats.append(coords[1])
    for way in ways:
        for coord in way["geometry"]["coordinates"]:
            all_lngs.append(coord[0])
            all_lats.append(coord[1])

    if all_lats:
        lat_centroid = sum(all_lats) / len(all_lats)
        lng_centroid = sum(all_lngs) / len(all_lngs)
    else:
        lat_centroid = dt_lat
        lng_centroid = dt_lng

    # Count customers
    customer_nodes = [
        n for n in nodes
        if n["properties"].get("node_type") == "CUSTOMER"
    ]
    customer_count = len(customer_nodes)

    now = utcnow()
    feeder_id = new_uuid()

    feeder = LVFeeder(
        id=feeder_id,
        deployment_id=deployment_id,
        dt_node_id=dt_node_id,
        name=feeder_name,
        description=f"LV feeder behind DT {dt_node_id} — source: {props.get('source', 'UNKNOWN')}",
        voltage_v=400.0,
        length_m=round(total_length_m, 1),
        customer_count=customer_count,
        lat_centroid=lat_centroid,
        lng_centroid=lng_centroid,
        osm_way_ids=json.dumps(osm_way_ids) if osm_way_ids else None,
        route_geojson=route_geojson,
        rated_kva=100.0,
        created_at=now,
        updated_at=now,
    )

    buses: list[LVBus] = []

    # Add DT secondary (slack bus) first — always present
    dt_secondary = LVBus(
        id=new_uuid(),
        lv_feeder_id=feeder_id,
        deployment_id=deployment_id,
        bus_ref="BUS-000",
        name=f"DT {dt_node_id} Secondary",
        bus_type="TRANSFORMER_SECONDARY",
        lat=dt_lat,
        lng=dt_lng,
        osm_node_id=None,
        phase="3PH",
        p_kw=0.0,
        q_kvar=0.0,
        v_pu=1.0,
        v_v=230.0,
        voltage_status="NORMAL",
        asset_id=None,
        created_at=now,
    )
    buses.append(dt_secondary)

    # Build buses from point features
    bus_counter = 1
    for node_feat in nodes:
        node_props = node_feat["properties"]
        node_type = node_props.get("node_type", "CUSTOMER")

        # Skip duplicate transformer secondary nodes — we already have one
        if node_type == "TRANSFORMER_SECONDARY":
            continue

        coords = node_feat["geometry"]["coordinates"]
        node_lng = coords[0]
        node_lat = coords[1]

        bus_ref = node_props.get("bus_ref") or f"BUS-{bus_counter:03d}"
        osm_node_id = str(node_props["osm_id"]) if node_props.get("osm_id") is not None else None

        bus = LVBus(
            id=new_uuid(),
            lv_feeder_id=feeder_id,
            deployment_id=deployment_id,
            bus_ref=bus_ref,
            name=None,
            bus_type=node_type,
            lat=node_lat,
            lng=node_lng,
            osm_node_id=osm_node_id,
            phase=node_props.get("phase", "3PH"),
            p_kw=0.0,
            q_kvar=0.0,
            v_pu=1.0,
            v_v=230.0,
            voltage_status="NORMAL",
            asset_id=None,
            created_at=now,
        )
        buses.append(bus)
        bus_counter += 1

    # If no customer nodes were found from OSM, add placeholder junction buses from ways
    if not customer_nodes and ways:
        for way in ways:
            coords_list = way["geometry"]["coordinates"]
            # Add midpoint of each segment as a junction bus
            for coord in coords_list[1:]:
                bus = LVBus(
                    id=new_uuid(),
                    lv_feeder_id=feeder_id,
                    deployment_id=deployment_id,
                    bus_ref=f"BUS-{bus_counter:03d}",
                    name=None,
                    bus_type="JUNCTION",
                    lat=coord[1],
                    lng=coord[0],
                    osm_node_id=None,
                    phase="3PH",
                    p_kw=0.0,
                    q_kvar=0.0,
                    v_pu=1.0,
                    v_v=230.0,
                    voltage_status="NORMAL",
                    asset_id=None,
                    created_at=now,
                )
                buses.append(bus)
                bus_counter += 1

    return feeder, buses


# ---------------------------------------------------------------------------
# Core service functions
# ---------------------------------------------------------------------------

async def get_or_build_lv_network(
    db: AsyncSession,
    dt_node_id: str,
    deployment_id: str,
    dt_lat: float,
    dt_lng: float,
    force_rebuild: bool = False,
    provider: str = "overpass",
) -> tuple[LVFeeder, list[LVBus]]:
    """
    Get existing LV network for a DT, or build one from OSM / synthetic data.

    Steps:
      1. Query DB for an existing LVFeeder with matching dt_node_id
      2. If found and force_rebuild is False, return it with its buses
      3. Otherwise: call osm_client.fetch_lv_network_around_dt()
      4. Parse the GeoJSON into LVFeeder + LVBus records
      5. Delete stale records (if force_rebuild) and persist the new ones
      6. Return (feeder, buses)
    """
    # 1. Check for existing feeder
    existing_result = await db.execute(
        select(LVFeeder).where(
            LVFeeder.dt_node_id == dt_node_id,
            LVFeeder.deployment_id == deployment_id,
        ).limit(1)
    )
    existing_feeder = existing_result.scalar_one_or_none()

    if existing_feeder and not force_rebuild:
        # 2. Return existing feeder with buses
        buses_result = await db.execute(
            select(LVBus).where(
                LVBus.lv_feeder_id == existing_feeder.id,
                LVBus.deployment_id == deployment_id,
            )
        )
        existing_buses = list(buses_result.scalars().all())
        return existing_feeder, existing_buses

    # 3. Fetch from OSM / synthetic
    geojson = await fetch_lv_network_around_dt(
        lat=dt_lat,
        lng=dt_lng,
        provider=provider,
    )

    # 4. Parse into ORM records
    feeder_name = f"LV-{dt_node_id}"
    feeder, buses = _geojson_to_feeder_and_buses(geojson, dt_node_id, deployment_id, feeder_name)

    # 5. Persist — delete stale records first if force_rebuild
    if existing_feeder and force_rebuild:
        # Delete existing buses
        stale_buses_result = await db.execute(
            select(LVBus).where(LVBus.lv_feeder_id == existing_feeder.id)
        )
        for stale_bus in stale_buses_result.scalars().all():
            await db.delete(stale_bus)
        await db.delete(existing_feeder)
        await db.flush()

    db.add(feeder)
    for bus in buses:
        db.add(bus)
    await db.flush()

    logger.info(
        "Built LV network for DT %s: %d buses, %.0fm cable",
        dt_node_id,
        len(buses),
        feeder.length_m,
    )

    return feeder, buses


async def run_lv_power_flow(
    db: AsyncSession,
    lv_feeder_id: str,
    deployment_id: str,
) -> dict:
    """
    Run DistFlow power flow on an LV feeder network.

    Steps:
      1. Load LVFeeder and LVBus records
      2. Load DERAsset current_kw for assets linked to buses
      3. Build BusData list (DT secondary = slack bus at 1.0 pu, 230V base)
      4. Build BranchData list (infer R/X from cable length;
         default: r_ohm = length_m/1000 * 0.25 Ω/km for 400V XLPE)
      5. Run DistFlowSolver
      6. Update LVBus.v_pu, v_v, voltage_status from result
      7. Cache result in LVFeeder.pf_result_json
      8. Return result dict
    """
    from app.grid.power_flow import BranchData, BusData, DistFlowSolver

    # 1. Load feeder
    feeder_result = await db.execute(
        select(LVFeeder).where(
            LVFeeder.id == lv_feeder_id,
            LVFeeder.deployment_id == deployment_id,
        )
    )
    feeder = feeder_result.scalar_one_or_none()
    if not feeder:
        raise ValueError(f"LVFeeder {lv_feeder_id} not found")

    # Load buses
    buses_result = await db.execute(
        select(LVBus).where(
            LVBus.lv_feeder_id == lv_feeder_id,
            LVBus.deployment_id == deployment_id,
        )
    )
    lv_buses: list[LVBus] = list(buses_result.scalars().all())

    if len(lv_buses) < 2:
        raise ValueError(f"LVFeeder {lv_feeder_id} has fewer than 2 buses — run get_or_build_lv_network first")

    # 2. Load DERAsset current_kw for linked assets
    asset_ids = [b.asset_id for b in lv_buses if b.asset_id]
    asset_kw_map: dict[str, float] = {}
    if asset_ids:
        try:
            from app.assets.models import DERAsset
            assets_result = await db.execute(
                select(DERAsset).where(DERAsset.id.in_(asset_ids))
            )
            for asset in assets_result.scalars().all():
                # PV / Wind = generation (negative load)
                if asset.type in ("PV", "WIND"):
                    asset_kw_map[asset.id] = -(asset.current_kw or 0.0)
                else:
                    asset_kw_map[asset.id] = asset.current_kw or 0.0
        except Exception as exc:
            logger.warning("Could not load DERAsset telemetry for LV PF: %s", exc)

    # Identify the slack bus (DT secondary = TRANSFORMER_SECONDARY)
    slack_bus = next(
        (b for b in lv_buses if b.bus_type == "TRANSFORMER_SECONDARY"),
        lv_buses[0],
    )

    # V_base for LV: 0.23 kV (230 V single-phase) or 0.4 kV (3-phase)
    v_base_kv = 0.4 if feeder.voltage_v >= 380.0 else 0.23

    # 3. Build BusData list
    bus_data_list: list[BusData] = []
    for lv_bus in lv_buses:
        # Net load from asset (if linked) or from bus p_kw field
        if lv_bus.asset_id and lv_bus.asset_id in asset_kw_map:
            p_kw = asset_kw_map[lv_bus.asset_id]
        else:
            p_kw = lv_bus.p_kw

        q_kvar = lv_bus.q_kvar if lv_bus.q_kvar != 0.0 else p_kw * 0.329

        is_slack = lv_bus.id == slack_bus.id

        bus_data_list.append(
            BusData(
                id=lv_bus.id,
                v_pu=1.0,
                p_kw=0.0 if is_slack else p_kw,
                q_kvar=0.0 if is_slack else q_kvar,
                v_base_kv=v_base_kv,
                is_slack=is_slack,
            )
        )

    # 4. Build BranchData list
    # Strategy: connect each non-slack bus to the slack (radial star topology)
    # For longer feeders this is a simplification; real topology would need a
    # proper adjacency graph, but that requires explicit topology data.
    #
    # Cable impedance defaults for 400V XLPE:
    #   r_ohm_per_km = 0.25  x_ohm_per_km = 0.08
    # For 230V single-phase:
    #   r_ohm_per_km = 0.50  x_ohm_per_km = 0.10
    R_PER_KM = 0.25 if v_base_kv >= 0.38 else 0.50
    X_PER_KM = 0.08 if v_base_kv >= 0.38 else 0.10
    AMPACITY_A = 200.0  # default for 95mm² XLPE

    # Build a bus lookup by id
    lv_bus_by_id: dict[str, LVBus] = {b.id: b for b in lv_buses}

    slack_lat = slack_bus.lat or feeder.lat_centroid or 0.0
    slack_lng = slack_bus.lng or feeder.lng_centroid or 0.0

    # Compute total feeder length for distributing cable segments
    non_slack_buses = [b for b in lv_buses if b.id != slack_bus.id]
    total_buses = len(non_slack_buses)

    # Distribute total feeder length evenly if we don't have per-bus coordinates
    avg_segment_km = (feeder.length_m / 1000.0 / total_buses) if total_buses > 0 else 0.05

    branch_data_list: list[BranchData] = []
    for lv_bus in non_slack_buses:
        # Calculate segment length from geographic coordinates if available
        if (
            lv_bus.lat is not None and lv_bus.lng is not None
            and slack_lat != 0.0 and slack_lng != 0.0
        ):
            from app.lv_network.osm_client import _haversine_m
            seg_m = _haversine_m(slack_lat, slack_lng, lv_bus.lat, lv_bus.lng)
            seg_km = max(0.01, seg_m / 1000.0)
        else:
            seg_km = avg_segment_km

        r_ohm = R_PER_KM * seg_km
        x_ohm = X_PER_KM * seg_km

        branch_data_list.append(
            BranchData(
                id=f"BR-{slack_bus.id[:8]}-{lv_bus.id[:8]}",
                from_bus=slack_bus.id,
                to_bus=lv_bus.id,
                r_ohm=r_ohm,
                x_ohm=x_ohm,
                ampacity_a=AMPACITY_A,
            )
        )

    if not branch_data_list:
        raise ValueError(f"No branches could be built for LVFeeder {lv_feeder_id}")

    # 5. Run DistFlow solver
    solver = DistFlowSolver(
        buses=bus_data_list,
        branches=branch_data_list,
        v_slack=1.0,
        max_iter=20,
        tol_pu=1e-5,
    )
    pf_result = solver.solve()

    # 6. Update LVBus voltage results
    v_nom_v = v_base_kv * 1000.0
    pf_bus_map: dict[str, dict] = {b["id"]: b for b in pf_result.buses}

    for lv_bus in lv_buses:
        if lv_bus.id in pf_bus_map:
            pf_bus = pf_bus_map[lv_bus.id]
            lv_bus.v_pu = pf_bus["v_pu"]
            lv_bus.v_v = round(pf_bus["v_pu"] * v_nom_v, 2)
            lv_bus.voltage_status = _voltage_status(pf_bus["v_pu"])

    # 7. Cache result in feeder
    result_dict = {
        "converged": pf_result.converged,
        "iterations": pf_result.iterations,
        "max_voltage_error_pu": pf_result.max_voltage_error_pu,
        "total_load_kw": pf_result.total_load_kw,
        "total_gen_kw": pf_result.total_gen_kw,
        "total_loss_kw": pf_result.total_loss_kw,
        "total_loss_kvar": pf_result.total_loss_kvar,
        "slack_injection_kw": pf_result.slack_injection_kw,
        "slack_injection_kvar": pf_result.slack_injection_kvar,
        "buses": pf_result.buses,
        "branches": pf_result.branches,
    }

    feeder.pf_result_json = json.dumps(result_dict)
    feeder.last_pf_run_at = utcnow()
    feeder.updated_at = feeder.last_pf_run_at

    await db.flush()

    # 8. Return enriched result
    violations = [b for b in pf_result.buses if b["voltage_status"] != "NORMAL"]
    return {
        **result_dict,
        "feeder_id": lv_feeder_id,
        "dt_node_id": feeder.dt_node_id,
        "source": "LV_DISTFLOW",
        "bus_count": len(lv_buses),
        "violations": violations,
        "violation_count": len(violations),
    }


async def seed_lv_networks(db: AsyncSession) -> None:
    """
    Seed synthetic LV networks behind each DISTRIBUTION_TRANSFORMER node
    in the grid topology.

    Idempotent — skips DTs that already have an LVFeeder.
    """
    from app.grid.models import GridNode

    # Find all DT nodes across all deployments
    dt_result = await db.execute(
        select(GridNode).where(
            GridNode.node_type == "DISTRIBUTION_TRANSFORMER"
        )
    )
    dt_nodes = list(dt_result.scalars().all())

    if not dt_nodes:
        logger.info("No DISTRIBUTION_TRANSFORMER nodes found — LV seed skipped")
        return

    seeded = 0
    skipped = 0

    for dt in dt_nodes:
        # Check if feeder already exists for this DT
        existing = await db.execute(
            select(LVFeeder).where(
                LVFeeder.dt_node_id == dt.node_id,
                LVFeeder.deployment_id == dt.deployment_id,
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        # Use DT lat/lng; default to 0,0 if missing (shouldn't happen in real data)
        dt_lat = dt.lat or 0.0
        dt_lng = dt.lng or 0.0

        # Vary customer count and feeder count by DT to produce diverse topologies
        # Use a deterministic pseudorandom variation based on node_id hash
        h = abs(hash(dt.node_id)) % 100
        customer_count = 6 + (h % 10)    # 6–15 customers
        feeder_count = 2 + (h % 3)       # 2–4 arms
        radius_m = 80.0 + (h % 120)      # 80–200 m

        geojson = build_synthetic_lv_network(
            dt_lat=dt_lat,
            dt_lng=dt_lng,
            customer_count=customer_count,
            feeder_count=feeder_count,
            radius_m=radius_m,
        )

        feeder_name = f"LV-{dt.node_id}"
        feeder, buses = _geojson_to_feeder_and_buses(
            geojson,
            dt.node_id,
            dt.deployment_id,
            feeder_name,
        )

        db.add(feeder)
        for bus in buses:
            db.add(bus)

        seeded += 1

    await db.flush()

    logger.info(
        "LV network seed complete: %d seeded, %d skipped (already exist)",
        seeded,
        skipped,
    )


async def get_congested_dts(
    db,
    deployment_id: str,
    threshold_loading_pct: float = 75.0,
    threshold_voltage_low: float = 0.95,
    threshold_voltage_high: float = 1.05,
) -> list[dict]:
    """
    Identify and rank distribution transformers (DTs) by congestion severity.

    Congestion score for each DT:
      score = max_branch_loading_pct
              + (count of buses with v_pu < threshold_voltage_low) * 20
              + (count of buses with v_pu > threshold_voltage_high) * 20

    For solar-heavy networks, voltage_high violations (reverse power flow)
    are the primary congestion type.

    Returns list of dicts sorted by congestion_score descending:
    {
        dt_node_id, feeder_id, rated_kva,
        congestion_score,
        congestion_type: THERMAL | VOLTAGE_LOW | VOLTAGE_HIGH | MIXED | NONE,
        max_loading_pct, violation_count_low, violation_count_high,
        has_power_flow_result: bool,
        lat, lng   (from GridNode if available, else null)
    }
    """
    # Query all LVFeeder records for this deployment
    feeders_result = await db.execute(
        select(LVFeeder).where(LVFeeder.deployment_id == deployment_id)
    )
    feeders: list[LVFeeder] = list(feeders_result.scalars().all())

    # Build a lat/lng lookup from GridNode keyed by dt_node_id
    dt_coords: dict[str, tuple[Optional[float], Optional[float]]] = {}
    try:
        from app.grid.models import GridNode
        gn_result = await db.execute(
            select(GridNode).where(
                GridNode.deployment_id == deployment_id,
                GridNode.node_type == "DISTRIBUTION_TRANSFORMER",
            )
        )
        for gn in gn_result.scalars().all():
            dt_coords[gn.node_id] = (gn.lat, gn.lng)
    except Exception as exc:
        logger.warning("Could not load GridNode coords for congestion analysis: %s", exc)

    results: list[dict] = []

    for feeder in feeders:
        lat, lng = dt_coords.get(feeder.dt_node_id, (None, None))

        if feeder.pf_result_json is None:
            results.append({
                "dt_node_id": feeder.dt_node_id,
                "feeder_id": feeder.id,
                "rated_kva": feeder.rated_kva,
                "congestion_score": 0.0,
                "congestion_type": "NONE",
                "max_loading_pct": 0.0,
                "violation_count_low": 0,
                "violation_count_high": 0,
                "has_power_flow_result": False,
                "lat": lat,
                "lng": lng,
            })
            continue

        # Parse power flow result
        try:
            pf: dict = json.loads(feeder.pf_result_json) if isinstance(feeder.pf_result_json, str) else feeder.pf_result_json
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Could not parse pf_result_json for feeder %s: %s", feeder.id, exc)
            results.append({
                "dt_node_id": feeder.dt_node_id,
                "feeder_id": feeder.id,
                "rated_kva": feeder.rated_kva,
                "congestion_score": 0.0,
                "congestion_type": "NONE",
                "max_loading_pct": 0.0,
                "violation_count_low": 0,
                "violation_count_high": 0,
                "has_power_flow_result": False,
                "lat": lat,
                "lng": lng,
            })
            continue

        branches: list[dict] = pf.get("branches", [])
        buses: list[dict] = pf.get("buses", [])

        # Max branch loading percentage
        max_loading_pct: float = 0.0
        for branch in branches:
            loading = branch.get("loading_pct", 0.0)
            if loading is not None and loading > max_loading_pct:
                max_loading_pct = loading

        # Count voltage violations
        violation_count_low = sum(
            1 for b in buses
            if (b.get("v_pu") is not None and b["v_pu"] < threshold_voltage_low)
        )
        violation_count_high = sum(
            1 for b in buses
            if (b.get("v_pu") is not None and b["v_pu"] > threshold_voltage_high)
        )

        congestion_score = (
            max_loading_pct
            + violation_count_low * 20.0
            + violation_count_high * 20.0
        )

        # Determine congestion type
        thermal_violation = max_loading_pct >= threshold_loading_pct
        low_violation = violation_count_low > 0
        high_violation = violation_count_high > 0

        violation_types = sum([thermal_violation, low_violation, high_violation])
        if violation_types == 0:
            congestion_type = "NONE"
        elif violation_types > 1:
            congestion_type = "MIXED"
        elif thermal_violation:
            congestion_type = "THERMAL"
        elif high_violation:
            congestion_type = "VOLTAGE_HIGH"
        else:
            congestion_type = "VOLTAGE_LOW"

        results.append({
            "dt_node_id": feeder.dt_node_id,
            "feeder_id": feeder.id,
            "rated_kva": feeder.rated_kva,
            "congestion_score": round(congestion_score, 2),
            "congestion_type": congestion_type,
            "max_loading_pct": round(max_loading_pct, 2),
            "violation_count_low": violation_count_low,
            "violation_count_high": violation_count_high,
            "has_power_flow_result": True,
            "lat": lat,
            "lng": lng,
        })

    # Sort by congestion_score descending
    results.sort(key=lambda x: x["congestion_score"], reverse=True)
    return results


async def fetch_area_lv_network(
    south: float,
    west: float,
    north: float,
    east: float,
    deployment_id: str,
    provider: str = "overpass",
) -> dict:
    """
    Fetch LV network GeoJSON for a geographic bounding box.
    Wraps fetch_lv_network_in_bbox from osm_client.
    Returns the GeoJSON FeatureCollection directly.
    """
    return await fetch_lv_network_in_bbox(
        south=south,
        west=west,
        north=north,
        east=east,
        provider=provider,
    )
