"""
Unit tests for shared title resolver
Purpose: Verify resolve_display_title works correctly across all scenarios
Author: Kevin Lefebvre
Last Updated: 2026-02-14
"""

from twifo_app import resolve_display_title


def test_filename_to_clean_title():
    """Test: Known filename resolves to clean title."""
    folder = "20260211__O__weekly_municipal_monitor_seasonal_strength_02_10_20260211_w__abc123"
    result = resolve_display_title(folder)
    
    # Should remove: O_ prefix, embedded date 20260211, _w suffix
    # Should convert: underscores to spaces, title case
    expected = "Weekly Municipal Monitor Seasonal Strength 02 10"
    
    assert result == expected, f"Expected '{expected}', got '{result}'"
    print(f"[PASS] Filename cleaned correctly: {result}")


def test_clean_meta_title_preferred():
    """Test: Clean meta.title is used over derived title."""
    folder = "20260211__GM__foo_bar__abc123"
    meta_title = "Clean Title from LLM"
    
    result = resolve_display_title(folder, meta_title=meta_title)
    
    # Should use meta_title directly since it's clean (no underscores/dates)
    assert result == meta_title, f"Expected '{meta_title}', got '{result}'"
    print(f"[PASS] Clean meta.title preferred: {result}")


def test_dirty_meta_title_fallback():
    """Test: Dirty meta.title (with underscores/dates) falls back to derived."""
    folder = "20260211__GM__commodity_analyst_report__abc123"
    meta_title = "GM_Commodity_Analyst_Report_20260211_u"  # Dirty: has underscores and date
    
    result = resolve_display_title(folder, meta_title=meta_title)
    
    # Should fallback to derived title since meta_title is dirty
    expected = "Commodity Analyst Report"
    assert result == expected, f"Expected '{expected}', got '{result}'"
    print(f"[PASS] Dirty meta.title fell back to derived: {result}")


def test_sum_json_meta_extraction():
    """Test: meta.title extracted from sum_json dict."""
    folder = "20260211__ING__test__abc123"
    sum_json = {
        "meta": {
            "title": "ING Think Commodities Feed",
            "provider": "ING"
        }
    }
    
    result = resolve_display_title(folder, sum_json=sum_json)
    
    # Should extract and use meta.title from sum_json
    expected = "ING Think Commodities Feed"
    assert result == expected, f"Expected '{expected}', got '{result}'"
    print(f"[PASS] sum_json meta.title extracted: {result}")


def test_missing_meta_title_fallback():
    """Test: Missing meta.title falls back to derived title, not raw filename."""
    folder = "20260211__GM__weekly_options_watch_ai_reactions_tracker_20260211_w__abc123"
    meta_title = ""  # Empty
    
    result = resolve_display_title(folder, meta_title=meta_title)
    
    # Should derive from folder, NOT return raw filename
    expected = "Weekly Options Watch Ai Reactions Tracker"
    assert result == expected, f"Expected '{expected}', got '{result}'"
    assert "_" not in result, f"Result should not contain underscores: {result}"
    assert "20260211" not in result, f"Result should not contain embedded date: {result}"
    print(f"[PASS] Missing meta.title fell back to derived (not raw filename): {result}")


def test_provider_prefix_removal():
    """Test: Provider prefix is removed from derived title."""
    folder = "20260211__GM__gm_commodity_analyst_what_the_great_gold_rally__abc123"
    
    result = resolve_display_title(folder)
    
    # Should remove "gm_" prefix
    assert not result.lower().startswith("gm "), f"Provider prefix not removed: {result}"
    expected_start = "Commodity Analyst"
    assert result.startswith(expected_start), f"Expected to start with '{expected_start}', got '{result}'"
    print(f"[PASS] Provider prefix removed: {result}")


def test_frequency_suffix_removal():
    """Test: Frequency suffix (_w, _m, _q, etc.) is removed."""
    test_cases = [
        ("20260211__GM__report_w__abc", "Report"),
        ("20260211__GM__analysis_m__abc", "Analysis"),
        ("20260211__GM__quarterly_q__abc", "Quarterly"),
        ("20260211__GM__daily_d__abc", "Daily"),
    ]
    
    for folder, expected in test_cases:
        result = resolve_display_title(folder)
        assert result == expected, f"For '{folder}': expected '{expected}', got '{result}'"
        print(f"[PASS] Frequency suffix removed: {folder} -> {result}")


if __name__ == "__main__":
    print("\n=== Testing resolve_display_title ===\n")
    
    test_filename_to_clean_title()
    test_clean_meta_title_preferred()
    test_dirty_meta_title_fallback()
    test_sum_json_meta_extraction()
    test_missing_meta_title_fallback()
    test_provider_prefix_removal()
    test_frequency_suffix_removal()
    
    print("\n=== All tests passed! ===\n")
