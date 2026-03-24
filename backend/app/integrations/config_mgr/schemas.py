"""Pydantic schemas for Integration Configuration Manager."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Integration Config schemas
# ---------------------------------------------------------------------------

class IntegrationConfigCreate(BaseModel):
    """Fields required / accepted when creating a new integration config."""
    integration_type: str
    name: str
    description: Optional[str] = None
    mode: str = "SIMULATION"
    base_url: Optional[str] = None
    auth_type: str = "NONE"
    auth_config: Optional[Dict[str, Any]] = None
    polling_interval_seconds: int = 30
    timeout_seconds: int = 10
    is_active: bool = True


class IntegrationConfigUpdate(BaseModel):
    """All fields optional — only provided fields are applied."""
    name: Optional[str] = None
    description: Optional[str] = None
    mode: Optional[str] = None
    base_url: Optional[str] = None
    auth_type: Optional[str] = None
    auth_config: Optional[Dict[str, Any]] = None
    polling_interval_seconds: Optional[int] = None
    timeout_seconds: Optional[int] = None
    is_active: Optional[bool] = None
    sim_params: Optional[Dict[str, Any]] = None


class IntegrationConfigRead(BaseModel):
    """Full read schema — returned by GET endpoints."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    deployment_id: str
    integration_type: str
    name: str
    description: Optional[str] = None
    mode: str
    base_url: Optional[str] = None
    auth_type: str
    # auth_config is intentionally omitted from the read schema (sensitive)
    polling_interval_seconds: int
    timeout_seconds: int
    is_active: bool
    last_test_at: Optional[datetime] = None
    last_test_status: Optional[str] = None
    last_test_message: Optional[str] = None
    sim_params: Optional[str] = None  # Raw JSON string from DB
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Connection test result
# ---------------------------------------------------------------------------

class ConnectionTestResult(BaseModel):
    """Result returned after testing connectivity to an integration endpoint."""
    status: str                    # OK / FAILED / TIMEOUT
    message: str
    latency_ms: Optional[int] = None
    tested_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Simulation parameters update
# ---------------------------------------------------------------------------

class SimParamsUpdate(BaseModel):
    """
    Typed dict of simulation parameters that can be overridden per integration.

    Fields map to known sim_params keys; all are optional so callers may
    supply any subset.  Unknown keys are also accepted (passed through as-is).
    """
    # ADMS
    solar_peak_factor: Optional[float] = None
    cloud_noise_factor: Optional[float] = None
    feeder_loading_warn_pct: Optional[float] = None
    feeder_loading_max_pct: Optional[float] = None
    voltage_nominal_v: Optional[float] = None
    voltage_high_warn_v: Optional[float] = None
    voltage_low_warn_v: Optional[float] = None
    voltage_high_trip_v: Optional[float] = None
    voltage_low_trip_v: Optional[float] = None
    adms_poll_interval_seconds: Optional[int] = None

    # DER_AGGREGATOR_IEEE2030_5
    aggregator_poll_interval_seconds: Optional[int] = None
    oe_ack_timeout_seconds: Optional[int] = None
    default_response_time_seconds: Optional[int] = None

    # DER_AGGREGATOR_OPENADR
    vtn_push_enabled: Optional[bool] = None
    event_lead_time_minutes: Optional[int] = None
    ven_registration_timeout_minutes: Optional[int] = None

    # MDMS
    baseline_lookback_days: Optional[int] = None
    meter_read_interval_minutes: Optional[int] = None
    sftp_poll_interval_minutes: Optional[int] = None

    # WEATHER_API
    provider: Optional[str] = None
    forecast_horizon_hours: Optional[int] = None

    model_config = ConfigDict(extra="allow")  # allow unknown keys to pass through
