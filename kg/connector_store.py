"""
kg/connector_store.py
---------------------
Read/write helpers for the connector snapshot database.

Every hermes_tool calls record_*() after a successful poll to persist the
derived signals.  The UI calls get_latest() and get_history() to render
status cards and history tables.

All functions open a short-lived connection and close it on return so the
file lock is never held across the UI's polling interval.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from config.store import get_config
from kg.connector_schema import get_connector_db_connection


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _db():
    """Return a fresh connection to the connector DB."""
    cfg = get_config()
    return get_connector_db_connection(cfg.connector_db_path)


def _record_run(conn, connector: str, source: str, success: bool, summary: str) -> int:
    cur = conn.execute(
        "INSERT INTO connector_runs (connector, polled_at, source, success, summary) "
        "VALUES (?, ?, ?, ?, ?)",
        (connector, time.time(), source, int(success), summary),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Write: one function per connector
# ---------------------------------------------------------------------------

def record_strava(signals: dict) -> None:
    """Persist a Strava snapshot to the connector DB."""
    conn = _db()
    try:
        run_id = _record_run(
            conn, "strava",
            signals.get("source", "mock"),
            signals.get("success", True),
            signals.get("summary", ""),
        )
        conn.execute(
            """INSERT INTO strava_snapshots
               (run_id, polled_at, days_since_last_activity, last_activity_type,
                last_activity_date, weekly_run_km, weekly_vs_4w_avg,
                gap_threshold_exceeded, source)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                run_id, time.time(),
                signals.get("days_since_last_activity"),
                signals.get("last_activity_type"),
                signals.get("last_activity_date"),
                signals.get("weekly_run_km"),
                signals.get("weekly_vs_4w_avg"),
                int(bool(signals.get("gap_threshold_exceeded"))),
                signals.get("source", "mock"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def record_apple_health(signals: dict) -> None:
    """Persist an Apple Health snapshot to the connector DB."""
    conn = _db()
    try:
        run_id = _record_run(
            conn, "apple_health",
            signals.get("source", "mock"),
            signals.get("success", True),
            signals.get("summary", ""),
        )
        conn.execute(
            """INSERT INTO apple_health_snapshots
               (run_id, polled_at, health_date, sleep_quality, sleep_hours,
                recovery_status, low_hrv, high_rhr, steps, source)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, time.time(),
                signals.get("date"),
                signals.get("sleep_quality"),
                signals.get("sleep_hours"),
                signals.get("recovery_status"),
                int(bool(signals.get("low_hrv"))),
                int(bool(signals.get("high_rhr"))),
                signals.get("steps"),
                signals.get("source", "mock"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def record_todoist(signals: dict) -> None:
    """Persist a Todoist snapshot to the connector DB."""
    conn = _db()
    try:
        run_id = _record_run(
            conn, "todoist",
            signals.get("source", "mock"),
            signals.get("success", True),
            signals.get("summary", ""),
        )
        top_tasks = signals.get("top_tasks") or []
        conn.execute(
            """INSERT INTO todoist_snapshots
               (run_id, polled_at, total, overdue_count, due_today_count,
                heavy_day, clear_day, top_tasks, source)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                run_id, time.time(),
                signals.get("total"),
                signals.get("overdue_count"),
                signals.get("due_today_count"),
                int(bool(signals.get("heavy_day"))),
                int(bool(signals.get("clear_day"))),
                json.dumps(top_tasks),
                signals.get("source", "mock"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def record_spotify(signals: dict) -> None:
    """Persist a Spotify snapshot to the connector DB."""
    conn = _db()
    try:
        run_id = _record_run(
            conn, "spotify",
            signals.get("source", "mock"),
            signals.get("success", True),
            signals.get("summary", ""),
        )
        conn.execute(
            """INSERT INTO spotify_snapshots
               (run_id, polled_at, mood, avg_valence, avg_energy,
                deep_work_session, session_minutes, source)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                run_id, time.time(),
                signals.get("mood"),
                signals.get("avg_valence"),
                signals.get("avg_energy"),
                int(bool(signals.get("deep_work_session"))),
                signals.get("session_minutes"),
                signals.get("source", "mock"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def record_discord(signals: dict) -> None:
    """Persist a Discord snapshot to the connector DB."""
    conn = _db()
    try:
        run_id = _record_run(
            conn, "discord",
            signals.get("source", "mock"),
            signals.get("success", True),
            signals.get("summary", ""),
        )
        conn.execute(
            """INSERT INTO discord_snapshots
               (run_id, polled_at, unread_count, mention_count,
                oldest_unread_hours, source)
               VALUES (?,?,?,?,?,?)""",
            (
                run_id, time.time(),
                signals.get("unread_count"),
                signals.get("mention_count"),
                signals.get("oldest_unread_hours"),
                signals.get("source", "mock"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def record_nudge(nudge_type: str, message: str, surfaced: bool = True,
                 platform: str = "discord") -> None:
    """Record a preemptive nudge (sent or suppressed)."""
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO preemptive_nudges "
            "(generated_at, nudge_type, message, surfaced, platform) VALUES (?,?,?,?,?)",
            (time.time(), nudge_type, message, int(surfaced), platform),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Read: latest snapshot + history
# ---------------------------------------------------------------------------

_LATEST_QUERIES: dict[str, str] = {
    "strava": """
        SELECT s.*, r.polled_at as run_polled_at
        FROM strava_snapshots s
        JOIN connector_runs r ON r.id = s.run_id
        ORDER BY s.polled_at DESC LIMIT 1
    """,
    "apple_health": """
        SELECT s.*, r.polled_at as run_polled_at
        FROM apple_health_snapshots s
        JOIN connector_runs r ON r.id = s.run_id
        ORDER BY s.polled_at DESC LIMIT 1
    """,
    "todoist": """
        SELECT s.*, r.polled_at as run_polled_at
        FROM todoist_snapshots s
        JOIN connector_runs r ON r.id = s.run_id
        ORDER BY s.polled_at DESC LIMIT 1
    """,
    "spotify": """
        SELECT s.*, r.polled_at as run_polled_at
        FROM spotify_snapshots s
        JOIN connector_runs r ON r.id = s.run_id
        ORDER BY s.polled_at DESC LIMIT 1
    """,
    "discord": """
        SELECT s.*, r.polled_at as run_polled_at
        FROM discord_snapshots s
        JOIN connector_runs r ON r.id = s.run_id
        ORDER BY s.polled_at DESC LIMIT 1
    """,
}

_HISTORY_QUERIES: dict[str, str] = {
    "strava": """
        SELECT s.polled_at, s.days_since_last_activity, s.last_activity_type,
               s.last_activity_date, s.weekly_run_km, s.weekly_vs_4w_avg,
               s.gap_threshold_exceeded, s.source
        FROM strava_snapshots s
        ORDER BY s.polled_at DESC LIMIT ?
    """,
    "apple_health": """
        SELECT s.polled_at, s.health_date, s.sleep_quality, s.sleep_hours,
               s.recovery_status, s.low_hrv, s.high_rhr, s.steps, s.source
        FROM apple_health_snapshots s
        ORDER BY s.polled_at DESC LIMIT ?
    """,
    "todoist": """
        SELECT s.polled_at, s.total, s.overdue_count, s.due_today_count,
               s.heavy_day, s.clear_day, s.top_tasks, s.source
        FROM todoist_snapshots s
        ORDER BY s.polled_at DESC LIMIT ?
    """,
    "spotify": """
        SELECT s.polled_at, s.mood, s.avg_valence, s.avg_energy,
               s.deep_work_session, s.session_minutes, s.source
        FROM spotify_snapshots s
        ORDER BY s.polled_at DESC LIMIT ?
    """,
    "discord": """
        SELECT s.polled_at, s.unread_count, s.mention_count,
               s.oldest_unread_hours, s.source
        FROM discord_snapshots s
        ORDER BY s.polled_at DESC LIMIT ?
    """,
}


def get_latest(connector: str) -> Optional[dict]:
    """Return the most recent snapshot for a connector, or None."""
    query = _LATEST_QUERIES.get(connector)
    if not query:
        return None
    conn = _db()
    try:
        row = conn.execute(query).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_history(connector: str, limit: int = 10) -> list[dict]:
    """Return the most recent `limit` snapshots for a connector."""
    query = _HISTORY_QUERIES.get(connector)
    if not query:
        return []
    conn = _db()
    try:
        rows = conn.execute(query, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_run_counts() -> dict[str, int]:
    """Return poll count per connector (for the status overview)."""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT connector, COUNT(*) as cnt FROM connector_runs GROUP BY connector"
        ).fetchall()
        return {r["connector"]: r["cnt"] for r in rows}
    finally:
        conn.close()


def get_latest_run(connector: str) -> Optional[dict]:
    """Return the most recent connector_runs row for a connector."""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT * FROM connector_runs WHERE connector=? ORDER BY polled_at DESC LIMIT 1",
            (connector,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_nudge_history(limit: int = 20) -> list[dict]:
    """Return the most recent preemptive nudges."""
    conn = _db()
    try:
        rows = conn.execute(
            "SELECT * FROM preemptive_nudges ORDER BY generated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
