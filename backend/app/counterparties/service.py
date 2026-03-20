"""Business logic for Counterparties."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.core.utils import new_uuid, utcnow
from app.counterparties.models import (
    Counterparty,
    CounterpartyStatus,
    CounterpartyType,
    PrequalificationCheck,
    PrequalStatus,
    CommCapability,
)
from app.counterparties.schemas import (
    CounterpartyCreate,
    CounterpartyUpdate,
    PrequalificationCheckCreate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_json(obj) -> Optional[str]:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump())
    if isinstance(obj, (dict, list)):
        return json.dumps(obj)
    return str(obj)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def list_counterparties(
    db: AsyncSession,
    deployment_id: str,
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
) -> list[Counterparty]:
    stmt = select(Counterparty).where(
        Counterparty.deployment_id == deployment_id,
        Counterparty.deleted_at.is_(None),
    )
    if status_filter:
        stmt = stmt.where(Counterparty.status == status_filter)
    if type_filter:
        stmt = stmt.where(Counterparty.type == type_filter)
    stmt = stmt.order_by(Counterparty.name)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_counterparty(
    db: AsyncSession,
    counterparty_id: str,
    deployment_id: str,
) -> Counterparty:
    stmt = select(Counterparty).where(
        Counterparty.id == counterparty_id,
        Counterparty.deployment_id == deployment_id,
        Counterparty.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    cp = result.scalar_one_or_none()
    if not cp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Counterparty {counterparty_id} not found.",
        )
    return cp


async def create_counterparty(
    db: AsyncSession,
    data: CounterpartyCreate,
    deployment_id: str,
    user_id: str,
) -> Counterparty:
    type_val = data.type.value if hasattr(data.type, "value") else str(data.type)
    comm_val = data.comm_capability.value if hasattr(data.comm_capability, "value") else str(data.comm_capability)
    cp = Counterparty(
        id=new_uuid(),
        deployment_id=deployment_id,
        name=data.name,
        type=type_val,
        status=CounterpartyStatus.PENDING.value,
        registration_number=data.registration_number,
        contact_name=data.contact_name,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
        portfolio_kw=data.portfolio_kw,
        asset_types=json.dumps(data.asset_types),
        comm_capability=comm_val,
        comm_endpoint=data.comm_endpoint,
        prequalification_status=PrequalStatus.NOT_SUBMITTED.value,
        framework_agreement_ref=data.framework_agreement_ref,
        framework_signed_date=data.framework_signed_date,
        overarching_agreement=data.overarching_agreement,
        region=data.region,
        notes=data.notes,
        created_by=user_id,
        created_at=utcnow(),
        updated_at=utcnow(),
        meta=_serialize_json(data.meta),
    )
    db.add(cp)
    await db.flush()
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="CREATE",
        resource_type="counterparty",
        resource_id=cp.id,
        user_id=user_id,
        diff={"name": cp.name, "type": cp.type},
    )
    return cp


async def update_counterparty(
    db: AsyncSession,
    counterparty_id: str,
    data: CounterpartyUpdate,
    deployment_id: str,
    user_id: str,
) -> Counterparty:
    cp = await get_counterparty(db, counterparty_id, deployment_id)
    old_status = cp.status
    update_data = data.model_dump(exclude_unset=True)

    # Serialize enums and lists
    for enum_field in ("type", "status", "comm_capability"):
        if enum_field in update_data:
            v = update_data[enum_field]
            update_data[enum_field] = v.value if hasattr(v, "value") else str(v)
    if "asset_types" in update_data:
        update_data["asset_types"] = json.dumps(update_data["asset_types"])
    if "meta" in update_data:
        update_data["meta"] = _serialize_json(update_data["meta"])

    for key, value in update_data.items():
        setattr(cp, key, value)

    cp.updated_at = utcnow()
    await db.flush()
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="UPDATE",
        resource_type="counterparty",
        resource_id=cp.id,
        user_id=user_id,
        diff={"before_status": old_status, "updated_fields": list(update_data.keys())},
    )
    return cp


async def delete_counterparty(
    db: AsyncSession,
    counterparty_id: str,
    deployment_id: str,
    user_id: str,
) -> bool:
    cp = await get_counterparty(db, counterparty_id, deployment_id)
    if cp.status == CounterpartyStatus.APPROVED.value:
        # Check for active contracts
        try:
            from app.contracts.models import Contract, ContractStatus  # noqa: PLC0415
            stmt = select(func.count(Contract.id)).where(
                Contract.counterparty_id == counterparty_id,
                Contract.status == ContractStatus.ACTIVE.value,
                Contract.deleted_at.is_(None),
            )
            result = await db.execute(stmt)
            if (result.scalar_one() or 0) > 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Cannot delete counterparty with active contracts.",
                )
        except ImportError:
            pass

    cp.deleted_at = utcnow()
    cp.updated_at = utcnow()
    await db.flush()
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="DELETE",
        resource_type="counterparty",
        resource_id=cp.id,
        user_id=user_id,
        diff={"name": cp.name},
    )
    return True


# ---------------------------------------------------------------------------
# Prequalification
# ---------------------------------------------------------------------------

async def submit_prequalification(
    db: AsyncSession,
    counterparty_id: str,
    checks: list[PrequalificationCheckCreate],
    user_id: str,
    deployment_id: str,
) -> Counterparty:
    """
    Submit a batch of prequalification checks for a counterparty.
    Sets prequalification_status to PASSED if all checks PASS or WAIVED,
    FAILED if any check FAILs.
    """
    cp = await get_counterparty(db, counterparty_id, deployment_id)

    # Persist each check
    now = utcnow()
    for check_data in checks:
        check = PrequalificationCheck(
            id=new_uuid(),
            counterparty_id=counterparty_id,
            check_name=check_data.check_name,
            result=check_data.result,
            notes=check_data.notes,
            checked_by=user_id,
            checked_at=now,
            created_at=now,
        )
        db.add(check)

    # Determine overall result
    any_fail = any(c.result == "FAIL" for c in checks)
    all_pass_or_waived = all(c.result in ("PASS", "WAIVED") for c in checks)

    if any_fail:
        cp.prequalification_status = PrequalStatus.FAILED.value
    elif all_pass_or_waived:
        cp.prequalification_status = PrequalStatus.PASSED.value
        cp.prequalification_date = now.date().isoformat()
    else:
        cp.prequalification_status = PrequalStatus.SUBMITTED.value

    cp.updated_at = now
    await db.flush()
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="PREQUAL_SUBMIT",
        resource_type="counterparty",
        resource_id=cp.id,
        user_id=user_id,
        diff={"prequal_result": cp.prequalification_status, "checks_count": len(checks)},
    )
    return cp


async def approve_counterparty(
    db: AsyncSession,
    counterparty_id: str,
    deployment_id: str,
    user_id: str,
) -> Counterparty:
    """
    Approve a counterparty.
    Requires prequalification_status=PASSED and framework_signed_date set.
    """
    cp = await get_counterparty(db, counterparty_id, deployment_id)

    if cp.prequalification_status != PrequalStatus.PASSED.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot approve: prequalification_status is '{cp.prequalification_status}' (must be PASSED).",
        )
    if not cp.framework_signed_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot approve: framework_signed_date is not set.",
        )

    old_status = cp.status
    cp.status = CounterpartyStatus.APPROVED.value
    cp.updated_at = utcnow()
    await db.flush()
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="APPROVE",
        resource_type="counterparty",
        resource_id=cp.id,
        user_id=user_id,
        diff={"from_status": old_status, "to_status": CounterpartyStatus.APPROVED.value},
    )
    return cp


async def list_prequalification_checks(
    db: AsyncSession,
    counterparty_id: str,
    deployment_id: str,
) -> list[PrequalificationCheck]:
    await get_counterparty(db, counterparty_id, deployment_id)
    stmt = (
        select(PrequalificationCheck)
        .where(PrequalificationCheck.counterparty_id == counterparty_id)
        .order_by(PrequalificationCheck.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

async def seed_counterparties(db: AsyncSession) -> None:
    """Seed default counterparties for both deployments. Idempotent."""
    stmt = select(func.count(Counterparty.id)).where(
        Counterparty.created_by == "system",
        Counterparty.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    if (result.scalar_one() or 0) > 0:
        return  # Already seeded

    now = utcnow()

    ssen_counterparties = [
        Counterparty(
            id=new_uuid(),
            deployment_id="ssen",
            name="Alpha Flex Ltd",
            type=CounterpartyType.AGGREGATOR.value,
            status=CounterpartyStatus.APPROVED.value,
            contact_name="James Mackenzie",
            contact_email="james.mackenzie@alphaflex.co.uk",
            contact_phone="+44-1224-550100",
            portfolio_kw=500.0,
            asset_types=json.dumps(["V1G", "V2G", "BESS"]),
            comm_capability=CommCapability.OPENADR_2B.value,
            prequalification_status=PrequalStatus.PASSED.value,
            prequalification_date="2025-01-15",
            framework_agreement_ref="FA-SSEN-2025-001",
            framework_signed_date="2025-01-20",
            overarching_agreement=True,
            region="South Scotland",
            created_by="system",
            created_at=now,
            updated_at=now,
        ),
        Counterparty(
            id=new_uuid(),
            deployment_id="ssen",
            name="Western Power Renewables",
            type=CounterpartyType.COMMERCIAL.value,
            status=CounterpartyStatus.APPROVED.value,
            contact_name="Fiona Campbell",
            contact_email="fiona.campbell@wpr.co.uk",
            contact_phone="+44-141-332-8800",
            portfolio_kw=250.0,
            asset_types=json.dumps(["PV", "BESS", "WIND"]),
            comm_capability=CommCapability.IEEE_2030_5.value,
            prequalification_status=PrequalStatus.PASSED.value,
            prequalification_date="2025-02-01",
            framework_agreement_ref="FA-SSEN-2025-002",
            framework_signed_date="2025-02-10",
            overarching_agreement=False,
            region="Orkney & Shetland",
            created_by="system",
            created_at=now,
            updated_at=now,
        ),
        Counterparty(
            id=new_uuid(),
            deployment_id="ssen",
            name="Highland Homes Community",
            type=CounterpartyType.RESIDENTIAL_GROUP.value,
            status=CounterpartyStatus.APPROVED.value,
            contact_name="Morag Stewart",
            contact_email="morag@highlandhomes.coop",
            contact_phone="+44-1463-712345",
            portfolio_kw=75.0,
            asset_types=json.dumps(["HEAT_PUMP", "V1G", "PV"]),
            comm_capability=CommCapability.OPENADR_2A.value,
            prequalification_status=PrequalStatus.PASSED.value,
            prequalification_date="2025-03-01",
            framework_agreement_ref="FA-SSEN-2025-003",
            framework_signed_date="2025-03-05",
            overarching_agreement=False,
            region="Highland",
            created_by="system",
            created_at=now,
            updated_at=now,
        ),
    ]

    puvvnl_counterparties = [
        Counterparty(
            id=new_uuid(),
            deployment_id="puvvnl",
            name="GMR Energy Services",
            type=CounterpartyType.AGGREGATOR.value,
            status=CounterpartyStatus.APPROVED.value,
            contact_name="Rajeev Sharma",
            contact_email="rajeev.sharma@gmrenergy.in",
            contact_phone="+91-11-4567-8900",
            portfolio_kw=300.0,
            asset_types=json.dumps(["PV", "BESS", "INDUSTRIAL_LOAD"]),
            comm_capability=CommCapability.OPENADR_2B.value,
            prequalification_status=PrequalStatus.PASSED.value,
            prequalification_date="2025-03-01",
            framework_agreement_ref="FA-PUVVNL-2025-001",
            framework_signed_date="2025-03-10",
            overarching_agreement=True,
            region="Varanasi Urban",
            created_by="system",
            created_at=now,
            updated_at=now,
        ),
        Counterparty(
            id=new_uuid(),
            deployment_id="puvvnl",
            name="Varanasi Smart Industries",
            type=CounterpartyType.INDUSTRIAL.value,
            status=CounterpartyStatus.APPROVED.value,
            contact_name="Anand Mishra",
            contact_email="anand.mishra@vsi.in",
            contact_phone="+91-542-250-1234",
            portfolio_kw=150.0,
            asset_types=json.dumps(["INDUSTRIAL_LOAD", "BESS"]),
            comm_capability=CommCapability.SCADA_MODBUS.value,
            prequalification_status=PrequalStatus.PASSED.value,
            prequalification_date="2025-03-15",
            framework_agreement_ref="FA-PUVVNL-2025-002",
            framework_signed_date="2025-03-20",
            overarching_agreement=False,
            region="Varanasi Industrial Area",
            created_by="system",
            created_at=now,
            updated_at=now,
        ),
        Counterparty(
            id=new_uuid(),
            deployment_id="puvvnl",
            name="PM Surya Ghar Group",
            type=CounterpartyType.RESIDENTIAL_GROUP.value,
            status=CounterpartyStatus.APPROVED.value,
            contact_name="Priya Verma",
            contact_email="priya.verma@pmsg.in",
            contact_phone="+91-542-260-5678",
            portfolio_kw=50.0,
            asset_types=json.dumps(["PV", "V1G"]),
            comm_capability=CommCapability.HYBRID.value,
            prequalification_status=PrequalStatus.PASSED.value,
            prequalification_date="2025-04-01",
            framework_agreement_ref="FA-PUVVNL-2025-003",
            framework_signed_date="2025-04-05",
            overarching_agreement=False,
            region="Varanasi North",
            created_by="system",
            created_at=now,
            updated_at=now,
        ),
        Counterparty(
            id=new_uuid(),
            deployment_id="puvvnl",
            name="Varanasi DISCOM",
            type=CounterpartyType.DISCOM.value,
            status=CounterpartyStatus.APPROVED.value,
            contact_name="Chief Engineer",
            contact_email="ce@puvvnl.in",
            contact_phone="+91-542-222-0001",
            portfolio_kw=0.0,
            asset_types=json.dumps([]),
            comm_capability=CommCapability.MANUAL_NOTIFICATION.value,
            prequalification_status=PrequalStatus.WAIVED.value,
            prequalification_date=None,
            framework_agreement_ref="FA-PUVVNL-2025-GOV",
            framework_signed_date="2025-01-01",
            overarching_agreement=True,
            region="Varanasi",
            created_by="system",
            created_at=now,
            updated_at=now,
        ),
    ]

    for cp in ssen_counterparties + puvvnl_counterparties:
        db.add(cp)

    await db.flush()
