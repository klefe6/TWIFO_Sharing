"""
Purpose: Tests for level sanitization - no inferred/invented price levels.
Author: Kevin Lefebvre
Last Updated: 2026-02-04

Validates:
- Explicit levels (e.g. "gold at 2050") → included
- Vague levels (e.g. "gold near resistance") → no numeric level produced
- Ambiguous numbers (2026, counts "5") → not misclassified as price levels
- Regression: no inference from vague phrasing
"""

from __future__ import annotations

import pytest

from summarize_pdf import sanitize_key_levels, reject_hallucinated_levels


def _mk_sum_json(trade_ideas: list) -> dict:
    return {
        "sections": {"trade_ideas": trade_ideas},
        "extraction": {},
    }


def test_explicit_level_included():
    """Article with explicit level 'gold at 2050' → level is included."""
    source = "Gold rallied to 2,050 in early trading before pulling back."
    ideas = [
        {
            "product": "GC",
            "bias": "Bullish",
            "key_levels": ["Resistance at 2,050", "(not provided in inputs)"],
            "source_quote": "Gold rallied to 2,050 in early trading",
        }
    ]
    js = _mk_sum_json(ideas)
    dropped = sanitize_key_levels(js, source)
    assert dropped == []
    assert "Resistance at 2,050" in js["sections"]["trade_ideas"][0]["key_levels"]


def test_explicit_level_in_source_text():
    """Level appears in source_text even without source_quote → included."""
    source = "Support at 43,000 held for BTC."
    ideas = [
        {
            "product": "BTC",
            "bias": "Neutral",
            "key_levels": ["Support at 43,000"],
            "source_quote": None,
        }
    ]
    js = _mk_sum_json(ideas)
    dropped = sanitize_key_levels(js, source)
    assert dropped == []
    assert "Support at 43,000" in js["sections"]["trade_ideas"][0]["key_levels"]


def test_vague_level_no_number_produced():
    """Article says 'gold near resistance' with no numeric → keep statement, no inferred number."""
    source = "Gold is trading near key resistance with no specific level given."
    ideas = [
        {
            "product": "GC",
            "bias": "Bullish",
            "key_levels": ["Near key resistance"],
            "source_quote": "Gold is trading near key resistance",
        }
    ]
    js = _mk_sum_json(ideas)
    dropped = sanitize_key_levels(js, source)
    # No price-like number in level → kept (no drop)
    assert dropped == []
    assert "Near key resistance" in js["sections"]["trade_ideas"][0]["key_levels"]


def test_inferred_level_dropped():
    """LLM invents '2050' when source has no number → dropped."""
    source = "Gold is trading near key resistance with momentum."
    ideas = [
        {
            "product": "GC",
            "bias": "Bullish",
            "key_levels": ["Resistance at 2,050"],
            "source_quote": "Gold is trading near key resistance",
        }
    ]
    js = _mk_sum_json(ideas)
    dropped = sanitize_key_levels(js, source)
    assert len(dropped) == 1
    assert dropped[0]["level"] == "Resistance at 2,050"
    assert dropped[0]["reason"] == "not_explicit_in_source"
    assert "Resistance at 2,050" not in js["sections"]["trade_ideas"][0]["key_levels"]
    assert "(not provided in inputs)" not in js["sections"]["trade_ideas"][0]["key_levels"]
    # After drop, key_levels should be empty or placeholder
    assert js["sections"]["trade_ideas"][0]["key_levels"] == []


def test_ambiguous_year_not_misclassified():
    """Date '2026' in level → not treated as price level, not dropped."""
    source = "Target date for the project is 2026 with budget of 5 million."
    ideas = [
        {
            "product": "ES",
            "bias": "Neutral",
            "key_levels": ["Target 2026"],
            "source_quote": "Target date 2026",
        }
    ]
    js = _mk_sum_json(ideas)
    dropped = sanitize_key_levels(js, source)
    # 2026 is year-like → excluded from price validation → level kept
    assert dropped == []
    assert "Target 2026" in js["sections"]["trade_ideas"][0]["key_levels"]


def test_ambiguous_count_not_misclassified():
    """Count '5' alone → not a price pattern (no $, no dollars/points)."""
    source = "There are 5 key levels to watch."
    ideas = [
        {
            "product": "GC",
            "bias": "Neutral",
            "key_levels": ["5 key levels"],
            "source_quote": "5 key levels",
        }
    ]
    js = _mk_sum_json(ideas)
    dropped = sanitize_key_levels(js, source)
    # "5" without dollars/points doesn't match _PRICE_PATTERN → kept
    assert dropped == []
    assert "5 key levels" in js["sections"]["trade_ideas"][0]["key_levels"]


def test_placeholder_kept():
    """(not provided in inputs) and similar placeholders are preserved."""
    source = "Gold moved higher with no specific levels."
    ideas = [
        {
            "product": "GC",
            "bias": "Bullish",
            "key_levels": ["(not provided in inputs)"],
            "source_quote": None,
        }
    ]
    js = _mk_sum_json(ideas)
    dropped = sanitize_key_levels(js, source)
    assert dropped == []
    assert js["sections"]["trade_ideas"][0]["key_levels"] == ["(not provided in inputs)"]


def test_regression_no_inference_from_vague_phrasing():
    """Regression: 'around recent highs' with invented 2100 → dropped."""
    source = "Gold is around recent highs with strong momentum."
    ideas = [
        {
            "product": "GC",
            "bias": "Bullish",
            "key_levels": ["Resistance around 2,100", "Support at 2,050"],
            "source_quote": "around recent highs",
        }
    ]
    js = _mk_sum_json(ideas)
    dropped = sanitize_key_levels(js, source)
    assert len(dropped) == 2  # Both invented
    levels_kept = js["sections"]["trade_ideas"][0]["key_levels"]
    assert "2,100" not in " ".join(levels_kept)
    assert "2,050" not in " ".join(levels_kept)


def test_reject_hallucinated_levels_still_works():
    """reject_hallucinated_levels detects levels not in source."""
    source = "Gold rallied but no levels were stated."
    js = _mk_sum_json([
        {
            "product": "GC",
            "bias": "Bullish",
            "key_levels": ["Resistance at 2,050"],
            "source_quote": None,
        }
    ])
    has_h, reason = reject_hallucinated_levels(js, source)
    assert has_h is True
    assert "2,050" in reason
    assert "not found in source" in reason
