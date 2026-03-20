from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    # Relationships
    deployment_roles: Mapped[list["UserDeploymentRole"]] = relationship(
        "UserDeploymentRole", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


class UserDeploymentRole(Base):
    __tablename__ = "user_deployment_roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="deployment_roles")

    def __repr__(self) -> str:
        return f"<UserDeploymentRole user={self.user_id} deploy={self.deployment_id} role={self.role}>"


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)  # ISO 3166-1 alpha-2
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)  # ISO 4217
    currency_minor_units: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    regulatory_framework: Mapped[str] = mapped_column(String(255), nullable=False)
    voltage_nominal: Mapped[float] = mapped_column(Float, nullable=False, default=230.0)
    frequency_hz: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    settlement_cycle: Mapped[str] = mapped_column(String(32), nullable=False)  # WEEKLY/MONTHLY/QUARTERLY
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Deployment slug={self.slug} name={self.name}>"
