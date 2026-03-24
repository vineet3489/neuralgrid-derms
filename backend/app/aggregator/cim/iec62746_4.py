"""
IEC 62746-4 DER-DERMS direct interface message builders.

IEC 62746-4 defines the interface between a DERMS and individual DER assets
(or DER groups managed by an aggregator).  This module provides builder
functions for DERGroupDispatch and DERCapabilityInfo documents, and parsers
for DERGroupStatus and DERMonitoringInfo telemetry payloads received from
aggregators.

Asset-level quantities are in kW (consistent with the rest of the platform).
Grid/fleet summaries use kW as well; callers convert to MW when embedding in
IEC 62325 documents.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_mrid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_der_group_dispatch(
    group_id: str,
    dispatch_type: str,
    target_power_kw: float,
    start_time: str,
    end_time: str,
    der_targets: list[dict],
    deployment_id: str,
) -> dict:
    """
    DERGroupDispatch — DERMS sends a fleet dispatch command to an aggregator.

    Uses the IEC 62746-4 DERGroupDispatch structure.

    Parameters
    ----------
    group_id        : Aggregator-defined group identifier.
    dispatch_type   : One of CURTAIL | INCREASE | CHARGE | DISCHARGE.
    target_power_kw : Aggregate fleet target in kW.
    start_time      : ISO-8601 UTC dispatch window start.
    end_time        : ISO-8601 UTC dispatch window end.
    der_targets     : List of per-asset dicts:
                        { asset_ref (str), allocated_kw (float) }
    deployment_id   : Platform deployment slug.

    Returns
    -------
    dict — DERGroupDispatch message.
    """
    mrid = _new_mrid("DGD")
    now = _utcnow_iso()

    asset_dispatches = [
        {
            "EndDevice": {"mRID": t["asset_ref"]},
            "DERControl": {
                "mRID": f"{mrid}-{t['asset_ref']}",
                "DERControlBase": {
                    "dispatchType": dispatch_type,
                    "opModFixedW": {
                        "value": t.get("allocated_kw", 0.0),
                        "unit": "kW",
                    },
                },
            },
        }
        for t in der_targets
    ]

    return {
        "DERGroupDispatch": {
            "mRID": mrid,
            "createdDateTime": now,
            "sender.mRID": f"neuralgrid-{deployment_id}",
            "groupID": group_id,
            "dispatchType": dispatch_type,
            "targetPower": {
                "value": target_power_kw,
                "unit": "kW",
            },
            "dispatchInterval": {
                "start": start_time,
                "end": end_time,
            },
            "DERDispatch": asset_dispatches,
        }
    }


def build_der_capability_info(
    group_id: str,
    aggregator_ref: str,
    assets: list[dict],
    deployment_id: str,
) -> dict:
    """
    DERCapabilityInfo — aggregator declares fleet capabilities to the DERMS.

    Parameters
    ----------
    group_id        : Aggregator-defined group identifier.
    aggregator_ref  : Aggregator identifier string.
    assets          : List of per-asset dicts:
                        { asset_ref (str), type (str),
                          rated_kw (float), rated_kva (float),
                          flex_eligible (bool) }
    deployment_id   : Platform deployment slug.

    Returns
    -------
    dict — DERCapabilityInfo message.
    """
    mrid = _new_mrid("DCI")
    now = _utcnow_iso()

    asset_caps = []
    total_rated_kw = 0.0
    flex_count = 0
    for a in assets:
        rated_kw = float(a.get("rated_kw", 0.0))
        total_rated_kw += rated_kw
        if a.get("flex_eligible", False):
            flex_count += 1
        asset_caps.append(
            {
                "EndDevice": {"mRID": a["asset_ref"]},
                "DERCapability": {
                    "type": a.get("type", "UNKNOWN"),
                    "ratedS": {
                        "value": float(a.get("rated_kva", 0.0)),
                        "unit": "kVA",
                    },
                    "ratedW": {
                        "value": rated_kw,
                        "unit": "kW",
                    },
                    "flexEligible": a.get("flex_eligible", False),
                },
            }
        )

    return {
        "DERCapabilityInfo": {
            "mRID": mrid,
            "createdDateTime": now,
            "sender.mRID": aggregator_ref,
            "receiver.mRID": f"neuralgrid-{deployment_id}",
            "groupID": group_id,
            "aggregatorRef": aggregator_ref,
            "summary": {
                "totalAssets": len(assets),
                "flexEligibleAssets": flex_count,
                "totalRatedW": {
                    "value": total_rated_kw,
                    "unit": "kW",
                },
            },
            "DERCapabilities": asset_caps,
        }
    }


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_der_group_status(payload: dict) -> dict:
    """
    Parse inbound DERGroupStatus from an aggregator.

    Parameters
    ----------
    payload : Raw dict as received over REST or Kafka.

    Returns
    -------
    dict with keys:
        group_id     (str)
        report_time  (str, ISO-8601)
        assets       (list of dicts: asset_ref, power_kw, soc_pct, state)

    Raises
    ------
    ValueError  If required fields are missing.
    """
    doc = payload.get("DERGroupStatus", payload)

    group_id = doc.get("groupID") or doc.get("group_id")
    if not group_id:
        raise ValueError("DERGroupStatus.groupID is required")

    report_time = doc.get("reportDateTime") or doc.get("report_time") or _utcnow_iso()

    assets: list[dict] = []
    for entry in doc.get("DERStatus", []):
        end_device = entry.get("EndDevice", {})
        asset_ref = (
            end_device.get("mRID")
            or entry.get("asset_ref")
            or entry.get("endDevice.mRID")
        )
        der_status = entry.get("DERStatus", entry)  # may be nested or flat
        # Handle both nested and flat structures
        if isinstance(der_status, dict) and "operationalMode" in der_status:
            power_kw = float(der_status.get("operationalMode", {}).get("activePower", {}).get("value", 0.0))
            soc_pct = float(der_status.get("storedEnergy", {}).get("value", 0.0)) if der_status.get("storedEnergy") else None
            state = der_status.get("opState", "UNKNOWN")
        else:
            power_kw = float(entry.get("power_kw", 0.0))
            soc_pct = entry.get("soc_pct")
            if soc_pct is not None:
                soc_pct = float(soc_pct)
            state = entry.get("state", "UNKNOWN")

        assets.append(
            {
                "asset_ref": asset_ref,
                "power_kw": power_kw,
                "soc_pct": soc_pct,
                "state": state,
            }
        )

    return {
        "group_id": group_id,
        "report_time": report_time,
        "assets": assets,
    }


def parse_der_monitoring_info(payload: dict) -> dict:
    """
    Parse inbound DERMonitoringInfo telemetry from an aggregator.

    Parameters
    ----------
    payload : Raw dict as received over REST or Kafka.

    Returns
    -------
    dict with keys:
        group_id     (str)
        report_time  (str, ISO-8601)
        readings     (list of dicts: asset_ref, power_kw, voltage_v, current_a)

    Raises
    ------
    ValueError  If required fields are missing.
    """
    doc = payload.get("DERMonitoringInfo", payload)

    group_id = doc.get("groupID") or doc.get("group_id")
    if not group_id:
        raise ValueError("DERMonitoringInfo.groupID is required")

    report_time = doc.get("reportDateTime") or doc.get("report_time") or _utcnow_iso()

    readings: list[dict] = []
    for entry in doc.get("DERReading", []):
        end_device = entry.get("EndDevice", {})
        asset_ref = (
            end_device.get("mRID")
            or entry.get("asset_ref")
            or entry.get("endDevice.mRID")
        )

        # Support both nested CIM and flat convenience structures
        def _val(field: str, nested_path: list[str] | None = None) -> float | None:
            if field in entry:
                v = entry[field]
                return float(v) if v is not None else None
            if nested_path:
                obj = entry
                for key in nested_path:
                    if not isinstance(obj, dict):
                        return None
                    obj = obj.get(key)
                return float(obj) if obj is not None else None
            return None

        power_kw = _val("power_kw") or _val("activePower", ["Reading", "activePower", "value"]) or 0.0
        voltage_v = _val("voltage_v") or _val("voltage", ["Reading", "voltage", "value"])
        current_a = _val("current_a") or _val("current", ["Reading", "current", "value"])

        readings.append(
            {
                "asset_ref": asset_ref,
                "power_kw": float(power_kw),
                "voltage_v": voltage_v,
                "current_a": current_a,
            }
        )

    return {
        "group_id": group_id,
        "report_time": report_time,
        "readings": readings,
    }
