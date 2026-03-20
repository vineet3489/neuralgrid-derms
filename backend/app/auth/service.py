from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.auth.models import Deployment, User, UserDeploymentRole
from app.auth.schemas import Role, TokenData

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_http_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if the plain password matches the hash."""
    return _pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=settings.access_token_expire_hours)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT, returning TokenData."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: Optional[str] = payload.get("sub")
        email: Optional[str] = payload.get("email")
        is_superuser: bool = payload.get("is_superuser", False)
        if user_id is None or email is None:
            raise credentials_exception
        return TokenData(user_id=user_id, email=email, is_superuser=is_superuser)
    except JWTError:
        raise credentials_exception


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_http_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: validate Bearer token and return the User."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = decode_token(credentials.credentials)

    result = await db.execute(
        select(User)
        .options(selectinload(User.deployment_roles))
        .where(User.id == token_data.user_id)
    )
    user: Optional[User] = result.scalars().first()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


async def get_user_role(
    user: User,
    deployment_id: str,
    db: AsyncSession,
) -> Optional[Role]:
    """Return the Role a user has for a given deployment, or None."""
    if user.is_superuser:
        return Role.SUPER_ADMIN

    # Ensure roles are loaded
    if not user.deployment_roles:
        result = await db.execute(
            select(UserDeploymentRole).where(
                UserDeploymentRole.user_id == user.id,
                UserDeploymentRole.deployment_id == deployment_id,
            )
        )
        role_row: Optional[UserDeploymentRole] = result.scalars().first()
        if role_row:
            return Role(role_row.role)
        return None

    for dr in user.deployment_roles:
        if dr.deployment_id == deployment_id:
            return Role(dr.role)
    return None


_ROLE_ORDER = [
    Role.SUPER_ADMIN,
    Role.DEPLOY_ADMIN,
    Role.GRID_OPS,
    Role.PROG_MGR,
    Role.CONTRACT_MGR,
    Role.VIEWER,
]


def _role_level(role: Role) -> int:
    try:
        return _ROLE_ORDER.index(role)
    except ValueError:
        return len(_ROLE_ORDER)


def require_role(*roles: Role):
    """
    Factory for a FastAPI dependency that enforces the caller has at least one
    of the given roles for the deployment specified in the X-Deployment-ID header.
    """

    async def _checker(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(_http_bearer),
        db: AsyncSession = Depends(get_db),
        x_deployment_id: str = "ssen",
    ) -> User:
        user = await get_current_user(credentials=credentials, db=db)
        user_role = await get_user_role(user, x_deployment_id, db)
        if user_role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No role for this deployment",
            )
        # Allow if the user's role level is equal to or higher privilege than any required role
        user_level = _role_level(user_role)
        required_levels = [_role_level(r) for r in roles]
        if not any(user_level <= req_lvl for req_lvl in required_levels):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {[r.value for r in roles]}",
            )
        return user

    return _checker


# ---------------------------------------------------------------------------
# Seed default data
# ---------------------------------------------------------------------------

async def seed_default_data(db: AsyncSession) -> None:
    """
    Idempotent seed: creates default deployments and users on first startup.
    Safe to call multiple times — skips records that already exist.
    """
    # -----------------------------------------------------------------------
    # Deployments
    # -----------------------------------------------------------------------
    deployments_seed = [
        Deployment(
            id=str(uuid.uuid4()),
            slug="ssen",
            name="SSEN South Scotland",
            country="GB",
            currency_code="GBP",
            currency_minor_units=100,
            timezone="Europe/London",
            regulatory_framework="ENA-CPP-2024 / RIIO-ED2",
            voltage_nominal=230.0,
            frequency_hz=50.0,
            settlement_cycle="WEEKLY",
            is_active=True,
            config={
                "grid_operator": "Scottish and Southern Electricity Networks",
                "licence_area": "South of Scotland",
                "dno_code": "SSEN",
            },
        ),
        Deployment(
            id=str(uuid.uuid4()),
            slug="puvvnl",
            name="PUVVNL Varanasi",
            country="IN",
            currency_code="INR",
            currency_minor_units=100,
            timezone="Asia/Kolkata",
            regulatory_framework="UPERC-DR-2025",
            voltage_nominal=230.0,
            frequency_hz=50.0,
            settlement_cycle="MONTHLY",
            is_active=True,
            config={
                "grid_operator": "Purvanchal Vidyut Vitran Nigam Limited",
                "licence_area": "Varanasi Urban",
                "discom_code": "PUVVNL",
            },
        ),
    ]

    for deploy in deployments_seed:
        existing = await db.execute(
            select(Deployment).where(Deployment.slug == deploy.slug)
        )
        if existing.scalars().first() is None:
            db.add(deploy)

    await db.flush()

    # -----------------------------------------------------------------------
    # Users
    # -----------------------------------------------------------------------
    users_seed = [
        {
            "email": "admin@neuralgrid.com",
            "password": "NeuralGrid2026!",
            "full_name": "Neural Grid Super Admin",
            "is_superuser": True,
            "roles": [
                ("ssen", Role.SUPER_ADMIN),
                ("puvvnl", Role.SUPER_ADMIN),
            ],
        },
        {
            "email": "ssen-operator@neuralgrid.com",
            "password": "SSENOps2026!",
            "full_name": "SSEN Grid Operator",
            "is_superuser": False,
            "roles": [
                ("ssen", Role.GRID_OPS),
            ],
        },
        {
            "email": "puvvnl-operator@neuralgrid.com",
            "password": "PUVVNLOps2026!",
            "full_name": "PUVVNL Grid Operator",
            "is_superuser": False,
            "roles": [
                ("puvvnl", Role.GRID_OPS),
            ],
        },
    ]

    for u_data in users_seed:
        existing = await db.execute(
            select(User).where(User.email == u_data["email"])
        )
        user = existing.scalars().first()
        if user is None:
            user = User(
                id=str(uuid.uuid4()),
                email=u_data["email"],
                hashed_password=hash_password(str(u_data["password"])),
                full_name=str(u_data["full_name"]),
                is_superuser=bool(u_data["is_superuser"]),
                is_active=True,
            )
            db.add(user)
            await db.flush()

        # Assign roles
        for deploy_slug, role in u_data["roles"]:  # type: ignore[misc]
            existing_role = await db.execute(
                select(UserDeploymentRole).where(
                    UserDeploymentRole.user_id == user.id,
                    UserDeploymentRole.deployment_id == deploy_slug,
                )
            )
            if existing_role.scalars().first() is None:
                db.add(
                    UserDeploymentRole(
                        id=str(uuid.uuid4()),
                        user_id=user.id,
                        deployment_id=deploy_slug,
                        role=role.value,
                    )
                )

    await db.flush()
