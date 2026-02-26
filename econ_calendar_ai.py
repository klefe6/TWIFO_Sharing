"""
Purpose: Daily-level AI generation for economic calendar: event ranking and daily briefs.
         All GPT/LLM calls for the econ calendar flow through this module only.
Author: Kevin Lefebvre
Last Updated: 2026-02-22
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from econ_calendar_db import DB_PATH
from econ_calendar_hashing import compute_context_hash, compute_events_hash
from econ_calendar_store import (
    get_daily_brief,
    get_daily_rank,
    get_events_for_date,
    upsert_daily_brief,
    upsert_daily_rank,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Use the project's standard model (same as summarize_pdf.py, rollup_aggregator.py, etc.)
_LLM_MODEL = "gpt-4o-mini"

# Fallback priority tiers used when the LLM response is invalid
_FALLBACK_TIERS: list[tuple[re.Pattern, str, int]] = [
    (re.compile(r"\bcpi\b|\bconsumer price\b", re.IGNORECASE), "high", 1),
    (re.compile(r"\bppi\b|\bproducer price\b", re.IGNORECASE), "high", 2),
    (re.compile(r"\bgdp\b", re.IGNORECASE), "high", 3),
    (re.compile(r"\bnfp\b|\bnon.?farm\b|\bpayroll\b", re.IGNORECASE), "high", 4),
    (re.compile(r"\bfomc\b|\brate decision\b|\binterest rate\b", re.IGNORECASE), "high", 5),
    (re.compile(r"\bjobless\b|\binitial claims\b|\bunemployment claims\b", re.IGNORECASE), "medium", 6),
    (re.compile(r"\bretail sales\b", re.IGNORECASE), "medium", 7),
    (re.compile(r"\bindustrial production\b|\bism\b|\bpmi\b", re.IGNORECASE), "medium", 8),
    (re.compile(r"\bconsumer confidence\b|\bmichigan\b", re.IGNORECASE), "medium", 9),
    (re.compile(r"\bspeech\b|\bspeaks\b|\bremarks\b|\btestimony\b", re.IGNORECASE), "low", 10),
    (re.compile(r"\bholiday\b|\bmarket closed\b|\bbank holiday\b", re.IGNORECASE), "low", 11),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_hyphens(text: str) -> str:
    """Replace hyphens used as separators; no hyphens in output."""
    text = re.sub(r"\s+[–—]\s+", ", ", text)
    text = re.sub(r" - ", ", ", text)
    text = re.sub(r"^-\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+-$", "", text, flags=re.MULTILINE)
    # Replace remaining standalone hyphens between words
    text = re.sub(r"(?<=\w)-(?=\w)", ", ", text)
    return text.strip()


def _event_key(event: dict) -> str:
    """Stable key used to cross-reference ranking output with events."""
    time_part = event.get("time_local") or "all_day"
    title_part = (event.get("title") or "").strip().lower()
    return f"{time_part}|{title_part}"


def _classify_event_type(title: str) -> str:
    """Return 'data_release', 'speech', or 'holiday'."""
    t = title.lower()
    if re.search(r"\bholiday\b|\bmarket closed\b|\bbank holiday\b", t):
        return "holiday"
    if re.search(r"\bspeech\b|\bspeaks\b|\bremarks\b|\btestimony\b|\bchair\b|\bgovernor\b", t):
        return "speech"
    return "data_release"


def _get_llm_client():
    """Return the singleton OpenAI-compatible client (lazy import)."""
    from openai_client import get_client  # noqa: PLC0415

    return get_client()


def _fallback_rank(events: list[dict]) -> list[dict]:
    """Build a deterministic ranking when LLM output is unusable."""
    ranked = []
    unmatched = []
    matched_keys: set[str] = set()

    for pat, tier, base_priority in _FALLBACK_TIERS:
        for evt in events:
            key = _event_key(evt)
            if key in matched_keys:
                continue
            if pat.search(evt.get("title", "")):
                ranked.append(
                    {
                        "event_key": key,
                        "priority": base_priority,
                        "importance_tier": tier,
                        "reason": "Fallback heuristic ranking.",
                    }
                )
                matched_keys.add(key)

    # Everything else goes at the end as low priority
    next_priority = len(ranked) + 1
    for evt in events:
        key = _event_key(evt)
        if key not in matched_keys:
            unmatched.append(
                {
                    "event_key": key,
                    "priority": next_priority,
                    "importance_tier": "low",
                    "reason": "Fallback heuristic ranking.",
                }
            )
            next_priority += 1

    # Re-number priorities sequentially
    all_ranked = ranked + unmatched
    for i, item in enumerate(all_ranked, start=1):
        item["priority"] = i
    return all_ranked


def _build_rank_prompt(date_iso: str, events: list[dict], macro_context_text: str) -> str:
    """Construct the ranking prompt."""
    event_lines = []
    for evt in events:
        key = _event_key(evt)
        time_display = evt.get("time_local") or "All Day"
        country = evt.get("country_or_region") or ""
        currency = evt.get("currency_tag") or ""
        title = evt.get("title") or ""
        meta = ", ".join(filter(None, [country, currency]))
        event_lines.append(f'  event_key="{key}" | {time_display} | {title} ({meta})')

    events_block = "\n".join(event_lines) or "  (no events)"
    ctx_block = macro_context_text.strip() if macro_context_text else "(No rollup context available.)"

    return (
        f"Date: {date_iso}\n\n"
        "Macro context from today's research digest:\n"
        f"---\n{ctx_block}\n---\n\n"
        "Economic events for this date:\n"
        f"{events_block}\n\n"
        "Rank each event by market importance for a US-focused futures/FX trader.\n"
        "Return ONLY valid JSON matching this exact schema — no markdown, no commentary:\n"
        "{\n"
        '  "ranked": [\n'
        "    {\n"
        '      "event_key": "<exact string from above>",\n'
        '      "priority": <integer starting at 1>,\n'
        '      "importance_tier": "high" | "medium" | "low",\n'
        '      "reason": "<one sentence>"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Every event_key listed above must appear exactly once. "
        "Do not add events. Do not use hyphens in reason text."
    )


def _build_brief_prompt(
    date_iso: str,
    events: list[dict],
    ranked: list[dict],
    macro_context_text: str,
    dynamics_mode: bool,
) -> str:
    """Construct the daily brief prompt ordered by ranking."""
    rank_map = {r["event_key"]: r for r in ranked}

    # Sort events by their rank priority
    def _priority(evt: dict) -> int:
        key = _event_key(evt)
        return rank_map.get(key, {}).get("priority", 999)

    sorted_events = sorted(events, key=_priority)

    ctx_block = macro_context_text.strip() if macro_context_text else "(No rollup context available.)"

    event_lines = []
    for evt in sorted_events:
        key = _event_key(evt)
        rank_info = rank_map.get(key, {})
        tier = rank_info.get("importance_tier", "low")
        time_display = evt.get("time_local") or "All Day"
        title = evt.get("title") or ""
        currency = evt.get("currency_tag") or ""
        country = evt.get("country_or_region") or ""
        meta = ", ".join(filter(None, [currency, country]))
        evt_type = _classify_event_type(title)
        event_lines.append(f"[{tier.upper()}] {time_display} | {title} ({meta}) | type={evt_type}")

    events_block = "\n".join(event_lines) or "(no events)"

    dynamics_instruction = (
        "Include practical market implications and positioning advice."
        if dynamics_mode
        else "Focus on directional implications only."
    )

    ctx_instruction = (
        "Use the macro context to inform your market interpretation. "
        "Connect events to current regime dynamics where relevant."
        if dynamics_mode
        else ""
    )

    return (
        f"Date: {date_iso}\n\n"
        f"Macro context:\n---\n{ctx_block}\n---\n\n"
        "Events (ordered by priority, most important first):\n"
        f"{events_block}\n\n"
        "Write a concise, actionable daily economic summary for traders.\n\n"
        "Rules:\n"
        "1. Focus ONLY on the top 2-5 most market-moving events.\n"
        "2. Do NOT explain what each indicator is or define terms.\n"
        "3. For each key event, provide:\n"
        "   - What outcome would be bullish/bearish for USD, equities, or bonds\n"
        "   - How to position ahead of the release (e.g., 'watch for vol spike', 'fade initial move', 'breakout setup')\n"
        "   - Any timing considerations (e.g., 'data drops 30min before market open')\n"
        "4. Use conditional phrasing:\n"
        "   'If CPI comes in hot (>X%), expect...'\n"
        "   'Dovish tone from Powell would likely...'\n"
        "   'Miss on jobs could trigger...'\n"
        "5. Keep the entire summary under 10 sentences total.\n"
        "6. Ignore low-importance events unless they create confluence with a major release.\n"
        f"7. {dynamics_instruction}\n"
        f"8. {ctx_instruction}\n"
        "9. Never use hyphens. Use commas or parentheses instead.\n"
        "10. Return ONLY a JSON object with two keys:\n"
        '    "theory_text": "<actionable summary as plain text>"\n'
        '    "dynamics_text": "<positioning advice as plain text, or empty string if dynamics mode is off>"\n'
        "No markdown fences. No commentary outside the JSON."
    )


# ---------------------------------------------------------------------------
# Public AI functions
# ---------------------------------------------------------------------------


def rank_economic_events_ai(
    date_iso: str,
    events: list[dict],
    macro_context_text: str = "",
    db_path=None,
) -> list[dict]:
    """
    Call the LLM to rank events for a given date by market importance.

    Falls back to a heuristic ranking on any LLM or JSON failure.

    Args:
        date_iso: ISO date string YYYY-MM-DD.
        events: Event dicts from get_events_for_date.
        macro_context_text: Optional rollup context string.
        db_path: SQLite path override.

    Returns:
        List of rank dicts: {event_key, priority, importance_tier, reason}.
    """
    print(f"[ECON AI] rank_economic_events_ai START: {date_iso}, {len(events)} events")
    
    if not events:
        return []

    prompt = _build_rank_prompt(date_iso, events, macro_context_text)
    print(f"[ECON AI] rank_economic_events_ai: Calling LLM for {date_iso}...")

    try:
        client = _get_llm_client()
        response = client.chat.completions.create(
            model=_LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a financial markets analyst. "
                        "Return only valid JSON as instructed. No markdown. No commentary."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
            temperature=0.2,
        )
        print(f"[ECON AI] rank_economic_events_ai: LLM response received for {date_iso}")
        raw = (response.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[ECON AI] rank_economic_events_ai LLM call failed for {date_iso}: {exc}")
        return _fallback_rank(events)

    # Strip markdown fences if the model added them despite instructions
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        payload = json.loads(raw)
        ranked = payload.get("ranked", [])
        if not isinstance(ranked, list):
            raise ValueError("'ranked' is not a list")
        # Validate each entry
        valid = []
        for item in ranked:
            if not isinstance(item, dict):
                continue
            if not all(k in item for k in ("event_key", "priority", "importance_tier", "reason")):
                continue
            if item["importance_tier"] not in ("high", "medium", "low"):
                item["importance_tier"] = "low"
            item["reason"] = _strip_hyphens(str(item.get("reason", "")))
            valid.append(item)
        if not valid:
            raise ValueError("No valid ranked items in response")
        return valid
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[ECON AI] rank output invalid for {date_iso}: {exc}. Using fallback.")
        return _fallback_rank(events)


def generate_daily_brief_ai(
    date_iso: str,
    events: list[dict],
    ranked: list[dict],
    macro_context_text: str = "",
    dynamics_mode: bool = True,
    db_path=None,
) -> dict:
    """
    Call the LLM to produce a beginner-friendly daily economic brief.

    Returns theory_text and dynamics_text (dynamics_text is empty string
    when dynamics_mode is False).  Falls back to a plain-text stub on error.

    Args:
        date_iso: ISO date string YYYY-MM-DD.
        events: Event dicts for the date.
        ranked: Ranked event list from rank_economic_events_ai.
        macro_context_text: Optional rollup context string.
        dynamics_mode: When False, theory only; dynamics_text is returned as "".
        db_path: SQLite path override.

    Returns:
        Dict with keys 'theory_text' (str), 'dynamics_text' (str), and 'is_error' (bool).
        The 'is_error' key is True if the brief generation failed.
    """
    print(f"[ECON AI] generate_daily_brief_ai START: date_key={date_iso}, events_count={len(events)}, dynamics_mode={dynamics_mode}")
    
    if not events:
        return {"theory_text": "No events scheduled for this date.", "dynamics_text": ""}

    prompt = _build_brief_prompt(date_iso, events, ranked, macro_context_text, dynamics_mode)
    print(f"[ECON AI] generate_daily_brief_ai: Calling LLM for {date_iso}...")

    try:
        client = _get_llm_client()
        response = client.chat.completions.create(
            model=_LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional trader writing actionable market briefs. "
                        "Focus on how to trade the events, not on explaining what they are. "
                        "Return only valid JSON as instructed. No markdown. No commentary."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1800,
            temperature=0.35,
        )
        print(f"[ECON AI] generate_daily_brief_ai: LLM response received for {date_iso}")
        raw = (response.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[ECON AI] generate_daily_brief_ai LLM call FAILED for date_key={date_iso}: {exc}")
        # Return error dict - DO NOT store error messages as theory_text
        # The 'is_error' flag tells callers not to persist this as valid content
        return {
            "theory_text": "",
            "dynamics_text": "",
            "is_error": True,
            "error_msg": str(exc)[:500],
        }

    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        payload = json.loads(raw)
        theory_text = _strip_hyphens(str(payload.get("theory_text", "") or ""))
        dynamics_text = (
            _strip_hyphens(str(payload.get("dynamics_text", "") or ""))
            if dynamics_mode
            else ""
        )
        print(f"[ECON AI] generate_daily_brief_ai SUCCESS: date_key={date_iso}, theory_len={len(theory_text)}, dynamics_len={len(dynamics_text)}")
        return {"theory_text": theory_text, "dynamics_text": dynamics_text, "is_error": False}
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[ECON AI] brief output invalid JSON for date_key={date_iso}: {exc}. Returning raw text.")
        cleaned = _strip_hyphens(raw)
        return {"theory_text": cleaned, "dynamics_text": "", "is_error": False}


# ---------------------------------------------------------------------------
# Orchestration: run Steps A, B, C for a single date
# ---------------------------------------------------------------------------


def _build_rollup_context_text(rollup_data: dict) -> str:
    """
    Extract TLDR, Observations, and What to Watch Today text from a rollup dict.

    Args:
        rollup_data: Loaded rollup JSON dict.

    Returns:
        Plain-text context string (capped at 1200 chars).
    """
    sections = rollup_data.get("sections", {})
    lines: list[str] = []

    def _grab_list(items, label: str) -> None:
        if not items:
            return
        lines.append(f"[{label}]")
        for item in (items if isinstance(items, list) else [])[:5]:
            text = item.get("text", str(item)) if isinstance(item, dict) else str(item)
            lines.append(f"  {text[:220]}")

    def _grab_dict(d, label: str) -> None:
        if not d or not isinstance(d, dict):
            return
        lines.append(f"[{label}]")
        for _key, items in list(d.items())[:3]:
            for item in (items if isinstance(items, list) else [])[:2]:
                text = item.get("text", str(item)) if isinstance(item, dict) else str(item)
                lines.append(f"  {text[:220]}")

    _grab_list(sections.get("tldr", []), "TLDR")

    obs = sections.get("observations", {})
    if isinstance(obs, dict):
        _grab_dict(obs, "Observations")
    elif isinstance(obs, list):
        _grab_list(obs, "Observations")

    fw = sections.get("forward_watch", {})
    if isinstance(fw, dict):
        _grab_dict(fw, "What to Watch Today")
    elif isinstance(fw, list):
        _grab_list(fw, "What to Watch Today")

    return "\n".join(lines)[:1200]


def generate_for_date(
    date_iso: str,
    dynamics_mode: bool = True,
    db_path=None,
    rollups_daily_dir: Optional[Path] = None,
) -> dict:
    """
    Run Steps A, B, and C for one calendar date.

    Step A: Load events + hashes, find rollup context.
    Step B: Rank events (skip if cached and hashes match).
    Step C: Generate daily brief (skip if cached and hashes match, and text populated).

    Args:
        date_iso: ISO date YYYY-MM-DD.
        dynamics_mode: Whether to generate dynamics text.
        db_path: SQLite path override (None = default).
        rollups_daily_dir: Path to the rollups/daily directory. If None, caller
                           must have set the env or FILES_DIR constant is used.

    Returns:
        Dict with keys:
            'date_iso', 'skipped_rank' (bool), 'skipped_brief' (bool),
            'events_count' (int), 'error' (str or None).
    """
    print(f"[ECON AI] generate_for_date START: {date_iso}, dynamics_mode={dynamics_mode}")
    
    result: dict = {
        "date_iso": date_iso,
        "skipped_rank": False,
        "skipped_brief": False,
        "events_count": 0,
        "error": None,
    }

    try:
        print(f"[ECON AI] Step A: Loading events for {date_iso}...")
        # ── Step A: Load events and compute hashes ──────────────────────────
        events = get_events_for_date(db_path, date_iso)
        result["events_count"] = len(events)
        print(f"[ECON AI] Step A: Found {len(events)} events for {date_iso}")

        if not events:
            print(f"[ECON AI] No events for {date_iso}, skipping rank and brief")
            result["skipped_rank"] = True
            result["skipped_brief"] = True
            return result

        events_hash = compute_events_hash(events)
        print(f"[ECON AI] Step A: events_hash={events_hash[:16]}...")

        # Locate rollup for this date
        macro_context_text = ""
        if rollups_daily_dir and rollups_daily_dir.is_dir():
            yyyymmdd = date_iso.replace("-", "")
            rollup_fname = f"ROLLUP_DAILY_{yyyymmdd}__sum.json"
            rollup_path = rollups_daily_dir / rollup_fname
            if rollup_path.exists():
                try:
                    with open(rollup_path, "r", encoding="utf-8") as fh:
                        rollup_data = json.load(fh)
                    macro_context_text = _build_rollup_context_text(rollup_data)
                except Exception as exc:  # noqa: BLE001
                    print(f"[ECON AI] Could not load rollup for {date_iso}: {exc}")

        context_hash = compute_context_hash(macro_context_text or None)
        print(f"[ECON AI] Step A: context_hash={context_hash[:16]}...")

        # ── Step B: Ranking ─────────────────────────────────────────────────
        print(f"[ECON AI] Step B: Checking cached rank for {date_iso}...")
        cached_rank = get_daily_rank(db_path, date_iso)
        
        # Debug: type check cached_rank
        if cached_rank and not isinstance(cached_rank, dict):
            print(f"[ECON AI DEBUG] cached_rank for {date_iso} is type {type(cached_rank)}, not dict!")
            print(f"[ECON AI DEBUG] cached_rank value: {repr(cached_rank)[:200]}")
            cached_rank = None  # Force regeneration
        
        if (
            cached_rank
            and cached_rank.get("events_hash") == events_hash
            and cached_rank.get("context_hash") == context_hash
            and cached_rank.get("rank_json")
        ):
            result["skipped_rank"] = True
            rank_json_str = cached_rank["rank_json"]
            
            # Debug: type check rank_json before parsing
            if not isinstance(rank_json_str, str):
                print(f"[ECON AI DEBUG] rank_json for {date_iso} is type {type(rank_json_str)}, not str!")
                print(f"[ECON AI DEBUG] rank_json value: {repr(rank_json_str)[:200]}")
                raise TypeError(f"rank_json must be string, got {type(rank_json_str)}")
            
            parsed = json.loads(rank_json_str)
            
            # Debug: type check parsed JSON
            if not isinstance(parsed, dict):
                print(f"[ECON AI DEBUG] Parsed rank_json for {date_iso} is type {type(parsed)}, not dict!")
                print(f"[ECON AI DEBUG] Parsed value: {repr(parsed)[:200]}")
                raise TypeError(f"Parsed rank_json must be dict, got {type(parsed)}")
            
            # Extract the ranked list
            if "ranked" in parsed:
                ranked = parsed["ranked"]
            else:
                # Fallback: assume the whole thing is the ranked list
                print(f"[ECON AI DEBUG] No 'ranked' key in parsed JSON for {date_iso}, using parsed directly")
                ranked = parsed if isinstance(parsed, list) else []
        else:
            print(f"[ECON AI] Step B: Generating new rank for {date_iso}...")
            ranked = rank_economic_events_ai(date_iso, events, macro_context_text, db_path)
            rank_json_str = json.dumps({"ranked": ranked}, ensure_ascii=False)
            upsert_daily_rank(db_path, date_iso, context_hash, events_hash, rank_json_str)
            print(f"[ECON AI] Step B: Saved new rank for {date_iso}")

        # ── Step C: Daily brief ─────────────────────────────────────────────
        print(f"[ECON AI] Step C: Checking cached brief for {date_iso}...")
        cached_brief = get_daily_brief(db_path, date_iso)
        
        # Debug: type check cached_brief
        if cached_brief and not isinstance(cached_brief, dict):
            print(f"[ECON AI DEBUG] cached_brief for {date_iso} is type {type(cached_brief)}, not dict!")
            print(f"[ECON AI DEBUG] cached_brief value: {repr(cached_brief)[:200]}")
            cached_brief = None  # Force regeneration
        
        brief_valid = False
        if cached_brief:
            print(f"[ECON AI] Step C: Found cached brief for {date_iso}")
            hashes_match = (
                cached_brief.get("events_hash") == events_hash
                and cached_brief.get("context_hash") == context_hash
            )
            if hashes_match:
                if dynamics_mode:
                    brief_valid = bool(
                        cached_brief.get("theory_text") and cached_brief.get("dynamics_text")
                    )
                else:
                    brief_valid = bool(cached_brief.get("theory_text"))
                
                if brief_valid:
                    print(f"[ECON AI] Step C: Cached brief valid for {date_iso}, skipping generation")
                else:
                    print(f"[ECON AI] Step C: Cached brief missing required fields for {date_iso}")
            else:
                print(f"[ECON AI] Step C: Cached brief hashes don't match for {date_iso}")

        if brief_valid:
            result["skipped_brief"] = True
        else:
            print(f"[ECON AI] Step C: Generating new brief for date_key={date_iso}...")
            brief = generate_daily_brief_ai(
                date_iso, events, ranked, macro_context_text, dynamics_mode, db_path
            )
            
            # Debug: type check brief response
            if not isinstance(brief, dict):
                print(f"[ECON AI DEBUG] generate_daily_brief_ai returned type {type(brief)}, not dict!")
                print(f"[ECON AI DEBUG] brief value: {repr(brief)[:200]}")
                raise TypeError(f"generate_daily_brief_ai must return dict, got {type(brief)}")
            
            # Check if generation returned an error - do NOT persist error messages as content
            if brief.get("is_error"):
                error_msg = brief.get("error_msg", "Unknown error")
                print(f"[ECON AI] Step C: Brief generation FAILED for date_key={date_iso}: {error_msg}")
                result["error"] = f"Brief generation failed: {error_msg}"
                # Do NOT upsert - leave the brief row missing so it can be regenerated
            else:
                if "theory_text" not in brief or "dynamics_text" not in brief:
                    print(f"[ECON AI DEBUG] brief for {date_iso} missing required keys!")
                    print(f"[ECON AI DEBUG] brief keys: {brief.keys()}")
                    # Add defaults
                    if "theory_text" not in brief:
                        brief["theory_text"] = "Summary generation incomplete."
                    if "dynamics_text" not in brief:
                        brief["dynamics_text"] = ""
                
                # Log the DB write with date key and content length
                print(f"[ECON AI] Step C: DB WRITE for date_key={date_iso}, theory_len={len(brief['theory_text'])}, dynamics_len={len(brief['dynamics_text'])}")
                
                upsert_daily_brief(
                    db_path,
                    date_iso,
                    context_hash,
                    events_hash,
                    brief["theory_text"],
                    brief["dynamics_text"],
                )
                print(f"[ECON AI] Step C: Saved new brief for date_key={date_iso}")

        print(f"[ECON AI] generate_for_date COMPLETE: {date_iso}")

    except Exception as exc:  # noqa: BLE001
        import traceback

        tb = traceback.format_exc()
        print(f"[ECON AI] ERROR in generate_for_date for {date_iso}: {exc}\n{tb}")
        result["error"] = str(exc)

    return result


def generate_for_week(
    dates: list[str],
    dynamics_mode: bool = True,
    db_path=None,
    rollups_daily_dir: Optional[Path] = None,
    progress_callback=None,
) -> list[dict]:
    """
    Run generation sequentially across all dates in a week.

    Args:
        dates: Ordered list of ISO date strings.
        dynamics_mode: Whether to include dynamics text in the brief.
        db_path: SQLite path override.
        rollups_daily_dir: Path to rollups/daily directory.
        progress_callback: Optional callable(completed: int, total: int, result: dict).
                           Called after each date completes.

    Returns:
        List of per-date result dicts from generate_for_date.
    """
    total = len(dates)
    results = []
    for i, date_iso in enumerate(dates, start=1):
        res = generate_for_date(date_iso, dynamics_mode, db_path, rollups_daily_dir)
        results.append(res)
        if progress_callback is not None:
            try:
                progress_callback(i, total, res)
            except Exception as exc:  # noqa: BLE001
                print(f"[ECON AI] progress_callback error: {exc}")
    return results

