"""
Dispatch service — automated and manual flex event management.

Auto-dispatch loop evaluates the in-memory grid state every
dispatch_check_interval seconds and generates FlexEvents when
constraints are detected.  Manual dispatch is triggered via the
REST API.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.dispatch.models import EventStatus, FlexEvent, OEMessage

logger = logging.getLogger(__name__)


# ── Event reference counter (persists in memory for demo) ────────────────────
_event_counter: int = 0


def _next_event_ref(deployment_id: str) -> str:
    global _event_counter
    _event_counter += 1
    prefix = "SSEN" if deployment_id == "ssen" else "PUV"
    return f"EVT-{prefix}-{_event_counter:04d}"


# ── Greedy dispatch algorithm ─────────────────────────────────────────────────

async def calculate_optimal_dispatch(
    assets: list,
    target_kw: float,
    event_type: str,
    constraint_node_id: Optional[str] = None,
) -> List[dict]:
    """
    Greedy asset selection to meet target_kw of flex.

    Priority order:
      1. V2G (bidirectional — can export)
      2. BESS (can export if SoC > 20 %)
      3. V1G (can reduce charging load)
      4. HEAT_PUMP (shift-able load)
      5. PV (curtail export)

    For VOLTAGE events: only select assets at the affected DT node.

    Returns list of dicts: {asset_id, asset_name, dispatch_kw, asset_type, doe_export_max_kw}
    """
    # Filter: ONLINE assets only, skip tiny capacity
    MIN_KW = 1.0
    candidates = [
        a for a in assets
        if getattr(a, "status", "") in ("ONLINE", "CURTAILED")
        and getattr(a, "capacity_kw", 0) >= MIN_KW
    ]

    if constraint_node_id and event_type == "VOLTAGE_CORRECTION":
        candidates = [
            a for a in candidates
            if getattr(a, "dt_id", None) == constraint_node_id
        ]

    # Priority sort
    TYPE_PRIORITY = {"V2G": 0, "BESS": 1, "V1G": 2, "HEAT_PUMP": 3, "PV": 4}
    candidates.sort(key=lambda a: TYPE_PRIORITY.get(getattr(a, "type", ""), 99))

    plan: List[dict] = []
    remaining = target_kw

    for asset in candidates:
        if remaining <= 0.0:
            break
        atype = getattr(asset, "type", "")
        cap = getattr(asset, "capacity_kw", 0.0)
        current_kw = getattr(asset, "current_kw", 0.0) or 0.0
        soc = getattr(asset, "current_soc_pct", 50.0) or 50.0

        # Available flex capacity per asset type
        if atype == "V2G":
            available = cap * 0.9  # can export up to 90 % nameplate
        elif atype == "BESS" and soc > 20.0:
            available = cap * ((soc - 10.0) / 100.0)  # proportional to SoC
        elif atype == "V1G":
            available = max(0.0, current_kw * 0.8)  # can reduce charge by 80 %
        elif atype == "HEAT_PUMP":
            available = max(0.0, current_kw * 0.5)
        elif atype == "PV":
            available = abs(current_kw)  # curtail current export
        else:
            available = 0.0

        if available < MIN_KW:
            continue

        dispatch_kw = min(available, remaining)
        plan.append({
            "asset_id": asset.id,
            "asset_name": getattr(asset, "name", ""),
            "dispatch_kw": round(dispatch_kw, 2),
            "asset_type": atype,
            "doe_export_max_kw": round(
                max(0.0, abs(current_kw) - dispatch_kw), 2
            ) if atype == "PV" else None,
        })
        remaining -= dispatch_kw

    return plan


# ── Flex event CRUD ───────────────────────────────────────────────────────────

async def create_flex_event(
    db: AsyncSession,
    *,
    deployment_id: str,
    cmz_id: str,
    event_type: str,
    trigger: str,
    target_kw: float,
    start_time: datetime,
    duration_minutes: int = 30,
    program_id: Optional[str] = None,
    contract_id: Optional[str] = None,
    operator_notes: Optional[str] = None,
    auto_generated: bool = False,
    user_id: Optional[str] = None,
    user_email: str = "system",
) -> FlexEvent:
    event = FlexEvent(
        id=str(uuid.uuid4()),
        deployment_id=deployment_id,
        program_id=program_id,
        contract_id=contract_id,
        cmz_id=cmz_id,
        event_ref=_next_event_ref(deployment_id),
        event_type=event_type,
        status=EventStatus.PLANNED,
        trigger=trigger,
        target_kw=target_kw,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=duration_minutes),
        duration_minutes=duration_minutes,
        operator_notes=operator_notes,
        auto_generated=auto_generated,
        created_by=user_email,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(event)
    await db.flush()

    try:
        from app.audit import log_audit
        await log_audit(
            db,
            deployment_id=deployment_id,
            action="CREATE",
            resource_type="flex_event",
            resource_id=event.id,
            user_id=user_id,
            user_email=user_email,
        )
    except Exception:
        pass

    return event


async def dispatch_event(
    db: AsyncSession,
    event_id: str,
    deployment_id: str,
    user_email: str = "system",
    user_id: Optional[str] = None,
) -> FlexEvent:
    """
    Dispatch a flex event:
    1. Load assets for this deployment.
    2. Run greedy optimal dispatch.
    3. Generate OEMessages for each selected asset.
    4. Update asset DOE values in DB.
    5. Mark event as DISPATCHED.
    """
    result = await db.execute(
        select(FlexEvent).where(
            FlexEvent.id == event_id,
            FlexEvent.deployment_id == deployment_id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise ValueError(f"FlexEvent {event_id} not found")
    if event.status in (EventStatus.COMPLETED, EventStatus.CANCELLED, EventStatus.DISPATCHED):
        raise ValueError(f"Event is already in status {event.status}")

    # Load assets
    assets: list = []
    try:
        from app.assets.models import DERAsset

        assets_result = await db.execute(
            select(DERAsset).where(
                DERAsset.deployment_id == deployment_id,
                DERAsset.deleted_at.is_(None),
            )
        )
        assets = assets_result.scalars().all()
    except ImportError:
        pass

    # Constraint node for VOLTAGE events
    constraint_node = None
    if event.event_type == "VOLTAGE_CORRECTION" and event.asset_ids:
        try:
            ids = json.loads(event.asset_ids)
            constraint_node = ids[0] if ids else None
        except Exception:
            pass

    dispatch_plan = await calculate_optimal_dispatch(
        assets, event.target_kw, event.event_type, constraint_node
    )

    # Build asset id → asset map for DOE update
    asset_map = {a.id: a for a in assets}
    doe_values_dict: dict = {}
    total_dispatched = 0.0

    for item in dispatch_plan:
        aid = item["asset_id"]
        asset = asset_map.get(aid)
        if not asset:
            continue

        total_dispatched += item["dispatch_kw"]

        # Set new DOE (curtailment)
        new_export_max = item.get("doe_export_max_kw")
        if new_export_max is not None:
            asset.doe_export_max_kw = new_export_max
            asset.status = "CURTAILED"
        elif item["asset_type"] in ("V1G", "HEAT_PUMP"):
            # Reduce import limit
            existing_import = asset.doe_import_max_kw or asset.capacity_kw
            asset.doe_import_max_kw = max(0.0, existing_import - item["dispatch_kw"])
            asset.status = "CURTAILED"
        elif item["asset_type"] in ("V2G", "BESS"):
            # Set export max to encourage discharge
            asset.doe_export_max_kw = item["dispatch_kw"]
            asset.status = "ONLINE"

        doe_values_dict[aid] = {
            "import_max_kw": asset.doe_import_max_kw,
            "export_max_kw": asset.doe_export_max_kw,
        }

        # Create OEMessage record
        oe = OEMessage(
            id=str(uuid.uuid4()),
            event_id=event.id,
            asset_id=aid,
            direction="CURTAIL" if item["asset_type"] == "PV" else "SET_DOE",
            import_max_kw=asset.doe_import_max_kw,
            export_max_kw=asset.doe_export_max_kw,
            sent_at=datetime.now(timezone.utc),
            # Simulate acknowledgement for demo
            ack_received=random.random() > 0.05,
            ack_at=datetime.now(timezone.utc) if random.random() > 0.05 else None,
            delivery_channel="IEEE_2030_5" if deployment_id == "ssen" else "OPENADR",
        )
        db.add(oe)

    event.dispatched_kw = round(total_dispatched, 2)
    event.status = EventStatus.DISPATCHED
    event.dispatched_at = datetime.now(timezone.utc)
    event.asset_ids = json.dumps([item["asset_id"] for item in dispatch_plan])
    event.doe_values = json.dumps(doe_values_dict)
    event.updated_at = datetime.now(timezone.utc)

    try:
        from app.audit import log_audit
        await log_audit(
            db,
            deployment_id=deployment_id,
            action="DISPATCH",
            resource_type="flex_event",
            resource_id=event.id,
            user_email=user_email,
            user_id=user_id,
            diff={"dispatched_kw": event.dispatched_kw, "assets": len(dispatch_plan)},
        )
    except Exception:
        pass

    return event


async def complete_event(db: AsyncSession, event_id: str, deployment_id: str) -> FlexEvent:
    """
    Complete an event and calculate delivered_kw via M&V stub.
    In production this would query MDMS for interval metering data.
    """
    result = await db.execute(
        select(FlexEvent).where(
            FlexEvent.id == event_id,
            FlexEvent.deployment_id == deployment_id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise ValueError(f"FlexEvent {event_id} not found")

    # M&V stub: simulate 85-105 % delivery
    delivery_ratio = random.uniform(0.85, 1.05)
    event.delivered_kw = round(event.dispatched_kw * delivery_ratio, 2)
    event.status = EventStatus.COMPLETED
    event.completed_at = datetime.now(timezone.utc)
    event.updated_at = datetime.now(timezone.utc)

    # Restore asset DOE values
    if event.asset_ids:
        try:
            from app.assets.models import DERAsset

            asset_ids = json.loads(event.asset_ids)
            for aid in asset_ids:
                asset_result = await db.execute(
                    select(DERAsset).where(DERAsset.id == aid)
                )
                asset = asset_result.scalar_one_or_none()
                if asset and asset.status == "CURTAILED":
                    asset.status = "ONLINE"
                    asset.doe_export_max_kw = None
                    asset.doe_import_max_kw = None
        except Exception as exc:
            logger.warning("Could not restore asset DOEs after event completion: %s", exc)

    return event


# ── Automated dispatch loop ───────────────────────────────────────────────────

async def run_dispatch_cycle(db: AsyncSession) -> None:
    """
    Evaluate current grid state and issue operating envelopes as needed.

    Rules (from Varanasi prototype, enhanced):
    1. Feeder loading > 80 %  → create VOLTAGE_CORRECTION / DR_CURTAILMENT event
    2. DT voltage > 244 V     → curtail PV on that DT
    3. DT voltage < 216 V     → dispatch BESS on that DT
    4. Loading < 70 % AND previously curtailed → restore (hysteresis)
    5. Scheduled PLANNED events that should start now → dispatch them
    """
    from app.grid.simulation import get_grid_state, DEPLOYMENT_TOPOLOGIES

    for deployment_id in DEPLOYMENT_TOPOLOGIES.keys():
        state = get_grid_state(deployment_id)
        if not state:
            continue

        nodes = state.get("nodes", [])

        for node in nodes:
            loading = node.get("current_loading_pct", 0.0)
            v1 = node.get("voltage_l1_v") or 230.0
            node_id = node.get("node_id", "")
            cmz_id = node.get("cmz_id", "")

            # Check for feeder overload → curtail exports
            if node.get("node_type") == "FEEDER" and loading > settings.feeder_loading_warn:
                # Only create if no active event for this node
                existing = await db.execute(
                    select(FlexEvent).where(
                        FlexEvent.deployment_id == deployment_id,
                        FlexEvent.cmz_id == cmz_id,
                        FlexEvent.status.in_(["PLANNED", "DISPATCHED", "IN_PROGRESS"]),
                        FlexEvent.event_type == "DR_CURTAILMENT",
                    )
                )
                if not existing.scalar_one_or_none():
                    target_kw = (loading - 70.0) / 100.0 * (node.get("hosting_capacity_kw", 1000.0))
                    await create_flex_event(
                        db,
                        deployment_id=deployment_id,
                        cmz_id=cmz_id,
                        event_type="DR_CURTAILMENT",
                        trigger="AUTO_OVERLOAD",
                        target_kw=max(10.0, round(target_kw, 0)),
                        start_time=datetime.now(timezone.utc),
                        duration_minutes=30,
                        auto_generated=True,
                        operator_notes=f"Auto: feeder {node_id} loading {loading:.0f}%",
                    )
                    logger.info(
                        "Auto DR_CURTAILMENT event created for %s (loading=%.0f%%)",
                        node_id, loading
                    )

            # DT overvoltage → curtail PV
            if node.get("node_type") == "DISTRIBUTION_TRANSFORMER" and v1 > settings.voltage_high_warn:
                existing = await db.execute(
                    select(FlexEvent).where(
                        FlexEvent.deployment_id == deployment_id,
                        FlexEvent.cmz_id == cmz_id,
                        FlexEvent.status.in_(["PLANNED", "DISPATCHED", "IN_PROGRESS"]),
                        FlexEvent.event_type == "VOLTAGE_CORRECTION",
                    )
                )
                if not existing.scalar_one_or_none():
                    await create_flex_event(
                        db,
                        deployment_id=deployment_id,
                        cmz_id=cmz_id,
                        event_type="VOLTAGE_CORRECTION",
                        trigger="AUTO_VOLTAGE",
                        target_kw=20.0,
                        start_time=datetime.now(timezone.utc),
                        duration_minutes=15,
                        auto_generated=True,
                        operator_notes=f"Auto: DT {node_id} voltage {v1:.1f} V",
                    )

            # DT undervoltage → dispatch BESS
            if node.get("node_type") == "DISTRIBUTION_TRANSFORMER" and v1 < settings.voltage_low_warn:
                existing = await db.execute(
                    select(FlexEvent).where(
                        FlexEvent.deployment_id == deployment_id,
                        FlexEvent.cmz_id == cmz_id,
                        FlexEvent.status.in_(["PLANNED", "DISPATCHED", "IN_PROGRESS"]),
                        FlexEvent.event_type == "VOLTAGE_CORRECTION",
                    )
                )
                if not existing.scalar_one_or_none():
                    await create_flex_event(
                        db,
                        deployment_id=deployment_id,
                        cmz_id=cmz_id,
                        event_type="VOLTAGE_CORRECTION",
                        trigger="AUTO_VOLTAGE",
                        target_kw=15.0,
                        start_time=datetime.now(timezone.utc),
                        duration_minutes=15,
                        auto_generated=True,
                        operator_notes=f"Auto: DT {node_id} undervoltage {v1:.1f} V — dispatch BESS",
                    )

        # Hysteresis: release curtailment when feeder loading < 70 %
        overloaded_node_ids = {
            n["node_id"]
            for n in nodes
            if n.get("node_type") == "FEEDER" and n.get("current_loading_pct", 0) > settings.feeder_loading_warn
        }
        # Get all active CURTAILMENT events where loading has normalised
        active_events_result = await db.execute(
            select(FlexEvent).where(
                FlexEvent.deployment_id == deployment_id,
                FlexEvent.status.in_(["DISPATCHED", "IN_PROGRESS"]),
                FlexEvent.auto_generated == True,
            )
        )
        for ev in active_events_result.scalars().all():
            # If all feeders in the CMZ are now below 70 %, complete the event
            cmz_feeders = [
                n for n in nodes
                if n.get("cmz_id") == ev.cmz_id and n.get("node_type") == "FEEDER"
            ]
            all_clear = all(n.get("current_loading_pct", 0) < 70.0 for n in cmz_feeders)
            if all_clear and cmz_feeders:
                try:
                    await complete_event(db, ev.id, deployment_id)
                    logger.info("Auto-completed event %s (loading normalised)", ev.event_ref)
                except Exception as exc:
                    logger.warning("Could not auto-complete event %s: %s", ev.event_ref, exc)

        # Dispatch scheduled PLANNED events that should start now
        now = datetime.now(timezone.utc)
        scheduled_result = await db.execute(
            select(FlexEvent).where(
                FlexEvent.deployment_id == deployment_id,
                FlexEvent.status == EventStatus.PLANNED,
                FlexEvent.start_time <= now,
                FlexEvent.auto_generated == False,
            )
        )
        for ev in scheduled_result.scalars().all():
            try:
                await dispatch_event(db, ev.id, deployment_id, user_email="auto-scheduler")
                logger.info("Auto-dispatched scheduled event %s", ev.event_ref)
            except Exception as exc:
                logger.warning("Auto-dispatch failed for event %s: %s", ev.event_ref, exc)

    await db.commit()


async def dispatch_loop() -> None:
    """Background task: run dispatch cycle every dispatch_check_interval seconds."""
    logger.info("Dispatch loop started (interval=%ds)", settings.dispatch_check_interval)
    await asyncio.sleep(10)

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_dispatch_cycle(db)
        except Exception as exc:
            logger.error("Dispatch loop error: %s", exc, exc_info=True)
        await asyncio.sleep(settings.dispatch_check_interval)
