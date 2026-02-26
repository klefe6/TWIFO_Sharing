"""
Purpose: Stable SHA-256 hashing utilities for economic calendar events and rollup context.
Author: Kevin Lefebvre
Last Updated: 2026-02-22
"""

from __future__ import annotations

import hashlib
import json


def compute_events_hash(events: list) -> str:
    """
    Derive a stable SHA-256 hash from a normalised economic event list.

    Only the fields that define event identity are included: time_local
    (or the literal "all_day" when absent), stripped/lowercased title,
    currency_tag, and country_or_region.  Events are sorted by time_local
    before serialisation so insertion order does not affect the result.

    Args:
        events: List of event dicts (or objects with matching attributes).
                Accepts both plain dicts and objects that expose fields as
                attributes (e.g. ParsedEvent instances).

    Returns:
        Lowercase hex SHA-256 digest string.
    """

    def _field(evt: object, key: str):
        """Read a field from a dict or an attribute-bearing object."""
        return evt[key] if isinstance(evt, dict) else getattr(evt, key, None)

    normalised = []
    for evt in events:
        time_local = _field(evt, "time_local")
        normalised.append(
            {
                "time_local": time_local if time_local else "all_day",
                "title": (_field(evt, "title") or "").strip().lower(),
                "currency_tag": _field(evt, "currency_tag"),
                "country_or_region": _field(evt, "country_or_region"),
            }
        )

    # Sort by normalised time_local so order is deterministic
    normalised.sort(key=lambda e: e["time_local"])

    payload = json.dumps(normalised, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_context_hash(rollup_text: str | None) -> str:
    """
    Derive a stable SHA-256 hash from rollup context text.

    Returns the sentinel string ``"no_rollup_context"`` when the input is
    None or empty so callers can reliably detect a missing context without
    special-casing None.  No timestamps or metadata are included in the
    hash input — only the stripped text content.

    Args:
        rollup_text: Raw rollup/context string, or None.

    Returns:
        Lowercase hex SHA-256 digest, or ``"no_rollup_context"``.
    """
    if not rollup_text or not rollup_text.strip():
        return "no_rollup_context"

    payload = rollup_text.strip()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

