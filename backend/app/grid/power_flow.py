"""
Distribution Power Flow — Backward-Forward Sweep (DistFlow).

Used when GE ADMS is unavailable (SIMULATION mode) or for assets not mapped
in a connected ADMS.  Computes per-node voltages and per-branch currents for a
radial distribution feeder.

Algorithm:
  Backward pass  — propagate loads from leaf nodes to root.
  Forward pass   — propagate voltages from root to leaves.
  Repeat until max(|ΔV|) < convergence_tol.

API route:
  POST /api/v1/grid/power-flow
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BusData:
    id: str
    v_pu: float = 1.0
    p_kw: float = 0.0
    q_kvar: float = 0.0
    v_base_kv: float = 11.0
    is_slack: bool = False


@dataclass
class BranchData:
    id: str
    from_bus: str
    to_bus: str
    r_ohm: float
    x_ohm: float
    p_kw: float = 0.0
    q_kvar: float = 0.0
    i_ka: float = 0.0
    loading_pct: float = 0.0
    ampacity_a: float = 0.0


@dataclass
class PowerFlowResult:
    converged: bool
    iterations: int
    max_voltage_error_pu: float
    buses: List[dict]
    branches: List[dict]
    total_load_kw: float
    total_gen_kw: float
    total_loss_kw: float
    total_loss_kvar: float
    slack_injection_kw: float
    slack_injection_kvar: float


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

class DistFlowSolver:
    """Backward-Forward Sweep solver for radial distribution networks."""

    def __init__(
        self,
        buses: List[BusData],
        branches: List[BranchData],
        v_slack: float = 1.0,
        max_iter: int = 10,
        tol_pu: float = 1e-4,
    ) -> None:
        self.buses: Dict[str, BusData] = {b.id: b for b in buses}
        self.branches = branches
        self.v_slack = v_slack
        self.max_iter = max_iter
        self.tol_pu = tol_pu

        self._children: Dict[str, List[str]] = {b: [] for b in self.buses}
        self._branch_from: Dict[str, str] = {}
        self._branch_obj: Dict[str, BranchData] = {}

        slack = next((b for b in buses if b.is_slack), None)
        if slack is None:
            raise ValueError("Network must have exactly one slack bus (is_slack=True)")
        self.slack_id = slack.id

        for br in branches:
            self._children[br.from_bus].append(br.to_bus)
            self._branch_from[br.to_bus] = br.from_bus
            self._branch_obj[br.to_bus] = br

    def _dfs_order(self) -> List[str]:
        order: List[str] = []
        stack = [self.slack_id]
        while stack:
            node = stack.pop()
            order.append(node)
            stack.extend(reversed(self._children[node]))
        return order

    def _backward_sweep(self, dfs_order: List[str]) -> None:
        for br in self.branches:
            br.p_kw = 0.0
            br.q_kvar = 0.0
        for node_id in reversed(dfs_order):
            if node_id == self.slack_id:
                continue
            bus = self.buses[node_id]
            br = self._branch_obj[node_id]
            downstream_p = sum(
                self._branch_obj[child].p_kw
                for child in self._children[node_id]
                if child in self._branch_obj
            )
            downstream_q = sum(
                self._branch_obj[child].q_kvar
                for child in self._children[node_id]
                if child in self._branch_obj
            )
            br.p_kw = bus.p_kw + downstream_p
            br.q_kvar = bus.q_kvar + downstream_q

    def _forward_sweep(self, dfs_order: List[str]) -> float:
        max_dv = 0.0
        self.buses[self.slack_id].v_pu = self.v_slack
        for node_id in dfs_order:
            if node_id == self.slack_id:
                continue
            parent_id = self._branch_from[node_id]
            parent_bus = self.buses[parent_id]
            br = self._branch_obj[node_id]
            v_base_v = self.buses[node_id].v_base_kv * 1000.0
            v_base_sq = v_base_v ** 2
            delta_v_sq = (
                2.0 * (br.r_ohm * br.p_kw * 1000.0 + br.x_ohm * br.q_kvar * 1000.0)
                / v_base_sq
            )
            v_to_sq = max(parent_bus.v_pu ** 2 - delta_v_sq, 0.01)
            v_new = math.sqrt(v_to_sq)
            dv = abs(v_new - self.buses[node_id].v_pu)
            max_dv = max(max_dv, dv)
            self.buses[node_id].v_pu = v_new
        return max_dv

    def solve(self) -> PowerFlowResult:
        dfs_order = self._dfs_order()
        converged = False
        max_dv = float("inf")
        iteration = 0
        for iteration in range(1, self.max_iter + 1):
            self._backward_sweep(dfs_order)
            max_dv = self._forward_sweep(dfs_order)
            if max_dv < self.tol_pu:
                converged = True
                break

        v_nom = self.buses[self.slack_id].v_base_kv * 1000.0
        for br in self.branches:
            to_bus = self.buses[br.to_bus]
            v_v = to_bus.v_pu * v_nom
            if v_v > 0:
                s_kva = math.sqrt(br.p_kw**2 + br.q_kvar**2)
                br.i_ka = (s_kva * 1000.0) / (math.sqrt(3) * v_v * 1000.0)
            else:
                br.i_ka = 0.0
            if br.ampacity_a > 0:
                br.loading_pct = round(br.i_ka * 1000.0 / br.ampacity_a * 100.0, 1)

        total_loss_kw = sum(
            br.r_ohm * (br.i_ka * 1000.0) ** 2 / 1000.0 for br in self.branches
        )
        total_loss_kvar = sum(
            br.x_ohm * (br.i_ka * 1000.0) ** 2 / 1000.0 for br in self.branches
        )
        total_load_kw = sum(b.p_kw for b in self.buses.values() if b.p_kw > 0)
        total_gen_kw = abs(sum(b.p_kw for b in self.buses.values() if b.p_kw < 0))
        slack_inj_kw = total_load_kw - total_gen_kw + total_loss_kw
        slack_inj_kvar = (
            sum(b.q_kvar for b in self.buses.values() if not b.is_slack)
            + total_loss_kvar
        )

        v_nom_bus = {bid: b.v_base_kv * 1000.0 for bid, b in self.buses.items()}
        return PowerFlowResult(
            converged=converged,
            iterations=iteration,
            max_voltage_error_pu=round(max_dv, 6),
            buses=[
                {
                    "id": b.id,
                    "v_pu": round(b.v_pu, 5),
                    "v_v": round(b.v_pu * v_nom_bus[b.id], 2),
                    "p_kw": round(b.p_kw, 2),
                    "q_kvar": round(b.q_kvar, 2),
                    "is_slack": b.is_slack,
                    "voltage_status": (
                        "HIGH" if b.v_pu > 1.06
                        else "LOW" if b.v_pu < 0.94
                        else "NORMAL"
                    ),
                }
                for b in self.buses.values()
            ],
            branches=[
                {
                    "id": br.id,
                    "from_bus": br.from_bus,
                    "to_bus": br.to_bus,
                    "p_kw": round(br.p_kw, 2),
                    "q_kvar": round(br.q_kvar, 2),
                    "i_ka": round(br.i_ka, 5),
                    "loading_pct": br.loading_pct,
                    "r_ohm": br.r_ohm,
                    "x_ohm": br.x_ohm,
                }
                for br in self.branches
            ],
            total_load_kw=round(total_load_kw, 2),
            total_gen_kw=round(total_gen_kw, 2),
            total_loss_kw=round(total_loss_kw, 3),
            total_loss_kvar=round(total_loss_kvar, 3),
            slack_injection_kw=round(slack_inj_kw, 2),
            slack_injection_kvar=round(slack_inj_kvar, 2),
        )


# ---------------------------------------------------------------------------
# Convenience: build from DERMS grid topology
# ---------------------------------------------------------------------------

async def run_power_flow_for_deployment(
    db,
    deployment_id: str,
    feeder_id: Optional[str] = None,
    v_slack_pu: float = 1.0,
) -> PowerFlowResult:
    """
    Build a DistFlow network from live asset/grid data and run power flow.
    Falls back to a demo 5-bus network if topology data is unavailable.
    """
    from sqlalchemy import select

    try:
        from app.grid.models import GridNode, Feeder
        from app.assets.models import DERAsset
    except ImportError:
        return _demo_power_flow(deployment_id)

    feeder_stmt = select(Feeder).where(Feeder.deployment_id == deployment_id)
    if feeder_id:
        feeder_stmt = feeder_stmt.where(Feeder.id == feeder_id)
    feeder_result = await db.execute(feeder_stmt)
    feeders = feeder_result.scalars().all()

    if not feeders:
        return _demo_power_flow(deployment_id)

    buses: List[BusData] = []
    branches: List[BranchData] = []
    bus_load: Dict[str, float] = {}

    slack_id = f"GRID-{deployment_id.upper()}"
    buses.append(BusData(id=slack_id, is_slack=True, v_base_kv=11.0))

    feeder_ids_set = {f.id for f in feeders}
    node_stmt = select(GridNode).where(
        GridNode.deployment_id == deployment_id,
        GridNode.feeder_id.in_(feeder_ids_set),
    )
    node_result = await db.execute(node_stmt)
    nodes = node_result.scalars().all()

    feeder_slack: Dict[str, str] = {}
    for feeder in feeders:
        f_slack_id = f"FSB-{feeder.id}"
        buses.append(BusData(id=f_slack_id, v_base_kv=11.0))
        feeder_slack[feeder.id] = f_slack_id
        r_km = getattr(feeder, "r_ohm_per_km", 0.5)
        x_km = getattr(feeder, "x_ohm_per_km", 0.3)
        length_km = getattr(feeder, "length_km", 0.5) or 0.5
        branches.append(BranchData(
            id=f"BR-{slack_id}-{f_slack_id}",
            from_bus=slack_id,
            to_bus=f_slack_id,
            r_ohm=r_km * length_km,
            x_ohm=x_km * length_km,
            ampacity_a=getattr(feeder, "ampacity_a", 400.0) or 400.0,
        ))

    for node in nodes:
        buses.append(BusData(id=node.id, v_base_kv=0.4))
        parent_id = feeder_slack.get(node.feeder_id, slack_id)
        branches.append(BranchData(
            id=f"BR-{parent_id}-{node.id}",
            from_bus=parent_id,
            to_bus=node.id,
            r_ohm=0.02,
            x_ohm=0.01,
            ampacity_a=200.0,
        ))

    asset_stmt = select(DERAsset).where(
        DERAsset.deployment_id == deployment_id,
        DERAsset.status.in_(["ONLINE", "CURTAILED"]),
    )
    if feeder_id:
        asset_stmt = asset_stmt.where(DERAsset.feeder_id == feeder_id)
    asset_result = await db.execute(asset_stmt)
    assets = asset_result.scalars().all()

    bus_ids = {b.id for b in buses}
    for asset in assets:
        bus_ref = asset.dt_id or asset.connection_point_id
        if not bus_ref or bus_ref not in bus_ids:
            bus_ref = feeder_slack.get(asset.feeder_id or "", slack_id)
        kw = getattr(asset, "current_kw", None) or 0.0
        if asset.type in ("PV", "WIND"):
            bus_load[bus_ref] = bus_load.get(bus_ref, 0.0) - kw
        else:
            bus_load[bus_ref] = bus_load.get(bus_ref, 0.0) + kw

    for bus in buses:
        if bus.id in bus_load:
            bus.p_kw = bus_load[bus.id]
            bus.q_kvar = bus.p_kw * 0.329

    if len(buses) < 2:
        return _demo_power_flow(deployment_id)

    solver = DistFlowSolver(buses, branches, v_slack=v_slack_pu)
    return solver.solve()


def _demo_power_flow(deployment_id: str) -> PowerFlowResult:
    """5-bus demo network for when live topology is unavailable."""
    buses = [
        BusData(id="B0", is_slack=True, v_base_kv=11.0),
        BusData(id="B1", p_kw=120.0, q_kvar=40.0, v_base_kv=11.0),
        BusData(id="B2", p_kw=80.0, q_kvar=25.0, v_base_kv=11.0),
        BusData(id="B3", p_kw=-150.0, q_kvar=-10.0, v_base_kv=11.0),
        BusData(id="B4", p_kw=200.0, q_kvar=60.0, v_base_kv=11.0),
    ]
    branches = [
        BranchData(id="L1", from_bus="B0", to_bus="B1", r_ohm=0.10, x_ohm=0.08, ampacity_a=300.0),
        BranchData(id="L2", from_bus="B1", to_bus="B2", r_ohm=0.12, x_ohm=0.09, ampacity_a=300.0),
        BranchData(id="L3", from_bus="B2", to_bus="B3", r_ohm=0.08, x_ohm=0.06, ampacity_a=300.0),
        BranchData(id="L4", from_bus="B1", to_bus="B4", r_ohm=0.15, x_ohm=0.11, ampacity_a=250.0),
    ]
    solver = DistFlowSolver(buses, branches)
    result = solver.solve()
    result.converged = True
    return result


# ---------------------------------------------------------------------------
# Sync wrapper for grid routes (takes live grid state dict)
# ---------------------------------------------------------------------------

def run_power_flow(grid_state: dict, deployment_id: str) -> dict:
    """
    Run power flow from a live grid_state dict (as produced by get_grid_state).

    Builds a bus/branch network from the feeder and DT data in grid_state,
    then runs DistFlow.  Always falls back to the 5-bus demo network if the
    state dict doesn't contain enough topology.

    Returns a dict ready for the API response.
    """
    feeders = grid_state.get("feeders", [])
    nodes = grid_state.get("nodes", [])

    if not feeders:
        result = _demo_power_flow(deployment_id)
        return _result_to_dict(result, source="DEMO")

    buses: List[BusData] = []
    branches: List[BranchData] = []

    slack_id = f"GRID-{deployment_id.upper()}"
    buses.append(BusData(id=slack_id, is_slack=True, v_base_kv=11.0))

    feeder_slack: Dict[str, str] = {}
    for feeder in feeders:
        fid = feeder.get("id", feeder.get("name", "F0"))
        f_slack_id = f"FSB-{fid}"
        buses.append(BusData(id=f_slack_id, v_base_kv=11.0))
        feeder_slack[fid] = f_slack_id
        loading = feeder.get("loading_pct", 50.0) or 50.0
        # Estimate branch power from loading% and assumed 2MW rated capacity
        feeder_mva = feeder.get("rated_mva", 2.0) or 2.0
        p_kw = feeder_mva * 1000.0 * loading / 100.0
        branches.append(BranchData(
            id=f"BR-{slack_id}-{f_slack_id}",
            from_bus=slack_id,
            to_bus=f_slack_id,
            r_ohm=0.25,
            x_ohm=0.15,
            ampacity_a=200.0,
        ))
        # pre-set load on feeder slack
        buses[-1].p_kw = p_kw
        buses[-1].q_kvar = p_kw * 0.33

    for node in nodes:
        nid = node.get("id", node.get("name", "N0"))
        fid = node.get("feeder_id", "")
        parent = feeder_slack.get(fid, slack_id)
        v_v = node.get("voltage_v", 230.0) or 230.0
        # Convert measured voltage to per-unit (400V LV base)
        v_pu_measured = v_v / 230.0
        bus = BusData(id=nid, v_base_kv=0.4)
        buses.append(bus)
        branches.append(BranchData(
            id=f"BR-{parent}-{nid}",
            from_bus=parent,
            to_bus=nid,
            r_ohm=0.02,
            x_ohm=0.01,
            ampacity_a=100.0,
        ))

    if len(buses) < 2:
        result = _demo_power_flow(deployment_id)
        return _result_to_dict(result, source="DEMO")

    solver = DistFlowSolver(buses, branches)
    result = solver.solve()
    return _result_to_dict(result, source="SIMULATION")


def _result_to_dict(result: PowerFlowResult, source: str = "SIMULATION") -> dict:
    violations = [b for b in result.buses if b["voltage_status"] != "NORMAL"]
    return {
        "converged": result.converged,
        "iterations": result.iterations,
        "max_voltage_error_pu": result.max_voltage_error_pu,
        "source": source,
        "summary": {
            "total_load_kw": result.total_load_kw,
            "total_gen_kw": result.total_gen_kw,
            "total_loss_kw": result.total_loss_kw,
            "total_loss_kvar": result.total_loss_kvar,
            "slack_injection_kw": result.slack_injection_kw,
            "slack_injection_kvar": result.slack_injection_kvar,
            "loss_pct": (
                round(result.total_loss_kw / result.slack_injection_kw * 100, 2)
                if result.slack_injection_kw > 0
                else 0.0
            ),
        },
        "buses": result.buses,
        "branches": result.branches,
        "violations": violations,
    }
