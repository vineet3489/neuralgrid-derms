from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.service import get_current_user
from app.auth.schemas import Role


async def get_deployment_id(
    x_deployment_id: str = Header(default="ssen", alias="X-Deployment-ID")
) -> str:
    """Extract and normalise deployment ID from X-Deployment-ID header."""
    return x_deployment_id.lower()


# Typed dependency aliases -------------------------------------------------------

DBDep = Annotated[AsyncSession, Depends(get_db)]
DeploymentDep = Annotated[str, Depends(get_deployment_id)]

# CurrentUserDep is typed as Any here to avoid circular import; callers should
# annotate the parameter as `User` directly when they need the model type.
from app.auth.models import User  # noqa: E402

CurrentUserDep = Annotated[User, Depends(get_current_user)]
