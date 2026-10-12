"""Schedule evaluation and contact-rule overrides for call decisions."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any


def _parse_clock(value: str) -> time:
    hour, minute = (int(part) for part in value.split(":"))
    return time(hour, minute)


def schedule_is_active(settings: dict[str, Any], now: datetime | None = None) -> bool:
    if not settings.get("schedule_enabled"):
        return False
    try:
        timezone = ZoneInfo(settings.get("timezone", "UTC"))
        local_now = (now or datetime.now(timezone)).astimezone(timezone)
        start = _parse_clock(settings.get("schedule_start", "09:00"))
        end = _parse_clock(settings.get("schedule_end", "17:00"))
        days = {int(day) for day in settings.get("schedule_days", [])}
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return False
    if not days or start == end:
        return False
    clock = local_now.timetz().replace(tzinfo=None)
    weekday = local_now.weekday()
    if start < end:
        return weekday in days and start <= clock < end
    previous_day = (weekday - 1) % 7
    return (weekday in days and clock >= start) or (previous_day in days and clock < end)


def effective_agent_state(settings: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    scheduled = schedule_is_active(settings, now)
    manual = bool(settings.get("manual_active", False))
    return {
        "active": manual or scheduled,
        "manual_active": manual,
        "scheduled_active": scheduled,
        "source": "schedule" if scheduled and not manual else "manual" if manual else "offline",
    }


def apply_contact_rule(analysis: Any, contact: dict[str, Any] | None) -> Any:
    identity = contact.get("name", "Saved contact") if contact else "Unknown caller; identity not verified"
    if not contact:
        return analysis.model_copy(update={"caller_identity": identity})
    rule = contact.get("rule", "screen")
    if rule == "always_transfer":
        return analysis.model_copy(update={
            "decision": "Transfer",
            "risk_level": "Medium",
            "caller_identity": identity,
            "decision_reason": "Your saved rule requests a transfer for this caller.",
        })
    if rule == "always_handle":
        return analysis.model_copy(update={
            "decision": "Handle",
            "caller_identity": identity,
            "decision_reason": "Your saved rule lets the agent handle this caller.",
        })
    return analysis.model_copy(update={"caller_identity": identity})