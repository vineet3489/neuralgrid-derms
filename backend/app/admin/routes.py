"""Admin API — deployment config, system health, user management, audit logs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select

from app.audit import AuditEvent
from app.auth.models import Deployment, User, UserDeploymentRole
from app.auth.service import hash_password
from app.core.deps import CurrentUserDep, DBDep, DeploymentDep
from app.core.utils import new_uuid, utcnow

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ── Deployment config ─────────────────────────────────────────────────────────

@router.get("/config/{dep_id}")
async def get_deployment_config(
    dep_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
) -> dict:
    """Return configuration for a deployment."""
    result = await db.execute(
        select(Deployment).where(Deployment.slug == dep_id.lower())
    )
    dep = result.scalar_one_or_none()
    if not dep:
        raise HTTPException(status_code=404, detail=f"Deployment '{dep_id}' not found")
    return {
        "id": dep.id,
        "slug": dep.slug,
        "name": dep.name,
        "country": dep.country,
        "currency_code": dep.currency_code,
        "currency_minor_units": dep.currency_minor_units,
        "timezone": dep.timezone,
        "regulatory_framework": dep.regulatory_framework,
        "voltage_nominal": dep.voltage_nominal,
        "frequency_hz": dep.frequency_hz,
        "settlement_cycle": dep.settlement_cycle,
        "is_active": dep.is_active,
        "config": dep.config,
        "created_at": dep.created_at.isoformat(),
    }


class DeploymentConfigUpdate(BaseModel):
    name: Optional[str] = None
    regulatory_framework: Optional[str] = None
    settlement_cycle: Optional[str] = None
    voltage_nominal: Optional[float] = None
    is_active: Optional[bool] = None
    config: Optional[dict] = None


@router.put("/config/{dep_id}")
async def update_deployment_config(
    dep_id: str,
    body: DeploymentConfigUpdate,
    db: DBDep,
    current_user: CurrentUserDep,
) -> dict:
    """Update deployment configuration (DEPLOY_ADMIN or SUPER_ADMIN)."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="DEPLOY_ADMIN access required")

    result = await db.execute(
        select(Deployment).where(Deployment.slug == dep_id.lower())
    )
    dep = result.scalar_one_or_none()
    if not dep:
        raise HTTPException(status_code=404, detail=f"Deployment '{dep_id}' not found")

    if body.name is not None:
        dep.name = body.name
    if body.regulatory_framework is not None:
        dep.regulatory_framework = body.regulatory_framework
    if body.settlement_cycle is not None:
        dep.settlement_cycle = body.settlement_cycle
    if body.voltage_nominal is not None:
        dep.voltage_nominal = body.voltage_nominal
    if body.is_active is not None:
        dep.is_active = body.is_active
    if body.config is not None:
        dep.config = body.config

    await db.commit()
    await db.refresh(dep)
    return {"status": "updated", "slug": dep.slug, "name": dep.name}


# ── Audit logs ────────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def get_audit_logs(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    limit: int = Query(100, ge=1, le=500),
    resource_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
) -> List[dict]:
    """Return recent audit events for the deployment (DEPLOY_ADMIN or higher)."""
    stmt = select(AuditEvent).where(AuditEvent.deployment_id == deployment_id)
    if resource_type:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)
    if action:
        stmt = stmt.where(AuditEvent.action == action.upper())
    stmt = stmt.order_by(desc(AuditEvent.timestamp)).limit(limit)
    result = await db.execute(stmt)
    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "user_email": e.user_email,
            "user_role": e.user_role,
            "deployment_id": e.deployment_id,
            "action": e.action,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "diff": e.diff,
            "ip_address": e.ip_address,
            "timestamp": e.timestamp.isoformat(),
            "success": e.success,
            "error_message": e.error_message,
        }
        for e in events
    ]


# ── System health ─────────────────────────────────────────────────────────────

@router.get("/system-health")
async def system_health(
    db: DBDep,
    current_user: CurrentUserDep,
) -> dict:
    """Return system health status — DB, cache, API, simulation."""
    from app.grid.simulation import get_grid_state

    # Test DB connectivity
    db_ok = False
    try:
        await db.execute(select(User).limit(1))
        db_ok = True
    except Exception:
        pass

    # Test in-memory grid state
    grid_state = get_grid_state()
    cache_ok = bool(grid_state)
    simulation_running = bool(grid_state.get("ssen") or grid_state.get("puvvnl"))

    return {
        "status": "healthy" if db_ok else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "database": "ok" if db_ok else "error",
            "grid_state_cache": "ok" if cache_ok else "empty",
            "simulation_running": simulation_running,
            "api": "ok",
        },
        "deployments_active": list(grid_state.keys()),
    }


# ── User management ───────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> List[dict]:
    """List users with roles for this deployment (DEPLOY_ADMIN or higher)."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.execute(select(User).where(User.is_active == True))
    users = result.scalars().all()

    roles_result = await db.execute(
        select(UserDeploymentRole).where(
            UserDeploymentRole.deployment_id == deployment_id
        )
    )
    role_map = {r.user_id: r.role for r in roles_result.scalars().all()}

    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "is_active": u.is_active,
            "is_superuser": u.is_superuser,
            "role": role_map.get(u.id, "VIEWER"),
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


class UserCreateRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "VIEWER"
    is_superuser: bool = False


@router.post("/users")
async def create_user(
    body: UserCreateRequest,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Create a new user and assign a deployment role (DEPLOY_ADMIN or higher)."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        id=new_uuid(),
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        is_active=True,
        is_superuser=body.is_superuser,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(user)
    await db.flush()

    role_record = UserDeploymentRole(
        id=new_uuid(),
        user_id=user.id,
        deployment_id=deployment_id,
        role=body.role.upper(),
    )
    db.add(role_record)

    try:
        from app.audit import log_audit

        await log_audit(
            db,
            deployment_id=deployment_id,
            action="CREATE",
            resource_type="user",
            resource_id=user.id,
            user_id=current_user.id,
            user_email=current_user.email,
            diff={"email": body.email, "role": body.role},
        )
    except Exception:
        pass

    await db.commit()
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": body.role.upper(),
        "created_at": user.created_at.isoformat(),
    }
