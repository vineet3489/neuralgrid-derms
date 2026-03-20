"""Optimization API endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.deps import CurrentUserDep, DBDep, DeploymentDep
from app.optimization.service import (
    calculate_operating_envelopes,
    optimize_dr_dispatch,
    optimize_p2p_matching,
    run_optimization_scenario,
)

router = APIRouter(prefix="/api/v1/optimization", tags=["optimization"])


# ── Request models ────────────────────────────────────────────────────────────

class DRDispatchRequest(BaseModel):
    target_kw: float
    cmz_id: Optional[str] = None
    event_type: str = "DR_CURTAILMENT"
    constraints: Optional[Dict[str, Any]] = None


class P2PClearingRequest(BaseModel):
    sellers: Optional[List[dict]] = None
    buyers: Optional[List[dict]] = None


class DOECalculateRequest(BaseModel):
    cmz_id: Optional[str] = None


class ScenarioRequest(BaseModel):
    scenario_type: str
    params: Dict[str, Any] = {}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/dr-dispatch")
async def dr_dispatch_optimization(
    body: DRDispatchRequest,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Optimize DR dispatch for a target kW — returns greedy asset selection plan."""
    from app.grid.simulation import get_grid_state

    state = get_grid_state(deployment_id)
    assets = state.get("assets", [])

    if body.cmz_id:
        # Filter assets to the CMZ using node-to-CMZ lookup
        nodes = {n["node_id"]: n["cmz_id"] for n in state.get("nodes", [])}
        assets = [
            a for a in assets
            if nodes.get(a.get("feeder_id") or a.get("dt_id", "")) == body.cmz_id
        ]

    result = optimize_dr_dispatch(assets, body.target_kw, body.constraints)

    # Optionally enrich with LLM recommendation
    try:
        from app.integrations.llm.claude import optimize_with_llm

        scenario = {
            "target_kw": body.target_kw,
            "duration_minutes": 30,
            "available_assets": [
                {"id": a.get("id"), "type": a.get("type"), "capacity_kw": a.get("capacity_kw")}
                for a in assets[:10]
            ],
            "constraint_type": body.event_type,
        }
        llm_rec = await optimize_with_llm(scenario, deployment_id)
        result["ai_recommendation"] = llm_rec
    except Exception:
        pass

    return result


@router.post("/p2p-clearing")
async def p2p_market_clearing(
    body: P2PClearingRequest,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Run P2P double-auction market clearing."""
    from app.grid.simulation import get_grid_state
    import random

    state = get_grid_state(deployment_id)
    assets = state.get("assets", [])

    sellers = body.sellers
    buyers = body.buyers

    if sellers is None or buyers is None:
        # Auto-build from live grid state
        sellers = [
            {
                "asset_id": a["id"],
                "max_export_kw": abs(a.get("current_kw", 0.0)),
                "ask_price_minor_per_kwh": random.randint(5, 12),
            }
            for a in assets
            if a.get("type") in ("PV", "WIND", "V2G")
            and (a.get("current_kw") or 0.0) < 0.0
        ]
        buyers = [
            {
                "counterparty_id": a["id"],
                "max_import_kw": a.get("capacity_kw", 0.0) * 0.5,
                "bid_price_minor_per_kwh": random.randint(8, 18),
            }
            for a in assets
            if a.get("type") in ("V1G", "HEAT_PUMP", "BESS")
            and (a.get("current_kw") or 0.0) >= 0.0
        ]

    return optimize_p2p_matching(sellers or [], buyers or [])


@router.post("/doe-calculate")
async def calculate_doe(
    body: DOECalculateRequest,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Calculate Dynamic Operating Envelopes for all assets in a CMZ."""
    from app.grid.simulation import get_grid_state

    state = get_grid_state(deployment_id)
    nodes = state.get("nodes", [])
    assets = state.get("assets", [])

    if body.cmz_id:
        nodes = [n for n in nodes if n.get("cmz_id") == body.cmz_id]

    does = calculate_operating_envelopes(nodes, assets)
    return {
        "deployment_id": deployment_id,
        "cmz_id": body.cmz_id,
        "asset_count": len(does),
        "doe_values": does,
    }


@router.get("/recommendations")
async def get_optimization_recommendations(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """LLM-powered optimization recommendations based on current grid state."""
    from app.grid.simulation import get_grid_state

    state = get_grid_state(deployment_id)

    try:
        from app.integrations.llm.claude import get_grid_insight

        insight = await get_grid_insight(deployment_id, state)
        return {
            "deployment_id": deployment_id,
            "recommendations": insight,
            "grid_snapshot": {
                "total_gen_kw": state.get("total_gen_kw"),
                "total_load_kw": state.get("total_load_kw"),
                "net_kw": state.get("net_kw"),
                "assets_curtailed": state.get("assets_curtailed"),
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not generate recommendations: {exc}")


@router.post("/scenario")
async def run_scenario(
    body: ScenarioRequest,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Run an arbitrary optimization scenario."""
    try:
        result = await run_optimization_scenario(db, deployment_id, body.scenario_type, body.params)
        return {"scenario_type": body.scenario_type, "deployment_id": deployment_id, "result": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
