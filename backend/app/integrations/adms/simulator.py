"""
Simulated GE ADMS REST API.

In production, this would be replaced by actual GE APM/ADMS REST endpoints.
Provides: topology, real-time SCADA state, constraint data, and a DER status
receive endpoint.

Mounted at /sim/adms by main.py (not behind auth for simulator convenience).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/sim/adms", tags=["adms-simulator"])


@router.get("/realtime/state")
async def get_realtime_state(deployment_id: str = "ssen") -> dict:
    """Return simulated ADMS real-time grid state (proxies in-memory simulation)."""
    from app.grid.simulation import get_grid_state

    state = get_grid_state(deployment_id.lower())
    return {
        "source": "simulated-adms",
        "deployment_id": deployment_id.lower(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "state": state,
    }


@router.get("/topology/cim/{deployment_id}")
async def get_cim_topology(deployment_id: str) -> dict:
    """
    Return simplified topology JSON for a deployment.
    In production this would return CIM XML (IEC 61968/61970).
    """
    from app.grid.simulation import DEPLOYMENT_TOPOLOGIES

    dep = deployment_id.lower()
    topo = DEPLOYMENT_TOPOLOGIES.get(dep, {})
    if not topo:
        return {"error": f"Unknown deployment '{dep}'", "known": list(DEPLOYMENT_TOPOLOGIES.keys())}

    return {
        "deployment_id": dep,
        "format": "simplified_json",
        "note": "Production would return IEC 61968 CIM XML",
        "topology": {
            "timezone_offset_hours": topo.get("timezone_offset"),
            "voltage_nominal_v": topo.get("voltage_nominal"),
            "cmzs": [
                {
                    "slug": cmz["slug"],
                    "name": cmz["name"],
                    "topology_type": cmz["topology"],
                    "max_import_kw": cmz["max_import_kw"],
                    "max_export_kw": cmz["max_export_kw"],
                    "feeders": [
                        {
                            "id": f["id"],
                            "name": f["name"],
                            "voltage_kv": f["voltage_kv"],
                            "rated_mva": f["rated_mva"],
                            "distribution_transformers": [
                                {
                                    "id": dt["id"],
                                    "name": dt["name"],
                                    "rated_kva": dt["rated_kva"],
                                    "lat": dt.get("lat"),
                                    "lng": dt.get("lng"),
                                }
                                for dt in f.get("dts", [])
                            ],
                        }
                        for f in cmz.get("feeders", [])
                    ],
                }
                for cmz in topo.get("cmzs", [])
            ],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/constraints/{deployment_id}")
async def get_active_constraints(deployment_id: str) -> dict:
    """Return currently active network constraints from simulated ADMS."""
    from app.grid.simulation import get_grid_state
    from app.config import settings

    state = get_grid_state(deployment_id.lower())
    if not state:
        return {"deployment_id": deployment_id, "constraints": []}

    constraints = []
    for node in state.get("nodes", []):
        loading = node.get("current_loading_pct", 0.0)
        v1 = node.get("voltage_l1_v", 230.0) or 230.0
        nid = node.get("node_id", "")

        if loading > settings.feeder_loading_warn:
            constraints.append({
                "node_id": nid,
                "constraint_type": "OVERLOAD",
                "current_value": loading,
                "threshold": settings.feeder_loading_warn,
                "severity": "CRITICAL" if loading >= 100.0 else "WARNING",
            })
        if v1 > settings.voltage_high_warn:
            constraints.append({
                "node_id": nid,
                "constraint_type": "OVERVOLTAGE",
                "current_value": v1,
                "threshold": settings.voltage_high_warn,
                "severity": "CRITICAL" if v1 > settings.voltage_high_trip else "WARNING",
            })
        if v1 < settings.voltage_low_warn:
            constraints.append({
                "node_id": nid,
                "constraint_type": "UNDERVOLTAGE",
                "current_value": v1,
                "threshold": settings.voltage_low_warn,
                "severity": "CRITICAL" if v1 < settings.voltage_low_trip else "WARNING",
            })

    return {
        "deployment_id": deployment_id.lower(),
        "constraint_count": len(constraints),
        "constraints": constraints,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/der-status")
async def receive_der_status(payload: dict) -> dict:
    """
    Receive DER status updates from DERMS (simulated ADMS ingest endpoint).
    In production: validate CIM DERGroupStatusInfo payload.
    """
    return {
        "status": "accepted",
        "received_assets": len(payload.get("assets", [])),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/scada/readings/{deployment_id}")
async def get_scada_readings(deployment_id: str) -> dict:
    """Return simulated SCADA interval readings for all nodes."""
    from app.grid.simulation import get_grid_state

    state = get_grid_state(deployment_id.lower())
    nodes = state.get("nodes", [])

    readings = []
    for node in nodes:
        readings.append({
            "node_id": node.get("node_id"),
            "timestamp": state.get("timestamp"),
            "active_power_kw": round(
                (node.get("current_loading_pct", 0) / 100.0)
                * (node.get("hosting_capacity_kw", 0) or 100.0),
                1,
            ),
            "voltage_v": node.get("voltage_l1_v"),
            "loading_pct": node.get("current_loading_pct"),
        })

    return {
        "deployment_id": deployment_id.lower(),
        "reading_count": len(readings),
        "readings": readings,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
