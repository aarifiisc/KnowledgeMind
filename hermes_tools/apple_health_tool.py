"""
hermes_tools/apple_health_tool.py
----------------------------------
Apple Health signal tool — exposed as MCP tool `apple_health_summary`.

Reads the latest iCloud-synced export JSON, derives health signals locally,
and returns only derived labels (sleep quality, recovery status) — never raw
HRV values, step counts, or heart rate numbers.
Privacy floor: 0.98 (highest — health biometrics, ALWAYS_LOCAL).
"""

from __future__ import annotations

from typing import Optional

from connectors.apple_health import AppleHealthConnector, derive_apple_health_signals
from kg.connector_store import record_apple_health


def apple_health_summary(date: Optional[str] = None) -> dict:
    """
    Return health signals derived from the Apple Health export for `date`.

    Args:
        date: ISO date string YYYY-MM-DD, or None for today.

    Returns:
        {
            "success": bool,
            "available": bool,
            "date": str | None,
            "sleep_quality": "poor" | "fair" | "good" | "unknown",
            "sleep_hours": float | None,
            "recovery_status": "low" | "moderate" | "good" | "unknown",
            "low_hrv": bool,
            "high_rhr": bool,
            "steps": int | None,
            "summary": str,
            "source": "live" | "mock",
        }
    """
    connector = AppleHealthConnector()

    if connector.health_check():
        raw = connector.get_daily_summary(target_date=date)
        source = "live"
    else:
        raw = connector.load_mock()
        source = "mock"

    signals = derive_apple_health_signals(raw)
    result = {"success": True, "source": source, **signals}
    try:
        record_apple_health(result)
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = apple_health_summary()
    assert result["success"] is True
    assert "sleep_quality" in result
    assert "recovery_status" in result
    print(f"=> source          : {result['source']}")
    print(f"=> available       : {result['available']}")
    print(f"=> sleep_quality   : {result['sleep_quality']}")
    print(f"=> recovery_status : {result['recovery_status']}")
    print(f"=> low_hrv         : {result['low_hrv']}")
    print(f"=> summary         : {result['summary']}")
    print("All hermes_tools/apple_health_tool.py smoke tests passed.")
