"""
LLM-powered rollup aggregator.
Purpose: Feed validated sum.json objects to an LLM and produce a structured
         rollup JSON with consensus themes, divergences, catalysts, risk framing,
         and a numeric registry. Validates the output schema before returning.
Author: Kevin Lefebvre
Last Updated: 2026-02-12
ZERO-OCR RULE: This module NEVER touches PDFs or uses OCR.
"""

from __future__ import annotations

import json
import os
import re
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROLLUP_SCHEMA_VERSION = "twifo.rollup.v2"
ROLLUP_MODEL = os.getenv("TWIFO_ROLLUP_MODEL", "gpt-4o")
ROLLUP_MAX_OUTPUT_TOKENS = 4000
ROLLUP_TEMPERATURE = 0.15

# Max chars of serialised input summaries to feed the LLM (safety cap)
MAX_INPUT_CHARS = 120_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _iso_now() -> str:
    """UTC ISO-8601 timestamp."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json / ``` wrappers from LLM output."""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Input preparation — slim down sum.json objects for the LLM context window
# ---------------------------------------------------------------------------
_KEEP_META_KEYS = {
    "title", "provider", "published_date", "horizon", "products",
    "primary_entities", "low_confidence", "low_confidence_reason",
}

_KEEP_SECTION_KEYS = {
    "tldr", "what_moved_today", "what_can_move_tomorrow", "trade_ideas",
    "what_occurred", "forward_watch", "warnings", "cross_asset_impacts",
    "scenarios",
}


def slim_summary(summary: dict) -> dict:
    """
    Reduce a full sum.json to the fields the rollup LLM needs.

    Keeps: meta (subset), fingerprint_quotes, numeric_claims, sections (subset),
    chart_score_0_3, chart_observations, sentiment_indicator, volatility_impact.
    """
    meta = summary.get("meta", {})
    slimmed_meta = {k: meta[k] for k in _KEEP_META_KEYS if k in meta}

    sections = summary.get("sections", {})
    slimmed_sections = {}
    for key in _KEEP_SECTION_KEYS:
        val = sections.get(key)
        if val:
            slimmed_sections[key] = val

    result: dict[str, Any] = {
        "meta": slimmed_meta,
        "fingerprint_quotes": summary.get("fingerprint_quotes", []),
        "numeric_claims": summary.get("numeric_claims", []),
        "sections": slimmed_sections,
    }

    # Optional top-level fields
    for opt_key in ("chart_score_0_3", "chart_observations",
                    "sentiment_indicator", "volatility_impact"):
        val = summary.get(opt_key)
        if val is not None:
            result[opt_key] = val

    # Carry forward sections that live at top level in some schemas
    for opt_section in ("what_moved_today", "what_can_move_tomorrow"):
        if opt_section not in slimmed_sections:
            top_val = summary.get(opt_section)
            if top_val:
                result["sections"][opt_section] = top_val

    return result


def prepare_llm_input(summaries: List[dict]) -> str:
    """
    Serialise a list of sum.json dicts into a compact JSON string for the LLM.
    Applies slim_summary() to each and truncates to MAX_INPUT_CHARS.
    """
    slimmed = [slim_summary(s) for s in summaries]
    payload = json.dumps(slimmed, indent=1, ensure_ascii=False)
    if len(payload) > MAX_INPUT_CHARS:
        payload = payload[:MAX_INPUT_CHARS] + "\n... (truncated)"
    return payload


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------
def call_rollup_llm(
    summaries: List[dict],
    *,
    model: str = ROLLUP_MODEL,
    temperature: float = ROLLUP_TEMPERATURE,
    max_output_tokens: int = ROLLUP_MAX_OUTPUT_TOKENS,
) -> Tuple[dict, str]:
    """
    Call the LLM with the rollup aggregator prompt and return parsed JSON.

    Args:
        summaries: List of validated sum.json dicts.
        model: OpenAI model to use.
        temperature: Sampling temperature.
        max_output_tokens: Max output tokens.

    Returns:
        Tuple of (parsed_rollup_dict, raw_output_text).

    Raises:
        ValueError: If the LLM returns unparseable output.
    """
    from openai_client import get_client
    from twifo_prompts.prompts.rollup_prompts import (
        ROLLUP_SYSTEM_PROMPT,
        ROLLUP_USER_PROMPT,
        SUMMARIES_PLACEHOLDER,
    )

    client = get_client()

    # Build prompts
    input_payload = prepare_llm_input(summaries)
    user_prompt = ROLLUP_USER_PROMPT.replace(SUMMARIES_PLACEHOLDER, input_payload)

    print(
        f"[ROLLUP-LLM] model={model}, input_summaries={len(summaries)}, "
        f"payload_chars={len(input_payload)}, max_tokens={max_output_tokens}"
    )

    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": ROLLUP_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )

    # Extract text
    raw_text = ""
    for item in response.output:
        for content_item in item.content:
            if content_item.type == "output_text":
                raw_text += content_item.text

    if not raw_text.strip():
        raise ValueError("[ROLLUP-LLM] API returned empty output")

    cleaned = _strip_markdown_fences(raw_text)
    parsed = json.loads(cleaned)

    return parsed, raw_text


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
_REQUIRED_TOP_KEYS = {
    "_meta", "consensus_themes", "divergences", "catalysts_calendar",
    "risk_framing", "trade_ideas_synthesis", "rollup_numeric_claims",
    "tldr",
}

_REQUIRED_META_KEYS = {
    "rollup_prompt_version", "input_count", "input_providers",
}

_REQUIRED_CONSENSUS_KEYS = {
    "theme", "provider_count", "source_providers", "direction",
    "summary", "evidence_quotes",
}

_REQUIRED_DIVERGENCE_KEYS = {
    "entity", "description", "side_a", "side_b",
}

_REQUIRED_SIDE_KEYS = {
    "position", "source_providers", "evidence_quotes",
}

_REQUIRED_CATALYST_KEYS = {
    "date_or_window", "event", "source_providers",
}

_REQUIRED_RISK_KEYS = {
    "overall_risk_sentiment", "key_risks",
}

_REQUIRED_TRADE_SYNTH_KEYS = {
    "product", "consensus_bias", "source_providers",
}

_REQUIRED_NUMERIC_CLAIM_KEYS = {
    "value", "context", "source_summary",
}


def validate_rollup_schema(rollup: dict) -> Tuple[bool, List[str]]:
    """
    Validate that a rollup dict conforms to the expected schema.

    Returns:
        Tuple of (is_valid, list_of_violation_strings).
    """
    violations: List[str] = []

    # Top-level keys
    missing_top = _REQUIRED_TOP_KEYS - set(rollup.keys())
    if missing_top:
        violations.append(f"Missing top-level keys: {sorted(missing_top)}")

    # _meta
    meta = rollup.get("_meta", {})
    if not isinstance(meta, dict):
        violations.append("_meta must be a dict")
    else:
        missing_meta = _REQUIRED_META_KEYS - set(meta.keys())
        if missing_meta:
            violations.append(f"_meta missing keys: {sorted(missing_meta)}")
        if not isinstance(meta.get("input_providers"), list):
            violations.append("_meta.input_providers must be a list")

    # consensus_themes
    themes = rollup.get("consensus_themes", [])
    if not isinstance(themes, list):
        violations.append("consensus_themes must be a list")
    else:
        for i, theme in enumerate(themes):
            if not isinstance(theme, dict):
                violations.append(f"consensus_themes[{i}] must be a dict")
                continue
            missing = _REQUIRED_CONSENSUS_KEYS - set(theme.keys())
            if missing:
                violations.append(f"consensus_themes[{i}] missing: {sorted(missing)}")
            # provider_count must match source_providers length
            pc = theme.get("provider_count", 0)
            sp = theme.get("source_providers", [])
            if isinstance(pc, int) and isinstance(sp, list) and pc != len(sp):
                violations.append(
                    f"consensus_themes[{i}].provider_count={pc} != "
                    f"len(source_providers)={len(sp)}"
                )
            # evidence_quotes must be a non-empty list
            eq = theme.get("evidence_quotes", [])
            if not isinstance(eq, list) or len(eq) == 0:
                violations.append(
                    f"consensus_themes[{i}].evidence_quotes must be non-empty list"
                )

    # divergences
    divs = rollup.get("divergences", [])
    if not isinstance(divs, list):
        violations.append("divergences must be a list")
    else:
        for i, div in enumerate(divs):
            if not isinstance(div, dict):
                violations.append(f"divergences[{i}] must be a dict")
                continue
            missing = _REQUIRED_DIVERGENCE_KEYS - set(div.keys())
            if missing:
                violations.append(f"divergences[{i}] missing: {sorted(missing)}")
            for side_key in ("side_a", "side_b"):
                side = div.get(side_key, {})
                if isinstance(side, dict):
                    missing_s = _REQUIRED_SIDE_KEYS - set(side.keys())
                    if missing_s:
                        violations.append(
                            f"divergences[{i}].{side_key} missing: {sorted(missing_s)}"
                        )

    # catalysts_calendar
    cats = rollup.get("catalysts_calendar", [])
    if not isinstance(cats, list):
        violations.append("catalysts_calendar must be a list")
    else:
        for i, cat in enumerate(cats):
            if not isinstance(cat, dict):
                violations.append(f"catalysts_calendar[{i}] must be a dict")
                continue
            missing = _REQUIRED_CATALYST_KEYS - set(cat.keys())
            if missing:
                violations.append(f"catalysts_calendar[{i}] missing: {sorted(missing)}")

    # risk_framing
    risk = rollup.get("risk_framing", {})
    if not isinstance(risk, dict):
        violations.append("risk_framing must be a dict")
    else:
        missing_r = _REQUIRED_RISK_KEYS - set(risk.keys())
        if missing_r:
            violations.append(f"risk_framing missing: {sorted(missing_r)}")
        key_risks = risk.get("key_risks", [])
        if not isinstance(key_risks, list):
            violations.append("risk_framing.key_risks must be a list")
        else:
            for i, kr in enumerate(key_risks):
                if isinstance(kr, dict):
                    if "evidence_quote" not in kr and "evidence_quotes" not in kr:
                        violations.append(
                            f"risk_framing.key_risks[{i}] missing evidence_quote"
                        )

    # trade_ideas_synthesis
    trades = rollup.get("trade_ideas_synthesis", [])
    if not isinstance(trades, list):
        violations.append("trade_ideas_synthesis must be a list")
    else:
        for i, t in enumerate(trades):
            if not isinstance(t, dict):
                violations.append(f"trade_ideas_synthesis[{i}] must be a dict")
                continue
            missing = _REQUIRED_TRADE_SYNTH_KEYS - set(t.keys())
            if missing:
                violations.append(
                    f"trade_ideas_synthesis[{i}] missing: {sorted(missing)}"
                )

    # rollup_numeric_claims
    claims = rollup.get("rollup_numeric_claims", [])
    if not isinstance(claims, list):
        violations.append("rollup_numeric_claims must be a list")
    else:
        for i, c in enumerate(claims):
            if not isinstance(c, dict):
                violations.append(f"rollup_numeric_claims[{i}] must be a dict")
                continue
            missing = _REQUIRED_NUMERIC_CLAIM_KEYS - set(c.keys())
            if missing:
                violations.append(
                    f"rollup_numeric_claims[{i}] missing: {sorted(missing)}"
                )

    # tldr
    tldr = rollup.get("tldr", [])
    if not isinstance(tldr, list):
        violations.append("tldr must be a list")
    elif len(tldr) < 3:
        violations.append(f"tldr has {len(tldr)} bullets, need >=3")

    return len(violations) == 0, violations


# ---------------------------------------------------------------------------
# Numeric cross-check: verify every number in the rollup traces to an input
# ---------------------------------------------------------------------------
_NUMERIC_RE = re.compile(
    r"(?<![a-zA-Z])"
    r"(?:\$)?"
    r"\d[\d,]*(?:\.\d+)?"
    r"(?:\s*%?)?"
    r"(?![a-zA-Z])"
)

_EXEMPT_KEYS = frozenset({
    "provider_count", "confidence_0_100", "input_count",
    "rollup_prompt_version", "chart_score_0_3",
    "date_or_window", "input_date_range", "target_date",
    "generated_at_iso", "numeric_coverage_pct",
})


def _extract_numbers_from_value(value: Any) -> List[str]:
    """Extract numeric tokens from a string value."""
    if not isinstance(value, str):
        return []
    return _NUMERIC_RE.findall(value)


def _walk_for_numerics(
    obj: Any, path: str = "", exempt_keys: frozenset = _EXEMPT_KEYS
) -> List[Dict[str, str]]:
    """
    Recursively extract all numeric tokens from a JSON structure.
    Skips keys in exempt_keys and the rollup_numeric_claims section itself.
    """
    results: List[Dict[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in exempt_keys:
                continue
            if k == "rollup_numeric_claims":
                continue
            _walk_for_numerics_inner(v, f"{path}.{k}", results, exempt_keys)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_for_numerics_inner(v, f"{path}[{i}]", results, exempt_keys)
    return results


def _walk_for_numerics_inner(
    obj: Any, path: str, results: List[Dict[str, str]],
    exempt_keys: frozenset,
) -> None:
    """Inner recursive walker."""
    if isinstance(obj, str):
        for token in _extract_numbers_from_value(obj):
            results.append({"token": token, "path": path})
    elif isinstance(obj, (int, float)):
        results.append({"token": str(obj), "path": path})
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in exempt_keys or k == "rollup_numeric_claims":
                continue
            _walk_for_numerics_inner(v, f"{path}.{k}", results, exempt_keys)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_for_numerics_inner(v, f"{path}[{i}]", results, exempt_keys)


def _normalize_num(raw: str) -> str:
    """Normalize a numeric string for comparison: strip $, commas, whitespace."""
    return re.sub(r"[\s,$]", "", raw).rstrip("%").strip()


def build_input_numeric_index(summaries: List[dict]) -> set:
    """
    Build a set of all normalized numeric values present in the input summaries.
    Used to verify rollup numbers trace back to inputs.
    """
    index: set = set()
    for s in summaries:
        # numeric_claims
        for claim in s.get("numeric_claims", []):
            if isinstance(claim, dict):
                val = claim.get("value", "")
                if val:
                    index.add(_normalize_num(str(val)))
        # Walk all text fields for numbers
        for token_info in _walk_for_numerics(s):
            index.add(_normalize_num(token_info["token"]))
    return index


def verify_rollup_numerics(
    rollup: dict, input_summaries: List[dict]
) -> Tuple[dict, List[str]]:
    """
    Verify every numeric token in the rollup traces to an input summary.

    Mutates rollup in-place:
    - Adds _meta.numeric_coverage_pct
    - Adds _meta.unverified_numbers[] for any that fail

    Returns:
        Tuple of (rollup, list_of_unverified_tokens).
    """
    input_index = build_input_numeric_index(input_summaries)
    rollup_tokens = _walk_for_numerics(rollup)

    verified = 0
    unverified: List[str] = []

    for info in rollup_tokens:
        norm = _normalize_num(info["token"])
        if not norm or norm == "0":
            verified += 1
            continue
        if norm in input_index:
            verified += 1
        else:
            unverified.append(f"{info['token']} at {info['path']}")

    total = verified + len(unverified)
    coverage = round(100.0 * verified / total, 1) if total > 0 else 100.0

    meta = rollup.setdefault("_meta", {})
    meta["numeric_coverage_pct"] = coverage
    if unverified:
        meta["unverified_numbers"] = unverified

    return rollup, unverified


# ---------------------------------------------------------------------------
# Main aggregator entry point
# ---------------------------------------------------------------------------
def aggregate_rollup(
    summaries: List[dict],
    *,
    rollup_kind: str = "daily",
    target_date: Optional[str] = None,
    model: str = ROLLUP_MODEL,
    temperature: float = ROLLUP_TEMPERATURE,
    max_output_tokens: int = ROLLUP_MAX_OUTPUT_TOKENS,
) -> Tuple[dict, List[str]]:
    """
    Full pipeline: prepare inputs -> call LLM -> validate schema -> verify numerics.

    Args:
        summaries: List of validated sum.json dicts.
        rollup_kind: "daily" or "weekly".
        target_date: ISO date string for the rollup.
        model: OpenAI model.
        temperature: Sampling temperature.
        max_output_tokens: Max output tokens.

    Returns:
        Tuple of (validated_rollup_dict, list_of_schema_violations).
        If violations exist, the rollup is still returned but may be incomplete.
    """
    if not summaries:
        raise ValueError("No input summaries provided for rollup aggregation")

    print(f"[ROLLUP-AGG] Starting {rollup_kind} rollup with {len(summaries)} summaries")

    # 1. Call LLM
    parsed, raw_text = call_rollup_llm(
        summaries,
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    # 2. Inject/override _meta fields
    meta = parsed.setdefault("_meta", {})
    providers = sorted({
        s.get("meta", {}).get("provider", "O") for s in summaries
    })
    dates = sorted({
        s.get("meta", {}).get("published_date", "") for s in summaries
        if s.get("meta", {}).get("published_date")
    })
    meta["rollup_prompt_version"] = "1.0"
    meta["input_count"] = len(summaries)
    meta["input_providers"] = providers
    if dates:
        meta["input_date_range"] = f"{dates[0]} to {dates[-1]}"
    meta["rollup_kind"] = rollup_kind
    meta["generated_at_iso"] = _iso_now()
    meta["model"] = model
    if target_date:
        meta["target_date"] = target_date

    # 3. Validate schema
    is_valid, violations = validate_rollup_schema(parsed)
    if violations:
        print(f"[ROLLUP-AGG] Schema violations ({len(violations)}):")
        for v in violations[:10]:
            print(f"  - {v}")
    else:
        print("[ROLLUP-AGG] Schema validation passed")

    # 4. Verify numeric traceability
    parsed, unverified = verify_rollup_numerics(parsed, summaries)
    if unverified:
        print(f"[ROLLUP-AGG] Unverified numbers ({len(unverified)}):")
        for u in unverified[:5]:
            print(f"  - {u}")
    else:
        print("[ROLLUP-AGG] All rollup numbers verified against inputs")

    # 5. Stamp schema version
    parsed["schema_version"] = ROLLUP_SCHEMA_VERSION

    return parsed, violations
