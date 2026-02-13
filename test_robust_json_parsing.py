"""
Test: Robust JSON Parsing with Recovery
Purpose: Verify extract_first_json_object, repair_json_deterministic, and parse_json_with_recovery
Author: Kevin Lefebvre
Last Updated: 2026-02-12

Tests malformed LLM outputs:
1. Unterminated string (should fail cleanly, write debug artifact, return stub)
2. Extra text before/after JSON (should recover)
3. Trailing commas (should repair)
4. Missing closing braces (should repair if simple)
"""

import sys
import tempfile
import json
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from summarize_pdf import (
    extract_first_json_object,
    repair_json_deterministic,
    parse_json_with_recovery,
)


def test_extract_clean_json():
    """Test extraction of clean JSON."""
    print("\n[TEST 1] Extract clean JSON")
    
    json_str = '{"key": "value", "number": 42}'
    result, error = extract_first_json_object(json_str)
    
    assert result is not None, "Should extract clean JSON"
    assert error is None, "No error expected"
    parsed = json.loads(result)
    assert parsed["key"] == "value"
    print(f"  [PASS] Clean JSON extracted: {result[:50]}...")


def test_extract_json_with_markdown_fences():
    """Test extraction of JSON wrapped in markdown code fences."""
    print("\n[TEST 2] Extract JSON with markdown fences")
    
    json_str = '```json\n{"key": "value"}\n```'
    result, error = extract_first_json_object(json_str)
    
    assert result is not None, "Should extract JSON from markdown"
    assert error is None
    parsed = json.loads(result)
    assert parsed["key"] == "value"
    print(f"  [PASS] JSON extracted from markdown fences")


def test_extract_json_with_extra_text_before():
    """Test extraction of JSON with preamble text."""
    print("\n[TEST 3] Extract JSON with extra text before")
    
    json_str = 'Here is the analysis:\n\n{"key": "value", "data": [1, 2, 3]}'
    result, error = extract_first_json_object(json_str)
    
    assert result is not None, "Should extract JSON ignoring preamble"
    assert error is None
    parsed = json.loads(result)
    assert parsed["key"] == "value"
    assert parsed["data"] == [1, 2, 3]
    print(f"  [PASS] JSON extracted, preamble ignored")


def test_extract_json_with_extra_text_after():
    """Test extraction of JSON with trailing text."""
    print("\n[TEST 4] Extract JSON with extra text after")
    
    json_str = '{"key": "value"}\n\nNote: This is additional commentary.'
    result, error = extract_first_json_object(json_str)
    
    assert result is not None, "Should extract JSON ignoring trailing text"
    assert error is None
    parsed = json.loads(result)
    assert parsed["key"] == "value"
    print(f"  [PASS] JSON extracted, trailing text ignored")


def test_extract_json_with_text_before_and_after():
    """Test extraction with both preamble and trailing text (RECOVERY CASE)."""
    print("\n[TEST 5] Extract JSON with text before AND after (should RECOVER)")
    
    json_str = '''
    The analysis is as follows:
    
    {"tldr": ["First point", "Second point", "Third point"], "sections": {"what_moved": []}}
    
    End of analysis.
    '''
    result, error = extract_first_json_object(json_str)
    
    assert result is not None, "Should extract JSON from middle of text"
    assert error is None
    parsed = json.loads(result)
    assert "tldr" in parsed
    assert len(parsed["tldr"]) == 3
    print(f"  [PASS] JSON recovered from middle of text")


def test_extract_unterminated_string():
    """Test unterminated string (FAILURE CASE)."""
    print("\n[TEST 6] Unterminated string (should FAIL cleanly)")
    
    json_str = '{"key": "value with unterminated string'
    result, error = extract_first_json_object(json_str)
    
    assert result is None, "Should fail on unterminated JSON"
    assert error is not None
    assert "Unterminated" in error or "depth" in error
    print(f"  [PASS] Unterminated string detected: {error}")


def test_extract_no_json():
    """Test input with no JSON."""
    print("\n[TEST 7] No JSON in input")
    
    json_str = "This is just plain text with no JSON at all."
    result, error = extract_first_json_object(json_str)
    
    assert result is None
    assert error is not None
    assert "brace" in error.lower()
    print(f"  [PASS] No JSON detected: {error}")


def test_repair_trailing_commas():
    """Test repair of trailing commas."""
    print("\n[TEST 8] Repair trailing commas")
    
    json_str = '{"key": "value", "array": [1, 2, 3,], "nested": {"a": 1,}}'
    repaired, msg = repair_json_deterministic(json_str)
    
    assert repaired is not None, "Should repair trailing commas"
    assert "trailing_commas" in msg
    parsed = json.loads(repaired)
    assert parsed["key"] == "value"
    assert parsed["array"] == [1, 2, 3]
    print(f"  [PASS] Trailing commas repaired: {msg}")


def test_repair_missing_closing_brace():
    """Test repair of missing closing brace (simple case)."""
    print("\n[TEST 9] Repair missing closing brace")
    
    json_str = '{"key": "value", "nested": {"a": 1}'
    repaired, msg = repair_json_deterministic(json_str)
    
    assert repaired is not None, "Should repair simple missing brace"
    assert "closing_braces" in msg
    parsed = json.loads(repaired)
    assert parsed["key"] == "value"
    print(f"  [PASS] Missing brace repaired: {msg}")


def test_repair_too_many_missing_braces():
    """Test failure when too many braces missing."""
    print("\n[TEST 10] Too many missing braces (should fail)")
    
    json_str = '{"a": {"b": {"c": {"d": "value"'
    repaired, msg = repair_json_deterministic(json_str)
    
    assert repaired is None, "Should not repair too many missing braces"
    assert "Too many" in msg or "unrecoverable" in msg.lower()
    print(f"  [PASS] Complex damage detected as unrecoverable: {msg}")


def test_repair_unterminated_string():
    """Test that unterminated strings are detected as unrecoverable."""
    print("\n[TEST 11] Unterminated string (should fail)")
    
    json_str = '{"key": "value with no closing quote}'
    repaired, msg = repair_json_deterministic(json_str)
    
    # Should either fail or leave as-is
    # The key test is that it doesn't hallucinate a fix
    if repaired is None:
        assert "Unterminated string" in msg
        print(f"  [PASS] Unterminated string detected: {msg}")
    else:
        # If it didn't detect, ensure it still fails to parse
        try:
            json.loads(repaired)
            assert False, "Should not successfully parse unterminated string"
        except json.JSONDecodeError:
            print(f"  [PASS] Unterminated string left unrepaired (will fail parse)")


def test_parse_with_recovery_clean_json():
    """Test parse_json_with_recovery with clean JSON (fast path)."""
    print("\n[TEST 12] Parse clean JSON (fast path)")
    
    json_str = '{"key": "value", "number": 42}'
    result, status = parse_json_with_recovery(json_str)
    
    assert result is not None
    assert "Direct parse succeeded" in status
    assert result["key"] == "value"
    print(f"  [PASS] Fast path used: {status}")


def test_parse_with_recovery_markdown():
    """Test parse_json_with_recovery with markdown fences."""
    print("\n[TEST 13] Parse JSON with markdown (extraction)")
    
    json_str = '```json\n{"key": "value"}\n```'
    result, status = parse_json_with_recovery(json_str)
    
    assert result is not None
    assert result["key"] == "value"
    print(f"  [PASS] Extracted and parsed: {status}")


def test_parse_with_recovery_extra_text():
    """Test parse_json_with_recovery with extra text (RECOVERY CASE)."""
    print("\n[TEST 14] Parse with extra text before/after (should RECOVER)")
    
    json_str = '''
    Analysis summary:
    
    {"tldr": ["Point 1", "Point 2", "Point 3"], "sections": {"what_moved": [], "forward_watch": []}}
    
    End of summary.
    '''
    result, status = parse_json_with_recovery(json_str)
    
    assert result is not None, "Should recover JSON from text"
    assert "tldr" in result
    assert len(result["tldr"]) == 3
    print(f"  [PASS] Recovered JSON: {status}")


def test_parse_with_recovery_trailing_commas():
    """Test parse_json_with_recovery with trailing commas (REPAIR CASE)."""
    print("\n[TEST 15] Parse with trailing commas (should REPAIR)")
    
    json_str = '{"key": "value", "array": [1, 2, 3,],}'
    result, status = parse_json_with_recovery(json_str)
    
    assert result is not None, "Should repair and parse"
    assert "Repaired" in status or "trailing" in status.lower()
    assert result["key"] == "value"
    print(f"  [PASS] Repaired and parsed: {status}")


def test_parse_with_recovery_unterminated_string():
    """Test parse_json_with_recovery with unterminated string (FAILURE CASE)."""
    print("\n[TEST 16] Parse unterminated string (should FAIL cleanly)")
    
    json_str = '{"key": "value", "bad": "unterminated string'
    
    with tempfile.TemporaryDirectory() as tmpdir:
        debug_path = Path(tmpdir) / "debug.txt"
        pdf_path = Path(tmpdir) / "test.pdf"
        
        result, status = parse_json_with_recovery(
            json_str,
            pdf_path=pdf_path,
            debug_path=debug_path
        )
        
        # Should fail
        assert result is None, "Should not parse unterminated string"
        assert "exhausted" in status.lower() or "unterminated" in status.lower()
        
        # Should write debug artifact
        assert debug_path.exists(), "Debug artifact should be written"
        debug_content = debug_path.read_text(encoding='utf-8')
        assert "JSON PARSE FAILURE" in debug_content
        assert "unterminated" in debug_content.lower() or "exhausted" in debug_content.lower()
        
        print(f"  [PASS] Failed cleanly, debug artifact written")
        print(f"  Status: {status[:100]}...")


def test_parse_with_recovery_complex_real_world():
    """Test with realistic malformed LLM output."""
    print("\n[TEST 17] Complex real-world malformed output")
    
    # Simulate LLM adding commentary + trailing comma
    json_str = '''
    Here's the structured summary:
    
    {
        "tldr": [
            "Gold prices rose 2% on safe-haven demand",
            "Fed signals potential rate cuts in Q2",
            "Equity markets showed mixed performance"
        ],
        "sections": {
            "what_moved_today": ["Gold rallied to $2,150"],
            "what_can_move_tomorrow": [],
            "trade_ideas": [],
        },
        "meta": {
            "theme": "Risk-off sentiment drives gold higher",
        }
    }
    
    That's the analysis.
    '''
    
    result, status = parse_json_with_recovery(json_str)
    
    assert result is not None, "Should recover complex malformed output"
    assert "tldr" in result
    assert len(result["tldr"]) == 3
    assert "Gold prices rose" in result["tldr"][0]
    print(f"  [PASS] Complex recovery succeeded: {status}")


if __name__ == "__main__":
    tests = [
        test_extract_clean_json,
        test_extract_json_with_markdown_fences,
        test_extract_json_with_extra_text_before,
        test_extract_json_with_extra_text_after,
        test_extract_json_with_text_before_and_after,
        test_extract_unterminated_string,
        test_extract_no_json,
        test_repair_trailing_commas,
        test_repair_missing_closing_brace,
        test_repair_too_many_missing_braces,
        test_repair_unterminated_string,
        test_parse_with_recovery_clean_json,
        test_parse_with_recovery_markdown,
        test_parse_with_recovery_extra_text,
        test_parse_with_recovery_trailing_commas,
        test_parse_with_recovery_unterminated_string,
        test_parse_with_recovery_complex_real_world,
    ]
    
    passed = 0
    failed = 0
    
    print("=" * 70)
    print("ROBUST JSON PARSING TESTS")
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
        print("\nKey behaviors validated:")
        print("  1. Clean JSON uses fast path")
        print("  2. Extra text before/after JSON is recovered")
        print("  3. Trailing commas are repaired")
        print("  4. Simple missing braces are repaired")
        print("  5. Unterminated strings fail cleanly")
        print("  6. Debug artifacts written on failure")
        print("  7. Complex real-world cases handled")
    
    sys.exit(1 if failed else 0)
