"""ORM model for Integration Configuration."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.utils import new_uuid, utcnow


class IntegrationConfig(Base):
    """
    Per-deployment configuration for each external system integration.

    integration_type values:
        ADMS / DER_AGGREGATOR_IEEE2030_5 / DER_AGGREGATOR_OPENADR /
        SCADA / DMS / MDM / MDMS / WEATHER_API
    mode values: SIMULATION / LIVE
    auth_type values: NONE / API_KEY / BASIC / OAUTH2 / CERTIFICATE
    last_test_status values: OK / FAILED / TIMEOUT
    """

    __tablename__ = "integration_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    integration_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="SIMULATION")

    base_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    auth_type: Mapped[str] = mapped_column(String(16), nullable=False, default="NONE")
    auth_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    polling_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Connection test tracking
    last_test_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    last_test_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Simulation parameter overrides (JSON)
    sim_params: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<IntegrationConfig id={self.id} type={self.integration_type} "
            f"mode={self.mode} deployment={self.deployment_id}>"
        )
