"""
Test suite for Economic Brief currency/region attribution fix.

Ensures that EUR CPI does not generate USD-focused reactions,
and that each event currency correctly conditions the macro reaction logic.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from econ_calendar_ai import _build_brief_prompt


def test_eur_cpi_prompt_attribution():
    """Test Case A: EUR CPI must reference EURUSD and Bunds, NOT USD as primary."""
    print("\n" + "=" * 80)
    print("TEST A: EUR CPI Event - Must focus on EURUSD/Bunds, not USD")
    print("=" * 80)
    
    mock_events = [
        {
            "time_local": "05:00",
            "title": "CPI YoY",
            "currency_tag": "EUR",
            "country_or_region": "Eurozone",
        }
    ]
    
    mock_ranked = [
        {
            "event_key": "05:00|cpi yoy",
            "priority": 1,
            "importance_tier": "high",
            "reason": "Major inflation data"
        }
    ]
    
    prompt = _build_brief_prompt(
        date_iso="2026-02-26",
        events=mock_events,
        ranked=mock_ranked,
        macro_context_text="Market volatility elevated.",
        dynamics_mode=True
    )
    
    # Verify prompt contains EUR-specific guidance
    assert "EUR events: Primary impact on EURUSD, Bund yields, Euro Stoxx, DAX" in prompt, \
        "Prompt must include EUR-specific guidance"
    
    assert "USD, ES, GC are SECONDARY spillover only" in prompt, \
        "Prompt must specify USD as secondary for EUR events"
    
    assert "CURRENCY/REGION REACTION TEMPLATES" in prompt, \
        "Prompt must include currency reaction templates section"
    
    assert "[HIGH] 05:00 | CPI YoY (EUR, Eurozone)" in prompt, \
        "Event must show EUR currency tag"
    
    assert "Never mention USD, DXY, ES, SPX, US10Y, or GC as PRIMARY products unless the event currency is USD" in prompt, \
        "Prompt must include hard constraint against USD attribution for non-USD events"
    
    print("[OK] Prompt correctly identifies EUR event")
    print("[OK] Prompt includes EUR-specific reaction template")
    print("[OK] Prompt specifies USD as SECONDARY spillover only")
    print("[OK] Prompt includes hard constraint")
    sys.stdout.buffer.write(b"[PASS] EUR CPI prompt attribution correct\n")


def test_usd_cpi_prompt_attribution():
    """Test Case B: USD CPI must reference DXY, US10Y, ES as primary."""
    print("\n" + "=" * 80)
    print("TEST B: USD CPI Event - Must focus on USD/US rates/equities")
    print("=" * 80)
    
    mock_events = [
        {
            "time_local": "08:30",
            "title": "CPI YoY",
            "currency_tag": "USD",
            "country_or_region": "United States",
        }
    ]
    
    mock_ranked = [
        {
            "event_key": "08:30|cpi yoy",
            "priority": 1,
            "importance_tier": "high",
            "reason": "Major inflation data"
        }
    ]
    
    prompt = _build_brief_prompt(
        date_iso="2026-02-27",
        events=mock_events,
        ranked=mock_ranked,
        macro_context_text="Fed in focus.",
        dynamics_mode=True
    )
    
    # Verify prompt contains USD-specific guidance
    assert "USD events: Primary impact on DXY, US10Y, ES, SPX, GC" in prompt, \
        "Prompt must include USD-specific guidance"
    
    assert "[HIGH] 08:30 | CPI YoY (USD, United States)" in prompt, \
        "Event must show USD currency tag"
    
    # Verify EUR guidance is NOT present (only USD event)
    assert "EUR events:" not in prompt, \
        "Prompt should not include EUR guidance when only USD events present"
    
    print("[OK] Prompt correctly identifies USD event")
    print("[OK] Prompt includes USD-specific reaction template")
    print("[OK] Prompt does not include irrelevant currency guidance")
    sys.stdout.buffer.write(b"[PASS] USD CPI prompt attribution correct\n")


def test_gbp_event_prompt_attribution():
    """Test Case C: GBP data must reference GBPUSD and Gilts, with USD as secondary."""
    print("\n" + "=" * 80)
    print("TEST C: GBP Event - Must focus on GBPUSD/Gilts")
    print("=" * 80)
    
    mock_events = [
        {
            "time_local": "07:00",
            "title": "GDP QoQ",
            "currency_tag": "GBP",
            "country_or_region": "United Kingdom",
        }
    ]
    
    mock_ranked = [
        {
            "event_key": "07:00|gdp qoq",
            "priority": 1,
            "importance_tier": "high",
            "reason": "Growth data"
        }
    ]
    
    prompt = _build_brief_prompt(
        date_iso="2026-02-28",
        events=mock_events,
        ranked=mock_ranked,
        macro_context_text="",
        dynamics_mode=False
    )
    
    # Verify prompt contains GBP-specific guidance
    assert "GBP events: Primary impact on GBPUSD, Gilts, FTSE" in prompt, \
        "Prompt must include GBP-specific guidance"
    
    assert "USD markets are SECONDARY spillover only" in prompt, \
        "Prompt must specify USD as secondary for GBP events"
    
    assert "[HIGH] 07:00 | GDP QoQ (GBP, United Kingdom)" in prompt, \
        "Event must show GBP currency tag"
    
    print("[OK] Prompt correctly identifies GBP event")
    print("[OK] Prompt includes GBP-specific reaction template")
    print("[OK] Prompt specifies USD as SECONDARY")
    sys.stdout.buffer.write(b"[PASS] GBP event prompt attribution correct\n")


def test_jpy_boj_prompt_attribution():
    """Test Case D: JPY/BOJ events must reference USDJPY and JGBs."""
    print("\n" + "=" * 80)
    print("TEST D: JPY/BOJ Event - Must focus on USDJPY/JGB/Nikkei")
    print("=" * 80)
    
    mock_events = [
        {
            "time_local": "03:00",
            "title": "BOJ Policy Decision",
            "currency_tag": "JPY",
            "country_or_region": "Japan",
        }
    ]
    
    mock_ranked = [
        {
            "event_key": "03:00|boj policy decision",
            "priority": 1,
            "importance_tier": "high",
            "reason": "Central bank decision"
        }
    ]
    
    prompt = _build_brief_prompt(
        date_iso="2026-03-01",
        events=mock_events,
        ranked=mock_ranked,
        macro_context_text="BOJ dovish expectations.",
        dynamics_mode=True
    )
    
    # Verify prompt contains JPY-specific guidance
    assert "JPY events (including BOJ): Primary impact on USDJPY, JGB, Nikkei" in prompt, \
        "Prompt must include JPY-specific guidance"
    
    assert "USD markets are SECONDARY spillover only" in prompt, \
        "Prompt must specify USD as secondary for JPY events"
    
    assert "[HIGH] 03:00 | BOJ Policy Decision (JPY, Japan)" in prompt, \
        "Event must show JPY currency tag"
    
    print("[OK] Prompt correctly identifies JPY/BOJ event")
    print("[OK] Prompt includes JPY-specific reaction template")
    print("[OK] Prompt specifies USD as SECONDARY")
    sys.stdout.buffer.write(b"[PASS] JPY/BOJ event prompt attribution correct\n")


def test_unknown_currency_prompt_attribution():
    """Test Case E: Unknown currency events must use general guidance, no USD-specific mention."""
    print("\n" + "=" * 80)
    print("TEST E: Unknown Currency Event - Must use GENERAL guidance")
    print("=" * 80)
    
    mock_events = [
        {
            "time_local": "All Day",
            "title": "Market Holiday",
            "currency_tag": "",
            "country_or_region": "Brazil",
        }
    ]
    
    mock_ranked = [
        {
            "event_key": "all_day|market holiday",
            "priority": 1,
            "importance_tier": "low",
            "reason": "Holiday"
        }
    ]
    
    prompt = _build_brief_prompt(
        date_iso="2026-03-02",
        events=mock_events,
        ranked=mock_ranked,
        macro_context_text="",
        dynamics_mode=False
    )
    
    # Verify prompt contains generic guidance when currency is unknown
    assert "Events lack clear currency tags" in prompt or "CURRENCY/REGION REACTION TEMPLATES" in prompt, \
        "Prompt must handle unknown currencies"
    
    assert "Use GENERAL labeling and avoid mentioning USD specifically unless the event explicitly references US data" in prompt, \
        "Prompt must instruct to avoid USD-specific mention for unknown currencies"
    
    print("[OK] Prompt handles unknown currency correctly")
    print("[OK] Prompt includes generic guidance")
    sys.stdout.buffer.write(b"[PASS] Unknown currency prompt attribution correct\n")


def test_mixed_currencies_prompt():
    """Test Case F: Mixed currencies must include multiple region templates."""
    print("\n" + "=" * 80)
    print("TEST F: Mixed Currencies - Must include all relevant templates")
    print("=" * 80)
    
    mock_events = [
        {
            "time_local": "05:00",
            "title": "CPI YoY",
            "currency_tag": "EUR",
            "country_or_region": "Eurozone",
        },
        {
            "time_local": "08:30",
            "title": "NFP",
            "currency_tag": "USD",
            "country_or_region": "United States",
        },
        {
            "time_local": "09:30",
            "title": "GDP QoQ",
            "currency_tag": "GBP",
            "country_or_region": "United Kingdom",
        }
    ]
    
    mock_ranked = [
        {
            "event_key": "08:30|nfp",
            "priority": 1,
            "importance_tier": "high",
            "reason": "Major jobs data"
        },
        {
            "event_key": "05:00|cpi yoy",
            "priority": 2,
            "importance_tier": "high",
            "reason": "Inflation data"
        },
        {
            "event_key": "09:30|gdp qoq",
            "priority": 3,
            "importance_tier": "medium",
            "reason": "Growth data"
        }
    ]
    
    prompt = _build_brief_prompt(
        date_iso="2026-03-03",
        events=mock_events,
        ranked=mock_ranked,
        macro_context_text="",
        dynamics_mode=True
    )
    
    # Verify prompt contains ALL relevant currency guidance
    assert "USD events: Primary impact on DXY, US10Y, ES, SPX, GC" in prompt, \
        "Prompt must include USD guidance"
    
    assert "EUR events: Primary impact on EURUSD, Bund yields, Euro Stoxx, DAX" in prompt, \
        "Prompt must include EUR guidance"
    
    assert "GBP events: Primary impact on GBPUSD, Gilts, FTSE" in prompt, \
        "Prompt must include GBP guidance"
    
    # Verify all events are listed
    assert "[HIGH] 08:30 | NFP (USD, United States)" in prompt, \
        "USD event must be present"
    
    assert "[HIGH] 05:00 | CPI YoY (EUR, Eurozone)" in prompt, \
        "EUR event must be present"
    
    assert "[MEDIUM] 09:30 | GDP QoQ (GBP, United Kingdom)" in prompt, \
        "GBP event must be present"
    
    print("[OK] Prompt includes USD guidance")
    print("[OK] Prompt includes EUR guidance")
    print("[OK] Prompt includes GBP guidance")
    print("[OK] All events present with correct currency tags")
    sys.stdout.buffer.write(b"[PASS] Mixed currencies prompt attribution correct\n")


def run_all_tests():
    """Run all test functions."""
    print("=" * 80)
    print("ECONOMIC BRIEF CURRENCY ATTRIBUTION TEST SUITE")
    print("=" * 80)
    print("\nTesting that EUR CPI never generates USD-focused reactions,")
    print("and that each currency correctly conditions macro reaction logic.")
    
    test_functions = [
        test_eur_cpi_prompt_attribution,
        test_usd_cpi_prompt_attribution,
        test_gbp_event_prompt_attribution,
        test_jpy_boj_prompt_attribution,
        test_unknown_currency_prompt_attribution,
        test_mixed_currencies_prompt,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in test_functions:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"\n[FAIL] {test_func.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        except Exception as e:
            print(f"\n[ERROR] {test_func.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 80)
    
    if failed == 0:
        print("\n[SUCCESS] All tests passed! Currency attribution logic is correct.")
        print("[SUCCESS] EUR CPI will NOT generate USD-focused reactions.")
        print("[SUCCESS] Each currency correctly conditions macro reaction templates.")
    else:
        print(f"\n[FAIL] {failed} test(s) failed. Please review and fix.")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

