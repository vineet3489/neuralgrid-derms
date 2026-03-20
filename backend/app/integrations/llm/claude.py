"""
Claude API integration for AI-powered grid operations assistance.

claude-haiku-4-5  — fast analysis (get_grid_insight, explain_alert, generate_settlement_narrative)
claude-sonnet-4-6 — complex reasoning (optimize_with_llm)

All functions degrade gracefully when the API key is absent or the call fails.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ── Grid insight ──────────────────────────────────────────────────────────────

async def get_grid_insight(
    deployment_id: str,
    grid_state: dict,
    question: Optional[str] = None,
) -> dict:
    """
    Ask Claude to analyse current grid state and provide operational insights.

    Returns: {"insight": str, "model": str, "deployment": str, "generated_at": str}
    """
    if not settings.anthropic_api_key:
        logger.debug("No Anthropic API key — returning fallback insight")
        return _fallback_insight(grid_state)

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        constrained_nodes = [
            n for n in grid_state.get("nodes", [])
            if n.get("current_loading_pct", 0) > 75
            or (n.get("voltage_l1_v") or 230.0) > settings.voltage_high_warn
            or (n.get("voltage_l1_v") or 230.0) < settings.voltage_low_warn
        ]

        context = (
            f"You are an expert grid operations assistant for L&T Neural Grid DERMS.\n"
            f"Deployment: {deployment_id.upper()}\n"
            f"Current grid state:\n"
            f"- Total generation: {grid_state.get('total_gen_kw', 0):.1f} kW\n"
            f"- Total load: {grid_state.get('total_load_kw', 0):.1f} kW\n"
            f"- Net import/export: {grid_state.get('net_kw', 0):.1f} kW\n"
            f"- Assets online: {grid_state.get('assets_online', 0)}\n"
            f"- Assets curtailed: {grid_state.get('assets_curtailed', 0)}\n"
            f"- Solar factor: {grid_state.get('solar_factor', 0):.2f}\n"
            f"- Load factor: {grid_state.get('load_factor', 0):.2f}\n\n"
            f"Constrained nodes:\n{json.dumps(constrained_nodes[:5], indent=2)}"
        )
        prompt = question or (
            "Analyse the current grid state. What are the key operational priorities? "
            "What actions should the operator take? Be concise (3-4 sentences)."
        )

        message = await client.messages.create(
            model=settings.llm_model,
            max_tokens=500,
            messages=[{"role": "user", "content": f"{context}\n\nQuestion: {prompt}"}],
        )
        return {
            "insight": message.content[0].text,
            "model": settings.llm_model,
            "deployment": deployment_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.warning("Claude get_grid_insight failed: %s", exc)
        return _fallback_insight(grid_state)


# ── Alert explanation ─────────────────────────────────────────────────────────

async def explain_alert(alert: dict, deployment_id: str) -> str:
    """Explain a grid alert in plain English and suggest one remediation action."""
    if not settings.anthropic_api_key:
        return (
            f"Alert: {alert.get('message', 'Unknown alert')}. "
            "Please review grid conditions and take appropriate action."
        )

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=settings.llm_model,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Explain this grid alert to a utility operator in 2-3 sentences "
                        f"and suggest one immediate action:\n"
                        f"Alert type: {alert.get('alert_type')}\n"
                        f"Severity: {alert.get('severity')}\n"
                        f"Message: {alert.get('message')}\n"
                        f"Deployment: {deployment_id.upper()}"
                    ),
                }
            ],
        )
        return message.content[0].text
    except Exception as exc:
        logger.warning("Claude explain_alert failed: %s", exc)
        return alert.get("message", "Alert requires operator attention.")


# ── Optimization advisory ─────────────────────────────────────────────────────

async def optimize_with_llm(scenario: dict, deployment_id: str) -> dict:
    """
    Use Claude Sonnet for complex optimization reasoning.
    Returns natural language dispatch recommendation.
    """
    if not settings.anthropic_api_key:
        return {
            "recommendation": (
                "Standard greedy dispatch recommended. "
                "Prioritise BESS discharge then V2G, then heat pump load-shifting."
            ),
            "confidence": "medium",
            "model": "fallback",
        }

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        message = await client.messages.create(
            model=settings.llm_advisor_model,
            max_tokens=600,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"You are a grid optimization expert. Recommend the optimal dispatch strategy:\n"
                        f"Deployment: {deployment_id.upper()}\n"
                        f"Target flex: {scenario.get('target_kw')} kW\n"
                        f"Duration: {scenario.get('duration_minutes')} minutes\n"
                        f"Available assets: {json.dumps(scenario.get('available_assets', [])[:8], indent=2)}\n"
                        f"Grid constraint: {scenario.get('constraint_type')}\n\n"
                        "Provide: (1) Recommended asset selection order, (2) Why, "
                        "(3) Risk factors, (4) Alternative if primary fails.\n"
                        "Be concise and operational."
                    ),
                }
            ],
        )
        return {
            "recommendation": message.content[0].text,
            "model": settings.llm_advisor_model,
            "confidence": "high",
        }
    except Exception as exc:
        logger.warning("Claude optimize_with_llm failed: %s", exc)
        return {
            "recommendation": "Unable to generate AI recommendation. Use standard dispatch protocol.",
            "confidence": "low",
            "model": "fallback",
        }


# ── Settlement narrative ──────────────────────────────────────────────────────

async def generate_settlement_narrative(statement: dict, deployment_id: str) -> str:
    """Generate plain-English settlement summary for a statement dict."""
    if not settings.anthropic_api_key:
        ps = statement.get("period_start", "")[:10]
        pe = statement.get("period_end", "")[:10]
        return (
            f"Settlement period {ps} to {pe}. "
            f"Net payment: {statement.get('net_payment_minor', 0)} minor units "
            f"({statement.get('currency_code', 'GBP')}). "
            "Please review the figures in the statement below."
        )

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        # Summarise key figures to avoid sending entire JSON
        summary = {
            "period": f"{statement.get('period_start', '')[:10]} to {statement.get('period_end', '')[:10]}",
            "events_dispatched": statement.get("events_count", 0),
            "avg_delivery_pct": statement.get("avg_delivery_pct", 0),
            "delivered_kwh": statement.get("delivered_kwh", 0),
            "gross_payment_minor": statement.get("gross_payment_minor", 0),
            "penalties_minor": statement.get("penalty_amount_minor", 0),
            "net_payment_minor": statement.get("net_payment_minor", 0),
            "currency": statement.get("currency_code", "GBP"),
        }
        message = await client.messages.create(
            model=settings.llm_model,
            max_tokens=250,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Write a 3-sentence plain-English settlement summary for a utility "
                        f"flexibility program settlement statement:\n{json.dumps(summary, indent=2)}"
                    ),
                }
            ],
        )
        return message.content[0].text
    except Exception as exc:
        logger.warning("Claude generate_settlement_narrative failed: %s", exc)
        return "Settlement calculation complete. Please review figures below."


# ── Fallback (no API key) ─────────────────────────────────────────────────────

def _fallback_insight(grid_state: dict) -> dict:
    """Return rule-based insight when the Claude API is unavailable."""
    issues = []
    for node in grid_state.get("nodes", []):
        loading = node.get("current_loading_pct", 0.0)
        v = node.get("voltage_l1_v", 230.0) or 230.0
        nid = node.get("node_id", "")

        if loading > settings.feeder_loading_warn:
            issues.append(f"Feeder {nid} overloaded at {loading:.0f}%")
        if v > settings.voltage_high_warn:
            issues.append(f"Overvoltage at {nid}: {v:.1f} V")
        if v < settings.voltage_low_warn:
            issues.append(f"Undervoltage at {nid}: {v:.1f} V")

    if not issues:
        insight = (
            "Grid operating normally. No constraints detected. "
            "Monitor solar ramp and EV charging load during peak hours."
        )
    else:
        insight = (
            "Constraints detected: " + "; ".join(issues[:3]) + ". "
            "Consider curtailing exports or dispatching BESS to relieve constraint."
        )

    return {
        "insight": insight,
        "model": "fallback",
        "deployment": grid_state.get("deployment_id", "unknown"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
