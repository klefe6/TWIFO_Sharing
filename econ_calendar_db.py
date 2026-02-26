"""
Economic Calendar SQLite database layer.
Purpose: Create and manage schema for weekly economic calendar events.
Author: Kevin Lefebvre
Last Updated: 2026-02-22
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "twifo_econ.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS econ_week (
    id              TEXT PRIMARY KEY,
    week_start_date TEXT NOT NULL,
    week_end_date   TEXT NOT NULL,
    raw_text        TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS econ_event (
    id                TEXT PRIMARY KEY,
    week_id           TEXT NOT NULL REFERENCES econ_week(id) ON DELETE CASCADE,
    event_date        TEXT NOT NULL,
    time_local        TEXT,
    all_day           INTEGER NOT NULL DEFAULT 0,
    country_or_region TEXT,
    currency_tag      TEXT,
    title             TEXT NOT NULL,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS econ_event_analysis (
    id              TEXT PRIMARY KEY,
    event_id        TEXT NOT NULL REFERENCES econ_event(id) ON DELETE CASCADE,
    as_of_date      TEXT NOT NULL,
    theory_text     TEXT,
    dynamics_text   TEXT,
    context_hash    TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS econ_daily_rank (
    date_iso     TEXT PRIMARY KEY,
    context_hash TEXT,
    events_hash  TEXT,
    rank_json    TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS econ_daily_brief (
    date_iso       TEXT PRIMARY KEY,
    context_hash   TEXT,
    events_hash    TEXT,
    theory_text    TEXT,
    dynamics_text  TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_event_week   ON econ_event(week_id);
CREATE INDEX IF NOT EXISTS idx_event_date   ON econ_event(event_date);
CREATE INDEX IF NOT EXISTS idx_analysis_evt ON econ_event_analysis(event_id);
"""


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """
    Open a connection and ensure schema exists.

    Args:
        db_path: Override path to SQLite file. Defaults to data/twifo_econ.db.

    Returns:
        sqlite3.Connection with row_factory set to sqlite3.Row.
    """
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA_SQL)
    return conn

