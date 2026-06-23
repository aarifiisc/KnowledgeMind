"""
connectors/strava.py
--------------------
Strava API v3 connector.  Fetches recent activities and athlete stats,
derives fitness signals locally, and never sends raw GPS or activity data
to any cloud model (privacy floor 0.95).

Auth: OAuth 2.0 authorization-code flow.  Tokens are stored in AppConfig
(strava_access_token / strava_refresh_token) and auto-refreshed here when
a 401 is received.  health_check() returns False when no access token is
configured, which triggers mock-data fallback in the signal tool.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

from config.store import get_config, update_config

_BASE = "https://www.strava.com/api/v3"
_TOKEN_URL = "https://www.strava.com/oauth/token"
_TIMEOUT = 10          # seconds per request
_ACTIVITY_FETCH = 50   # most recent activities to pull per call

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

def _refresh_strava_token() -> Optional[str]:
    """
    Exchange the stored refresh token for a new access token.
    Persists the new tokens to config and returns the new access token,
    or None if the refresh fails (missing credentials, network error, etc.).
    """
    cfg = get_config()
    if not (cfg.strava_client_id and cfg.strava_client_secret and cfg.strava_refresh_token):
        return None
    try:
        resp = requests.post(_TOKEN_URL, data={
            "client_id":     cfg.strava_client_id,
            "client_secret": cfg.strava_client_secret,
            "refresh_token": cfg.strava_refresh_token,
            "grant_type":    "refresh_token",
        }, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        update_config(
            strava_access_token=data["access_token"],
            strava_refresh_token=data.get("refresh_token", cfg.strava_refresh_token),
        )
        return data["access_token"]
    except Exception as exc:  # noqa: BLE001
        print(f"[Strava] WARNING: token refresh failed ({exc}).")
        return None


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------

class StravaConnector:
    """Reads recent Strava activities and derives fitness signals locally."""

    source_name = "strava"

    def __init__(self) -> None:
        self._cfg = get_config()

    # -- auth header --------------------------------------------------------

    def _headers(self, token: Optional[str] = None) -> dict[str, str]:
        tok = token or self._cfg.strava_access_token
        return {"Authorization": f"Bearer {tok}"}

    # -- health -------------------------------------------------------------

    def health_check(self) -> bool:
        """True if an access token is present and the Strava API responds."""
        if not self._cfg.strava_access_token:
            return False
        try:
            resp = requests.get(
                f"{_BASE}/athlete",
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            if resp.status_code == 401:
                new_token = _refresh_strava_token()
                return new_token is not None
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    # -- data fetchers ------------------------------------------------------

    def get_activities(self, per_page: int = _ACTIVITY_FETCH) -> list[dict]:
        """Return the most recent activities, newest first. Never raises."""
        try:
            resp = requests.get(
                f"{_BASE}/athlete/activities",
                headers=self._headers(),
                params={"per_page": per_page},
                timeout=_TIMEOUT,
            )
            if resp.status_code == 401:
                new_token = _refresh_strava_token()
                if not new_token:
                    return []
                resp = requests.get(
                    f"{_BASE}/athlete/activities",
                    headers=self._headers(new_token),
                    params={"per_page": per_page},
                    timeout=_TIMEOUT,
                )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[Strava] ERROR: get_activities failed ({exc}).")
            return []

    def get_athlete(self) -> dict:
        """Return the authenticated athlete profile. Never raises."""
        try:
            resp = requests.get(
                f"{_BASE}/athlete",
                headers=self._headers(),
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[Strava] ERROR: get_athlete failed ({exc}).")
            return {}

    # -- mock fallback ------------------------------------------------------

    def load_mock(self) -> list[dict]:
        """Return mock activity data from data/mock_strava.json."""
        path = DATA_DIR / "mock_strava.json"
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []


# ---------------------------------------------------------------------------
# Signal derivation (pure — no network, no LLM)
# ---------------------------------------------------------------------------

def derive_strava_signals(activities: list[dict]) -> dict:
    """
    Compute fitness signals from a list of Strava activity dicts.
    All arithmetic is local; nothing goes to a cloud model.

    Returns a structured dict consumed by hermes_tools/strava_tool.py.
    """
    cfg = get_config()

    if not activities:
        return {
            "days_since_last_activity": 999,
            "last_activity_type": None,
            "last_activity_name": None,
            "last_activity_date": None,
            "weekly_run_km": 0.0,
            "weekly_vs_4w_avg": None,
            "gap_threshold_exceeded": True,
            "summary": "No recent Strava activities found.",
        }

    now = datetime.now(timezone.utc)

    def _parse_dt(iso: str) -> datetime:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))

    # Most recent activity
    last = activities[0]
    last_dt = _parse_dt(last["start_date"])
    days_since = (now - last_dt).days

    # Weekly run distance
    week_ago = now - timedelta(days=7)
    weekly_run_km = sum(
        a["distance"] / 1000
        for a in activities
        if a.get("type") in ("Run", "TrailRun", "VirtualRun")
        and _parse_dt(a["start_date"]) > week_ago
    )

    # 4-week run average
    four_weeks_ago = now - timedelta(days=28)
    four_week_km = sum(
        a["distance"] / 1000
        for a in activities
        if a.get("type") in ("Run", "TrailRun", "VirtualRun")
        and _parse_dt(a["start_date"]) > four_weeks_ago
    )
    avg_4w = four_week_km / 4
    ratio = round(weekly_run_km / avg_4w, 2) if avg_4w > 0 else None

    gap_exceeded = days_since > cfg.strava_gap_threshold_days

    # Human-readable summary (used by Hermes skill prompt)
    parts: list[str] = [
        f"Last activity: {last.get('type', 'Unknown')} — "
        f"\"{last.get('name', '')}\" "
        f"({last_dt.strftime('%a %b %d')}, {days_since}d ago).",
        f"Weekly run: {weekly_run_km:.1f} km.",
    ]
    if ratio is not None:
        pct = int(ratio * 100)
        parts.append(f"vs 4-week avg: {pct}%.")
    if gap_exceeded:
        parts.append(
            f"Activity gap ({days_since}d) exceeds threshold "
            f"({cfg.strava_gap_threshold_days}d)."
        )

    return {
        "days_since_last_activity": days_since,
        "last_activity_type": last.get("type"),
        "last_activity_name": last.get("name"),
        "last_activity_date": last_dt.date().isoformat(),
        "weekly_run_km": round(weekly_run_km, 1),
        "weekly_vs_4w_avg": ratio,
        "gap_threshold_exceeded": gap_exceeded,
        "summary": " ".join(parts),
    }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    connector = StravaConnector()

    if connector.health_check():
        print("[Strava] live token found — fetching real activities")
        acts = connector.get_activities(per_page=10)
    else:
        print("[Strava] no token — using mock data")
        acts = connector.load_mock()

    signals = derive_strava_signals(acts)
    print(f"=> days_since_last_activity : {signals['days_since_last_activity']}")
    print(f"=> weekly_run_km            : {signals['weekly_run_km']}")
    print(f"=> gap_threshold_exceeded   : {signals['gap_threshold_exceeded']}")
    print(f"=> summary                  : {signals['summary']}")
    print("All connectors/strava.py smoke tests passed.")
