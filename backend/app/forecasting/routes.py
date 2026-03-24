"""Forecasting API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import CurrentUserDep, DBDep, DeploymentDep
from app.forecasting.service import (
    generate_asset_level_forecast,
    generate_lv_feeder_forecast,
    generate_oe_headroom_forecast,
    get_latest_forecast,
    run_forecast_update,
)

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


@router.get("/lv-feeder/{feeder_id}")
async def get_lv_feeder_forecast(
    feeder_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    horizon_hours: int = Query(48, ge=1, le=168, description="Forecast horizon in hours"),
) -> dict:
    """
    Load/solar/EV generation forecast for an LV feeder behind a DT.
    Returns 30-min intervals with load_kw, solar_kw, ev_kw, net_kw and confidence bands.
    """
    try:
        result = await generate_lv_feeder_forecast(db, feeder_id, deployment_id, horizon_hours)
        return {
            "feeder_id": feeder_id,
            "deployment_id": deployment_id,
            "horizon_hours": horizon_hours,
            "interval_count": len(result),
            "intervals": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/asset/{asset_id}")
async def get_asset_forecast(
    asset_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    horizon_hours: int = Query(48, ge=1, le=168, description="Forecast horizon in hours"),
) -> dict:
    """
    Asset-specific generation or consumption forecast.
    Accounts for asset type: PV bell-curve, BESS flat-zero, EV arrival pattern,
    heat pump temperature profile, or industrial weekday/weekend profile.
    """
    try:
        result = await generate_asset_level_forecast(db, asset_id, deployment_id, horizon_hours)
        return {
            "asset_id": asset_id,
            "deployment_id": deployment_id,
            "horizon_hours": horizon_hours,
            "interval_count": len(result),
            "intervals": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/oe-headroom/{cmz_id}")
async def get_oe_headroom_forecast(
    cmz_id: str,
    db: DBDep,
    current_user: CurrentUserDep,
    deployment_id: DeploymentDep,
    horizon_hours: int = Query(24, ge=1, le=72, description="Forecast horizon in hours"),
) -> dict:
    """
    Operating envelope headroom forecast for a CMZ.
    Returns available flex headroom, OE limits, and forecast load/generation
    at 30-min intervals.  Feeds directly into the OE planning workflow.
    """
    try:
        result = await generate_oe_headroom_forecast(db, cmz_id, deployment_id, horizon_hours)
        return {
            "cmz_id": cmz_id,
            "deployment_id": deployment_id,
            "horizon_hours": horizon_hours,
            "interval_count": len(result),
            "intervals": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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
