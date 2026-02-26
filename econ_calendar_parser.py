"""
Economic Calendar text parser.
Purpose: Parse pasted weekly economic calendar blocks into structured events.
Author: Kevin Lefebvre
Last Updated: 2026-02-22
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedEvent:
    """Single economic calendar event."""
    event_date: str              # ISO YYYY-MM-DD
    time_local: Optional[str]    # HH:MM or None
    all_day: bool
    country_or_region: Optional[str]
    currency_tag: Optional[str]
    title: str


@dataclass
class ParsedWeek:
    """Result of parsing a weekly calendar block."""
    week_start_date: str         # ISO YYYY-MM-DD
    week_end_date: str           # ISO YYYY-MM-DD
    events: list[ParsedEvent] = field(default_factory=list)


# Regex for the week header: "Sunday, February 22 to Saturday, February 28, 2026"
_WEEK_HEADER_RE = re.compile(
    r"^(?:Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),\s+"
    r"(\w+ \d{1,2})\s+to\s+"
    r"(?:Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),\s+"
    r"(\w+ \d{1,2}),\s+(\d{4})$",
    re.IGNORECASE,
)

# Regex for a day header: "Monday, February 23, 2026"
_DAY_HEADER_RE = re.compile(
    r"^(?:Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),\s+"
    r"(\w+ \d{1,2}),\s+(\d{4})$",
    re.IGNORECASE,
)

# Lines to skip (section headers, blanks)
_SKIP_LINE_RE = re.compile(
    r"^(Notable|Key|Important|Economic|Data|Major|Releases|Events)",
    re.IGNORECASE,
)

# Trailing currency marker like EUR* or JPY* or CHINA*
_CURRENCY_TAG_RE = re.compile(r"\s+([A-Z]{3,5})\*\s*$")

# Time prefix like 10:00 or 21:30
_TIME_PREFIX_RE = re.compile(r"^(\d{1,2}:\d{2})\s+")

# Country prefix: "China - Chinese New Year" or "Japan - Emperor's Birthday"
_COUNTRY_DASH_RE = re.compile(r"^([A-Za-z.\s]+?)\s*[-–—]\s+(.+)$")

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_month_day_year(month_day: str, year: str) -> str:
    """Convert 'February 22' + '2026' to '2026-02-22'."""
    parts = month_day.strip().split()
    if len(parts) != 2:
        raise ValueError(f"Cannot parse month/day from '{month_day}'")
    month_name, day_str = parts
    month = _MONTH_MAP.get(month_name.lower())
    if month is None:
        raise ValueError(f"Unknown month '{month_name}'")
    return f"{year}-{month:02d}-{int(day_str):02d}"


def _parse_event_line(line: str, current_date: str, line_idx: int) -> ParsedEvent:
    """
    Parse a single event line within a day block.

    Args:
        line: Trimmed event line text.
        current_date: ISO date for the current day block.
        line_idx: Original 0-based line index for error reporting.

    Returns:
        ParsedEvent dataclass.

    Raises:
        ValueError: If the line cannot be parsed (includes line index).
    """
    remaining = line

    # Extract trailing currency tag (e.g. "EUR*", "CHINA*")
    currency_tag: Optional[str] = None
    m_currency = _CURRENCY_TAG_RE.search(remaining)
    if m_currency:
        currency_tag = m_currency.group(1)
        remaining = remaining[: m_currency.start()].rstrip()
        # Strip trailing separator dash left behind (e.g. "China - Holiday -")
        remaining = re.sub(r"\s*[-–—]\s*$", "", remaining)

    # Determine time vs all-day
    all_day = False
    time_local: Optional[str] = None

    if remaining.lower().startswith("all"):
        all_day = True
        remaining = remaining[3:].strip()
    else:
        m_time = _TIME_PREFIX_RE.match(remaining)
        if m_time:
            raw_time = m_time.group(1)
            # Normalize to HH:MM
            h, m = raw_time.split(":")
            time_local = f"{int(h):02d}:{m}"
            remaining = remaining[m_time.end():].strip()
        else:
            raise ValueError(
                f"Line {line_idx}: Event must start with 'All' or HH:MM, "
                f"got: '{line}'"
            )

    if not remaining:
        raise ValueError(f"Line {line_idx}: Empty event title after prefix in: '{line}'")

    # Extract country/region via dash pattern
    country_or_region: Optional[str] = None
    title = remaining

    m_country = _COUNTRY_DASH_RE.match(remaining)
    if m_country:
        candidate_country = m_country.group(1).strip()
        candidate_title = m_country.group(2).strip()
        # Only treat as country if the left side looks like a name (no digits)
        if candidate_country and not any(c.isdigit() for c in candidate_country):
            country_or_region = candidate_country
            title = candidate_title

    return ParsedEvent(
        event_date=current_date,
        time_local=time_local,
        all_day=all_day,
        country_or_region=country_or_region,
        currency_tag=currency_tag,
        title=title,
    )


def parse_week_block(
    raw_text: str,
    default_tz: str = "America/New_York",
) -> ParsedWeek:
    """
    Parse a pasted weekly economic calendar text block.

    Args:
        raw_text: Full pasted text with week header, day headers, and events.
        default_tz: Assumed timezone for event times (stored for reference).

    Returns:
        ParsedWeek with week_start_date, week_end_date, and events list.

    Raises:
        ValueError: With descriptive message and failing line index.
    """
    lines = raw_text.strip().splitlines()
    if not lines:
        raise ValueError("Empty input text. Expected week header like: "
                         "'Sunday, February 22 to Saturday, February 28, 2026'")

    # Pass 1: Find week header
    week_start: Optional[str] = None
    week_end: Optional[str] = None
    header_line_idx: Optional[int] = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        m = _WEEK_HEADER_RE.match(stripped)
        if m:
            year = m.group(3)
            week_start = _parse_month_day_year(m.group(1), year)
            week_end = _parse_month_day_year(m.group(2), year)
            header_line_idx = i
            break

    if week_start is None or week_end is None:
        raise ValueError(
            "Line 0: Week range header not detected. "
            "Expected format: 'Sunday, February 22 to Saturday, February 28, 2026'"
        )

    # Pass 2: Parse day blocks and events
    events: list[ParsedEvent] = []
    current_date: Optional[str] = None

    for i, line in enumerate(lines):
        if i <= header_line_idx:
            continue

        stripped = line.strip()
        if not stripped:
            continue

        # Skip known section headers
        if _SKIP_LINE_RE.match(stripped):
            continue

        # Check for day header
        m_day = _DAY_HEADER_RE.match(stripped)
        if m_day:
            current_date = _parse_month_day_year(m_day.group(1), m_day.group(2))
            continue

        # Must be an event line
        if current_date is None:
            raise ValueError(
                f"Line {i}: Event line found before any day header: '{stripped}'"
            )

        event = _parse_event_line(stripped, current_date, i)
        events.append(event)

    return ParsedWeek(
        week_start_date=week_start,
        week_end_date=week_end,
        events=events,
    )

