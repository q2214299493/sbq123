"""Strict identity and timestamp fields shared by source and model provenance."""
from __future__ import annotations

from datetime import datetime


def required_text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value.strip().lower() in {"none", "null", "unknown"}:
        raise ValueError(f"{label} requires identified text")
    return value


def timestamp(value, label: str) -> datetime:
    text = required_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} requires an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} requires a timezone")
    return parsed


