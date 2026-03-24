"""
Pydantic schemas for LV Network API responses.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, field_validator, model_validator


class LVFeederRead(BaseModel):
    """Response schema for an LVFeeder record."""

    model_config = {"from_attributes": True}

    id: str
    deployment_id: str
    dt_node_id: str
    name: str
    description: Optional[str] = None
    voltage_v: float
    length_m: float
    customer_count: int
    lat_centroid: Optional[float] = None
    lng_centroid: Optional[float] = None
    osm_way_ids: Optional[Any] = None       # returned as parsed list when possible
    route_geojson: Optional[Any] = None     # returned as parsed dict when possible
    last_pf_run_at: Optional[datetime] = None
    pf_result_json: Optional[Any] = None    # returned as parsed dict
    rated_kva: float
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _parse_json_fields(cls, data: Any) -> Any:
        """
        If the input is an ORM object (or dict with JSON strings), parse the
        JSON text fields into Python objects so the API response contains
        proper dicts / lists instead of raw JSON strings.
        """
        # Support both ORM objects and raw dicts
        if hasattr(data, "__dict__"):
            # ORM model instance — convert to dict for validation
            obj = data
            values: dict = {}

            for field in [
                "id", "deployment_id", "dt_node_id", "name", "description",
                "voltage_v", "length_m", "customer_count", "lat_centroid",
                "lng_centroid", "osm_way_ids", "route_geojson", "last_pf_run_at",
                "pf_result_json", "rated_kva", "created_at", "updated_at",
            ]:
                values[field] = getattr(obj, field, None)

            # Parse JSON string fields
            for json_field in ("osm_way_ids", "route_geojson", "pf_result_json"):
                raw = values.get(json_field)
                if isinstance(raw, str):
                    try:
                        values[json_field] = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        pass  # leave as string if unparseable

            return values

        elif isinstance(data, dict):
            for json_field in ("osm_way_ids", "route_geojson", "pf_result_json"):
                raw = data.get(json_field)
                if isinstance(raw, str):
                    try:
                        data[json_field] = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        pass
            return data

        return data


class LVBusRead(BaseModel):
    """Response schema for an LVBus record."""

    model_config = {"from_attributes": True}

    id: str
    lv_feeder_id: str
    deployment_id: str
    bus_ref: str
    name: Optional[str] = None
    bus_type: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    osm_node_id: Optional[str] = None
    phase: str
    p_kw: float
    q_kvar: float
    v_pu: float
    v_v: float
    voltage_status: str
    asset_id: Optional[str] = None
    created_at: datetime
