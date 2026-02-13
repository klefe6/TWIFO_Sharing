"""
Tests for llm_summarize_to_json() schema robustness.

Feeds the JSON-building portion of the function with various sparse/malformed
LLM responses and verifies no UnboundLocalError, KeyError, or TypeError occurs.

Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_llm_summarize(api_response: dict, meta: dict | None = None) -> dict:
    """
    Call llm_summarize_to_json with a mocked OpenAI client that returns
    the given api_response dict as its JSON output.

    This exercises the full JSON-building code path without hitting the API.
    """
    if meta is None:
        meta = {
            "title": "Test Article",
            "provider": "TEST",
            "published_date": "2026-02-12",
            "horizon": "Intraday",
            "extraction": {},
        }

    json_str = json.dumps(api_response)

    # Build a mock response object that matches the OpenAI Responses API shape
    content_item = MagicMock()
    content_item.type = "output_text"
    content_item.text = json_str

    output_item = MagicMock()
    output_item.content = [content_item]

    response_obj = MagicMock()
    response_obj.output = [output_item]

    mock_client = MagicMock()
    mock_client.responses.create.return_value = response_obj
    mock_client.base_url = "https://test.example.com"

    # Inject mock modules for the in-function imports
    mock_openai_client = MagicMock()
    mock_openai_client.get_client = MagicMock(return_value=mock_client)
    mock_auth_env = MagicMock()
    mock_auth_env.describe_key = MagicMock(return_value="test_key")

    with patch.dict(sys.modules, {
        "openai_client": mock_openai_client,
        "auth_env": mock_auth_env,
    }):
        # Force reimport so the function picks up patched modules
        import importlib
        import summarize_pdf
        importlib.reload(summarize_pdf)
        return summarize_pdf.llm_summarize_to_json(
            "Some article text for testing.",
            meta=meta,
            model="gpt-4o-mini",
        )


def _assert_valid_structure(result: dict) -> None:
    """Verify the output has the mandatory top-level keys and correct types."""
    assert "schema_version" in result, "Missing schema_version"
    assert "kind" in result, "Missing kind"
    assert "meta" in result, "Missing meta"
    assert "sections" in result, "Missing sections"
    assert "extraction" in result, "Missing extraction"

    sections = result["sections"]
    for key in [
        "what_moved_today", "what_can_move_tomorrow", "trade_ideas",
        "tldr", "what_occurred", "forward_watch", "warnings",
        "tips_reminders", "cross_asset_impacts", "scenarios",
    ]:
        assert key in sections, f"Missing sections.{key}"
        assert isinstance(sections[key], list), f"sections.{key} should be list, got {type(sections[key])}"

    assert isinstance(result.get("fingerprint_quotes"), list), "fingerprint_quotes not a list"
    assert isinstance(result.get("numeric_claims"), list), "numeric_claims not a list"
    assert isinstance(result.get("chart_text_sources_used"), list), "chart_text_sources_used not a list"
    assert isinstance(result.get("chart_observations"), list), "chart_observations not a list"
    assert isinstance(result.get("volatility_impact"), dict), "volatility_impact not a dict"
    assert isinstance(result.get("sentiment_indicator"), dict), "sentiment_indicator not a dict"
    assert isinstance(result.get("summary_score_0_10"), (int, float)), "score not numeric"
    assert isinstance(result.get("chart_score_0_3"), (int, float)), "chart_score not numeric"


# ===========================================================================
# Test cases
# ===========================================================================

def test_sparse_response_no_trade_ideas_no_entities():
    """Minimal valid LLM response — no trade ideas, no entities, bare sections."""
    api_response = {
        "what_moved_today": ["ES fell 0.5%"],
        "what_can_move_tomorrow": [],
        "tldr": ["Fed hawkish", "ES down", "Watch CPI"],
        "what_occurred": [],
        "forward_watch": [],
        "warnings": [],
        "tips_reminders": [],
        "cross_asset_impacts": [],
        "scenarios": [],
        "score_0_10": 5,
        # trade_ideas, _meta, fingerprint_quotes, numeric_claims — all missing
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    assert result["sections"]["trade_ideas"] == []
    assert result["meta"]["primary_entities"] == []
    print("  [PASS] sparse response (no trade_ideas, no entities)")


def test_completely_empty_response():
    """LLM returned {}."""
    result = _call_llm_summarize({})
    _assert_valid_structure(result)
    assert result["sections"]["trade_ideas"] == []
    assert result["sections"]["tldr"] == []
    # Products should exist (inferred from text or Macro fallback)
    assert isinstance(result["meta"]["products"], list)
    assert len(result["meta"]["products"]) >= 1
    print("  [PASS] completely empty response")


def test_trade_ideas_as_flat_array_v12():
    """v1.2 format: trade_ideas is a flat array of objects."""
    api_response = {
        "trade_ideas": [
            {"product": "ES", "bias": "Bearish", "catalyst": "CPI", "key_levels": ["5,450", "5,400"]},
            {"product": "GC", "bias": "Bullish", "catalyst": "Safe haven"},
        ],
        "tldr": ["ES down on CPI", "Gold up", "Watch rates"],
        "score_0_10": 7,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    assert len(result["sections"]["trade_ideas"]) == 2
    assert result["sections"]["trade_ideas"][0]["product"] == "ES"
    assert result["sections"]["trade_ideas"][0]["category"] == "indices"
    print("  [PASS] v1.2 flat array trade_ideas")


def test_trade_ideas_as_v11_product_grid():
    """v1.1 format: trade ideas under products.indices.ES, etc."""
    api_response = {
        "products": {
            "indices": {
                "ES": {"bias": "Bullish", "catalyst": "FOMC", "key_levels": ["5,500"]},
                "NQ": {"bias": "Neutral", "catalyst": "", "key_levels": []},
            }
        },
        "tldr": ["FOMC coming", "ES buy dips", "NQ range-bound"],
        "score_0_10": 6,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    assert len(result["sections"]["trade_ideas"]) == 2
    assert result["sections"]["trade_ideas"][0]["product"] == "ES"
    print("  [PASS] v1.1 product grid trade_ideas")


def test_trade_ideas_missing_entirely():
    """trade_ideas key absent from response."""
    api_response = {
        "tldr": ["Markets quiet", "No setups", "Wait for data"],
        "score_0_10": 3,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    assert result["sections"]["trade_ideas"] == []
    print("  [PASS] trade_ideas missing entirely")


def test_trade_ideas_is_string():
    """LLM returned trade_ideas as a string (malformed)."""
    api_response = {
        "trade_ideas": "ES is bearish",
        "tldr": ["ES bearish", "Caution advised", "Short term risk"],
        "score_0_10": 4,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    assert result["sections"]["trade_ideas"] == []
    print("  [PASS] trade_ideas is string (gracefully ignored)")


def test_trade_ideas_is_none():
    """LLM returned trade_ideas: null."""
    api_response = {
        "trade_ideas": None,
        "tldr": ["Nothing notable", "Quiet session", "Wait"],
        "score_0_10": 2,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    assert result["sections"]["trade_ideas"] == []
    print("  [PASS] trade_ideas is None")


def test_sections_as_strings_not_lists():
    """LLM returned section values as strings instead of arrays."""
    api_response = {
        "what_moved_today": "ES fell 1%",
        "what_can_move_tomorrow": "CPI tomorrow",
        "tldr": "Fed hawkish. ES down. Watch CPI.",
        "score_0_10": 5,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    # _safe_list wraps strings into single-element lists
    assert len(result["sections"]["what_moved_today"]) == 1
    assert result["sections"]["what_moved_today"][0]["text"] == "ES fell 1%"
    print("  [PASS] string sections wrapped into lists")


def test_malformed_volatility_and_sentiment():
    """LLM returned volatility_impact as string and sentiment as null."""
    api_response = {
        "volatility_impact": "High",
        "sentiment_indicator": None,
        "tldr": ["Vol spike", "Risk off", "Hedge"],
        "score_0_10": 8,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    assert result["volatility_impact"]["expected_volatility"] == "Medium"  # Default
    assert result["sentiment_indicator"]["risk_on_off"] == "Neutral"  # Default
    print("  [PASS] malformed volatility/sentiment get safe defaults")


def test_score_as_string():
    """LLM returned score_0_10 as a string like '7'."""
    api_response = {
        "score_0_10": "7",
        "chart_score_0_3": "2",
        "tldr": ["Good article", "Actionable", "Clear levels"],
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    assert result["summary_score_0_10"] == 7
    assert result["chart_score_0_3"] == 2
    print("  [PASS] string scores parsed to int")


def test_score_out_of_range():
    """LLM returned score_0_10: 15 (out of range)."""
    api_response = {
        "score_0_10": 15,
        "chart_score_0_3": -1,
        "tldr": ["Test", "Test", "Test"],
    }
    result = _call_llm_summarize(api_response)
    assert result["summary_score_0_10"] == 10  # Clamped
    assert result["chart_score_0_3"] == 0  # Clamped
    print("  [PASS] out-of-range scores clamped")


def test_products_as_list_not_dict():
    """LLM returned products as a list (malformed)."""
    api_response = {
        "products": ["ES", "NQ", "GC"],
        "tldr": ["Multiple products", "Broad view", "Mixed signals"],
        "score_0_10": 5,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    # products_structured should have been reset to {}
    # Products should be inferred from text or fallback to Macro
    assert isinstance(result["meta"]["products"], list)
    print("  [PASS] products as list (gracefully handled)")


def test_meta_with_primary_entities():
    """v1.2 _meta.primary_entities provided and capped at 6."""
    api_response = {
        "_meta": {
            "primary_entities": ["ES", "NQ", "GC", "SI", "BTC", "ETH", "VIX", "CL"]
        },
        "tldr": ["Multi-asset", "Broad rally", "Risk on"],
        "score_0_10": 7,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    assert len(result["meta"]["primary_entities"]) == 6  # Capped
    print("  [PASS] primary_entities capped at 6")


def test_numeric_claims_with_malformed_entries():
    """Some numeric_claims entries are missing required fields."""
    api_response = {
        "numeric_claims": [
            {"value": "5,450", "context": "ES level", "source_quote": "at 5,450"},
            {"context": "missing value"},  # No 'value' key
            "not a dict",  # Not a dict
            {"value": "4.25%"},  # No context (allowed; defaults to "")
        ],
        "tldr": ["ES at 5,450", "Yields at 4.25%", "Data-driven"],
        "score_0_10": 6,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    # Only entries with "value" key pass validation
    assert len(result["numeric_claims"]) == 2
    print("  [PASS] malformed numeric_claims filtered correctly")


def test_key_levels_as_various_types():
    """Trade idea key_levels can be string, list, int, or missing."""
    api_response = {
        "trade_ideas": [
            {"product": "ES", "key_levels": "5,450"},         # String
            {"product": "NQ", "key_levels": ["18,500"]},      # List
            {"product": "GC", "key_levels": 2050},            # Int (malformed)
            {"product": "ZN"},                                  # Missing
        ],
        "tldr": ["Test", "Test", "Test"],
        "score_0_10": 5,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    ideas = result["sections"]["trade_ideas"]
    assert len(ideas) == 4
    assert ideas[0]["key_levels"] == ["5,450"]  # String wrapped
    assert ideas[1]["key_levels"] == ["18,500"]  # List kept
    assert ideas[2]["key_levels"] == []  # Int → empty list
    assert ideas[3]["key_levels"] == []  # Missing → empty list
    print("  [PASS] key_levels of various types handled")


def test_bare_minimum_tldr_and_meta_only():
    """User-specified test: LLM returns only { "tldr": [], "meta": {} }.

    This is the absolute minimum: an empty tldr and a "meta" key (which is
    NOT the same as "_meta" — the code reads "_meta").  Must complete with
    a fully valid output and no exception.
    """
    api_response = {
        "tldr": [],
        "meta": {},
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    assert result["sections"]["tldr"] == []
    assert result["sections"]["trade_ideas"] == []
    assert result["sections"]["what_moved_today"] == []
    assert result["meta"]["primary_entities"] == []
    assert result["fingerprint_quotes"] == []
    assert result["numeric_claims"] == []
    assert result["chart_text_sources_used"] == []
    assert isinstance(result["volatility_impact"], dict)
    assert isinstance(result["sentiment_indicator"], dict)
    assert result["summary_score_0_10"] == 0
    assert result["chart_score_0_3"] == 0
    assert result["explain_like_refresher"] == "(none)"
    print("  [PASS] bare minimum { tldr: [], meta: {} }")


def test_volatility_partial_dict():
    """LLM returns volatility_impact with only one inner key."""
    api_response = {
        "volatility_impact": {"expected_volatility": "High"},
        "tldr": ["Vol spike", "Risk off", "Hedge"],
        "score_0_10": 8,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    vi = result["volatility_impact"]
    assert vi["expected_volatility"] == "High"
    # Missing inner keys should get defaults
    assert vi["drivers"] == []
    assert vi["directional_skew"] == "Two-sided"
    assert vi["confidence_0_100"] == 50
    print("  [PASS] volatility partial dict (defaults filled)")


def test_sentiment_partial_dict():
    """LLM returns sentiment_indicator with only one inner key."""
    api_response = {
        "sentiment_indicator": {"risk_on_off": "Risk-On"},
        "tldr": ["Bull run", "Green across board", "Momentum"],
        "score_0_10": 9,
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    si = result["sentiment_indicator"]
    assert si["risk_on_off"] == "Risk-On"
    assert si["confidence_0_100"] == 50
    assert si["rationale"] == "(none)"
    print("  [PASS] sentiment partial dict (defaults filled)")


def test_score_as_bool():
    """LLM returns score_0_10: true (JSON boolean)."""
    api_response = {
        "score_0_10": True,
        "chart_score_0_3": False,
        "tldr": ["Test", "Test", "Test"],
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    assert result["summary_score_0_10"] == 0  # bool → default, not 1
    assert result["chart_score_0_3"] == 0     # bool → default, not 0 via int()
    print("  [PASS] boolean scores default to 0")


def test_explain_like_refresher_empty_string():
    """LLM returns explain_like_refresher as empty string."""
    api_response = {
        "explain_like_refresher": "",
        "tldr": ["Test", "Test", "Test"],
    }
    result = _call_llm_summarize(api_response)
    assert result["explain_like_refresher"] == "(none)"
    print("  [PASS] empty explain_like_refresher defaults to (none)")


def test_sections_as_list_of_dicts():
    """LLM returns section bullets as [{"text": "..."}, ...] instead of strings."""
    api_response = {
        "what_moved_today": [{"text": "ES fell 1%"}, {"text": "Gold up 0.5%"}],
        "tldr": [{"text": "Fed hawkish"}, {"text": "ES down"}, {"text": "Watch CPI"}],
    }
    result = _call_llm_summarize(api_response)
    _assert_valid_structure(result)
    # _safe_list should extract "text" field from dicts
    assert result["sections"]["what_moved_today"][0]["text"] == "ES fell 1%"
    assert result["sections"]["tldr"][0]["text"] == "Fed hawkish"
    print("  [PASS] list-of-dicts sections handled (text extracted)")


def test_d5_d6_d7_compatible_output():
    """Verify the output structure is compatible with D.5, D.6, D.7.

    Each downstream consumer needs specific keys to exist as specific types.
    This test creates a minimal output and runs type assertions matching
    what each consumer actually reads.
    """
    api_response = {
        "tldr": ["ES at 5,450"],
        "what_moved_today": ["ES fell"],
        "numeric_claims": [{"value": "5,450", "context": "ES", "source_quote": "ES at 5,450"}],
        "fingerprint_quotes": ["ES at 5,450"],
        "score_0_10": 5,
    }
    result = _call_llm_summarize(api_response)

    # D.5 verify_and_scrub_numerics needs:
    assert isinstance(result.get("meta"), dict), "D.5 needs meta as dict"
    assert isinstance(result.get("numeric_claims"), list), "D.5 needs numeric_claims as list"
    # D.5 walks entire tree — no direct key requirements beyond these

    # D.6 similarity_guard needs:
    sections = result.get("sections", {})
    assert isinstance(sections, dict), "D.6 needs sections as dict"
    for k in ("tldr", "what_moved_today", "what_can_move_tomorrow"):
        items = sections.get(k, [])
        assert isinstance(items, list), f"D.6 needs sections.{k} as list"
        for item in items:
            assert isinstance(item, dict), f"D.6 expects dict items in sections.{k}"
            assert "text" in item, f"D.6 reads item['text'] from sections.{k}"

    # D.7 critic_pass needs:
    assert isinstance(result.get("fingerprint_quotes"), list), "D.7 needs fingerprint_quotes as list"
    trade_ideas = sections.get("trade_ideas", [])
    assert isinstance(trade_ideas, list), "D.7 needs sections.trade_ideas as list"

    print("  [PASS] output compatible with D.5, D.6, D.7")


# ===========================================================================
# Runner
# ===========================================================================

def _run_all():
    """Simple test runner (avoids pytest/selenium issues)."""
    tests = [
        ("sparse_no_trade_ideas_no_entities", test_sparse_response_no_trade_ideas_no_entities),
        ("completely_empty_response", test_completely_empty_response),
        ("v12_flat_array", test_trade_ideas_as_flat_array_v12),
        ("v11_product_grid", test_trade_ideas_as_v11_product_grid),
        ("trade_ideas_missing", test_trade_ideas_missing_entirely),
        ("trade_ideas_string", test_trade_ideas_is_string),
        ("trade_ideas_none", test_trade_ideas_is_none),
        ("sections_as_strings", test_sections_as_strings_not_lists),
        ("malformed_volatility_sentiment", test_malformed_volatility_and_sentiment),
        ("score_as_string", test_score_as_string),
        ("score_out_of_range", test_score_out_of_range),
        ("products_as_list", test_products_as_list_not_dict),
        ("primary_entities_capped", test_meta_with_primary_entities),
        ("malformed_numeric_claims", test_numeric_claims_with_malformed_entries),
        ("key_levels_various_types", test_key_levels_as_various_types),
        ("bare_minimum_tldr_and_meta", test_bare_minimum_tldr_and_meta_only),
        ("volatility_partial_dict", test_volatility_partial_dict),
        ("sentiment_partial_dict", test_sentiment_partial_dict),
        ("score_as_bool", test_score_as_bool),
        ("explain_empty_string", test_explain_like_refresher_empty_string),
        ("sections_as_list_of_dicts", test_sections_as_list_of_dicts),
        ("d5_d6_d7_compatible", test_d5_d6_d7_compatible_output),
    ]

    print("=" * 70)
    print("Running _build_sum_json / llm_summarize_to_json robustness tests")
    print("=" * 70)
    print()

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed out of {passed + failed}")
    return failed == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
