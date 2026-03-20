"""ORM models for Dispatch — FlexEvents and OE messages."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.utils import new_uuid, utcnow


class EventStatus(str, Enum):
    PLANNED = "PLANNED"
    PENDING_DISPATCH = "PENDING_DISPATCH"
    DISPATCHED = "DISPATCHED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class FlexEvent(Base):
    """A flexibility dispatch event — manual or auto-generated."""

    __tablename__ = "flex_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Links to program & contract (nullable so auto events don't require them)
    program_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    contract_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    cmz_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_ref: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # EVT-001

    # PEAK_REDUCTION / DR_CURTAILMENT / VOLTAGE_CORRECTION / P2P_DISPATCH / DOE_UPDATE / MANUAL
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PLANNED", index=True)

    # AUTO_VOLTAGE / AUTO_OVERLOAD / MANUAL_OPERATOR / SCHEDULED / DR_REQUEST
    trigger: Mapped[str] = mapped_column(String(64), nullable=False, default="MANUAL_OPERATOR")

    target_kw: Mapped[float] = mapped_column(Float, nullable=False)
    dispatched_kw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    delivered_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    notification_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    operator_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auto_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # JSON arrays / objects stored as text
    asset_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON array of asset IDs
    doe_values: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON {asset_id: {import_max_kw, export_max_kw}}

    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:
        return f"<FlexEvent ref={self.event_ref} type={self.event_type} status={self.status}>"


class OEMessage(Base):
    """Operating Envelope message sent to a DER asset."""

    __tablename__ = "oe_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    direction: Mapped[str] = mapped_column(String(32), nullable=False)  # CURTAIL / RESTORE / SET_DOE
    import_max_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    export_max_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    ack_received: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ack_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # KAFKA / IEEE_2030_5 / OPENADR / MANUAL
    delivery_channel: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")

    def __repr__(self) -> str:
        return f"<OEMessage event={self.event_id} asset={self.asset_id} dir={self.direction}>"
