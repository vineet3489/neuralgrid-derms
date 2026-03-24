"""
IEC 62746-4 / Digital4Grids market document builders and parsers.

Implements the Digital4Grids D4G messaging profile for IEC 62746-4 FCA
(Flexibility Contracting and Activation) exchange between DSO/DERMS and
Service Providing Groups (SPGs / aggregators).

Four document types (all use ReferenceEnergyCurve*_MarketDocument structure):
  • OperatingEnvelope   — DSO → SPG: desired power at grid node (CMZ)
  • FlexOffer           — SPG → DSO: volume of flexibility available
  • BaselineNotification— DSO → SPG: baseline 24 h ahead
  • HistoricalData      — DSO → SPG: historical measurement data

References:
  AsyncAPI spec : d4g-iec62746_4_messages-_asyncapi.yaml  (v1.0.0)
  OpenAPI spec  : d4g-iec62746_4_messages-swagger.yml      (v2.0.0)

Kafka topics (as per D4G spec):
  dso_operating_envelope  — DSO publishes OE to aggregators
  flex-offers             — Aggregators publish flex offers to DSO
  baseline_24h            — DSO publishes 24-h baseline
  historical_data         — DSO publishes historical measurements

Units: all power quantities in MAW (megawatt) per spec.
Internal platform values in kW are divided by 1000 before serialisation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# EIC coding scheme (ENTSO-E)
CODING_EIC = "A01"

# Default DSO / DERMS market role (Z01 = DSO in D4G context)
ROLE_DSO = "Z01"
# Default SPG / aggregator market role
ROLE_SPG = "Z02"

# Default process type — A01 Day ahead
PROCESS_DAY_AHEAD = "A01"

# Flow directions
FLOW_UP = "A01"    # generation increase / export
FLOW_DOWN = "A02"  # generation decrease / curtailment / import


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_mrid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _party(eic_value: str, role: str) -> dict:
    """Build a MarketParticipant block."""
    return {
        "MarketParticipant.mRID": {
            "value": eic_value[:16],   # spec: maxLength 16
            "codingScheme": CODING_EIC,
        },
        "MarketParticipant.MarketRole": {"type": role},
    }


def _resource_id(resource_ref: str) -> dict:
    """Build a RegisteredResource block."""
    return {
        "RegisteredResource.mRID": {
            "value": resource_ref[:60],  # spec: maxLength 60
            "codingScheme": CODING_EIC,
        }
    }


def _message_header(message_type: str, source: str = "NeuralGrid-DERMS",
                    correlation_id: str | None = None) -> dict:
    """Build a MessageDocumentHeader block (required wrapper in every message)."""
    return {
        "messageId": str(uuid.uuid4()),
        "messageType": message_type,
        "timestamp": _utcnow_iso(),
        "version": "1.0",
        "source": source,
        "correlationId": correlation_id,
    }


def _kw_to_maw(kw: float) -> float:
    """Convert kW to MW (spec unit: MAW)."""
    return round(kw / 1000.0, 6)


def _quality_code(slot_start: str) -> str:
    """
    IEC 62746-4 quality code based on temporal distance from now.

    A04 — Measured  (live telemetry,    ≤ 1 h ahead  — near-real-time actuals)
    A06 — Calculated (DistFlow result,  1 – 8 h ahead — deterministic power flow)
    A03 — Estimated  (forecast-based,   > 8 h ahead  — probabilistic)
    """
    try:
        # Accept both "Z" suffix and "+00:00" aware strings
        slot_iso = slot_start.replace("Z", "+00:00") if slot_start.endswith("Z") else slot_start
        slot_dt = datetime.fromisoformat(slot_iso)
        if slot_dt.tzinfo is None:
            slot_dt = slot_dt.replace(tzinfo=timezone.utc)
        hours_ahead = (slot_dt - datetime.now(timezone.utc)).total_seconds() / 3600.0
    except Exception:
        return "A06"   # fallback: calculated

    if hours_ahead <= 1.0:
        return "A04"   # Measured — within live telemetry horizon
    if hours_ahead <= 8.0:
        return "A06"   # Calculated — DistFlow result
    return "A03"        # Estimated — forecast-based


# ---------------------------------------------------------------------------
# Operating Envelope (DSO → SPG)
# Published on Kafka topic: dso_operating_envelope
# ---------------------------------------------------------------------------

def build_operating_envelope(
    cmz_id: str,
    slots: list[dict],
    dso_eic: str,
    spg_eic: str,
    deployment_id: str,
    correlation_id: str | None = None,
) -> dict:
    """
    Build a D4G OperatingEnvelopeMessage (DSO → SPG).

    Published on Kafka topic ``dso_operating_envelope``.

    Parameters
    ----------
    cmz_id        : Constraint Management Zone identifier (RegisteredResource.mRID).
    slots         : List of 30-min slots:
                      { slot_start (ISO str), slot_end (ISO str),
                        export_max_kw (float), import_max_kw (float) }
    dso_eic       : EIC code of the DSO / DERMS (sender).
    spg_eic       : EIC code of the SPG / aggregator (receiver).
    deployment_id : Platform deployment slug (used in mRID).
    correlation_id: Optional correlation ID for request-response tracing.

    Returns
    -------
    dict — OperatingEnvelopeMessage (MessageDocumentHeader +
           ReferenceEnergyCurveOperatingEnvelope_MarketDocument).
    """
    mrid = _new_mrid(f"OE-{deployment_id.upper()}")
    now = _utcnow_iso()

    if not slots:
        raise ValueError("At least one time slot is required")

    period_start = slots[0]["slot_start"]
    period_end = slots[-1]["slot_end"]

    # Export OE series (UP direction — generation export limit)
    export_points = [
        {
            "position": i + 1,
            "Max_Quantity": {
                "quantity": _kw_to_maw(s.get("export_max_kw", 0.0)),
                # Quality per slot: A04 measured / A06 calculated / A03 estimated
                "quality": _quality_code(s["slot_start"]),
            },
        }
        for i, s in enumerate(slots)
    ]

    # Import OE series (DOWN direction — import limit)
    import_points = [
        {
            "position": i + 1,
            "Max_Quantity": {
                "quantity": _kw_to_maw(s.get("import_max_kw", 0.0)),
                "quality": _quality_code(s["slot_start"]),
            },
        }
        for i, s in enumerate(slots)
    ]

    def _ts(direction: str, points: list[dict]) -> dict:
        return {
            "curveType": "A01",
            "RegisteredResource": _resource_id(cmz_id),
            "FlowDirection": {"direction": direction},
            "ResourceTimeSeries": {"value1ScheduleType": "generation"},
            "Series": [
                {
                    "Measurement_Unit": {"name": "MAW"},
                    "Period": [
                        {
                            "resolution": "PT30M",
                            "timeInterval": {
                                "start": period_start,
                                "end": period_end,
                            },
                            "Point": points,
                        }
                    ],
                }
            ],
        }

    document = {
        "mRID": mrid,
        "revisionNumber": "1",
        "type": "A26",  # Operating envelope document type
        "createdDateTime": now,
        "Sender_MarketParticipant": _party(dso_eic, ROLE_DSO),
        "Receiver_MarketParticipant": _party(spg_eic, ROLE_SPG),
        "Process": {"processType": PROCESS_DAY_AHEAD},
        "Period": {"timeInterval": {"start": period_start, "end": period_end}},
        "Series": [
            _ts(FLOW_UP, export_points),
            _ts(FLOW_DOWN, import_points),
        ],
    }

    return {
        "MessageDocumentHeader": _message_header("OperatingEnvelope",
                                                  correlation_id=correlation_id),
        "ReferenceEnergyCurveOperatingEnvelope_MarketDocument": document,
    }


# ---------------------------------------------------------------------------
# Flex Offer (SPG → DSO)
# Received on Kafka topic: flex-offers  |  REST: POST /flex-offer
# ---------------------------------------------------------------------------

def build_flex_offer(
    cmz_id: str,
    slots: list[dict],
    spg_eic: str,
    dso_eic: str,
    deployment_id: str,
    correlation_id: str | None = None,
) -> dict:
    """
    Build a D4G FlexOfferMessage (SPG → DSO).

    Sent on Kafka topic ``flex-offers`` or REST ``POST /api/v1/aggregator/flex-offer``.

    Parameters
    ----------
    cmz_id        : CMZ / grid node identifier.
    slots         : List of slots:
                      { slot_start, slot_end, flex_up_kw (float), flex_down_kw (float) }
    spg_eic       : EIC code of the SPG / aggregator (sender).
    dso_eic       : EIC code of the DSO / DERMS (receiver).
    deployment_id : Platform deployment slug.
    correlation_id: Optional correlation ID.
    """
    mrid = _new_mrid(f"FO-{deployment_id.upper()}")
    now = _utcnow_iso()

    if not slots:
        raise ValueError("At least one time slot is required")

    period_start = slots[0]["slot_start"]
    period_end = slots[-1]["slot_end"]

    up_points = [
        {
            "position": i + 1,
            "Quantity": {
                "quantity": _kw_to_maw(s.get("flex_up_kw", 0.0)),
                "quality": "A04",  # As provided
            },
        }
        for i, s in enumerate(slots)
    ]

    down_points = [
        {
            "position": i + 1,
            "Quantity": {
                "quantity": _kw_to_maw(s.get("flex_down_kw", 0.0)),
                "quality": "A04",
            },
        }
        for i, s in enumerate(slots)
    ]

    def _ts(direction: str, points: list[dict]) -> dict:
        return {
            "curveType": "A01",
            "RegisteredResource": _resource_id(cmz_id),
            "FlowDirection": {"direction": direction},
            "ResourceTimeSeries": {"value1ScheduleType": "generationReduction" if direction == FLOW_DOWN else "generationIncrease"},
            "Series": [
                {
                    "Measurement_Unit": {"name": "MAW"},
                    "Period": [
                        {
                            "resolution": "PT30M",
                            "timeInterval": {"start": period_start, "end": period_end},
                            "Point": points,
                        }
                    ],
                }
            ],
        }

    document = {
        "mRID": mrid,
        "revisionNumber": "1",
        "type": "A62",  # Registration / flex offer
        "createdDateTime": now,
        "Sender_MarketParticipant": _party(spg_eic, ROLE_SPG),
        "Receiver_MarketParticipant": _party(dso_eic, ROLE_DSO),
        "Process": {"processType": PROCESS_DAY_AHEAD},
        "Period": {"timeInterval": {"start": period_start, "end": period_end}},
        "Series": [_ts(FLOW_UP, up_points), _ts(FLOW_DOWN, down_points)],
    }

    return {
        "MessageDocumentHeader": _message_header("FlexOffer", source=f"SPG-{spg_eic}",
                                                  correlation_id=correlation_id),
        "ReferenceEnergyCurveFlexOffer_MarketDocument": document,
    }


# ---------------------------------------------------------------------------
# Baseline Notification (DSO → SPG)
# Published on Kafka topic: baseline_24h
# ---------------------------------------------------------------------------

def build_baseline_notification(
    cmz_id: str,
    slots: list[dict],
    dso_eic: str,
    spg_eic: str,
    deployment_id: str,
    correlation_id: str | None = None,
) -> dict:
    """
    Build a D4G BaselineNotificationMessage (DSO → SPG).

    Published on Kafka topic ``baseline_24h``.

    Parameters
    ----------
    slots : List of slots:
              { slot_start, slot_end, baseline_kw (float) }
    """
    mrid = _new_mrid(f"BL-{deployment_id.upper()}")
    now = _utcnow_iso()

    if not slots:
        raise ValueError("At least one time slot is required")

    period_start = slots[0]["slot_start"]
    period_end = slots[-1]["slot_end"]

    points = [
        {
            "position": i + 1,
            "Baseline_Quantity": {
                "quantity": _kw_to_maw(s.get("baseline_kw", 0.0)),
                "quality": "A06",
            },
        }
        for i, s in enumerate(slots)
    ]

    document = {
        "mRID": mrid,
        "revisionNumber": "1",
        "type": "A01",
        "createdDateTime": now,
        "Sender_MarketParticipant": _party(dso_eic, ROLE_DSO),
        "Receiver_MarketParticipant": _party(spg_eic, ROLE_SPG),
        "Process": {"processType": PROCESS_DAY_AHEAD},
        "Period": {"timeInterval": {"start": period_start, "end": period_end}},
        "Series": [
            {
                "curveType": "A01",
                "RegisteredResource": _resource_id(cmz_id),
                "FlowDirection": {"direction": FLOW_UP},
                "ResourceTimeSeries": {"value1ScheduleType": "generation"},
                "Series": [
                    {
                        "Measurement_Unit": {"name": "MAW"},
                        "Period": [
                            {
                                "resolution": "PT30M",
                                "timeInterval": {"start": period_start, "end": period_end},
                                "Point": points,
                            }
                        ],
                    }
                ],
            }
        ],
    }

    return {
        "MessageDocumentHeader": _message_header("BaselineNotification",
                                                  correlation_id=correlation_id),
        "ReferenceEnergyCurveBaselineNotification_MarketDocument": document,
    }


# ---------------------------------------------------------------------------
# Historical Data (DSO → SPG)
# Published on Kafka topic: historical_data
# ---------------------------------------------------------------------------

def build_historical_data(
    cmz_id: str,
    slots: list[dict],
    dso_eic: str,
    spg_eic: str,
    deployment_id: str,
    correlation_id: str | None = None,
) -> dict:
    """
    Build a D4G HistoricalDataMessage (DSO → SPG).

    Published on Kafka topic ``historical_data``.

    Parameters
    ----------
    slots : List of slots:
              { slot_start, slot_end, actual_kw (float) }
    """
    mrid = _new_mrid(f"HD-{deployment_id.upper()}")
    now = _utcnow_iso()

    if not slots:
        raise ValueError("At least one time slot is required")

    period_start = slots[0]["slot_start"]
    period_end = slots[-1]["slot_end"]

    points = [
        {
            "position": i + 1,
            "Historical_Quantity": {
                "quantity": _kw_to_maw(s.get("actual_kw", 0.0)),
                "quality": "A04",  # As provided
            },
        }
        for i, s in enumerate(slots)
    ]

    document = {
        "mRID": mrid,
        "revisionNumber": "1",
        "type": "A16",  # Realised
        "createdDateTime": now,
        "Sender_MarketParticipant": _party(dso_eic, ROLE_DSO),
        "Receiver_MarketParticipant": _party(spg_eic, ROLE_SPG),
        "Process": {"processType": "A16"},  # Realised
        "Period": {"timeInterval": {"start": period_start, "end": period_end}},
        "Series": [
            {
                "curveType": "A01",
                "RegisteredResource": _resource_id(cmz_id),
                "FlowDirection": {"direction": FLOW_UP},
                "ResourceTimeSeries": {"value1ScheduleType": "generation"},
                "Series": [
                    {
                        "Measurement_Unit": {"name": "MAW"},
                        "Period": [
                            {
                                "resolution": "PT30M",
                                "timeInterval": {"start": period_start, "end": period_end},
                                "Point": points,
                            }
                        ],
                    }
                ],
            }
        ],
    }

    return {
        "MessageDocumentHeader": _message_header("HistoricalData",
                                                  correlation_id=correlation_id),
        "ReferenceEnergyCurveHistoricalData_MarketDocument": document,
    }


# ---------------------------------------------------------------------------
# Inbound parsers — receive flex offers and market documents from aggregators
# ---------------------------------------------------------------------------

def parse_flex_offer(payload: dict) -> dict:
    """
    Parse an inbound D4G FlexOfferMessage from an aggregator/SPG.

    Accepts both the full wrapper format (MessageDocumentHeader + document)
    and the bare document wrapper (ReferenceEnergyCurveFlexOffer_MarketDocument).

    Returns
    -------
    dict with keys:
        mrid         (str)
        cmz_id       (str)
        spg_eic      (str)
        created      (str, ISO-8601)
        slots        (list of dicts: position, slot_start, slot_end, flex_up_maw, flex_down_maw)
        correlation_id (str | None)
    """
    header = payload.get("MessageDocumentHeader", {})
    correlation_id = header.get("correlationId")

    doc_key = "ReferenceEnergyCurveFlexOffer_MarketDocument"
    doc = payload.get(doc_key) or payload

    mrid = doc.get("mRID", "")
    created = doc.get("createdDateTime", _utcnow_iso())

    sender = doc.get("Sender_MarketParticipant", {})
    spg_eic = (sender.get("MarketParticipant.mRID") or {}).get("value", "")

    slots: list[dict] = []
    for ts in doc.get("Series", []):
        direction = (ts.get("FlowDirection") or {}).get("direction", FLOW_UP)
        cmz_id = ((ts.get("RegisteredResource") or {}).get("RegisteredResource.mRID") or {}).get("value", "")

        for series in ts.get("Series", []):
            for period in series.get("Period", []):
                t_interval = period.get("timeInterval", {})
                p_start = t_interval.get("start", "")
                p_end = t_interval.get("end", "")
                for pt in period.get("Point", []):
                    qty = (pt.get("Quantity") or {}).get("quantity", 0.0)
                    slot = {
                        "position": pt.get("position"),
                        "slot_start": p_start,
                        "slot_end": p_end,
                        "direction": direction,
                        "flex_maw": float(qty),
                    }
                    slots.append(slot)

    return {
        "mrid": mrid,
        "cmz_id": cmz_id,
        "spg_eic": spg_eic,
        "created": created,
        "slots": slots,
        "correlation_id": correlation_id,
    }


def parse_market_document(payload: dict) -> tuple[str, dict]:
    """
    Auto-detect and parse any D4G market document.

    Returns
    -------
    (document_type, parsed_dict)  where document_type is one of:
        'OperatingEnvelope' | 'FlexOffer' | 'BaselineNotification' | 'HistoricalData'
    """
    header = payload.get("MessageDocumentHeader", {})
    msg_type = header.get("messageType", "")

    if "ReferenceEnergyCurveFlexOffer_MarketDocument" in payload or msg_type == "FlexOffer":
        return "FlexOffer", parse_flex_offer(payload)

    # Other types: return raw doc with type tag
    for key in (
        "ReferenceEnergyCurveOperatingEnvelope_MarketDocument",
        "ReferenceEnergyCurveBaselineNotification_MarketDocument",
        "ReferenceEnergyCurveHistoricalData_MarketDocument",
    ):
        if key in payload:
            label = key.replace("ReferenceEnergyCurve", "").replace("_MarketDocument", "")
            return label, {"raw": payload[key], "header": header}

    return msg_type or "Unknown", {"raw": payload, "header": header}
