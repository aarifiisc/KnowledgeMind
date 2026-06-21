from __future__ import annotations

import re
from datetime import date, timedelta

from dateutil import parser as _du_parser

from config import CURRENT_DATE

_WEEKDAYS: dict[str, int] = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

_TIME_WORDS: dict[str, str] = {
    "noon": "12:00",
    "midnight": "00:00",
    "morning": "09:00",
    "afternoon": "14:00",
    "evening": "18:00",
    "night": "20:00",
}


def resolve_date(text: str, anchor: date | None = None) -> str:
    """
    Convert a natural-language date string to YYYY-MM-DD.
    Falls back to the original string if it cannot be resolved.
    """
    anchor = anchor or CURRENT_DATE
    raw = text.strip().lower()

    if raw in ("today", "now"):
        return anchor.isoformat()

    if raw == "tomorrow":
        return (anchor + timedelta(days=1)).isoformat()

    if raw == "yesterday":
        return (anchor - timedelta(days=1)).isoformat()

    # "in N days/weeks"
    m = re.match(r"in (\d+) (day|week)s?", raw)
    if m:
        n = int(m.group(1))
        delta = timedelta(days=n) if m.group(2) == "day" else timedelta(weeks=n)
        return (anchor + delta).isoformat()

    # "next <weekday>" — always the coming occurrence, minimum 1 day ahead
    m = re.match(r"next (\w+)", raw)
    if m and m.group(1) in _WEEKDAYS:
        target = _WEEKDAYS[m.group(1)]
        days_ahead = (target - anchor.weekday()) % 7 or 7
        return (anchor + timedelta(days=days_ahead)).isoformat()

    # "this <weekday>" — current week's occurrence (may be today or past)
    m = re.match(r"this (\w+)", raw)
    if m and m.group(1) in _WEEKDAYS:
        target = _WEEKDAYS[m.group(1)]
        days_ahead = (target - anchor.weekday()) % 7
        return (anchor + timedelta(days=days_ahead)).isoformat()

    # bare weekday name — nearest future occurrence
    if raw in _WEEKDAYS:
        target = _WEEKDAYS[raw]
        days_ahead = (target - anchor.weekday()) % 7 or 7
        return (anchor + timedelta(days=days_ahead)).isoformat()

    # absolute date strings via dateutil ("June 20", "20th March", "2026-06-20")
    try:
        default_dt = date(anchor.year, anchor.month, anchor.day)
        parsed = _du_parser.parse(text, default=_du_parser.parse(default_dt.isoformat()))
        return parsed.date().isoformat()
    except (ValueError, OverflowError):
        return text  # return as-is; graph_store will treat it as an opaque label


def resolve_time(text: str) -> str:
    """
    Convert a natural-language or 12h time string to HH:MM 24h.
    Returns "TBD" if the time cannot be resolved.
    """
    raw = text.strip().lower()

    if raw in ("tbd", "unknown", "n/a", ""):
        return "TBD"

    if raw in _TIME_WORDS:
        return _TIME_WORDS[raw]

    # "3pm", "3 pm", "15:00", "3:30 AM", etc.
    try:
        parsed = _du_parser.parse(text)
        return parsed.strftime("%H:%M")
    except (ValueError, OverflowError):
        return "TBD"
