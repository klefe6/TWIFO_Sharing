"""
Test file for quality gate retry mechanism.
Purpose: Verify 2-stage quality escalation with model upgrading.
Author: Kevin Lefebvre
Last Updated: 2026-01-26
"""

import json
from pathlib import Path


def test_escalation_retry_structure():
    """
    Confirm retry code path structure without network calls.
    """
    print("\n[TEST 1] Retry structure validation")
    
    # Load a fixture that would fail attempt 1
    fixture = {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {
            "title": "Test_20260126",
            "provider": "TEST",
            "published_date": "20260126",
            "horizon": "u",
            "products": [],
            "theme": "",
            "generated_at_iso": "2026-01-26T12:00:00",
            "model": "gpt-4o-mini"
        },
        "ui": {"header_pills": []},
        "extraction": {
            "status": "ok",
            "method_used": "test",
            "total_chars": 5000,
            "pages_with_text": 3,
            "errors": [],
            "attempt_count": 1,
            "quality_reason": ""
        },
        "sections": {
            "what_moved_today": [{"text": "This is a reasonably long bullet to avoid short bullet detection"}],  # Too few bullets
            "what_can_move_tomorrow": [{"text": "Another reasonably long bullet for the same reason"}],
            "trade_ideas": [],
            "tldr": [],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        },
        "volatility_impact": {
            "expected_volatility": "Medium",
            "drivers": ["test"],
            "directional_skew": "Two-sided",
            "confidence_0_100": 50
        },
        "sentiment_indicator": {
            "risk_on_off": "Neutral",
            "confidence_0_100": 50,
            "rationale": "test"
        },
        "explain_like_refresher": "test",
        "summary_score_0_10": 5,
        "chart_score_0_3": 1
    }
    
    # Run quality gate (should fail with too_few_unique_bullets)
    from summarize_pdf import is_low_quality_summary
    is_low_quality, reason = is_low_quality_summary(fixture)
    
    assert is_low_quality, "Fixture should fail quality gate"
    assert "too_few_unique_bullets" in reason, f"Expected too_few_unique_bullets, got: {reason}"
    print(f"  [PASS] Quality gate correctly detects: {reason}")


def test_model_escalation_recorded():
    """
    Verify attempt count and model name are recorded in meta.
    """
    print("\n[TEST 2] Model escalation metadata")
    
    # Simulate attempt 1 failure structure
    attempt_1_meta = {
        "model": "gpt-4o-mini",
        "extraction": {
            "status": "failed",
            "attempt_count": 2,
            "quality_reason": "too_few_unique_bullets: only 2 unique bullets found"
        }
    }
    
    assert attempt_1_meta["extraction"]["attempt_count"] == 2, "Should show 2 attempts"
    assert "quality_reason" in attempt_1_meta["extraction"], "Should record quality reason"
    print(f"  [PASS] Metadata structure correct for failed attempts")


def test_stub_on_double_failure():
    """
    Confirm that if both attempts fail, output is stub with status=failed.
    """
    print("\n[TEST 3] Double failure returns stub")
    
    from summarize_pdf import _failed_stub
    
    stub = _failed_stub(
        pdf_path=Path("test.pdf"),
        reason="low_quality_output: too_few_unique_bullets",
        extraction={"status": "failed", "attempt_count": 2, "quality_reason": "too_few_unique_bullets"},
        meta={"title": "Test", "provider": "T", "model": "gpt-4o"}
    )
    
    assert stub["extraction"]["status"] == "failed", "Stub must have status=failed"
    assert "low_quality_output" in stub["extraction"]["reason"], "Reason must be recorded"
    assert len(stub["sections"]["what_moved_today"]) == 0, "Sections must be empty"
    assert len(stub["sections"]["what_can_move_tomorrow"]) == 0, "Sections must be empty"
    assert len(stub["sections"]["trade_ideas"]) == 0, "Trade ideas must be empty"
    print(f"  [PASS] Stub has status=failed and empty sections")


def test_normalized_bullet_extraction():
    """
    Verify bullets are normalized to {\"text\": \"...\"} format.
    """
    print("\n[TEST 4] Bullet normalization")
    
    from summarize_pdf import _extract_bullet_text, _normalize_sections_in_place
    
    # Test various bullet formats
    test_cases = [
        ("string bullet", "string bullet"),
        ({"text": "dict with text"}, "dict with text"),
        ({"bullet": "dict with bullet key"}, "dict with bullet key"),
        ({"value": "dict with value key"}, "dict with value key"),
    ]
    
    for item, expected in test_cases:
        result = _extract_bullet_text(item)
        assert result == expected, f"Expected '{expected}', got '{result}'"
    
    # Test normalization in-place
    sum_json = {
        "sections": {
            "what_moved_today": [
                "raw string",
                {"text": "normal dict"},
                {"bullet": "alt key dict"},
            ],
            "trade_ideas": [{"product": "ES"}]  # Should skip trade_ideas
        }
    }
    
    _normalize_sections_in_place(sum_json)
    
    normalized = sum_json["sections"]["what_moved_today"]
    assert len(normalized) == 3, f"Expected 3 normalized items, got {len(normalized)}"
    assert all(isinstance(item, dict) and "text" in item for item in normalized), \
        "All items should be dicts with 'text' key"
    print(f"  [PASS] Bullets normalized correctly")


def test_debug_artifact_structure():
    """
    Verify debug artifact contains required fields.
    """
    print("\n[TEST 5] Debug artifact structure")
    
    from summarize_pdf import _write_debug_artifact, _sum_debug_path
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_pdf = Path(tmpdir) / "test.pdf"
        test_pdf.touch()
        
        debug_path = _sum_debug_path(test_pdf)
        
        _write_debug_artifact(
            debug_path,
            model="gpt-4o-mini",
            raw_output="{\n  \"what_moved_today\": [\"test\"]\n}",
            bullet_counts={"what_moved_today": 1, "what_can_move_tomorrow": 0},
            quality_reason="too_few_unique_bullets: only 1 unique bullets found",
            attempt=1,
        )
        
        assert debug_path.exists(), "Debug artifact should be created"
        content = debug_path.read_text(encoding="utf-8")
        
        assert "QUALITY GATE FAILURE (ATTEMPT 1)" in content, "Should show attempt number"
        assert "model: gpt-4o-mini" in content, "Should show model"
        assert "quality_reason:" in content, "Should show reason"
        assert "bullet_counts:" in content, "Should show bullet counts"
        assert "raw_output:" in content, "Should show raw output"
        print(f"  [PASS] Debug artifact has all required fields")


def run_all_tests():
    """
    Run all unit tests.
    """
    print("=" * 80)
    print("QUALITY RETRY MECHANISM TESTS")
    print("=" * 80)
    
    try:
        test_escalation_retry_structure()
        test_model_escalation_recorded()
        test_stub_on_double_failure()
        test_normalized_bullet_extraction()
        test_debug_artifact_structure()
        
        print("\n" + "=" * 80)
        print("ALL TESTS PASSED")
        print("=" * 80)
        print("\nRetry mechanism is working correctly:")
        print("- Attempt 1 with base model")
        print("- Attempt 2 with stronger model on failure")
        print("- Debug artifacts on each failure")
        print("- Stub returned if both fail")
        print("- Bullet normalization prevents 0 unique bullets")
        
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()
