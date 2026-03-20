"""FastAPI routes for Flexibility Contracts."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, status

from app.auth.models import User
from app.auth.schemas import Role
from app.auth.service import get_current_user, require_role
from app.core.deps import DBDep, DeploymentDep
from app.contracts.schemas import (
    ContractAmendmentRead,
    ContractCreate,
    ContractPerformance,
    ContractRead,
    ContractUpdate,
    SettlementSimulation,
)
from app.contracts.service import (
    activate_contract,
    create_contract,
    delete_contract,
    get_contract,
    get_contract_performance,
    list_amendments,
    list_contracts,
    simulate_settlement,
    suspend_contract,
    update_contract,
)

router = APIRouter(tags=["contracts"])

_contract_mgr_plus = require_role(
    Role.CONTRACT_MGR, Role.PROG_MGR, Role.DEPLOY_ADMIN, Role.SUPER_ADMIN
)
_deploy_admin_plus = require_role(Role.DEPLOY_ADMIN, Role.SUPER_ADMIN)


@router.get("/", response_model=list[ContractRead])
async def route_list_contracts(
    db: DBDep,
    deployment_id: DeploymentDep,
    program_id: Optional[str] = Query(default=None),
    counterparty_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    _user: User = Depends(get_current_user),
):
    """List contracts. Optionally filter by program, counterparty, or status."""
    return await list_contracts(
        db, deployment_id, program_id=program_id, counterparty_id=counterparty_id, status_filter=status
    )


@router.get("/{contract_id}", response_model=ContractRead)
async def route_get_contract(
    contract_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    _user: User = Depends(get_current_user),
):
    return await get_contract(db, contract_id, deployment_id)


@router.get("/{contract_id}/performance", response_model=ContractPerformance)
async def route_get_contract_performance(
    contract_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    _user: User = Depends(get_current_user),
):
    """Return performance summary for a contract."""
    return await get_contract_performance(db, contract_id, deployment_id)


@router.post("/{contract_id}/simulate-settlement", response_model=SettlementSimulation)
async def route_simulate_settlement(
    contract_id: str,
    hypothetical_kw: float = Body(..., embed=True),
    duration_hours: float = Body(..., embed=True),
    db: DBDep = ...,
    deployment_id: DeploymentDep = ...,
    _user: User = Depends(get_current_user),
):
    """Simulate a settlement calculation for hypothetical dispatch parameters."""
    return await simulate_settlement(db, contract_id, hypothetical_kw, duration_hours, deployment_id)


@router.get("/{contract_id}/amendments", response_model=list[ContractAmendmentRead])
async def route_list_amendments(
    contract_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    _user: User = Depends(get_current_user),
):
    """List all amendments for a contract."""
    return await list_amendments(db, contract_id, deployment_id)


@router.post("/", response_model=ContractRead, status_code=status.HTTP_201_CREATED)
async def route_create_contract(
    data: ContractCreate,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_contract_mgr_plus),
):
    """Create a new contract. Requires CONTRACT_MGR or higher."""
    return await create_contract(db, data, deployment_id, user.id)


@router.put("/{contract_id}", response_model=ContractRead)
async def route_update_contract(
    contract_id: str,
    data: ContractUpdate,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_contract_mgr_plus),
):
    """Update a contract. Requires CONTRACT_MGR or higher."""
    return await update_contract(db, contract_id, data, deployment_id, user.id)


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def route_delete_contract(
    contract_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_deploy_admin_plus),
):
    """Soft-delete a contract. Requires DEPLOY_ADMIN or higher."""
    await delete_contract(db, contract_id, deployment_id, user.id)


@router.post("/{contract_id}/activate", response_model=ContractRead)
async def route_activate_contract(
    contract_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_contract_mgr_plus),
):
    """Activate a contract after signature and counterparty approval."""
    return await activate_contract(db, contract_id, deployment_id, user.id)


@router.post("/{contract_id}/suspend", response_model=ContractRead)
async def route_suspend_contract(
    contract_id: str,
    reason: str = Body(..., embed=True),
    db: DBDep = ...,
    deployment_id: DeploymentDep = ...,
    user: User = Depends(_contract_mgr_plus),
):
    """Suspend an active contract with a stated reason."""
    return await suspend_contract(db, contract_id, reason, deployment_id, user.id)
