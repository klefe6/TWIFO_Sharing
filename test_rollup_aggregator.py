"""
Tests for rollup_aggregator.py — schema validation, numeric verification,
input preparation, and prompt construction.
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

from __future__ import annotations

import json
import sys
import os

# Ensure TWIFO_Sharing is on the path
sys.path.insert(0, os.path.dirname(__file__))


# ---------------------------------------------------------------------------
# Fixtures: minimal valid sum.json objects
# ---------------------------------------------------------------------------

def _make_summary(
    provider: str = "BOA",
    title: str = "Test Article",
    published_date: str = "20260210",
    tldr: list | None = None,
    what_moved_today: list | None = None,
    what_can_move_tomorrow: list | None = None,
    trade_ideas: list | None = None,
    numeric_claims: list | None = None,
    fingerprint_quotes: list | None = None,
) -> dict:
    """Build a minimal valid sum.json for testing."""
    return {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {
            "title": title,
            "provider": provider,
            "published_date": published_date,
            "horizon": "d",
            "products": ["ES", "GC"],
            "primary_entities": ["ES", "GC"],
        },
        "fingerprint_quotes": fingerprint_quotes or [
            "Gold rallied sharply on safe-haven demand",
            "ES futures tested the 5,450 support level",
            "The Fed minutes showed hawkish tilt",
        ],
        "numeric_claims": numeric_claims or [
            {"value": "5,450", "context": "ES support", "source_quote": "tested 5,450"},
            {"value": "2,050", "context": "GC target", "source_quote": "gold at 2,050"},
        ],
        "sections": {
            "tldr": tldr or [
                {"text": "ES tested 5,450 support on heavy volume", "sources": [provider]},
                {"text": "Gold rallied to 2,050 on safe-haven flows", "sources": [provider]},
                {"text": "Fed minutes showed hawkish tilt", "sources": [provider]},
            ],
            "what_moved_today": what_moved_today or [
                {"text": "ES dropped 0.8% to test 5,450", "sources": [provider]},
            ],
            "what_can_move_tomorrow": what_can_move_tomorrow or [
                {"text": "FOMC minutes release at 2pm ET", "sources": [provider]},
            ],
            "trade_ideas": trade_ideas or [
                {
                    "product": "ES",
                    "bias": "Bearish",
                    "catalyst": "Hawkish Fed",
                    "key_levels": ["5,450", "5,400"],
                    "source_quote": "support at 5,450 with 5,400 next",
                },
            ],
            "what_occurred": [],
            "forward_watch": [
                {"text": "FOMC minutes Wednesday 2pm ET", "sources": [provider]},
            ],
            "warnings": [],
            "cross_asset_impacts": [],
            "scenarios": [],
        },
        "sentiment_indicator": {
            "risk_on_off": "Risk-Off",
            "confidence_0_100": 70,
            "rationale": "Hawkish Fed tilt",
        },
        "chart_score_0_3": 1,
        "chart_observations": ["ES volume spike at 5,450"],
    }


def _make_valid_rollup() -> dict:
    """Build a minimal valid rollup output for schema validation tests."""
    return {
        "_meta": {
            "rollup_prompt_version": "1.0",
            "input_count": 2,
            "input_providers": ["BOA", "JPM"],
            "input_date_range": "20260210 to 20260210",
            "primary_entities": ["ES", "GC"],
        },
        "consensus_themes": [
            {
                "theme": "Risk-off rotation",
                "provider_count": 2,
                "source_providers": ["BOA", "JPM"],
                "direction": "Bearish",
                "affected_entities": ["ES"],
                "summary": "Both providers see risk-off driven by hawkish Fed",
                "evidence_quotes": [
                    "ES tested 5,450 support on heavy volume",
                    "Equities under pressure from rate concerns",
                ],
            }
        ],
        "divergences": [],
        "catalysts_calendar": [
            {
                "date_or_window": "2026-02-12",
                "event": "FOMC minutes release",
                "affected_entities": ["ZN", "ES"],
                "source_providers": ["BOA"],
                "evidence_quote": "FOMC minutes Wednesday 2pm ET",
            }
        ],
        "risk_framing": {
            "overall_risk_sentiment": "Risk-Off",
            "confidence_0_100": 70,
            "key_risks": [
                {
                    "risk": "Hawkish Fed repricing",
                    "severity": "High",
                    "source_providers": ["BOA"],
                    "evidence_quote": "Fed minutes showed hawkish tilt",
                }
            ],
            "sentiment_rationale": "Broad risk-off on hawkish Fed signals (BOA, JPM)",
        },
        "trade_ideas_synthesis": [
            {
                "product": "ES",
                "consensus_bias": "Bearish",
                "provider_count": 2,
                "source_providers": ["BOA", "JPM"],
                "key_levels": ["5,450", "5,400"],
                "catalyst": "Hawkish Fed",
                "evidence_quotes": ["support at 5,450 with 5,400 next"],
            }
        ],
        "rollup_numeric_claims": [
            {"value": "5,450", "context": "ES support", "source_summary": "BOA"},
            {"value": "5,400", "context": "ES next support", "source_summary": "BOA"},
            {"value": "2,050", "context": "GC target", "source_summary": "BOA"},
        ],
        "tldr": [
            "ES tested 5,450 support on hawkish Fed signals (BOA, JPM)",
            "Gold rallied to 2,050 on safe-haven demand (BOA)",
            "FOMC minutes Wednesday key catalyst (BOA)",
        ],
        "forward_watch": [
            "FOMC minutes release Wednesday 2pm ET (BOA)",
        ],
    }


# ===========================================================================
# Tests: Schema Validation
# ===========================================================================

def test_valid_rollup_passes_validation():
    from rollup_aggregator import validate_rollup_schema
    rollup = _make_valid_rollup()
    is_valid, violations = validate_rollup_schema(rollup)
    assert is_valid, f"Expected valid, got violations: {violations}"
    assert violations == []


def test_missing_top_level_keys():
    from rollup_aggregator import validate_rollup_schema
    rollup = {"_meta": {"rollup_prompt_version": "1.0", "input_count": 1, "input_providers": ["BOA"]}}
    is_valid, violations = validate_rollup_schema(rollup)
    assert not is_valid
    assert any("Missing top-level" in v for v in violations)


def test_missing_meta_keys():
    from rollup_aggregator import validate_rollup_schema
    rollup = _make_valid_rollup()
    del rollup["_meta"]["input_count"]
    _, violations = validate_rollup_schema(rollup)
    assert any("_meta missing" in v for v in violations)


def test_consensus_provider_count_mismatch():
    from rollup_aggregator import validate_rollup_schema
    rollup = _make_valid_rollup()
    rollup["consensus_themes"][0]["provider_count"] = 5  # Wrong
    _, violations = validate_rollup_schema(rollup)
    assert any("provider_count" in v for v in violations)


def test_consensus_empty_evidence():
    from rollup_aggregator import validate_rollup_schema
    rollup = _make_valid_rollup()
    rollup["consensus_themes"][0]["evidence_quotes"] = []
    _, violations = validate_rollup_schema(rollup)
    assert any("evidence_quotes" in v for v in violations)


def test_divergence_missing_side():
    from rollup_aggregator import validate_rollup_schema
    rollup = _make_valid_rollup()
    rollup["divergences"] = [{
        "entity": "ES",
        "description": "ES split",
        "side_a": {"position": "Bullish", "source_providers": ["BOA"], "evidence_quotes": ["quote"]},
        # side_b missing
    }]
    _, violations = validate_rollup_schema(rollup)
    assert any("side_b" in v for v in violations)


def test_divergence_side_missing_evidence():
    from rollup_aggregator import validate_rollup_schema
    rollup = _make_valid_rollup()
    rollup["divergences"] = [{
        "entity": "ES",
        "description": "ES split",
        "side_a": {"position": "Bullish", "source_providers": ["BOA"]},  # missing evidence_quotes
        "side_b": {"position": "Bearish", "source_providers": ["DB"], "evidence_quotes": ["q"]},
    }]
    _, violations = validate_rollup_schema(rollup)
    assert any("side_a" in v and "evidence_quotes" in v for v in violations)


def test_catalyst_missing_keys():
    from rollup_aggregator import validate_rollup_schema
    rollup = _make_valid_rollup()
    rollup["catalysts_calendar"] = [{"event": "FOMC"}]  # missing date_or_window, source_providers
    _, violations = validate_rollup_schema(rollup)
    assert any("catalysts_calendar" in v for v in violations)


def test_risk_framing_missing_keys():
    from rollup_aggregator import validate_rollup_schema
    rollup = _make_valid_rollup()
    rollup["risk_framing"] = {}
    _, violations = validate_rollup_schema(rollup)
    assert any("risk_framing missing" in v for v in violations)


def test_risk_key_risks_missing_evidence():
    from rollup_aggregator import validate_rollup_schema
    rollup = _make_valid_rollup()
    rollup["risk_framing"]["key_risks"] = [{"risk": "something", "severity": "High", "source_providers": ["BOA"]}]
    _, violations = validate_rollup_schema(rollup)
    assert any("evidence_quote" in v for v in violations)


def test_trade_synthesis_missing_keys():
    from rollup_aggregator import validate_rollup_schema
    rollup = _make_valid_rollup()
    rollup["trade_ideas_synthesis"] = [{"product": "ES"}]  # missing consensus_bias, source_providers
    _, violations = validate_rollup_schema(rollup)
    assert any("trade_ideas_synthesis" in v for v in violations)


def test_numeric_claim_missing_keys():
    from rollup_aggregator import validate_rollup_schema
    rollup = _make_valid_rollup()
    rollup["rollup_numeric_claims"] = [{"value": "100"}]  # missing context, source_summary
    _, violations = validate_rollup_schema(rollup)
    assert any("rollup_numeric_claims" in v for v in violations)


def test_tldr_too_short():
    from rollup_aggregator import validate_rollup_schema
    rollup = _make_valid_rollup()
    rollup["tldr"] = ["one", "two"]  # need >= 3
    _, violations = validate_rollup_schema(rollup)
    assert any("tldr" in v for v in violations)


def test_empty_rollup_sections_valid():
    """A rollup with all empty arrays should still be structurally valid."""
    from rollup_aggregator import validate_rollup_schema
    rollup = {
        "_meta": {
            "rollup_prompt_version": "1.0",
            "input_count": 0,
            "input_providers": [],
        },
        "consensus_themes": [],
        "divergences": [],
        "catalysts_calendar": [],
        "risk_framing": {
            "overall_risk_sentiment": "Neutral",
            "key_risks": [],
        },
        "trade_ideas_synthesis": [],
        "rollup_numeric_claims": [],
        "tldr": ["a", "b", "c"],
    }
    is_valid, violations = validate_rollup_schema(rollup)
    assert is_valid, f"Expected valid, got: {violations}"


# ===========================================================================
# Tests: Numeric Verification
# ===========================================================================

def test_numeric_verification_all_traced():
    from rollup_aggregator import verify_rollup_numerics
    summaries = [_make_summary(provider="BOA"), _make_summary(provider="JPM")]
    rollup = _make_valid_rollup()
    result, unverified = verify_rollup_numerics(rollup, summaries)
    assert result["_meta"]["numeric_coverage_pct"] == 100.0
    assert unverified == []


def test_numeric_verification_detects_hallucinated():
    from rollup_aggregator import verify_rollup_numerics
    summaries = [_make_summary(provider="BOA")]
    rollup = _make_valid_rollup()
    # Inject a number not in any input
    rollup["tldr"].append("ES could reach 6,200 by Friday")
    result, unverified = verify_rollup_numerics(rollup, summaries)
    assert len(unverified) > 0
    assert any("6,200" in u or "6200" in u for u in unverified)
    assert result["_meta"]["numeric_coverage_pct"] < 100.0


def test_numeric_verification_exempt_keys():
    """provider_count, confidence_0_100 etc. should not be checked."""
    from rollup_aggregator import verify_rollup_numerics
    summaries = [_make_summary()]
    rollup = _make_valid_rollup()
    # These are exempt — should not appear as unverified
    rollup["_meta"]["input_count"] = 999
    rollup["risk_framing"]["confidence_0_100"] = 999
    _, unverified = verify_rollup_numerics(rollup, summaries)
    assert not any("999" in u for u in unverified)


def test_build_input_numeric_index():
    from rollup_aggregator import build_input_numeric_index
    summaries = [_make_summary()]
    index = build_input_numeric_index(summaries)
    assert "5450" in index  # normalized from "5,450"
    assert "2050" in index  # normalized from "2,050"


def test_normalize_num():
    from rollup_aggregator import _normalize_num
    assert _normalize_num("5,450") == "5450"
    assert _normalize_num("$2,050.50") == "2050.50"
    assert _normalize_num("4.25%") == "4.25"
    assert _normalize_num("  100 ") == "100"


# ===========================================================================
# Tests: Input Preparation (slim_summary)
# ===========================================================================

def test_slim_summary_keeps_required_fields():
    from rollup_aggregator import slim_summary
    full = _make_summary()
    slimmed = slim_summary(full)
    assert "meta" in slimmed
    assert "fingerprint_quotes" in slimmed
    assert "numeric_claims" in slimmed
    assert "sections" in slimmed
    assert slimmed["meta"]["provider"] == "BOA"


def test_slim_summary_drops_extraction():
    from rollup_aggregator import slim_summary
    full = _make_summary()
    full["extraction"] = {"status": "ok", "method_used": "pypdf2", "pages_total": 10}
    slimmed = slim_summary(full)
    assert "extraction" not in slimmed


def test_slim_summary_keeps_chart_fields():
    from rollup_aggregator import slim_summary
    full = _make_summary()
    slimmed = slim_summary(full)
    assert slimmed.get("chart_score_0_3") == 1
    assert "chart_observations" in slimmed


def test_slim_summary_keeps_sentiment():
    from rollup_aggregator import slim_summary
    full = _make_summary()
    slimmed = slim_summary(full)
    assert "sentiment_indicator" in slimmed


def test_prepare_llm_input_is_valid_json():
    from rollup_aggregator import prepare_llm_input
    summaries = [_make_summary(provider="BOA"), _make_summary(provider="JPM")]
    payload = prepare_llm_input(summaries)
    parsed = json.loads(payload)
    assert isinstance(parsed, list)
    assert len(parsed) == 2


def test_prepare_llm_input_truncation():
    from rollup_aggregator import prepare_llm_input, MAX_INPUT_CHARS
    # Create many summaries to exceed limit
    summaries = [_make_summary(provider=f"P{i}") for i in range(200)]
    payload = prepare_llm_input(summaries)
    assert len(payload) <= MAX_INPUT_CHARS + 50  # small buffer for truncation marker


# ===========================================================================
# Tests: Prompt Construction
# ===========================================================================

def test_rollup_prompt_has_placeholder():
    from twifo_prompts.prompts.rollup_prompts import (
        ROLLUP_USER_PROMPT, SUMMARIES_PLACEHOLDER,
    )
    assert SUMMARIES_PLACEHOLDER in ROLLUP_USER_PROMPT


def test_rollup_prompt_version():
    from twifo_prompts.prompts.rollup_prompts import ROLLUP_PROMPT_VERSION
    assert ROLLUP_PROMPT_VERSION == "1.0"


def test_rollup_prompt_sha256_deterministic():
    from twifo_prompts.prompts.rollup_prompts import rollup_prompt_sha256
    h1 = rollup_prompt_sha256()
    h2 = rollup_prompt_sha256()
    assert h1 == h2
    assert len(h1) == 64  # SHA256 hex


def test_rollup_system_prompt_contains_grounding_rules():
    from twifo_prompts.prompts.rollup_prompts import ROLLUP_SYSTEM_PROMPT
    assert "STRICT GROUNDING" in ROLLUP_SYSTEM_PROMPT
    assert "NUMERIC REGISTRY" in ROLLUP_SYSTEM_PROMPT
    assert "CONSENSUS VS DIVERGENCE" in ROLLUP_SYSTEM_PROMPT
    assert "CATALYSTS CALENDAR" in ROLLUP_SYSTEM_PROMPT


def test_rollup_user_prompt_contains_schema_keys():
    from twifo_prompts.prompts.rollup_prompts import ROLLUP_USER_PROMPT
    for key in ("consensus_themes", "divergences", "catalysts_calendar",
                "risk_framing", "trade_ideas_synthesis", "rollup_numeric_claims",
                "tldr", "forward_watch"):
        assert key in ROLLUP_USER_PROMPT, f"Missing key in user prompt: {key}"


def test_rollup_user_prompt_placeholder_replacement():
    from twifo_prompts.prompts.rollup_prompts import (
        ROLLUP_USER_PROMPT, SUMMARIES_PLACEHOLDER,
    )
    test_payload = '[{"meta": {"provider": "BOA"}}]'
    filled = ROLLUP_USER_PROMPT.replace(SUMMARIES_PLACEHOLDER, test_payload)
    assert test_payload in filled
    assert SUMMARIES_PLACEHOLDER not in filled


# ===========================================================================
# Tests: Walk for numerics
# ===========================================================================

def test_walk_for_numerics_finds_numbers():
    from rollup_aggregator import _walk_for_numerics
    obj = {
        "tldr": ["ES tested 5,450 support"],
        "risk_framing": {"key_risks": [{"evidence_quote": "gold at 2,050"}]},
    }
    tokens = _walk_for_numerics(obj)
    values = {t["token"] for t in tokens}
    assert "5,450" in values
    assert "2,050" in values


def test_walk_for_numerics_skips_exempt():
    from rollup_aggregator import _walk_for_numerics
    obj = {
        "provider_count": 5,
        "confidence_0_100": 70,
        "rollup_numeric_claims": [{"value": "999"}],
        "tldr": ["no numbers here"],
    }
    tokens = _walk_for_numerics(obj)
    values = {t["token"] for t in tokens}
    assert "5" not in values
    assert "70" not in values
    assert "999" not in values


def test_walk_for_numerics_nested():
    from rollup_aggregator import _walk_for_numerics
    obj = {
        "consensus_themes": [
            {"summary": "ES at 5,500 and GC at 2,100", "provider_count": 2}
        ]
    }
    tokens = _walk_for_numerics(obj)
    values = {t["token"] for t in tokens}
    assert "5,500" in values
    assert "2,100" in values
    assert "2" not in values  # provider_count is exempt


# ===========================================================================
# Tests: generate_rollup_clean.py integration
# ===========================================================================

def test_generate_rollup_clean_imports():
    """Verify the updated generate_rollup_clean.py imports work."""
    import generate_rollup_clean
    assert hasattr(generate_rollup_clean, "generate_daily_rollup")
    assert hasattr(generate_rollup_clean, "generate_weekly_rollup")
    assert hasattr(generate_rollup_clean, "_generate_llm_rollup")
    assert hasattr(generate_rollup_clean, "_parse_date_arg")


def test_parse_date_arg():
    from generate_rollup_clean import _parse_date_arg
    from datetime import date
    assert _parse_date_arg("20260210") == date(2026, 2, 10)
    assert _parse_date_arg("2026-02-10") == date(2026, 2, 10)


# ===========================================================================
# Runner
# ===========================================================================

def _run_all():
    """Simple test runner that doesn't depend on pytest."""
    test_functions = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    errors = []

    for fn in test_functions:
        name = fn.__name__
        try:
            fn()
            passed += 1
            print(f"  [PASS] {name}")
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  [FAIL] {name}: {e}")

    print(f"\nResults: {passed} passed, {failed} failed out of {passed + failed}")
    if errors:
        print("\nFailures:")
        for name, err in errors:
            print(f"  {name}: {err}")
    return failed == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
