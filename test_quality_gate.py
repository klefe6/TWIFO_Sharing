"""
Regression Test: Quality Gate for Low-Quality Summaries

Purpose: Verify that is_low_quality_summary() correctly detects and fails garbage/templated LLM output
Author: Kevin Lefebvre
Last Updated: 2026-01-26
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from summarize_pdf import is_low_quality_summary


def test_too_few_unique_bullets():
    """Test detection of summaries with too few unique bullets."""
    print("\n[TEST 1] Too few unique bullets")
    
    garbage_summary = {
        "sections": {
            "tldr": [{"text": "Market moved today"}],
            "what_occurred": [{"text": "Data released"}],
            "trade_ideas": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(garbage_summary)
    assert is_low_quality, "Should detect too few unique bullets"
    assert "too_few_unique_bullets" in reason, f"Expected 'too_few_unique_bullets' in reason, got: {reason}"
    print(f"  [PASS] Detected: {reason}")


def test_excessive_duplication():
    """Test detection of copy-paste behavior."""
    print("\n[TEST 2] Excessive duplication")
    
    garbage_summary = {
        "sections": {
            "tldr": [
                {"text": "Monitor key levels for breakout"},
                {"text": "Monitor key levels for breakout"},
                {"text": "Monitor key levels for breakout"}
            ],
            "what_occurred": [
                {"text": "Monitor key levels for breakout"},
                {"text": "Watch for data releases this week"},
                {"text": "Watch for data releases this week"}
            ],
            "forward_watch": [
                {"text": "Monitor key levels for breakout"},
                {"text": "Watch for data releases this week"},
                {"text": "Track volatility patterns going forward"}
            ],
            "trade_ideas": [],
            "warnings": [],
            "tips_reminders": [
                {"text": "Monitor key levels for breakout"},
                {"text": "Watch for data releases this week"}
            ],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(garbage_summary)
    assert is_low_quality, "Should detect excessive duplication"
    assert "excessive_duplication" in reason, f"Expected 'excessive_duplication' in reason, got: {reason}"
    print(f"  [PASS] Detected: {reason}")


def test_excessive_placeholders():
    """Test detection of generic placeholder phrases."""
    print("\n[TEST 3] Excessive placeholders")
    
    garbage_summary = {
        "sections": {
            "tldr": [
                {"text": "Pending analysis of market conditions"},
                {"text": "Monitor key levels going forward"},
                {"text": "Await further information on data releases"}
            ],
            "what_occurred": [
                {"text": "Data not available yet"},
                {"text": "Subject to change pending clarification"}
            ],
            "forward_watch": [
                {"text": "Watch for updates on economic calendar"},
                {"text": "More details needed on policy decision"}
            ],
            "trade_ideas": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(garbage_summary)
    assert is_low_quality, "Should detect excessive placeholders"
    assert "excessive_placeholders" in reason, f"Expected 'excessive_placeholders' in reason, got: {reason}"
    print(f"  [PASS] Detected: {reason}")


def test_excessive_short_bullets():
    """Test detection of suspiciously short bullets."""
    print("\n[TEST 4] Excessive short bullets")
    
    garbage_summary = {
        "sections": {
            "tldr": [
                {"text": "ES up"},
                {"text": "NQ down"},
                {"text": "GC flat"}
            ],
            "what_occurred": [
                {"text": "Fed met"},
                {"text": "Rates cut"},
                {"text": "Data out"}
            ],
            "forward_watch": [
                {"text": "Watch ES"},
                {"text": "Monitor NQ"},
                {"text": "Track GC"}
            ],
            "trade_ideas": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(garbage_summary)
    assert is_low_quality, "Should detect excessive short bullets"
    assert "excessive_short_bullets" in reason, f"Expected 'excessive_short_bullets' in reason, got: {reason}"
    print(f"  [PASS] Detected: {reason}")


def test_valid_summary_passes():
    """Test that a valid summary passes quality gate."""
    print("\n[TEST 5] Valid summary should pass")
    
    valid_summary = {
        "sections": {
            "tldr": [
                {"text": "Fed raised rates 25bps citing persistent inflation above 3% target, signaling at least 2 more hikes this cycle"},
                {"text": "European energy crisis intensified as Russian gas flows dropped 40% week-over-week, pushing TTF futures to record highs"},
                {"text": "China manufacturing PMI beat at 52.1 vs 50.5 expected, driven by domestic consumption recovery and easing supply chain pressures"}
            ],
            "what_occurred": [
                {"text": "US PCE inflation printed 3.2% YoY vs 3.0% expected, core PCE at 3.4% remains sticky"},
                {"text": "Initial jobless claims fell to 215k from 225k, continuing tight labor market theme"},
                {"text": "Q2 GDP revised higher to 2.3% from 2.1% on strong consumer spending"}
            ],
            "forward_watch": [
                {"text": "September FOMC decision Wednesday - markets pricing 85% chance of 25bp hike"},
                {"text": "Nonfarm payrolls Friday - consensus 180k vs 187k prior"},
                {"text": "EU energy ministers meeting Thursday to discuss price caps and supply diversification"}
            ],
            "trade_ideas": [
                {
                    "product": "ES",
                    "bias": "Bearish",
                    "catalyst": "Fed hawkish pivot and sticky inflation forcing higher rates",
                    "setup": "If ES fails to reclaim prior session VWAP and VIX breaks above 18, short ES targeting 4400-4380 range",
                    "key_levels": "Resistance at 4450 VWAP, support at 4400 then 4380",
                    "risk": "Invalidation above 4465 (recent range high)",
                    "time_horizon": "1-3D"
                }
            ],
            "warnings": [],
            "tips_reminders": [
                {"text": "Watch for Fed speak after decision - any language around 'sufficiently restrictive' could signal pause"},
                {"text": "European gas storage currently at 82% vs 5-year average of 76% - winter cushion improving"}
            ],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(valid_summary)
    assert not is_low_quality, f"Valid summary should pass, but got: {reason}"
    print(f"  [PASS] Valid summary correctly passed quality gate")


def test_neutral_trade_ideas_allowed():
    """Test that neutral trade ideas with 'no direct trade idea' don't trigger placeholder detection."""
    print("\n[TEST 6] Neutral products with 'no direct trade idea' should be allowed")
    
    summary_with_neutrals = {
        "sections": {
            "tldr": [
                {"text": "Fed raised rates 25bps citing persistent inflation above 3% target"},
                {"text": "European energy crisis intensified as Russian gas flows dropped 40% week-over-week"},
                {"text": "This article focuses on European energy markets with minimal ES/NQ relevance"}
            ],
            "what_occurred": [
                {"text": "US PCE inflation printed 3.2% YoY vs 3.0% expected, core PCE at 3.4%"},
                {"text": "European natural gas TTF futures surged 12% to €95/MWh on supply concerns"},
                {"text": "German manufacturing PMI contracted to 48.2 vs 49.0 expected"}
            ],
            "trade_ideas": [
                {
                    "product": "ES",
                    "bias": "Neutral",
                    "catalyst": "No direct trade idea from this article",
                    "setup": "",
                    "key_levels": "",
                    "risk": "",
                    "time_horizon": ""
                },
                {
                    "product": "NQ",
                    "bias": "Neutral",
                    "catalyst": "No direct trade idea from this article",
                    "setup": "",
                    "key_levels": "",
                    "risk": "",
                    "time_horizon": ""
                },
                {
                    "product": "GC",
                    "bias": "Bullish",
                    "catalyst": "Rising geopolitical risk premium from European energy crisis",
                    "setup": "If GC breaks above $1980 with volume, target $2000-2010",
                    "key_levels": "Support at $1960, resistance at $1980 then $2000",
                    "risk": "Invalidation below $1950",
                    "time_horizon": "1-2W"
                }
            ],
            "forward_watch": [
                {"text": "EU energy ministers meeting Thursday to discuss price caps"},
                {"text": "Russian gas flows via Nord Stream 1 - currently at 20% capacity"}
            ],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary_with_neutrals)
    assert not is_low_quality, f"Summary with neutral products should pass, but got: {reason}"
    print(f"  [PASS] Neutral products with 'no direct trade idea' correctly allowed")


def test_completely_empty_summary():
    """Test detection of completely empty summary."""
    print("\n[TEST 7] Completely empty summary")
    
    empty_summary = {
        "sections": {
            "tldr": [],
            "what_occurred": [],
            "forward_watch": [],
            "trade_ideas": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(empty_summary)
    assert is_low_quality, "Should detect completely empty summary"
    assert "too_few_unique_bullets" in reason, f"Expected 'too_few_unique_bullets' in reason, got: {reason}"
    print(f"  [PASS] Detected: {reason}")


def test_banned_phrase_market_data_pending():
    """Test detection of banned phrase 'market data pending analysis'."""
    print("\n[TEST 8] Banned phrase: 'market data pending analysis'")
    
    summary_with_banned_phrase = {
        "sections": {
            "tldr": [
                {"text": "Fed raised rates 25bps citing persistent inflation above 3% target"},
                {"text": "European energy crisis intensified as Russian gas flows dropped 40% week-over-week"},
                {"text": "Market data pending analysis for further insights"}
            ],
            "what_occurred": [
                {"text": "US PCE inflation printed 3.2% YoY vs 3.0% expected, core PCE at 3.4%"},
                {"text": "European natural gas TTF futures surged 12% to €95/MWh on supply concerns"},
                {"text": "German manufacturing PMI contracted to 48.2 vs 49.0 expected"}
            ],
            "forward_watch": [
                {"text": "EU energy ministers meeting Thursday to discuss price caps"},
                {"text": "Russian gas flows via Nord Stream 1 - currently at 20% capacity"},
                {"text": "Fed minutes release next week"}
            ],
            "trade_ideas": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary_with_banned_phrase)
    assert is_low_quality, "Should detect banned phrase 'market data pending analysis'"
    assert "filler:banned_phrase" in reason, f"Expected 'filler:banned_phrase' in reason, got: {reason}"
    assert "market data pending analysis" in reason, f"Expected banned phrase in reason, got: {reason}"
    print(f"  [PASS] Detected: {reason}")


def test_banned_phrase_monitor_key_levels():
    """Test detection of banned phrase 'monitor key levels and data releases'."""
    print("\n[TEST 9] Banned phrase: 'monitor key levels and data releases'")
    
    summary_with_banned_phrase = {
        "sections": {
            "tldr": [
                {"text": "Fed raised rates 25bps citing persistent inflation above 3% target"},
                {"text": "European energy crisis intensified as Russian gas flows dropped 40% week-over-week"},
                {"text": "China manufacturing PMI beat at 52.1 vs 50.5 expected"}
            ],
            "what_occurred": [
                {"text": "US PCE inflation printed 3.2% YoY vs 3.0% expected, core PCE at 3.4%"},
                {"text": "European natural gas TTF futures surged 12% to €95/MWh on supply concerns"},
                {"text": "German manufacturing PMI contracted to 48.2 vs 49.0 expected"}
            ],
            "forward_watch": [
                {"text": "Monitor key levels and data releases for trading opportunities"},
                {"text": "Russian gas flows via Nord Stream 1 - currently at 20% capacity"},
                {"text": "Fed minutes release next week"}
            ],
            "trade_ideas": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary_with_banned_phrase)
    assert is_low_quality, "Should detect banned phrase 'monitor key levels and data releases'"
    assert "filler:banned_phrase" in reason, f"Expected 'filler:banned_phrase' in reason, got: {reason}"
    assert "monitor key levels and data releases" in reason, f"Expected banned phrase in reason, got: {reason}"
    print(f"  [PASS] Detected: {reason}")


def test_banned_phrase_case_insensitive():
    """Test that banned phrase detection is case-insensitive."""
    print("\n[TEST 10] Banned phrase detection (case-insensitive)")
    
    summary_with_uppercase_banned = {
        "sections": {
            "tldr": [
                {"text": "Fed raised rates 25bps citing persistent inflation above 3% target"},
                {"text": "European energy crisis intensified as Russian gas flows dropped 40% week-over-week"},
                {"text": "MARKET DATA PENDING ANALYSIS for next session"}
            ],
            "what_occurred": [
                {"text": "US PCE inflation printed 3.2% YoY vs 3.0% expected, core PCE at 3.4%"},
                {"text": "European natural gas TTF futures surged 12% to €95/MWh on supply concerns"},
                {"text": "German manufacturing PMI contracted to 48.2 vs 49.0 expected"}
            ],
            "forward_watch": [
                {"text": "EU energy ministers meeting Thursday to discuss price caps"},
                {"text": "Russian gas flows via Nord Stream 1 - currently at 20% capacity"},
                {"text": "Fed minutes release next week"}
            ],
            "trade_ideas": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary_with_uppercase_banned)
    assert is_low_quality, "Should detect banned phrase regardless of case"
    assert "filler:banned_phrase" in reason, f"Expected 'filler:banned_phrase' in reason, got: {reason}"
    print(f"  [PASS] Detected: {reason}")


def test_section_level_repetition():
    """Test detection of 2+ identical bullets within same section."""
    print("\n[TEST 11] Section-level repetition (2+ identical bullets)")
    
    summary_with_section_repetition = {
        "sections": {
            "tldr": [
                {"text": "Fed raised rates 25bps citing persistent inflation above 3% target"},
                {"text": "European energy crisis intensified as Russian gas flows dropped"},
                {"text": "China manufacturing PMI beat expectations"}
            ],
            "what_occurred": [
                {"text": "US PCE inflation printed 3.2% YoY vs 3.0% expected"},
                {"text": "Watch for volatility around key support levels"},
                {"text": "Watch for volatility around key support levels"}  # Duplicate in same section
            ],
            "forward_watch": [
                {"text": "EU energy ministers meeting Thursday to discuss price caps"},
                {"text": "Russian gas flows via Nord Stream 1 - currently at 20% capacity"},
                {"text": "Fed minutes release next week"}
            ],
            "trade_ideas": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary_with_section_repetition)
    assert is_low_quality, "Should detect section-level repetition"
    assert "filler:repeated_bullets" in reason, f"Expected 'filler:repeated_bullets' in reason, got: {reason}"
    assert "what_occurred" in reason, f"Expected section name in reason, got: {reason}"
    print(f"  [PASS] Detected: {reason}")


def test_section_level_repetition_multiple_sections():
    """Test detection of repetition across multiple sections."""
    print("\n[TEST 12] Section-level repetition in multiple sections")
    
    summary_with_multiple_repetitions = {
        "sections": {
            "tldr": [
                {"text": "Monitor key developments closely"},
                {"text": "Monitor key developments closely"},  # Duplicate
                {"text": "China manufacturing PMI beat expectations"}
            ],
            "what_occurred": [
                {"text": "US PCE inflation printed 3.2% YoY vs 3.0% expected"},
                {"text": "European natural gas TTF futures surged on supply concerns"},
                {"text": "German manufacturing PMI contracted to 48.2 vs 49.0 expected"}
            ],
            "forward_watch": [
                {"text": "EU energy ministers meeting Thursday"},
                {"text": "Russian gas flows monitoring continues"},
                {"text": "Fed minutes release next week"}
            ],
            "trade_ideas": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary_with_multiple_repetitions)
    assert is_low_quality, "Should detect repetition in any section"
    assert "filler:repeated_bullets" in reason, f"Expected 'filler:repeated_bullets' in reason, got: {reason}"
    print(f"  [PASS] Detected: {reason}")


def run_all_tests():
    """Run all quality gate tests."""
    print("=" * 80)
    print("QUALITY GATE REGRESSION TESTS")
    print("=" * 80)
    
    test_too_few_unique_bullets()
    test_excessive_duplication()
    test_excessive_placeholders()
    test_excessive_short_bullets()
    test_valid_summary_passes()
    test_neutral_trade_ideas_allowed()
    test_completely_empty_summary()
    test_banned_phrase_market_data_pending()
    test_banned_phrase_monitor_key_levels()
    test_banned_phrase_case_insensitive()
    test_section_level_repetition()
    test_section_level_repetition_multiple_sections()
    
    print("\n" + "=" * 80)
    print("ALL TESTS PASSED")
    print("=" * 80)


if __name__ == "__main__":
    run_all_tests()
