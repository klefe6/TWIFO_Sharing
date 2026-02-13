"""
Simple test runner for extraction quality (no pytest dependency)
Purpose: Verify extraction quality scoring and status determination
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

import sys
sys.path.insert(0, r'c:\Coding Projects\TWIFO_Sharing')

from summarize_pdf import compute_extraction_quality, determine_extraction_status


def test_quality_excellent():
    """Test excellent quality extraction (high score)."""
    extraction_meta = {
        'pages_total': 10,
        'pages_with_text': 10,
        'chars_total': 15000,
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    assert score >= 80, f"Expected score >= 80, got {score}"
    assert status == 'ok', f"Expected status 'ok', got '{status}'"
    print(f"[PASS] test_quality_excellent: score={score}, status={status}")


def test_quality_degraded_low_chars():
    """Test degraded extraction due to low character count."""
    extraction_meta = {
        'pages_total': 10,
        'pages_with_text': 10,
        'chars_total': 1200,  # < 1500 threshold
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    assert status == 'degraded', f"Expected status 'degraded', got '{status}'"
    assert 'degradation_reasons' in extraction_meta, "Missing degradation_reasons"
    assert any('low_char_count' in reason for reason in extraction_meta['degradation_reasons']), \
        "Expected 'low_char_count' in degradation_reasons"
    print(f"[PASS] test_quality_degraded_low_chars: score={score}, status={status}")


def test_quality_degraded_low_page_coverage():
    """Test degraded extraction due to low page coverage."""
    extraction_meta = {
        'pages_total': 10,
        'pages_with_text': 3,  # Only 30% coverage (< 40% threshold)
        'chars_total': 5000,
        'ocr_used': False,
        'errors': [],
        'method_used': 'pdfplumber'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    assert status == 'degraded', f"Expected status 'degraded', got '{status}'"
    assert 'degradation_reasons' in extraction_meta, "Missing degradation_reasons"
    assert any('low_page_coverage' in reason for reason in extraction_meta['degradation_reasons']), \
        "Expected 'low_page_coverage' in degradation_reasons"
    print(f"[PASS] test_quality_degraded_low_page_coverage: score={score}, status={status}")


def test_quality_ocr_penalty():
    """Test OCR usage applies penalty."""
    # Without OCR
    meta_no_ocr = {
        'pages_total': 5,
        'pages_with_text': 5,
        'chars_total': 5000,
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score_no_ocr, _ = compute_extraction_quality(meta_no_ocr)
    
    # With OCR
    meta_with_ocr = {
        'pages_total': 5,
        'pages_with_text': 5,
        'chars_total': 5000,
        'ocr_used': True,
        'errors': [],
        'method_used': 'ocr_pymupdf+tesseract'
    }
    
    score_with_ocr, _ = compute_extraction_quality(meta_with_ocr)
    
    assert score_with_ocr < score_no_ocr, f"OCR should lower score: {score_with_ocr} vs {score_no_ocr}"
    assert score_with_ocr == score_no_ocr - 20, f"OCR penalty should be 20 points"
    print(f"[PASS] test_quality_ocr_penalty: no_ocr={score_no_ocr}, with_ocr={score_with_ocr}")


def test_quality_failed_status():
    """Test failed extraction status."""
    extraction_meta = {
        'pages_total': 5,
        'pages_with_text': 0,
        'chars_total': 0,
        'ocr_used': False,
        'errors': ['pypdf failed', 'pdfplumber failed', 'pymupdf failed'],
        'method_used': 'failed'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    assert status == 'failed', f"Expected status 'failed', got '{status}'"
    assert score <= 10, f"Failed extraction should have score <= 10, got {score}"
    print(f"[PASS] test_quality_failed_status: score={score}, status={status}")


def test_quality_failed_insufficient_chars():
    """Test failed status for insufficient characters."""
    extraction_meta = {
        'pages_total': 5,
        'pages_with_text': 1,
        'chars_total': 50,  # < 100 chars
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    assert status == 'failed', f"Expected status 'failed', got '{status}'"
    print(f"[PASS] test_quality_failed_insufficient_chars: score={score}, status={status}")


def test_quality_score_clamping():
    """Test that quality score is clamped to 0-100."""
    # Test upper bound
    extraction_meta = {
        'pages_total': 10,
        'pages_with_text': 10,
        'chars_total': 50000,  # Excessive
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score, _ = compute_extraction_quality(extraction_meta)
    assert 0 <= score <= 100, f"Score should be 0-100, got {score}"
    
    # Test lower bound (with penalties)
    extraction_meta = {
        'pages_total': 10,
        'pages_with_text': 1,
        'chars_total': 100,
        'ocr_used': True,
        'errors': ['error1', 'error2', 'error3', 'error4'],
        'method_used': 'ocr_pymupdf+tesseract'
    }
    
    score, _ = compute_extraction_quality(extraction_meta)
    assert 0 <= score <= 100, f"Score should be 0-100, got {score}"
    print(f"[PASS] test_quality_score_clamping: scores within 0-100 range")


def test_determine_status_thresholds():
    """Test status determination at exact thresholds."""
    # Exactly at degraded threshold for chars (1500)
    meta1 = {
        'pages_total': 10,
        'pages_with_text': 10,
        'chars_total': 1500,
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score1, status1 = compute_extraction_quality(meta1)
    # At threshold should be ok
    assert status1 == 'ok', f"At threshold (1500 chars) should be 'ok', got '{status1}'"
    
    # Just below threshold (1499)
    meta2 = {
        'pages_total': 10,
        'pages_with_text': 10,
        'chars_total': 1499,
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score2, status2 = compute_extraction_quality(meta2)
    assert status2 == 'degraded', f"Below threshold (1499 chars) should be 'degraded', got '{status2}'"
    print(f"[PASS] test_determine_status_thresholds: threshold boundaries correct")


def test_chars_total_key_regression():
    """Regression: extraction_meta must use 'chars_total' (not 'total_chars').

    Bug: extract_text() wrote 'total_chars' but compute_extraction_quality()
    and determine_extraction_status() read 'chars_total'. Key mismatch made
    chars_total default to 0, so every PDF got status='failed'.
    """
    # Simulate the CORRECT metadata that extract_text now produces
    meta_correct = {
        'pages_total': 18,
        'pages_with_text': 18,
        'chars_total': 52844,  # The correct key
        'ocr_used': False,
        'errors': ['pypdf failed: parse error', 'pdfplumber failed: not installed'],
        'method_used': 'pymupdf',
    }
    score, status = compute_extraction_quality(meta_correct)
    assert status != 'failed', (
        f"52,844 chars across 18 pages must NOT be 'failed', got status={status!r} score={score}"
    )
    assert score >= 50, f"Expected score >= 50 for 52k chars, got {score}"

    # Simulate the OLD buggy metadata (total_chars instead of chars_total)
    # This must also not fail because we've fixed the source — but let's
    # prove the quality function reads the right key
    meta_old_key = {
        'pages_total': 18,
        'pages_with_text': 18,
        'total_chars': 52844,  # WRONG key (the old bug)
        'ocr_used': False,
        'errors': [],
        'method_used': 'pymupdf',
    }
    score2, status2 = compute_extraction_quality(meta_old_key)
    # With the wrong key, chars_total defaults to 0 → failed
    # This proves the key name matters
    assert status2 == 'failed', (
        f"Wrong key 'total_chars' should cause failed (chars defaults to 0), got {status2!r}"
    )
    print(f"[PASS] test_chars_total_key_regression: correct_key={status}({score}), wrong_key={status2}({score2})")


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        test_quality_excellent,
        test_quality_degraded_low_chars,
        test_quality_degraded_low_page_coverage,
        test_quality_ocr_penalty,
        test_quality_failed_status,
        test_quality_failed_insufficient_chars,
        test_quality_score_clamping,
        test_determine_status_thresholds,
        test_chars_total_key_regression,
    ]
    
    passed = 0
    failed = 0
    
    print("\n" + "="*60)
    print("Running Extraction Quality Tests")
    print("="*60 + "\n")
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
