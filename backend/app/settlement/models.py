"""ORM models for Settlement statements."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.utils import new_uuid, utcnow


class SettlementStatement(Base):
    """Calculated settlement statement for a contract over a billing period."""

    __tablename__ = "settlement_statements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    contract_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # DRAFT / PENDING_APPROVAL / APPROVED / PAID / DISPUTED
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)

    # Availability payments
    availability_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    availability_rate_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    availability_payment_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Utilisation payments
    delivered_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    utilisation_rate_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    utilisation_payment_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Penalties
    missed_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    penalty_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Net
    gross_payment_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    net_payment_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP")

    # Summary stats
    events_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_delivery_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    def __repr__(self) -> str:
        return f"<SettlementStatement contract={self.contract_id} status={self.status}>"
