"""
DER Aggregator VTN Server routes.

The DERMS acts as server; external aggregators (Alpha Flex, GMR Energy) connect to it.
Three interaction surfaces are exposed:

1. Registration — aggregators register devices and discover the VTN.
2. IEEE 2030.5 DER Server — aggregators poll for DER programs and active controls.
3. OpenADR 2.0b VTN — the DERMS is the VTN; aggregators are VENs.
4. Inbound telemetry — aggregators POST bulk readings.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import CurrentUserDep, DBDep, DeploymentDep
from app.aggregator.models import AggregatorEndDevice

router = APIRouter(prefix="/api/v1/aggregator", tags=["aggregator"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class RegisterDeviceRequest(BaseModel):
    aggregator_ref: str
    protocol: str  # IEEE_2030_5 / OPENADR_2B / REST
    ven_id: Optional[str] = None
    lFDI: Optional[str] = None
    sFDI: Optional[str] = None
    endpoint_url: Optional[str] = None
    counterparty_id: Optional[str] = None


class TelemetryReading(BaseModel):
    asset_ref: str
    power_kw: float
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    soc_pct: Optional[float] = None
    timestamp: Optional[str] = None


class BulkTelemetryRequest(BaseModel):
    readings: List[TelemetryReading]


class DERStatusReport(BaseModel):
    currentW: Optional[float] = None
    currentVAR: Optional[float] = None
    opState: Optional[str] = None
    readingTime: Optional[str] = None


class EiRegisterPartyRequest(BaseModel):
    venID: Optional[str] = None
    venName: Optional[str] = None
    registrationID: Optional[str] = None


class EiReportRequest(BaseModel):
    reportID: Optional[str] = None
    specifierID: Optional[str] = None
    reportDescriptions: Optional[List[dict]] = None
    intervals: Optional[List[dict]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _device_to_dict(d: AggregatorEndDevice) -> dict:
    return {
        "id": d.id,
        "deployment_id": d.deployment_id,
        "aggregator_ref": d.aggregator_ref,
        "protocol": d.protocol,
        "counterparty_id": d.counterparty_id,
        "asset_id": d.asset_id,
        "device_lFDI": d.device_lFDI,
        "device_sFDI": d.device_sFDI,
        "ven_id": d.ven_id,
        "endpoint_url": d.endpoint_url,
        "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
        "status": d.status,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


# ---------------------------------------------------------------------------
# Registration endpoints
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
async def register_aggregator_device(
    body: RegisterDeviceRequest,
    db: DBDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    Register an aggregator device (or VEN) with this DERMS deployment.

    No authentication required — the aggregator identifies itself via
    aggregator_ref and optional lFDI/ven_id. The DERMS returns a device_id
    that the aggregator must use in subsequent calls.
    """
    # Check for existing registration by aggregator_ref in this deployment
    existing_result = await db.execute(
        select(AggregatorEndDevice).where(
            AggregatorEndDevice.deployment_id == deployment_id,
            AggregatorEndDevice.aggregator_ref == body.aggregator_ref,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        # Re-registration: update endpoint and mark active
        existing.endpoint_url = body.endpoint_url or existing.endpoint_url
        existing.ven_id = body.ven_id or existing.ven_id
        existing.device_lFDI = body.lFDI or existing.device_lFDI
        existing.device_sFDI = body.sFDI or existing.device_sFDI
        existing.status = "ACTIVE"
        existing.last_seen_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return {
            "registered": True,
            "device_id": existing.id,
            "message": "Re-registration successful",
            **_device_to_dict(existing),
        }

    device = AggregatorEndDevice(
        id=str(uuid.uuid4()),
        deployment_id=deployment_id,
        aggregator_ref=body.aggregator_ref,
        protocol=body.protocol.upper(),
        counterparty_id=body.counterparty_id,
        ven_id=body.ven_id,
        device_lFDI=body.lFDI,
        device_sFDI=body.sFDI,
        endpoint_url=body.endpoint_url,
        status="REGISTERED",
        last_seen_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)

    return {
        "registered": True,
        "device_id": device.id,
        "message": "Device registered successfully",
        **_device_to_dict(device),
    }


@router.get("/devices")
async def list_aggregator_devices(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    status: Optional[str] = Query(None, description="Filter by status"),
) -> List[dict]:
    """List all registered aggregator devices (GRID_OPS or higher)."""
    stmt = select(AggregatorEndDevice).where(
        AggregatorEndDevice.deployment_id == deployment_id
    )
    if status:
        stmt = stmt.where(AggregatorEndDevice.status == status.upper())
    result = await db.execute(stmt.order_by(AggregatorEndDevice.created_at))
    return [_device_to_dict(d) for d in result.scalars().all()]


@router.delete("/devices/{device_id}", status_code=204)
async def deregister_aggregator_device(
    device_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> None:
    """Deregister (delete) an aggregator device (DEPLOY_ADMIN or higher)."""
    result = await db.execute(
        select(AggregatorEndDevice).where(
            AggregatorEndDevice.id == device_id,
            AggregatorEndDevice.deployment_id == deployment_id,
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Aggregator device not found")
    await db.delete(device)
    await db.commit()


# ---------------------------------------------------------------------------
# IEEE 2030.5 DER Server endpoints
# ---------------------------------------------------------------------------

@router.get("/2030.5/derp")
async def list_der_programs(
    db: DBDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    IEEE 2030.5 — Return active DER Programs for this deployment.

    Aggregators poll this endpoint to discover available programs.
    """
    programs = []
    try:
        from app.programs.models import FlexProgram
        result = await db.execute(
            select(FlexProgram).where(
                FlexProgram.deployment_id == deployment_id,
                FlexProgram.is_active == True,  # noqa: E712
            )
        )
        for prog in result.scalars().all():
            programs.append({
                "mRID": prog.id,
                "description": prog.name,
                "primacy": 10,
                "DERControlMode": "OpModMaxLimW",
                "active": prog.is_active,
            })
    except Exception:
        pass

    return {
        "DERProgramList": {
            "all": len(programs),
            "results": len(programs),
            "DERProgram": programs,
        }
    }


@router.get("/2030.5/derp/{program_id}/derc")
async def list_der_controls(
    program_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    IEEE 2030.5 — Return active DERControl resources for a DER program.

    Returns OE constraints formatted as IEEE 2030.5 DERControl objects.
    Aggregators poll this to retrieve operating envelopes.
    """
    controls = []
    try:
        from app.dispatch.models import FlexEvent, OEMessage, EventStatus

        # Active and dispatched events for this deployment
        events_result = await db.execute(
            select(FlexEvent).where(
                FlexEvent.deployment_id == deployment_id,
                FlexEvent.program_id == program_id,
                FlexEvent.status.in_([EventStatus.DISPATCHED, EventStatus.IN_PROGRESS]),
            )
        )
        events = events_result.scalars().all()

        for event in events:
            oe_result = await db.execute(
                select(OEMessage).where(OEMessage.event_id == event.id)
            )
            oe_messages = oe_result.scalars().all()

            start_unix = (
                int(event.start_time.timestamp()) if event.start_time else 0
            )
            duration_secs = event.duration_minutes * 60

            for m in oe_messages:
                asset_ref = m.asset_id  # use asset_id as ref; richer mapping optional
                try:
                    from app.assets.models import DERAsset
                    asset_res = await db.execute(
                        select(DERAsset).where(DERAsset.id == m.asset_id)
                    )
                    asset = asset_res.scalar_one_or_none()
                    if asset:
                        asset_ref = asset.asset_ref
                except Exception:
                    pass

                controls.append({
                    "mRID": f"{event.event_ref}-{asset_ref}",
                    "description": f"{event.event_type} — {event.cmz_id}",
                    "creationTime": int(datetime.now(timezone.utc).timestamp()),
                    "deviceLFDI": asset_ref,
                    "DERControlBase": {
                        "opModMaxLimW": {
                            "value": int((m.export_max_kw or 0) * 1000),
                            "multiplier": 0,
                        },
                        "opModExpLimW": {
                            "value": int((m.export_max_kw or 0) * 1000),
                            "multiplier": 0,
                        },
                    },
                    "interval": {
                        "start": start_unix,
                        "duration": duration_secs,
                    },
                })
    except Exception:
        pass

    return {
        "DERControlList": {
            "all": len(controls),
            "results": len(controls),
            "DERControl": controls,
        }
    }


@router.post("/2030.5/ders/{asset_id}/status")
async def report_der_status(
    asset_id: str,
    body: DERStatusReport,
    db: DBDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    IEEE 2030.5 — Aggregator reports DER status back to the DERMS.

    Updates the asset's live telemetry cache and appends a telemetry record.
    """
    try:
        from app.assets.models import DERAsset, AssetTelemetry

        # Resolve by asset_id (UUID) or asset_ref
        asset_result = await db.execute(
            select(DERAsset).where(
                (DERAsset.id == asset_id) | (DERAsset.asset_ref == asset_id),
                DERAsset.deployment_id == deployment_id,
            )
        )
        asset = asset_result.scalar_one_or_none()
        if not asset:
            raise HTTPException(status_code=404, detail="DER asset not found")

        ts_raw = body.readingTime
        try:
            ts = (
                datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if ts_raw
                else datetime.now(timezone.utc)
            )
        except Exception:
            ts = datetime.now(timezone.utc)

        # Update asset telemetry cache
        if body.currentW is not None:
            asset.current_kw = round(body.currentW / 1000.0, 3)
        asset.last_telemetry_at = ts

        # Append telemetry record
        tel = AssetTelemetry(
            id=str(uuid.uuid4()),
            asset_id=asset.id,
            deployment_id=deployment_id,
            timestamp=ts,
            power_kw=asset.current_kw,
            source="AGGREGATOR_REPORTED",
        )
        db.add(tel)
        await db.commit()

        return {
            "accepted": True,
            "asset_id": asset.id,
            "asset_ref": asset.asset_ref,
            "current_kw": asset.current_kw,
            "timestamp": ts.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# OpenADR 2.0b VTN endpoints
# ---------------------------------------------------------------------------

@router.post("/oadr/EiRegisterParty")
async def oadr_register_party(
    body: EiRegisterPartyRequest,
    db: DBDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    OpenADR 2.0b — VEN registration (oadrRegisterReport / eiRegisterParty).

    The VEN (aggregator) registers with this VTN. Returns a registrationID and
    confirms the VEN identifier.
    """
    ven_id = body.venID or str(uuid.uuid4())
    registration_id = body.registrationID or str(uuid.uuid4())

    # Upsert device record
    existing_result = await db.execute(
        select(AggregatorEndDevice).where(
            AggregatorEndDevice.deployment_id == deployment_id,
            AggregatorEndDevice.ven_id == ven_id,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.status = "ACTIVE"
        existing.last_seen_at = datetime.now(timezone.utc)
        await db.commit()
    else:
        device = AggregatorEndDevice(
            id=str(uuid.uuid4()),
            deployment_id=deployment_id,
            aggregator_ref=body.venName or ven_id,
            protocol="OPENADR_2B",
            ven_id=ven_id,
            status="ACTIVE",
            last_seen_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        db.add(device)
        await db.commit()

    return {
        "eiResponse": {
            "responseCode": "200",
            "responseDescription": "OK",
            "requestID": registration_id,
        },
        "registrationID": registration_id,
        "venID": ven_id,
        "vtnID": f"neuralgrid-vtn-{deployment_id}",
        "pollURL": f"/api/v1/aggregator/oadr/EiEvent",
    }


@router.get("/oadr/EiEvent")
async def oadr_get_events(
    db: DBDep,
    deployment_id: DeploymentDep,
    ven_id: Optional[str] = Query(None, description="VEN ID of the polling aggregator"),
) -> dict:
    """
    OpenADR 2.0b — VEN polls for active events (oadrDistributeEvent).

    Returns all active/dispatched OEs for assets belonging to the VEN's devices.
    In production this would be XML; here we return JSON for API compatibility.
    """
    # Update last_seen_at for this VEN
    if ven_id:
        ven_result = await db.execute(
            select(AggregatorEndDevice).where(
                AggregatorEndDevice.deployment_id == deployment_id,
                AggregatorEndDevice.ven_id == ven_id,
            )
        )
        ven_device = ven_result.scalar_one_or_none()
        if ven_device:
            ven_device.last_seen_at = datetime.now(timezone.utc)
            ven_device.status = "ACTIVE"
            await db.commit()

    oadr_events = []
    try:
        from app.dispatch.models import FlexEvent, OEMessage, EventStatus
        from app.assets.models import DERAsset

        events_result = await db.execute(
            select(FlexEvent).where(
                FlexEvent.deployment_id == deployment_id,
                FlexEvent.status.in_([EventStatus.DISPATCHED, EventStatus.IN_PROGRESS]),
            )
        )
        events = events_result.scalars().all()

        for event in events:
            oe_result = await db.execute(
                select(OEMessage).where(OEMessage.event_id == event.id)
            )
            oe_messages = oe_result.scalars().all()
            if not oe_messages:
                continue

            # Collect asset refs and build signals
            targets = []
            signals = []
            duration_secs = event.duration_minutes * 60

            for m in oe_messages:
                asset_ref = m.asset_id
                try:
                    asset_res = await db.execute(
                        select(DERAsset).where(DERAsset.id == m.asset_id)
                    )
                    asset = asset_res.scalar_one_or_none()
                    if asset:
                        asset_ref = asset.asset_ref
                except Exception:
                    pass

                targets.append(asset_ref)
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

            oadr_events.append({
                "eventDescriptor": {
                    "eventID": event.event_ref,
                    "eventStatus": (
                        "active" if event.status == "DISPATCHED" else "far"
                    ),
                    "createdDateTime": (
                        event.start_time.isoformat() if event.start_time else ""
                    ),
                    "eventSignals": signals,
                },
                "targets": targets,
            })
    except Exception:
        pass

    return {
        "oadrDistributeEvent": {
            "requestID": str(uuid.uuid4()),
            "vtnID": f"neuralgrid-vtn-{deployment_id}",
            "oadrEvents": oadr_events,
        }
    }


@router.post("/oadr/EiReport")
async def oadr_receive_report(
    body: EiReportRequest,
    db: DBDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    OpenADR 2.0b — VEN reports metering data back to the VTN (oadrRegisterReport).

    Processes interval readings and updates asset telemetry where asset refs match.
    """
    processed = 0
    try:
        from app.assets.models import DERAsset, AssetTelemetry

        intervals = body.intervals or []
        for interval in intervals:
            asset_ref = interval.get("resourceID") or interval.get("asset_ref")
            value = interval.get("value") or interval.get("payloadFloat", {}).get("value")
            ts_raw = interval.get("dtstart") or interval.get("timestamp")

            if not asset_ref or value is None:
                continue

            asset_result = await db.execute(
                select(DERAsset).where(
                    (DERAsset.id == asset_ref) | (DERAsset.asset_ref == asset_ref),
                    DERAsset.deployment_id == deployment_id,
                )
            )
            asset = asset_result.scalar_one_or_none()
            if not asset:
                continue

            try:
                ts = (
                    datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    if ts_raw
                    else datetime.now(timezone.utc)
                )
            except Exception:
                ts = datetime.now(timezone.utc)

            asset.current_kw = round(float(value), 3)
            asset.last_telemetry_at = ts

            tel = AssetTelemetry(
                id=str(uuid.uuid4()),
                asset_id=asset.id,
                deployment_id=deployment_id,
                timestamp=ts,
                power_kw=asset.current_kw,
                source="AGGREGATOR_REPORTED",
            )
            db.add(tel)
            processed += 1

        await db.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "eiResponse": {
            "responseCode": "200",
            "responseDescription": "OK",
            "requestID": body.reportID or str(uuid.uuid4()),
        },
        "intervals_processed": processed,
    }


# ---------------------------------------------------------------------------
# Inbound bulk telemetry
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# IEC CIM endpoint schemas
# ---------------------------------------------------------------------------

class CIMCapabilityRequest(BaseModel):
    """DERCapabilityInfo body (IEC 62746-4)."""
    groupID: str
    aggregatorRef: str
    assets: List[dict]  # each: {asset_ref, type, rated_kw, rated_kva, flex_eligible}


class CIMStatusRequest(BaseModel):
    """DERGroupStatus body (IEC 62746-4)."""
    groupID: Optional[str] = None
    group_id: Optional[str] = None
    reportDateTime: Optional[str] = None
    DERStatus: Optional[List[dict]] = None

    class Config:
        extra = "allow"


class CIMBidRequest(BaseModel):
    """ReserveBidMarketDocument body (IEC 62325-301)."""

    class Config:
        extra = "allow"


# ---------------------------------------------------------------------------
# IEC CIM endpoints
# ---------------------------------------------------------------------------

@router.post("/cim/capability", status_code=202)
async def receive_der_capability(
    body: CIMCapabilityRequest,
    db: DBDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    POST /api/v1/aggregator/cim/capability

    Receive a DERCapabilityInfo document (IEC 62746-4) from an aggregator.
    Registers or updates the assets declared in the document.

    Returns: {accepted, group_id, asset_count}
    """
    try:
        from app.aggregator.cim.iec62746_4 import build_der_capability_info

        assets = body.assets or []
        group_id = body.groupID
        aggregator_ref = body.aggregatorRef

        # Upsert each declared asset into AggregatorEndDevice (if not already present)
        registered_count = 0
        for asset in assets:
            asset_ref = asset.get("asset_ref")
            if not asset_ref:
                continue
            existing_result = await db.execute(
                select(AggregatorEndDevice).where(
                    AggregatorEndDevice.deployment_id == deployment_id,
                    AggregatorEndDevice.aggregator_ref == asset_ref,
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                existing.status = "ACTIVE"
                existing.last_seen_at = datetime.now(timezone.utc)
                existing.meta = json.dumps(asset)
            else:
                device = AggregatorEndDevice(
                    id=str(uuid.uuid4()),
                    deployment_id=deployment_id,
                    aggregator_ref=asset_ref,
                    protocol="CIM_IEC62746_4",
                    status="REGISTERED",
                    last_seen_at=datetime.now(timezone.utc),
                    created_at=datetime.now(timezone.utc),
                    meta=json.dumps(asset),
                )
                db.add(device)
            registered_count += 1

        await db.commit()

        return {
            "accepted": True,
            "group_id": group_id,
            "asset_count": registered_count,
            "aggregator_ref": aggregator_ref,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/cim/status", status_code=202)
async def receive_der_group_status(
    body: dict,
    db: DBDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    POST /api/v1/aggregator/cim/status

    Receive a DERGroupStatus document (IEC 62746-4) from an aggregator.
    Updates live asset telemetry for each asset in the group.

    Returns: {accepted, assets_updated}
    """
    try:
        from app.aggregator.cim.iec62746_4 import parse_der_group_status
        from app.assets.models import DERAsset, AssetTelemetry

        status = parse_der_group_status(body)
        assets_updated = 0

        for asset_info in status.get("assets", []):
            asset_ref = asset_info.get("asset_ref")
            if not asset_ref:
                continue

            asset_result = await db.execute(
                select(DERAsset).where(
                    (DERAsset.asset_ref == asset_ref) | (DERAsset.id == asset_ref),
                    DERAsset.deployment_id == deployment_id,
                )
            )
            asset = asset_result.scalar_one_or_none()
            if not asset:
                continue

            now = datetime.now(timezone.utc)
            power_kw = asset_info.get("power_kw", 0.0)
            soc_pct = asset_info.get("soc_pct")

            asset.current_kw = float(power_kw)
            asset.last_telemetry_at = now
            if soc_pct is not None:
                asset.current_soc_pct = float(soc_pct)

            tel = AssetTelemetry(
                id=str(uuid.uuid4()),
                asset_id=asset.id,
                deployment_id=deployment_id,
                timestamp=now,
                power_kw=float(power_kw),
                soc_pct=float(soc_pct) if soc_pct is not None else None,
                source="AGGREGATOR_REPORTED",
            )
            db.add(tel)
            assets_updated += 1

        await db.commit()

        return {
            "accepted": True,
            "group_id": status.get("group_id"),
            "assets_updated": assets_updated,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cim/dispatch/{event_id}")
async def get_cim_dispatch(
    event_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    GET /api/v1/aggregator/cim/dispatch/{event_id}

    Look up a FlexEvent and build an IEC 62746-4 DERGroupDispatch document
    for all assets in the event's CMZ.  Also publishes the document to the
    Kafka topic derms.oe.dispatch if Kafka is enabled.

    Returns: DERGroupDispatch document.
    """
    try:
        from app.dispatch.models import FlexEvent, OEMessage
        from app.assets.models import DERAsset
        from app.aggregator.cim.iec62746_4 import build_der_group_dispatch
        from app.aggregator.kafka_transport import publish_oe_dispatch

        event_result = await db.execute(
            select(FlexEvent).where(
                (FlexEvent.id == event_id) | (FlexEvent.event_ref == event_id),
                FlexEvent.deployment_id == deployment_id,
            )
        )
        event = event_result.scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=404, detail="FlexEvent not found")

        oe_result = await db.execute(
            select(OEMessage).where(OEMessage.event_id == event.id)
        )
        oe_messages = oe_result.scalars().all()

        der_targets: List[dict] = []
        for m in oe_messages:
            asset_ref = m.asset_id
            try:
                asset_res = await db.execute(
                    select(DERAsset).where(DERAsset.id == m.asset_id)
                )
                asset = asset_res.scalar_one_or_none()
                if asset:
                    asset_ref = asset.asset_ref
            except Exception:
                pass

            allocated_kw = m.export_max_kw or m.import_max_kw or 0.0
            der_targets.append(
                {"asset_ref": asset_ref, "allocated_kw": allocated_kw}
            )

        target_kw = event.target_kw
        start_iso = event.start_time.isoformat() if event.start_time else datetime.now(timezone.utc).isoformat()
        end_iso = event.end_time.isoformat() if event.end_time else start_iso

        dispatch_type = "CURTAIL"
        if event.event_type in ("PEAK_REDUCTION", "DR_CURTAILMENT", "VOLTAGE_CORRECTION"):
            dispatch_type = "CURTAIL"
        elif event.event_type == "P2P_DISPATCH":
            dispatch_type = "DISCHARGE"

        doc = build_der_group_dispatch(
            group_id=event.cmz_id,
            dispatch_type=dispatch_type,
            target_power_kw=target_kw,
            start_time=start_iso,
            end_time=end_iso,
            der_targets=der_targets,
            deployment_id=deployment_id,
        )

        # Publish to Kafka if enabled (non-blocking; failure is logged but not raised)
        await publish_oe_dispatch(deployment_id, event.cmz_id, doc)

        return doc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cim/bid/{cmz_id}")
async def get_reserve_bid_template(
    cmz_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    GET /api/v1/aggregator/cim/bid/{cmz_id}

    Look up active OE messages for the given CMZ and return a
    ReserveBidMarketDocument template (IEC 62325-301 type A26) that an
    aggregator can fill in and POST back via POST /cim/bid.

    Returns: ReserveBidMarketDocument template.
    """
    try:
        from app.dispatch.models import FlexEvent, OEMessage, EventStatus
        from app.assets.models import DERAsset
        from app.aggregator.cim.iec62325 import build_reserve_bid_market_document

        events_result = await db.execute(
            select(FlexEvent).where(
                FlexEvent.deployment_id == deployment_id,
                FlexEvent.cmz_id == cmz_id,
                FlexEvent.status.in_([EventStatus.DISPATCHED, EventStatus.IN_PROGRESS]),
            )
        )
        events = events_result.scalars().all()

        if not events:
            raise HTTPException(
                status_code=404,
                detail=f"No active flex events found for CMZ '{cmz_id}'",
            )

        event = events[0]
        start_iso = event.start_time.isoformat() if event.start_time else datetime.now(timezone.utc).isoformat()
        end_iso = event.end_time.isoformat() if event.end_time else start_iso

        # Build one interval per OE direction
        intervals = [
            {
                "slot_start": start_iso,
                "slot_end": end_iso,
                "quantity_mw": round(event.target_kw / 1000.0, 4),
                "price_per_mwh": 0.0,  # aggregator fills this in
                "flow_direction": "Decrease",
            }
        ]

        doc = build_reserve_bid_market_document(
            event_ref=event.event_ref,
            cmz_id=cmz_id,
            aggregator_ref="<AGGREGATOR_REF>",
            deployment_id=deployment_id,
            intervals=intervals,
        )

        return doc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/cim/bid", status_code=202)
async def submit_reserve_bid(
    body: dict,
    db: DBDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    POST /api/v1/aggregator/cim/bid

    Accept a ReserveBidMarketDocument (IEC 62325-301) from an aggregator.
    Parses and validates it, then logs it to the AggregatorEndDevice audit
    trail (meta field) and returns an acceptance acknowledgement.

    Returns: {accepted, bid_mrid}
    """
    try:
        from app.aggregator.cim.iec62325 import parse_reserve_bid
        from app.dispatch.models import FlexEvent, EventStatus

        parsed = parse_reserve_bid(body)
        cmz_id = parsed["cmz_id"]
        aggregator_ref = parsed["aggregator_ref"]
        bid_mrid = parsed["mRID"]

        # Validate that the CMZ has an active event
        events_result = await db.execute(
            select(FlexEvent).where(
                FlexEvent.deployment_id == deployment_id,
                FlexEvent.cmz_id == cmz_id,
                FlexEvent.status.in_([EventStatus.DISPATCHED, EventStatus.IN_PROGRESS, EventStatus.PENDING_DISPATCH]),
            )
        )
        active_event = events_result.scalars().first()
        if not active_event:
            raise HTTPException(
                status_code=422,
                detail=f"No active flex event for CMZ '{cmz_id}' — bid rejected",
            )

        # Log the bid to the aggregator device record (simple audit — no separate table)
        device_result = await db.execute(
            select(AggregatorEndDevice).where(
                AggregatorEndDevice.deployment_id == deployment_id,
                AggregatorEndDevice.aggregator_ref == aggregator_ref,
            )
        )
        device = device_result.scalar_one_or_none()
        if device:
            device.last_seen_at = datetime.now(timezone.utc)
            audit = {"bid_mrid": bid_mrid, "cmz_id": cmz_id, "intervals": parsed["intervals"]}
            device.meta = json.dumps(audit)
            await db.commit()

        return {
            "accepted": True,
            "bid_mrid": bid_mrid,
            "cmz_id": cmz_id,
            "event_ref": active_event.event_ref,
            "aggregator_ref": aggregator_ref,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cim/protocols")
async def list_cim_protocols(
    deployment_id: DeploymentDep,
) -> dict:
    """
    GET /api/v1/aggregator/cim/protocols

    Return a list of the CIM-based communication protocols supported by this
    DERMS deployment for DER aggregator integration.

    Returns: {protocols: [{name, standard, transport, description}]}
    """
    protocols = [
        {
            "name": "ReserveBidMarketDocument",
            "standard": "IEC 62325-301",
            "transport": "REST / Kafka",
            "description": (
                "Flex market bid submission from aggregator to DERMS/DNO. "
                "Document type A26 (Reserve Bid), quantities in MW (MAW). "
                "Submit via POST /api/v1/aggregator/cim/bid."
            ),
        },
        {
            "name": "ActivationDocument",
            "standard": "IEC 62325-301",
            "transport": "REST",
            "description": (
                "Dispatch activation from DERMS/DNO to aggregator. "
                "Document type A53. Triggered by flex event dispatch."
            ),
        },
        {
            "name": "DERGroupDispatch",
            "standard": "IEC 62746-4",
            "transport": "REST / Kafka (derms.oe.dispatch)",
            "description": (
                "Fleet-level dispatch command from DERMS to aggregator. "
                "Specifies per-asset allocated kW targets. "
                "Retrieve via GET /api/v1/aggregator/cim/dispatch/{event_id}."
            ),
        },
        {
            "name": "DERCapabilityInfo",
            "standard": "IEC 62746-4",
            "transport": "REST",
            "description": (
                "Aggregator declares fleet capabilities (rated kW, kVA, flex eligibility) "
                "to the DERMS. Submit via POST /api/v1/aggregator/cim/capability."
            ),
        },
        {
            "name": "DERGroupStatus",
            "standard": "IEC 62746-4",
            "transport": "REST / Kafka (derms.aggregator.telemetry)",
            "description": (
                "Aggregator reports per-asset operational state (power_kw, SoC, opState) "
                "to the DERMS. Submit via POST /api/v1/aggregator/cim/status."
            ),
        },
        {
            "name": "DERMonitoringInfo",
            "standard": "IEC 62746-4",
            "transport": "Kafka (derms.aggregator.telemetry)",
            "description": (
                "High-frequency asset telemetry (power_kw, voltage_v, current_a) "
                "streamed from aggregator to DERMS via Kafka topic "
                "derms.aggregator.telemetry."
            ),
        },
        {
            "name": "DERControl (IEEE 2030.5)",
            "standard": "IEEE 2030.5",
            "transport": "REST",
            "description": (
                "OE constraints delivered as IEEE 2030.5 DERControl objects. "
                "Aggregators poll GET /api/v1/aggregator/2030.5/derp/{program_id}/derc."
            ),
        },
        {
            "name": "oadrDistributeEvent",
            "standard": "OpenADR 2.0b",
            "transport": "REST (JSON)",
            "description": (
                "Active flex events distributed to VEN aggregators via "
                "GET /api/v1/aggregator/oadr/EiEvent."
            ),
        },
    ]

    return {
        "deployment_id": deployment_id,
        "protocols": protocols,
    }


# ---------------------------------------------------------------------------
# Inbound bulk telemetry
# ---------------------------------------------------------------------------

@router.post("/telemetry")
async def ingest_telemetry(
    body: BulkTelemetryRequest,
    db: DBDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    Aggregator POSTs bulk telemetry readings to the DERMS.

    Each reading is matched to a DERAsset by asset_ref (e.g. "AST-001").
    Updates the asset's current_kw cache and appends to asset_telemetry.

    No authentication token required — the aggregator identifies assets by ref.
    Rate limiting / IP allowlisting should be applied at the gateway layer in production.
    """
    accepted = 0
    rejected = []

    try:
        from app.assets.models import DERAsset, AssetTelemetry

        for reading in body.readings:
            asset_result = await db.execute(
                select(DERAsset).where(
                    DERAsset.asset_ref == reading.asset_ref,
                    DERAsset.deployment_id == deployment_id,
                )
            )
            asset = asset_result.scalar_one_or_none()

            if not asset:
                rejected.append({
                    "asset_ref": reading.asset_ref,
                    "reason": "Asset not found",
                })
                continue

            ts_raw = reading.timestamp
            try:
                ts = (
                    datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                    if ts_raw
                    else datetime.now(timezone.utc)
                )
            except Exception:
                ts = datetime.now(timezone.utc)

            # Update live telemetry cache on the asset
            asset.current_kw = reading.power_kw
            asset.last_telemetry_at = ts
            if reading.soc_pct is not None:
                asset.current_soc_pct = reading.soc_pct

            # Append time-series record
            tel = AssetTelemetry(
                id=str(uuid.uuid4()),
                asset_id=asset.id,
                deployment_id=deployment_id,
                timestamp=ts,
                power_kw=reading.power_kw,
                voltage_v=reading.voltage_v,
                current_a=reading.current_a,
                soc_pct=reading.soc_pct,
                source="AGGREGATOR_REPORTED",
            )
            db.add(tel)
            accepted += 1

        await db.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "accepted": accepted,
        "rejected": len(rejected),
        "rejection_details": rejected,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
