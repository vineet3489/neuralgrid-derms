"""FastAPI routes for Counterparties."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.auth.models import User
from app.auth.schemas import Role
from app.auth.service import get_current_user, require_role
from app.core.deps import DBDep, DeploymentDep
from app.counterparties.schemas import (
    CounterpartyCreate,
    CounterpartyRead,
    CounterpartyUpdate,
    PrequalificationCheckRead,
    PrequalificationSubmit,
)
from app.counterparties.service import (
    approve_counterparty,
    create_counterparty,
    delete_counterparty,
    get_counterparty,
    list_counterparties,
    list_prequalification_checks,
    submit_prequalification,
    update_counterparty,
)

router = APIRouter(prefix="/api/v1/counterparties", tags=["counterparties"])

_contract_mgr_plus = require_role(
    Role.CONTRACT_MGR, Role.PROG_MGR, Role.DEPLOY_ADMIN, Role.SUPER_ADMIN
)
_deploy_admin_plus = require_role(Role.DEPLOY_ADMIN, Role.SUPER_ADMIN)


@router.get("/", response_model=list[CounterpartyRead])
async def route_list_counterparties(
    db: DBDep,
    deployment_id: DeploymentDep,
    status: Optional[str] = Query(default=None),
    type: Optional[str] = Query(default=None),
    _user: User = Depends(get_current_user),
):
    """List counterparties for the deployment."""
    return await list_counterparties(db, deployment_id, status_filter=status, type_filter=type)


@router.get("/{counterparty_id}", response_model=CounterpartyRead)
async def route_get_counterparty(
    counterparty_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    _user: User = Depends(get_current_user),
):
    return await get_counterparty(db, counterparty_id, deployment_id)


@router.get("/{counterparty_id}/prequalification", response_model=list[PrequalificationCheckRead])
async def route_list_prequal_checks(
    counterparty_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    _user: User = Depends(get_current_user),
):
    """List all prequalification checks for a counterparty."""
    return await list_prequalification_checks(db, counterparty_id, deployment_id)


@router.post("/", response_model=CounterpartyRead, status_code=status.HTTP_201_CREATED)
async def route_create_counterparty(
    data: CounterpartyCreate,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_contract_mgr_plus),
):
    """Create a new counterparty. Requires CONTRACT_MGR or higher."""
    return await create_counterparty(db, data, deployment_id, user.id)


@router.put("/{counterparty_id}", response_model=CounterpartyRead)
async def route_update_counterparty(
    counterparty_id: str,
    data: CounterpartyUpdate,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_contract_mgr_plus),
):
    return await update_counterparty(db, counterparty_id, data, deployment_id, user.id)


@router.delete("/{counterparty_id}", status_code=status.HTTP_204_NO_CONTENT)
async def route_delete_counterparty(
    counterparty_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_deploy_admin_plus),
):
    await delete_counterparty(db, counterparty_id, deployment_id, user.id)


@router.post("/{counterparty_id}/prequalification", response_model=CounterpartyRead)
async def route_submit_prequalification(
    counterparty_id: str,
    data: PrequalificationSubmit,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_contract_mgr_plus),
):
    """Submit a batch of prequalification checks."""
    return await submit_prequalification(
        db, counterparty_id, data.checks, user.id, deployment_id
    )


@router.post("/{counterparty_id}/approve", response_model=CounterpartyRead)
async def route_approve_counterparty(
    counterparty_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_deploy_admin_plus),
):
    """Approve a counterparty after prequalification and framework agreement. Requires DEPLOY_ADMIN+."""
    return await approve_counterparty(db, counterparty_id, deployment_id, user.id)
