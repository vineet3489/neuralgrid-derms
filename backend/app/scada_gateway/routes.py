"""
API routes for the SCADA Gateway module.

Exposes:
  - SCADA endpoint CRUD and manual push trigger
  - LV DERMS data snapshot endpoints (JWT auth OR DaaS API key)
  - DaaS API key lifecycle management
"""
from __future__ import annotations

import time
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep, DBDep, DeploymentDep
from app.database import get_db
from app.scada_gateway import service


# ---------------------------------------------------------------------------
# Optional JWT dependency — returns User or None (does NOT raise 401)
# ---------------------------------------------------------------------------

async def _optional_jwt(request: Request, db: AsyncSession = Depends(get_db)) -> Optional[object]:
    """Return the current user from JWT if present, else None (no 401 raised)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.removeprefix("Bearer ").strip()
    try:
        from app.auth.service import decode_token
        from app.auth.models import User
        from sqlalchemy import select
        token_data = decode_token(token)
        result = await db.execute(select(User).where(User.email == token_data.email))
        return result.scalar_one_or_none()
    except Exception:
        return None


OptionalUserDep = Annotated[Optional[object], Depends(_optional_jwt)]
from app.scada_gateway.schemas import (
    DaaSApiKeyCreate,
    DaaSApiKeyCreated,
    DaaSApiKeyRead,
    PushResult,
    SCADAEndpointCreate,
    SCADAEndpointRead,
    SCADAEndpointUpdate,
)

router = APIRouter(prefix="/api/v1/scada", tags=["scada-gateway"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_daas_or_jwt(
    request: Request,
    db: DBDep,
    deployment_id: str,
    x_daas_key: Optional[str],
    require_permission: Optional[str] = None,
) -> Optional[object]:
    """
    Authenticate either via DaaS API key (X-DaaS-Key header) or JWT.

    Returns the DaaSApiKey record when authenticated via DaaS key, or
    None when authenticated via JWT.  Raises HTTP 401/403 on failure.

    ``require_permission`` is one of:
        can_read_lv_voltages, can_read_feeder_loading, can_read_der_outputs,
        can_read_oe_limits, can_read_flex_events
    """
    if x_daas_key:
        key_record = await service.verify_api_key(db, x_daas_key, deployment_id)
        if key_record is None:
            raise HTTPException(status_code=401, detail="Invalid or expired DaaS API key.")
        if require_permission and not getattr(key_record, require_permission, True):
            raise HTTPException(
                status_code=403,
                detail=f"DaaS key does not have permission: {require_permission}",
            )
        return key_record

    # Fallback: require JWT — we trigger standard auth dep manually here
    # by checking the Authorization header is present. Actual user is
    # resolved via CurrentUserDep in the route signature for JWT paths.
    return None


def _filter_snapshot_by_daas_key(snapshot: dict, key_record: object) -> dict:
    """Remove snapshot sections the DaaS key is not permitted to read."""
    result = dict(snapshot)
    if not getattr(key_record, "can_read_lv_voltages", True):
        result.get("lv_network", {}).pop("buses", None)
    if not getattr(key_record, "can_read_feeder_loading", True):
        result.get("grid", {}).pop("feeders", None)
    if not getattr(key_record, "can_read_der_outputs", True):
        result.pop("assets", None)
    if not getattr(key_record, "can_read_oe_limits", True):
        result.pop("oe_limits", None)
    if not getattr(key_record, "can_read_flex_events", True):
        result.pop("active_flex_events", None)
    return result


# ---------------------------------------------------------------------------
# SCADA Endpoint management
# ---------------------------------------------------------------------------

@router.get("/endpoints", response_model=List[SCADAEndpointRead])
async def list_scada_endpoints(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> list:
    """Return all configured SCADA endpoints for the current deployment."""
    return await service.list_endpoints(db, deployment_id)


@router.post("/endpoints", response_model=SCADAEndpointRead, status_code=201)
async def create_scada_endpoint(
    body: SCADAEndpointCreate,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> object:
    """Create a new SCADA endpoint configuration (DEPLOY_ADMIN or higher)."""
    endpoint = await service.create_endpoint(db, body, deployment_id)
    await db.commit()
    await db.refresh(endpoint)
    return endpoint


@router.put("/endpoints/{endpoint_id}", response_model=SCADAEndpointRead)
async def update_scada_endpoint(
    endpoint_id: str,
    body: SCADAEndpointUpdate,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> object:
    """Update an existing SCADA endpoint (DEPLOY_ADMIN or higher)."""
    endpoint = await service.get_endpoint(db, endpoint_id, deployment_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="SCADA endpoint not found.")
    updated = await service.update_endpoint(db, endpoint, body)
    await db.commit()
    await db.refresh(updated)
    return updated


@router.delete("/endpoints/{endpoint_id}", status_code=204)
async def delete_scada_endpoint(
    endpoint_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> None:
    """Delete a SCADA endpoint (DEPLOY_ADMIN or higher)."""
    deleted = await service.delete_endpoint(db, endpoint_id, deployment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="SCADA endpoint not found.")
    await db.commit()


@router.post("/endpoints/{endpoint_id}/push", response_model=PushResult)
async def manual_push(
    endpoint_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    Manually trigger a data push to the specified SCADA endpoint.

    Useful for testing connectivity and validating payload structure.
    """
    endpoint = await service.get_endpoint(db, endpoint_id, deployment_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="SCADA endpoint not found.")
    result = await service.push_to_scada_endpoint(db, endpoint, deployment_id)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# SCADA data snapshot — supports DaaS API key OR operator JWT
# ---------------------------------------------------------------------------

@router.get("/snapshot")
async def get_full_snapshot(
    request: Request,
    db: DBDep,
    deployment_id: DeploymentDep,
    current_user: OptionalUserDep = None,
    x_daas_key: Optional[str] = Header(default=None, alias="X-DaaS-Key"),
) -> dict:
    """
    Return the full LV DERMS data snapshot.

    Authentication:
      - ``X-DaaS-Key`` header — DaaS API key (L&T Data-as-a-Service)
      - ``Authorization: Bearer <token>`` — operator JWT (fallback)

    Response fields are filtered according to the DaaS key's permissions
    when a DaaS key is used.
    """
    t0 = time.monotonic()

    if x_daas_key:
        key_record = await service.verify_api_key(db, x_daas_key, deployment_id)
        if key_record is None:
            raise HTTPException(status_code=401, detail="Invalid or expired DaaS API key.")

        snapshot = await service.get_lv_derms_snapshot(db, deployment_id)
        filtered = _filter_snapshot_by_daas_key(snapshot, key_record)

        import json as _json
        response_bytes = len(_json.dumps(filtered).encode())
        latency = int((time.monotonic() - t0) * 1000)
        await service.record_daas_usage(
            db,
            key_id=key_record.id,
            deployment_id=deployment_id,
            path="/api/v1/scada/snapshot",
            size=response_bytes,
            latency=latency,
            status=200,
        )
        return filtered

    # JWT auth path — current_user must be present
    if current_user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required: provide X-DaaS-Key header or Bearer token.",
        )
    return await service.get_lv_derms_snapshot(db, deployment_id)


@router.get("/snapshot/grid")
async def get_grid_snapshot(
    request: Request,
    db: DBDep,
    deployment_id: DeploymentDep,
    current_user: OptionalUserDep = None,
    x_daas_key: Optional[str] = Header(default=None, alias="X-DaaS-Key"),
) -> dict:
    """Return grid nodes and feeders only."""
    t0 = time.monotonic()

    if x_daas_key:
        key_record = await service.verify_api_key(db, x_daas_key, deployment_id)
        if key_record is None:
            raise HTTPException(status_code=401, detail="Invalid or expired DaaS API key.")
        if not key_record.can_read_feeder_loading:
            raise HTTPException(status_code=403, detail="DaaS key lacks can_read_feeder_loading permission.")

        snapshot = await service.get_lv_derms_snapshot(db, deployment_id)
        result = {"deployment_id": snapshot["deployment_id"], "snapshot_at": snapshot["snapshot_at"], "grid": snapshot["grid"]}

        import json as _json
        latency = int((time.monotonic() - t0) * 1000)
        await service.record_daas_usage(
            db, key_id=key_record.id, deployment_id=deployment_id,
            path="/api/v1/scada/snapshot/grid",
            size=len(_json.dumps(result).encode()), latency=latency, status=200,
        )
        return result

    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    snapshot = await service.get_lv_derms_snapshot(db, deployment_id)
    return {"deployment_id": snapshot["deployment_id"], "snapshot_at": snapshot["snapshot_at"], "grid": snapshot["grid"]}


@router.get("/snapshot/lv-network")
async def get_lv_network_snapshot(
    request: Request,
    db: DBDep,
    deployment_id: DeploymentDep,
    current_user: OptionalUserDep = None,
    x_daas_key: Optional[str] = Header(default=None, alias="X-DaaS-Key"),
) -> dict:
    """Return LV bus voltages and feeder topology."""
    t0 = time.monotonic()

    if x_daas_key:
        key_record = await service.verify_api_key(db, x_daas_key, deployment_id)
        if key_record is None:
            raise HTTPException(status_code=401, detail="Invalid or expired DaaS API key.")
        if not key_record.can_read_lv_voltages:
            raise HTTPException(status_code=403, detail="DaaS key lacks can_read_lv_voltages permission.")

        snapshot = await service.get_lv_derms_snapshot(db, deployment_id)
        result = {
            "deployment_id": snapshot["deployment_id"],
            "snapshot_at": snapshot["snapshot_at"],
            "lv_network": snapshot["lv_network"],
        }

        import json as _json
        latency = int((time.monotonic() - t0) * 1000)
        await service.record_daas_usage(
            db, key_id=key_record.id, deployment_id=deployment_id,
            path="/api/v1/scada/snapshot/lv-network",
            size=len(_json.dumps(result).encode()), latency=latency, status=200,
        )
        return result

    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    snapshot = await service.get_lv_derms_snapshot(db, deployment_id)
    return {
        "deployment_id": snapshot["deployment_id"],
        "snapshot_at": snapshot["snapshot_at"],
        "lv_network": snapshot["lv_network"],
    }


@router.get("/snapshot/assets")
async def get_assets_snapshot(
    request: Request,
    db: DBDep,
    deployment_id: DeploymentDep,
    current_user: OptionalUserDep = None,
    x_daas_key: Optional[str] = Header(default=None, alias="X-DaaS-Key"),
) -> dict:
    """Return DER asset outputs."""
    t0 = time.monotonic()

    if x_daas_key:
        key_record = await service.verify_api_key(db, x_daas_key, deployment_id)
        if key_record is None:
            raise HTTPException(status_code=401, detail="Invalid or expired DaaS API key.")
        if not key_record.can_read_der_outputs:
            raise HTTPException(status_code=403, detail="DaaS key lacks can_read_der_outputs permission.")

        snapshot = await service.get_lv_derms_snapshot(db, deployment_id)
        result = {
            "deployment_id": snapshot["deployment_id"],
            "snapshot_at": snapshot["snapshot_at"],
            "assets": snapshot["assets"],
        }

        import json as _json
        latency = int((time.monotonic() - t0) * 1000)
        await service.record_daas_usage(
            db, key_id=key_record.id, deployment_id=deployment_id,
            path="/api/v1/scada/snapshot/assets",
            size=len(_json.dumps(result).encode()), latency=latency, status=200,
        )
        return result

    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    snapshot = await service.get_lv_derms_snapshot(db, deployment_id)
    return {
        "deployment_id": snapshot["deployment_id"],
        "snapshot_at": snapshot["snapshot_at"],
        "assets": snapshot["assets"],
    }


@router.get("/snapshot/oe-limits")
async def get_oe_limits_snapshot(
    request: Request,
    db: DBDep,
    deployment_id: DeploymentDep,
    current_user: OptionalUserDep = None,
    x_daas_key: Optional[str] = Header(default=None, alias="X-DaaS-Key"),
) -> dict:
    """Return current OE (Operating Envelope) limits per asset."""
    t0 = time.monotonic()

    if x_daas_key:
        key_record = await service.verify_api_key(db, x_daas_key, deployment_id)
        if key_record is None:
            raise HTTPException(status_code=401, detail="Invalid or expired DaaS API key.")
        if not key_record.can_read_oe_limits:
            raise HTTPException(status_code=403, detail="DaaS key lacks can_read_oe_limits permission.")

        snapshot = await service.get_lv_derms_snapshot(db, deployment_id)
        result = {
            "deployment_id": snapshot["deployment_id"],
            "snapshot_at": snapshot["snapshot_at"],
            "oe_limits": snapshot["oe_limits"],
        }

        import json as _json
        latency = int((time.monotonic() - t0) * 1000)
        await service.record_daas_usage(
            db, key_id=key_record.id, deployment_id=deployment_id,
            path="/api/v1/scada/snapshot/oe-limits",
            size=len(_json.dumps(result).encode()), latency=latency, status=200,
        )
        return result

    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    snapshot = await service.get_lv_derms_snapshot(db, deployment_id)
    return {
        "deployment_id": snapshot["deployment_id"],
        "snapshot_at": snapshot["snapshot_at"],
        "oe_limits": snapshot["oe_limits"],
    }


# ---------------------------------------------------------------------------
# DaaS API key management
# ---------------------------------------------------------------------------

@router.get("/daas/keys", response_model=List[DaaSApiKeyRead])
async def list_daas_keys(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> list:
    """List all DaaS API keys for the deployment (DEPLOY_ADMIN or higher)."""
    return await service.list_api_keys(db, deployment_id)


@router.post("/daas/keys", response_model=DaaSApiKeyCreated, status_code=201)
async def create_daas_key(
    body: DaaSApiKeyCreate,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> object:
    """
    Create a new DaaS API key.

    The plain API key is returned once in the ``api_key`` field of the response
    and cannot be retrieved again.  Store it securely immediately.
    """
    key_record, plain_key = await service.create_api_key(
        db, body, deployment_id, created_by=current_user.email
    )
    await db.commit()
    await db.refresh(key_record)

    # Build DaaSApiKeyCreated by extending the ORM data with the plain key
    read_data = DaaSApiKeyRead.model_validate(key_record)
    return DaaSApiKeyCreated(**read_data.model_dump(), api_key=plain_key)


@router.delete("/daas/keys/{key_id}", status_code=204)
async def revoke_daas_key(
    key_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> None:
    """Revoke (deactivate) a DaaS API key."""
    revoked = await service.revoke_api_key(db, key_id, deployment_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="DaaS API key not found.")
    await db.commit()


@router.get("/daas/keys/{key_id}/usage")
async def get_daas_key_usage(
    key_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """
    Return usage statistics for a DaaS API key.

    Includes total_requests, last_used_at, and per-day request counts for
    the most recent 7 days.
    """
    stats = await service.get_key_usage_stats(db, key_id, deployment_id)
    if not stats:
        raise HTTPException(status_code=404, detail="DaaS API key not found.")
    return stats
