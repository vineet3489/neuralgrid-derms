"""
Settlement service — calculates payments for contract periods.

Availability payment  = availability_hours * availability_rate_minor / 100
Utilisation payment   = delivered_kwh * utilisation_rate_minor / 100
Penalty               = missed_kwh * penalty_rate_minor / 100

All currency amounts are stored in minor units (pence / paise) as integers.
"""
from __future__ import annotations

import math

import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.settlement.models import SettlementStatement


# ── Baseline simulation ───────────────────────────────────────────────────────

async def simulate_baseline(
    method: str,
    asset_id: str,
    event_start: datetime,
) -> float:
    """
    Simulate baseline kW for an asset at event_start using the specified method.

    HIGH_5_OF_10  — Highest 5 of previous 10 similar-day readings.
    AVG_5_OF_10   — Average of 5 previous similar-day readings.
    SMART_BASELINE — Regression-adjusted (simulated).

    Returns estimated baseline kW (always >= 0).
    """
    # In production: query MDMS/meter data. For demo: generate plausible values.
    hour = event_start.hour
    # Typical load shape: higher in morning/evening
    base = 20.0 + 15.0 * abs(math.sin(3.14159 * hour / 12.0)) + random.gauss(0.0, 3.0)

    if method == "HIGH_5_OF_10":
        return max(5.0, base * 1.10)
    elif method == "AVG_5_OF_10":
        return max(5.0, base)
    else:  # SMART_BASELINE
        return max(5.0, base * random.uniform(0.95, 1.05))


# ── Core calculation ──────────────────────────────────────────────────────────

async def calculate_settlement(
    db: AsyncSession,
    contract_id: str,
    period_start: datetime,
    period_end: datetime,
    deployment_id: str,
) -> SettlementStatement:
    """
    Calculate settlement for a contract over a billing period.

    1. Fetch completed FlexEvents for the contract in the period.
    2. Sum availability hours (hours the asset was available regardless of dispatch).
    3. Sum delivered kWh from M&V on each event.
    4. Calculate penalties for events where delivery < 80 % of target.
    5. Build and persist SettlementStatement with DRAFT status.
    """
    import math

    # Load contract to get rates
    contract = None
    availability_rate_minor = 500    # pence per hour default
    utilisation_rate_minor = 120     # pence per kWh default
    penalty_rate_minor = 60          # pence per kWh under-delivery
    currency_code = "GBP"

    try:
        from app.contracts.models import Contract  # type: ignore[attr-defined]

        contract_result = await db.execute(
            select(Contract).where(Contract.id == contract_id)  # type: ignore[attr-defined]
        )
        contract = contract_result.scalar_one_or_none()
        if contract:
            import json
            rates_raw = getattr(contract, "payment_rates", None)
            if rates_raw:
                try:
                    rates = json.loads(rates_raw) if isinstance(rates_raw, str) else rates_raw
                    availability_rate_minor = int(rates.get("availability_pence_per_hour", 500))
                    utilisation_rate_minor = int(rates.get("utilisation_pence_per_kwh", 120))
                    penalty_rate_minor = int(rates.get("penalty_pence_per_kwh", 60))
                except Exception:
                    pass
            currency_code = getattr(contract, "currency_code", "GBP") or "GBP"
    except (ImportError, Exception):
        pass

    # Load completed flex events
    from app.dispatch.models import FlexEvent

    events_result = await db.execute(
        select(FlexEvent).where(
            FlexEvent.deployment_id == deployment_id,
            FlexEvent.contract_id == contract_id,
            FlexEvent.status == "COMPLETED",
            FlexEvent.start_time >= period_start,
            FlexEvent.start_time <= period_end,
        )
    )
    events = events_result.scalars().all()

    # Calculate period availability hours (fraction of contracted window)
    period_hours = (period_end - period_start).total_seconds() / 3600.0
    # Assume 90 % availability for demo; in production use asset availability calendar
    availability_hours = round(period_hours * 0.90, 2)

    # Sum delivered kWh and compute penalties
    total_delivered_kwh = 0.0
    total_missed_kwh = 0.0
    delivery_pcts: list = []

    for ev in events:
        target_kwh = ev.target_kw * (ev.duration_minutes / 60.0)
        delivered_kwh = (ev.delivered_kw or 0.0) * (ev.duration_minutes / 60.0)
        total_delivered_kwh += delivered_kwh

        delivery_pct = (delivered_kwh / target_kwh * 100.0) if target_kwh > 0 else 100.0
        delivery_pcts.append(delivery_pct)

        if delivery_pct < 80.0:
            missed_kwh = target_kwh - delivered_kwh
            total_missed_kwh += missed_kwh

    avg_delivery_pct = round(
        sum(delivery_pcts) / len(delivery_pcts) if delivery_pcts else 100.0, 1
    )

    # Payment calculations (all in minor units = pence / paise)
    availability_payment = int(availability_hours * availability_rate_minor)
    utilisation_payment = int(total_delivered_kwh * utilisation_rate_minor)
    penalty_amount = int(total_missed_kwh * penalty_rate_minor)
    gross_payment = availability_payment + utilisation_payment
    net_payment = gross_payment - penalty_amount

    statement = SettlementStatement(
        id=str(uuid.uuid4()),
        deployment_id=deployment_id,
        contract_id=contract_id,
        period_start=period_start,
        period_end=period_end,
        status="DRAFT",
        availability_hours=availability_hours,
        availability_rate_minor=availability_rate_minor,
        availability_payment_minor=availability_payment,
        delivered_kwh=round(total_delivered_kwh, 3),
        utilisation_rate_minor=utilisation_rate_minor,
        utilisation_payment_minor=utilisation_payment,
        missed_kwh=round(total_missed_kwh, 3),
        penalty_amount_minor=penalty_amount,
        gross_payment_minor=gross_payment,
        net_payment_minor=net_payment,
        currency_code=currency_code,
        events_count=len(events),
        avg_delivery_pct=avg_delivery_pct,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(statement)
    await db.flush()
    return statement


async def approve_settlement(
    db: AsyncSession,
    statement_id: str,
    user_id: str,
    user_email: str,
    deployment_id: str,
) -> SettlementStatement:
    """Approve a draft settlement statement (PROG_MGR or higher)."""
    result = await db.execute(
        select(SettlementStatement).where(
            SettlementStatement.id == statement_id,
            SettlementStatement.deployment_id == deployment_id,
        )
    )
    stmt = result.scalar_one_or_none()
    if not stmt:
        raise ValueError(f"Settlement statement {statement_id} not found")
    if stmt.status not in ("DRAFT", "PENDING_APPROVAL"):
        raise ValueError(f"Cannot approve statement in status {stmt.status}")

    stmt.status = "APPROVED"
    stmt.approved_by = user_email
    stmt.approved_at = datetime.now(timezone.utc)
    stmt.updated_at = datetime.now(timezone.utc)

    try:
        from app.audit import log_audit

        await log_audit(
            db,
            deployment_id=deployment_id,
            action="APPROVE",
            resource_type="settlement_statement",
            resource_id=statement_id,
            user_id=user_id,
            user_email=user_email,
        )
    except Exception:
        pass

    return stmt
