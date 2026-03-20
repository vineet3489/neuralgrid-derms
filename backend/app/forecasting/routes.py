"""Forecasting API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.deps import CurrentUserDep, DBDep, DeploymentDep
from app.forecasting.service import get_latest_forecast, run_forecast_update

router = APIRouter(prefix="/api/v1/forecasting", tags=["forecasting"])


@router.get("/solar")
async def get_solar_forecast(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Latest 48-hour solar generation forecast."""
    result = await get_latest_forecast(db, deployment_id, "SOLAR")
    if not result:
        raise HTTPException(status_code=404, detail="No solar forecast available. Try POST /forecasting/refresh")
    return result


@router.get("/load")
async def get_load_forecast(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Latest 48-hour demand forecast."""
    result = await get_latest_forecast(db, deployment_id, "LOAD")
    if not result:
        raise HTTPException(status_code=404, detail="No load forecast available. Try POST /forecasting/refresh")
    return result


@router.get("/flex")
async def get_flex_forecast(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Latest 48-hour flex availability forecast."""
    result = await get_latest_forecast(db, deployment_id, "FLEX_AVAILABILITY")
    if not result:
        raise HTTPException(status_code=404, detail="No flex forecast available. Try POST /forecasting/refresh")
    return result


@router.get("/all")
async def get_all_forecasts(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Return solar, load, and flex forecasts in a single response (used by dashboard)."""
    solar = await get_latest_forecast(db, deployment_id, "SOLAR")
    load = await get_latest_forecast(db, deployment_id, "LOAD")
    flex = await get_latest_forecast(db, deployment_id, "FLEX_AVAILABILITY")
    return {
        "deployment_id": deployment_id,
        "solar": solar,
        "load": load,
        "flex": flex,
    }


@router.post("/refresh")
async def refresh_forecasts(
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
) -> dict:
    """Manually trigger a forecast regeneration for this deployment (DEPLOY_ADMIN or higher)."""
    try:
        preview = await run_forecast_update(db, deployment_id)
        return {
            "status": "ok",
            "deployment_id": deployment_id,
            "preview_next_8_intervals": preview,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Forecast update failed: {exc}")
