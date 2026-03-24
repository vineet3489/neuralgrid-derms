"""
OSM Overpass API client for LV network discovery.

Queries the OpenStreetMap Overpass API for low-voltage electrical infrastructure
near a distribution transformer location.  Falls back to a synthetic radial
network topology when OSM has no relevant cable data (common for underground LV
which is rarely mapped in OSM).
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

OSM_PROVIDER = "overpass"

# Provider URL registry
_PROVIDER_URLS: dict[str, str] = {
    "overpass": "https://overpass-api.de/api/interpreter",
    "overpass_fr": "https://overpass.openstreetmap.fr/api/interpreter",
    "synthetic": "",
}

# Approximate metres per degree of latitude (constant)
_M_PER_DEG_LAT = 111_320.0


def _metres_per_deg_lng(lat_deg: float) -> float:
    """Metres per degree of longitude at given latitude."""
    return _M_PER_DEG_LAT * math.cos(math.radians(lat_deg))


def _offset_coord(lat: float, lng: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """
    Return (lat, lng) after travelling distance_m metres from (lat, lng)
    in direction bearing_deg (0 = North, 90 = East).
    Uses flat-earth approximation — accurate enough for <500 m offsets.
    """
    bearing_rad = math.radians(bearing_deg)
    d_north = distance_m * math.cos(bearing_rad)
    d_east = distance_m * math.sin(bearing_rad)
    new_lat = lat + d_north / _M_PER_DEG_LAT
    new_lng = lng + d_east / _metres_per_deg_lng(lat)
    return new_lat, new_lng


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in metres."""
    R = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _parse_overpass_to_geojson(overpass_data: dict, dt_lat: float, dt_lng: float) -> dict:
    """
    Convert raw Overpass JSON output into a GeoJSON FeatureCollection.

    Overpass returns elements with type 'way' or 'node'; ways include geometry
    when using 'out geom'.
    """
    features: list[dict] = []

    elements: list[dict] = overpass_data.get("elements", [])

    # Build node lookup for way geometry
    node_map: dict[int, dict] = {}
    for el in elements:
        if el.get("type") == "node":
            node_map[el["id"]] = el

    for el in elements:
        if el.get("type") == "way":
            tags = el.get("tags", {})
            geometry = el.get("geometry", [])  # list of {lat, lon}

            if not geometry:
                # Fall back to building coords from node refs if available
                refs = el.get("nodes", [])
                geometry = [
                    {"lat": node_map[ref]["lat"], "lon": node_map[ref]["lon"]}
                    for ref in refs
                    if ref in node_map
                ]

            if len(geometry) < 2:
                continue

            coords = [[g["lon"], g["lat"]] for g in geometry]

            # Compute approximate length from coordinate chain
            length_m = 0.0
            for i in range(len(coords) - 1):
                length_m += _haversine_m(
                    coords[i][1], coords[i][0],
                    coords[i + 1][1], coords[i + 1][0],
                )

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords,
                },
                "properties": {
                    "osm_id": el["id"],
                    "power": tags.get("power", "cable"),
                    "voltage": tags.get("voltage", "400"),
                    "cable_type": tags.get("cable", "unknown"),
                    "length_m": round(length_m, 1),
                    "source": "OSM",
                },
            })

        elif el.get("type") == "node":
            tags = el.get("tags", {})
            if not tags:
                continue
            node_type = "JUNCTION"
            if tags.get("power") in ("meter", "connection"):
                node_type = "CUSTOMER"
            elif tags.get("power") == "transformer":
                node_type = "TRANSFORMER_SECONDARY"

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [el["lon"], el["lat"]],
                },
                "properties": {
                    "osm_id": el["id"],
                    "node_type": node_type,
                    "phase": "3PH",
                    "source": "OSM",
                },
            })

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "source": "OSM",
            "dt_lat": dt_lat,
            "dt_lng": dt_lng,
        },
    }


def build_synthetic_lv_network(
    dt_lat: float,
    dt_lng: float,
    customer_count: int = 8,
    feeder_count: int = 3,
    radius_m: float = 150.0,
) -> dict:
    """
    Generate a synthetic radial LV feeder topology when OSM data is unavailable.

    Creates feeder_count radial arms radiating from the DT location, with
    customer_count / feeder_count customers evenly spaced along each arm.
    Uses bearing-based coordinate offsets from the DT location.

    Returns a GeoJSON FeatureCollection with the same structure as the Overpass
    query result, tagged with source='SYNTHETIC'.
    """
    features: list[dict] = []

    # Add the DT secondary (slack) bus node at the origin
    features.append({
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [dt_lng, dt_lat],
        },
        "properties": {
            "osm_id": None,
            "node_type": "TRANSFORMER_SECONDARY",
            "bus_ref": "BUS-000",
            "phase": "3PH",
            "source": "SYNTHETIC",
        },
    })

    # Distribute bearings evenly, starting from North, rotating clockwise
    # Offset slightly so arms don't overlap exactly on cardinal directions
    base_bearing_offset = 15.0
    bearing_step = 360.0 / feeder_count

    customers_per_feeder = max(1, customer_count // feeder_count)
    # Remaining customers go on the last feeder
    remainder = customer_count - customers_per_feeder * (feeder_count - 1)

    bus_counter = 1

    for arm_idx in range(feeder_count):
        bearing = (base_bearing_offset + arm_idx * bearing_step) % 360.0
        n_customers = customers_per_feeder if arm_idx < feeder_count - 1 else remainder
        if n_customers <= 0:
            n_customers = 1

        # Spacing between customers along the arm
        segment_len = radius_m / (n_customers + 1)

        arm_coords: list[list[float]] = [[dt_lng, dt_lat]]  # starts at DT
        prev_lat, prev_lng = dt_lat, dt_lng

        for cust_idx in range(n_customers):
            dist = segment_len * (cust_idx + 1)
            c_lat, c_lng = _offset_coord(dt_lat, dt_lng, bearing, dist)

            # Add a slight lateral offset to simulate real cable route meander
            meander_bearing = (bearing + 90.0) % 360.0
            meander_m = segment_len * 0.08 * ((cust_idx % 3) - 1)
            if meander_m != 0:
                c_lat, c_lng = _offset_coord(c_lat, c_lng, meander_bearing, meander_m)

            arm_coords.append([c_lng, c_lat])

            # Assign phase: rotate L1/L2/L3 across customers
            phases = ["L1", "L2", "L3", "3PH"]
            phase = phases[cust_idx % 3]

            bus_ref = f"BUS-{bus_counter:03d}"
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [c_lng, c_lat],
                },
                "properties": {
                    "osm_id": None,
                    "node_type": "CUSTOMER",
                    "bus_ref": bus_ref,
                    "arm": arm_idx,
                    "phase": phase,
                    "source": "SYNTHETIC",
                },
            })
            bus_counter += 1
            prev_lat, prev_lng = c_lat, c_lng

        # Compute arm cable length
        arm_length_m = 0.0
        for i in range(len(arm_coords) - 1):
            arm_length_m += _haversine_m(
                arm_coords[i][1], arm_coords[i][0],
                arm_coords[i + 1][1], arm_coords[i + 1][0],
            )

        # Add the cable way for this arm
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": arm_coords,
            },
            "properties": {
                "osm_id": None,
                "power": "cable",
                "voltage": "400",
                "cable_type": "XLPE",
                "length_m": round(arm_length_m, 1),
                "arm": arm_idx,
                "source": "SYNTHETIC",
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "source": "SYNTHETIC",
            "dt_lat": dt_lat,
            "dt_lng": dt_lng,
            "customer_count": customer_count,
            "feeder_count": feeder_count,
            "radius_m": radius_m,
        },
    }


async def fetch_lv_network_around_dt(
    lat: float,
    lng: float,
    radius_m: int = 300,
    provider: str = "overpass",
) -> dict:
    """
    Query Overpass API for LV electrical infrastructure near a DT.

    Returns a GeoJSON FeatureCollection with ways (cables / overhead lines)
    and nodes (connection points / meters).

    Overpass query fetches:
      - ways tagged power=cable with voltage ~400 or 230
      - ways tagged power=line  with voltage ~400 or 230
      - ways tagged power=cable or power=line (any voltage, for wider net)

    Falls back to synthetic radial network generation when OSM has no data or
    a network error occurs.  Underground LV cables are rarely mapped in OSM so
    the synthetic fallback is used frequently in production.
    """
    if provider == "synthetic":
        logger.info("Synthetic provider requested — skipping Overpass query")
        return build_synthetic_lv_network(lat, lng)

    provider_url = _PROVIDER_URLS.get(provider, _PROVIDER_URLS["overpass"])

    overpass_query = (
        f"[out:json];"
        f"("
        f'way["power"="cable"]["voltage"~"400|230"](around:{radius_m},{lat},{lng});'
        f'way["power"="line"]["voltage"~"400|230"](around:{radius_m},{lat},{lng});'
        f'way["power"~"cable|line"](around:{radius_m},{lat},{lng});'
        f");"
        f"out geom;"
    )

    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                provider_url,
                data={"data": overpass_query},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            overpass_data: dict = response.json()

    except Exception as exc:
        logger.warning(
            "Overpass API request failed (%s: %s) — falling back to synthetic network",
            type(exc).__name__,
            exc,
        )
        return build_synthetic_lv_network(lat, lng)

    # Parse the OSM response
    geojson = _parse_overpass_to_geojson(overpass_data, lat, lng)

    # Check if we got meaningful data (at least one way feature)
    way_features = [
        f for f in geojson["features"]
        if f["geometry"]["type"] == "LineString"
    ]

    if not way_features:
        logger.info(
            "No LV cable ways found in OSM around (%.5f, %.5f) r=%dm — using synthetic",
            lat, lng, radius_m,
        )
        return build_synthetic_lv_network(lat, lng)

    logger.info(
        "Fetched %d OSM features (ways=%d) around (%.5f, %.5f)",
        len(geojson["features"]),
        len(way_features),
        lat,
        lng,
    )
    return geojson


async def fetch_lv_network_in_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    provider: str = "overpass",
) -> dict:
    """
    Query Overpass API for ALL LV electrical infrastructure within a bounding box.

    Used for area-level queries (e.g. a pilot zone) rather than per-DT queries.
    Returns a GeoJSON FeatureCollection with:
      - ways: LV cables and overhead lines (LineString)
      - nodes: transformers, substations, connection points (Point)

    Overpass query uses [bbox:south,west,north,east] format.
    Falls back to empty FeatureCollection (not synthetic) on failure — bbox
    synthetic generation is not meaningful without a specific DT anchor point.
    """
    provider_url = _PROVIDER_URLS.get(provider, _PROVIDER_URLS["overpass"])

    overpass_query = (
        f"[out:json][timeout:30][bbox:{south},{west},{north},{east}];\n"
        f"(\n"
        f'  way["power"="cable"]["voltage"~"400|230|11000"];\n'
        f'  way["power"="line"]["voltage"~"400|230|11000"];\n'
        f'  way["power"="minor_line"];\n'
        f'  node["power"="transformer"];\n'
        f'  node["power"="substation"];\n'
        f'  node["power"~"meter|connection"];\n'
        f");\n"
        f"out geom;"
    )

    # Use the centre of the bbox as the dt_lat/dt_lng anchor for _parse_overpass_to_geojson
    center_lat = (south + north) / 2.0
    center_lng = (west + east) / 2.0

    try:
        import httpx

        async with httpx.AsyncClient(timeout=35.0) as client:
            response = await client.post(
                provider_url,
                data={"data": overpass_query},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            overpass_data: dict = response.json()

    except Exception as exc:
        logger.warning(
            "Overpass bbox query failed (%s: %s) — returning empty FeatureCollection",
            type(exc).__name__,
            exc,
        )
        return {
            "type": "FeatureCollection",
            "features": [],
            "properties": {
                "source": "ERROR",
                "error": str(exc),
                "bbox": [south, west, north, east],
            },
        }

    geojson = _parse_overpass_to_geojson(overpass_data, center_lat, center_lng)

    # Augment properties with bbox info
    geojson["properties"]["bbox"] = [south, west, north, east]

    logger.info(
        "Bbox query [%.5f,%.5f,%.5f,%.5f]: %d features returned",
        south, west, north, east,
        len(geojson["features"]),
    )
    return geojson
