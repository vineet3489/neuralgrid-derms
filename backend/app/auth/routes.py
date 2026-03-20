from datetime import timedelta
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.auth.models import Deployment, User, UserDeploymentRole
from app.auth.schemas import (
    DeploymentCreate,
    DeploymentRead,
    LoginRequest,
    Role,
    Token,
    UserCreate,
    UserDeploymentRoleRead,
    UserDeploymentRoleUpdate,
    UserRead,
)
from app.auth.service import (
    create_access_token,
    get_current_user,
    get_user_role,
    hash_password,
    verify_password,
)
import uuid

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=Token)
async def login(body: LoginRequest, db: DBDep) -> Token:
    """Authenticate with email + password, return a JWT access token."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.deployment_roles))
        .where(User.email == body.email)
    )
    user: User | None = result.scalars().first()

    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    expire_hours = settings.access_token_expire_hours
    access_token = create_access_token(
        data={
            "sub": user.id,
            "email": user.email,
            "is_superuser": user.is_superuser,
        },
        expires_delta=timedelta(hours=expire_hours),
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=expire_hours * 3600,
    )


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUserDep, db: DBDep) -> UserRead:
    """Return the currently authenticated user with their deployment roles."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.deployment_roles))
        .where(User.id == current_user.id)
    )
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserRead.model_validate(user)


# ---------------------------------------------------------------------------
# Deployments (public)
# ---------------------------------------------------------------------------

@router.get("/deployments", response_model=List[DeploymentRead])
async def list_deployments(db: DBDep) -> List[DeploymentRead]:
    """List all active deployments (public endpoint, no auth required)."""
    result = await db.execute(
        select(Deployment).where(Deployment.is_active == True).order_by(Deployment.name)  # noqa: E712
    )
    deployments = result.scalars().all()
    return [DeploymentRead.model_validate(d) for d in deployments]


@router.post("/deployments", response_model=DeploymentRead, status_code=201)
async def create_deployment(
    body: DeploymentCreate,
    current_user: CurrentUserDep,
    db: DBDep,
) -> DeploymentRead:
    """Create a new deployment (SUPER_ADMIN only)."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Super admin required")

    existing = await db.execute(
        select(Deployment).where(Deployment.slug == body.slug)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Deployment slug already exists")

    deploy = Deployment(
        id=str(uuid.uuid4()),
        **body.model_dump(),
    )
    db.add(deploy)
    await db.flush()
    await db.refresh(deploy)
    return DeploymentRead.model_validate(deploy)


# ---------------------------------------------------------------------------
# User management (DEPLOY_ADMIN+)
# ---------------------------------------------------------------------------

def _require_deploy_admin(current_user: User, deployment_id: str) -> None:
    """Raise 403 if user is not DEPLOY_ADMIN or above for the deployment."""
    if current_user.is_superuser:
        return
    for dr in current_user.deployment_roles:
        if dr.deployment_id == deployment_id:
            if dr.role in (Role.SUPER_ADMIN.value, Role.DEPLOY_ADMIN.value):
                return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="DEPLOY_ADMIN or higher required",
    )


@router.post("/users", response_model=UserRead, status_code=201)
async def create_user(
    body: UserCreate,
    current_user: CurrentUserDep,
    db: DBDep,
    x_deployment_id: str = Header(default="ssen", alias="X-Deployment-ID"),
) -> UserRead:
    """Create a new user (DEPLOY_ADMIN+ for the target deployment)."""
    await db.execute(
        select(User).options(selectinload(User.deployment_roles)).where(User.id == current_user.id)
    )
    _require_deploy_admin(current_user, x_deployment_id.lower())

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Email already registered")

    new_user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        is_superuser=body.is_superuser and current_user.is_superuser,
        is_active=True,
    )
    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)

    result = await db.execute(
        select(User)
        .options(selectinload(User.deployment_roles))
        .where(User.id == new_user.id)
    )
    user = result.scalars().first()
    return UserRead.model_validate(user)


@router.get("/users", response_model=List[UserRead])
async def list_users(
    current_user: CurrentUserDep,
    db: DBDep,
    x_deployment_id: str = Header(default="ssen", alias="X-Deployment-ID"),
) -> List[UserRead]:
    """List all users that have a role in the given deployment (DEPLOY_ADMIN+)."""
    _require_deploy_admin(current_user, x_deployment_id.lower())

    result = await db.execute(
        select(User)
        .options(selectinload(User.deployment_roles))
        .join(UserDeploymentRole, User.id == UserDeploymentRole.user_id)
        .where(UserDeploymentRole.deployment_id == x_deployment_id.lower())
    )
    users = result.scalars().unique().all()
    return [UserRead.model_validate(u) for u in users]


@router.put("/users/{user_id}/role", response_model=UserDeploymentRoleRead)
async def update_user_role(
    user_id: str,
    body: UserDeploymentRoleUpdate,
    current_user: CurrentUserDep,
    db: DBDep,
    x_deployment_id: str = Header(default="ssen", alias="X-Deployment-ID"),
) -> UserDeploymentRoleRead:
    """Update a user's role for the given deployment (DEPLOY_ADMIN+)."""
    _require_deploy_admin(current_user, x_deployment_id.lower())

    result = await db.execute(
        select(UserDeploymentRole).where(
            UserDeploymentRole.user_id == user_id,
            UserDeploymentRole.deployment_id == x_deployment_id.lower(),
        )
    )
    role_row: UserDeploymentRole | None = result.scalars().first()

    if role_row is None:
        # Create new role assignment
        role_row = UserDeploymentRole(
            id=str(uuid.uuid4()),
            user_id=user_id,
            deployment_id=x_deployment_id.lower(),
            role=body.role.value,
        )
        db.add(role_row)
        await db.flush()
    else:
        role_row.role = body.role.value
        await db.flush()

    await db.refresh(role_row)
    return UserDeploymentRoleRead.model_validate(role_row)
