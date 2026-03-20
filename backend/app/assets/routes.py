"""FastAPI routes for DER Assets."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.auth.models import User
from app.auth.schemas import Role
from app.auth.service import get_current_user, require_role
from app.core.deps import DBDep, DeploymentDep
from app.assets.schemas import (
    DERAssetCreate,
    DERAssetRead,
    DERAssetUpdate,
    AssetTelemetryRead,
    DOECurrentRead,
    DOEHistoryRead,
    DOEUpdate,
    TelemetryIngest,
)
from app.assets.service import (
    create_asset,
    delete_asset,
    get_asset,
    get_asset_telemetry_history,
    get_doe_history,
    ingest_telemetry,
    list_assets,
    update_asset,
    update_doe,
)

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])

_grid_ops_plus = require_role(
    Role.GRID_OPS, Role.CONTRACT_MGR, Role.PROG_MGR, Role.DEPLOY_ADMIN, Role.SUPER_ADMIN
)
_deploy_admin_plus = require_role(Role.DEPLOY_ADMIN, Role.SUPER_ADMIN)


@router.get("/", response_model=list[DERAssetRead])
async def route_list_assets(
    db: DBDep,
    deployment_id: DeploymentDep,
    counterparty_id: Optional[str] = Query(default=None),
    type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    _user: User = Depends(get_current_user),
):
    """List DER assets for the deployment."""
    return await list_assets(
        db, deployment_id,
        counterparty_id=counterparty_id,
        type_filter=type,
        status_filter=status,
    )


@router.get("/summary")
async def route_assets_summary(
    db: DBDep,
    deployment_id: DeploymentDep,
    _user: User = Depends(get_current_user),
) -> dict:
    """Return aggregated capacity summary grouped by asset type."""
    from sqlalchemy import select, func  # noqa: PLC0415
    from app.assets.models import DERAsset  # noqa: PLC0415

    stmt = (
        select(DERAsset.type, func.count(DERAsset.id), func.sum(DERAsset.capacity_kw))
        .where(DERAsset.deployment_id == deployment_id, DERAsset.deleted_at.is_(None))
        .group_by(DERAsset.type)
    )
    result = await db.execute(stmt)
    rows = result.all()
    by_type = {r[0]: {"count": r[1], "capacity_kw": r[2] or 0.0} for r in rows}
    total_assets = sum(v["count"] for v in by_type.values())
    total_kw = sum(v["capacity_kw"] for v in by_type.values())
    return {
        "deployment_id": deployment_id,
        "total_assets": total_assets,
        "total_capacity_kw": total_kw,
        "by_type": by_type,
    }


@router.get("/{asset_id}", response_model=DERAssetRead)
async def route_get_asset(
    asset_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    _user: User = Depends(get_current_user),
):
    return await get_asset(db, asset_id, deployment_id)


@router.get("/{asset_id}/telemetry", response_model=list[AssetTelemetryRead])
async def route_get_telemetry(
    asset_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    hours: int = Query(default=24, ge=1, le=168),
    _user: User = Depends(get_current_user),
):
    """Return telemetry history for an asset (default last 24 hours, max 7 days)."""
    return await get_asset_telemetry_history(db, asset_id, deployment_id, hours=hours)


@router.post("/{asset_id}/telemetry", response_model=AssetTelemetryRead, status_code=status.HTTP_201_CREATED)
async def route_ingest_telemetry(
    asset_id: str,
    data: TelemetryIngest,
    db: DBDep,
    deployment_id: DeploymentDep,
    _user: User = Depends(get_current_user),
):
    """Manually ingest a telemetry reading (for testing / manual override)."""
    ts = await ingest_telemetry(
        db,
        asset_id=asset_id,
        deployment_id=deployment_id,
        power_kw=data.power_kw,
        voltage_v=data.voltage_v,
        current_a=data.current_a,
        soc_pct=data.soc_pct,
        frequency_hz=data.frequency_hz,
        temperature_c=data.temperature_c,
        source=data.source,
    )
    return ts


@router.get("/{asset_id}/doe", response_model=DOECurrentRead)
async def route_get_doe(
    asset_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    _user: User = Depends(get_current_user),
):
    """Return current DOE limits and recent history for an asset."""
    asset = await get_asset(db, asset_id, deployment_id)
    history = await get_doe_history(db, asset_id, deployment_id)
    return DOECurrentRead(
        asset_id=asset.id,
        doe_import_max_kw=asset.doe_import_max_kw,
        doe_export_max_kw=asset.doe_export_max_kw,
        doe_last_updated=asset.doe_last_updated,
        history=history,  # type: ignore[arg-type]
    )


@router.post("/{asset_id}/doe", response_model=DERAssetRead)
async def route_update_doe(
    asset_id: str,
    data: DOEUpdate,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_grid_ops_plus),
):
    """Update Dynamic Operating Envelope for an asset. Requires GRID_OPS or higher."""
    asset = await update_doe(
        db,
        asset_id=asset_id,
        deployment_id=deployment_id,
        import_max_kw=data.import_max_kw,
        export_max_kw=data.export_max_kw,
        event_id=data.event_id,
        reason=data.reason,
        issued_by=user.id,
        interval_start=data.interval_start,
        interval_end=data.interval_end,
    )
    return asset


@router.post("/", response_model=DERAssetRead, status_code=status.HTTP_201_CREATED)
async def route_create_asset(
    data: DERAssetCreate,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_grid_ops_plus),
):
    """Register a new DER asset. Requires GRID_OPS or higher."""
    return await create_asset(db, data, deployment_id, user.id)


@router.put("/{asset_id}", response_model=DERAssetRead)
async def route_update_asset(
    asset_id: str,
    data: DERAssetUpdate,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_grid_ops_plus),
):
    return await update_asset(db, asset_id, data, deployment_id, user.id)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def route_delete_asset(
    asset_id: str,
    db: DBDep,
    deployment_id: DeploymentDep,
    user: User = Depends(_deploy_admin_plus),
):
    """Deregister (soft-delete) an asset. Requires DEPLOY_ADMIN or higher."""
    await delete_asset(db, asset_id, deployment_id, user.id)
