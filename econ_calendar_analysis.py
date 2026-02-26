"""
Economic Calendar LLM analysis generation with caching.
Purpose: Generate theory/dynamics blurbs per event, cache in econ_event_analysis table.
Author: Kevin Lefebvre
Last Updated: 2026-02-22
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from econ_calendar_db import DB_PATH, get_connection


# ---------------------------------------------------------------------------
# Event classification helpers
# ---------------------------------------------------------------------------

_SPEECH_HOLIDAY_PATTERNS = re.compile(
    r"\b(speech|speaks|remarks|testify|testimony|holiday|bank holiday|celebration|"
    r"day off|market closed|president|chair|governor|minister)\b",
    re.IGNORECASE,
)

_MACRO_INDICATOR_MAP = {
    "cpi": "CPI",
    "consumer price": "CPI",
    "ppi": "PPI",
    "producer price": "PPI",
    "jobless claims": "jobless claims",
    "initial claims": "jobless claims",
    "unemployment claims": "jobless claims",
    "consumer confidence": "consumer confidence",
    "cb consumer confidence": "consumer confidence",
    "michigan": "consumer confidence",
}

_MACRO_BEGINNER_LINES: dict[str, str] = {
    "CPI": (
        "Higher CPI prints typically push bond yields up and the USD higher "
        "as markets price in tighter Fed policy; a softer print does the opposite."
    ),
    "PPI": (
        "PPI is a leading indicator of consumer inflation; a hotter reading "
        "tends to lift yields and USD while pressuring fixed income prices."
    ),
    "jobless claims": (
        "Rising claims signal labour market softening, which can ease rate-hike "
        "expectations, compress yields, and weaken the USD."
    ),
    "consumer confidence": (
        "Strong confidence boosts spending expectations, supporting risk assets "
        "and USD while a miss can flatten or invert the yield curve."
    ),
}


def _classify_event(title: str) -> tuple[bool, Optional[str]]:
    """
    Return (is_speech_or_holiday, macro_indicator_key).

    Args:
        title: Event title string.

    Returns:
        Tuple of a bool flag and an optional macro indicator label.
    """
    is_speech_holiday = bool(_SPEECH_HOLIDAY_PATTERNS.search(title))
    indicator = None
    lower = title.lower()
    for pattern, label in _MACRO_INDICATOR_MAP.items():
        if pattern in lower:
            indicator = label
            break
    return is_speech_holiday, indicator


def _strip_hyphens(text: str) -> str:
    """
    Replace isolated hyphens used as em-dash separators with commas or parentheses.

    Rules:
    - ' - ' between clauses → ', '
    - Leading '- ' on a line → empty (bullet artifact)
    - Trailing ' -' → empty

    Args:
        text: Raw generated text.

    Returns:
        Post-processed text.
    """
    # em-dash variants with spaces
    text = re.sub(r"\s+[–—]\s+", ", ", text)
    # mid-word hyphen separating two phrases: space-hyphen-space
    text = re.sub(r" - ", ", ", text)
    # leading bullet hyphen
    text = re.sub(r"^-\s+", "", text, flags=re.MULTILINE)
    # trailing hanging hyphen
    text = re.sub(r"\s+-$", "", text, flags=re.MULTILINE)
    return text.strip()


def _trim_to_lines(text: str, max_lines: int = 6) -> str:
    """
    Truncate text to at most max_lines non-empty lines.

    Args:
        text: Multi-line text block.
        max_lines: Maximum lines to keep.

    Returns:
        Trimmed text.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines[:max_lines])


# ---------------------------------------------------------------------------
# Context hash
# ---------------------------------------------------------------------------

def compute_context_hash(rollup_json: Optional[dict]) -> str:
    """
    Compute a short SHA-256 hex digest over the rollup sections used as LLM context.

    Incorporates: tldr, forward_risks, executive_snapshot.
    Also handles the ``{"_ctx": {"context_hash": ...}}`` shell format produced by
    the on-demand callback — returns the pre-computed hash directly in that case.
    An empty or missing rollup gets the digest of an empty string.

    Args:
        rollup_json: Parsed rollup dict, context shell, or None.

    Returns:
        12-character hex digest.
    """
    if not rollup_json:
        return hashlib.sha256(b"").hexdigest()[:12]

    # Shell format: use the pre-computed hash stored in the shell
    if "_ctx" in rollup_json:
        ctx_payload = rollup_json["_ctx"]
        if isinstance(ctx_payload, dict) and ctx_payload.get("context_hash"):
            return ctx_payload["context_hash"][:12]
        return hashlib.sha256(b"").hexdigest()[:12]

    sections = rollup_json.get("sections", {})
    parts: list[str] = []

    def _extract_texts(items) -> list[str]:
        if isinstance(items, list):
            return [
                (i.get("text", "") if isinstance(i, dict) else str(i))
                for i in items
            ]
        return []

    parts += _extract_texts(sections.get("tldr", []))
    parts += _extract_texts(sections.get("forward_risks", []))
    parts += _extract_texts(sections.get("executive_snapshot", []))

    fw = sections.get("forward_watch", {})
    if isinstance(fw, dict):
        for items in fw.values():
            parts += _extract_texts(items)

    payload = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a concise financial educator. Write clear, plain-English explanations "
    "of macroeconomic events aimed at intermediate traders. Avoid political commentary. "
    "Never mention specific politicians or parties by name. Use neutral, factual language only. "
    "Keep each response to a maximum of 6 lines."
)


def _build_theory_prompt(
    title: str,
    country: Optional[str],
    currency: Optional[str],
    is_speech_holiday: bool,
    indicator: Optional[str],
) -> str:
    """Build the theory explainer prompt for one event."""
    ctx_parts = []
    if country:
        ctx_parts.append(f"Country/Region: {country}")
    if currency:
        ctx_parts.append(f"Currency: {currency}")
    context_line = ("  " + "  ".join(ctx_parts)) if ctx_parts else ""

    base = (
        f"Economic event: {title}\n"
        f"{context_line}\n\n"
        "Write a brief Theory explainer (max 6 lines) covering:\n"
        "- What this event or indicator measures\n"
        "- Why it matters to financial markets\n"
        "- What a high vs low reading (or hawkish vs dovish tone) typically implies\n"
    )

    if is_speech_holiday:
        base += (
            "\nIMPORTANT: For speeches and holidays, state clearly that "
            "market reaction depends on the actual content and current positioning, "
            "and that no directional assumption can be made in advance.\n"
        )

    if indicator:
        base += (
            f"\nAdd one beginner-level sentence linking {indicator} releases "
            "to bond yields and USD direction.\n"
        )

    return base


def _build_dynamics_prompt(
    title: str,
    country: Optional[str],
    is_speech_holiday: bool,
    indicator: Optional[str],
    rollup_context: str,
) -> str:
    """Build the dynamics explainer prompt using rollup context."""
    ctx = rollup_context.strip() if rollup_context else ""
    base = (
        f"Economic event: {title}\n"
        f"{'Country: ' + country if country else ''}\n\n"
        "Current macro context from today's research digest:\n"
        f"---\n{ctx if ctx else '(No context available.)'}\n---\n\n"
        "Write a brief Dynamics explainer (max 6 lines) covering:\n"
        "- How today's macro backdrop could amplify or dampen this event's impact\n"
        "- Which asset classes or currencies are most likely to react\n"
        "- One specific scenario to watch (if context is available)\n"
    )

    if not ctx:
        base += (
            "\nSince no current rollup context is available, "
            "note this briefly and fall back to general theory-based dynamics.\n"
        )

    if is_speech_holiday:
        base += (
            "\nFor speeches and holidays, state that the reaction depends entirely "
            "on content and market positioning; avoid directional claims.\n"
        )

    if indicator:
        base += (
            f"\nInclude one beginner-level sentence linking {indicator} to "
            "bond yields and USD direction given current conditions.\n"
        )

    return base


# ---------------------------------------------------------------------------
# Cache read / write
# ---------------------------------------------------------------------------

def _load_cached_analysis(
    db_path,
    event_id: str,
    as_of_date: str,
    context_hash: str,
) -> Optional[dict]:
    """
    Return cached analysis row if event_id + as_of_date + context_hash match.

    Args:
        db_path: SQLite path.
        event_id: UUID of the econ_event row.
        as_of_date: ISO date string.
        context_hash: 12-char hash of rollup context.

    Returns:
        Dict with theory_text and dynamics_text, or None.
    """
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT theory_text, dynamics_text FROM econ_event_analysis "
            "WHERE event_id = ? AND as_of_date = ? AND context_hash = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (event_id, as_of_date, context_hash),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _store_analysis(
    db_path,
    event_id: str,
    as_of_date: str,
    theory_text: str,
    dynamics_text: str,
    context_hash: str,
) -> None:
    """
    Persist a new analysis row. Deletes older rows for same event + date first.

    Args:
        db_path: SQLite path.
        event_id: UUID of the econ_event row.
        as_of_date: ISO date string.
        theory_text: Generated theory blurb.
        dynamics_text: Generated dynamics blurb.
        context_hash: 12-char hash used for cache keying.
    """
    conn = get_connection(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        # Remove stale rows for this event / date (keep storage tidy)
        conn.execute(
            "DELETE FROM econ_event_analysis WHERE event_id = ? AND as_of_date = ?",
            (event_id, as_of_date),
        )
        conn.execute(
            "INSERT INTO econ_event_analysis "
            "(id, event_id, as_of_date, theory_text, dynamics_text, context_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                event_id,
                as_of_date,
                theory_text,
                dynamics_text,
                context_hash,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Rollup context extractor
# ---------------------------------------------------------------------------

def extract_rollup_context(rollup_json: Optional[dict]) -> str:
    """
    Pull TLDR, forward risks, and executive snapshot from rollup JSON.

    Also handles the lightweight ``{"_ctx": {"context_text": ..., "context_hash": ...}}``
    shell format produced by the on-demand panel callback, returning the pre-extracted
    context text directly.

    Args:
        rollup_json: Parsed rollup dict, context shell, or None.

    Returns:
        Concatenated plain-text context block (max ~900 chars).
    """
    if not rollup_json:
        return ""

    # Shell format from on-demand callback
    if "_ctx" in rollup_json:
        ctx_payload = rollup_json["_ctx"]
        if isinstance(ctx_payload, dict):
            return (ctx_payload.get("context_text") or "")[:900]
        return ""

    sections = rollup_json.get("sections", {})
    lines: list[str] = []

    def _grab(items, label: str) -> None:
        if not items:
            return
        lines.append(f"[{label}]")
        for item in items[:4]:
            text = item.get("text", str(item)) if isinstance(item, dict) else str(item)
            lines.append(f"  {text[:200]}")

    _grab(sections.get("executive_snapshot", []), "Top Insights")
    _grab(sections.get("tldr", []), "TLDR")
    _grab(sections.get("forward_risks", []), "Forward Risks")

    raw = "\n".join(lines)
    return raw[:900]  # cap to keep prompts lean


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def generate_event_analysis(
    event: dict,
    as_of_date: str,
    rollup_json: Optional[dict],
    db_path=None,
    model: str = "gpt-4o-mini",
    theory_only: bool = False,
) -> dict:
    """
    Return theory_text (and optionally dynamics_text) for one event.

    Uses the cache when a matching row exists.  When ``theory_only=True`` only
    the Theory prompt is sent to the LLM; Dynamics is returned as an empty string
    and the row is NOT stored (so a later full call can still populate it).

    Args:
        event: Event dict from get_events_for_date (must have 'id', 'title', etc.).
        as_of_date: ISO date string for the date being rendered.
        rollup_json: Parsed rollup JSON, context shell, or None.
        db_path: Override SQLite path; None for default.
        model: OpenAI model name.
        theory_only: When True, skip Dynamics generation entirely.

    Returns:
        Dict with keys 'theory_text', 'dynamics_text', 'from_cache' (bool),
        'no_context' (bool).
    """
    if db_path is None:
        db_path = DB_PATH

    event_id: str = event["id"]
    title: str = event.get("title", "Unknown Event")
    country: Optional[str] = event.get("country_or_region")
    currency: Optional[str] = event.get("currency_tag")

    is_speech_holiday, indicator = _classify_event(title)
    context_hash = compute_context_hash(rollup_json)
    has_context = bool(rollup_json)

    # ── Cache hit ──────────────────────────────────────────────────────────
    cached = _load_cached_analysis(db_path, event_id, as_of_date, context_hash)
    if cached:
        result = {
            "theory_text": cached["theory_text"],
            "dynamics_text": cached["dynamics_text"] if not theory_only else "",
            "from_cache": True,
            "no_context": not has_context,
        }
        return result

    # ── LLM client ────────────────────────────────────────────────────────
    try:
        from openai_client import get_client  # lazy import – avoids circular deps
        client = get_client()
    except ImportError:
        # OpenAI module not installed
        return {
            "theory_text": "Analysis requires OpenAI module. Install with: pip install openai",
            "dynamics_text": "" if theory_only else "Analysis requires OpenAI module. Install with: pip install openai",
            "from_cache": False,
            "no_context": not has_context,
        }
    except Exception as e:
        error_note = f"Analysis unavailable: {e}"
        return {
            "theory_text": error_note,
            "dynamics_text": "" if theory_only else error_note,
            "from_cache": False,
            "no_context": not has_context,
        }

    rollup_context = extract_rollup_context(rollup_json)

    def _call(prompt: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.4,
        )
        raw = resp.choices[0].message.content or ""
        return _strip_hyphens(_trim_to_lines(raw, 6))

    # ── Theory ────────────────────────────────────────────────────────────
    theory_prompt = _build_theory_prompt(
        title, country, currency, is_speech_holiday, indicator
    )
    theory_text = _call(theory_prompt)
    theory_text = _strip_hyphens(theory_text)

    # ── Dynamics (skipped when theory_only) ───────────────────────────────
    if theory_only:
        # Do not persist — a later Dynamics expand will complete the row.
        return {
            "theory_text": theory_text,
            "dynamics_text": "",
            "from_cache": False,
            "no_context": not has_context,
        }

    dynamics_prompt = _build_dynamics_prompt(
        title, country, is_speech_holiday, indicator, rollup_context
    )
    dynamics_text = _call(dynamics_prompt)

    if not has_context:
        no_ctx_note = "(No current rollup context was available; dynamics are theory-based only.)"
        dynamics_text = f"{no_ctx_note}\n{dynamics_text}"
        dynamics_text = _trim_to_lines(dynamics_text, 6)

    dynamics_text = _strip_hyphens(dynamics_text)

    # ── Persist full row ───────────────────────────────────────────────────
    _store_analysis(db_path, event_id, as_of_date, theory_text, dynamics_text, context_hash)

    return {
        "theory_text": theory_text,
        "dynamics_text": dynamics_text,
        "from_cache": False,
        "no_context": not has_context,
    }

