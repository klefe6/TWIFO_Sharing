"""
Test Volatility Outlook Reference Symbol and Bias Definition
Purpose: Verify that volatility outlook rows are unambiguous with reference instruments
Author: AI Assistant
Created: 2026-02-25
"""

import sys
import os
import datetime as dt

# Set UTF-8 encoding for console output
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None


def test_reference_mapping():
    """Test that canonical reference mapping is defined correctly."""
    
    print("=" * 70)
    print("TEST 1: CANONICAL REFERENCE MAPPING")
    print("=" * 70)
    
    print("\n[1] Importing rollups module...")
    try:
        from rollups import _aggregate_volatility_by_asset_class, _build_bias_definition
        print("✓ Import successful")
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False
    
    print("\n[2] Testing bias definition builder...")
    
    # Test FX with DXY
    test_cases = [
        ("FX", "DXY", "Bearish", "DXY falls, EURUSD tends to rise"),
        ("FX", "DXY", "Bullish", "DXY rises, EURUSD tends to fall"),
        ("FX", "DXY", "Neutral", "Mixed signals"),
        ("EQUITIES", "SPX", "Bearish", "downside"),
        ("EQUITIES", "SPX", "Bullish", "upside"),
        ("RATES", "US10Y", "Neutral", "neutral"),
        ("GENERAL", None, "Bearish", "No single reference"),
    ]
    
    all_passed = True
    for asset_class, ref_symbol, skew, expected_substring in test_cases:
        bias_def = _build_bias_definition(asset_class, ref_symbol, skew)
        if expected_substring in bias_def:
            print(f"  ✓ {asset_class} + {ref_symbol} + {skew}")
            print(f"    → {bias_def[:60]}...")
        else:
            print(f"  ✗ {asset_class} + {ref_symbol} + {skew}")
            print(f"    Expected substring: '{expected_substring}'")
            print(f"    Got: {bias_def}")
            all_passed = False
    
    if not all_passed:
        return False
    
    print("\n" + "=" * 70)
    print("TEST 1: ✓ PASSED")
    print("=" * 70)
    return True


def test_volatility_aggregation_with_reference():
    """Test that volatility aggregation adds reference_symbol and bias_definition."""
    
    print("\n" + "=" * 70)
    print("TEST 2: VOLATILITY AGGREGATION WITH REFERENCE")
    print("=" * 70)
    
    print("\n[1] Importing rollups module...")
    try:
        from rollups import _aggregate_volatility_by_asset_class
        print("✓ Import successful")
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False
    
    print("\n[2] Creating test articles with FX products...")
    test_articles = [
        {
            "meta": {
                "provider": "Test Provider 1",
                "products": ["EUR", "DXY"]
            },
            "volatility_impact": {
                "expected_volatility": "High",
                "directional_skew": "Bearish"
            }
        },
        {
            "meta": {
                "provider": "Test Provider 2",
                "products": ["GBP", "JPY"]
            },
            "volatility_impact": {
                "expected_volatility": "Medium",
                "directional_skew": "Bearish"
            }
        }
    ]
    
    print("\n[3] Running aggregation...")
    try:
        result = _aggregate_volatility_by_asset_class(test_articles)
        print(f"✓ Aggregation completed, {len(result)} asset classes")
    except Exception as e:
        print(f"✗ Aggregation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n[4] Verifying FX row has reference_symbol...")
    if "FX" not in result:
        print("✗ FX not in result")
        return False
    
    fx_data = result["FX"]
    print(f"  FX data keys: {list(fx_data.keys())}")
    
    # Check required fields
    required_fields = ["expected_volatility", "directional_skew", "confidence_score", "sources", "reference_symbol", "bias_definition"]
    all_present = True
    for field in required_fields:
        if field in fx_data:
            print(f"  ✓ {field}: {fx_data[field]}")
        else:
            print(f"  ✗ {field}: MISSING")
            all_present = False
    
    if not all_present:
        return False
    
    # Verify reference_symbol is DXY
    if fx_data["reference_symbol"] == "DXY":
        print(f"\n  ✓ reference_symbol is 'DXY'")
    else:
        print(f"\n  ✗ reference_symbol should be 'DXY', got: {fx_data['reference_symbol']}")
        return False
    
    # Verify bias_definition mentions DXY
    if "DXY" in fx_data["bias_definition"]:
        print(f"  ✓ bias_definition mentions DXY")
        print(f"    → {fx_data['bias_definition']}")
    else:
        print(f"  ✗ bias_definition should mention DXY")
        print(f"    Got: {fx_data['bias_definition']}")
        return False
    
    print("\n" + "=" * 70)
    print("TEST 2: ✓ PASSED")
    print("=" * 70)
    return True


def test_ui_rendering_with_reference():
    """Test that UI renders reference symbol and tooltip correctly."""
    
    print("\n" + "=" * 70)
    print("TEST 3: UI RENDERING WITH REFERENCE")
    print("=" * 70)
    
    print("\n[1] Importing twifo module...")
    try:
        import twifo
        print("✓ Import successful")
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False
    
    print("\n[2] Creating test rollup with volatility data...")
    test_rollup = {
        "meta": {
            "date": "2026-02-25",
            "providers": ["Test Provider"],
        },
        "ui": {
            "title": "Test Rollup"
        },
        "sections": {
            "tldr": [],
            "volatility_by_asset_class": {
                "FX": {
                    "expected_volatility": "Medium",
                    "directional_skew": "Bearish",
                    "confidence_score": 2.0,
                    "sources": ["Test Provider"],
                    "reference_symbol": "DXY",
                    "bias_definition": "Bearish bias relative to DXY. If DXY falls, EURUSD tends to rise (USD weakness)."
                },
                "EQUITIES": {
                    "expected_volatility": "High",
                    "directional_skew": "Bullish",
                    "confidence_score": 2.8,
                    "sources": ["Test Provider"],
                    "reference_symbol": "SPX",
                    "bias_definition": "Bullish bias relative to SPX. Expected upside movement."
                }
            }
        }
    }
    
    print("\n[3] Rendering rollup summary...")
    try:
        result = twifo.render_rollup_summary(test_rollup, article_count=1, dynamics_mode=True, is_logged_in=False)
        result_str = str(result)
        print("✓ Rendering completed")
    except Exception as e:
        print(f"✗ Rendering failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n[4] Verifying rendered output...")
    
    # Check for FX (DXY) label
    if "FX (DXY)" in result_str:
        print("  ✓ FX (DXY) label found")
    else:
        print("  ✗ FX (DXY) label not found")
        print(f"    Searching for 'FX' in output...")
        if "FX" in result_str:
            print("    Found 'FX' but not '(DXY)'")
        return False
    
    # Check for EQUITIES (SPX) label
    if "EQUITIES (SPX)" in result_str:
        print("  ✓ EQUITIES (SPX) label found")
    else:
        print("  ✗ EQUITIES (SPX) label not found")
        return False
    
    # Check for tooltip icon
    if "ⓘ" in result_str:
        print("  ✓ Tooltip icon (ⓘ) found")
    else:
        print("  ✗ Tooltip icon (ⓘ) not found")
        return False
    
    # Check for bias definition in title attribute
    if "DXY falls, EURUSD tends to rise" in result_str:
        print("  ✓ Bias definition found in tooltip")
    else:
        print("  ✗ Bias definition not found in tooltip")
        return False
    
    print("\n" + "=" * 70)
    print("TEST 3: ✓ PASSED")
    print("=" * 70)
    return True


def test_backward_compatibility():
    """Test that old rollups without reference_symbol still render correctly."""
    
    print("\n" + "=" * 70)
    print("TEST 4: BACKWARD COMPATIBILITY (OLD ROLLUPS)")
    print("=" * 70)
    
    print("\n[1] Importing twifo module...")
    try:
        import twifo
        print("✓ Import successful")
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False
    
    print("\n[2] Creating old rollup WITHOUT reference_symbol...")
    old_rollup = {
        "meta": {
            "date": "2026-02-25",
            "providers": ["Test Provider"],
        },
        "ui": {
            "title": "Old Rollup"
        },
        "sections": {
            "tldr": [],
            "volatility_by_asset_class": {
                "FX": {
                    "expected_volatility": "Medium",
                    "directional_skew": "Bearish",
                    "confidence_score": 2.0,
                    "sources": ["Test Provider"],
                    # NO reference_symbol or bias_definition
                }
            }
        }
    }
    
    print("\n[3] Rendering old rollup...")
    try:
        result = twifo.render_rollup_summary(old_rollup, article_count=1, dynamics_mode=True, is_logged_in=False)
        result_str = str(result)
        print("✓ Rendering completed without errors")
    except Exception as e:
        print(f"✗ Rendering failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n[4] Verifying fallback behavior...")
    
    # Should still show FX (DXY) using fallback mapping
    if "FX (DXY)" in result_str:
        print("  ✓ FX (DXY) label found (fallback mapping worked)")
    else:
        print("  ✗ FX (DXY) label not found (fallback failed)")
        return False
    
    # Should still have tooltip
    if "ⓘ" in result_str:
        print("  ✓ Tooltip icon found (fallback tooltip generated)")
    else:
        print("  ✗ Tooltip icon not found")
        return False
    
    print("\n" + "=" * 70)
    print("TEST 4: ✓ PASSED - Old rollups work correctly")
    print("=" * 70)
    return True


def test_general_asset_class():
    """Test that GENERAL asset class has no reference (too broad)."""
    
    print("\n" + "=" * 70)
    print("TEST 5: GENERAL ASSET CLASS (NO REFERENCE)")
    print("=" * 70)
    
    print("\n[1] Importing twifo module...")
    try:
        import twifo
        print("✓ Import successful")
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False
    
    print("\n[2] Creating rollup with GENERAL asset class...")
    test_rollup = {
        "meta": {
            "date": "2026-02-25",
            "providers": ["Test Provider"],
        },
        "ui": {
            "title": "Test Rollup"
        },
        "sections": {
            "tldr": [],
            "volatility_by_asset_class": {
                "GENERAL": {
                    "expected_volatility": "Low",
                    "directional_skew": "Neutral",
                    "confidence_score": 1.5,
                    "sources": ["Test Provider"],
                    "reference_symbol": None,  # No reference for GENERAL
                    "bias_definition": "Neutral bias for GENERAL. No single reference instrument."
                }
            }
        }
    }
    
    print("\n[3] Rendering rollup...")
    try:
        result = twifo.render_rollup_summary(test_rollup, article_count=1, dynamics_mode=True, is_logged_in=False)
        result_str = str(result)
        print("✓ Rendering completed")
    except Exception as e:
        print(f"✗ Rendering failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n[4] Verifying GENERAL has no parenthetical...")
    
    # Should show "GENERAL" without parenthetical
    if "GENERAL (" in result_str:
        print("  ✗ GENERAL should not have parenthetical reference")
        return False
    elif "GENERAL" in result_str:
        print("  ✓ GENERAL shown without parenthetical (correct)")
    else:
        print("  ✗ GENERAL not found in output")
        return False
    
    print("\n" + "=" * 70)
    print("TEST 5: ✓ PASSED")
    print("=" * 70)
    return True


if __name__ == "__main__":
    print("Starting Volatility Outlook Reference Tests...\n")
    
    test1_result = test_reference_mapping()
    test2_result = test_volatility_aggregation_with_reference()
    test3_result = test_ui_rendering_with_reference()
    test4_result = test_backward_compatibility()
    test5_result = test_general_asset_class()
    
    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    print(f"Test 1 (Reference Mapping):        {'PASS' if test1_result else 'FAIL'}")
    print(f"Test 2 (Aggregation):               {'PASS' if test2_result else 'FAIL'}")
    print(f"Test 3 (UI Rendering):              {'PASS' if test3_result else 'FAIL'}")
    print(f"Test 4 (Backward Compatibility):    {'PASS' if test4_result else 'FAIL'}")
    print(f"Test 5 (GENERAL No Reference):      {'PASS' if test5_result else 'FAIL'}")
    print("=" * 70)
    
    all_passed = test1_result and test2_result and test3_result and test4_result and test5_result
    
    if all_passed:
        print("\n✓ ALL TESTS PASSED")
        print("\nExample rendered output:")
        print("  FX (DXY)  |  Medium  |  ↘️ Bearish ⓘ")
        print("  Tooltip: 'Bearish bias relative to DXY. If DXY falls, EURUSD tends to rise (USD weakness).'")
    else:
        print("\n✗ SOME TESTS FAILED")
    
    print("=" * 70)
    
    sys.exit(0 if all_passed else 1)

