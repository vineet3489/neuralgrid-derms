"""ORM models for Flexibility Programs."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.utils import new_uuid, utcnow


class ProgramType(str, Enum):
    PEAK_REDUCTION = "PEAK_REDUCTION"
    SCHEDULED_UTILISATION = "SCHEDULED_UTILISATION"
    OPERATIONAL_UTILISATION = "OPERATIONAL_UTILISATION"
    DYNAMIC_CONSTRAINT = "DYNAMIC_CONSTRAINT"
    RESTORATION = "RESTORATION"
    DEMAND_RESPONSE = "DEMAND_RESPONSE"
    P2P_TRADING = "P2P_TRADING"
    VPP_DISPATCH = "VPP_DISPATCH"


class ProgramStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON-serialised config stored as text (SQLite + PG compatible)
    service_window_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    target_mw: Mapped[float] = mapped_column(Float, nullable=False)
    enrolled_mw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    regulatory_basis: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cmz_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    notification_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    kpi_thresholds: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    max_events_per_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_events_per_season: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_rest_hours_between_events: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    start_date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO date YYYY-MM-DD
    end_date: Mapped[str] = mapped_column(String(10), nullable=False)    # ISO date YYYY-MM-DD
    stackable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    meta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    def __repr__(self) -> str:
        return f"<Program id={self.id} name={self.name} status={self.status}>"
