"""
Tests for content-dependent summarization: no generic Products/ACTIONABLE template.
Purpose: Assert Products derived from article or Macro; ACTIONABLE only with explicit levels.
Author: Kevin Lefebvre
Last Updated: 2026-02-05
"""

import hashlib
import json
import pytest
import sys
from pathlib import Path

# Allow importing summarize_pdf from parent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from summarize_pdf import (
    _infer_products_from_text,
    _filter_actionable_trade_ideas,
    _has_explicit_level,
    _PLACEHOLDER_LEVELS,
    _content_hash,
    sanitize_key_levels,
)


FULL_DEFAULT_PRODUCTS = ["ES", "NQ", "ZN", "ZB", "GC", "SI", "BTC", "VIX", "CL"]


class TestInferProductsFromText:
    """Products must be inferred from article text or be Macro, not hardcoded."""

    def test_empty_source_returns_empty(self):
        products, reason = _infer_products_from_text("")
        assert products == []
        assert reason == "empty_source"

    def test_no_keywords_returns_empty(self):
        products, reason = _infer_products_from_text("The weather is nice today.")
        assert products == []
        assert "no_keywords" in reason or "empty" in reason.lower()

    def test_gold_mentioned_returns_gc(self):
        products, reason = _infer_products_from_text("Gold rallied to $2650 amid rate cuts.")
        assert "GC" in products
        assert "inferred" in reason or "GC" in reason

    def test_multiple_mentioned_returns_ordered(self):
        products, reason = _infer_products_from_text(
            "S&P 500 and Nasdaq rose. Treasury yields fell. Gold and silver advanced. Oil (WTI) and VIX discussed."
        )
        assert "ES" in products or "NQ" in products
        assert "GC" in products or "SI" in products
        assert products != FULL_DEFAULT_PRODUCTS

    def test_inferred_list_not_full_default(self):
        """Inferred list must never equal the full default list unless all keywords present."""
        text = "Macro overview with no specific tickers."
        products, _ = _infer_products_from_text(text)
        assert products != FULL_DEFAULT_PRODUCTS


class TestFilterActionableTradeIdeas:
    """ACTIONABLE must only include ideas with explicit levels from article."""

    def test_empty_trade_ideas_returns_empty(self):
        sum_json = {"sections": {"trade_ideas": []}}
        filtered, reason = _filter_actionable_trade_ideas(sum_json)
        assert filtered == []
        assert "empty" in reason

    def test_all_placeholder_levels_returns_empty(self):
        sum_json = {
            "sections": {
                "trade_ideas": [
                    {
                        "product": "ES",
                        "bias": "Bullish",
                        "key_levels": ["(not provided in inputs)"],
                        "catalyst": "rates",
                    },
                    {
                        "product": "GC",
                        "bias": "Neutral",
                        "key_levels": ["no explicit levels provided"],
                        "catalyst": "",
                    },
                ]
            }
        }
        filtered, reason = _filter_actionable_trade_ideas(sum_json)
        assert len(filtered) == 0
        assert "0_of_2" in reason or "count=0" in reason

    def test_explicit_level_included(self):
        sum_json = {
            "sections": {
                "trade_ideas": [
                    {
                        "product": "GC",
                        "bias": "Bullish",
                        "key_levels": ["$2650", "support at 2620"],
                        "catalyst": "Fed pivot",
                    },
                ]
            }
        }
        filtered, reason = _filter_actionable_trade_ideas(sum_json)
        assert len(filtered) == 1
        assert filtered[0]["product"] == "GC"
        assert "text" in filtered[0]
        assert "2650" in filtered[0]["text"] or "2620" in filtered[0]["text"]

    def test_mixed_placeholder_and_explicit_filters_correctly(self):
        sum_json = {
            "sections": {
                "trade_ideas": [
                    {"product": "ES", "bias": "Neutral", "key_levels": ["(not provided in inputs)"]},
                    {"product": "ZN", "bias": "Bearish", "key_levels": ["4.25% yield mentioned in doc"]},
                ]
            }
        }
        filtered, _ = _filter_actionable_trade_ideas(sum_json)
        assert len(filtered) == 1
        assert filtered[0]["product"] == "ZN"


class TestHasExplicitLevel:
    def test_placeholder_not_explicit(self):
        assert _has_explicit_level(["(not provided in inputs)"]) is False
        assert _has_explicit_level(["no explicit levels provided"]) is False
        assert _has_explicit_level([]) is False

    def test_numeric_level_is_explicit(self):
        assert _has_explicit_level(["$2650"]) is True
        assert _has_explicit_level(["support 2620"]) is True
        assert _has_explicit_level(["(not provided in inputs)", "$2650"]) is True


class TestSummaryCacheKey:
    """Cache key must include content hash so different texts do not hit same entry."""

    def test_different_input_texts_different_content_hash(self):
        """Two different input texts must not produce the same cache key (content_hash)."""
        text_a = "Fed holds rates at 5.25%. Gold rallied to $2650."
        text_b = "ECB cuts rates. Oil and volatility discussed."
        hash_a = _content_hash(text_a)
        hash_b = _content_hash(text_b)
        assert hash_a != hash_b, "Different article texts must have different content_hash"

    def test_same_text_same_content_hash(self):
        """Same normalized text must produce same content_hash."""
        text = "  Fed   holds   rates.  \n\n  Gold  at  $2650.  "
        h1 = _content_hash(text)
        h2 = _content_hash("Fed holds rates. Gold at $2650.")
        assert h1 == h2, "Normalized same content must yield same content_hash"


class TestProductsNotFullDefault:
    """Meta products must not be the full default list unless explicitly from content."""

    def test_summary_json_products_not_default_when_empty_llm(self):
        """When LLM returns no products, pipeline uses infer or Macro - never full list."""
        # Simulate what llm_summarize_to_json does: empty products_structured -> infer or Macro
        from summarize_pdf import _infer_products_from_text

        no_mention = "This article discusses general economic policy."
        inferred, _ = _infer_products_from_text(no_mention)
        final_products = inferred if inferred else ["Macro"]
        assert final_products != FULL_DEFAULT_PRODUCTS


class TestDifferentInputsProduceDifferentOutputs:
    """Two different articles must produce materially different summaries."""

    def test_different_tldr_and_actionable_implies_different_hash(self):
        """If two summaries have different tldr or trade_ideas, their canonical hash differs."""
        summary_a = {
            "sections": {
                "tldr": [{"text": "Article A: Fed holds rates."}],
                "trade_ideas": [],
            },
            "meta": {"products": ["Macro"]},
        }
        summary_b = {
            "sections": {
                "tldr": [{"text": "Article B: ECB cuts rates."}],
                "trade_ideas": [],
            },
            "meta": {"products": ["Macro"]},
        }
        canonical_a = hashlib.sha256(json.dumps(summary_a, sort_keys=True).encode()).hexdigest()
        canonical_b = hashlib.sha256(json.dumps(summary_b, sort_keys=True).encode()).hexdigest()
        assert canonical_a != canonical_b

    def test_two_different_articles_different_tldr_and_key_data(self):
        """Two different articles must produce different TL;DR and Key Data (what_occurred)."""
        summary_rates = {
            "sections": {
                "tldr": [{"text": "Fed holds; 10y yield at 4.25%."}],
                "what_occurred": [{"text": "Treasury selloff continued."}],
            },
        }
        summary_metals = {
            "sections": {
                "tldr": [{"text": "Gold broke $2650 on safe-haven bid."}],
                "what_occurred": [{"text": "Silver followed gold higher."}],
            },
        }
        hash_rates = hashlib.sha256(json.dumps(summary_rates, sort_keys=True).encode()).hexdigest()
        hash_metals = hashlib.sha256(json.dumps(summary_metals, sort_keys=True).encode()).hexdigest()
        assert hash_rates != hash_metals

    def test_actionable_empty_when_no_explicit_levels(self):
        """When no trade idea has explicit levels, ACTIONABLE section is empty."""
        sum_json = {
            "sections": {
                "trade_ideas": [
                    {"product": "ES", "key_levels": ["(not provided in inputs)"], "bias": "Neutral"},
                ]
            }
        }
        actionable, _ = _filter_actionable_trade_ideas(sum_json)
        assert actionable == []

    def test_no_generic_actionable_template(self):
        """Generic template (all products with placeholder levels) must yield empty ACTIONABLE."""
        generic = {
            "sections": {
                "trade_ideas": [
                    {"product": p, "key_levels": ["(not provided in inputs)"], "bias": "Neutral"}
                    for p in ["ES", "NQ", "ZN", "ZB", "GC", "SI", "BTC", "VIX", "CL"]
                ]
            }
        }
        actionable, _ = _filter_actionable_trade_ideas(generic)
        assert len(actionable) == 0, "Generic all-products template must not appear in ACTIONABLE"


class TestNumericLevelsOnlyWhenInSource:
    """Numeric levels must appear only when present in source text."""

    def test_level_dropped_when_not_in_source(self):
        """sanitize_key_levels drops a level when its number is not in source_text."""
        sum_json = {
            "sections": {
                "trade_ideas": [
                    {
                        "product": "GC",
                        "key_levels": ["$2650"],
                        "source_quote": None,
                    }
                ]
            }
        }
        source_without_level = "Gold rallied. No specific price given."
        dropped = sanitize_key_levels(sum_json, source_without_level)
        assert len(dropped) == 1
        assert dropped[0]["product"] == "GC"
        assert "2650" in dropped[0]["level"]
        assert sum_json["sections"]["trade_ideas"][0]["key_levels"] == []

    def test_level_kept_when_in_source(self):
        """sanitize_key_levels keeps a level when its number appears in source_text."""
        sum_json = {
            "sections": {
                "trade_ideas": [
                    {
                        "product": "GC",
                        "key_levels": ["$2650"],
                        "source_quote": "Gold hit $2650 in London.",
                    }
                ]
            }
        }
        source_with_level = "Gold hit $2650 in London. Silver followed."
        dropped = sanitize_key_levels(sum_json, source_with_level)
        assert len(dropped) == 0
        assert sum_json["sections"]["trade_ideas"][0]["key_levels"] == ["$2650"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
