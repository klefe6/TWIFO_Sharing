"""
Simple test runner for extraction quality tests (no pytest dependency).
Run: python test_extraction_quality_benign_errors.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from summarize_pdf import compute_extraction_quality


def run_test(name, test_fn):
    """Run a single test and report result."""
    try:
        test_fn()
        print(f"  [PASS] {name}")
        return True
    except AssertionError as e:
        print(f"  [FAIL] {name}: {e}")
        return False
    except Exception as e:
        print(f"  [ERROR] {name}: {e}")
        return False


def test_benign_parser_warning_with_good_extraction():
    """Test that benign parser warnings (like 'invalid xref') don't cause 'failed' when extraction succeeded."""
    extraction_meta = {
        'pages_total': 50,
        'pages_with_text': 48,  # 96% coverage
        'chars_total': 30000,   # Substantial text
        'ocr_used': False,
        'errors': ['invalid xref table'],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    # Should be degraded (due to parser warning) but NOT failed
    assert status in ('ok', 'degraded'), f"Expected 'ok' or 'degraded', got '{status}'"
    assert status != 'failed', "Benign parser warning with good extraction should not be 'failed'"
    # Score should still be good
    assert score >= 50


def test_benign_parser_warning_with_poor_extraction():
    """Test that benign warnings ARE fatal when extraction actually failed."""
    extraction_meta = {
        'pages_total': 10,
        'pages_with_text': 1,  # Only 10% coverage
        'chars_total': 300,     # Low text
        'ocr_used': False,
        'errors': ['invalid stream object'],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    # Should be failed because extraction didn't succeed + benign error
    assert status == 'failed', f"Expected 'failed', got '{status}'"


def test_fatal_error_always_fails():
    """Test that truly fatal errors (corrupt, missing, unreadable) always cause 'failed'."""
    # Test each fatal keyword
    for keyword in ['missing', 'corrupt', 'unreadable']:
        extraction_meta = {
            'pages_total': 50,
            'pages_with_text': 50,
            'chars_total': 30000,  # Even with good text
            'ocr_used': False,
            'errors': [f'PDF is {keyword} and cannot be parsed'],
            'method_used': 'pypdf'
        }
        
        score, status = compute_extraction_quality(extraction_meta)
        assert status == 'failed', f"Fatal keyword '{keyword}' should always cause 'failed' status, got '{status}'"


def test_multiple_benign_warnings_with_good_extraction():
    """Test that multiple benign warnings with good extraction result in 'degraded' not 'failed'."""
    extraction_meta = {
        'pages_total': 25,
        'pages_with_text': 25,
        'chars_total': 20000,
        'ocr_used': False,
        'errors': ['invalid xref table', 'invalid stream length', 'invalid object reference'],
        'method_used': 'pdfplumber'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    # Multiple benign errors with good extraction -> degraded (not failed)
    assert status == 'degraded', f"Expected 'degraded', got '{status}'"
    assert 'degradation_reasons' in extraction_meta
    assert any('parser_warnings' in reason for reason in extraction_meta['degradation_reasons'])


def test_benign_warning_at_threshold():
    """Test benign warning exactly at the success threshold."""
    # Exactly at threshold: chars_total=1500, page_ratio=0.4
    extraction_meta = {
        'pages_total': 10,
        'pages_with_text': 4,  # Exactly 40%
        'chars_total': 1500,    # Exactly 1500
        'ocr_used': False,
        'errors': ['invalid xref entry'],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    # At threshold with benign error should be degraded (not failed)
    assert status == 'degraded', f"Expected 'degraded' at threshold, got '{status}'"
    
    # Just below threshold
    extraction_meta = {
        'pages_total': 10,
        'pages_with_text': 3,  # 30% < 40%
        'chars_total': 1499,    # < 1500
        'ocr_used': False,
        'errors': ['invalid xref entry'],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    # Below threshold with benign error should be failed
    assert status == 'failed', f"Expected 'failed' below threshold, got '{status}'"


def test_mixed_fatal_and_benign_errors():
    """Test that any fatal error causes 'failed' even with benign errors present."""
    extraction_meta = {
        'pages_total': 50,
        'pages_with_text': 50,
        'chars_total': 30000,
        'ocr_used': False,
        'errors': ['invalid xref table', 'PDF is corrupt', 'invalid stream'],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    # Should be failed due to 'corrupt' keyword
    assert status == 'failed', f"Expected 'failed' due to 'corrupt', got '{status}'"


def test_no_errors_good_extraction():
    """Test that good extraction with no errors is 'ok'."""
    extraction_meta = {
        'pages_total': 20,
        'pages_with_text': 20,
        'chars_total': 15000,
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    assert status == 'ok', f"Expected 'ok', got '{status}'"
    assert score >= 70, f"Expected score >= 70, got {score}"


def test_single_benign_warning_good_extraction():
    """Test single benign warning with excellent extraction."""
    extraction_meta = {
        'pages_total': 100,
        'pages_with_text': 100,
        'chars_total': 50000,
        'ocr_used': False,
        'errors': ['invalid xref offset at position 12345'],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    # Should be degraded (benign warning) but NOT failed
    assert status == 'degraded', f"Expected 'degraded', got '{status}'"
    assert score >= 60, f"Score should still be good (>= 60), got {score}"


def test_no_pages_but_good_text_with_benign_error():
    """Test edge case: no page count but substantial text + benign error."""
    extraction_meta = {
        'pages_total': 0,  # No page info
        'pages_with_text': 0,
        'chars_total': 25000,  # But got plenty of text
        'ocr_used': False,
        'errors': ['invalid object stream'],
        'method_used': 'pdfplumber'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    # With no page info, we check chars_total >= 1500 for success
    # This should be degraded (benign warning) not failed
    assert status == 'degraded', f"Expected 'degraded', got '{status}'"


if __name__ == '__main__':
    print("Running benign error handling tests...")
    print()
    
    tests = [
        ("benign_parser_warning_with_good_extraction", test_benign_parser_warning_with_good_extraction),
        ("benign_parser_warning_with_poor_extraction", test_benign_parser_warning_with_poor_extraction),
        ("fatal_error_always_fails", test_fatal_error_always_fails),
        ("multiple_benign_warnings_with_good_extraction", test_multiple_benign_warnings_with_good_extraction),
        ("benign_warning_at_threshold", test_benign_warning_at_threshold),
        ("mixed_fatal_and_benign_errors", test_mixed_fatal_and_benign_errors),
        ("no_errors_good_extraction", test_no_errors_good_extraction),
        ("single_benign_warning_good_extraction", test_single_benign_warning_good_extraction),
        ("no_pages_but_good_text_with_benign_error", test_no_pages_but_good_text_with_benign_error),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        if run_test(name, test_fn):
            passed += 1
        else:
            failed += 1
    
    print()
    print(f"Results: {passed} passed, {failed} failed out of {passed + failed}")
    sys.exit(0 if failed == 0 else 1)
