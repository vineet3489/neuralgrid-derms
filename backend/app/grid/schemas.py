"""Pydantic schemas for the Grid module."""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ── CMZ ─────────────────────────────────────────────────────────────────────

class CMZBase(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    topology_type: str  # ISLAND / RADIAL / MESHED
    max_import_kw: float
    max_export_kw: float
    voltage_nominal_v: float = 230.0
    feeder_ids: Optional[str] = None  # JSON string


class CMZCreate(CMZBase):
    deployment_id: str


class CMZRead(CMZBase):
    id: str
    deployment_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── GridNode ─────────────────────────────────────────────────────────────────

class GridNodeBase(BaseModel):
    node_id: str
    cmz_id: str
    node_type: str  # FEEDER / DISTRIBUTION_TRANSFORMER / SUBSTATION
    name: str
    voltage_kv: Optional[float] = None
    rated_mva: Optional[float] = None
    rated_kva: Optional[float] = None
    hosting_capacity_kw: float = 0.0
    lat: Optional[float] = None
    lng: Optional[float] = None
    cim_id: Optional[str] = None


class GridNodeCreate(GridNodeBase):
    deployment_id: str


class GridNodeRead(GridNodeBase):
    id: str
    deployment_id: str
    current_loading_pct: float
    voltage_l1_v: Optional[float] = None
    voltage_l2_v: Optional[float] = None
    voltage_l3_v: Optional[float] = None
    used_capacity_kw: float
    created_at: datetime

    model_config = {"from_attributes": True}


# ── GridAlert ────────────────────────────────────────────────────────────────

class GridAlertBase(BaseModel):
    node_id: Optional[str] = None
    asset_id: Optional[str] = None
    alert_type: str
    severity: str
    message: str
    meta: Optional[str] = None  # JSON string


class GridAlertCreate(GridAlertBase):
    deployment_id: str


class GridAlertRead(GridAlertBase):
    id: str
    deployment_id: str
    is_acknowledged: bool
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class GridAlertAcknowledge(BaseModel):
    acknowledged_by: str


# ── GridState (real-time snapshot) ──────────────────────────────────────────

class GridAssetSnapshot(BaseModel):
    id: str
    asset_ref: str
    name: str
    type: str
    status: str
    feeder_id: Optional[str] = None
    dt_id: Optional[str] = None
    current_kw: Optional[float] = None
    capacity_kw: float
    current_soc_pct: Optional[float] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    doe_export_max_kw: Optional[float] = None
    doe_import_max_kw: Optional[float] = None


class GridNodeSnapshot(BaseModel):
    node_id: str
    node_type: str
    name: str
    cmz_id: str
    current_loading_pct: float
    voltage_l1_v: Optional[float] = None
    voltage_l2_v: Optional[float] = None
    voltage_l3_v: Optional[float] = None
    hosting_capacity_kw: float
    used_capacity_kw: float
    lat: Optional[float] = None
    lng: Optional[float] = None


class GridState(BaseModel):
    deployment_id: str
    timestamp: str
    local_hour: float
    solar_factor: float
    load_factor: float
    total_gen_kw: float
    total_load_kw: float
    net_kw: float
    assets_online: int
    assets_curtailed: int
    assets_offline: int
    nodes: List[GridNodeSnapshot] = []
    assets: List[GridAssetSnapshot] = []


# ── GridConstraint ───────────────────────────────────────────────────────────

class GridConstraint(BaseModel):
    node_id: str
    node_name: str
    constraint_type: str  # OVERLOAD / OVERVOLTAGE / UNDERVOLTAGE / HOSTING_CAPACITY
    current_value: float
    threshold: float
    severity: str
    suggested_action: str


# ── Hosting Capacity ─────────────────────────────────────────────────────────

class HostingCapacitySummary(BaseModel):
    cmz_id: str
    cmz_name: str
    total_capacity_kw: float
    used_capacity_kw: float
    available_kw: float
    utilisation_pct: float
    nodes: List[dict] = []


# ── Dashboard ────────────────────────────────────────────────────────────────

class DashboardKPIs(BaseModel):
    total_gen_kw: float
    total_load_kw: float
    net_kw: float
    assets_online: int
    assets_curtailed: int
    assets_offline: int
    alerts_active: int
    alerts_critical: int
    renewable_penetration_pct: float


class DashboardResponse(BaseModel):
    deployment_id: str
    timestamp: str
    kpis: DashboardKPIs
    grid_state: Optional[dict] = None
    active_alerts: List[dict] = []
    recent_events: List[dict] = []
    forecast_24h: Optional[dict] = None
