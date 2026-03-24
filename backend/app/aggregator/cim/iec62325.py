"""
IEC 62325-301 Electricity Market message builders for flex market exchange.

Implements ReserveBidMarketDocument (A26) and ActivationDocument (A53) as
plain-dict representations of the CIM XML structure, suitable for JSON
transport over REST or Kafka.

All grid quantities are in MW (measureUnit.name: MAW) per SSEN IEC format
conventions. Timestamps are ISO-8601 UTC strings.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmz_slug(cmz_id: str) -> str:
    """Convert CMZ id to a slug safe for use in mRID strings."""
    return re.sub(r"[^A-Za-z0-9]", "", cmz_id).upper()[:12]


def _stamp_from_iso(iso: str) -> str:
    """Return yyyymmddHHMM from an ISO-8601 string; falls back to now."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y%m%d%H%M")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y%m%d%H%M")


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

def build_reserve_bid_market_document(
    event_ref: str,
    cmz_id: str,
    aggregator_ref: str,
    deployment_id: str,
    intervals: list[dict],
) -> dict:
    """
    Build a ReserveBidMarketDocument (IEC 62325-301 type A26).

    Used by aggregators to submit flex bids to the DNO/market.

    Parameters
    ----------
    event_ref       : Platform event reference, e.g. "EVT-042".
    cmz_id          : Constraint Managed Zone identifier.
    aggregator_ref  : Aggregator identifier string.
    deployment_id   : Platform deployment slug.
    intervals       : List of dicts, each containing:
                        slot_start       (ISO-8601 UTC str)
                        slot_end         (ISO-8601 UTC str)
                        quantity_mw      (float, MW)
                        price_per_mwh    (float)
                        flow_direction   ("Increase" | "Decrease")

    Returns
    -------
    dict — ReserveBidMarketDocument structure.
    mRID format: BID-{event_ref}-{cmz_slug}-{yyyymmddHHMM}
    All quantities in MW (measureUnit.name: MAW).
    flowDirection: Increase | Decrease
    process.processType: Z02 (Reserve Bid)
    """
    now = _utcnow_iso()
    slug = _cmz_slug(cmz_id)
    first_start = intervals[0]["slot_start"] if intervals else now
    stamp = _stamp_from_iso(first_start)
    mrid = f"BID-{event_ref}-{slug}-{stamp}"

    time_series = []
    for i, iv in enumerate(intervals):
        flow = iv.get("flow_direction", "Decrease")
        ts_entry = {
            "mRID": f"{mrid}-TS{i + 1:03d}",
            "businessType": "A95",  # IEC 62325 — Flexible resource up-regulation
            "flowDirection.name": flow,
            "measureUnit.name": "MAW",
            "registeredResource.mRID": aggregator_ref,
            "Period": {
                "timeInterval": {
                    "start": iv.get("slot_start", now),
                    "end": iv.get("slot_end", now),
                },
                "Point": [
                    {
                        "position": 1,
                        "quantity": iv.get("quantity_mw", 0.0),
                        "price.amount": iv.get("price_per_mwh", 0.0),
                    }
                ],
            },
        }
        time_series.append(ts_entry)

    return {
        "ReserveBidMarketDocument": {
            "mRID": mrid,
            "revisionNumber": "1",
            "type": "A26",
            "process.processType": "Z02",
            "sender_MarketParticipant.mRID": aggregator_ref,
            "sender_MarketParticipant.marketRole.type": "A46",  # Balance Responsible Party
            "receiver_MarketParticipant.mRID": f"neuralgrid-{deployment_id}",
            "receiver_MarketParticipant.marketRole.type": "A04",  # DSO
            "createdDateTime": now,
            "subject_MarketParticipant.mRID": aggregator_ref,
            "subject_MarketParticipant.marketRole.type": "A46",
            "reserveBid_Period.timeInterval": {
                "start": intervals[0]["slot_start"] if intervals else now,
                "end": intervals[-1]["slot_end"] if intervals else now,
            },
            "domain.mRID": cmz_id,
            "TimeSeries": time_series,
        }
    }


def build_activation_document(
    bid_mrid: str,
    event_ref: str,
    requested_mw: float,
    start_time: str,
    deployment_id: str,
) -> dict:
    """
    Build an ActivationDocument (IEC 62325 type A53).

    Sent from DNO/market to aggregator to trigger dispatch.

    Parameters
    ----------
    bid_mrid      : mRID of the ReserveBidMarketDocument being activated.
    event_ref     : Platform event reference.
    requested_mw  : Quantity to activate in MW.
    start_time    : ISO-8601 UTC activation start time.
    deployment_id : Platform deployment slug.

    Returns
    -------
    dict — ActivationDocument structure.
    """
    now = _utcnow_iso()
    stamp = _stamp_from_iso(start_time)
    mrid = f"ACT-{event_ref}-{stamp}"

    return {
        "ActivationDocument": {
            "mRID": mrid,
            "revisionNumber": "1",
            "type": "A53",
            "process.processType": "A56",  # Balancing — activation
            "sender_MarketParticipant.mRID": f"neuralgrid-{deployment_id}",
            "sender_MarketParticipant.marketRole.type": "A04",  # DSO
            "receiver_MarketParticipant.mRID": bid_mrid.split("-")[1] if "-" in bid_mrid else bid_mrid,
            "receiver_MarketParticipant.marketRole.type": "A46",
            "createdDateTime": now,
            "reserveBid_mRID": bid_mrid,
            "TimeSeries": [
                {
                    "mRID": f"{mrid}-TS001",
                    "businessType": "C24",  # Activation
                    "measureUnit.name": "MAW",
                    "flowDirection.name": "Decrease",
                    "Period": {
                        "timeInterval": {
                            "start": start_time,
                            "end": start_time,  # caller should override end if known
                        },
                        "Point": [
                            {
                                "position": 1,
                                "quantity": requested_mw,
                            }
                        ],
                    },
                }
            ],
        }
    }


def parse_reserve_bid(payload: dict) -> dict:
    """
    Parse an inbound ReserveBidMarketDocument from an aggregator.

    Parameters
    ----------
    payload : Raw dict as received over REST or Kafka.

    Returns
    -------
    Normalised dict with keys:
        mRID            (str)
        cmz_id          (str)
        aggregator_ref  (str)
        process_type    (str)
        intervals       (list of dicts with slot_start, slot_end,
                         quantity_mw, price_per_mwh, flow_direction)

    Raises
    ------
    ValueError  If required top-level fields are missing.
    """
    doc = payload.get("ReserveBidMarketDocument", payload)

    mrid = doc.get("mRID")
    if not mrid:
        raise ValueError("ReserveBidMarketDocument.mRID is required")

    aggregator_ref = doc.get("sender_MarketParticipant.mRID")
    if not aggregator_ref:
        raise ValueError("ReserveBidMarketDocument.sender_MarketParticipant.mRID is required")

    cmz_id = doc.get("domain.mRID")
    if not cmz_id:
        raise ValueError("ReserveBidMarketDocument.domain.mRID (CMZ) is required")

    process_type = doc.get("process.processType", "Z02")

    intervals: list[dict] = []
    for ts in doc.get("TimeSeries", []):
        period = ts.get("Period", {})
        time_interval = period.get("timeInterval", {})
        flow = ts.get("flowDirection.name", "Decrease")
        for point in period.get("Point", []):
            intervals.append(
                {
                    "slot_start": time_interval.get("start", ""),
                    "slot_end": time_interval.get("end", ""),
                    "quantity_mw": float(point.get("quantity", 0.0)),
                    "price_per_mwh": float(point.get("price.amount", 0.0)),
                    "flow_direction": flow,
                }
            )

    return {
        "mRID": mrid,
        "cmz_id": cmz_id,
        "aggregator_ref": aggregator_ref,
        "process_type": process_type,
        "intervals": intervals,
    }
