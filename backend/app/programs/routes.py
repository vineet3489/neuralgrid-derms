"""FastAPI routes for Flexibility Programs."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.models import User
from app.auth.schemas import Role
from app.auth.service import get_current_user, require_role
from app.core.deps import DBDep, DeploymentDep
from app.programs.schemas import (
    ProgramCloneRequest,
    ProgramCreate,
    ProgramKPIs,
    ProgramRead,
    ProgramUpdate,
)
from app.programs.service import (
    clone_program,
    create_program,
    delete_program,
    get_program,
    get_program_kpis,
    list_programs,
    update_program,
)

router = APIRouter(tags=["programs"])

# Role shorthand
_prog_mgr_plus = require_role(Role.PROG_MGR, Role.CONTRACT_MGR, Role.DEPLOY_ADMIN, Role.SUPER_ADMIN)
_deploy_admin_plus = require_role(Role.DEPLOY_ADMIN, Role.SUPER_ADMIN)


@router.get("/", response_model=list[ProgramRead])
async def route_list_programs(
    db: DBDep,
    deployment_id: DeploymentDep,
    status: Optional[str] = Query(default=None, description="Filter by program status"),
    type: Optional[str] = Query(default=None, description="Filter by program type"),
    _user: User = Depends(get_current_user),
) -> list[ProgramRead]:
    """List all programs for the deployment. All authenticated roles."""
    programs = await list_programs(db, deployment_id, status_filter=status, type_filter=type)
    return programs  # type: ignore[return-value]


@router.get("/{program_id}", response_model=ProgramRead)
async def route_get_program(
    program_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    _user: User = Depends(get_current_user),
) -> ProgramRead:
    """Retrieve a single program by ID."""
    program = await get_program(db, program_id, deployment_id)
    return program  # type: ignore[return-value]


@router.get("/{program_id}/kpis", response_model=ProgramKPIs)
async def route_get_program_kpis(
    program_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    _user: User = Depends(get_current_user),
) -> ProgramKPIs:
    """Return KPI summary for a program."""
    return await get_program_kpis(db, program_id, deployment_id)


@router.get("/{program_id}/contracts")
async def route_list_program_contracts(
    program_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    _user: User = Depends(get_current_user),
):
    """List all contracts enrolled in a program."""
    # Verify the program exists in this deployment first
    await get_program(db, program_id, deployment_id)

    try:
        from app.contracts.models import Contract  # noqa: PLC0415
        from app.contracts.schemas import ContractRead  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        stmt = select(Contract).where(
            Contract.program_id == program_id,
            Contract.deployment_id == deployment_id,
            Contract.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        contracts = result.scalars().all()
        return contracts
    except ImportError:
        return []


@router.post("/", response_model=ProgramRead, status_code=status.HTTP_201_CREATED)
async def route_create_program(
    data: ProgramCreate,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_prog_mgr_plus),
) -> ProgramRead:
    """Create a new flexibility program. Requires PROG_MGR or higher."""
    program = await create_program(db, data, deployment_id, user.id)
    return program  # type: ignore[return-value]


@router.put("/{program_id}", response_model=ProgramRead)
async def route_update_program(
    program_id: str,
    data: ProgramUpdate,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_prog_mgr_plus),
) -> ProgramRead:
    """Update an existing program. Requires PROG_MGR or higher."""
    program = await update_program(db, program_id, data, deployment_id, user.id)
    return program  # type: ignore[return-value]


@router.delete("/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
async def route_delete_program(
    program_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_deploy_admin_plus),
) -> None:
    """Soft-delete a program. Requires DEPLOY_ADMIN or higher."""
    await delete_program(db, program_id, deployment_id, user.id)


@router.post("/{program_id}/clone", response_model=ProgramRead, status_code=status.HTTP_201_CREATED)
async def route_clone_program(
    program_id: str,
    data: ProgramCloneRequest,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_prog_mgr_plus),
) -> ProgramRead:
    """Clone a program with a new name and date range. Requires PROG_MGR or higher."""
    program = await clone_program(
        db,
        program_id,
        new_name=data.new_name,
        new_start_date=data.new_start_date,
        new_end_date=data.new_end_date,
        deployment_id=deployment_id,
        user_id=user.id,
    )
    return program  # type: ignore[return-value]
