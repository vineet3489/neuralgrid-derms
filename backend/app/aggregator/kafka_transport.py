"""
Kafka transport for DER aggregator messages.

Topics (D4G IEC 62746-4 spec):
  dso_operating_envelope     — DERMS/DSO publishes OE to aggregators/SPGs
  flex-offers                — Aggregators/SPGs publish flex offers to DSO
  baseline_24h               — DERMS/DSO publishes 24-h baseline to SPGs
  historical_data            — DERMS/DSO publishes historical measurements to SPGs

Enabled only when KAFKA_BOOTSTRAP_SERVERS is set in config/environment.
Falls back silently to REST-only mode when Kafka is not configured.

All Kafka operations are wrapped in try/except so that aiokafka being absent
or the broker being unreachable never raises an exception that would break the
application.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional aiokafka import
# ---------------------------------------------------------------------------

try:
    from aiokafka import AIOKafkaProducer, AIOKafkaConsumer  # type: ignore
    _AIOKAFKA_AVAILABLE = True
except ImportError:
    _AIOKAFKA_AVAILABLE = False
    logger.debug("aiokafka not installed — Kafka transport disabled")

# ---------------------------------------------------------------------------
# Topic constants
# ---------------------------------------------------------------------------

# D4G IEC 62746-4 spec topic names
TOPIC_OE_DISPATCH   = "dso_operating_envelope"   # DSO → SPG: operating envelopes
TOPIC_FLEX_OFFERS   = "flex-offers"               # SPG → DSO: flex offer bids
TOPIC_BASELINE      = "baseline_24h"              # DSO → SPG: 24-h baseline
TOPIC_HISTORICAL    = "historical_data"            # DSO → SPG: historical measurements

# Legacy aliases kept for internal callers
TOPIC_FLEX_EVENTS   = TOPIC_FLEX_OFFERS
TOPIC_AGG_TELEMETRY = TOPIC_FLEX_OFFERS


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def kafka_enabled() -> bool:
    """Return True if KAFKA_BOOTSTRAP_SERVERS is configured and non-empty."""
    return bool(getattr(settings, "kafka_bootstrap_servers", "").strip())


def _make_message(deployment_id: str, key: str, payload: dict) -> tuple[bytes, bytes]:
    """Encode routing key and JSON payload as bytes."""
    msg_key = f"{deployment_id}:{key}".encode()
    msg_value = json.dumps(payload, default=str).encode()
    return msg_key, msg_value


async def _get_producer() -> "AIOKafkaProducer | None":  # type: ignore[name-defined]
    """Create a short-lived producer, or return None when Kafka is unavailable."""
    if not kafka_enabled() or not _AIOKAFKA_AVAILABLE:
        return None
    try:
        producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            security_protocol=getattr(settings, "kafka_security_protocol", "PLAINTEXT"),
            value_serializer=None,
            key_serializer=None,
        )
        await producer.start()
        return producer
    except Exception as exc:  # pragma: no cover
        logger.warning("Kafka producer start failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Publish helpers
# ---------------------------------------------------------------------------

async def _publish(topic: str, deployment_id: str, routing_key: str, message: dict) -> bool:
    """Internal: publish a message to a Kafka topic. Returns True on success."""
    if not kafka_enabled():
        logger.debug("Kafka disabled — skipping publish to %s", topic)
        return False
    if not _AIOKAFKA_AVAILABLE:
        logger.warning("aiokafka not installed — cannot publish to %s", topic)
        return False
    producer = await _get_producer()
    if producer is None:
        return False
    try:
        key_bytes, value_bytes = _make_message(deployment_id, routing_key, message)
        await producer.send_and_wait(topic, value=value_bytes, key=key_bytes)
        logger.debug("Published to %s key=%s:%s", topic, deployment_id, routing_key)
        return True
    except Exception as exc:
        logger.warning("Kafka publish to %s failed: %s", topic, exc)
        return False
    finally:
        try:
            await producer.stop()
        except Exception:
            pass


async def publish_operating_envelope(deployment_id: str, cmz_id: str, message: dict) -> bool:
    """
    Publish a D4G OperatingEnvelopeMessage to Kafka topic ``dso_operating_envelope``.

    Parameters
    ----------
    deployment_id : Platform deployment slug (routing prefix).
    cmz_id        : CMZ identifier (message key).
    message       : OperatingEnvelopeMessage dict from build_operating_envelope().
    """
    return await _publish(TOPIC_OE_DISPATCH, deployment_id, cmz_id, message)


# Legacy alias
publish_oe_dispatch = publish_operating_envelope


async def publish_baseline(deployment_id: str, cmz_id: str, message: dict) -> bool:
    """
    Publish a D4G BaselineNotificationMessage to Kafka topic ``baseline_24h``.
    """
    return await _publish(TOPIC_BASELINE, deployment_id, cmz_id, message)


async def publish_historical_data(deployment_id: str, cmz_id: str, message: dict) -> bool:
    """
    Publish a D4G HistoricalDataMessage to Kafka topic ``historical_data``.
    """
    return await _publish(TOPIC_HISTORICAL, deployment_id, cmz_id, message)


async def publish_flex_event(deployment_id: str, event_ref: str, message: dict) -> bool:
    """
    Publish a flex offer / activation to Kafka topic ``flex-offers``.
    (Legacy name kept for compatibility with existing callers.)
    """
    return await _publish(TOPIC_FLEX_OFFERS, deployment_id, event_ref, message)


# ---------------------------------------------------------------------------
# Background consumer
# ---------------------------------------------------------------------------

async def start_telemetry_consumer(
    db_factory: Callable[[], Any],
    deployment_id: str,
) -> None:
    """
    Background consumer: reads DERGroupStatus from derms.aggregator.telemetry.

    Parses each message using parse_der_group_status() and updates asset
    telemetry in the database.  Runs as an asyncio task.  No-ops if Kafka is
    not configured or aiokafka is not installed.

    Parameters
    ----------
    db_factory    : Zero-argument async context-manager factory that yields an
                    AsyncSession (e.g. AsyncSessionLocal from app.database).
    deployment_id : Platform deployment slug; used to filter messages.
    """
    if not kafka_enabled():
        logger.debug("Kafka disabled — telemetry consumer will not start")
        return
    if not _AIOKAFKA_AVAILABLE:
        logger.warning("aiokafka not installed — telemetry consumer will not start")
        return

    group_id: str = getattr(settings, "kafka_group_id", "neuralgrid-derms")
    consumer: "AIOKafkaConsumer | None" = None  # type: ignore[name-defined]

    try:
        consumer = AIOKafkaConsumer(
            TOPIC_FLEX_OFFERS,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            security_protocol=getattr(settings, "kafka_security_protocol", "PLAINTEXT"),
            group_id=group_id,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )
        await consumer.start()
        logger.info("Kafka flex-offers consumer started (deployment=%s, topic=%s)",
                    deployment_id, TOPIC_FLEX_OFFERS)

        async for msg in consumer:
            try:
                await _handle_telemetry_message(msg.value, db_factory, deployment_id)
            except Exception as exc:
                logger.warning("Error handling Kafka telemetry message: %s", exc)

    except Exception as exc:
        logger.warning("Kafka telemetry consumer error: %s", exc)
    finally:
        if consumer is not None:
            try:
                await consumer.stop()
            except Exception:
                pass


async def _handle_telemetry_message(
    payload: dict,
    db_factory: Callable[[], Any],
    deployment_id: str,
) -> None:
    """Process a single DERGroupStatus message from Kafka and persist telemetry."""
    from app.aggregator.cim.iec62746_4 import parse_der_group_status

    try:
        status = parse_der_group_status(payload)
    except ValueError as exc:
        logger.debug("Skipping unparseable telemetry message: %s", exc)
        return

    from datetime import datetime, timezone
    import uuid
    from sqlalchemy import select

    try:
        async with db_factory() as db:
            from app.assets.models import DERAsset, AssetTelemetry

            for asset_info in status.get("assets", []):
                asset_ref = asset_info.get("asset_ref")
                power_kw = asset_info.get("power_kw", 0.0)
                soc_pct = asset_info.get("soc_pct")
                if not asset_ref:
                    continue

                result = await db.execute(
                    select(DERAsset).where(
                        (DERAsset.asset_ref == asset_ref) | (DERAsset.id == asset_ref),
                        DERAsset.deployment_id == deployment_id,
                    )
                )
                asset = result.scalar_one_or_none()
                if not asset:
                    logger.debug("Kafka telemetry: asset_ref=%s not found", asset_ref)
                    continue

                now = datetime.now(timezone.utc)
                asset.current_kw = float(power_kw)
                asset.last_telemetry_at = now
                if soc_pct is not None:
                    asset.current_soc_pct = float(soc_pct)

                tel = AssetTelemetry(
                    id=str(uuid.uuid4()),
                    asset_id=asset.id,
                    deployment_id=deployment_id,
                    timestamp=now,
                    power_kw=float(power_kw),
                    soc_pct=float(soc_pct) if soc_pct is not None else None,
                    source="AGGREGATOR_REPORTED",
                )
                db.add(tel)

            await db.commit()
            logger.debug(
                "Kafka: updated telemetry for group=%s (%d assets)",
                status.get("group_id"),
                len(status.get("assets", [])),
            )
    except Exception as exc:
        logger.warning("Kafka telemetry DB update failed: %s", exc)
