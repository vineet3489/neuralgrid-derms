"""
Business logic for the SCADA Gateway module.

Responsibilities:
  - Assemble the LV DERMS data snapshot for outbound push or DaaS serving
  - Push snapshots to configured SCADA endpoints (REST_JSON / CIM / edge protocols)
  - Generate and verify DaaS API keys (SHA-256, never store plain text)
  - Record metered DaaS usage (fire-and-forget)
  - Seed default SCADA endpoint configs (idempotent)
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from typing import Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import new_uuid, utcnow
from app.scada_gateway.models import DaaSApiKey, DaaSUsageRecord, SCADAEndpoint
from app.scada_gateway.schemas import DaaSApiKeyCreate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocols that require the hardware Edge Agent and cannot be simulated
# over plain HTTP.
# ---------------------------------------------------------------------------
_EDGE_AGENT_PROTOCOLS = {"MODBUS_TCP", "DNP3", "OPC_UA"}


# ---------------------------------------------------------------------------
# Data assembly
# ---------------------------------------------------------------------------

async def get_lv_derms_snapshot(db: AsyncSession, deployment_id: str) -> dict:
    """
    Assemble the full LV DERMS data snapshot for a deployment.

    Queries CMZs, GridNodes, LVFeeders, LVBuses, DERAssets, OEMessages,
    and active FlexEvents.  All fields are serialised to plain Python dicts
    so the result is JSON-serialisable without further processing.
    """
    snapshot_at = utcnow().isoformat()

    # ── Grid ──────────────────────────────────────────────────────────────
    from app.grid.models import CMZ, GridNode  # local import to avoid circulars

    cmz_rows = (
        await db.execute(
            select(CMZ).where(CMZ.deployment_id == deployment_id)
        )
    ).scalars().all()

    cmzs = [
        {
            "id": c.id,
            "slug": c.slug,
            "name": c.name,
            "max_import_kw": c.max_import_kw,
            "max_export_kw": c.max_export_kw,
        }
        for c in cmz_rows
    ]

    node_rows = (
        await db.execute(
            select(GridNode).where(GridNode.deployment_id == deployment_id)
        )
    ).scalars().all()

    feeders_grid = [
        {
            "node_id": n.node_id,
            "name": n.name,
            "loading_pct": n.current_loading_pct,
            "voltage_kv": n.voltage_kv,
            "status": "OVERLOADED" if n.current_loading_pct > 100 else "NORMAL",
        }
        for n in node_rows
        if n.node_type == "FEEDER"
    ]

    substations = [
        {
            "node_id": n.node_id,
            "name": n.name,
            "loading_pct": n.current_loading_pct,
            "status": "OVERLOADED" if n.current_loading_pct > 100 else "NORMAL",
        }
        for n in node_rows
        if n.node_type in ("SUBSTATION", "DISTRIBUTION_TRANSFORMER")
    ]

    # ── LV Network ────────────────────────────────────────────────────────
    from app.lv_network.models import LVBus, LVFeeder  # local import

    lv_feeder_rows = (
        await db.execute(
            select(LVFeeder).where(LVFeeder.deployment_id == deployment_id)
        )
    ).scalars().all()

    lv_feeders = [
        {
            "id": f.id,
            "dt_node_id": f.dt_node_id,
            "name": f.name,
            "voltage_v": f.voltage_v,
            "customer_count": f.customer_count,
        }
        for f in lv_feeder_rows
    ]

    lv_bus_rows = (
        await db.execute(
            select(LVBus).where(LVBus.deployment_id == deployment_id)
        )
    ).scalars().all()

    lv_buses = [
        {
            "id": b.id,
            "bus_ref": b.bus_ref,
            "v_pu": b.v_pu,
            "v_v": b.v_v,
            "voltage_status": b.voltage_status,
            "p_kw": b.p_kw,
            "q_kvar": b.q_kvar,
        }
        for b in lv_bus_rows
    ]

    # ── DER Assets ────────────────────────────────────────────────────────
    from app.assets.models import DERAsset  # local import

    asset_rows = (
        await db.execute(
            select(DERAsset).where(
                DERAsset.deployment_id == deployment_id,
                DERAsset.deleted_at.is_(None),
            )
        )
    ).scalars().all()

    assets = [
        {
            "id": a.id,
            "asset_ref": a.asset_ref,
            "name": a.name,
            "type": a.type,
            "status": a.status,
            "current_kw": a.current_kw,
            "lat": a.lat,
            "lng": a.lng,
            "connection_point_id": a.connection_point_id,
            "feeder_id": a.feeder_id,
            "dt_id": a.dt_id,
        }
        for a in asset_rows
    ]

    # ── OE Limits (latest per asset) ──────────────────────────────────────
    from app.dispatch.models import OEMessage  # local import

    # Fetch all OE messages ordered newest-first; deduplicate by asset_id
    oe_rows = (
        await db.execute(
            select(OEMessage).order_by(OEMessage.sent_at.desc())
        )
    ).scalars().all()

    seen_assets: set[str] = set()
    oe_limits = []
    for oe in oe_rows:
        if oe.asset_id not in seen_assets:
            seen_assets.add(oe.asset_id)
            oe_limits.append(
                {
                    "asset_id": oe.asset_id,
                    "import_max_kw": oe.import_max_kw,
                    "export_max_kw": oe.export_max_kw,
                    "direction": oe.direction,
                    "sent_at": oe.sent_at.isoformat() if oe.sent_at else None,
                }
            )

    # ── Active Flex Events ────────────────────────────────────────────────
    from app.dispatch.models import FlexEvent  # local import

    active_statuses = ("PLANNED", "PENDING_DISPATCH", "DISPATCHED", "IN_PROGRESS")
    flex_rows = (
        await db.execute(
            select(FlexEvent).where(
                FlexEvent.deployment_id == deployment_id,
                FlexEvent.status.in_(active_statuses),
            )
        )
    ).scalars().all()

    active_flex_events = [
        {
            "event_ref": e.event_ref,
            "event_type": e.event_type,
            "status": e.status,
            "cmz_id": e.cmz_id,
            "target_kw": e.target_kw,
            "dispatched_kw": e.dispatched_kw,
        }
        for e in flex_rows
    ]

    return {
        "deployment_id": deployment_id,
        "snapshot_at": snapshot_at,
        "grid": {
            "cmzs": cmzs,
            "feeders": feeders_grid,
            "substations": substations,
        },
        "lv_network": {
            "feeders": lv_feeders,
            "buses": lv_buses,
        },
        "assets": assets,
        "oe_limits": oe_limits,
        "active_flex_events": active_flex_events,
    }


async def push_to_scada_endpoint(
    db: AsyncSession, endpoint: SCADAEndpoint, deployment_id: str
) -> dict:
    """
    Push the current LV DERMS snapshot to a single configured SCADA endpoint.

    SIMULATION mode:
        - REST_JSON / IEC_61968_CIM / MQTT: snapshot assembled, returns SIMULATED result.
        - MODBUS_TCP / DNP3 / OPC_UA: returns SIMULATED with Edge Agent notice.
    LIVE mode:
        - REST_JSON / IEC_61968_CIM / MQTT: HTTP POST to {endpoint_url}/derms-data.
        - MODBUS_TCP / DNP3 / OPC_UA: returns SKIPPED with Edge Agent notice.

    Updates endpoint.last_push_at / last_push_status / last_push_message.
    Returns a PushResult-compatible dict.
    """
    started_at = time.monotonic()
    now = utcnow()

    # ── Check if Edge Agent protocol ──────────────────────────────────────
    if endpoint.protocol in _EDGE_AGENT_PROTOCOLS:
        msg = (
            f"Protocol {endpoint.protocol} requires L&T DERMS Edge Agent hardware "
            "gateway. Snapshot data returned for simulation."
        )
        endpoint.last_push_at = now
        endpoint.last_push_status = "SIMULATED"
        endpoint.last_push_message = msg
        db.add(endpoint)
        return {
            "status": "SIMULATED",
            "message": msg,
            "records_pushed": 0,
            "latency_ms": 0,
            "pushed_at": now.isoformat(),
        }

    # ── Assemble snapshot ─────────────────────────────────────────────────
    snapshot = await get_lv_derms_snapshot(db, deployment_id)

    # Filter based on push flags
    if not endpoint.push_lv_voltages:
        snapshot.get("lv_network", {}).pop("buses", None)
    if not endpoint.push_feeder_loading:
        snapshot.get("grid", {}).pop("feeders", None)
    if not endpoint.push_der_outputs:
        snapshot.pop("assets", None)
    if not endpoint.push_oe_limits:
        snapshot.pop("oe_limits", None)
    if not endpoint.push_flex_events:
        snapshot.pop("active_flex_events", None)

    records_pushed = _count_snapshot_records(snapshot)

    # ── SIMULATION mode ───────────────────────────────────────────────────
    # Determine mode from IntegrationConfig for SCADA type, defaulting to SIMULATION
    mode = await _get_scada_mode(db, deployment_id)

    if mode == "SIMULATION":
        latency_ms = int((time.monotonic() - started_at) * 1000)
        endpoint.last_push_at = now
        endpoint.last_push_status = "OK"
        endpoint.last_push_message = (
            f"SIMULATION: snapshot assembled, {records_pushed} records, "
            f"not transmitted."
        )
        db.add(endpoint)
        return {
            "status": "OK",
            "message": endpoint.last_push_message,
            "records_pushed": records_pushed,
            "latency_ms": latency_ms,
            "pushed_at": now.isoformat(),
        }

    # ── LIVE mode — HTTP POST ─────────────────────────────────────────────
    if not endpoint.endpoint_url:
        msg = "LIVE mode push skipped: no endpoint_url configured."
        endpoint.last_push_at = now
        endpoint.last_push_status = "SKIPPED"
        endpoint.last_push_message = msg
        db.add(endpoint)
        return {
            "status": "SKIPPED",
            "message": msg,
            "records_pushed": 0,
            "latency_ms": 0,
            "pushed_at": now.isoformat(),
        }

    target_url = endpoint.endpoint_url.rstrip("/") + "/derms-data"
    headers = _build_auth_headers(endpoint)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(target_url, json=snapshot, headers=headers)
            response.raise_for_status()

        latency_ms = int((time.monotonic() - started_at) * 1000)
        msg = f"OK: HTTP {response.status_code}, {records_pushed} records pushed."
        endpoint.last_push_at = now
        endpoint.last_push_status = "OK"
        endpoint.last_push_message = msg
        db.add(endpoint)
        return {
            "status": "OK",
            "message": msg,
            "records_pushed": records_pushed,
            "latency_ms": latency_ms,
            "pushed_at": now.isoformat(),
        }

    except httpx.HTTPStatusError as exc:
        latency_ms = int((time.monotonic() - started_at) * 1000)
        msg = f"FAILED: HTTP {exc.response.status_code} from {target_url}"
        endpoint.last_push_at = now
        endpoint.last_push_status = "FAILED"
        endpoint.last_push_message = msg
        db.add(endpoint)
        return {
            "status": "FAILED",
            "message": msg,
            "records_pushed": 0,
            "latency_ms": latency_ms,
            "pushed_at": now.isoformat(),
        }

    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.monotonic() - started_at) * 1000)
        msg = f"FAILED: {type(exc).__name__}: {exc}"
        endpoint.last_push_at = now
        endpoint.last_push_status = "FAILED"
        endpoint.last_push_message = msg
        db.add(endpoint)
        return {
            "status": "FAILED",
            "message": msg,
            "records_pushed": 0,
            "latency_ms": latency_ms,
            "pushed_at": now.isoformat(),
        }


async def run_push_cycle(db: AsyncSession, deployment_id: str) -> list[dict]:
    """
    Push to all active SCADA endpoints for a deployment.

    Called by the periodic background task.  Commits after each push so that
    endpoint state is persisted even if a subsequent endpoint fails.
    """
    rows = (
        await db.execute(
            select(SCADAEndpoint).where(
                SCADAEndpoint.deployment_id == deployment_id,
                SCADAEndpoint.is_active.is_(True),
            )
        )
    ).scalars().all()

    results = []
    for endpoint in rows:
        try:
            result = await push_to_scada_endpoint(db, endpoint, deployment_id)
            await db.commit()
            results.append({"endpoint_id": endpoint.id, "endpoint_name": endpoint.name, **result})
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "push_to_scada_endpoint failed for endpoint %s (%s): %s",
                endpoint.id,
                endpoint.name,
                exc,
            )
            results.append(
                {
                    "endpoint_id": endpoint.id,
                    "endpoint_name": endpoint.name,
                    "status": "FAILED",
                    "message": str(exc),
                    "records_pushed": 0,
                    "latency_ms": 0,
                    "pushed_at": utcnow().isoformat(),
                }
            )
    return results


# ---------------------------------------------------------------------------
# DaaS API key management
# ---------------------------------------------------------------------------

def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new DaaS API key.

    Returns:
        (plain_key, key_hash, key_prefix)

        plain_key  — "lt_daas_" + 32 random hex chars  (shown to user once only)
        key_prefix — first 16 chars of plain_key        (stored; shown in UI)
        key_hash   — SHA-256 hex digest of plain_key    (stored; used for verification)
    """
    random_part = secrets.token_hex(16)  # 32 hex chars
    plain_key = f"lt_daas_{random_part}"
    key_prefix = plain_key[:16]
    key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
    return plain_key, key_hash, key_prefix


async def create_api_key(
    db: AsyncSession,
    data: DaaSApiKeyCreate,
    deployment_id: str,
    created_by: Optional[str],
) -> tuple[DaaSApiKey, str]:
    """
    Create a new DaaS API key record.

    Returns:
        (DaaSApiKey ORM instance, plain_key)

    The plain_key must be shown to the caller exactly once and is not
    recoverable from the database thereafter.
    """
    plain_key, key_hash, key_prefix = generate_api_key()

    record = DaaSApiKey(
        id=new_uuid(),
        deployment_id=deployment_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=data.name,
        description=data.description,
        is_active=True,
        can_read_lv_voltages=data.can_read_lv_voltages,
        can_read_feeder_loading=data.can_read_feeder_loading,
        can_read_der_outputs=data.can_read_der_outputs,
        can_read_oe_limits=data.can_read_oe_limits,
        can_read_flex_events=data.can_read_flex_events,
        rate_limit_per_minute=data.rate_limit_per_minute,
        expires_at=data.expires_at,
        created_at=utcnow(),
        created_by=created_by,
    )
    db.add(record)
    return record, plain_key


async def verify_api_key(
    db: AsyncSession, plain_key: str, deployment_id: str
) -> Optional[DaaSApiKey]:
    """
    Verify a DaaS API key against stored hashes.

    Returns the DaaSApiKey record if the key is valid, active, not expired,
    and belongs to the given deployment.  Returns None otherwise.
    """
    key_hash = hashlib.sha256(plain_key.encode()).hexdigest()

    row = (
        await db.execute(
            select(DaaSApiKey).where(
                DaaSApiKey.key_hash == key_hash,
                DaaSApiKey.deployment_id == deployment_id,
                DaaSApiKey.is_active.is_(True),
            )
        )
    ).scalars().first()

    if row is None:
        return None

    # Check expiry
    if row.expires_at is not None and row.expires_at < utcnow():
        return None

    return row


async def record_daas_usage(
    db: AsyncSession,
    key_id: str,
    deployment_id: str,
    path: str,
    size: int,
    latency: int,
    status: int,
) -> None:
    """
    Append a DaaS usage record and increment the key's request counter.

    Fire-and-forget: exceptions are swallowed so they never propagate to the
    caller's response path.
    """
    try:
        record = DaaSUsageRecord(
            id=new_uuid(),
            api_key_id=key_id,
            deployment_id=deployment_id,
            endpoint_path=path,
            timestamp=utcnow(),
            response_size_bytes=size,
            latency_ms=latency,
            status_code=status,
        )
        db.add(record)

        # Increment total_requests and update last_used_at on the key
        key_row = await db.get(DaaSApiKey, key_id)
        if key_row is not None:
            key_row.total_requests = (key_row.total_requests or 0) + 1
            key_row.last_used_at = utcnow()
            db.add(key_row)

        await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("record_daas_usage failed silently: %s", exc)


# ---------------------------------------------------------------------------
# SCADA endpoint CRUD helpers used by routes
# ---------------------------------------------------------------------------

async def list_endpoints(db: AsyncSession, deployment_id: str) -> list[SCADAEndpoint]:
    rows = (
        await db.execute(
            select(SCADAEndpoint)
            .where(SCADAEndpoint.deployment_id == deployment_id)
            .order_by(SCADAEndpoint.created_at)
        )
    ).scalars().all()
    return list(rows)


async def get_endpoint(
    db: AsyncSession, endpoint_id: str, deployment_id: str
) -> Optional[SCADAEndpoint]:
    return (
        await db.execute(
            select(SCADAEndpoint).where(
                SCADAEndpoint.id == endpoint_id,
                SCADAEndpoint.deployment_id == deployment_id,
            )
        )
    ).scalars().first()


async def create_endpoint(
    db: AsyncSession,
    data: "SCADAEndpointCreate",  # type: ignore[name-defined]  # noqa: F821
    deployment_id: str,
) -> SCADAEndpoint:
    from app.scada_gateway.schemas import SCADAEndpointCreate as _Create  # noqa: F401

    now = utcnow()
    endpoint = SCADAEndpoint(
        id=new_uuid(),
        deployment_id=deployment_id,
        name=data.name,
        description=data.description,
        protocol=data.protocol,
        endpoint_url=data.endpoint_url,
        port=data.port,
        auth_type=data.auth_type,
        auth_config=data.auth_config,
        push_lv_voltages=data.push_lv_voltages,
        push_feeder_loading=data.push_feeder_loading,
        push_der_outputs=data.push_der_outputs,
        push_oe_limits=data.push_oe_limits,
        push_flex_events=data.push_flex_events,
        push_interval_seconds=data.push_interval_seconds,
        is_active=data.is_active,
        cim_model_id=data.cim_model_id,
        created_at=now,
        updated_at=now,
    )
    db.add(endpoint)
    return endpoint


async def update_endpoint(
    db: AsyncSession,
    endpoint: SCADAEndpoint,
    data: "SCADAEndpointUpdate",  # type: ignore[name-defined]  # noqa: F821
) -> SCADAEndpoint:
    update_data = data.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(endpoint, field, value)
    endpoint.updated_at = utcnow()
    db.add(endpoint)
    return endpoint


async def delete_endpoint(
    db: AsyncSession, endpoint_id: str, deployment_id: str
) -> bool:
    endpoint = await get_endpoint(db, endpoint_id, deployment_id)
    if endpoint is None:
        return False
    await db.delete(endpoint)
    return True


# ---------------------------------------------------------------------------
# DaaS API key CRUD helpers
# ---------------------------------------------------------------------------

async def list_api_keys(db: AsyncSession, deployment_id: str) -> list[DaaSApiKey]:
    rows = (
        await db.execute(
            select(DaaSApiKey)
            .where(DaaSApiKey.deployment_id == deployment_id)
            .order_by(DaaSApiKey.created_at)
        )
    ).scalars().all()
    return list(rows)


async def get_api_key_record(
    db: AsyncSession, key_id: str, deployment_id: str
) -> Optional[DaaSApiKey]:
    return (
        await db.execute(
            select(DaaSApiKey).where(
                DaaSApiKey.id == key_id,
                DaaSApiKey.deployment_id == deployment_id,
            )
        )
    ).scalars().first()


async def revoke_api_key(
    db: AsyncSession, key_id: str, deployment_id: str
) -> bool:
    key_record = await get_api_key_record(db, key_id, deployment_id)
    if key_record is None:
        return False
    key_record.is_active = False
    db.add(key_record)
    return True


async def get_key_usage_stats(
    db: AsyncSession, key_id: str, deployment_id: str
) -> dict:
    """
    Return usage statistics for a single DaaS API key.

    Includes total_requests, last_used_at, and per-day counts for the
    last 7 days.
    """
    key_record = await get_api_key_record(db, key_id, deployment_id)
    if key_record is None:
        return {}

    # Daily totals — group by date portion of timestamp
    daily_rows = (
        await db.execute(
            select(
                func.date(DaaSUsageRecord.timestamp).label("day"),
                func.count(DaaSUsageRecord.id).label("requests"),
                func.sum(DaaSUsageRecord.response_size_bytes).label("bytes"),
            )
            .where(DaaSUsageRecord.api_key_id == key_id)
            .group_by(func.date(DaaSUsageRecord.timestamp))
            .order_by(func.date(DaaSUsageRecord.timestamp).desc())
            .limit(7)
        )
    ).all()

    daily = [
        {"day": str(row.day), "requests": row.requests, "bytes": row.bytes or 0}
        for row in daily_rows
    ]

    return {
        "key_id": key_id,
        "total_requests": key_record.total_requests,
        "last_used_at": key_record.last_used_at.isoformat() if key_record.last_used_at else None,
        "daily": daily,
    }


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

async def seed_scada_endpoints(db: AsyncSession) -> None:
    """
    Seed default SCADA endpoint configs for both SSEN and PUVVNL deployments.

    Idempotent — checks by (deployment_id, name) before inserting.
    """
    default_endpoints: list[dict] = [
        # SSEN
        {
            "deployment_id": "ssen",
            "name": "GE ADMS (Primary)",
            "description": "GE Advanced Distribution Management System — primary connection",
            "protocol": "REST_JSON",
            "endpoint_url": "https://adms.ssen-simulation.local",
            "auth_type": "API_KEY",
            "push_lv_voltages": True,
            "push_feeder_loading": True,
            "push_der_outputs": True,
            "push_oe_limits": True,
            "push_flex_events": True,
            "push_interval_seconds": 30,
            "is_active": True,
        },
        {
            "deployment_id": "ssen",
            "name": "OSIsoft PI Historian",
            "description": "OSIsoft PI data historian for long-term DERMS telemetry archival",
            "protocol": "REST_JSON",
            "endpoint_url": "https://pi-historian.ssen-simulation.local",
            "auth_type": "BASIC",
            "push_lv_voltages": True,
            "push_feeder_loading": True,
            "push_der_outputs": True,
            "push_oe_limits": False,
            "push_flex_events": False,
            "push_interval_seconds": 60,
            "is_active": True,
        },
        # PUVVNL
        {
            "deployment_id": "puvvnl",
            "name": "PUVVNL SCADA",
            "description": "PUVVNL main SCADA system — Varanasi distribution circle",
            "protocol": "REST_JSON",
            "endpoint_url": "https://scada.puvvnl-simulation.local",
            "auth_type": "API_KEY",
            "push_lv_voltages": True,
            "push_feeder_loading": True,
            "push_der_outputs": True,
            "push_oe_limits": True,
            "push_flex_events": True,
            "push_interval_seconds": 30,
            "is_active": True,
        },
        {
            "deployment_id": "puvvnl",
            "name": "ABB MicroSCADA",
            "description": "ABB MicroSCADA Pro DMS substation automation — requires Edge Agent",
            "protocol": "MODBUS_TCP",
            "endpoint_url": None,
            "port": 502,
            "auth_type": "NONE",
            "push_lv_voltages": True,
            "push_feeder_loading": True,
            "push_der_outputs": False,
            "push_oe_limits": False,
            "push_flex_events": False,
            "push_interval_seconds": 10,
            "is_active": True,
        },
    ]

    now = utcnow()
    for ep in default_endpoints:
        existing = (
            await db.execute(
                select(SCADAEndpoint).where(
                    SCADAEndpoint.deployment_id == ep["deployment_id"],
                    SCADAEndpoint.name == ep["name"],
                )
            )
        ).scalars().first()

        if existing is not None:
            continue

        record = SCADAEndpoint(
            id=new_uuid(),
            created_at=now,
            updated_at=now,
            **ep,
        )
        db.add(record)

    await db.flush()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _count_snapshot_records(snapshot: dict) -> int:
    """Count the total number of data records in a snapshot dict."""
    total = 0
    grid = snapshot.get("grid", {})
    total += len(grid.get("cmzs", []))
    total += len(grid.get("feeders", []))
    total += len(grid.get("substations", []))
    lv = snapshot.get("lv_network", {})
    total += len(lv.get("feeders", []))
    total += len(lv.get("buses", []))
    total += len(snapshot.get("assets", []))
    total += len(snapshot.get("oe_limits", []))
    total += len(snapshot.get("active_flex_events", []))
    return total


def _build_auth_headers(endpoint: SCADAEndpoint) -> dict[str, str]:
    """Build HTTP request headers based on the endpoint's auth_type and auth_config."""
    headers: dict[str, str] = {"Content-Type": "application/json"}

    if endpoint.auth_type == "API_KEY" and endpoint.auth_config:
        try:
            cfg = json.loads(endpoint.auth_config)
            header_name = cfg.get("header", "X-API-Key")
            api_key_value = cfg.get("key", "")
            if api_key_value:
                headers[header_name] = api_key_value
        except (json.JSONDecodeError, KeyError):
            pass

    elif endpoint.auth_type == "BASIC" and endpoint.auth_config:
        try:
            import base64
            cfg = json.loads(endpoint.auth_config)
            username = cfg.get("username", "")
            password = cfg.get("password", "")
            if username:
                token = base64.b64encode(f"{username}:{password}".encode()).decode()
                headers["Authorization"] = f"Basic {token}"
        except (json.JSONDecodeError, KeyError):
            pass

    return headers


async def _get_scada_mode(db: AsyncSession, deployment_id: str) -> str:
    """
    Look up the SCADA IntegrationConfig mode for this deployment.

    Defaults to SIMULATION if no config exists.
    """
    try:
        from app.integrations.config_mgr.models import IntegrationConfig

        cfg = (
            await db.execute(
                select(IntegrationConfig).where(
                    IntegrationConfig.deployment_id == deployment_id,
                    IntegrationConfig.integration_type == "SCADA",
                    IntegrationConfig.is_active.is_(True),
                )
            )
        ).scalars().first()

        if cfg is not None:
            return cfg.mode
    except Exception:  # noqa: BLE001
        pass

    return "SIMULATION"
