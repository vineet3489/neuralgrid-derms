"""Reporting API — summary reports, event statistics, settlement summaries, regulatory stubs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc, func, select

from app.core.deps import CurrentUserDep, DBDep, DeploymentDep

router = APIRouter(prefix="/api/v1/reports", tags=["reporting"])


# ── Platform summary ──────────────────────────────────────────────────────────

@router.get("/summary/{dep_id}")
async def platform_summary(
    dep_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
) -> dict:
    """High-level platform summary for a deployment."""
    from app.grid.simulation import get_grid_state
    from app.grid.models import GridAlert

    dep = dep_id.lower()
    state = get_grid_state(dep)

    # Count active alerts
    alert_count_result = await db.execute(
        select(func.count(GridAlert.id)).where(
            GridAlert.deployment_id == dep,
            GridAlert.resolved_at.is_(None),
        )
    )
    alert_count = alert_count_result.scalar() or 0

    # Event stats
    event_stats: dict = {}
    try:
        from app.dispatch.models import FlexEvent

        total_events_result = await db.execute(
            select(func.count(FlexEvent.id)).where(FlexEvent.deployment_id == dep)
        )
        completed_events_result = await db.execute(
            select(func.count(FlexEvent.id)).where(
                FlexEvent.deployment_id == dep,
                FlexEvent.status == "COMPLETED",
            )
        )
        event_stats = {
            "total": total_events_result.scalar() or 0,
            "completed": completed_events_result.scalar() or 0,
        }
    except Exception:
        pass

    # Settlement stats
    settlement_stats: dict = {}
    try:
        from app.settlement.models import SettlementStatement

        total_paid_result = await db.execute(
            select(func.sum(SettlementStatement.net_payment_minor)).where(
                SettlementStatement.deployment_id == dep,
                SettlementStatement.status == "APPROVED",
            )
        )
        settlement_stats = {
            "total_net_minor": total_paid_result.scalar() or 0,
        }
    except Exception:
        pass

    return {
        "deployment_id": dep,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "grid": {
            "total_gen_kw": state.get("total_gen_kw", 0.0),
            "total_load_kw": state.get("total_load_kw", 0.0),
            "assets_online": state.get("assets_online", 0),
            "assets_curtailed": state.get("assets_curtailed", 0),
            "active_alerts": alert_count,
        },
        "events": event_stats,
        "settlement": settlement_stats,
    }


# ── Events report ─────────────────────────────────────────────────────────────

@router.get("/events-report")
async def events_report(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    from_date: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
) -> dict:
    """Events summary for a date range."""
    try:
        from app.dispatch.models import FlexEvent
        from sqlalchemy import and_

        stmt = select(FlexEvent).where(FlexEvent.deployment_id == deployment_id)

        if from_date:
            stmt = stmt.where(FlexEvent.start_time >= datetime.fromisoformat(from_date))
        if to_date:
            stmt = stmt.where(FlexEvent.start_time <= datetime.fromisoformat(to_date + "T23:59:59"))

        result = await db.execute(stmt.order_by(desc(FlexEvent.start_time)))
        events = result.scalars().all()

        total_target_kw = sum(e.target_kw for e in events)
        total_dispatched_kw = sum(e.dispatched_kw or 0.0 for e in events)
        total_delivered_kw = sum(e.delivered_kw or 0.0 for e in events if e.delivered_kw is not None)
        completed = [e for e in events if e.status == "COMPLETED"]

        avg_delivery = (
            sum((e.delivered_kw or 0.0) / max(e.target_kw, 0.001) for e in completed)
            / len(completed) * 100.0
            if completed
            else 0.0
        )

        by_type: dict = {}
        for e in events:
            by_type.setdefault(e.event_type, {"count": 0, "target_kw_total": 0.0})
            by_type[e.event_type]["count"] += 1
            by_type[e.event_type]["target_kw_total"] += e.target_kw

        return {
            "deployment_id": deployment_id,
            "from_date": from_date,
            "to_date": to_date,
            "total_events": len(events),
            "completed_events": len(completed),
            "total_target_kw": round(total_target_kw, 1),
            "total_dispatched_kw": round(total_dispatched_kw, 1),
            "total_delivered_kw": round(total_delivered_kw, 1),
            "avg_delivery_pct": round(avg_delivery, 1),
            "by_event_type": by_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="Dispatch module not available")


# ── Settlement report ─────────────────────────────────────────────────────────

@router.get("/settlement-report")
async def settlement_report(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    contract_id: Optional[str] = Query(None),
) -> dict:
    """Settlement summary across all statements for the deployment."""
    try:
        from app.settlement.models import SettlementStatement

        stmt = select(SettlementStatement).where(
            SettlementStatement.deployment_id == deployment_id
        )
        if contract_id:
            stmt = stmt.where(SettlementStatement.contract_id == contract_id)
        stmt = stmt.order_by(desc(SettlementStatement.created_at))

        result = await db.execute(stmt)
        statements = result.scalars().all()

        by_status: dict = {}
        total_net = 0
        total_delivered_kwh = 0.0

        for s in statements:
            by_status.setdefault(s.status, {"count": 0, "net_minor": 0})
            by_status[s.status]["count"] += 1
            by_status[s.status]["net_minor"] += s.net_payment_minor
            total_net += s.net_payment_minor
            total_delivered_kwh += s.delivered_kwh

        return {
            "deployment_id": deployment_id,
            "total_statements": len(statements),
            "total_net_payment_minor": total_net,
            "total_delivered_kwh": round(total_delivered_kwh, 2),
            "by_status": by_status,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except ImportError:
        raise HTTPException(status_code=503, detail="Settlement module not available")


# ── Regulatory stubs ──────────────────────────────────────────────────────────

@router.get("/regulatory/{report_type}")
async def regulatory_report(
    report_type: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    Placeholder for regulatory reporting.

    Supported types:
    - ofgem_slc31e   : Ofgem Smart Metering Installation Condition 31E (SSEN)
    - uperc_der      : UPERC DER Connectivity Report (PUVVNL)
    - ssen_flexibility: SSEN Flexibility Annual Report
    - carbon_summary : Carbon avoidance summary
    """
    from app.grid.simulation import get_grid_state

    state = get_grid_state(deployment_id)
    total_gen = state.get("total_gen_kw", 0.0)

    REPORT_STUBS = {
        "ofgem_slc31e": {
            "title": "Ofgem SLC 31E — Smart Metering Installation Condition",
            "regulator": "Ofgem",
            "applicable_deployments": ["ssen"],
            "status": "STUB — production requires Ofgem MHHS API integration",
            "data": {
                "smart_meter_coverage_pct": 87.3,
                "der_registered_count": state.get("assets_online", 0),
                "total_enrolled_kw": total_gen,
            },
        },
        "uperc_der": {
            "title": "UPERC DER Connectivity Quarterly Report",
            "regulator": "UPERC (Uttar Pradesh Electricity Regulatory Commission)",
            "applicable_deployments": ["puvvnl"],
            "status": "STUB — production requires UPERC reporting portal integration",
            "data": {
                "der_registered_count": state.get("assets_online", 0),
                "total_capacity_kw": total_gen,
                "period": datetime.now(timezone.utc).strftime("%Y-Q%q"),
            },
        },
        "ssen_flexibility": {
            "title": "SSEN Flexibility Annual Report",
            "regulator": "Ofgem / SSEN",
            "applicable_deployments": ["ssen"],
            "status": "STUB",
            "data": {
                "total_flex_kw_available": state.get("assets_online", 0) * 5,
                "events_dispatched_ytd": 0,
                "avg_delivery_pct": 94.2,
            },
        },
        "carbon_summary": {
            "title": "Carbon Avoidance Summary",
            "applicable_deployments": ["ssen", "puvvnl"],
            "status": "STUB — production uses grid carbon intensity API",
            "data": {
                "renewable_gen_kw": total_gen,
                "estimated_carbon_avoided_kg_co2_per_hour": round(total_gen * 0.233, 1),
                "grid_intensity_g_per_kwh": 233,
            },
        },
    }

    report = REPORT_STUBS.get(report_type.lower())
    if not report:
        raise HTTPException(
            status_code=404,
            detail=f"Report type '{report_type}' not found. Available: {list(REPORT_STUBS.keys())}",
        )

    return {
        "report_type": report_type,
        "deployment_id": deployment_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **report,
    }
