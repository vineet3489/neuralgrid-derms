"""ORM models for forecast records."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.core.utils import new_uuid, utcnow


class ForecastRecord(Base):
    """Persisted forecast time-series for a deployment."""

    __tablename__ = "forecast_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # LOAD / SOLAR / PRICE / FLEX_AVAILABILITY
    forecast_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    cmz_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    asset_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # JSON array of {timestamp, value_kw, confidence_low, confidence_high}
    values: Mapped[str] = mapped_column(Text, nullable=False)

    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0-simple")

    # Filled in after the forecast period passes (backcasting accuracy)
    mae_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<ForecastRecord type={self.forecast_type} deploy={self.deployment_id} at={self.generated_at}>"
