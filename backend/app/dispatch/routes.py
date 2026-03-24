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

# OE formatter import — keep here so it is always available at module level
from app.assets.models import DERAsset  # noqa: F401 (used inside formatted endpoint)

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
        "notes": e.operator_notes,   # alias for frontend compatibility
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


@router.get("/{event_id}/oe-messages/formatted")
async def get_oe_messages_formatted(
    event_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    protocol: str = Query(
        "IEEE_2030_5",
        description="IEEE_2030_5 / OPENADR_2B / IEC_62746_4 / SSEN_IEC / RAW",
    ),
) -> dict:
    """
    Return OE messages formatted per the requested protocol.

    IEEE_2030_5  — DERControl resource JSON (as sent to an IEEE 2030.5 aggregator)
    OPENADR_2B   — oadrDistributeEvent JSON (would be XML in production)
    IEC_62746_4  — IEC 62746-4 Operating Envelope message
    RAW          — raw DB records with all fields
    """
    # Fetch event
    event_result = await db.execute(
        select(FlexEvent).where(
            FlexEvent.id == event_id,
            FlexEvent.deployment_id == deployment_id,
        )
    )
    event = event_result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Fetch OE messages
    oe_result = await db.execute(
        select(OEMessage).where(OEMessage.event_id == event_id)
    )
    oe_messages = oe_result.scalars().all()

    # Load asset info for names / refs
    asset_map: dict = {}
    try:
        from app.assets.models import DERAsset as _DERAsset
        if oe_messages:
            asset_ids = [m.asset_id for m in oe_messages]
            assets_result = await db.execute(
                select(_DERAsset).where(_DERAsset.id.in_(asset_ids))
            )
            asset_map = {a.id: a for a in assets_result.scalars().all()}
    except Exception:
        pass

    start_unix = int(event.start_time.timestamp()) if event.start_time else 0
    duration_secs = event.duration_minutes * 60

    proto = protocol.upper()

    # ── SSEN IEC MarketDocument ───────────────────────────────────────────────
    if proto == "SSEN_IEC":
        from app.dispatch import ssen_messages as _ssen

        oe_doc = _ssen.build_operating_envelope_doc(
            event=event,
            oe_messages=list(oe_messages),
            deployment_id=deployment_id,
            cmz_id=event.cmz_id,
        )

        start_iso = event.start_time.strftime("%Y-%m-%dT%H:%M:%SZ") if event.start_time else ""
        end_iso = event.end_time.strftime("%Y-%m-%dT%H:%M:%SZ") if event.end_time else ""

        # Total export capacity in MW for the flex offer / activation templates
        total_export_kw = sum((m.export_max_kw or 0.0) for m in oe_messages)
        total_export_mw = round(total_export_kw / 1000.0, 6)
        delivered_mw = round((event.delivered_kw or 0.0) / 1000.0, 6)

        envelope_mrid = (
            oe_doc["OperatingEnvelope_MarketDocument"]["mRID"]
        )

        # Aggregator ref — use first asset's counterparty or fall back to event ref
        aggregator_ref = event.event_ref
        if asset_map:
            first_asset = next(iter(asset_map.values()), None)
            if first_asset:
                aggregator_ref = getattr(first_asset, "counterparty_id", event.event_ref) or event.event_ref

        flex_offer_template = _ssen.build_flex_offer_doc(
            envelope_mrid=envelope_mrid,
            aggregator_ref=aggregator_ref,
            cmz_id=event.cmz_id,
            start_time=start_iso,
            end_time=end_iso,
            direction="Decrease",   # default: curtailment (export reduction)
            capacity_mw=total_export_mw,
        )

        activation_template = _ssen.build_activation_doc(
            event_ref=event.event_ref,
            requested_mw=total_export_mw,
            cmz_id=event.cmz_id,
        )

        performance_template = _ssen.build_performance_doc(
            event_ref=event.event_ref,
            delivered_mw=delivered_mw,
            cmz_id=event.cmz_id,
        )

        ack_template = _ssen.build_ack_doc(received_mrid=envelope_mrid)

        return {
            "protocol": "SSEN_IEC",
            "document_type": "OperatingEnvelope_MarketDocument",
            "document": oe_doc,
            "related_documents": {
                "flex_offer_template": flex_offer_template,
                "activation_template": activation_template,
                "performance_template": performance_template,
                "acknowledgement_template": ack_template,
            },
        }

    # ── IEEE 2030.5 ───────────────────────────────────────────────────────────
    if proto == "IEEE_2030_5":
        formatted = []
        for m in oe_messages:
            asset = asset_map.get(m.asset_id)
            asset_ref = getattr(asset, "asset_ref", m.asset_id)
            control: dict = {
                "mRID": f"{event.event_ref}-{asset_ref}",
                "description": f"{event.event_type} — {event.cmz_id}",
                "creationTime": int(datetime.now(timezone.utc).timestamp()),
                "deviceLFDI": asset_ref,
                "DERControlBase": {
                    "opModMaxLimW": {
                        "value": int((m.export_max_kw or 0) * 1000),
                        "multiplier": -3,
                        "unit": "W",
                    },
                },
                "interval": {
                    "start": start_unix,
                    "duration": duration_secs,
                },
                "primacy": 10,
                "status": 1 if event.status == "DISPATCHED" else 0,
                "_channel": m.delivery_channel,
                "_ack_received": m.ack_received,
            }
            if m.import_max_kw is not None:
                control["DERControlBase"]["opModImpLimW"] = {
                    "value": int(m.import_max_kw * 1000),
                    "multiplier": -3,
                    "unit": "W",
                }
            formatted.append(control)

        return {
            "protocol": "IEEE_2030_5",
            "event_ref": event.event_ref,
            "message_count": len(formatted),
            "messages": formatted,
        }

    # ── OpenADR 2.0b ──────────────────────────────────────────────────────────
    elif proto == "OPENADR_2B":
        targets: List[str] = []
        signals: List[dict] = []
        for m in oe_messages:
            asset = asset_map.get(m.asset_id)
            targets.append(getattr(asset, "asset_ref", m.asset_id))
            if m.export_max_kw is not None:
                signals.append({
                    "signalName": "LOAD_CONTROL",
                    "signalType": "delta",
                    "signalID": f"SIG-{m.id[:8]}",
                    "intervals": [
                        {
                            "uid": 0,
                            "duration": duration_secs,
                            "payloadFloat": {"value": -(m.export_max_kw)},
                        }
                    ],
                    "currentValue": {
                        "payloadFloat": {"value": -(m.export_max_kw or 0)}
                    },
                })

        return {
            "protocol": "OpenADR_2.0b",
            "oadrDistributeEvent": {
                "requestID": f"REQ-{event.event_ref}",
                "oadrEvents": [
                    {
                        "eiEvent": {
                            "eventDescriptor": {
                                "eventID": event.event_ref,
                                "modificationNumber": 0,
                                "marketContext": (
                                    f"http://neuralgrid.io/{deployment_id}"
                                ),
                                "eventStatus": (
                                    "active"
                                    if event.status == "DISPATCHED"
                                    else "far"
                                ),
                                "createdDateTime": (
                                    event.start_time.isoformat()
                                    if event.start_time
                                    else ""
                                ),
                                "vtnComment": event.operator_notes or "",
                            },
                            "eiActivePeriod": {
                                "dtstart": (
                                    event.start_time.isoformat()
                                    if event.start_time
                                    else ""
                                ),
                                "duration": f"PT{event.duration_minutes}M",
                            },
                            "eiEventSignals": {"eiEventSignal": signals},
                            "eiTarget": {"resourceID": targets},
                        },
                        "oadrResponseRequired": "always",
                    }
                ],
            },
        }

    # ── IEC 62746-4 ───────────────────────────────────────────────────────────
    elif proto == "IEC_62746_4":
        oes = []
        for m in oe_messages:
            asset = asset_map.get(m.asset_id)
            meter_id = getattr(asset, "meter_id", None) or m.asset_id
            oes.append({
                "operatingEnvelopeID": f"{event.event_ref}-{meter_id}",
                "meterID": meter_id,
                "startTime": (
                    event.start_time.isoformat() if event.start_time else ""
                ),
                "endTime": (
                    event.end_time.isoformat() if event.end_time else ""
                ),
                "importLimit_kW": m.import_max_kw,
                "exportLimit_kW": m.export_max_kw,
                "unit": "kW",
                "version": "IEC62746-4:2022",
                "issuerID": "neuralgrid-derms",
                "status": (
                    "ACTIVE" if event.status == "DISPATCHED" else "PENDING"
                ),
            })
        return {
            "protocol": "IEC_62746-4",
            "event_ref": event.event_ref,
            "operatingEnvelopes": oes,
        }

    # ── RAW ───────────────────────────────────────────────────────────────────
    else:
        return {
            "protocol": "RAW",
            "event_ref": event.event_ref,
            "messages": [
                {
                    "id": m.id,
                    "asset_id": m.asset_id,
                    "asset_ref": getattr(
                        asset_map.get(m.asset_id), "asset_ref", m.asset_id
                    ),
                    "direction": m.direction,
                    "import_max_kw": m.import_max_kw,
                    "export_max_kw": m.export_max_kw,
                    "sent_at": m.sent_at.isoformat(),
                    "ack_received": m.ack_received,
                    "delivery_channel": m.delivery_channel,
                }
                for m in oe_messages
            ],
        }


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
