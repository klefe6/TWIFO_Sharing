"""
Tests for TWIFO Extraction Quality Metrics
Purpose: Verify extraction quality scoring and status determination
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

import pytest
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
    
    assert score >= 80  # High score for excellent extraction
    assert status == 'ok'


def test_quality_good():
    """Test good quality extraction (medium score)."""
    extraction_meta = {
        'pages_total': 8,
        'pages_with_text': 8,
        'chars_total': 7000,
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    assert 60 <= score < 80  # Medium score for good extraction
    assert status == 'ok'


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
    
    assert status == 'degraded'
    assert 'degradation_reasons' in extraction_meta
    assert any('low_char_count' in reason for reason in extraction_meta['degradation_reasons'])


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
    
    assert status == 'degraded'
    assert 'degradation_reasons' in extraction_meta
    assert any('low_page_coverage' in reason for reason in extraction_meta['degradation_reasons'])


def test_quality_degraded_ocr_penalty():
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
    
    score_no_ocr, status_no_ocr = compute_extraction_quality(meta_no_ocr)
    
    # With OCR
    meta_with_ocr = {
        'pages_total': 5,
        'pages_with_text': 5,
        'chars_total': 5000,
        'ocr_used': True,
        'errors': [],
        'method_used': 'ocr_pymupdf+tesseract'
    }
    
    score_with_ocr, status_with_ocr = compute_extraction_quality(meta_with_ocr)
    
    # OCR should have lower score
    assert score_with_ocr < score_no_ocr
    assert score_with_ocr == score_no_ocr - 20  # OCR penalty is 20 points


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
    
    assert status == 'failed'
    assert score <= 10  # Very low score for failed extraction


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
    
    assert status == 'failed'


def test_quality_failed_critical_error():
    """Test failed status for critical errors."""
    extraction_meta = {
        'pages_total': 5,
        'pages_with_text': 5,
        'chars_total': 5000,
        'ocr_used': False,
        'errors': ['PDF is corrupt and unreadable'],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    assert status == 'failed'


def test_quality_degraded_multiple_errors():
    """Test degraded status for multiple errors."""
    extraction_meta = {
        'pages_total': 10,
        'pages_with_text': 8,
        'chars_total': 5000,
        'ocr_used': False,
        'errors': ['warning: page 2 skipped', 'warning: page 5 incomplete'],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    assert status == 'degraded'
    assert 'degradation_reasons' in extraction_meta
    assert any('multiple_errors' in reason for reason in extraction_meta['degradation_reasons'])


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
    
    score, status = compute_extraction_quality(extraction_meta)
    assert 0 <= score <= 100
    
    # Test lower bound (with penalties)
    extraction_meta = {
        'pages_total': 10,
        'pages_with_text': 1,
        'chars_total': 100,
        'ocr_used': True,
        'errors': ['error1', 'error2', 'error3', 'error4'],
        'method_used': 'ocr_pymupdf+tesseract'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    assert 0 <= score <= 100


def test_quality_edge_case_no_pages():
    """Test extraction with no page count (edge case)."""
    extraction_meta = {
        'pages_total': 0,
        'pages_with_text': 0,
        'chars_total': 5000,  # Got text somehow
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score, status = compute_extraction_quality(extraction_meta)
    
    # Should give credit for getting text despite no page count
    assert score > 20
    assert status == 'ok'


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
    assert status1 == 'ok'
    
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
    assert status2 == 'degraded'
    
    # Exactly at page coverage threshold (40%)
    meta3 = {
        'pages_total': 10,
        'pages_with_text': 4,  # Exactly 40%
        'chars_total': 5000,
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score3, status3 = compute_extraction_quality(meta3)
    # At threshold should be ok
    assert status3 == 'ok'
    
    # Just below threshold (39%)
    meta4 = {
        'pages_total': 10,
        'pages_with_text': 3,  # 30% < 40%
        'chars_total': 5000,
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score4, status4 = compute_extraction_quality(meta4)
    assert status4 == 'degraded'


def test_quality_scoring_components():
    """Test individual scoring components."""
    # Perfect page coverage (40 points)
    meta = {
        'pages_total': 10,
        'pages_with_text': 10,
        'chars_total': 0,  # No char score
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score, _ = compute_extraction_quality(meta)
    # Should get page score but not char score
    assert 35 <= score <= 45  # ~40 from pages
    
    # Perfect char count (40 points)
    meta = {
        'pages_total': 0,
        'pages_with_text': 0,
        'chars_total': 15000,
        'ocr_used': False,
        'errors': [],
        'method_used': 'pypdf'
    }
    
    score, _ = compute_extraction_quality(meta)
    # Should get char score
    assert 55 <= score <= 65  # ~40 from chars + ~20 from no pages bonus


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
    assert status == 'failed'


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
        assert status == 'failed', f"Fatal keyword '{keyword}' should always cause 'failed' status"


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
    assert status == 'degraded'
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
    assert status == 'degraded'
    
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
    assert status == 'failed'


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
    assert status == 'failed'


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
    
    assert status == 'ok'
    assert score >= 70


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
