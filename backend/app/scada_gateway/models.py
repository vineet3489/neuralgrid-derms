"""ORM models for SCADA Gateway — SCADAEndpoint, DaaSApiKey, DaaSUsageRecord."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.utils import new_uuid, utcnow


class SCADAEndpoint(Base):
    """
    A configured SCADA system connection.

    L&T DERMS pushes LV DERMS data to upstream SCADA/EMS/ADMS/Historian systems
    on a periodic basis (default every 30 seconds).

    protocol values:
        REST_JSON / IEC_61968_CIM / MODBUS_TCP / DNP3 / MQTT / OPC_UA
    auth_type values:
        NONE / API_KEY / BASIC / CERTIFICATE
    last_push_status values:
        OK / FAILED / SKIPPED
    """

    __tablename__ = "scada_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Transport / protocol
    protocol: Mapped[str] = mapped_column(String(32), nullable=False, default="REST_JSON")
    endpoint_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Authentication
    auth_type: Mapped[str] = mapped_column(String(16), nullable=False, default="NONE")
    auth_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # What data to push
    push_lv_voltages: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    push_feeder_loading: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    push_der_outputs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    push_oe_limits: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    push_flex_events: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Push configuration
    push_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Connection state tracking
    last_push_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_push_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    last_push_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # CIM model reference (IEC 61970)
    cim_model_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<SCADAEndpoint id={self.id} name={self.name!r} "
            f"protocol={self.protocol} deployment={self.deployment_id}>"
        )


class DaaSApiKey(Base):
    """
    L&T Data-as-a-Service API key for external SCADA operators.

    The plain key is never stored; only a SHA-256 hash is persisted.
    The key_prefix (first 16 chars) is displayed in the UI to help
    operators identify which key is which.
    """

    __tablename__ = "daas_api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hex digest
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)  # First 16 chars for UI display

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Data access permissions
    can_read_lv_voltages: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_read_feeder_loading: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_read_der_outputs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_read_oe_limits: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_read_flex_events: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Rate limiting
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    # Usage tracking
    total_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DaaSApiKey id={self.id} prefix={self.key_prefix!r} "
            f"name={self.name!r} deployment={self.deployment_id}>"
        )


class DaaSUsageRecord(Base):
    """
    Metered usage record for DaaS API billing and monitoring.

    One record is created per inbound API call authenticated with a DaaS key.
    """

    __tablename__ = "daas_usage_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    api_key_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    endpoint_path: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )

    response_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, default=200)

    def __repr__(self) -> str:
        return (
            f"<DaaSUsageRecord key={self.api_key_id} path={self.endpoint_path!r} "
            f"ts={self.timestamp} status={self.status_code}>"
        )
