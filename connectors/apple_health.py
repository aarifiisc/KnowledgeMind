"""
connectors/apple_health.py
--------------------------
Apple Health export reader.

Apple Health data lives on iPhone / Apple Watch — there is no public REST API
accessible from macOS without a companion iOS app.  The POC approach:

  iOS Shortcut (runs daily or on-demand)
    → reads HealthKit fields (sleep, HRV, resting HR, steps, active energy)
    → writes a JSON file to iCloud Drive at:
        ~/Library/Mobile Documents/com~apple~CloudDocs/HealthExport/
          health_YYYY-MM-DD.json

This connector reads the latest such file.  All arithmetic is local;
raw biometric values never leave the device (privacy floor 0.98).

See docs/apple_health_shortcut.md for the Shortcut recipe.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from config.store import get_config

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------------------
# Expected JSON schema from the iOS Shortcut export
# ---------------------------------------------------------------------------
# {
#   "date": "2026-06-21",
#   "steps": 8432,
#   "sleep_hours": 6.2,
#   "sleep_quality": "fair",      # "poor" | "fair" | "good"
#   "resting_hr": 58,
#   "hrv_ms": 42.0,
#   "active_energy_kcal": 380,
#   "stand_hours": 9
# }


class AppleHealthConnector:
    """Reads the latest Apple Health JSON export from iCloud Drive."""

    source_name = "apple_health"

    def __init__(self) -> None:
        cfg = get_config()
        self._export_dir = Path(os.path.expanduser(cfg.apple_health_export_path))

    # -- health -------------------------------------------------------------

    def health_check(self) -> bool:
        """True if the iCloud export directory exists and contains at least one file."""
        if not self._export_dir.exists():
            return False
        return any(self._export_dir.glob("health_*.json"))

    # -- data fetcher -------------------------------------------------------

    def get_daily_summary(self, target_date: Optional[str] = None) -> Optional[dict]:
        """
        Return the health summary dict for target_date (YYYY-MM-DD).
        Falls back to the most recent available file if the exact date is missing.
        Returns None when no export file exists at all.
        """
        if target_date is None:
            target_date = date.today().isoformat()

        # Try exact date first
        exact = self._export_dir / f"health_{target_date}.json"
        if exact.exists():
            return self._read(exact)

        # Fall back to the most recent file
        files = sorted(self._export_dir.glob("health_*.json"))
        if not files:
            return None
        return self._read(files[-1])

    @staticmethod
    def _read(path: Path) -> Optional[dict]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"[AppleHealth] WARNING: could not read {path.name} ({exc}).")
            return None

    # -- mock fallback ------------------------------------------------------

    def load_mock(self) -> Optional[dict]:
        """Return mock health data from data/mock_apple_health.json."""
        path = DATA_DIR / "mock_apple_health.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None


# ---------------------------------------------------------------------------
# Signal derivation (pure — no network, no LLM)
# ---------------------------------------------------------------------------

_SLEEP_THRESHOLDS = {"poor": 5.5, "fair": 6.5}  # hours — below fair = poor, etc.


def _classify_sleep(hours: Optional[float]) -> str:
    if hours is None:
        return "unknown"
    if hours < _SLEEP_THRESHOLDS["poor"]:
        return "poor"
    if hours < _SLEEP_THRESHOLDS["fair"]:
        return "fair"
    return "good"


def derive_apple_health_signals(summary: Optional[dict]) -> dict:
    """
    Compute health signals from one day's Apple Health export.
    All arithmetic is local; no raw values are forwarded to any cloud model.
    Only derived labels ("sleep: poor", "recovery: low") reach Hermes reasoning.
    """
    if not summary:
        return {
            "available": False,
            "date": None,
            "sleep_quality": "unknown",
            "sleep_hours": None,
            "recovery_status": "unknown",
            "low_hrv": False,
            "high_rhr": False,
            "steps": None,
            "summary": "No Apple Health export available for today.",
        }

    cfg = get_config()

    sleep_hrs: Optional[float] = summary.get("sleep_hours")
    hrv: Optional[float]       = summary.get("hrv_ms")
    rhr: Optional[float]       = summary.get("resting_hr")
    steps: Optional[int]       = summary.get("steps")

    sleep_qual = summary.get("sleep_quality") or _classify_sleep(sleep_hrs)

    # HRV — low if < 80 % of learned baseline (skip check when baseline = 0)
    low_hrv = (
        cfg.apple_health_hrv_baseline > 0
        and hrv is not None
        and hrv < cfg.apple_health_hrv_baseline * 0.80
    )

    # Resting HR — high if > baseline + 8 bpm
    high_rhr = (
        cfg.apple_health_rhr_baseline > 0
        and rhr is not None
        and rhr > cfg.apple_health_rhr_baseline + 8
    )

    # Recovery status
    if low_hrv or high_rhr or sleep_qual == "poor":
        recovery = "low"
    elif sleep_qual == "fair":
        recovery = "moderate"
    else:
        recovery = "good"

    # Human-readable summary
    parts: list[str] = []
    if sleep_hrs is not None:
        parts.append(f"Sleep: {sleep_hrs:.1f}h ({sleep_qual}).")
    if hrv is not None:
        parts.append(f"HRV: {hrv:.0f} ms{'  ↓ (low)' if low_hrv else ''}.")
    if rhr is not None:
        parts.append(f"Resting HR: {rhr:.0f} bpm{'  ↑ (elevated)' if high_rhr else ''}.")
    if steps is not None:
        parts.append(f"Steps: {steps:,}.")
    parts.append(f"Recovery: {recovery}.")

    return {
        "available": True,
        "date": summary.get("date"),
        "sleep_quality": sleep_qual,
        "sleep_hours": sleep_hrs,
        "recovery_status": recovery,
        "low_hrv": low_hrv,
        "high_rhr": high_rhr,
        "steps": steps,
        "summary": " ".join(parts),
    }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    connector = AppleHealthConnector()

    if connector.health_check():
        print("[AppleHealth] export directory found — reading latest file")
        raw = connector.get_daily_summary()
    else:
        print("[AppleHealth] export not available — using mock data")
        raw = connector.load_mock()

    signals = derive_apple_health_signals(raw)
    print(f"=> available       : {signals['available']}")
    print(f"=> sleep_quality   : {signals['sleep_quality']}")
    print(f"=> recovery_status : {signals['recovery_status']}")
    print(f"=> low_hrv         : {signals['low_hrv']}")
    print(f"=> summary         : {signals['summary']}")
    print("All connectors/apple_health.py smoke tests passed.")
