import uuid
from datetime import datetime, timezone


def new_uuid() -> str:
    """Generate a new UUID4 as a string."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def format_currency(minor_units: int, currency_code: str) -> str:
    """
    Convert an amount expressed in minor currency units to a human-readable string.

    Examples:
        format_currency(12350, "GBP")  → "£123.50"
        format_currency(500000, "INR") → "₹5000.00"
    """
    symbols: dict[str, str] = {
        "GBP": "£",
        "INR": "₹",
        "USD": "$",
        "EUR": "€",
    }
    symbol = symbols.get(currency_code, currency_code + " ")
    return f"{symbol}{minor_units / 100:.2f}"
