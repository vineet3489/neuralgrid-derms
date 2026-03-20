"""Pydantic schemas for Contracts."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.models import (
    BaselineMethod,
    ContractStatus,
    ContractType,
    MeasurementSource,
)


class ContractCreate(BaseModel):
    program_id: str
    counterparty_id: str
    contract_ref: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    type: ContractType
    cmz_id: str
    contracted_capacity_kw: float = Field(..., gt=0)
    min_dispatch_kw: Optional[float] = Field(default=None, gt=0)
    service_window_config: Optional[dict[str, Any]] = None
    response_time_minutes: int = Field(default=30, ge=1)
    notification_lead_config: Optional[dict[str, Any]] = None
    availability_rate_minor: int = Field(default=0, ge=0)
    utilisation_rate_minor: int = Field(default=0, ge=0)
    penalty_multiplier: float = Field(default=3.0, ge=0)
    grace_factor_pct: float = Field(default=5.0, ge=0, le=100)
    baseline_method: BaselineMethod = BaselineMethod.HIGH_5_OF_10
    baseline_params: Optional[dict[str, Any]] = None
    doe_clause: bool = False
    stackable: bool = False
    max_activations_per_day: Optional[int] = Field(default=None, ge=1)
    max_activations_per_period: Optional[int] = Field(default=None, ge=1)
    min_rest_hours: float = 0.0
    measurement_source: MeasurementSource = MeasurementSource.AMI_MDMS
    settlement_cycle: str = "MONTHLY"
    signed_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    framework_agreement_id: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


class ContractUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    status: Optional[ContractStatus] = None
    cmz_id: Optional[str] = None
    contracted_capacity_kw: Optional[float] = Field(default=None, gt=0)
    min_dispatch_kw: Optional[float] = Field(default=None, gt=0)
    service_window_config: Optional[dict[str, Any]] = None
    response_time_minutes: Optional[int] = Field(default=None, ge=1)
    notification_lead_config: Optional[dict[str, Any]] = None
    availability_rate_minor: Optional[int] = Field(default=None, ge=0)
    utilisation_rate_minor: Optional[int] = Field(default=None, ge=0)
    penalty_multiplier: Optional[float] = Field(default=None, ge=0)
    grace_factor_pct: Optional[float] = Field(default=None, ge=0, le=100)
    baseline_method: Optional[BaselineMethod] = None
    baseline_params: Optional[dict[str, Any]] = None
    doe_clause: Optional[bool] = None
    stackable: Optional[bool] = None
    max_activations_per_day: Optional[int] = Field(default=None, ge=1)
    max_activations_per_period: Optional[int] = Field(default=None, ge=1)
    min_rest_hours: Optional[float] = None
    measurement_source: Optional[MeasurementSource] = None
    settlement_cycle: Optional[str] = None
    signed_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    framework_agreement_id: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


class ContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deployment_id: str
    program_id: str
    counterparty_id: str
    contract_ref: str
    name: str
    type: str
    status: str
    cmz_id: str
    contracted_capacity_kw: float
    min_dispatch_kw: Optional[float] = None
    service_window_config: Optional[str] = None
    response_time_minutes: int
    notification_lead_config: Optional[str] = None
    availability_rate_minor: int
    utilisation_rate_minor: int
    penalty_multiplier: float
    grace_factor_pct: float
    baseline_method: str
    baseline_params: Optional[str] = None
    doe_clause: bool
    stackable: bool
    max_activations_per_day: Optional[int] = None
    max_activations_per_period: Optional[int] = None
    min_rest_hours: float
    measurement_source: str
    settlement_cycle: str
    signed_date: Optional[str] = None
    start_date: str
    end_date: str
    framework_agreement_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    meta: Optional[str] = None


class ContractAmendmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_id: str
    amendment_type: str
    effective_date: str
    old_values: str
    new_values: str
    created_by: Optional[str] = None
    created_at: datetime
    notes: Optional[str] = None


class ContractPerformance(BaseModel):
    """Performance summary for a contract."""
    activations_count: int = 0
    avg_delivery_pct: float = 0.0
    total_paid_minor: int = 0
    penalty_events: int = 0


class SettlementSimulation(BaseModel):
    """Result of a hypothetical settlement calculation."""
    contracted_capacity_kw: float
    hypothetical_kw: float
    duration_hours: float
    availability_payment_minor: int
    utilisation_payment_minor: int
    penalty_minor: int
    net_payment_minor: int
    delivery_pct: float
    within_grace_factor: bool
