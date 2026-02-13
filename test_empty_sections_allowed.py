"""
Test: Empty Sections Allowed (No Filler Requirement)
Purpose: Verify that articles with weak content produce empty sections and pass quality gate
Author: Kevin Lefebvre
Last Updated: 2026-02-12

Tests the fix for prompt + quality gate to allow [] sections when article doesn't support content.
tldr must remain EXACTLY 3 bullets.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from summarize_pdf import is_low_quality_summary


def test_weak_article_with_empty_sections_passes():
    """
    Test that a weak article with only tldr (3 bullets) and empty other sections passes quality gate.
    This is the key behavior change: empty sections are now VALID.
    """
    print("\n[TEST 1] Weak article with empty sections (should PASS quality gate)")
    
    summary = {
        "sections": {
            "tldr": [
                "Article discusses general market conditions",
                "No specific price levels or catalysts mentioned",
                "Author provides general macro overview"
            ],
            "what_moved_today": [],  # Empty - article has no specific past data
            "what_can_move_tomorrow": [],  # Empty - article has no forward catalysts
            "what_occurred": [],  # Empty
            "forward_watch": [],  # Empty
            "warnings": [],  # Empty
            "tips_reminders": [],  # Empty
            "cross_asset_impacts": [],  # Empty
            "scenarios": [],  # Empty
            "trade_ideas": []  # Empty - no actionable ideas
        },
        "meta": {
            "title": "Weak Article Test",
            "provider": "TEST"
        },
        "extraction": {
            "status": "ok"
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary)
    
    # Should PASS (is_low_quality = False)
    assert not is_low_quality, f"Weak article with valid tldr should pass, but got: {reason}"
    print(f"  [PASS] Weak article with only tldr passes quality gate")
    print(f"  Reason: Empty sections are now valid (no filler required)")


def test_only_tldr_with_good_content_passes():
    """
    Test that an article with detailed tldr but sparse other sections passes.
    """
    print("\n[TEST 2] Article with detailed tldr, sparse other sections (should PASS)")
    
    summary = {
        "sections": {
            "tldr": [
                "Gold prices reached $2,150 on safe-haven demand",
                "Fed signals potential rate cuts in Q2 2026",
                "Equity volatility increased on geopolitical tensions"
            ],
            "what_moved_today": [
                "Gold rallied 2.3% to $2,150 on safe-haven flows"
            ],
            "what_can_move_tomorrow": [],  # Empty - no forward catalysts
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": [],
            "trade_ideas": []
        },
        "meta": {
            "title": "Sparse Article Test",
            "provider": "TEST"
        },
        "extraction": {
            "status": "ok"
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary)
    
    assert not is_low_quality, f"Article with good tldr + sparse sections should pass, but got: {reason}"
    print(f"  [PASS] Article with detailed tldr + sparse sections passes")


def test_banned_phrase_still_fails():
    """
    Test that banned phrases like 'market data pending analysis' still trigger quality gate failure.
    This ensures quality gate remains active for filler detection.
    """
    print("\n[TEST 3] Banned phrase 'market data pending analysis' (should FAIL)")
    
    summary = {
        "sections": {
            "tldr": [
                "Article discusses market conditions",
                "Market data pending analysis for key levels",  # BANNED PHRASE
                "Author provides outlook"
            ],
            "what_moved_today": [],
            "what_can_move_tomorrow": [],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": [],
            "trade_ideas": []
        },
        "meta": {
            "title": "Banned Phrase Test",
            "provider": "TEST"
        },
        "extraction": {
            "status": "ok"
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary)
    
    # Should FAIL (is_low_quality = True)
    assert is_low_quality, "Banned phrase should trigger quality gate failure"
    assert "market data pending analysis" in reason, f"Expected banned phrase in reason, got: {reason}"
    print(f"  [PASS] Banned phrase correctly triggers quality gate failure")
    print(f"  Reason: {reason}")


def test_generic_placeholders_still_fail():
    """
    Test that excessive generic placeholders still fail quality gate.
    """
    print("\n[TEST 4] Excessive generic placeholders (should FAIL)")
    
    summary = {
        "sections": {
            "tldr": [
                "Monitor key levels for potential breakout",
                "Watch for updates on data releases",
                "Pending clarification on policy stance"
            ],
            "what_moved_today": [
                "Monitor developments in equity markets",
                "Data releases pending"
            ],
            "what_can_move_tomorrow": [
                "Await further information on Fed policy"
            ],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": [],
            "trade_ideas": []
        },
        "meta": {
            "title": "Placeholder Test",
            "provider": "TEST"
        },
        "extraction": {
            "status": "ok"
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary)
    
    # Should FAIL due to excessive placeholders
    assert is_low_quality, "Excessive placeholders should fail quality gate"
    assert "placeholder" in reason.lower() or "filler" in reason.lower(), (
        f"Expected placeholder/filler in reason, got: {reason}"
    )
    print(f"  [PASS] Excessive placeholders correctly fail quality gate")
    print(f"  Reason: {reason}")


def test_repeated_bullets_still_fail():
    """
    Test that repeated identical bullets within a section still fail.
    """
    print("\n[TEST 5] Repeated bullets in section (should FAIL)")
    
    summary = {
        "sections": {
            "tldr": [
                "Gold prices rose on safe-haven demand",
                "Equity markets declined on risk-off sentiment",
                "Treasury yields fell as investors sought safety"
            ],
            "what_moved_today": [
                "Gold gained 2% on safe-haven flows",
                "Gold gained 2% on safe-haven flows",  # DUPLICATE
                "Equities declined across the board"
            ],
            "what_can_move_tomorrow": [],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": [],
            "trade_ideas": []
        },
        "meta": {
            "title": "Repeated Bullets Test",
            "provider": "TEST"
        },
        "extraction": {
            "status": "ok"
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary)
    
    # Should FAIL due to repeated bullets
    assert is_low_quality, "Repeated bullets should fail quality gate"
    assert "repeated" in reason.lower(), f"Expected 'repeated' in reason, got: {reason}"
    print(f"  [PASS] Repeated bullets correctly fail quality gate")
    print(f"  Reason: {reason}")


def test_tldr_must_have_3_bullets():
    """
    Test that tldr with < 3 bullets fails (tldr is still mandatory with exactly 3).
    """
    print("\n[TEST 6] tldr with < 3 bullets (should FAIL)")
    
    summary = {
        "sections": {
            "tldr": [
                "Single bullet only"  # Only 1 bullet
            ],
            "what_moved_today": [],
            "what_can_move_tomorrow": [],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": [],
            "trade_ideas": []
        },
        "meta": {
            "title": "TL;DR Too Short Test",
            "provider": "TEST"
        },
        "extraction": {
            "status": "ok"
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary)
    
    # Should FAIL - tldr must have 3 bullets
    assert is_low_quality, "TL;DR with < 3 bullets should fail"
    print(f"  [PASS] TL;DR with < 3 bullets correctly fails")
    print(f"  Reason: {reason}")


def test_all_empty_except_tldr_passes():
    """
    Test that summary with only tldr (all other sections empty) passes.
    This is the core new behavior: empty sections are valid.
    """
    print("\n[TEST 7] All sections empty except tldr (should PASS)")
    
    summary = {
        "sections": {
            "tldr": [
                "Markets showed mixed performance today",
                "Key economic data releases scheduled for tomorrow",
                "Overall sentiment remains cautious"
            ],
            "what_moved_today": [],
            "what_can_move_tomorrow": [],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": [],
            "trade_ideas": []
        },
        "meta": {
            "title": "Minimal Content Test",
            "provider": "TEST"
        },
        "extraction": {
            "status": "ok"
        }
    }
    
    is_low_quality, reason = is_low_quality_summary(summary)
    
    assert not is_low_quality, f"Summary with only tldr should pass, but got: {reason}"
    print(f"  [PASS] Summary with only tldr (all other sections []) passes")


if __name__ == "__main__":
    tests = [
        test_weak_article_with_empty_sections_passes,
        test_only_tldr_with_good_content_passes,
        test_banned_phrase_still_fails,
        test_generic_placeholders_still_fail,
        test_repeated_bullets_still_fail,
        test_tldr_must_have_3_bullets,
        test_all_empty_except_tldr_passes,
    ]
    
    passed = 0
    failed = 0
    
    print("=" * 70)
    print("EMPTY SECTIONS ALLOWED - QUALITY GATE TESTS")
    print("=" * 70)
    
    for fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {fn.__name__}")
            print(f"    Error: {e}")
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print("=" * 70)
    
    if failed > 0:
        print("\nKey behaviors tested:")
        print("  1. Empty sections (except tldr) are now VALID")
        print("  2. tldr must still have EXACTLY 3 bullets")
        print("  3. Banned phrases still trigger failure")
        print("  4. Excessive placeholders still trigger failure")
        print("  5. Repeated bullets still trigger failure")
    
    sys.exit(1 if failed else 0)
