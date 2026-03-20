"""
Optimization module — rule-based greedy algorithms for demo.

For production: replace inner logic with scipy.optimize LP, PuLP,
or a commercial solver (Gurobi, CPLEX) accessed via REST.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


# ── DR dispatch optimization ──────────────────────────────────────────────────

def optimize_dr_dispatch(
    assets: list,
    target_kw: float,
    constraints: Optional[dict] = None,
) -> dict:
    """
    Greedy dispatch optimization — fills target_kw from available DER assets.

    Priority order: V2G → BESS → V1G → HEAT_PUMP → PV (curtailment).

    Returns:
        {
            "feasible": bool,
            "total_dispatched_kw": float,
            "gap_kw": float,
            "dispatch_plan": [...],
            "cost_estimate_minor": int,
        }
    """
    if constraints is None:
        constraints = {}

    MIN_KW = 1.0
    TYPE_PRIORITY = {"V2G": 0, "BESS": 1, "V1G": 2, "HEAT_PUMP": 3, "PV": 4}

    candidates = [
        a for a in assets
        if isinstance(a, dict)
        and a.get("status") in ("ONLINE", "CURTAILED")
        and a.get("capacity_kw", 0) >= MIN_KW
    ]
    candidates.sort(key=lambda a: TYPE_PRIORITY.get(a.get("type", ""), 99))

    plan: List[dict] = []
    remaining = target_kw
    cost_minor = 0

    for asset in candidates:
        if remaining <= 0.0:
            break
        atype = asset.get("type", "")
        cap = asset.get("capacity_kw", 0.0)
        current_kw = asset.get("current_kw", 0.0) or 0.0
        soc = asset.get("current_soc_pct", 50.0) or 50.0

        if atype == "V2G":
            available = cap * 0.9
        elif atype == "BESS" and soc > 20.0:
            available = cap * ((soc - 10.0) / 100.0)
        elif atype == "V1G":
            available = max(0.0, current_kw * 0.8)
        elif atype == "HEAT_PUMP":
            available = max(0.0, current_kw * 0.5)
        elif atype == "PV":
            available = abs(current_kw)
        else:
            available = 0.0

        if available < MIN_KW:
            continue

        dispatch_kw = min(available, remaining)

        # Cost estimate: BESS/V2G are cheapest, PV curtailment has opportunity cost
        unit_rate = {"V2G": 8, "BESS": 10, "V1G": 5, "HEAT_PUMP": 3, "PV": 15}.get(atype, 10)
        cost_minor += int(dispatch_kw * unit_rate)

        plan.append({
            "asset_id": asset.get("id", ""),
            "asset_name": asset.get("name", ""),
            "dispatch_kw": round(dispatch_kw, 2),
            "asset_type": atype,
        })
        remaining -= dispatch_kw

    total_dispatched = target_kw - remaining

    return {
        "feasible": remaining <= 0.05,
        "total_dispatched_kw": round(total_dispatched, 2),
        "gap_kw": round(max(0.0, remaining), 2),
        "dispatch_plan": plan,
        "cost_estimate_minor": cost_minor,
    }


# ── P2P market clearing ───────────────────────────────────────────────────────

def optimize_p2p_matching(sellers: list, buyers: list) -> dict:
    """
    Double-auction P2P market clearing.

    Sellers: [{asset_id, max_export_kw, ask_price_minor_per_kwh}]
    Buyers:  [{counterparty_id, max_import_kw, bid_price_minor_per_kwh}]

    Sorts sellers ascending (cheapest first) and buyers descending (highest bid first),
    matches at mid-point clearing price of last matched pair.

    Returns:
        {
            "clearing_price_minor": int,
            "total_matched_kw": float,
            "matches": [...],
            "unmatched_sellers": [...],
            "unmatched_buyers": [...],
        }
    """
    # Sort
    sorted_sellers = sorted(sellers, key=lambda s: s.get("ask_price_minor_per_kwh", 999999))
    sorted_buyers = sorted(buyers, key=lambda b: b.get("bid_price_minor_per_kwh", 0), reverse=True)

    matches: List[dict] = []
    unmatched_sellers = []
    unmatched_buyers = []
    clearing_price_minor = 0
    total_matched = 0.0

    si = 0
    bi = 0
    seller_remaining = [s.get("max_export_kw", 0.0) for s in sorted_sellers]
    buyer_remaining = [b.get("max_import_kw", 0.0) for b in sorted_buyers]

    while si < len(sorted_sellers) and bi < len(sorted_buyers):
        seller = sorted_sellers[si]
        buyer = sorted_buyers[bi]

        ask = seller.get("ask_price_minor_per_kwh", 0)
        bid = buyer.get("bid_price_minor_per_kwh", 0)

        if bid < ask:
            # No more profitable matches
            break

        # Match at mid-price
        price = (ask + bid) // 2
        matched_kw = min(seller_remaining[si], buyer_remaining[bi])

        if matched_kw > 0.0:
            matches.append({
                "seller_asset_id": seller.get("asset_id", ""),
                "buyer_id": buyer.get("counterparty_id", ""),
                "matched_kw": round(matched_kw, 2),
                "price_minor": price,
            })
            total_matched += matched_kw
            clearing_price_minor = price
            seller_remaining[si] -= matched_kw
            buyer_remaining[bi] -= matched_kw

        if seller_remaining[si] <= 0.01:
            si += 1
        if buyer_remaining[bi] <= 0.01:
            bi += 1

    # Collect unmatched
    for i in range(si, len(sorted_sellers)):
        if seller_remaining[i] > 0.01:
            unmatched_sellers.append({**sorted_sellers[i], "remaining_kw": round(seller_remaining[i], 2)})
    for i in range(bi, len(sorted_buyers)):
        if buyer_remaining[i] > 0.01:
            unmatched_buyers.append({**sorted_buyers[i], "remaining_kw": round(buyer_remaining[i], 2)})

    return {
        "clearing_price_minor": clearing_price_minor,
        "total_matched_kw": round(total_matched, 2),
        "matches": matches,
        "unmatched_sellers": unmatched_sellers,
        "unmatched_buyers": unmatched_buyers,
    }


# ── Operating Envelope calculation ────────────────────────────────────────────

def calculate_operating_envelopes(
    nodes: list,
    assets: list,
    constraints: Optional[dict] = None,
) -> Dict[str, dict]:
    """
    Calculate Dynamic Operating Envelopes (DOEs) for assets in a CMZ.

    For each DT node:
      available_headroom = hosting_capacity_kw - current_used_kw
      Each asset gets a proportional share based on nameplate capacity.

    Returns: {asset_id: {"export_max_kw": float, "import_max_kw": float}}
    """
    if constraints is None:
        constraints = {}

    # Build node map
    node_map = {n.get("node_id") or n.get("id", ""): n for n in nodes}

    # Group assets by DT
    dt_assets: Dict[str, list] = {}
    for asset in assets:
        dt_id = asset.get("dt_id") or asset.get("feeder_id", "")
        if dt_id:
            dt_assets.setdefault(dt_id, []).append(asset)

    result: Dict[str, dict] = {}

    for dt_id, dt_asset_list in dt_assets.items():
        node = node_map.get(dt_id)
        if not node:
            continue

        hosting_cap = node.get("hosting_capacity_kw", 0.0)
        used_cap = node.get("used_capacity_kw", 0.0)
        headroom = max(0.0, hosting_cap - used_cap)

        # Total nameplate of generators under this DT
        total_gen_cap = sum(
            a.get("capacity_kw", 0.0)
            for a in dt_asset_list
            if a.get("type") in ("PV", "WIND", "BESS", "V2G")
        )

        for asset in dt_asset_list:
            cap = asset.get("capacity_kw", 0.0)
            atype = asset.get("type", "")
            aid = asset.get("id", "")

            if atype in ("PV", "WIND"):
                if total_gen_cap > 0.0:
                    share = cap / total_gen_cap
                    export_max = round(min(cap, headroom * share), 2)
                else:
                    export_max = round(cap, 2)
                result[aid] = {
                    "export_max_kw": export_max,
                    "import_max_kw": 0.0,
                }
            elif atype in ("BESS", "V2G"):
                # BESS/V2G can both export (discharge) and import (charge)
                result[aid] = {
                    "export_max_kw": round(cap * 0.9, 2),
                    "import_max_kw": round(cap, 2),
                }
            elif atype in ("V1G", "HEAT_PUMP", "INDUSTRIAL_LOAD", "RESIDENTIAL_LOAD"):
                # Loads only import
                result[aid] = {
                    "export_max_kw": 0.0,
                    "import_max_kw": round(cap, 2),
                }
            else:
                result[aid] = {
                    "export_max_kw": round(cap, 2),
                    "import_max_kw": round(cap, 2),
                }

    return result


# ── Optimization scenario runner ──────────────────────────────────────────────

async def run_optimization_scenario(
    db,
    deployment_id: str,
    scenario_type: str,
    params: dict,
) -> dict:
    """
    Run an optimization scenario and return results.

    scenario_type: DR_DISPATCH / P2P_CLEARING / DOE_CALCULATION / VPP_SCHEDULE
    """
    from app.grid.simulation import get_grid_state

    state = get_grid_state(deployment_id)
    assets = state.get("assets", [])
    nodes = state.get("nodes", [])

    if scenario_type == "DR_DISPATCH":
        target_kw = params.get("target_kw", 50.0)
        return optimize_dr_dispatch(assets, target_kw, params.get("constraints"))

    elif scenario_type == "P2P_CLEARING":
        sellers = params.get("sellers", [])
        buyers = params.get("buyers", [])
        if not sellers and not buyers:
            # Auto-build from grid state
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
        return optimize_p2p_matching(sellers, buyers)

    elif scenario_type == "DOE_CALCULATION":
        cmz_id = params.get("cmz_id")
        filtered_nodes = [n for n in nodes if not cmz_id or n.get("cmz_id") == cmz_id]
        filtered_assets = [a for a in assets if not cmz_id or True]  # TODO: filter by CMZ
        return {
            "doe_values": calculate_operating_envelopes(filtered_nodes, filtered_assets),
            "cmz_id": cmz_id,
            "asset_count": len(filtered_assets),
        }

    elif scenario_type == "VPP_SCHEDULE":
        # VPP schedule: stack all available generation/flex into an 8-hour schedule
        schedule_hours = params.get("hours", 8)
        target_kw = params.get("target_kw", 100.0)
        schedule = []
        current_kw_available = sum(
            abs(a.get("current_kw", 0.0))
            for a in assets
            if a.get("type") in ("PV", "WIND", "BESS", "V2G")
            and (a.get("current_kw") or 0.0) < 0.0
        )
        for hour in range(schedule_hours):
            # Simulate declining availability as SoC depletes
            avail = max(0.0, current_kw_available * (1.0 - hour * 0.05) * random.uniform(0.9, 1.0))
            schedule.append({
                "hour": hour,
                "available_kw": round(avail, 1),
                "committed_kw": round(min(avail, target_kw), 1),
            })
        return {"schedule": schedule, "target_kw": target_kw}

    else:
        raise ValueError(f"Unknown scenario_type: {scenario_type}")
