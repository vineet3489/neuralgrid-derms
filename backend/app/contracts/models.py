"""ORM models for Flexibility Contracts."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.utils import new_uuid, utcnow


class ContractType(str, Enum):
    SCHEDULED_UTILISATION = "SCHEDULED_UTILISATION"
    OPERATIONAL_UTILISATION = "OPERATIONAL_UTILISATION"
    DYNAMIC_CONSTRAINT = "DYNAMIC_CONSTRAINT"
    RESTORATION = "RESTORATION"
    DEMAND_RESPONSE = "DEMAND_RESPONSE"
    P2P = "P2P"


class ContractStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_SIGNATURE = "PENDING_SIGNATURE"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"


class BaselineMethod(str, Enum):
    HIGH_5_OF_10 = "HIGH_5_OF_10"
    AVG_5_OF_10 = "AVG_5_OF_10"
    REGRESSION_ADJUSTED = "REGRESSION_ADJUSTED"
    METERED_BASELINE = "METERED_BASELINE"
    SMART_BASELINE = "SMART_BASELINE"


class MeasurementSource(str, Enum):
    AMI_MDMS = "AMI_MDMS"
    IOT_GATEWAY = "IOT_GATEWAY"
    AGGREGATOR_REPORTED = "AGGREGATOR_REPORTED"
    HYBRID = "HYBRID"


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    program_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("programs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    counterparty_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("counterparties.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Unique contract reference per deployment (enforced at service layer)
    contract_ref: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")

    cmz_id: Mapped[str] = mapped_column(String(64), nullable=False)
    contracted_capacity_kw: Mapped[float] = mapped_column(Float, nullable=False)
    min_dispatch_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    service_window_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    response_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    notification_lead_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # Payment rates in minor currency units (e.g. pence / paise)
    availability_rate_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    utilisation_rate_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    penalty_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    grace_factor_pct: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)

    baseline_method: Mapped[str] = mapped_column(String(32), nullable=False, default="HIGH_5_OF_10")
    baseline_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    doe_clause: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stackable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    max_activations_per_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_activations_per_period: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_rest_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    measurement_source: Mapped[str] = mapped_column(String(32), nullable=False, default="AMI_MDMS")
    settlement_cycle: Mapped[str] = mapped_column(String(16), nullable=False, default="MONTHLY")

    signed_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    start_date: Mapped[str] = mapped_column(String(10), nullable=False)
    end_date: Mapped[str] = mapped_column(String(10), nullable=False)

    framework_agreement_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    def __repr__(self) -> str:
        return f"<Contract id={self.id} ref={self.contract_ref} status={self.status}>"


class ContractAmendment(Base):
    __tablename__ = "contract_amendments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    contract_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amendment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # RATE_CHANGE / CAPACITY_CHANGE / STATUS_CHANGE
    effective_date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO date
    old_values: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    new_values: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ContractAmendment id={self.id} contract={self.contract_id} type={self.amendment_type}>"
