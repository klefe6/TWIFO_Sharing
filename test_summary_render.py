"""
Tests for summary_render: LOW CONFIDENCE banner message by meta.low_confidence_reason.
Purpose: Ensure banner text changes correctly for degraded_extraction, unverified_numerics, ocr_fallback, default.
"""

from summary_render import get_low_confidence_banner_message, LOW_CONFIDENCE_MESSAGES


def test_low_confidence_banner_degraded_extraction():
    """degraded_extraction → degraded extraction message."""
    msg = get_low_confidence_banner_message({"low_confidence_reason": "degraded_extraction"})
    assert "degraded text extraction" in msg
    assert msg == LOW_CONFIDENCE_MESSAGES["degraded_extraction"]


def test_low_confidence_banner_unverified_numerics():
    """unverified_numerics → numeric verification message."""
    msg = get_low_confidence_banner_message({"low_confidence_reason": "unverified_numerics"})
    assert "could not be verified" in msg
    assert msg == LOW_CONFIDENCE_MESSAGES["unverified_numerics"]


def test_low_confidence_banner_ocr_fallback():
    """ocr_fallback → OCR fallback message."""
    msg = get_low_confidence_banner_message({"low_confidence_reason": "ocr_fallback"})
    assert "OCR fallback" in msg
    assert msg == LOW_CONFIDENCE_MESSAGES["ocr_fallback"]


def test_low_confidence_banner_default():
    """Unknown or missing reason → generic low confidence message."""
    msg_empty = get_low_confidence_banner_message({})
    msg_unknown = get_low_confidence_banner_message({"low_confidence_reason": "insufficient_text_chars_500"})
    assert "low confidence" in msg_empty
    assert "low confidence" in msg_unknown
    assert "degraded text extraction" not in msg_empty
    assert msg_empty == msg_unknown


def test_low_confidence_banner_compound_reason():
    """Compound reason (e.g. degraded_extraction; unverified_numerics) uses first segment."""
    msg = get_low_confidence_banner_message({"low_confidence_reason": "degraded_extraction; unverified_numerics"})
    assert "degraded text extraction" in msg
