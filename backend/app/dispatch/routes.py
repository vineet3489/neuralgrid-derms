"""Dispatch API — flex event lifecycle management."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select

from app.core.deps import CurrentUserDep, DBDep, DeploymentDep
from app.dispatch.models import EventStatus, FlexEvent, OEMessage
from app.dispatch.service import complete_event, create_flex_event, dispatch_event

router = APIRouter(prefix="/api/v1/events", tags=["dispatch"])


# ── Request schemas ───────────────────────────────────────────────────────────

class FlexEventCreate(BaseModel):
    cmz_id: str
    event_type: str
    trigger: str = "MANUAL_OPERATOR"
    target_kw: float
    start_time: datetime
    duration_minutes: int = 30
    program_id: Optional[str] = None
    contract_id: Optional[str] = None
    operator_notes: Optional[str] = None


# ── Response helper ───────────────────────────────────────────────────────────

def _event_to_dict(e: FlexEvent) -> dict:
    return {
        "id": e.id,
        "deployment_id": e.deployment_id,
        "program_id": e.program_id,
        "contract_id": e.contract_id,
        "cmz_id": e.cmz_id,
        "event_ref": e.event_ref,
        "event_type": e.event_type,
        "status": e.status,
        "trigger": e.trigger,
        "target_kw": e.target_kw,
        "dispatched_kw": e.dispatched_kw,
        "delivered_kw": e.delivered_kw,
        "start_time": e.start_time.isoformat() if e.start_time else None,
        "end_time": e.end_time.isoformat() if e.end_time else None,
        "duration_minutes": e.duration_minutes,
        "notification_sent_at": e.notification_sent_at.isoformat() if e.notification_sent_at else None,
        "dispatched_at": e.dispatched_at.isoformat() if e.dispatched_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        "operator_notes": e.operator_notes,
        "auto_generated": e.auto_generated,
        "asset_ids": json.loads(e.asset_ids) if e.asset_ids else [],
        "doe_values": json.loads(e.doe_values) if e.doe_values else {},
        "created_by": e.created_by,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/")
async def list_flex_events(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    status: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    stmt = select(FlexEvent).where(FlexEvent.deployment_id == deployment_id)
    if status:
        stmt = stmt.where(FlexEvent.status == status.upper())
    if event_type:
        stmt = stmt.where(FlexEvent.event_type == event_type.upper())
    stmt = stmt.order_by(desc(FlexEvent.created_at)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    events = result.scalars().all()
    return {"items": [_event_to_dict(e) for e in events], "total": len(events), "offset": offset}


@router.get("/active")
async def list_active_events(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> List[dict]:
    result = await db.execute(
        select(FlexEvent)
        .where(
            FlexEvent.deployment_id == deployment_id,
            FlexEvent.status.in_([EventStatus.DISPATCHED, EventStatus.IN_PROGRESS]),
        )
        .order_by(FlexEvent.start_time)
    )
    return [_event_to_dict(e) for e in result.scalars().all()]


@router.get("/history")
async def events_history(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    limit: int = Query(50, ge=1, le=200),
) -> List[dict]:
    result = await db.execute(
        select(FlexEvent)
        .where(
            FlexEvent.deployment_id == deployment_id,
            FlexEvent.status.in_([EventStatus.COMPLETED, EventStatus.FAILED, EventStatus.CANCELLED]),
        )
        .order_by(desc(FlexEvent.completed_at))
        .limit(limit)
    )
    events = result.scalars().all()
    return [
        {
            **_event_to_dict(e),
            "delivery_pct": round(
                (e.delivered_kw / e.target_kw * 100.0) if e.delivered_kw and e.target_kw else 0.0, 1
            ),
        }
        for e in events
    ]


@router.get("/{event_id}")
async def get_flex_event(
    event_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    result = await db.execute(
        select(FlexEvent).where(
            FlexEvent.id == event_id,
            FlexEvent.deployment_id == deployment_id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Include OE messages
    oe_result = await db.execute(
        select(OEMessage).where(OEMessage.event_id == event_id)
    )
    oe_messages = [
        {
            "id": m.id,
            "asset_id": m.asset_id,
            "direction": m.direction,
            "import_max_kw": m.import_max_kw,
            "export_max_kw": m.export_max_kw,
            "sent_at": m.sent_at.isoformat(),
            "ack_received": m.ack_received,
            "delivery_channel": m.delivery_channel,
        }
        for m in oe_result.scalars().all()
    ]
    return {**_event_to_dict(event), "oe_messages": oe_messages}


@router.post("/")
async def create_event(
    body: FlexEventCreate,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Create a flex event (GRID_OPS or higher)."""
    event = await create_flex_event(
        db,
        deployment_id=deployment_id,
        cmz_id=body.cmz_id,
        event_type=body.event_type,
        trigger=body.trigger,
        target_kw=body.target_kw,
        start_time=body.start_time,
        duration_minutes=body.duration_minutes,
        program_id=body.program_id,
        contract_id=body.contract_id,
        operator_notes=body.operator_notes,
        user_id=current_user.id,
        user_email=current_user.email,
    )
    await db.commit()
    await db.refresh(event)
    return _event_to_dict(event)


@router.post("/{event_id}/dispatch")
async def dispatch_flex_event(
    event_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Dispatch a flex event — sends OEs to assets (GRID_OPS or higher)."""
    try:
        event = await dispatch_event(
            db, event_id, deployment_id,
            user_email=current_user.email,
            user_id=current_user.id,
        )
        await db.commit()
        await db.refresh(event)
        return _event_to_dict(event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{event_id}/complete")
async def complete_flex_event(
    event_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Mark event as completed and run M&V calculation."""
    try:
        event = await complete_event(db, event_id, deployment_id)
        await db.commit()
        await db.refresh(event)
        return _event_to_dict(event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{event_id}/cancel")
async def cancel_flex_event(
    event_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    reason: Optional[str] = Query(None),
) -> dict:
    """Cancel a flex event (GRID_OPS or higher)."""
    result = await db.execute(
        select(FlexEvent).where(
            FlexEvent.id == event_id,
            FlexEvent.deployment_id == deployment_id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status in (EventStatus.COMPLETED, EventStatus.CANCELLED):
        raise HTTPException(status_code=409, detail=f"Event already in status {event.status}")

    event.status = EventStatus.CANCELLED
    event.operator_notes = (event.operator_notes or "") + (f" | Cancelled: {reason}" if reason else " | Cancelled by operator")
    event.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(event)
    return _event_to_dict(event)
