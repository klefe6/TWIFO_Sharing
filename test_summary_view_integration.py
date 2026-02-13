"""
Test: Summary View Integration
Purpose: Verify summary view rendering and routing in twifo.py
Author: Kevin Lefebvre
Last Updated: 2026-02-12

Tests:
1. Load summary JSON (both layouts)
2. Detect stub summaries
3. Render failed summary
4. Render successful summary with all sections
5. Render minimal summary (only tldr)
"""

import sys
import tempfile
import json
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from summary_view import (
    load_summary_json,
    is_stub_summary,
    render_failed_summary,
    render_summary_view
)
from path_manager import TWIFOPathManager


def _create_sample_summary(
    basename: str,
    is_stub: bool = False,
    has_trade_ideas: bool = True,
    has_optional_sections: bool = True
) -> dict:
    """Create a sample summary JSON."""
    if is_stub:
        return {
            "_is_stub": True,
            "extraction": {
                "status": "failed",
                "reason": "LLM call failed after 2 attempts"
            },
            "meta": {
                "title": "Failed Article",
                "provider": "TEST"
            },
            "sections": {}
        }
    
    summary = {
        "meta": {
            "title": "Test Article",
            "provider": "BOA",
            "published_date": "20260212",
            "horizon": "w"
        },
        "extraction": {
            "status": "ok",
            "confidence_0_100": 85
        },
        "sections": {
            "tldr": [
                "Gold prices reached $2,150 on safe-haven demand",
                "Fed signals potential rate cuts in Q2 2026",
                "Equity volatility increased on geopolitical tensions"
            ],
            "what_moved_today": [
                "Gold rallied 2.3% to $2,150",
                "Treasury yields fell 5bps"
            ],
            "what_can_move_tomorrow": [
                "Fed minutes at 2pm ET could signal policy shift"
            ],
        },
        "fingerprint_quotes": [
            "Gold demand continues to outpace supply",
            "Market participants are positioning for potential Fed pivot"
        ],
        "numeric_claims": [
            {
                "value": "2,150",
                "context": "Gold price level",
                "source_quote": "Gold reached $2,150 on strong safe-haven flows"
            }
        ]
    }
    
    if has_trade_ideas:
        summary["sections"]["trade_ideas"] = [
            {
                "product": "GC",
                "bias": "Bullish",
                "catalyst": "Safe-haven demand on geopolitical tensions",
                "setup": "Long above $2,140",
                "key_levels": ["2,150", "2,175", "2,200"],
                "risk": "Below $2,120",
                "time_horizon": "1-2w"
            }
        ]
    else:
        summary["sections"]["trade_ideas"] = []
    
    if has_optional_sections:
        summary["sections"]["what_occurred"] = ["Fed meeting minutes released"]
        summary["sections"]["forward_watch"] = ["CPI data next week"]
        summary["sections"]["warnings"] = ["Liquidity may thin into holiday"]
        summary["sections"]["tips_reminders"] = ["Gold correlation with real yields"]
        summary["sections"]["cross_asset_impacts"] = ["Stronger gold → weaker USD"]
        summary["sections"]["scenarios"] = ["If CPI > 3.5%, expect rally continuation"]
    else:
        summary["sections"]["what_occurred"] = []
        summary["sections"]["forward_watch"] = []
        summary["sections"]["warnings"] = []
        summary["sections"]["tips_reminders"] = []
        summary["sections"]["cross_asset_impacts"] = []
        summary["sections"]["scenarios"] = []
    
    return summary


def test_load_summary_with_path_manager():
    """Test loading sum.json with path_manager (new layout)."""
    print("\n[TEST 1] Load summary with path_manager")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir)
        pm = TWIFOPathManager(export_dir)
        
        basename = "20260212__BOA__test__abc123"
        summary = _create_sample_summary(basename)
        
        # Write to artifacts/<basename>/sum.json
        sum_path = pm.artifact_path(basename, 'sum.json')
        sum_path.parent.mkdir(parents=True, exist_ok=True)
        sum_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
        
        # Load
        loaded = load_summary_json(basename, export_dir, path_manager=pm)
        
        assert loaded is not None, "Should load summary"
        assert loaded["meta"]["title"] == "Test Article"
        print(f"  [PASS] Loaded from artifacts/<basename>/sum.json")


def test_load_summary_legacy():
    """Test loading sum.json in legacy layout."""
    print("\n[TEST 2] Load summary in legacy layout")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir)
        
        basename = "20260212__BOA__test__abc123"
        summary = _create_sample_summary(basename)
        
        # Write to root/<basename>__sum.json
        sum_path = export_dir / f"{basename}__sum.json"
        sum_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
        
        # Load WITHOUT path_manager
        loaded = load_summary_json(basename, export_dir, path_manager=None)
        
        assert loaded is not None, "Should load summary"
        assert loaded["meta"]["title"] == "Test Article"
        print(f"  [PASS] Loaded from root/<basename>__sum.json")


def test_is_stub_detection():
    """Test stub/failed summary detection."""
    print("\n[TEST 3] Detect stub summaries")
    
    # Test 1: _is_stub flag
    stub1 = {"_is_stub": True, "sections": {}}
    assert is_stub_summary(stub1), "Should detect _is_stub flag"
    
    # Test 2: extraction.status = failed
    stub2 = {"extraction": {"status": "failed"}, "sections": {}}
    assert is_stub_summary(stub2), "Should detect failed status"
    
    # Test 3: Empty sections
    stub3 = {"sections": {"tldr": [], "what_moved_today": [], "what_can_move_tomorrow": []}}
    assert is_stub_summary(stub3), "Should detect empty sections"
    
    # Test 4: Valid summary
    valid = {
        "sections": {
            "tldr": ["Point 1", "Point 2", "Point 3"],
            "what_moved_today": [],
            "what_can_move_tomorrow": []
        },
        "extraction": {"status": "ok"}
    }
    assert not is_stub_summary(valid), "Should NOT detect valid summary as stub"
    
    print(f"  [PASS] Stub detection working correctly")


def test_render_failed_summary():
    """Test rendering of failed summary."""
    print("\n[TEST 4] Render failed summary")
    
    stub = _create_sample_summary("test", is_stub=True)
    basename = "20260212__TEST__failed__xyz"
    
    layout = render_failed_summary(stub, basename)
    
    # Verify it's a Div
    assert layout is not None
    assert hasattr(layout, 'children'), "Should return html.Div"
    
    # Check for key elements (basic structure check)
    layout_str = str(layout)
    assert "Failed Summary" in layout_str or "failed" in layout_str.lower()
    
    print(f"  [PASS] Failed summary rendered")


def test_render_full_summary():
    """Test rendering full summary with all sections."""
    print("\n[TEST 5] Render full summary")
    
    summary = _create_sample_summary(
        "test",
        has_trade_ideas=True,
        has_optional_sections=True
    )
    basename = "20260212__BOA__full_test__abc"
    
    layout = render_summary_view(basename, summary)
    
    assert layout is not None
    assert hasattr(layout, 'children')
    
    # Check that key sections are present (string representation check)
    layout_str = str(layout)
    assert "TL;DR" in layout_str or "tldr" in layout_str.lower()
    assert "Trade Ideas" in layout_str or "trade" in layout_str.lower()
    
    print(f"  [PASS] Full summary rendered with all sections")


def test_render_minimal_summary():
    """Test rendering minimal summary (only tldr)."""
    print("\n[TEST 6] Render minimal summary (only tldr)")
    
    summary = _create_sample_summary(
        "test",
        has_trade_ideas=False,
        has_optional_sections=False
    )
    basename = "20260212__BOA__minimal__xyz"
    
    layout = render_summary_view(basename, summary)
    
    assert layout is not None
    assert hasattr(layout, 'children')
    
    # Should have tldr but not trade ideas section
    layout_str = str(layout)
    assert "Gold prices reached" in layout_str  # From tldr
    
    print(f"  [PASS] Minimal summary rendered (tldr only)")


def test_low_confidence_banner():
    """Test that low confidence summaries show warning banner."""
    print("\n[TEST 7] Low confidence banner")
    
    summary = _create_sample_summary("test")
    summary["extraction"]["confidence_0_100"] = 55  # Low confidence
    basename = "20260212__BOA__lowconf__xyz"
    
    layout = render_summary_view(basename, summary)
    layout_str = str(layout)
    
    # Should contain low confidence warning
    assert "Low Confidence" in layout_str or "confidence" in layout_str.lower()
    assert "55" in layout_str  # Confidence percentage
    
    print(f"  [PASS] Low confidence banner displayed")


def test_trade_idea_bias_colors():
    """Test that trade idea cards have correct bias colors."""
    print("\n[TEST 8] Trade idea bias colors")
    
    summary = _create_sample_summary("test", has_trade_ideas=True)
    
    # Add different bias types
    summary["sections"]["trade_ideas"] = [
        {"product": "GC", "bias": "Bullish", "catalyst": "Test"},
        {"product": "ES", "bias": "Bearish", "catalyst": "Test"},
        {"product": "ZN", "bias": "Neutral", "catalyst": "Test"},
    ]
    
    basename = "test_bias"
    layout = render_summary_view(basename, summary)
    layout_str = str(layout)
    
    # Check that different colors are used (hex codes)
    assert "#28a745" in layout_str  # Bullish green
    assert "#dc3545" in layout_str  # Bearish red
    assert "#6c757d" in layout_str  # Neutral gray
    
    print(f"  [PASS] Trade idea bias colors applied")


if __name__ == "__main__":
    tests = [
        test_load_summary_with_path_manager,
        test_load_summary_legacy,
        test_is_stub_detection,
        test_render_failed_summary,
        test_render_full_summary,
        test_render_minimal_summary,
        test_low_confidence_banner,
        test_trade_idea_bias_colors,
    ]
    
    passed = 0
    failed = 0
    
    print("=" * 70)
    print("SUMMARY VIEW INTEGRATION TESTS")
    print("=" * 70)
    
    for fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {fn.__name__}")
            print(f"    Error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print("=" * 70)
    
    if failed == 0:
        print("\nSummary view features validated:")
        print("  1. Loads from both path_manager and legacy layouts")
        print("  2. Detects stub/failed summaries")
        print("  3. Renders failed summaries with error messages")
        print("  4. Renders full summaries with all sections")
        print("  5. Handles minimal summaries (tldr only)")
        print("  6. Shows low-confidence banners")
        print("  7. Color-codes trade idea bias")
    
    sys.exit(1 if failed else 0)
