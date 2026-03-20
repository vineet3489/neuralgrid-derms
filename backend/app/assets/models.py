"""ORM models for DER Assets, Telemetry, and DOE history."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.utils import new_uuid, utcnow


class AssetType(str, Enum):
    PV = "PV"
    BESS = "BESS"
    V1G = "V1G"
    V2G = "V2G"
    HEAT_PUMP = "HEAT_PUMP"
    INDUSTRIAL_LOAD = "INDUSTRIAL_LOAD"
    RESIDENTIAL_LOAD = "RESIDENTIAL_LOAD"
    HYBRID = "HYBRID"
    WIND = "WIND"


class AssetStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    CURTAILED = "CURTAILED"
    DEGRADED = "DEGRADED"
    FAULT = "FAULT"
    MAINTENANCE = "MAINTENANCE"
    DEREGISTERED = "DEREGISTERED"


class CommCapability(str, Enum):
    IEEE_2030_5 = "IEEE_2030_5"
    OPENADR_2B = "OPENADR_2B"
    OPENADR_2A = "OPENADR_2A"
    SCADA_MODBUS = "SCADA_MODBUS"
    OEM_CLOUD_API = "OEM_CLOUD_API"
    MQTT_GATEWAY = "MQTT_GATEWAY"
    MANUAL = "MANUAL"


class TelemetrySource(str, Enum):
    IOT_GATEWAY = "IOT_GATEWAY"
    OEM_CLOUD = "OEM_CLOUD"
    AMI_MDMS = "AMI_MDMS"
    SCADA = "SCADA"
    AGGREGATOR_REPORTED = "AGGREGATOR_REPORTED"
    MANUAL = "MANUAL"


class DERAsset(Base):
    __tablename__ = "der_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    counterparty_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("counterparties.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    asset_ref: Mapped[str] = mapped_column(String(32), nullable=False)   # e.g. AST-001
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OFFLINE")

    is_digital_twin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Grid topology
    connection_point_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    feeder_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    dt_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    phase: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")

    # Capacity
    capacity_kw: Mapped[float] = mapped_column(Float, nullable=False)
    capacity_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # BESS only

    # Communications
    comm_capability: Mapped[str] = mapped_column(String(32), nullable=False, default="MQTT_GATEWAY")
    comm_endpoint: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    telemetry_source: Mapped[str] = mapped_column(String(32), nullable=False, default="IOT_GATEWAY")
    telemetry_topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    meter_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Location
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Dynamic Operating Envelopes
    doe_import_max_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    doe_export_max_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    doe_last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Live telemetry cache
    current_kw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_soc_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_telemetry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    hosting_capacity_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    def __repr__(self) -> str:
        return f"<DERAsset id={self.id} ref={self.asset_ref} type={self.type} status={self.status}>"


class AssetTelemetry(Base):
    """Time-series telemetry records per asset."""
    __tablename__ = "asset_telemetry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("der_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    power_kw: Mapped[float] = mapped_column(Float, nullable=False)  # Negative = export
    voltage_v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_a: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    soc_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # BESS only
    frequency_hz: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="IOT_GATEWAY")

    def __repr__(self) -> str:
        return f"<AssetTelemetry asset={self.asset_id} ts={self.timestamp} kw={self.power_kw}>"


class DOEHistory(Base):
    """History of Dynamic Operating Envelope updates for assets."""
    __tablename__ = "doe_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("der_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)  # NULL for non-event DOE
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doe_import_max_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    doe_export_max_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    issued_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    def __repr__(self) -> str:
        return f"<DOEHistory asset={self.asset_id} start={self.interval_start}>"
