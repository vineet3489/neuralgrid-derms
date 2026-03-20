"""Business logic for Flexibility Programs."""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.core.utils import new_uuid, utcnow
from app.programs.models import Program, ProgramStatus, ProgramType
from app.programs.schemas import ProgramCreate, ProgramKPIs, ProgramUpdate


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _serialize_json(obj) -> Optional[str]:
    """Serialize a dict/list/Pydantic model to a JSON string, or return None."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump())
    if isinstance(obj, (dict, list)):
        return json.dumps(obj)
    return str(obj)


def _validate_activation(program: Program) -> None:
    """Raise HTTP 422 if the program fails activation prerequisites."""
    if not program.cmz_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot activate program without at least one CMZ assigned.",
        )
    today = date.today().isoformat()
    if program.end_date < today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot activate program: end_date is in the past.",
        )
    # P2P_TRADING is exempt from service_window_config requirement
    # enrolled_mw must be > 0
    if program.enrolled_mw <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot activate program with enrolled_mw = 0. Enroll contracts first.",
        )


async def _check_no_active_contracts(db: AsyncSession, program_id: str) -> None:
    """Raise HTTP 422 if the program has active contracts (blocks CLOSING/CLOSED transition)."""
    try:
        from app.contracts.models import Contract, ContractStatus  # noqa: PLC0415
        stmt = select(func.count(Contract.id)).where(
            Contract.program_id == program_id,
            Contract.status == ContractStatus.ACTIVE.value,
            Contract.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        count = result.scalar_one() or 0
        if count > 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot close program: {count} active contract(s) still exist.",
            )
    except ImportError:
        pass  # contracts module not yet installed — skip check


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def list_programs(
    db: AsyncSession,
    deployment_id: str,
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
) -> list[Program]:
    stmt = select(Program).where(
        Program.deployment_id == deployment_id,
        Program.deleted_at.is_(None),
    )
    if status_filter:
        stmt = stmt.where(Program.status == status_filter)
    if type_filter:
        stmt = stmt.where(Program.type == type_filter)
    stmt = stmt.order_by(Program.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_program(db: AsyncSession, program_id: str, deployment_id: str) -> Program:
    stmt = select(Program).where(
        Program.id == program_id,
        Program.deployment_id == deployment_id,
        Program.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    program = result.scalar_one_or_none()
    if not program:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Program {program_id} not found.",
        )
    return program


async def create_program(
    db: AsyncSession,
    data: ProgramCreate,
    deployment_id: str,
    user_id: str,
) -> Program:
    type_val = data.type.value if hasattr(data.type, "value") else str(data.type)
    program = Program(
        id=new_uuid(),
        deployment_id=deployment_id,
        name=data.name,
        type=type_val,
        status=ProgramStatus.DRAFT.value,
        description=data.description,
        service_window_config=_serialize_json(data.service_window_config),
        target_mw=data.target_mw,
        enrolled_mw=0.0,
        regulatory_basis=data.regulatory_basis,
        cmz_ids=_serialize_json(data.cmz_ids),
        notification_config=_serialize_json(data.notification_config),
        kpi_thresholds=_serialize_json(data.kpi_thresholds),
        max_events_per_day=data.max_events_per_day,
        max_events_per_season=data.max_events_per_season,
        min_rest_hours_between_events=data.min_rest_hours_between_events,
        start_date=data.start_date,
        end_date=data.end_date,
        stackable=data.stackable,
        created_by=user_id,
        created_at=utcnow(),
        updated_at=utcnow(),
        meta=_serialize_json(data.meta),
    )
    db.add(program)
    await db.flush()
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="CREATE",
        resource_type="program",
        resource_id=program.id,
        user_id=user_id,
        diff={"name": program.name, "type": program.type, "status": program.status},
    )
    return program


async def update_program(
    db: AsyncSession,
    program_id: str,
    data: ProgramUpdate,
    deployment_id: str,
    user_id: str,
) -> Program:
    program = await get_program(db, program_id, deployment_id)
    old_values = {
        "status": program.status,
        "name": program.name,
        "target_mw": program.target_mw,
    }

    update_data = data.model_dump(exclude_unset=True)

    # Handle status transitions that require extra validation
    if "status" in update_data:
        new_status = update_data["status"]
        new_status_val = new_status.value if hasattr(new_status, "value") else str(new_status)
        if new_status_val == ProgramStatus.ACTIVE.value:
            _validate_activation(program)
        if new_status_val in (ProgramStatus.CLOSING.value, ProgramStatus.CLOSED.value):
            await _check_no_active_contracts(db, program_id)
        update_data["status"] = new_status_val

    # Serialize JSON/enum fields
    for json_field in ("service_window_config", "notification_config", "kpi_thresholds", "meta"):
        if json_field in update_data:
            update_data[json_field] = _serialize_json(update_data[json_field])
    if "cmz_ids" in update_data:
        update_data["cmz_ids"] = _serialize_json(update_data["cmz_ids"])
    if "type" in update_data:
        tv = update_data["type"]
        update_data["type"] = tv.value if hasattr(tv, "value") else str(tv)

    for key, value in update_data.items():
        setattr(program, key, value)

    program.updated_at = utcnow()
    await db.flush()
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="UPDATE",
        resource_type="program",
        resource_id=program.id,
        user_id=user_id,
        diff={"before": old_values, "updated_fields": list(update_data.keys())},
    )
    return program


async def delete_program(
    db: AsyncSession,
    program_id: str,
    deployment_id: str,
    user_id: str,
) -> bool:
    program = await get_program(db, program_id, deployment_id)
    if program.status == ProgramStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot delete an ACTIVE program. Suspend or close it first.",
        )
    program.deleted_at = utcnow()
    program.updated_at = utcnow()
    await db.flush()
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="DELETE",
        resource_type="program",
        resource_id=program.id,
        user_id=user_id,
        diff={"name": program.name},
    )
    return True


async def get_program_kpis(
    db: AsyncSession,
    program_id: str,
    deployment_id: str,
) -> ProgramKPIs:
    # Verify program exists
    await get_program(db, program_id, deployment_id)

    contracts_count = 0
    try:
        from app.contracts.models import Contract  # noqa: PLC0415
        stmt = select(func.count(Contract.id)).where(
            Contract.program_id == program_id,
            Contract.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        contracts_count = result.scalar_one() or 0
    except ImportError:
        pass

    events_dispatched = 0
    avg_delivery_pct = 0.0
    total_cost_minor = 0
    try:
        from app.dispatch.models import DispatchEvent, DispatchStatus  # noqa: PLC0415
        stmt = select(func.count(DispatchEvent.id)).where(
            DispatchEvent.program_id == program_id,
            DispatchEvent.status == DispatchStatus.COMPLETED.value,
        )
        result = await db.execute(stmt)
        events_dispatched = result.scalar_one() or 0

        if events_dispatched > 0:
            stmt2 = select(func.avg(DispatchEvent.delivery_pct)).where(
                DispatchEvent.program_id == program_id,
                DispatchEvent.status == DispatchStatus.COMPLETED.value,
                DispatchEvent.delivery_pct.isnot(None),
            )
            result2 = await db.execute(stmt2)
            avg_delivery_pct = float(result2.scalar_one() or 0.0)
    except (ImportError, Exception):
        pass

    return ProgramKPIs(
        events_dispatched=events_dispatched,
        avg_delivery_pct=round(avg_delivery_pct, 2),
        total_cost_minor=total_cost_minor,
        contracts_count=contracts_count,
    )


async def clone_program(
    db: AsyncSession,
    program_id: str,
    new_name: str,
    new_start_date: str,
    new_end_date: str,
    deployment_id: str,
    user_id: str,
) -> Program:
    source = await get_program(db, program_id, deployment_id)
    clone_data = ProgramCreate(
        name=new_name,
        type=source.type,
        description=source.description,
        service_window_config=json.loads(source.service_window_config) if source.service_window_config else None,
        target_mw=source.target_mw,
        regulatory_basis=source.regulatory_basis,
        cmz_ids=json.loads(source.cmz_ids) if source.cmz_ids else None,
        notification_config=json.loads(source.notification_config) if source.notification_config else None,
        kpi_thresholds=json.loads(source.kpi_thresholds) if source.kpi_thresholds else None,
        max_events_per_day=source.max_events_per_day,
        max_events_per_season=source.max_events_per_season,
        min_rest_hours_between_events=source.min_rest_hours_between_events,
        start_date=new_start_date,
        end_date=new_end_date,
        stackable=source.stackable,
        meta=json.loads(source.meta) if source.meta else None,
    )
    new_program = await create_program(db, clone_data, deployment_id, user_id)
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="CLONE",
        resource_type="program",
        resource_id=new_program.id,
        user_id=user_id,
        diff={"source_program_id": program_id, "new_name": new_name},
    )
    return new_program


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

async def seed_demo_programs(db: AsyncSession) -> None:
    """Seed demonstration programs for SSEN and PUVVNL deployments. Idempotent."""
    stmt = select(func.count(Program.id)).where(
        Program.created_by == "system",
        Program.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    if (result.scalar_one() or 0) > 0:
        return  # Already seeded

    ssen_programs: list[ProgramCreate] = [
        ProgramCreate(
            name="SSEN Winter Peak Reduction 2025-26",
            type=ProgramType.PEAK_REDUCTION,
            target_mw=2.5,
            start_date="2025-11-01",
            end_date="2026-03-31",
            regulatory_basis="ENA-CPP-2024",
            cmz_ids=["CMZ-ORKNEY", "CMZ-SHETLAND"],
            service_window_config={
                "days": ["MON", "TUE", "WED", "THU", "FRI"],
                "hours": {"start": "17:00", "end": "21:00"},
                "months": ["NOV", "DEC", "JAN", "FEB", "MAR"],
                "tz": "Europe/London",
            },
        ),
        ProgramCreate(
            name="SSEN Dynamic Constraint Management 2026",
            type=ProgramType.DYNAMIC_CONSTRAINT,
            target_mw=1.0,
            start_date="2026-01-01",
            end_date="2026-12-31",
            regulatory_basis="RIIO-ED2",
            cmz_ids=["CMZ-SHETLAND"],
        ),
    ]
    for prog in ssen_programs:
        await create_program(db, prog, "ssen", "system")

    puvvnl_programs: list[ProgramCreate] = [
        ProgramCreate(
            name="PUVVNL Demand Response Pilot 2025",
            type=ProgramType.DEMAND_RESPONSE,
            target_mw=0.5,
            start_date="2025-04-01",
            end_date="2026-03-31",
            regulatory_basis="UPERC-DR-2025",
            cmz_ids=["CMZ-VARANASI-NORTH", "CMZ-VARANASI-SOUTH"],
        ),
        ProgramCreate(
            name="PM Surya Ghar P2P Trading Program",
            type=ProgramType.P2P_TRADING,
            target_mw=0.1,
            start_date="2025-04-01",
            end_date="2026-03-31",
            regulatory_basis="UPERC-P2P-2025",
            cmz_ids=["CMZ-VARANASI-NORTH"],
        ),
    ]
    for prog in puvvnl_programs:
        await create_program(db, prog, "puvvnl", "system")
