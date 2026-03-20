"""Pydantic schemas for DER Assets."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.assets.models import AssetStatus, AssetType, CommCapability, TelemetrySource


class DERAssetCreate(BaseModel):
    counterparty_id: str
    asset_ref: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=255)
    type: AssetType
    is_digital_twin: bool = True
    connection_point_id: Optional[str] = None
    feeder_id: Optional[str] = None
    dt_id: Optional[str] = None
    phase: str = "UNKNOWN"
    capacity_kw: float = Field(..., gt=0)
    capacity_kwh: Optional[float] = Field(default=None, gt=0)
    comm_capability: CommCapability = CommCapability.MQTT_GATEWAY
    comm_endpoint: Optional[str] = None
    telemetry_source: TelemetrySource = TelemetrySource.IOT_GATEWAY
    telemetry_topic: Optional[str] = None
    meter_id: Optional[str] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    doe_import_max_kw: Optional[float] = None
    doe_export_max_kw: Optional[float] = None
    hosting_capacity_kw: Optional[float] = None
    meta: Optional[dict[str, Any]] = None


class DERAssetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    status: Optional[AssetStatus] = None
    connection_point_id: Optional[str] = None
    feeder_id: Optional[str] = None
    dt_id: Optional[str] = None
    phase: Optional[str] = None
    capacity_kw: Optional[float] = Field(default=None, gt=0)
    capacity_kwh: Optional[float] = Field(default=None, gt=0)
    comm_capability: Optional[CommCapability] = None
    comm_endpoint: Optional[str] = None
    telemetry_source: Optional[TelemetrySource] = None
    telemetry_topic: Optional[str] = None
    meter_id: Optional[str] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    doe_import_max_kw: Optional[float] = None
    doe_export_max_kw: Optional[float] = None
    hosting_capacity_kw: Optional[float] = None
    meta: Optional[dict[str, Any]] = None


class DERAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deployment_id: str
    counterparty_id: str
    asset_ref: str
    name: str
    type: str
    status: str
    is_digital_twin: bool
    connection_point_id: Optional[str] = None
    feeder_id: Optional[str] = None
    dt_id: Optional[str] = None
    phase: str
    capacity_kw: float
    capacity_kwh: Optional[float] = None
    comm_capability: str
    comm_endpoint: Optional[str] = None
    telemetry_source: str
    telemetry_topic: Optional[str] = None
    meter_id: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    doe_import_max_kw: Optional[float] = None
    doe_export_max_kw: Optional[float] = None
    doe_last_updated: Optional[datetime] = None
    current_kw: float
    current_soc_pct: Optional[float] = None
    last_telemetry_at: Optional[datetime] = None
    hosting_capacity_kw: Optional[float] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    meta: Optional[str] = None


class AssetTelemetryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    asset_id: str
    deployment_id: str
    timestamp: datetime
    power_kw: float
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    soc_pct: Optional[float] = None
    frequency_hz: Optional[float] = None
    temperature_c: Optional[float] = None
    source: str


class TelemetryIngest(BaseModel):
    """Manual telemetry ingest payload."""
    power_kw: float
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    soc_pct: Optional[float] = Field(default=None, ge=0, le=100)
    frequency_hz: Optional[float] = None
    temperature_c: Optional[float] = None
    source: str = "MANUAL"


class DOEUpdate(BaseModel):
    """Payload for updating an asset's Dynamic Operating Envelope."""
    import_max_kw: Optional[float] = Field(default=None, ge=0)
    export_max_kw: Optional[float] = Field(default=None, ge=0)
    event_id: Optional[str] = None
    reason: Optional[str] = None
    interval_start: Optional[datetime] = None
    interval_end: Optional[datetime] = None


class DOEHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    asset_id: str
    event_id: Optional[str] = None
    interval_start: datetime
    interval_end: datetime
    doe_import_max_kw: Optional[float] = None
    doe_export_max_kw: Optional[float] = None
    reason: Optional[str] = None
    issued_by: Optional[str] = None
    created_at: datetime


class DOECurrentRead(BaseModel):
    """Current DOE state for an asset."""
    asset_id: str
    doe_import_max_kw: Optional[float] = None
    doe_export_max_kw: Optional[float] = None
    doe_last_updated: Optional[datetime] = None
    history: list[DOEHistoryRead] = Field(default_factory=list)
