"""ORM models for Counterparties (flexibility providers)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.utils import new_uuid, utcnow


class CounterpartyType(str, Enum):
    AGGREGATOR = "AGGREGATOR"
    COMMERCIAL = "COMMERCIAL"
    INDUSTRIAL = "INDUSTRIAL"
    RESIDENTIAL_GROUP = "RESIDENTIAL_GROUP"
    GOVERNMENT = "GOVERNMENT"
    DISCOM = "DISCOM"


class CounterpartyStatus(str, Enum):
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    SUSPENDED = "SUSPENDED"
    REJECTED = "REJECTED"


class PrequalStatus(str, Enum):
    NOT_SUBMITTED = "NOT_SUBMITTED"
    SUBMITTED = "SUBMITTED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    WAIVED = "WAIVED"


class CommCapability(str, Enum):
    IEEE_2030_5 = "IEEE_2030_5"
    OPENADR_2B = "OPENADR_2B"
    OPENADR_2A = "OPENADR_2A"
    SCADA_MODBUS = "SCADA_MODBUS"
    MANUAL_NOTIFICATION = "MANUAL_NOTIFICATION"
    HYBRID = "HYBRID"


class Counterparty(Base):
    __tablename__ = "counterparties"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    registration_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    portfolio_kw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    asset_types: Mapped[str] = mapped_column(Text, nullable=False, default='[]')  # JSON array
    comm_capability: Mapped[str] = mapped_column(String(32), nullable=False, default="HYBRID")
    comm_endpoint: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    prequalification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NOT_SUBMITTED"
    )
    prequalification_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    framework_agreement_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    framework_signed_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    overarching_agreement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    region: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
        return f"<Counterparty id={self.id} name={self.name} status={self.status}>"


class PrequalificationCheck(Base):
    __tablename__ = "prequalification_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    counterparty_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("counterparties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # check_name: "financial_standing" / "insurance" / "technical_capability" / "meter_accuracy"
    check_name: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)  # PASS / FAIL / WAIVED
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checked_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<PrequalificationCheck id={self.id} cp={self.counterparty_id} "
            f"check={self.check_name} result={self.result}>"
        )
