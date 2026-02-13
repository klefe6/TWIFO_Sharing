"""
Test: Rollup No-Hallucination Validation
Purpose: Verify rollups only include exact strings from article summaries (no invented levels)
Author: Kevin Lefebvre
Last Updated: 2026-02-04
"""

import re
from pathlib import Path
from datetime import date
from rollups import build_daily_rollup

def test_rollup_no_hallucinated_levels():
    """
    Test that rollup aggregation:
    1. Only includes key_levels that exist in source articles
    2. Includes volatility_impact when present in articles
    3. Maintains global product ordering (Indices → Rates → Metals → Crypto → Others)
    4. Deduplicates trade ideas correctly
    5. Fails closed if no trade ideas exist
    """
    
    # Create mock article summaries with known key_levels
    article1 = {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {
            "provider": "JPM",
            "title": "Test Article 1",
            "published_date": "20260126",
            "products": ["ES", "GC", "BTC"],
            "horizon": "d"
        },
        "sections": {
            "trade_ideas": [
                {
                    "product": "ES",
                    "bias": "Bull",
                    "catalyst": "Strong employment data",
                    "setup": "If ES holds above 5,000",
                    "key_levels": "Support at 5,000, resistance at 5,100",
                    "risk": "Break below 4,950 invalidates",
                    "time_horizon": "1-3D",
                    "volatility_impact": "Moderate volatility expected on NFP release"
                },
                {
                    "product": "GC",
                    "bias": "Bear",
                    "catalyst": "Rising yields",
                    "setup": "If GC breaks below 2,000",
                    "key_levels": "Resistance at 2,050, support at 1,980",
                    "risk": "Above 2,050 negates bearish case",
                    "time_horizon": "1-2W"
                }
            ],
            "tldr": [{"text": "Markets showing strength", "sources": ["JPM"]}],
            "what_occurred": [],
            "forward_watch": []
        },
        "volatility_impact": "High volatility expected this week"
    }
    
    article2 = {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {
            "provider": "DB",
            "title": "Test Article 2",
            "published_date": "20260126",
            "products": ["NQ", "ZN", "GC"],
            "horizon": "w"
        },
        "sections": {
            "trade_ideas": [
                {
                    "product": "NQ",
                    "bias": "Bull",
                    "catalyst": "Tech earnings beat",
                    "setup": "Long above 18,000",
                    "key_levels": "Support at 17,800, resistance at 18,500",
                    "risk": "Below 17,500 invalidates",
                    "time_horizon": "1-2W",
                    "volatility_impact": "Earnings volatility spike expected"
                },
                {
                    "product": "GC",
                    "bias": "Neutral",
                    "catalyst": "Consolidation phase",
                    "setup": "Wait for breakout",
                    "key_levels": "Range 1,980-2,050",
                    "risk": "False breakout risk",
                    "time_horizon": "1-2W"
                },
                {
                    "product": "ZN",
                    "bias": "Bear",
                    "catalyst": "Fed hawkish stance",
                    "setup": "Short on rallies",
                    "key_levels": "Resistance at 112, support at 110",
                    "risk": "Above 113 negates",
                    "time_horizon": "1-2W"
                },
                {
                    "product": "BTC",
                    "bias": "Bull",
                    "catalyst": "Institutional inflows",
                    "setup": "Long above 45,000",
                    "key_levels": "Support at 43,000, resistance at 48,000",
                    "risk": "Below 42,000 invalidates",
                    "time_horizon": "1-2W"
                }
            ],
            "tldr": [{"text": "Mixed signals across assets", "sources": ["DB"]}],
            "what_occurred": [],
            "forward_watch": []
        }
    }
    
    # Add model to one article so meta.model is derived (not "aggregated")
    article1["meta"]["model"] = "gpt-4o-mini"

    # Build rollup
    test_date = date(2026, 1, 26)
    rollup = build_daily_rollup(test_date, [article1, article2], min_articles_required=1)
    
    # Extract trade ideas from rollup
    trade_ideas = rollup.get("sections", {}).get("trade_ideas", [])
    
    print("\n" + "="*80)
    print("TEST: Rollup No-Hallucination Validation")
    print("="*80)
    
    # Test 1: Verify all products are present
    products_in_rollup = {t["product"] for t in trade_ideas}
    expected_products = {"ES", "NQ", "GC", "ZN", "BTC"}
    assert products_in_rollup == expected_products, f"Missing products: {expected_products - products_in_rollup}"
    print("[PASS] Test 1: All products present in rollup")

    # Test 1b: meta.generated_at_iso must be timezone-aware (ends with Z or +/-HH:MM)
    generated_at = rollup.get("meta", {}).get("generated_at_iso", "")
    assert generated_at, "meta.generated_at_iso must be set"
    assert (
        generated_at.endswith("Z") or re.search(r"[+-]\d{2}:\d{2}$", generated_at)
    ), f"generated_at_iso must be timezone-aware (end with Z or +/-HH:MM): got {generated_at}"
    print(f"[PASS] Test 1b: generated_at_iso is timezone-aware: {generated_at}")

    # Test 1c: meta.model must be non-empty string (never null)
    model = rollup.get("meta", {}).get("model")
    assert model is not None, "meta.model must not be null"
    assert isinstance(model, str) and model.strip(), f"meta.model must be non-empty string: got {model!r}"
    print(f"[PASS] Test 1c: meta.model is non-empty: {model}")
    
    # Test 2: Verify global product ordering (Indices -> Rates -> Metals -> Crypto)
    product_order = [t["product"] for t in trade_ideas]
    # Expected order: ES, NQ (indices), ZN (rates), GC (metals), BTC (crypto)
    expected_order = ["ES", "NQ", "ZN", "GC", "BTC"]
    assert product_order == expected_order, f"Product order incorrect: {product_order} != {expected_order}"
    print(f"[PASS] Test 2: Global product ordering correct: {' -> '.join(product_order)}")
    
    # Test 3: Verify key_levels are ONLY from source articles (no hallucination)
    for trade_idea in trade_ideas:
        product = trade_idea["product"]
        key_levels = trade_idea.get("key_levels", "")
        
        # Check that key_levels exist in at least one source article
        found_in_article = False
        for article in [article1, article2]:
            article_trades = article.get("sections", {}).get("trade_ideas", [])
            for at in article_trades:
                if at.get("product") == product and at.get("key_levels"):
                    # Verify the rollup key_levels is a subset/combination of article key_levels
                    article_levels = at.get("key_levels", "")
                    if article_levels in key_levels or key_levels in article_levels:
                        found_in_article = True
                        break
            if found_in_article:
                break
        
        if key_levels:  # Only check if key_levels exist
            assert found_in_article, f"HALLUCINATION DETECTED: {product} key_levels '{key_levels}' not found in source articles"
    
    print("[PASS] Test 3: No hallucinated key_levels detected")
    
    # Test 4: Verify volatility_impact is aggregated
    volatility_found = False
    for trade_idea in trade_ideas:
        vol_impact = trade_idea.get("volatility_impact", "")
        if vol_impact:
            volatility_found = True
            # Verify it comes from source articles
            found_in_article = False
            for article in [article1, article2]:
                article_vol = article.get("volatility_impact", "")
                article_trades = article.get("sections", {}).get("trade_ideas", [])
                for at in article_trades:
                    trade_vol = at.get("volatility_impact", "")
                    if (article_vol and article_vol in vol_impact) or (trade_vol and trade_vol in vol_impact):
                        found_in_article = True
                        break
                if found_in_article:
                    break
            
            assert found_in_article, f"HALLUCINATION: volatility_impact '{vol_impact}' not in source articles"
    
    assert volatility_found, "FAIL: No volatility_impact found in rollup (should be aggregated from articles)"
    print("[PASS] Test 4: Volatility impact aggregated correctly")
    
    # Test 5: Verify deduplication works (GC appears in both articles)
    gc_trade = next((t for t in trade_ideas if t["product"] == "GC"), None)
    assert gc_trade is not None, "GC trade idea missing"
    
    # GC should have combined key_levels from both articles
    gc_levels = gc_trade.get("key_levels", "")
    assert "1,980" in gc_levels or "2,050" in gc_levels, f"GC key_levels incomplete: {gc_levels}"
    
    # GC should have both sources
    gc_sources = gc_trade.get("sources", [])
    assert set(gc_sources) == {"JPM", "DB"}, f"GC sources incorrect: {gc_sources}"
    
    print("[PASS] Test 5: Deduplication working correctly")
    
    # Test 6: Verify fail-closed behavior (test with empty articles)
    try:
        empty_rollup = build_daily_rollup(test_date, [], min_articles_required=1)
        assert False, "Should have raised ValueError for empty articles"
    except ValueError as e:
        assert "Not enough articles" in str(e)
        print("[PASS] Test 6: Fail-closed behavior correct (rejects empty input)")

    # Test 6b: When articles have no model, meta.model falls back to "aggregated"
    article_no_model = {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {"provider": "X", "title": "No Model", "products": []},
        "sections": {"trade_ideas": [], "tldr": [], "what_occurred": [], "forward_watch": []},
    }
    rollup_no_model = build_daily_rollup(test_date, [article_no_model], min_articles_required=1)
    assert rollup_no_model["meta"]["model"] == "aggregated", f"Expected 'aggregated', got {rollup_no_model['meta']['model']}"
    print("[PASS] Test 6b: meta.model fallback to 'aggregated' when articles have no model")
    
    # Test 7: Print full rollup for manual inspection
    print("\n" + "-"*80)
    print("ROLLUP TRADE IDEAS (for manual inspection):")
    print("-"*80)
    for trade_idea in trade_ideas:
        print(f"\n{trade_idea['product']}:")
        print(f"  Bias: {trade_idea['bias']}")
        print(f"  Catalyst: {trade_idea.get('catalyst', 'N/A')}")
        print(f"  Setup: {trade_idea.get('setup', 'N/A')}")
        print(f"  Key Levels: {trade_idea.get('key_levels', 'N/A')}")
        print(f"  Risk: {trade_idea.get('risk', 'N/A')}")
        print(f"  Time Horizon: {trade_idea.get('time_horizon', 'N/A')}")
        print(f"  Volatility Impact: {trade_idea.get('volatility_impact', 'N/A')}")
        print(f"  Sources: {', '.join(trade_idea.get('sources', []))}")
    
    print("\n" + "="*80)
    print("ALL TESTS PASSED")
    print("="*80)
    print("\nSummary:")
    print("  - No hallucinated key_levels detected")
    print("  - Volatility impact aggregated correctly")
    print("  - Global product ordering maintained (Indices -> Rates -> Metals -> Crypto)")
    print("  - Deduplication working correctly")
    print("  - Fail-closed behavior verified")
    print("\n")

if __name__ == "__main__":
    test_rollup_no_hallucinated_levels()
