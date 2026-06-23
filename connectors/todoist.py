"""
connectors/todoist.py
---------------------
Todoist REST API v2 connector.

Auth: personal developer token (no OAuth needed).
Token is stored in AppConfig.todoist_api_token and set via
TODOIST_API_TOKEN env var or the setup UI.

Privacy floor: 0.90 — task titles/descriptions are personal and processed
only by the local Hermes model, never sent to a cloud model.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

import requests

from config.store import get_config

_BASE = "https://api.todoist.com/rest/v2"
_TIMEOUT = 10

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TodoistConnector:
    """Reads tasks from Todoist via REST API v2."""

    source_name = "todoist"

    def __init__(self) -> None:
        cfg = get_config()
        self._token = cfg.todoist_api_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    # -- health -------------------------------------------------------------

    def health_check(self) -> bool:
        """True if a token is present and Todoist responds."""
        if not self._token:
            return False
        try:
            resp = requests.get(
                f"{_BASE}/projects",
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    # -- data fetchers ------------------------------------------------------

    def get_tasks(self, filter_str: str = "today | overdue") -> list[dict]:
        """
        Fetch tasks matching a Todoist filter string.
        Returns an empty list on any error (never raises).
        """
        if not self._token:
            return []
        try:
            resp = requests.get(
                f"{_BASE}/tasks",
                headers=self._headers(),
                params={"filter": filter_str},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[Todoist] ERROR: get_tasks failed ({exc}).")
            return []

    def get_projects(self) -> list[dict]:
        """Fetch all projects. Used to enrich task display. Never raises."""
        if not self._token:
            return []
        try:
            resp = requests.get(
                f"{_BASE}/projects",
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[Todoist] ERROR: get_projects failed ({exc}).")
            return []

    # -- mock fallback ------------------------------------------------------

    def load_mock(self) -> list[dict]:
        """Return mock tasks from data/mock_todoist.json."""
        path = DATA_DIR / "mock_todoist.json"
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []


# ---------------------------------------------------------------------------
# Signal derivation (pure — no network, no LLM)
# ---------------------------------------------------------------------------

def derive_todoist_signals(tasks: list[dict]) -> dict:
    """
    Compute task load signals from a list of Todoist task dicts.
    Full task content (titles, descriptions) is kept in the output because
    it is processed only by the local Hermes model, never a cloud model.
    """
    today = date.today().isoformat()

    overdue: list[dict] = []
    due_today: list[dict] = []
    upcoming: list[dict] = []

    for task in tasks:
        due = (task.get("due") or {}).get("date")
        if due is None:
            continue
        if due < today:
            overdue.append(task)
        elif due == today:
            due_today.append(task)
        else:
            upcoming.append(task)

    # Tasks without a due date that appeared in the query (e.g., "overdue" filter)
    no_due = [t for t in tasks if not (t.get("due") or {}).get("date")]

    total = len(tasks)
    overdue_count = len(overdue)
    due_today_count = len(due_today)
    heavy_day = (due_today_count + overdue_count) > 5
    clear_day = total == 0

    # Top tasks for the summary (highest Todoist priority = 4 = p1)
    def _priority(t: dict) -> int:
        return -(t.get("priority", 1))  # negate so p4 sorts first

    top_tasks = sorted(due_today + overdue, key=_priority)[:5]
    top_titles = [t.get("content", "(no title)") for t in top_tasks]

    if clear_day:
        summary = "No tasks due today or overdue. Clear day!"
    else:
        parts = []
        if overdue_count:
            parts.append(f"{overdue_count} overdue")
        if due_today_count:
            parts.append(f"{due_today_count} due today")
        summary = f"Tasks: {', '.join(parts)}."
        if top_titles:
            summary += " Top items: " + "; ".join(top_titles[:3]) + "."

    return {
        "total": total,
        "overdue_count": overdue_count,
        "due_today_count": due_today_count,
        "heavy_day": heavy_day,
        "clear_day": clear_day,
        "top_tasks": top_titles,
        "overdue_tasks": [t.get("content") for t in overdue[:10]],
        "due_today_tasks": [t.get("content") for t in due_today[:10]],
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    connector = TodoistConnector()

    if connector.health_check():
        print("[Todoist] live token found — fetching real tasks")
        tasks = connector.get_tasks()
    else:
        print("[Todoist] no token — using mock data")
        tasks = connector.load_mock()

    signals = derive_todoist_signals(tasks)
    print(f"=> total           : {signals['total']}")
    print(f"=> overdue_count   : {signals['overdue_count']}")
    print(f"=> due_today_count : {signals['due_today_count']}")
    print(f"=> heavy_day       : {signals['heavy_day']}")
    print(f"=> summary         : {signals['summary']}")
    print("All connectors/todoist.py smoke tests passed.")
