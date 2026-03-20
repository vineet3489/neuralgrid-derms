from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class Role(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    DEPLOY_ADMIN = "DEPLOY_ADMIN"
    GRID_OPS = "GRID_OPS"
    PROG_MGR = "PROG_MGR"
    CONTRACT_MGR = "CONTRACT_MGR"
    VIEWER = "VIEWER"


# ---------------------------------------------------------------------------
# Token schemas
# ---------------------------------------------------------------------------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenData(BaseModel):
    user_id: str
    email: str
    is_superuser: bool = False


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    full_name: str
    is_superuser: bool = False


class UserRead(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
    deployment_roles: list["UserDeploymentRoleRead"] = []

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8)


# ---------------------------------------------------------------------------
# Deployment schemas
# ---------------------------------------------------------------------------

class DeploymentCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=64)
    name: str
    country: str = Field(..., min_length=2, max_length=2)
    currency_code: str = Field(..., min_length=3, max_length=3)
    currency_minor_units: int = 100
    timezone: str
    regulatory_framework: str
    voltage_nominal: float = 230.0
    frequency_hz: float = 50.0
    settlement_cycle: str = Field(..., pattern="^(WEEKLY|MONTHLY|QUARTERLY)$")
    config: Optional[dict] = None


class DeploymentRead(BaseModel):
    id: str
    slug: str
    name: str
    country: str
    currency_code: str
    currency_minor_units: int
    timezone: str
    regulatory_framework: str
    voltage_nominal: float
    frequency_hz: float
    settlement_cycle: str
    is_active: bool
    config: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# UserDeploymentRole schemas
# ---------------------------------------------------------------------------

class UserDeploymentRoleRead(BaseModel):
    id: str
    user_id: str
    deployment_id: str
    role: Role

    model_config = {"from_attributes": True}


class UserDeploymentRoleUpdate(BaseModel):
    role: Role


# Resolve forward reference
UserRead.model_rebuild()
