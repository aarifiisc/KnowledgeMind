from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, field_validator


class EventEntity(BaseModel):
    person: str
    activity: str
    date_str: str   # absolute date YYYY-MM-DD after resolver runs
    time_str: str   # HH:MM 24h, or "TBD"
    action: Literal["add", "remove", "update"]

    @field_validator("person", "activity", mode="before")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("time_str", mode="before")
    @classmethod
    def _normalise_tbd(cls, v: str) -> str:
        if v.strip().upper() in ("TBD", "UNKNOWN", "N/A", ""):
            return "TBD"
        return v.strip()
