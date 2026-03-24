"""ORM models for LV Network — LV Feeders and LV Buses."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.utils import new_uuid, utcnow


class LVFeeder(Base):
    """
    A low-voltage feeder behind a distribution transformer.
    Represents the LV cable network supplying customers from a DT.
    """

    __tablename__ = "lv_feeders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # The DT this feeder hangs off — FK-like ref to GridNode.node_id
    dt_node_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # LV network voltage — UK: 400V 3-phase / 230V single-phase
    voltage_v: Mapped[float] = mapped_column(Float, nullable=False, default=400.0)

    # Total feeder route length in metres
    length_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    customer_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Centroid of the feeder geographic extent
    lat_centroid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng_centroid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # OSM data — often absent for underground LV cables
    osm_way_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON list of OSM way IDs
    route_geojson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # GeoJSON LineString

    # Power flow results cached from last run
    last_pf_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pf_result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-serialised PowerFlowResult

    # Ratings
    rated_kva: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:
        return f"<LVFeeder id={self.id} dt={self.dt_node_id} name={self.name}>"


class LVBus(Base):
    """
    A connection point on an LV feeder — customer meter, junction,
    transformer secondary, or smart meter point.
    """

    __tablename__ = "lv_buses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # Parent feeder
    lv_feeder_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Human-readable or OSM-derived reference, e.g. "BUS-001"
    bus_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # CUSTOMER / JUNCTION / TRANSFORMER_SECONDARY / METER
    bus_type: Mapped[str] = mapped_column(String(32), nullable=False, default="CUSTOMER")

    # Geography
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    osm_node_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Electrical phase configuration
    phase: Mapped[str] = mapped_column(String(8), nullable=False, default="3PH")  # 3PH / L1 / L2 / L3

    # Net load/generation at this bus — positive = load, negative = generation
    p_kw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    q_kvar: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Power flow result — updated after each run
    v_pu: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    v_v: Mapped[float] = mapped_column(Float, nullable=False, default=230.0)

    # NORMAL / HIGH / LOW / CRITICAL
    voltage_status: Mapped[str] = mapped_column(String(16), nullable=False, default="NORMAL")

    # Linked DERAsset if any
    asset_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    def __repr__(self) -> str:
        return f"<LVBus id={self.id} ref={self.bus_ref} feeder={self.lv_feeder_id}>"


class DynamicOESlot(Base):
    """
    A single 30-minute Operating Envelope slot derived from DistFlow power flow.

    source values:
      DISTFLOW   — computed from time-series DistFlow (physics-based)
      ARITHMETIC — fallback: rated_kva - forecast_load + forecast_generation
    """

    __tablename__ = "dynamic_oe_slots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cmz_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    feeder_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    asset_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # OE limits derived from power flow
    export_max_kw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    import_max_kw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Power flow results for this slot
    min_voltage_pu: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_voltage_pu: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_branch_loading_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    forecast_load_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    forecast_gen_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    headroom_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    source: Mapped[str] = mapped_column(String(16), nullable=False, default="ARITHMETIC")
    pf_converged: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    def __repr__(self) -> str:
        return f"<DynamicOESlot cmz={self.cmz_id} start={self.slot_start} export={self.export_max_kw}kW>"
