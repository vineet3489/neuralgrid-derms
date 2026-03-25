"""Business logic for Flexibility Contracts."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.core.utils import new_uuid, utcnow
from app.contracts.models import (
    Contract,
    ContractAmendment,
    ContractStatus,
)
from app.contracts.schemas import (
    ContractCreate,
    ContractPerformance,
    ContractUpdate,
    SettlementSimulation,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _serialize_json(obj) -> Optional[str]:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump())
    if isinstance(obj, (dict, list)):
        return json.dumps(obj)
    return str(obj)


async def _get_counterparty(db: AsyncSession, counterparty_id: str, deployment_id: str):
    """Fetch a counterparty or raise 404."""
    try:
        from app.counterparties.models import Counterparty  # noqa: PLC0415
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
    except ImportError:
        return None


async def _count_counterparty_assets(db: AsyncSession, counterparty_id: str) -> int:
    """Count active DER assets registered to a counterparty."""
    try:
        from app.assets.models import DERAsset, AssetStatus  # noqa: PLC0415
        stmt = select(func.count(DERAsset.id)).where(
            DERAsset.counterparty_id == counterparty_id,
            DERAsset.status != AssetStatus.DEREGISTERED.value,
            DERAsset.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        return result.scalar_one() or 0
    except ImportError:
        return 0


async def _validate_unique_contract_ref(
    db: AsyncSession, contract_ref: str, deployment_id: str, exclude_id: Optional[str] = None
) -> None:
    stmt = select(Contract).where(
        Contract.contract_ref == contract_ref,
        Contract.deployment_id == deployment_id,
        Contract.deleted_at.is_(None),
    )
    if exclude_id:
        stmt = stmt.where(Contract.id != exclude_id)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Contract ref '{contract_ref}' already exists in this deployment.",
        )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def list_contracts(
    db: AsyncSession,
    deployment_id: str,
    program_id: Optional[str] = None,
    counterparty_id: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> list[Contract]:
    stmt = select(Contract).where(
        Contract.deployment_id == deployment_id,
        Contract.deleted_at.is_(None),
    )
    if program_id:
        stmt = stmt.where(Contract.program_id == program_id)
    if counterparty_id:
        stmt = stmt.where(Contract.counterparty_id == counterparty_id)
    if status_filter:
        stmt = stmt.where(Contract.status == status_filter)
    stmt = stmt.order_by(Contract.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_contract(db: AsyncSession, contract_id: str, deployment_id: str) -> Contract:
    stmt = select(Contract).where(
        Contract.id == contract_id,
        Contract.deployment_id == deployment_id,
        Contract.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contract {contract_id} not found.",
        )
    return contract


async def create_contract(
    db: AsyncSession,
    data: ContractCreate,
    deployment_id: str,
    user_id: str,
) -> Contract:
    await _validate_unique_contract_ref(db, data.contract_ref, deployment_id)

    # Verify program exists
    try:
        from app.programs.service import get_program  # noqa: PLC0415
        program = await get_program(db, data.program_id, deployment_id)
    except ImportError:
        program = None

    baseline_val = data.baseline_method.value if hasattr(data.baseline_method, "value") else str(data.baseline_method)
    ms_val = data.measurement_source.value if hasattr(data.measurement_source, "value") else str(data.measurement_source)
    type_val = data.type.value if hasattr(data.type, "value") else str(data.type)

    contract = Contract(
        id=new_uuid(),
        deployment_id=deployment_id,
        program_id=data.program_id,
        counterparty_id=data.counterparty_id,
        contract_ref=data.contract_ref,
        name=data.name,
        type=type_val,
        status=ContractStatus.DRAFT.value,
        cmz_id=data.cmz_id,
        contracted_capacity_kw=data.contracted_capacity_kw,
        min_dispatch_kw=data.min_dispatch_kw,
        service_window_config=_serialize_json(data.service_window_config),
        response_time_minutes=data.response_time_minutes,
        notification_lead_config=_serialize_json(data.notification_lead_config),
        availability_rate_minor=data.availability_rate_minor,
        utilisation_rate_minor=data.utilisation_rate_minor,
        penalty_multiplier=data.penalty_multiplier,
        grace_factor_pct=data.grace_factor_pct,
        baseline_method=baseline_val,
        baseline_params=_serialize_json(data.baseline_params),
        doe_clause=data.doe_clause,
        stackable=data.stackable,
        max_activations_per_day=data.max_activations_per_day,
        max_activations_per_period=data.max_activations_per_period,
        min_rest_hours=data.min_rest_hours,
        measurement_source=ms_val,
        settlement_cycle=data.settlement_cycle,
        signed_date=data.signed_date,
        start_date=data.start_date,
        end_date=data.end_date,
        framework_agreement_id=data.framework_agreement_id,
        created_by=user_id,
        created_at=utcnow(),
        updated_at=utcnow(),
        meta=_serialize_json(data.meta),
    )
    db.add(contract)
    await db.flush()

    # Update program enrolled_mw
    if program is not None:
        program.enrolled_mw = (program.enrolled_mw or 0.0) + (data.contracted_capacity_kw / 1000.0)
        program.updated_at = utcnow()

    await log_audit(
        db,
        deployment_id=deployment_id,
        action="CREATE",
        resource_type="contract",
        resource_id=contract.id,
        user_id=user_id,
        diff={"contract_ref": contract.contract_ref, "program_id": contract.program_id},
    )
    return contract


async def update_contract(
    db: AsyncSession,
    contract_id: str,
    data: ContractUpdate,
    deployment_id: str,
    user_id: str,
) -> Contract:
    contract = await get_contract(db, contract_id, deployment_id)
    old_status = contract.status
    old_capacity = contract.contracted_capacity_kw

    update_data = data.model_dump(exclude_unset=True)

    # Status transitions handled by dedicated functions; reject direct status write here
    # unless it's a simple draft→pending or similar non-critical move
    if "status" in update_data:
        new_status = update_data["status"]
        new_status_val = new_status.value if hasattr(new_status, "value") else str(new_status)
        # ACTIVE/SUSPENDED transitions must use activate_contract/suspend_contract
        if new_status_val in (ContractStatus.ACTIVE.value, ContractStatus.SUSPENDED.value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Use dedicated endpoint to transition contract to {new_status_val}.",
            )
        update_data["status"] = new_status_val

    # Serialize JSON fields
    for json_field in ("service_window_config", "notification_lead_config", "baseline_params", "meta"):
        if json_field in update_data:
            update_data[json_field] = _serialize_json(update_data[json_field])
    for enum_field in ("baseline_method", "measurement_source", "type"):
        if enum_field in update_data:
            v = update_data[enum_field]
            update_data[enum_field] = v.value if hasattr(v, "value") else str(v)

    for key, value in update_data.items():
        setattr(contract, key, value)

    contract.updated_at = utcnow()
    await db.flush()

    # Record amendment if capacity or rates changed
    amendment_fields = {"contracted_capacity_kw", "availability_rate_minor", "utilisation_rate_minor"}
    changed_amendment = amendment_fields.intersection(set(update_data.keys()))
    if changed_amendment:
        amendment_type = "CAPACITY_CHANGE" if "contracted_capacity_kw" in changed_amendment else "RATE_CHANGE"
        amendment = ContractAmendment(
            id=new_uuid(),
            contract_id=contract.id,
            amendment_type=amendment_type,
            effective_date=utcnow().date().isoformat(),
            old_values=json.dumps({"contracted_capacity_kw": old_capacity}),
            new_values=json.dumps({k: update_data[k] for k in changed_amendment}),
            created_by=user_id,
            created_at=utcnow(),
        )
        db.add(amendment)

    await log_audit(
        db,
        deployment_id=deployment_id,
        action="UPDATE",
        resource_type="contract",
        resource_id=contract.id,
        user_id=user_id,
        diff={"before_status": old_status, "updated_fields": list(update_data.keys())},
    )
    return contract


async def delete_contract(
    db: AsyncSession,
    contract_id: str,
    deployment_id: str,
    user_id: str,
) -> bool:
    contract = await get_contract(db, contract_id, deployment_id)
    if contract.status == ContractStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot delete an ACTIVE contract. Terminate or expire it first.",
        )
    contract.deleted_at = utcnow()
    contract.updated_at = utcnow()
    await db.flush()
    await log_audit(
        db,
        deployment_id=deployment_id,
        action="DELETE",
        resource_type="contract",
        resource_id=contract.id,
        user_id=user_id,
        diff={"contract_ref": contract.contract_ref},
    )
    return True


# ---------------------------------------------------------------------------
# Business operations
# ---------------------------------------------------------------------------

async def activate_contract(
    db: AsyncSession,
    contract_id: str,
    deployment_id: str,
    user_id: str,
) -> Contract:
    """
    Activate a contract.
    Validates: signed_date set, counterparty APPROVED, at least 1 asset registered.
    """
    contract = await get_contract(db, contract_id, deployment_id)

    if contract.status == ContractStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contract is already ACTIVE.",
        )
    if contract.status not in (
        ContractStatus.DRAFT.value,
        ContractStatus.PENDING_SIGNATURE.value,
        ContractStatus.SUSPENDED.value,
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot activate a contract with status '{contract.status}'.",
        )
    if not contract.signed_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot activate contract: signed_date is not set.",
        )

    # Validate counterparty is APPROVED
    try:
        from app.counterparties.models import Counterparty, CounterpartyStatus  # noqa: PLC0415
        stmt = select(Counterparty).where(
            Counterparty.id == contract.counterparty_id,
            Counterparty.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        cp = result.scalar_one_or_none()
        if cp and cp.status != CounterpartyStatus.APPROVED.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot activate contract: counterparty status is '{cp.status}' (must be APPROVED).",
            )
    except ImportError:
        pass

    # Validate at least 1 asset registered to counterparty
    asset_count = await _count_counterparty_assets(db, contract.counterparty_id)
    if asset_count == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot activate contract: counterparty has no registered DER assets.",
        )

    old_status = contract.status
    contract.status = ContractStatus.ACTIVE.value
    contract.updated_at = utcnow()

    # Record amendment
    amendment = ContractAmendment(
        id=new_uuid(),
        contract_id=contract.id,
        amendment_type="STATUS_CHANGE",
        effective_date=utcnow().date().isoformat(),
        old_values=json.dumps({"status": old_status}),
        new_values=json.dumps({"status": ContractStatus.ACTIVE.value}),
        created_by=user_id,
        created_at=utcnow(),
        notes="Contract activated.",
    )
    db.add(amendment)
    await db.flush()

    await log_audit(
        db,
        deployment_id=deployment_id,
        action="ACTIVATE",
        resource_type="contract",
        resource_id=contract.id,
        user_id=user_id,
        diff={"from_status": old_status, "to_status": ContractStatus.ACTIVE.value},
    )
    return contract


async def suspend_contract(
    db: AsyncSession,
    contract_id: str,
    reason: str,
    deployment_id: str,
    user_id: str,
) -> Contract:
    """Suspend an active contract."""
    contract = await get_contract(db, contract_id, deployment_id)
    if contract.status != ContractStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Can only suspend ACTIVE contracts (current: '{contract.status}').",
        )
    old_status = contract.status
    contract.status = ContractStatus.SUSPENDED.value
    contract.updated_at = utcnow()

    amendment = ContractAmendment(
        id=new_uuid(),
        contract_id=contract.id,
        amendment_type="STATUS_CHANGE",
        effective_date=utcnow().date().isoformat(),
        old_values=json.dumps({"status": old_status}),
        new_values=json.dumps({"status": ContractStatus.SUSPENDED.value}),
        created_by=user_id,
        created_at=utcnow(),
        notes=reason,
    )
    db.add(amendment)
    await db.flush()

    await log_audit(
        db,
        deployment_id=deployment_id,
        action="SUSPEND",
        resource_type="contract",
        resource_id=contract.id,
        user_id=user_id,
        diff={"reason": reason},
    )
    return contract


async def get_contract_performance(
    db: AsyncSession,
    contract_id: str,
    deployment_id: str,
) -> ContractPerformance:
    """Return performance summary for a contract."""
    await get_contract(db, contract_id, deployment_id)

    activations_count = 0
    avg_delivery_pct = 0.0
    total_paid_minor = 0
    penalty_events = 0

    try:
        from app.dispatch.models import DispatchEvent, DispatchStatus  # noqa: PLC0415
        from sqlalchemy import and_  # noqa: PLC0415

        # Count activations where this contract was involved
        stmt = (
            select(func.count(DispatchEvent.id))
            .where(
                DispatchEvent.deployment_id == deployment_id,
                DispatchEvent.status == DispatchStatus.COMPLETED.value,
            )
        )
        result = await db.execute(stmt)
        activations_count = result.scalar_one() or 0

    except (ImportError, Exception):
        pass

    return ContractPerformance(
        activations_count=activations_count,
        avg_delivery_pct=round(avg_delivery_pct, 2),
        total_paid_minor=total_paid_minor,
        penalty_events=penalty_events,
    )


async def simulate_settlement(
    db: AsyncSession,
    contract_id: str,
    hypothetical_kw: float,
    duration_hours: float,
    deployment_id: str,
) -> SettlementSimulation:
    """
    Simulate settlement for a hypothetical dispatch scenario.

    Returns availability_payment, utilisation_payment, penalty, and net_payment
    all expressed in minor currency units.
    """
    contract = await get_contract(db, contract_id, deployment_id)

    # Availability payment: rate_minor per kW per hour × contracted_kw × duration
    availability_payment = int(
        contract.availability_rate_minor * contract.contracted_capacity_kw * duration_hours
    )

    # Utilisation payment: rate_minor per kWh × actual kWh delivered
    actual_kwh = hypothetical_kw * duration_hours
    utilisation_payment = int(contract.utilisation_rate_minor * actual_kwh)

    # Delivery percentage
    delivery_pct = (
        (hypothetical_kw / contract.contracted_capacity_kw * 100)
        if contract.contracted_capacity_kw > 0
        else 0.0
    )
    within_grace = delivery_pct >= (100.0 - contract.grace_factor_pct)

    # Penalty: if delivery < (100% - grace_factor), apply penalty on the shortfall
    penalty = 0
    if not within_grace:
        shortfall_kw = contract.contracted_capacity_kw - hypothetical_kw
        shortfall_kwh = shortfall_kw * duration_hours
        penalty = int(
            contract.utilisation_rate_minor * shortfall_kwh * contract.penalty_multiplier
        )

    net_payment = availability_payment + utilisation_payment - penalty

    return SettlementSimulation(
        contracted_capacity_kw=contract.contracted_capacity_kw,
        hypothetical_kw=hypothetical_kw,
        duration_hours=duration_hours,
        availability_payment_minor=availability_payment,
        utilisation_payment_minor=utilisation_payment,
        penalty_minor=penalty,
        net_payment_minor=net_payment,
        delivery_pct=round(delivery_pct, 2),
        within_grace_factor=within_grace,
    )


async def list_amendments(
    db: AsyncSession,
    contract_id: str,
    deployment_id: str,
) -> list[ContractAmendment]:
    # Verify contract exists in this deployment
    await get_contract(db, contract_id, deployment_id)
    stmt = (
        select(ContractAmendment)
        .where(ContractAmendment.contract_id == contract_id)
        .order_by(ContractAmendment.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Demo seed
# ---------------------------------------------------------------------------

async def seed_demo_contracts(db: AsyncSession) -> None:
    """
    Idempotent seed: creates realistic flexibility contracts tied to seeded
    programs and counterparties for SSEN and PUVVNL deployments.
    """
    import json as _json
    from app.programs.models import Program  # noqa: PLC0415
    from app.counterparties.models import Counterparty  # noqa: PLC0415

    # Check whether already seeded
    existing_count_result = await db.execute(
        select(func.count(Contract.id)).where(
            Contract.contract_ref.like("CTR-%"),
            Contract.deleted_at.is_(None),
        )
    )
    if (existing_count_result.scalar_one() or 0) >= 4:
        return  # Already seeded

    now = utcnow()

    for deployment_id, dep_data in [
        ("ssen", {
            "program_names": ["SSEN Winter Peak Reduction 2025-26", "SSEN Dynamic Constraint Management 2026"],
            "counterparty_names": ["Alpha Flex Ltd", "Western Power Renewables"],
            "currency": "GBP",
            "contracts": [
                {
                    "contract_ref": "CTR-SSEN-001",
                    "name": "Alpha Flex — Orkney Peak Reduction 2025-26",
                    "type": "OPERATIONAL_UTILISATION",
                    "program_idx": 0,
                    "counterparty_idx": 0,
                    "cmz_id": "CMZ-ORKNEY",
                    "contracted_capacity_kw": 1200.0,
                    "min_dispatch_kw": 200.0,
                    "availability_rate_minor": 850,   # 850 pence/kW/day = £8.50/kW/day
                    "utilisation_rate_minor": 12500,  # 12500 pence/MWh = £125/MWh
                    "response_time_minutes": 15,
                    "status": "ACTIVE",
                    "start_date": "2025-11-01",
                    "end_date": "2026-03-31",
                    "signed_date": "2025-10-15",
                    "baseline_method": "HIGH_5_OF_10",
                    "settlement_cycle": "MONTHLY",
                    "doe_clause": True,
                    "stackable": True,
                    "max_activations_per_day": 3,
                    "service_window_config": {
                        "days": ["MON","TUE","WED","THU","FRI"],
                        "hours": {"start": "17:00", "end": "21:00"},
                        "tz": "Europe/London",
                    },
                },
                {
                    "contract_ref": "CTR-SSEN-002",
                    "name": "Western Power — Shetland BESS Dynamic Constraint",
                    "type": "DYNAMIC_CONSTRAINT",
                    "program_idx": 1,
                    "counterparty_idx": 1,
                    "cmz_id": "CMZ-SHETLAND",
                    "contracted_capacity_kw": 2000.0,
                    "min_dispatch_kw": 500.0,
                    "availability_rate_minor": 700,   # 700 pence/kW/day
                    "utilisation_rate_minor": 9500,   # £95/MWh
                    "response_time_minutes": 5,
                    "status": "ACTIVE",
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                    "signed_date": "2025-12-10",
                    "baseline_method": "SMART_BASELINE",
                    "settlement_cycle": "MONTHLY",
                    "doe_clause": True,
                    "stackable": False,
                    "max_activations_per_day": 10,
                    "service_window_config": None,    # Any time
                },
                {
                    "contract_ref": "CTR-SSEN-003",
                    "name": "Alpha Flex — Orkney V1G Scheduled Utilisation",
                    "type": "SCHEDULED_UTILISATION",
                    "program_idx": 0,
                    "counterparty_idx": 0,
                    "cmz_id": "CMZ-ORKNEY",
                    "contracted_capacity_kw": 350.0,
                    "min_dispatch_kw": 50.0,
                    "availability_rate_minor": 400,
                    "utilisation_rate_minor": 8000,
                    "response_time_minutes": 30,
                    "status": "PENDING_SIGNATURE",
                    "start_date": "2026-04-01",
                    "end_date": "2027-03-31",
                    "signed_date": None,
                    "baseline_method": "AVG_5_OF_10",
                    "settlement_cycle": "MONTHLY",
                    "doe_clause": False,
                    "stackable": True,
                    "max_activations_per_day": 2,
                    "service_window_config": {
                        "days": ["SAT","SUN"],
                        "hours": {"start": "10:00", "end": "16:00"},
                        "tz": "Europe/London",
                    },
                },
            ],
        }),
        ("puvvnl", {
            "program_names": ["PUVVNL Demand Response Pilot 2025", "PM Surya Ghar P2P Trading Program"],
            "counterparty_names": ["GMR Energy Services", "PM Surya Ghar Group"],
            "currency": "INR",
            "contracts": [
                {
                    "contract_ref": "CTR-PUV-001",
                    "name": "GMR Energy — Varanasi Industrial DR Pilot",
                    "type": "DEMAND_RESPONSE",
                    "program_idx": 0,
                    "counterparty_idx": 0,
                    "cmz_id": "CMZ-VARANASI-NORTH",
                    "contracted_capacity_kw": 600.0,
                    "min_dispatch_kw": 100.0,
                    "availability_rate_minor": 15000,   # ₹150/kW/day in paise
                    "utilisation_rate_minor": 450000,   # ₹4,500/MWh in paise
                    "response_time_minutes": 20,
                    "status": "ACTIVE",
                    "start_date": "2025-04-01",
                    "end_date": "2026-03-31",
                    "signed_date": "2025-03-20",
                    "baseline_method": "HIGH_5_OF_10",
                    "settlement_cycle": "MONTHLY",
                    "doe_clause": True,
                    "stackable": True,
                    "max_activations_per_day": 4,
                    "service_window_config": {
                        "days": ["MON","TUE","WED","THU","FRI"],
                        "hours": {"start": "13:00", "end": "17:00"},
                        "tz": "Asia/Kolkata",
                    },
                },
                {
                    "contract_ref": "CTR-PUV-002",
                    "name": "PM Surya Ghar — BHU Campus P2P Solar",
                    "type": "P2P",
                    "program_idx": 1,
                    "counterparty_idx": 1,
                    "cmz_id": "CMZ-VARANASI-SOUTH",
                    "contracted_capacity_kw": 175.0,
                    "min_dispatch_kw": 25.0,
                    "availability_rate_minor": 5000,
                    "utilisation_rate_minor": 180000,
                    "response_time_minutes": 15,
                    "status": "ACTIVE",
                    "start_date": "2025-04-01",
                    "end_date": "2026-03-31",
                    "signed_date": "2025-03-28",
                    "baseline_method": "METERED_BASELINE",
                    "settlement_cycle": "MONTHLY",
                    "doe_clause": False,
                    "stackable": False,
                    "max_activations_per_day": None,
                    "service_window_config": None,
                },
            ],
        }),
    ]:
        # Look up program IDs
        prog_result = await db.execute(
            select(Program).where(
                Program.deployment_id == deployment_id,
                Program.deleted_at.is_(None),
            ).order_by(Program.created_at)
        )
        programs = list(prog_result.scalars().all())

        # Look up counterparty IDs
        cp_result = await db.execute(
            select(Counterparty).where(
                Counterparty.deployment_id == deployment_id,
                Counterparty.deleted_at.is_(None),
            )
        )
        cps = {cp.name: cp.id for cp in cp_result.scalars().all()}
        cp_names = dep_data["counterparty_names"]

        for c in dep_data["contracts"]:
            # Skip if already exists
            dup = await db.execute(
                select(Contract).where(
                    Contract.contract_ref == c["contract_ref"],
                    Contract.deployment_id == deployment_id,
                )
            )
            if dup.scalar_one_or_none():
                continue

            prog_idx = c["program_idx"]
            if prog_idx >= len(programs):
                continue  # Programs not seeded yet
            program_id = programs[prog_idx].id

            cp_name = cp_names[c["counterparty_idx"]]
            cp_id = cps.get(cp_name)
            if not cp_id:
                cp_id = next(iter(cps.values()), None)
            if not cp_id:
                continue

            svc_window = c.get("service_window_config")
            contract = Contract(
                id=new_uuid(),
                deployment_id=deployment_id,
                program_id=program_id,
                counterparty_id=cp_id,
                contract_ref=c["contract_ref"],
                name=c["name"],
                type=c["type"],
                status=c["status"],
                cmz_id=c["cmz_id"],
                contracted_capacity_kw=c["contracted_capacity_kw"],
                min_dispatch_kw=c.get("min_dispatch_kw"),
                availability_rate_minor=c["availability_rate_minor"],
                utilisation_rate_minor=c["utilisation_rate_minor"],
                penalty_multiplier=3.0,
                grace_factor_pct=5.0,
                response_time_minutes=c["response_time_minutes"],
                baseline_method=c["baseline_method"],
                doe_clause=c["doe_clause"],
                stackable=c["stackable"],
                max_activations_per_day=c.get("max_activations_per_day"),
                min_rest_hours=2.0,
                measurement_source="AMI_MDMS",
                settlement_cycle=c["settlement_cycle"],
                start_date=c["start_date"],
                end_date=c["end_date"],
                signed_date=c.get("signed_date"),
                service_window_config=_json.dumps(svc_window) if svc_window else None,
                created_by="system",
                created_at=now,
                updated_at=now,
            )
            db.add(contract)

    await db.flush()
