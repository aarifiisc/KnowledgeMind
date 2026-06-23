"""
kg/connector_schema.py
----------------------
SQLite schema for connector snapshots (Strava, Apple Health, Todoist, Spotify,
Discord).  Lives in a separate database file (connectors.db) from the main
knowledgemind.db so the two concerns stay independent.

Every poll by a hermes_tool writes a row to connector_runs (the master log)
and a detail row to the connector-specific snapshot table.  The UI reads from
both to render status cards and history tables.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_BUSY_TIMEOUT_MS: int = 3000

CONNECTOR_SCHEMA_SQL: str = """
-- Master log: one row per connector poll attempt
CREATE TABLE IF NOT EXISTS connector_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    connector   TEXT    NOT NULL,   -- 'strava'|'apple_health'|'todoist'|'spotify'|'discord'
    polled_at   REAL    NOT NULL,   -- Unix timestamp
    source      TEXT    NOT NULL,   -- 'live'|'mock'
    success     INTEGER NOT NULL,   -- 1=ok, 0=error
    summary     TEXT                -- one-liner from derive_*_signals()
);

-- Strava fitness signals
CREATE TABLE IF NOT EXISTS strava_snapshots (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                   INTEGER REFERENCES connector_runs(id),
    polled_at                REAL    NOT NULL,
    days_since_last_activity INTEGER,
    last_activity_type       TEXT,
    last_activity_date       TEXT,   -- YYYY-MM-DD
    weekly_run_km            REAL,
    weekly_vs_4w_avg         REAL,
    gap_threshold_exceeded   INTEGER,
    source                   TEXT
);

-- Apple Health derived signals
CREATE TABLE IF NOT EXISTS apple_health_snapshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           INTEGER REFERENCES connector_runs(id),
    polled_at        REAL    NOT NULL,
    health_date      TEXT,           -- YYYY-MM-DD the reading is for
    sleep_quality    TEXT,           -- 'poor'|'fair'|'good'|'unknown'
    sleep_hours      REAL,
    recovery_status  TEXT,           -- 'low'|'moderate'|'good'|'unknown'
    low_hrv          INTEGER,        -- 0/1
    high_rhr         INTEGER,        -- 0/1
    steps            INTEGER,
    source           TEXT
);

-- Todoist task-load signals
CREATE TABLE IF NOT EXISTS todoist_snapshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           INTEGER REFERENCES connector_runs(id),
    polled_at        REAL    NOT NULL,
    total            INTEGER,
    overdue_count    INTEGER,
    due_today_count  INTEGER,
    heavy_day        INTEGER,        -- 0/1
    clear_day        INTEGER,        -- 0/1
    top_tasks        TEXT,           -- JSON list of task title strings
    source           TEXT
);

-- Spotify mood signals
CREATE TABLE IF NOT EXISTS spotify_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            INTEGER REFERENCES connector_runs(id),
    polled_at         REAL    NOT NULL,
    mood              TEXT,
    avg_valence       REAL,
    avg_energy        REAL,
    deep_work_session INTEGER,       -- 0/1
    session_minutes   REAL,
    source            TEXT
);

-- Discord unread / mention signals (populated by the Hermes gateway adapter)
CREATE TABLE IF NOT EXISTS discord_snapshots (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id               INTEGER REFERENCES connector_runs(id),
    polled_at            REAL    NOT NULL,
    unread_count         INTEGER,
    mention_count        INTEGER,
    oldest_unread_hours  REAL,
    source               TEXT
);

-- Preemptive nudges generated (for audit / noise tracking)
CREATE TABLE IF NOT EXISTS preemptive_nudges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at REAL   NOT NULL,
    nudge_type  TEXT    NOT NULL,   -- 'fitness'|'tasks'|'deep_work'|'communication'|'mood'
    message     TEXT    NOT NULL,
    surfaced    INTEGER NOT NULL DEFAULT 1,   -- 1=sent, 0=suppressed
    platform    TEXT    NOT NULL DEFAULT 'discord'
);

CREATE INDEX IF NOT EXISTS idx_runs_connector  ON connector_runs (connector, polled_at DESC);
CREATE INDEX IF NOT EXISTS idx_strava_polled   ON strava_snapshots (polled_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_polled   ON apple_health_snapshots (polled_at DESC);
CREATE INDEX IF NOT EXISTS idx_todoist_polled  ON todoist_snapshots (polled_at DESC);
CREATE INDEX IF NOT EXISTS idx_spotify_polled  ON spotify_snapshots (polled_at DESC);
CREATE INDEX IF NOT EXISTS idx_discord_polled  ON discord_snapshots (polled_at DESC);
CREATE INDEX IF NOT EXISTS idx_nudges_time     ON preemptive_nudges (generated_at DESC);
"""


def init_connector_db(path: str) -> sqlite3.Connection:
    """
    Create (or open) the connector database at `path`, apply the schema
    idempotently, and return an open connection.
    """
    db_file = Path(path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(CONNECTOR_SCHEMA_SQL)
    conn.commit()
    return conn


def get_connector_db_connection(path: str) -> sqlite3.Connection:
    return init_connector_db(path)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "connectors.db")
        conn = init_connector_db(path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        conn.close()

        expected = {
            "connector_runs", "strava_snapshots", "apple_health_snapshots",
            "todoist_snapshots", "spotify_snapshots", "discord_snapshots",
            "preemptive_nudges",
        }
        missing = expected - set(tables)
        assert not missing, f"Missing tables: {missing}"
        print(f"=> tables: {', '.join(sorted(tables))}")
    print("All kg/connector_schema.py smoke tests passed.")
