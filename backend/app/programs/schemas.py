"""Pydantic schemas for Programs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.programs.models import ProgramStatus, ProgramType


class ServiceWindowConfig(BaseModel):
    """Defines when a program's service window is active."""
    days: list[str] = Field(
        default_factory=list,
        description="ISO weekday names e.g. ['MON','TUE','WED','THU','FRI']",
    )
    hours: dict[str, str] = Field(
        default_factory=lambda: {"start": "17:00", "end": "21:00"},
        description="start/end times in HH:MM format",
    )
    months: list[str] = Field(
        default_factory=list,
        description="3-letter month codes e.g. ['NOV','DEC','JAN']",
    )
    tz: str = Field(default="UTC", description="IANA timezone string")


class ProgramCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: ProgramType
    description: Optional[str] = None
    service_window_config: Optional[ServiceWindowConfig] = None
    target_mw: float = Field(..., gt=0)
    regulatory_basis: Optional[str] = None
    cmz_ids: Optional[list[str]] = None
    notification_config: Optional[dict[str, Any]] = None
    kpi_thresholds: Optional[dict[str, Any]] = None
    max_events_per_day: Optional[int] = Field(default=None, ge=1)
    max_events_per_season: Optional[int] = Field(default=None, ge=1)
    min_rest_hours_between_events: float = 0.0
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    stackable: bool = False
    meta: Optional[dict[str, Any]] = None


class ProgramUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[ProgramStatus] = None
    service_window_config: Optional[ServiceWindowConfig] = None
    target_mw: Optional[float] = Field(default=None, gt=0)
    regulatory_basis: Optional[str] = None
    cmz_ids: Optional[list[str]] = None
    notification_config: Optional[dict[str, Any]] = None
    kpi_thresholds: Optional[dict[str, Any]] = None
    max_events_per_day: Optional[int] = Field(default=None, ge=1)
    max_events_per_season: Optional[int] = Field(default=None, ge=1)
    min_rest_hours_between_events: Optional[float] = None
    start_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    stackable: Optional[bool] = None
    meta: Optional[dict[str, Any]] = None


class ProgramRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    deployment_id: str
    name: str
    type: str
    status: str
    description: Optional[str] = None
    service_window_config: Optional[str] = None
    target_mw: float
    enrolled_mw: float
    regulatory_basis: Optional[str] = None
    cmz_ids: Optional[str] = None
    notification_config: Optional[str] = None
    kpi_thresholds: Optional[str] = None
    max_events_per_day: Optional[int] = None
    max_events_per_season: Optional[int] = None
    min_rest_hours_between_events: float
    start_date: str
    end_date: str
    stackable: bool
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    meta: Optional[str] = None


class ProgramKPIs(BaseModel):
    events_dispatched: int = 0
    avg_delivery_pct: float = 0.0
    total_cost_minor: int = 0
    contracts_count: int = 0


class ProgramCloneRequest(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=255)
    new_start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    new_end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
