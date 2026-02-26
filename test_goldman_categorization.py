"""
Test: Goldman Sachs Categorization Fix

Verifies that Goldman Sachs articles are correctly categorized as "Goldman Sachs"
instead of "Others" in both Daily View and Daily Summary.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from twifo import PREFIX_MAP, detect_category
from twifo_app import _detect_provider, _parse_folder_segments


def test_prefix_map_has_gs():
    """Test that PREFIX_MAP includes GS_ prefix for Goldman Sachs"""
    print("TEST 1: PREFIX_MAP includes GS_ prefix")
    
    assert "GS_" in PREFIX_MAP, "GS_ prefix missing from PREFIX_MAP"
    assert PREFIX_MAP["GS_"] == "Goldman Sachs", f"GS_ maps to '{PREFIX_MAP['GS_']}', expected 'Goldman Sachs'"
    assert "GM_" in PREFIX_MAP, "GM_ prefix missing from PREFIX_MAP"
    assert PREFIX_MAP["GM_"] == "Goldman Sachs", f"GM_ maps to '{PREFIX_MAP['GM_']}', expected 'Goldman Sachs'"
    
    print("  [OK] GS_ -> Goldman Sachs")
    print("  [OK] GM_ -> Goldman Sachs")
    print()


def test_detect_category_gs_files():
    """Test that detect_category correctly identifies GS_ files"""
    print("TEST 2: detect_category() recognizes GS_ files")
    
    test_cases = [
        ("GS_commodities_weekly_20260211_w.pdf", "Goldman Sachs"),
        ("GM_commodities_weekly_20260211_w.pdf", "Goldman Sachs"),
        ("GS_rates_daily_20260211_d.pdf", "Goldman Sachs"),
        ("GM_rates_daily_20260211_d.pdf", "Goldman Sachs"),
        ("JPM_commodities_weekly_20260211_w.pdf", "JP Morgan"),
        ("UNKNOWN_file_20260211_d.pdf", "Others"),
    ]
    
    for filename, expected_category in test_cases:
        result = detect_category(filename)
        assert result == expected_category, f"detect_category('{filename}') returned '{result}', expected '{expected_category}'"
        print(f"  [OK] {filename} -> {result}")
    
    print()


def test_detect_provider_from_folder():
    """Test that _detect_provider correctly identifies Goldman from folder names"""
    print("TEST 3: _detect_provider() recognizes Goldman folders")
    
    test_cases = [
        ("20260211__GS__commodities_weekly__abc123", "Goldman Sachs"),
        ("20260211__GM__commodities_weekly__abc123", "Goldman Sachs"),
        ("20260211__JPM__rates_daily__def456", "JP Morgan"),
        ("20260211__UNKNOWN__file__ghi789", "UNKNOWN"),
    ]
    
    for folder_name, expected_provider in test_cases:
        result = _detect_provider(folder_name)
        assert result == expected_provider, f"_detect_provider('{folder_name}') returned '{result}', expected '{expected_provider}'"
        print(f"  [OK] {folder_name} -> {result}")
    
    print()


def test_parse_folder_segments():
    """Test that _parse_folder_segments correctly extracts provider code"""
    print("TEST 4: _parse_folder_segments() extracts provider code")
    
    test_cases = [
        ("20260211__GS__commodities_weekly__abc123", "GS"),
        ("20260211__GM__commodities_weekly__abc123", "GM"),
        ("20260211__JPM__rates_daily__def456", "JPM"),
    ]
    
    for folder_name, expected_code in test_cases:
        result = _parse_folder_segments(folder_name)
        assert result["provider_code"] == expected_code, f"provider_code for '{folder_name}' is '{result['provider_code']}', expected '{expected_code}'"
        print(f"  [OK] {folder_name} -> provider_code={result['provider_code']}")
    
    print()


def test_goldman_not_others():
    """Test that Goldman files are NOT categorized as Others"""
    print("TEST 5: Goldman files are NOT categorized as 'Others'")
    
    goldman_files = [
        "GS_commodities_weekly_20260211_w.pdf",
        "GM_commodities_weekly_20260211_w.pdf",
        "GS_rates_daily_20260211_d.pdf",
    ]
    
    for filename in goldman_files:
        category = detect_category(filename)
        assert category != "Others", f"ERROR: {filename} categorized as 'Others' instead of 'Goldman Sachs'"
        assert category == "Goldman Sachs", f"ERROR: {filename} categorized as '{category}' instead of 'Goldman Sachs'"
        print(f"  [OK] {filename} -> {category} (NOT Others)")
    
    print()


def test_detection_rule():
    """Print the exact detection rule used"""
    print("=" * 70)
    print("DETECTION RULE")
    print("=" * 70)
    print()
    print("Rule: Files with prefix 'GS_' or 'GM_' are categorized as 'Goldman Sachs'")
    print()
    print("Implementation:")
    print("  - PREFIX_MAP['GS_'] = 'Goldman Sachs'")
    print("  - PREFIX_MAP['GM_'] = 'Goldman Sachs'")
    print("  - detect_category() checks if filename starts with 'GS_' or 'GM_'")
    print("  - _detect_provider() extracts provider code from folder name and maps via PREFIX_MAP")
    print()
    print("=" * 70)
    print()


if __name__ == "__main__":
    print("=" * 70)
    print("GOLDMAN SACHS CATEGORIZATION TEST")
    print("=" * 70)
    print()
    
    try:
        test_prefix_map_has_gs()
        test_detect_category_gs_files()
        test_detect_provider_from_folder()
        test_parse_folder_segments()
        test_goldman_not_others()
        test_detection_rule()
        
        print("=" * 70)
        print("ALL TESTS PASSED")
        print("=" * 70)
        print()
        print("Goldman Sachs articles will now be categorized correctly")
        print("in both Daily View and Daily Summary (not as 'Others')")
        print()
        
        sys.exit(0)
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}\n")
        sys.exit(1)

