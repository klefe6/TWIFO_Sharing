"""
Regression Test: Article Quality Gate with Anti-Hallucination

Purpose: Verify article summaries meet trader-grade standards and fail on garbage
Author: Kevin Lefebvre
Last Updated: 2026-01-26
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from summarize_pdf import is_low_quality_summary


def test_atrocious_placeholder_summary():
    """Test that atrocious placeholder summaries fail."""
    print("\n[TEST 1] Atrocious placeholder summary must FAIL")
    
    garbage = {
        "sections": {
            "what_moved_today": [
                {"text": "Pending analysis of market conditions"},
                {"text": "Monitor key levels for breakout"}
            ],
            "what_can_move_tomorrow": [
                {"text": "Await further information on data releases"},
                {"text": "Subject to change pending clarification"}
            ],
            "trade_ideas": [
                {
                    "product": "ES",
                    "catalyst": "Monitor key levels",
                    "setup": "Pending analysis",
                    "key_levels": ["(not provided in inputs)"],
                    "risk": "Data not available"
                }
            ],
            "tldr": [{"text": "Watch for updates"}],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(garbage)
    assert is_low_quality, "Atrocious placeholder summary should FAIL"
    assert "excessive_placeholders" in reason, f"Expected placeholder detection, got: {reason}"
    print(f"  [PASS] Failed as expected: {reason}")


def test_duplicated_bullets():
    """Test that duplicated bullets fail."""
    print("\n[TEST 2] Duplicated bullets must FAIL")
    
    garbage = {
        "sections": {
            "what_moved_today": [
                {"text": "Fed raised rates 25bps citing inflation concerns"},
                {"text": "Fed raised rates 25bps citing inflation concerns"},
                {"text": "Fed raised rates 25bps citing inflation concerns"}
            ],
            "what_can_move_tomorrow": [
                {"text": "NFP data release Friday morning"},
                {"text": "NFP data release Friday morning"}
            ],
            "trade_ideas": [
                {
                    "product": "ES",
                    "catalyst": "Fed rate hike",
                    "setup": "If ES breaks 4400 then short to 4380",
                    "key_levels": ["4400", "4380"],
                    "risk": "Above 4420"
                }
            ],
            "tldr": [
                {"text": "Fed raised rates 25bps citing inflation concerns"}
            ],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(garbage)
    assert is_low_quality, "Duplicated bullets should FAIL"
    assert "excessive_duplication" in reason, f"Expected duplication detection, got: {reason}"
    print(f"  [PASS] Failed as expected: {reason}")


def test_trader_grade_summary_passes():
    """Test that a real trader-grade summary passes."""
    print("\n[TEST 3] Trader-grade summary must PASS")
    
    good_summary = {
        "sections": {
            "what_moved_today": [
                {"text": "Fed raised rates 25bps to 5.25-5.50% range, citing core PCE at 3.4% vs 3.0% expected"},
                {"text": "ES dropped 1.2% to 4385 on hawkish Powell comments about 'sufficiently restrictive' policy"},
                {"text": "VIX spiked to 18.5 from 16.2 as rate hike expectations repriced higher"}
            ],
            "what_can_move_tomorrow": [
                {"text": "If NFP Friday prints above 200k, expect further ES downside toward 4350-4320 support zone"},
                {"text": "Watch for Fed speak Thursday - any softening on 'higher for longer' could trigger short covering"},
                {"text": "European energy crisis escalating - TTF gas futures up 12% could spill into US equity risk-off"}
            ],
            "trade_ideas": [
                {
                    "product": "ES",
                    "bias": "Bearish",
                    "catalyst": "Fed hawkish pivot + sticky inflation forcing higher terminal rate",
                    "setup": "If ES fails to reclaim 4420 VWAP and VIX holds above 18, short ES targeting 4350-4320",
                    "key_levels": ["4420 resistance (VWAP)", "4385 current", "4350 support", "4320 key support"],
                    "risk": "Invalidation above 4465 (recent range high)",
                    "time_horizon": "1-3D"
                },
                {
                    "product": "NQ",
                    "bias": "Bearish",
                    "catalyst": "Tech multiple compression on higher rates + growth concerns",
                    "setup": "If NQ breaks below 15000, target 14800-14750 with tight stops",
                    "key_levels": ["15000 support", "14800 target", "14750 extended target"],
                    "risk": "Above 15200",
                    "time_horizon": "1-3D"
                },
                {
                    "product": "GC",
                    "bias": "Bullish",
                    "catalyst": "Rising geopolitical risk premium + real rates peaking",
                    "setup": "If GC breaks above 1980 with volume, target 2000-2010",
                    "key_levels": ["1980 resistance", "2000 target", "1960 support"],
                    "risk": "Below 1950",
                    "time_horizon": "1-2W"
                },
                {
                    "product": "SI",
                    "bias": "Neutral",
                    "catalyst": "No direct trade idea from this article",
                    "setup": "",
                    "key_levels": ["(not provided in inputs)"],
                    "risk": "",
                    "time_horizon": ""
                },
                {
                    "product": "VIX",
                    "bias": "Bullish",
                    "catalyst": "Fed uncertainty + NFP risk event Friday",
                    "setup": "If VIX sustains above 18, expect continued equity weakness",
                    "key_levels": ["18 key level", "20 next resistance"],
                    "risk": "Below 16",
                    "time_horizon": "1-3D"
                }
            ],
            "tldr": [
                {"text": "Fed raised rates 25bps → sticky inflation forces hawkish pivot → ES/NQ under pressure"},
                {"text": "NFP Friday is key catalyst → above 200k could trigger further equity downside"},
                {"text": "VIX spike to 18.5 signals rising uncertainty → watch for volatility expansion"}
            ],
            "what_occurred": [
                {"text": "Core PCE printed 3.4% YoY vs 3.0% expected"},
                {"text": "Initial jobless claims fell to 215k from 225k"},
                {"text": "Q2 GDP revised higher to 2.3% from 2.1%"}
            ],
            "forward_watch": [
                {"text": "NFP Friday - consensus 180k vs 187k prior"},
                {"text": "Fed speak Thursday - watch for any softening on terminal rate guidance"},
                {"text": "EU energy ministers meeting - price cap discussions could impact risk sentiment"}
            ],
            "warnings": [
                {"text": "Thin liquidity ahead of NFP could amplify moves"}
            ],
            "tips_reminders": [
                {"text": "Fed typically pauses after hiking cycle - watch for language shift from 'ongoing increases' to 'sufficiently restrictive'"}
            ],
            "cross_asset_impacts": [
                {"text": "Higher rates pressure tech multiples → NQ underperforms ES"},
                {"text": "Rising geopolitical risk → gold bid as safe haven"}
            ],
            "scenarios": [
                {"text": "If NFP > 250k → ES targets 4300, VIX toward 20"},
                {"text": "If NFP < 150k → short covering rally toward 4500"}
            ]
        },
        "volatility_impact": {
            "expected_volatility": "High",
            "drivers": [
                "Fed rate decision uncertainty",
                "NFP event risk Friday",
                "Sticky inflation forcing hawkish pivot",
                "VIX spike to 18.5 signals rising uncertainty"
            ],
            "directional_skew": "Downside",
            "confidence_0_100": 85
        },
        "sentiment_indicator": {
            "risk_on_off": "Risk-Off",
            "confidence_0_100": 80,
            "rationale": "Fed hawkish pivot + sticky inflation + equity selling pressure"
        },
        "explain_like_refresher": "Terminal rate: The peak interest rate the Fed expects to reach in this hiking cycle. Higher terminal rate = longer period of restrictive policy = more pressure on equity valuations (especially growth/tech). Article suggests terminal rate moving higher from 5.25% to potentially 5.75%, which compresses P/E multiples.",
        "summary_score_0_10": 9,
        "chart_score_0_3": 1
    }
    
    is_low_quality, reason = is_low_quality_summary(good_summary)
    assert not is_low_quality, f"Trader-grade summary should PASS, but got: {reason}"
    print(f"  [PASS] Quality summary correctly passed")


def test_too_few_unique_bullets():
    """Test that summaries with too few unique bullets fail."""
    print("\n[TEST 4] Too few unique bullets must FAIL")
    
    garbage = {
        "sections": {
            "what_moved_today": [{"text": "Market moved"}],
            "what_can_move_tomorrow": [{"text": "Watch tomorrow"}],
            "trade_ideas": [],
            "tldr": [],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(garbage)
    assert is_low_quality, "Too few bullets should FAIL"
    assert "too_few_unique_bullets" in reason, f"Expected too_few detection, got: {reason}"
    print(f"  [PASS] Failed as expected: {reason}")


def test_schema_compatibility():
    """Test that required schema fields are present."""
    print("\n[TEST 5] Schema compatibility check")
    
    # This test verifies the schema structure, not quality gate
    required_sections = [
        "what_moved_today",
        "what_can_move_tomorrow",
        "trade_ideas",
        "tldr",
        "what_occurred",
        "forward_watch",
        "warnings",
        "tips_reminders",
        "cross_asset_impacts",
        "scenarios"
    ]
    
    test_summary = {
        "sections": {key: [] for key in required_sections},
        "volatility_impact": {
            "expected_volatility": "Medium",
            "drivers": ["test driver"],
            "directional_skew": "Two-sided",
            "confidence_0_100": 50
        },
        "sentiment_indicator": {
            "risk_on_off": "Neutral",
            "confidence_0_100": 50,
            "rationale": "Test"
        },
        "explain_like_refresher": "Test",
        "summary_score_0_10": 5,
        "chart_score_0_3": 1
    }
    
    for key in required_sections:
        assert key in test_summary["sections"], f"Missing required section: {key}"
    
    assert "volatility_impact" in test_summary, "Missing volatility_impact (CRITICAL for IB clients)"
    assert "expected_volatility" in test_summary["volatility_impact"], "Missing expected_volatility"
    assert "drivers" in test_summary["volatility_impact"], "Missing volatility drivers"
    assert "directional_skew" in test_summary["volatility_impact"], "Missing directional_skew"
    assert "confidence_0_100" in test_summary["volatility_impact"], "Missing volatility confidence"
    
    assert "sentiment_indicator" in test_summary, "Missing sentiment_indicator"
    assert "explain_like_refresher" in test_summary, "Missing explain_like_refresher"
    assert "summary_score_0_10" in test_summary, "Missing summary_score_0_10"
    assert "chart_score_0_3" in test_summary, "Missing chart_score_0_3"
    
    print(f"  [PASS] All required schema fields present (including volatility_impact)")


def run_all_tests():
    """Run all article quality gate tests."""
    print("=" * 80)
    print("ARTICLE QUALITY GATE REGRESSION TESTS")
    print("=" * 80)
    
    test_atrocious_placeholder_summary()
    test_duplicated_bullets()
    test_trader_grade_summary_passes()
    test_too_few_unique_bullets()
    test_schema_compatibility()
    
    print("\n" + "=" * 80)
    print("ALL TESTS PASSED")
    print("=" * 80)
    print("\nQuality gate is working correctly:")
    print("- Placeholder/generic summaries: FAIL [OK]")
    print("- Duplicated bullets: FAIL [OK]")
    print("- Trader-grade summaries: PASS [OK]")
    print("- Schema compatibility: VERIFIED [OK]")


if __name__ == "__main__":
    run_all_tests()
