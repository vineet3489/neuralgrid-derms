"""Settlement API endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select

from app.core.deps import CurrentUserDep, DBDep, DeploymentDep
from app.settlement.models import SettlementStatement
from app.settlement.service import approve_settlement, calculate_settlement

router = APIRouter(prefix="/api/v1/settlement", tags=["settlement"])


class SettlementCalculateRequest(BaseModel):
    contract_id: str
    period_start: datetime
    period_end: datetime


def _stmt_to_dict(s: SettlementStatement) -> dict:
    return {
        "id": s.id,
        "deployment_id": s.deployment_id,
        "contract_id": s.contract_id,
        "period_start": s.period_start.isoformat(),
        "period_end": s.period_end.isoformat(),
        "status": s.status,
        "availability_hours": s.availability_hours,
        "availability_rate_minor": s.availability_rate_minor,
        "availability_payment_minor": s.availability_payment_minor,
        "delivered_kwh": s.delivered_kwh,
        "utilisation_rate_minor": s.utilisation_rate_minor,
        "utilisation_payment_minor": s.utilisation_payment_minor,
        "missed_kwh": s.missed_kwh,
        "penalty_amount_minor": s.penalty_amount_minor,
        "gross_payment_minor": s.gross_payment_minor,
        "net_payment_minor": s.net_payment_minor,
        "currency_code": s.currency_code,
        "events_count": s.events_count,
        "avg_delivery_pct": s.avg_delivery_pct,
        "approved_by": s.approved_by,
        "approved_at": s.approved_at.isoformat() if s.approved_at else None,
        "notes": s.notes,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
    }


@router.get("/statements")
async def list_statements(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    contract_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> List[dict]:
    stmt = select(SettlementStatement).where(
        SettlementStatement.deployment_id == deployment_id
    )
    if contract_id:
        stmt = stmt.where(SettlementStatement.contract_id == contract_id)
    if status:
        stmt = stmt.where(SettlementStatement.status == status.upper())
    stmt = stmt.order_by(desc(SettlementStatement.created_at)).limit(limit)
    result = await db.execute(stmt)
    return [_stmt_to_dict(s) for s in result.scalars().all()]


@router.get("/statements/{statement_id}")
async def get_statement(
    statement_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    result = await db.execute(
        select(SettlementStatement).where(
            SettlementStatement.id == statement_id,
            SettlementStatement.deployment_id == deployment_id,
        )
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Settlement statement not found")

    # Add LLM narrative if available
    d = _stmt_to_dict(s)
    try:
        from app.integrations.llm.claude import generate_settlement_narrative
        narrative = await generate_settlement_narrative(d, deployment_id)
        d["ai_narrative"] = narrative
    except Exception:
        pass
    return d


@router.post("/calculate")
async def calculate(
    body: SettlementCalculateRequest,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Calculate settlement for a contract period (creates DRAFT statement)."""
    try:
        s = await calculate_settlement(
            db,
            contract_id=body.contract_id,
            period_start=body.period_start,
            period_end=body.period_end,
            deployment_id=deployment_id,
        )
        await db.commit()
        await db.refresh(s)
        return _stmt_to_dict(s)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/statements/{statement_id}/approve")
async def approve_statement(
    statement_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Approve a settlement statement (PROG_MGR or higher)."""
    try:
        s = await approve_settlement(
            db,
            statement_id=statement_id,
            user_id=current_user.id,
            user_email=current_user.email,
            deployment_id=deployment_id,
        )
        await db.commit()
        await db.refresh(s)
        return _stmt_to_dict(s)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/statements/{statement_id}/dispute")
async def dispute_statement(
    statement_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    reason: Optional[str] = Query(None),
) -> dict:
    """Raise a dispute on a settlement statement."""
    result = await db.execute(
        select(SettlementStatement).where(
            SettlementStatement.id == statement_id,
            SettlementStatement.deployment_id == deployment_id,
        )
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Settlement statement not found")
    if s.status in ("PAID",):
        raise HTTPException(status_code=409, detail="Cannot dispute a paid statement")
    s.status = "DISPUTED"
    s.notes = (s.notes or "") + (f" | Disputed: {reason}" if reason else " | Disputed by operator")
    s.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(s)
    return _stmt_to_dict(s)
