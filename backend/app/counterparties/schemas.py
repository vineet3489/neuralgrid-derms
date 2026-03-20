"""Pydantic schemas for Counterparties."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.counterparties.models import (
    CommCapability,
    CounterpartyStatus,
    CounterpartyType,
    PrequalStatus,
)


class CounterpartyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: CounterpartyType
    registration_number: Optional[str] = None
    contact_name: str = Field(..., min_length=1, max_length=255)
    contact_email: str  # EmailStr would require email-validator; keep as str for compat
    contact_phone: Optional[str] = None
    portfolio_kw: float = Field(default=0.0, ge=0)
    asset_types: list[str] = Field(default_factory=list)
    comm_capability: CommCapability = CommCapability.HYBRID
    comm_endpoint: Optional[str] = None
    framework_agreement_ref: Optional[str] = None
    framework_signed_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    overarching_agreement: bool = False
    region: Optional[str] = None
    notes: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


class CounterpartyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    type: Optional[CounterpartyType] = None
    status: Optional[CounterpartyStatus] = None
    registration_number: Optional[str] = None
    contact_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    portfolio_kw: Optional[float] = Field(default=None, ge=0)
    asset_types: Optional[list[str]] = None
    comm_capability: Optional[CommCapability] = None
    comm_endpoint: Optional[str] = None
    framework_agreement_ref: Optional[str] = None
    framework_signed_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    overarching_agreement: Optional[bool] = None
    region: Optional[str] = None
    notes: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


class CounterpartyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deployment_id: str
    name: str
    type: str
    status: str
    registration_number: Optional[str] = None
    contact_name: str
    contact_email: str
    contact_phone: Optional[str] = None
    portfolio_kw: float
    asset_types: str  # JSON string stored in DB
    comm_capability: str
    comm_endpoint: Optional[str] = None
    prequalification_status: str
    prequalification_date: Optional[str] = None
    framework_agreement_ref: Optional[str] = None
    framework_signed_date: Optional[str] = None
    overarching_agreement: bool
    region: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    meta: Optional[str] = None


class PrequalificationCheckCreate(BaseModel):
    check_name: str = Field(..., description="e.g. financial_standing, insurance, technical_capability, meter_accuracy")
    result: str = Field(..., pattern="^(PASS|FAIL|WAIVED)$")
    notes: Optional[str] = None


class PrequalificationCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    counterparty_id: str
    check_name: str
    result: str
    notes: Optional[str] = None
    checked_by: Optional[str] = None
    checked_at: Optional[datetime] = None
    created_at: datetime


class PrequalificationSubmit(BaseModel):
    """Payload for submitting a batch of prequalification checks."""
    checks: list[PrequalificationCheckCreate]
