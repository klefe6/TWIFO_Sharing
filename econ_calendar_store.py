"""
Economic Calendar storage operations.
Purpose: Upsert parsed weekly calendars and query events by date.
Author: Kevin Lefebvre
Last Updated: 2026-02-22
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from econ_calendar_db import DB_PATH, get_connection
from econ_calendar_parser import ParsedEvent


def _now_iso() -> str:
    """UTC ISO-8601 timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


def upsert_week_and_events(
    db_path: str | Path | None,
    week_start: str,
    week_end: str,
    raw_text: str,
    events: list[ParsedEvent],
) -> str:
    """
    Store (or replace) a week and its events.

    If a week with the same start/end dates already exists, its events
    are deleted and re-inserted. The raw_text and created_at are updated.

    Args:
        db_path: Path to SQLite file, or None for default.
        week_start: ISO date for week start.
        week_end: ISO date for week end.
        raw_text: Original pasted text block.
        events: List of ParsedEvent objects from the parser.

    Returns:
        The week id (existing or newly created).
    """
    conn = get_connection(db_path)
    now = _now_iso()

    try:
        cur = conn.cursor()

        # Check for existing week with same date range
        row = cur.execute(
            "SELECT id FROM econ_week WHERE week_start_date = ? AND week_end_date = ?",
            (week_start, week_end),
        ).fetchone()

        if row:
            week_id = row["id"]
            # Update raw text and timestamp
            cur.execute(
                "UPDATE econ_week SET raw_text = ?, created_at = ? WHERE id = ?",
                (raw_text, now, week_id),
            )
            # Remove old events (cascade deletes analyses too)
            cur.execute("DELETE FROM econ_event WHERE week_id = ?", (week_id,))
        else:
            week_id = _new_id()
            cur.execute(
                "INSERT INTO econ_week (id, week_start_date, week_end_date, raw_text, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (week_id, week_start, week_end, raw_text, now),
            )

        # Insert events
        for evt in events:
            cur.execute(
                "INSERT INTO econ_event "
                "(id, week_id, event_date, time_local, all_day, "
                "country_or_region, currency_tag, title, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _new_id(),
                    week_id,
                    evt.event_date,
                    evt.time_local,
                    1 if evt.all_day else 0,
                    evt.country_or_region,
                    evt.currency_tag,
                    evt.title,
                    now,
                ),
            )

        conn.commit()
        return week_id

    finally:
        conn.close()


def get_events_for_date(
    db_path: str | Path | None,
    date_iso: str,
) -> list[dict]:
    """
    Return events for a given date, ordered by all_day desc, time asc, id asc.

    All-day events appear first (all_day=1 sorts higher), then timed events
    in chronological order.

    Args:
        db_path: Path to SQLite file, or None for default.
        date_iso: ISO date string YYYY-MM-DD.

    Returns:
        List of dicts with event fields.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, week_id, event_date, time_local, all_day, "
            "       country_or_region, currency_tag, title, created_at "
            "FROM econ_event "
            "WHERE event_date = ? "
            "ORDER BY all_day DESC, "
            "         CASE WHEN time_local IS NULL THEN '' ELSE time_local END ASC, "
            "         id ASC",
            (date_iso,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_weeks_in_range(
    db_path: str | Path | None,
    from_date: str,
    to_date: str,
) -> list[dict]:
    """
    Return weeks overlapping the given date range.

    Args:
        db_path: Path to SQLite file, or None for default.
        from_date: ISO date lower bound.
        to_date: ISO date upper bound.

    Returns:
        List of dicts with week fields (without raw_text for brevity).
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, week_start_date, week_end_date, created_at "
            "FROM econ_week "
            "WHERE week_end_date >= ? AND week_start_date <= ? "
            "ORDER BY week_start_date ASC",
            (from_date, to_date),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_week_raw_text(
    db_path: str | Path | None,
    week_id: str,
) -> Optional[str]:
    """
    Retrieve the raw pasted text for a stored week.

    Args:
        db_path: Path to SQLite file, or None for default.
        week_id: UUID of the week record.

    Returns:
        The raw_text string, or None if week not found.
    """
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT raw_text FROM econ_week WHERE id = ?",
            (week_id,),
        ).fetchone()
        return row["raw_text"] if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# econ_daily_rank helpers
# ---------------------------------------------------------------------------


def get_daily_rank(
    db_path: str | Path | None,
    date_iso: str,
) -> Optional[dict]:
    """
    Fetch the cached daily rank row for a given date.

    Args:
        db_path: Path to SQLite file, or None for default.
        date_iso: ISO date string YYYY-MM-DD.

    Returns:
        Dict with all row fields, or None if no row exists.
    """
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT date_iso, context_hash, events_hash, rank_json, created_at "
            "FROM econ_daily_rank WHERE date_iso = ?",
            (date_iso,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_daily_rank(
    db_path: str | Path | None,
    date_iso: str,
    context_hash: str,
    events_hash: str,
    rank_json: str,
) -> None:
    """
    Insert or replace the daily rank record for a given date.

    Args:
        db_path: Path to SQLite file, or None for default.
        date_iso: ISO date string YYYY-MM-DD (primary key).
        context_hash: Hash of the rollup context used to generate the rank.
        events_hash: Hash of the events list used to generate the rank.
        rank_json: JSON-serialised rank payload.
    """
    conn = get_connection(db_path)
    now = _now_iso()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO econ_daily_rank "
            "(date_iso, context_hash, events_hash, rank_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (date_iso, context_hash, events_hash, rank_json, now),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# econ_daily_brief helpers
# ---------------------------------------------------------------------------


def get_daily_brief(
    db_path: str | Path | None,
    date_iso: str,
) -> Optional[dict]:
    """
    Fetch the cached daily brief row for a given date.

    Args:
        db_path: Path to SQLite file, or None for default.
        date_iso: ISO date string YYYY-MM-DD.

    Returns:
        Dict with all row fields, or None if no row exists.
    """
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT date_iso, context_hash, events_hash, "
            "       theory_text, dynamics_text, created_at "
            "FROM econ_daily_brief WHERE date_iso = ?",
            (date_iso,),
        ).fetchone()
        result = dict(row) if row else None
        if result:
            print(f"[ECON STORE] get_daily_brief: date_key={date_iso} FOUND, theory_len={len(result.get('theory_text', ''))}")
        else:
            print(f"[ECON STORE] get_daily_brief: date_key={date_iso} NOT FOUND")
        return result
    finally:
        conn.close()


def upsert_daily_brief(
    db_path: str | Path | None,
    date_iso: str,
    context_hash: str,
    events_hash: str,
    theory_text: str,
    dynamics_text: str,
) -> None:
    """
    Insert or replace the daily brief record for a given date.

    Args:
        db_path: Path to SQLite file, or None for default.
        date_iso: ISO date string YYYY-MM-DD (primary key).
        context_hash: Hash of the rollup context used to generate the brief.
        events_hash: Hash of the events list used to generate the brief.
        theory_text: Theory/background section of the brief.
        dynamics_text: Current dynamics section of the brief.
    """
    print(f"[ECON STORE] upsert_daily_brief: date_key={date_iso}, theory_len={len(theory_text)}, dynamics_len={len(dynamics_text)}")
    conn = get_connection(db_path)
    now = _now_iso()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO econ_daily_brief "
            "(date_iso, context_hash, events_hash, theory_text, dynamics_text, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (date_iso, context_hash, events_hash, theory_text, dynamics_text, now),
        )
        conn.commit()
        print(f"[ECON STORE] upsert_daily_brief COMMITTED: date_key={date_iso}")
    finally:
        conn.close()


def delete_week(
    db_path: str | Path | None,
    week_id: str,
) -> None:
    """
    Delete a week and all its events (cascade deletes analyses automatically).

    Args:
        db_path: Path to SQLite file, or None for default.
        week_id: UUID of the week to delete.
    """
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM econ_week WHERE id = ?", (week_id,))
        conn.commit()
    finally:
        conn.close()