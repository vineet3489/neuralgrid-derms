"""
Audit logging for the L&T Neural Grid DERMS platform.
Append-only record of all significant state changes and user actions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import Boolean, DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    # Plain varchar — no FK so system/background processes can log without a real user row
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    # Denormalized for easy log reading without joins
    user_email: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    user_role: Mapped[str] = mapped_column(String(64), nullable=False, default="SYSTEM")
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # CREATE/UPDATE/DELETE/DISPATCH/APPROVE/IMPORT/LOGIN/LOGOUT
    resource_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # programs/contracts/events/config/settlement
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    diff: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # before/after values
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False, index=True
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AuditEvent id={self.id} action={self.action} "
            f"resource={self.resource_type}/{self.resource_id} "
            f"user={self.user_email} deploy={self.deployment_id}>"
        )


async def log_audit(
    db: AsyncSession,
    *,
    deployment_id: str,
    action: str,
    resource_type: str,
    user_id: Optional[str] = None,
    user_email: str = "system",
    user_role: str = "SYSTEM",
    resource_id: Optional[str] = None,
    diff: Optional[dict] = None,
    ip_address: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
) -> AuditEvent:
    """
    Append-only audit log writer.

    Adds an AuditEvent to the session without flushing — the caller controls
    the transaction boundary.  Call ``await db.flush()`` or let the session
    auto-commit after the request to persist the record.
    """
    event = AuditEvent(
        id=_new_uuid(),
        user_id=user_id,
        user_email=user_email,
        user_role=user_role,
        deployment_id=deployment_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        diff=diff,
        ip_address=ip_address,
        timestamp=_now(),
        success=success,
        error_message=error_message,
    )
    db.add(event)
    return event
