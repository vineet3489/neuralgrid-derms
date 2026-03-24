"""ORM model for Aggregator End Devices registered against the DERMS VTN server."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.utils import new_uuid, utcnow


class AggregatorEndDevice(Base):
    """
    An EndDevice registered by an external aggregator.

    Protocol values : IEEE_2030_5 / OPENADR_2B / REST
    Status values   : REGISTERED / ACTIVE / OFFLINE
    """

    __tablename__ = "aggregator_end_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Aggregator-supplied reference (e.g. "ALPHA-FLEX-001")
    aggregator_ref: Mapped[str] = mapped_column(String(128), nullable=False)

    # Communication protocol used by this device
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)

    # Optional FK references — kept as plain strings to avoid hard FK constraints
    # across optional modules; the application layer enforces integrity.
    counterparty_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    asset_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # IEEE 2030.5 device identifiers
    device_lFDI: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    device_sFDI: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # OpenADR VEN identifier
    ven_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Where the DERMS pushes OEs (aggregator's inbound endpoint)
    endpoint_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REGISTERED")

    meta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<AggregatorEndDevice id={self.id} ref={self.aggregator_ref} "
            f"protocol={self.protocol} status={self.status}>"
        )
