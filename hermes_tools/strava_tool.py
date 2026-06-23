"""
hermes_tools/strava_tool.py
----------------------------
Strava fitness signal tool — exposed as MCP tool `strava_summary`.

Calls StravaConnector, derives signals locally, returns a structured dict.
Raw GPS routes, timestamps, and activity names never leave this process.
Privacy floor: 0.95 (ALWAYS_LOCAL).
"""

from __future__ import annotations

from connectors.strava import StravaConnector, derive_strava_signals
from kg.connector_store import record_strava


def strava_summary() -> dict:
    """
    Return fitness signals derived from Strava recent activities.

    All computation is local. Only derived signals (days since last run,
    weekly km vs average, gap threshold flag) are returned — never raw
    GPS, timestamps, or activity names.

    Returns:
        {
            "success": bool,
            "days_since_last_activity": int,
            "last_activity_type": str | None,
            "last_activity_name": str | None,
            "last_activity_date": str | None,   # YYYY-MM-DD
            "weekly_run_km": float,
            "weekly_vs_4w_avg": float | None,   # ratio; None if no baseline
            "gap_threshold_exceeded": bool,
            "summary": str,                     # human-readable one-liner
            "source": "live" | "mock",
        }
    """
    connector = StravaConnector()

    if connector.health_check():
        activities = connector.get_activities()
        source = "live"
    else:
        activities = connector.load_mock()
        source = "mock"

    signals = derive_strava_signals(activities)
    result = {"success": True, "source": source, **signals}
    try:
        record_strava(result)
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = strava_summary()
    assert result["success"] is True
    assert "days_since_last_activity" in result
    assert "summary" in result
    print(f"=> source                   : {result['source']}")
    print(f"=> days_since_last_activity : {result['days_since_last_activity']}")
    print(f"=> weekly_run_km            : {result['weekly_run_km']}")
    print(f"=> gap_threshold_exceeded   : {result['gap_threshold_exceeded']}")
    print(f"=> summary                  : {result['summary']}")
    print("All hermes_tools/strava_tool.py smoke tests passed.")
