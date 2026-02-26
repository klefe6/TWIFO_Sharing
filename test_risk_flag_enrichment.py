"""
Test suite for Risk Flag enrichment with product context and time horizon.

Tests the _infer_risk_flag_context function and backward compatibility adapter.
"""
import sys
import datetime as dt
from pathlib import Path

# Add parent directory to path so we can import rollups
sys.path.insert(0, str(Path(__file__).parent))

# We can't directly test _infer_risk_flag_context since it's a nested function,
# so we'll test by building a minimal rollup and checking the warnings output

def test_oil_risk_flag():
    """Test that oil-related risk flags are tagged as COMMODITIES with CL."""
    from rollups import build_daily_rollup
    
    article = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test Article",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []
        },
        "sections": {
            "warnings": [
                "Rising oil price volatility tied to tensions around Iran could negatively impact the yen."
            ]
        }
    }
    
    rollup = build_daily_rollup(
        date_obj=dt.date(2024, 3, 1),
        article_sum_jsons=[article],
        min_articles_required=1
    )
    
    warnings = rollup["sections"]["warnings"]
    assert len(warnings) > 0, "Should have at least one warning"
    
    w = warnings[0]
    print(f"  Oil risk flag: asset_class={w['asset_class']}, products={w['products']}, horizon={w['horizon']}")
    
    # Check enrichment
    assert w["asset_class"] == "commodities", f"Expected 'commodities', got '{w['asset_class']}'"
    assert "CL" in w["products"], f"Expected 'CL' in products, got {w['products']}"
    assert w["horizon"] in ["intraday", "today", "week", "month"], f"Invalid horizon: {w['horizon']}"
    assert w["direction"] in ["bullish", "bearish", "mixed", "unknown"], f"Invalid direction: {w['direction']}"
    assert w["confidence"] is not None, "Confidence should be set"
    
    sys.stdout.buffer.write(b"[PASS] Oil risk flag correctly tagged as COMMODITIES | CL\n")


def test_inflation_risk_flag():
    """Test that inflation risk flags are tagged appropriately with multiple products."""
    from rollups import build_daily_rollup
    
    article = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test Article",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []
        },
        "sections": {
            "warnings": [
                "Sticky inflation could force Fed to keep rates higher for longer."
            ]
        }
    }
    
    rollup = build_daily_rollup(
        date_obj=dt.date(2024, 3, 1),
        article_sum_jsons=[article],
        min_articles_required=1
    )
    
    warnings = rollup["sections"]["warnings"]
    assert len(warnings) > 0, "Should have at least one warning"
    
    w = warnings[0]
    print(f"  Inflation risk flag: asset_class={w['asset_class']}, products={w['products']}, direction={w['direction']}")
    
    # Check enrichment - inflation with Fed/rates context should map to general or rates
    assert w["asset_class"] in ["general", "rates"], f"Expected 'general' or 'rates', got '{w['asset_class']}'"
    assert len(w["products"]) > 0, "Should have inferred products for inflation"
    
    sys.stdout.buffer.write(b"[PASS] Inflation risk flag correctly tagged with appropriate products\n")


def test_rates_risk_flag():
    """Test that Fed/rates risk flags are tagged as RATES."""
    from rollups import build_daily_rollup
    
    article = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test Article",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []
        },
        "sections": {
            "warnings": [
                "Treasury yields could spike if Fed signals more rate hikes."
            ]
        }
    }
    
    rollup = build_daily_rollup(
        date_obj=dt.date(2024, 3, 1),
        article_sum_jsons=[article],
        min_articles_required=1
    )
    
    warnings = rollup["sections"]["warnings"]
    assert len(warnings) > 0, "Should have at least one warning"
    
    w = warnings[0]
    print(f"  Rates risk flag: asset_class={w['asset_class']}, products={w['products']}, direction={w['direction']}")
    
    # Check enrichment
    assert w["asset_class"] == "rates", f"Expected 'rates', got '{w['asset_class']}'"
    assert "US10Y" in w["products"] or "ZN" in w["products"], f"Expected rates products, got {w['products']}"
    
    sys.stdout.buffer.write(b"[PASS] Rates risk flag correctly tagged as RATES with yields products\n")


def test_fx_jpy_risk_flag():
    """Test that JPY risk flags are tagged as FX with USDJPY."""
    from rollups import build_daily_rollup
    
    article = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test Article",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []
        },
        "sections": {
            "warnings": [
                "BOJ policy shift could trigger sharp yen moves next week."
            ]
        }
    }
    
    rollup = build_daily_rollup(
        date_obj=dt.date(2024, 3, 1),
        article_sum_jsons=[article],
        min_articles_required=1
    )
    
    warnings = rollup["sections"]["warnings"]
    assert len(warnings) > 0, "Should have at least one warning"
    
    w = warnings[0]
    print(f"  FX risk flag: asset_class={w['asset_class']}, products={w['products']}, horizon={w['horizon']}")
    
    # Check enrichment
    assert w["asset_class"] == "fx", f"Expected 'fx', got '{w['asset_class']}'"
    assert "USDJPY" in w["products"], f"Expected 'USDJPY' in products, got {w['products']}"
    assert w["horizon"] == "week", f"Expected 'week' horizon, got '{w['horizon']}'"
    
    sys.stdout.buffer.write(b"[PASS] FX risk flag correctly tagged as FX | USDJPY | week\n")


def test_direction_inference():
    """Test that bullish/bearish/mixed direction is inferred correctly."""
    from rollups import build_daily_rollup
    
    test_cases = [
        ("Bullish momentum in equities could extend gains.", "bullish"),
        ("Bearish pressure on gold amid strong dollar.", "bearish"),
        ("Mixed signals from Fed officials create uncertainty.", "mixed"),
        ("Market volatility elevated.", "unknown"),
    ]
    
    for text, expected_direction in test_cases:
        article = {
            "meta": {
                "source_file": "test.pdf",
                "provider": "TEST",
                "title": "Test Article",
                "published_date": "2024-03-01",
                "horizon": "d",
                "products": []
            },
            "sections": {
                "warnings": [text]
            }
        }
        
        rollup = build_daily_rollup(
            date_obj=dt.date(2024, 3, 1),
            article_sum_jsons=[article],
            min_articles_required=1
        )
        
        warnings = rollup["sections"]["warnings"]
        assert len(warnings) > 0, "Should have at least one warning"
        
        w = warnings[0]
        assert w["direction"] == expected_direction, f"Expected direction '{expected_direction}', got '{w['direction']}' for text: {text}"
        print(f"    '{text[:50]}...' -> direction={w['direction']}")
    
    sys.stdout.buffer.write(b"[PASS] Direction inference works correctly\n")


def test_horizon_inference():
    """Test that time horizon is inferred correctly from keywords."""
    from rollups import build_daily_rollup
    
    test_cases = [
        ("Risk of volatility spike intraday around PPI release.", "intraday"),
        ("Watch for overnight gaps in futures.", "today"),
        ("This week could see elevated volatility.", "week"),
        ("Longer-term structural risks remain.", "month"),
    ]
    
    for text, expected_horizon in test_cases:
        article = {
            "meta": {
                "source_file": "test.pdf",
                "provider": "TEST",
                "title": "Test Article",
                "published_date": "2024-03-01",
                "horizon": "d",
                "products": []
            },
            "sections": {
                "warnings": [text]
            }
        }
        
        rollup = build_daily_rollup(
            date_obj=dt.date(2024, 3, 1),
            article_sum_jsons=[article],
            min_articles_required=1
        )
        
        warnings = rollup["sections"]["warnings"]
        assert len(warnings) > 0, "Should have at least one warning"
        
        w = warnings[0]
        assert w["horizon"] == expected_horizon, f"Expected horizon '{expected_horizon}', got '{w['horizon']}' for text: {text}"
        print(f"    '{text[:50]}...' -> horizon={w['horizon']}")
    
    sys.stdout.buffer.write(b"[PASS] Horizon inference works correctly\n")


def test_backward_compatibility():
    """Test that old-format warnings (plain strings or missing fields) work correctly."""
    from rollups import build_daily_rollup
    
    # Old format: plain string
    article_old = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test Article",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []
        },
        "sections": {
            "warnings": [
                "Generic warning without context."
            ]
        }
    }
    
    rollup = build_daily_rollup(
        date_obj=dt.date(2024, 3, 1),
        article_sum_jsons=[article_old],
        min_articles_required=1
    )
    
    warnings = rollup["sections"]["warnings"]
    assert len(warnings) > 0, "Should have at least one warning"
    
    w = warnings[0]
    # Even old format gets enriched by _infer_risk_flag_context
    assert "asset_class" in w, "Old format should get asset_class field"
    assert "horizon" in w, "Old format should get horizon field"
    assert "direction" in w, "Old format should get direction field"
    assert "confidence" in w, "Old format should get confidence field"
    
    print(f"  Old format warning enriched: asset_class={w['asset_class']}, horizon={w['horizon']}")
    
    sys.stdout.buffer.write(b"[PASS] Backward compatibility works (old format gets enriched)\n")


def test_existing_products_preserved():
    """Test that text-based inference works even without article-level products."""
    from rollups import build_daily_rollup
    
    article = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test Article",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []  # No article-level products
        },
        "sections": {
            "warnings": [
                "OPEC decision could trigger oil price volatility."
            ]
        }
    }
    
    rollup = build_daily_rollup(
        date_obj=dt.date(2024, 3, 1),
        article_sum_jsons=[article],
        min_articles_required=1
    )
    
    warnings = rollup["sections"]["warnings"]
    assert len(warnings) > 0, "Should have at least one warning"
    
    w = warnings[0]
    print(f"  Inferred products: {w['products']}, asset_class={w['asset_class']}")
    
    # Should infer products from text keywords
    assert len(w["products"]) > 0, "Should have inferred products from text"
    assert w["asset_class"] == "commodities", f"Expected 'commodities', got '{w['asset_class']}'"
    assert "CL" in w["products"], f"Expected 'CL' in products, got {w['products']}"
    
    sys.stdout.buffer.write(b"[PASS] Products correctly inferred from text when article products empty\n")


def run_all_tests():
    """Run all test functions."""
    print("=" * 70)
    print("RISK FLAG ENRICHMENT TEST SUITE")
    print("=" * 70)
    print()
    
    test_functions = [
        test_oil_risk_flag,
        test_inflation_risk_flag,
        test_rates_risk_flag,
        test_fx_jpy_risk_flag,
        test_direction_inference,
        test_horizon_inference,
        test_backward_compatibility,
        test_existing_products_preserved,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in test_functions:
        try:
            print(f"\n{test_func.__name__}:")
            print(f"  {test_func.__doc__}")
            test_func()
            passed += 1
        except Exception as e:
            print(f"  [FAILED]: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print()
    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

