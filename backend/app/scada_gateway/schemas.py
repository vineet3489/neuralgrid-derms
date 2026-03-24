"""Pydantic v2 schemas for SCADA Gateway and DaaS API key management."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# SCADA Endpoint schemas
# ---------------------------------------------------------------------------

class SCADAEndpointCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    protocol: str = Field(default="REST_JSON")
    endpoint_url: Optional[str] = None
    port: Optional[int] = None
    auth_type: str = Field(default="NONE")
    auth_config: Optional[str] = None  # JSON string; stored but never returned in reads

    push_lv_voltages: bool = True
    push_feeder_loading: bool = True
    push_der_outputs: bool = True
    push_oe_limits: bool = True
    push_flex_events: bool = True

    push_interval_seconds: int = Field(default=30, ge=5)
    is_active: bool = True

    cim_model_id: Optional[str] = None


class SCADAEndpointUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    protocol: Optional[str] = None
    endpoint_url: Optional[str] = None
    port: Optional[int] = None
    auth_type: Optional[str] = None
    auth_config: Optional[str] = None

    push_lv_voltages: Optional[bool] = None
    push_feeder_loading: Optional[bool] = None
    push_der_outputs: Optional[bool] = None
    push_oe_limits: Optional[bool] = None
    push_flex_events: Optional[bool] = None

    push_interval_seconds: Optional[int] = Field(default=None, ge=5)
    is_active: Optional[bool] = None

    cim_model_id: Optional[str] = None


class SCADAEndpointRead(BaseModel):
    """Public representation of a SCADA endpoint — auth_config is intentionally omitted."""

    id: str
    deployment_id: str
    name: str
    description: Optional[str] = None
    protocol: str
    endpoint_url: Optional[str] = None
    port: Optional[int] = None
    auth_type: str

    push_lv_voltages: bool
    push_feeder_loading: bool
    push_der_outputs: bool
    push_oe_limits: bool
    push_flex_events: bool

    push_interval_seconds: int
    is_active: bool

    last_push_at: Optional[datetime] = None
    last_push_status: Optional[str] = None
    last_push_message: Optional[str] = None

    cim_model_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# DaaS API Key schemas
# ---------------------------------------------------------------------------

class DaaSApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None

    # Permissions
    can_read_lv_voltages: bool = True
    can_read_feeder_loading: bool = True
    can_read_der_outputs: bool = True
    can_read_oe_limits: bool = True
    can_read_flex_events: bool = False

    # Rate limit
    rate_limit_per_minute: int = Field(default=60, ge=1)

    # Expiry (None = never expires)
    expires_at: Optional[datetime] = None


class DaaSApiKeyRead(BaseModel):
    """Public representation of a DaaS API key — key_hash is intentionally omitted."""

    id: str
    deployment_id: str
    key_prefix: str
    name: str
    description: Optional[str] = None
    is_active: bool

    can_read_lv_voltages: bool
    can_read_feeder_loading: bool
    can_read_der_outputs: bool
    can_read_oe_limits: bool
    can_read_flex_events: bool

    rate_limit_per_minute: int
    total_requests: int
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    created_by: Optional[str] = None

    model_config = {"from_attributes": True}


class DaaSApiKeyCreated(DaaSApiKeyRead):
    """
    Returned once on key creation only.

    The ``api_key`` field contains the plain-text key and will never be
    retrievable again after this initial response.
    """

    api_key: str


# ---------------------------------------------------------------------------
# Push result schema
# ---------------------------------------------------------------------------

class PushResult(BaseModel):
    status: str          # OK / FAILED / SKIPPED / SIMULATED
    message: str
    records_pushed: int = 0
    latency_ms: int = 0
    pushed_at: datetime
