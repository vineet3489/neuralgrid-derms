"""
SSEN IEC MarketDocument message format builder.

Implements the IEC CIM / SSEN-specific MarketDocument types used in the
Scottish and Southern Electricity Networks (SSEN) flexibility market:

  - OperatingEnvelope_MarketDocument   (Z01)
  - ReferenceEnergyCurveFlexOffer_MarketDocument
  - Acknowledgement_MarketDocument
  - Activation_MarketDocument
  - Performance_MarketDocument

All monetary/energy quantities in MW (MAW) to match the SSEN spreadsheet.
mRID format: "OE-{event_ref}-{cmz_slug}-{yyyymmddHHMM}"

Document type codes follow the IEC 62325-451-1 profile used by SSEN.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mrid_timestamp() -> str:
    """Compact UTC timestamp for mRID suffix: yyyymmddHHMM."""
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M")


def _kw_to_mw(kw: float) -> float:
    """Convert kW to MW, rounded to 6 decimal places."""
    return round(kw / 1000.0, 6)


def _slug_safe(text: str) -> str:
    """Make a string safe for use in an mRID (alphanumeric + hyphens)."""
    return "".join(c if c.isalnum() or c == "-" else "_" for c in text).upper()


# ---------------------------------------------------------------------------
# OperatingEnvelope_MarketDocument
# ---------------------------------------------------------------------------

def build_operating_envelope_doc(
    event: Any,          # FlexEvent ORM instance
    oe_messages: list,   # list of OEMessage ORM instances
    deployment_id: str,
    cmz_id: str,
) -> dict:
    """
    Build OperatingEnvelope_MarketDocument from a dispatched FlexEvent.

    Total envelope capacity = sum of all OE message export limits (in MW).
    mRID format: "OE-{event_ref}-{cmz_slug}-{yyyymmddHHMM}"
    process.processType = "Z01" (Operating Envelope)

    Returns the full JSON structure matching SSEN format.
    """
    cmz_slug = _slug_safe(cmz_id)
    ts = _mrid_timestamp()
    mrid = f"OE-{event.event_ref}-{cmz_slug}-{ts}"

    # Aggregate total envelope capacity from OE messages (kW → MW)
    total_export_kw = sum(
        (m.export_max_kw or 0.0) for m in oe_messages
    )
    total_import_kw = sum(
        (m.import_max_kw or 0.0) for m in oe_messages
    )
    total_capacity_mw = _kw_to_mw(total_export_kw)
    total_import_mw = _kw_to_mw(total_import_kw)

    start_time = event.start_time.strftime("%Y-%m-%dT%H:%M:%SZ") if event.start_time else ""
    end_time = event.end_time.strftime("%Y-%m-%dT%H:%M:%SZ") if event.end_time else ""

    # Build per-asset envelope series
    time_series: list[dict] = []
    for m in oe_messages:
        ts_entry: dict = {
            "mRID": f"TS-{m.id[:12]}",
            "businessType": "A53",           # Operating Envelope
            "measureUnit.name": "MAW",
            "registeredResource.mRID": m.asset_id,
            "period": {
                "timeInterval": {
                    "start": start_time,
                    "end": end_time,
                },
                "resolution": "PT30M",
                "Point": [
                    {
                        "position": 1,
                        "quantity": _kw_to_mw(m.export_max_kw or 0.0),
                    }
                ],
            },
            "powerEnvelope": {
                "maxQuantity": {
                    "quantity": _kw_to_mw(m.export_max_kw or 0.0),
                    "unit": "MAW",
                },
                "minQuantity": {
                    "quantity": -_kw_to_mw(m.import_max_kw or 0.0),
                    "unit": "MAW",
                },
            },
        }
        time_series.append(ts_entry)

    return {
        "OperatingEnvelope_MarketDocument": {
            "mRID": mrid,
            "revisionNumber": "1",
            "type": "A44",
            "process.processType": "Z01",
            "sender_MarketParticipant.mRID": "neuralgrid-derms",
            "sender_MarketParticipant.marketRole.type": "A49",
            "receiver_MarketParticipant.mRID": deployment_id,
            "receiver_MarketParticipant.marketRole.type": "A04",
            "createdDateTime": _now_iso(),
            "constraintZone.mRID": cmz_id,
            "period.timeInterval": {
                "start": start_time,
                "end": end_time,
            },
            "powerEnvelope": {
                "maxQuantity": {
                    "quantity": total_capacity_mw,
                    "unit": "MAW",
                },
                "minQuantity": {
                    "quantity": -total_import_mw,
                    "unit": "MAW",
                },
            },
            "TimeSeries": time_series,
            "_meta": {
                "event_ref": event.event_ref,
                "event_type": event.event_type,
                "event_status": event.status,
                "cmz_id": cmz_id,
                "deployment_id": deployment_id,
                "asset_count": len(oe_messages),
                "total_export_mw": total_capacity_mw,
                "total_import_mw": total_import_mw,
            },
        }
    }


# ---------------------------------------------------------------------------
# ReferenceEnergyCurveFlexOffer_MarketDocument
# ---------------------------------------------------------------------------

def build_flex_offer_doc(
    envelope_mrid: str,
    aggregator_ref: str,
    cmz_id: str,
    start_time: str,
    end_time: str,
    direction: str,   # "Increase" or "Decrease"
    capacity_mw: float,
) -> dict:
    """
    Build ReferenceEnergyCurveFlexOffer_MarketDocument.

    Maps to: constraintZone.mRID, registeredResource.mRID,
    period.timeInterval.start/end, flowDirection.direction,
    energyCurve.point.quantity
    """
    ts = _mrid_timestamp()
    mrid = f"FO-{envelope_mrid}-{ts}"

    # flowDirection: A01 = Increase (import / load increase), A02 = Decrease (export / curtailment)
    direction_code = "A01" if direction.upper() in ("INCREASE", "UP") else "A02"
    direction_label = "Increase" if direction_code == "A01" else "Decrease"

    return {
        "ReferenceEnergyCurveFlexOffer_MarketDocument": {
            "mRID": mrid,
            "revisionNumber": "1",
            "type": "A71",
            "process.processType": "A18",
            "sender_MarketParticipant.mRID": aggregator_ref,
            "sender_MarketParticipant.marketRole.type": "A08",
            "receiver_MarketParticipant.mRID": "neuralgrid-derms",
            "receiver_MarketParticipant.marketRole.type": "A49",
            "createdDateTime": _now_iso(),
            "constraintZone.mRID": cmz_id,
            "registeredResource.mRID": aggregator_ref,
            "flowDirection.direction": direction_label,
            "period.timeInterval": {
                "start": start_time,
                "end": end_time,
            },
            "measureUnit.name": "MAW",
            "TimeSeries": [
                {
                    "mRID": f"TS-{mrid[:16]}",
                    "businessType": "A96",  # Flex offer
                    "flowDirection.direction": direction_label,
                    "measureUnit.name": "MAW",
                    "period": {
                        "timeInterval": {
                            "start": start_time,
                            "end": end_time,
                        },
                        "resolution": "PT30M",
                        "Point": [
                            {
                                "position": 1,
                                "energyCurve": {
                                    "point": {
                                        "quantity": capacity_mw,
                                        "unit": "MAW",
                                    }
                                },
                                "quantity": capacity_mw,
                            }
                        ],
                    },
                    "registeredResource.mRID": aggregator_ref,
                    "constraintZone.mRID": cmz_id,
                    "relatedDocument.mRID": envelope_mrid,
                }
            ],
        }
    }


# ---------------------------------------------------------------------------
# Acknowledgement_MarketDocument
# ---------------------------------------------------------------------------

def build_ack_doc(received_mrid: str, sender_id: str = "neuralgrid-derms") -> dict:
    """
    Build Acknowledgement_MarketDocument.

    Maps: receivedDocument.mRID
    """
    ts = _mrid_timestamp()
    mrid = f"ACK-{received_mrid[:24]}-{ts}"

    return {
        "Acknowledgement_MarketDocument": {
            "mRID": mrid,
            "revisionNumber": "1",
            "type": "A17",
            "process.processType": "A01",
            "sender_MarketParticipant.mRID": sender_id,
            "sender_MarketParticipant.marketRole.type": "A49",
            "createdDateTime": _now_iso(),
            "receivedDocument.mRID": received_mrid,
            "receivedDocument.revisionNumber": "1",
            "Reason": [
                {
                    "code": "A01",  # Message received and accepted
                    "text": "Document accepted",
                }
            ],
        }
    }


# ---------------------------------------------------------------------------
# Activation_MarketDocument
# ---------------------------------------------------------------------------

def build_activation_doc(
    event_ref: str,
    requested_mw: float,
    cmz_id: str,
) -> dict:
    """
    Build Activation_MarketDocument.

    Maps: requestedQuantity.quantity
    """
    cmz_slug = _slug_safe(cmz_id)
    ts = _mrid_timestamp()
    mrid = f"ACT-{event_ref}-{cmz_slug}-{ts}"
    now = _now_iso()

    return {
        "Activation_MarketDocument": {
            "mRID": mrid,
            "revisionNumber": "1",
            "type": "A58",
            "process.processType": "A18",
            "sender_MarketParticipant.mRID": "neuralgrid-derms",
            "sender_MarketParticipant.marketRole.type": "A49",
            "createdDateTime": now,
            "constraintZone.mRID": cmz_id,
            "requestedQuantity": {
                "quantity": requested_mw,
                "unit": "MAW",
            },
            "TimeSeries": [
                {
                    "mRID": f"TS-{mrid[:16]}",
                    "businessType": "A97",   # Activation
                    "measureUnit.name": "MAW",
                    "period": {
                        "timeInterval": {
                            "start": now,
                            "end": now,
                        },
                        "resolution": "PT30M",
                        "Point": [
                            {
                                "position": 1,
                                "quantity": requested_mw,
                            }
                        ],
                    },
                    "constraintZone.mRID": cmz_id,
                    "relatedDocument.mRID": f"OE-{event_ref}-{cmz_slug}",
                }
            ],
        }
    }


# ---------------------------------------------------------------------------
# Performance_MarketDocument
# ---------------------------------------------------------------------------

def build_performance_doc(
    event_ref: str,
    delivered_mw: float,
    cmz_id: str,
) -> dict:
    """
    Build Performance_MarketDocument.

    Maps: actualDeliveredQuantity.quantity
    """
    cmz_slug = _slug_safe(cmz_id)
    ts = _mrid_timestamp()
    mrid = f"PERF-{event_ref}-{cmz_slug}-{ts}"
    now = _now_iso()

    return {
        "Performance_MarketDocument": {
            "mRID": mrid,
            "revisionNumber": "1",
            "type": "A59",
            "process.processType": "A18",
            "sender_MarketParticipant.mRID": "neuralgrid-derms",
            "sender_MarketParticipant.marketRole.type": "A49",
            "createdDateTime": now,
            "constraintZone.mRID": cmz_id,
            "actualDeliveredQuantity": {
                "quantity": delivered_mw,
                "unit": "MAW",
            },
            "TimeSeries": [
                {
                    "mRID": f"TS-{mrid[:16]}",
                    "businessType": "A98",   # Performance measurement
                    "measureUnit.name": "MAW",
                    "period": {
                        "timeInterval": {
                            "start": now,
                            "end": now,
                        },
                        "resolution": "PT30M",
                        "Point": [
                            {
                                "position": 1,
                                "quantity": delivered_mw,
                            }
                        ],
                    },
                    "constraintZone.mRID": cmz_id,
                    "relatedDocument.mRID": f"OE-{event_ref}-{cmz_slug}",
                }
            ],
        }
    }
