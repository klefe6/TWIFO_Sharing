"""
Test extraction validation and fail-closed gating.

Purpose: Verify that validate_extraction() correctly blocks summarization when extraction fails
Author: Kevin Lefebvre
Last Updated: 2026-01-10
"""

import sys
from pathlib import Path

# Add parent directory to path to import summarize_pdf
sys.path.insert(0, str(Path(__file__).parent))

from summarize_pdf import validate_extraction


def test_validation_failure_scenarios():
    """Test validation function with various failure scenarios."""
    
    print("=" * 80)
    print("Testing validate_extraction() - Failure Scenarios")
    print("=" * 80)
    
    # Test Case 1: total_chars too low
    print("\n[TEST 1] total_chars below threshold (9 chars)")
    meta1 = {
        "total_chars": 9,
        "pages_with_text": 0,
        "extraction_quality_0_100": 0,
        "needs_ocr": False,
        "ocr_success": None
    }
    is_valid, reason = validate_extraction(meta1)
    assert not is_valid, "Should fail validation (total_chars too low)"
    assert "Total chars" in reason, f"Reason should mention total_chars: {reason}"
    print(f"  [PASS] Validation correctly blocked (reason: {reason})")
    
    # Test Case 2: pages_with_text = 0
    print("\n[TEST 2] pages_with_text = 0")
    meta2 = {
        "total_chars": 5000,
        "pages_with_text": 0,
        "extraction_quality_0_100": 0,
        "needs_ocr": False,
        "ocr_success": None
    }
    is_valid, reason = validate_extraction(meta2)
    assert not is_valid, "Should fail validation (no pages with text)"
    assert "Pages with text" in reason, f"Reason should mention pages_with_text: {reason}"
    print(f"  [PASS] Validation correctly blocked (reason: {reason})")
    
    # Test Case 3: extraction_quality too low
    print("\n[TEST 3] extraction_quality below threshold (30/100)")
    meta3 = {
        "total_chars": 5000,
        "pages_with_text": 5,
        "extraction_quality_0_100": 30,
        "needs_ocr": False,
        "ocr_success": None
    }
    is_valid, reason = validate_extraction(meta3)
    assert not is_valid, "Should fail validation (quality too low)"
    assert "Extraction quality" in reason, f"Reason should mention quality: {reason}"
    print(f"  [PASS] Validation correctly blocked (reason: {reason})")
    
    # Test Case 4: OCR needed but failed
    print("\n[TEST 4] OCR needed but ocr_success = False")
    meta4 = {
        "total_chars": 5000,
        "pages_with_text": 5,
        "extraction_quality_0_100": 50,
        "needs_ocr": True,
        "ocr_success": False
    }
    is_valid, reason = validate_extraction(meta4)
    assert not is_valid, "Should fail validation (OCR needed but failed)"
    assert "OCR" in reason, f"Reason should mention OCR: {reason}"
    print(f"  [PASS] Validation correctly blocked (reason: {reason})")
    
    # Test Case 5: OCR needed but status unknown
    print("\n[TEST 5] OCR needed but ocr_success = None")
    meta5 = {
        "total_chars": 5000,
        "pages_with_text": 5,
        "extraction_quality_0_100": 50,
        "needs_ocr": True,
        "ocr_success": None
    }
    is_valid, reason = validate_extraction(meta5)
    assert not is_valid, "Should fail validation (OCR status unknown)"
    assert "OCR" in reason or "unknown" in reason.lower(), f"Reason should mention OCR/unknown: {reason}"
    print(f"  [PASS] Validation correctly blocked (reason: {reason})")
    
    # Test Case 6: Successful validation (all thresholds met)
    print("\n[TEST 6] Successful validation - all thresholds met")
    meta6 = {
        "total_chars": 5000,
        "pages_with_text": 5,
        "extraction_quality_0_100": 60,
        "needs_ocr": False,
        "ocr_success": None
    }
    is_valid, reason = validate_extraction(meta6)
    assert is_valid, "Should pass validation"
    assert reason is None, f"Reason should be None when valid: {reason}"
    print(f"  [PASS] Validation correctly passed")
    
    # Test Case 7: Successful validation with OCR
    print("\n[TEST 7] Successful validation with OCR")
    meta7 = {
        "total_chars": 5000,
        "pages_with_text": 5,
        "extraction_quality_0_100": 60,
        "needs_ocr": True,
        "ocr_success": True
    }
    is_valid, reason = validate_extraction(meta7)
    assert is_valid, "Should pass validation (OCR succeeded)"
    assert reason is None, f"Reason should be None when valid: {reason}"
    print(f"  [PASS] Validation correctly passed with OCR")
    
    # Test Case 8: Simulate the failing PDF scenario (total_chars=9, ocr_success=False)
    print("\n[TEST 8] Simulate failing PDF scenario (DB_Gold example)")
    meta8 = {
        "total_chars": 9,
        "pages_with_text": 0,
        "extraction_quality_0_100": 0,
        "needs_ocr": True,
        "ocr_success": False
    }
    is_valid, reason = validate_extraction(meta8)
    assert not is_valid, "Should fail validation (simulating failed PDF)"
    print(f"  [PASS] Validation correctly blocked failed PDF scenario")
    print(f"     Reason: {reason}")
    
    print("\n" + "=" * 80)
    print("ALL TESTS PASSED")
    print("=" * 80)


if __name__ == "__main__":
    test_validation_failure_scenarios()

