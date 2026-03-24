"""
API routes for the Integration Configuration Manager.

Allows operators to configure, inspect, and toggle simulation / live mode
for each external system integration (ADMS, DER aggregators, MDMS, weather).
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException

from app.core.deps import CurrentUserDep, DBDep, DeploymentDep
from app.integrations.config_mgr.schemas import (
    ConnectionTestResult,
    IntegrationConfigCreate,
    IntegrationConfigRead,
    IntegrationConfigUpdate,
    SimParamsUpdate,
)
from app.integrations.config_mgr import service

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


# ---------------------------------------------------------------------------
# List / Get
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[IntegrationConfigRead])
async def list_integration_configs(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> list:
    """Return all integration configs for the current deployment."""
    return await service.list_configs(db, deployment_id)


@router.get("/{config_id}", response_model=IntegrationConfigRead)
async def get_integration_config(
    config_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
):
    """Return a single integration config by ID."""
    cfg = await service.get_config(db, config_id, deployment_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Integration config not found")
    return cfg


# ---------------------------------------------------------------------------
# Create / Update / Delete
# ---------------------------------------------------------------------------

@router.post("/", response_model=IntegrationConfigRead, status_code=201)
async def create_integration_config(
    body: IntegrationConfigCreate,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> object:
    """Create a new integration config (DEPLOY_ADMIN or higher)."""
    cfg = await service.create_config(
        db, body, deployment_id, user_email=current_user.email
    )
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.put("/{config_id}", response_model=IntegrationConfigRead)
async def update_integration_config(
    config_id: str,
    body: IntegrationConfigUpdate,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> object:
    """Update an integration config (DEPLOY_ADMIN or higher)."""
    cfg = await service.update_config(db, config_id, body, deployment_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Integration config not found")
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.delete("/{config_id}", status_code=204)
async def delete_integration_config(
    config_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> None:
    """Delete an integration config (DEPLOY_ADMIN or higher)."""
    deleted = await service.delete_config(db, config_id, deployment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Integration config not found")
    await db.commit()


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

@router.post("/{config_id}/test", response_model=ConnectionTestResult)
async def test_connection(
    config_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    Test connectivity to the configured integration endpoint.

    SIMULATION mode always returns OK without making a network call.
    LIVE mode performs an HTTP GET to base_url and measures latency.
    """
    result = await service.test_connection(db, config_id, deployment_id)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# Simulation parameters
# ---------------------------------------------------------------------------

@router.get("/{config_id}/sim-params")
async def get_sim_params(
    config_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    Return the effective simulation parameters for this config.

    Merges DEFAULT_SIM_PARAMS for the integration type with any stored overrides.
    """
    cfg = await service.get_config(db, config_id, deployment_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Integration config not found")
    params = await service.get_sim_params(db, deployment_id, cfg.integration_type)
    return {
        "config_id": config_id,
        "integration_type": cfg.integration_type,
        "sim_params": params,
    }


@router.put("/{config_id}/sim-params")
async def update_sim_params(
    config_id: str,
    body: SimParamsUpdate,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    Merge-update simulation parameters for this config (DEPLOY_ADMIN or higher).

    Only supplied (non-null) values are applied; existing params are preserved.
    """
    # Convert to dict, preserving extra fields (ConfigDict extra="allow")
    params_dict = body.model_dump(exclude_none=True)
    cfg = await service.update_sim_params(db, config_id, deployment_id, params_dict)
    if not cfg:
        raise HTTPException(status_code=404, detail="Integration config not found")
    await db.commit()
    await db.refresh(cfg)
    import json
    stored = {}
    if cfg.sim_params:
        try:
            stored = json.loads(cfg.sim_params)
        except Exception:
            pass
    return {
        "config_id": config_id,
        "integration_type": cfg.integration_type,
        "sim_params": stored,
    }


# ---------------------------------------------------------------------------
# Toggle mode
# ---------------------------------------------------------------------------

@router.post("/{config_id}/toggle-mode", response_model=IntegrationConfigRead)
async def toggle_mode(
    config_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> object:
    """
    Switch the integration mode between SIMULATION and LIVE (DEPLOY_ADMIN or higher).

    Switching to LIVE requires a base_url to be configured.
    """
    cfg = await service.get_config(db, config_id, deployment_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Integration config not found")

    if cfg.mode == "SIMULATION" and not cfg.base_url:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot switch to LIVE mode: no base_url configured. "
                "Set base_url before toggling to LIVE."
            ),
        )

    cfg = await service.toggle_mode(db, config_id, deployment_id)
    await db.commit()
    await db.refresh(cfg)
    return cfg
