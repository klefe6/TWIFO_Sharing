"""
Tests for the updated stub threshold logic — only stub if text is truly unusable.
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(__file__))


# ===========================================================================
# Mock helpers
# ===========================================================================

def _mock_path_manager():
    """Create a mock TWIFOPathManager."""
    pm = Mock()
    pm.originals_dir = Path("/tmp/originals")
    pm.artifacts_dir = Path("/tmp/artifacts")
    pm.get_artifact_dir = lambda x: Path("/tmp/artifacts/test")
    pm.get_extraction_path = lambda x: Path("/tmp/artifacts/test/extracted.txt")
    pm.get_extraction_json_path = lambda x: Path("/tmp/artifacts/test/extraction.json")
    return pm


# ===========================================================================
# Tests: Stub Threshold
# ===========================================================================

def test_stub_for_empty_text():
    """Empty text produces a stub (no summarization)."""
    from summarize_pdf import summarize_pdf
    
    with patch('summarize_pdf.extract_text') as mock_extract:
        mock_extract.return_value = (
            "",  # Empty text
            {
                "status": "ok",
                "method_used": "pypdf",
                "pages_total": 1,
                "pages_with_text": 0,
                "chars_total": 0,
                "ocr_used": False,
                "errors": [],
            }
        )
        
        with patch('summarize_pdf._write_json'), \
             patch('summarize_pdf._write_txt'), \
             patch('summarize_pdf.os.path.exists', return_value=True):
            
            test_pdf = Path("test.pdf")
            result, json_path = summarize_pdf(test_pdf, model="gpt-4o-mini", allow_ocr=False)
            
            # Should be a failed stub
            assert result["extraction"]["status"] in ("ok", "failed")
            assert result["sections"]["what_moved_today"] == []
            print("  [PASS] Empty text produces stub")


def test_stub_for_tiny_text():
    """Text < 100 chars produces a stub (no summarization)."""
    from summarize_pdf import summarize_pdf
    
    with patch('summarize_pdf.extract_text') as mock_extract:
        mock_extract.return_value = (
            "This is only fifty characters of extracted text.",  # 50 chars
            {
                "status": "ok",
                "method_used": "pypdf",
                "pages_total": 1,
                "pages_with_text": 1,
                "chars_total": 50,
                "ocr_used": False,
                "errors": [],
            }
        )
        
        with patch('summarize_pdf._write_json'), \
             patch('summarize_pdf._write_txt'), \
             patch('summarize_pdf.os.path.exists', return_value=True):
            
            test_pdf = Path("test.pdf")
            result, json_path = summarize_pdf(test_pdf, model="gpt-4o-mini", allow_ocr=False)
            
            # Should be a stub
            assert result["extraction"].get("reason") or result["sections"]["what_moved_today"] == []
            print("  [PASS] Text < 100 chars produces stub")


def test_summarize_with_low_text_above_threshold():
    """Text between 100-1500 chars produces a low-confidence summary (not a stub)."""
    from summarize_pdf import summarize_pdf
    
    # Create a 1000-char text with market-relevant content
    test_text = (
        "Federal Reserve minutes released today showing hawkish sentiment among members. "
        "ES futures declined 0.5% to 5,450 level on the news. Gold rallied to 2,050 on safe-haven flows. "
        "The 10-year Treasury yield climbed to 4.25% as traders repriced rate expectations. "
    ) * 5  # ~400 chars base text, repeat to get ~1000 chars
    
    with patch('summarize_pdf.extract_text') as mock_extract:
        mock_extract.return_value = (
            test_text[:1000],  # Exactly 1000 chars
            {
                "status": "ok",
                "method_used": "pypdf",
                "pages_total": 5,
                "pages_with_text": 3,
                "chars_total": 1000,
                "ocr_used": False,
                "errors": [],
            }
        )
        
        # Mock the LLM call to avoid actual API hit
        with patch('summarize_pdf.llm_summarize_to_json') as mock_llm:
            mock_llm.return_value = {
                "_meta": {"primary_entities": ["ES", "GC"]},
                "fingerprint_quotes": ["Fed showed hawkish sentiment", "ES declined to 5,450"],
                "numeric_claims": [{"value": "5,450", "context": "ES level", "source_quote": "ES...5,450"}],
                "what_moved_today": ["ES declined 0.5% to 5,450"],
                "what_can_move_tomorrow": ["Rate decision next week"],
                "trade_ideas": [],
                "tldr": ["Fed hawkish", "ES at 5,450", "Gold rallied"],
                "what_occurred": [],
                "forward_watch": [],
                "warnings": [],
                "tips_reminders": [],
                "cross_asset_impacts": [],
                "scenarios": [],
                "volatility_impact": {"expected_volatility": "Medium", "drivers": [], "directional_skew": "Two-sided", "confidence_0_100": 50},
                "sentiment_indicator": {"risk_on_off": "Neutral", "confidence_0_100": 50, "rationale": "Mixed"},
                "explain_like_refresher": "(none)",
                "score_0_10": 6,
                "chart_score_0_3": 0,
                "chart_text_sources_used": [],
                "chart_observations": [],
            }
            
            with patch('summarize_pdf._write_json'), \
                 patch('summarize_pdf._write_txt'), \
                 patch('summarize_pdf.os.path.exists', return_value=True):
                
                test_pdf = Path("test.pdf")
                result, json_path = summarize_pdf(test_pdf, model="gpt-4o-mini", allow_ocr=False)
                
                # Should NOT be a stub — should be a real summary
                assert "what_moved_today" in result["sections"]
                # Should have low_confidence flag
                assert result["meta"].get("low_confidence") is True
                assert "insufficient_text" in result["meta"].get("low_confidence_reason", "")
                print(f"  [PASS] 1000 chars produces low-confidence summary (not stub)")
                print(f"         low_confidence_reason={result['meta'].get('low_confidence_reason')}")


def test_summarize_with_failed_status_but_has_text():
    """extraction_status='failed' but text >= 100 chars produces low-confidence summary."""
    from summarize_pdf import summarize_pdf
    
    test_text = "ES futures declined. Gold rallied. Fed hawkish." * 10  # ~500 chars
    
    with patch('summarize_pdf.extract_text') as mock_extract:
        mock_extract.return_value = (
            test_text,
            {
                "status": "failed",  # Status says failed
                "method_used": "failed",
                "pages_total": 5,
                "pages_with_text": 1,
                "chars_total": len(test_text),
                "ocr_used": False,
                "errors": ["pypdf failed", "pdfplumber failed"],
            }
        )
        
        with patch('summarize_pdf.llm_summarize_to_json') as mock_llm:
            mock_llm.return_value = {
                "_meta": {"primary_entities": ["ES"]},
                "fingerprint_quotes": ["ES futures declined"],
                "numeric_claims": [],
                "what_moved_today": ["ES declined"],
                "what_can_move_tomorrow": [],
                "trade_ideas": [],
                "tldr": ["ES down", "Gold up", "Fed hawkish"],
                "what_occurred": [],
                "forward_watch": [],
                "warnings": [],
                "tips_reminders": [],
                "cross_asset_impacts": [],
                "scenarios": [],
                "volatility_impact": {"expected_volatility": "Medium", "drivers": [], "directional_skew": "Two-sided", "confidence_0_100": 50},
                "sentiment_indicator": {"risk_on_off": "Neutral", "confidence_0_100": 50, "rationale": "Mixed"},
                "explain_like_refresher": "(none)",
                "score_0_10": 5,
                "chart_score_0_3": 0,
                "chart_text_sources_used": [],
                "chart_observations": [],
            }
            
            with patch('summarize_pdf._write_json'), \
                 patch('summarize_pdf._write_txt'), \
                 patch('summarize_pdf.os.path.exists', return_value=True):
                
                test_pdf = Path("test.pdf")
                result, json_path = summarize_pdf(test_pdf, model="gpt-4o-mini", allow_ocr=False)
                
                # Should have real summary content
                assert len(result["sections"]["tldr"]) > 0
                # Should have low_confidence flag
                assert result["meta"].get("low_confidence") is True
                assert "failed_extraction" in result["meta"].get("low_confidence_reason", "")
                print(f"  [PASS] Failed status + text produces low-confidence summary")


def test_normal_extraction_no_low_confidence():
    """Normal extraction (>= MIN_TEXT_CHARS) does not set low_confidence."""
    from summarize_pdf import summarize_pdf
    
    test_text = "ES futures analysis. " * 100  # ~2000 chars
    
    with patch('summarize_pdf.extract_text') as mock_extract:
        mock_extract.return_value = (
            test_text,
            {
                "status": "ok",
                "method_used": "pypdf",
                "pages_total": 10,
                "pages_with_text": 10,
                "chars_total": len(test_text),
                "ocr_used": False,
                "errors": [],
            }
        )
        
        with patch('summarize_pdf.llm_summarize_to_json') as mock_llm:
            mock_llm.return_value = {
                "_meta": {"primary_entities": ["ES"]},
                "fingerprint_quotes": ["ES futures analysis"],
                "numeric_claims": [],
                "what_moved_today": ["ES moved"],
                "what_can_move_tomorrow": [],
                "trade_ideas": [],
                "tldr": ["ES analysis", "Good data", "Clear outlook"],
                "what_occurred": [],
                "forward_watch": [],
                "warnings": [],
                "tips_reminders": [],
                "cross_asset_impacts": [],
                "scenarios": [],
                "volatility_impact": {"expected_volatility": "Medium", "drivers": [], "directional_skew": "Two-sided", "confidence_0_100": 50},
                "sentiment_indicator": {"risk_on_off": "Neutral", "confidence_0_100": 50, "rationale": "Mixed"},
                "explain_like_refresher": "(none)",
                "score_0_10": 7,
                "chart_score_0_3": 0,
                "chart_text_sources_used": [],
                "chart_observations": [],
            }
            
            with patch('summarize_pdf._write_json'), \
                 patch('summarize_pdf._write_txt'), \
                 patch('summarize_pdf.os.path.exists', return_value=True):
                
                test_pdf = Path("test.pdf")
                result, json_path = summarize_pdf(test_pdf, model="gpt-4o-mini", allow_ocr=False)
                
                # Should NOT have low_confidence from text length
                # (may have it from other reasons, but not from insufficient_text)
                reason = result["meta"].get("low_confidence_reason", "")
                assert "insufficient_text" not in reason
                print("  [PASS] Normal extraction does not set low_confidence for text length")


def test_stub_threshold_exactly_at_100():
    """Text at exactly 100 chars is at the boundary."""
    from summarize_pdf import summarize_pdf
    
    test_text = "A" * 100  # Exactly 100 chars
    
    with patch('summarize_pdf.extract_text') as mock_extract:
        mock_extract.return_value = (
            test_text,
            {
                "status": "ok",
                "method_used": "pypdf",
                "pages_total": 1,
                "pages_with_text": 1,
                "chars_total": 100,
                "ocr_used": False,
                "errors": [],
            }
        )
        
        with patch('summarize_pdf.llm_summarize_to_json') as mock_llm:
            mock_llm.return_value = {
                "_meta": {"primary_entities": []},
                "fingerprint_quotes": ["test"],
                "numeric_claims": [],
                "what_moved_today": ["test"],
                "what_can_move_tomorrow": [],
                "trade_ideas": [],
                "tldr": ["a", "b", "c"],
                "what_occurred": [],
                "forward_watch": [],
                "warnings": [],
                "tips_reminders": [],
                "cross_asset_impacts": [],
                "scenarios": [],
                "volatility_impact": {"expected_volatility": "Medium", "drivers": [], "directional_skew": "Two-sided", "confidence_0_100": 50},
                "sentiment_indicator": {"risk_on_off": "Neutral", "confidence_0_100": 50, "rationale": "Mixed"},
                "explain_like_refresher": "(none)",
                "score_0_10": 5,
                "chart_score_0_3": 0,
                "chart_text_sources_used": [],
                "chart_observations": [],
            }
            
            with patch('summarize_pdf._write_json'), \
                 patch('summarize_pdf._write_txt'), \
                 patch('summarize_pdf.os.path.exists', return_value=True):
                
                test_pdf = Path("test.pdf")
                result, json_path = summarize_pdf(test_pdf, model="gpt-4o-mini", allow_ocr=False)
                
                # >= 100 chars should allow summarization (with low_confidence)
                assert result["meta"].get("low_confidence") is True
                assert len(result["sections"]["tldr"]) > 0
                print("  [PASS] Text at exactly 100 chars produces low-confidence summary")


def test_stub_for_99_chars():
    """Text at 99 chars (below threshold) produces stub."""
    from summarize_pdf import summarize_pdf
    
    test_text = "A" * 99
    
    with patch('summarize_pdf.extract_text') as mock_extract:
        mock_extract.return_value = (
            test_text,
            {
                "status": "ok",
                "method_used": "pypdf",
                "pages_total": 1,
                "pages_with_text": 1,
                "chars_total": 99,
                "ocr_used": False,
                "errors": [],
            }
        )
        
        with patch('summarize_pdf._write_json'), \
             patch('summarize_pdf._write_txt'), \
             patch('summarize_pdf.os.path.exists', return_value=True):
            
            test_pdf = Path("test.pdf")
            result, json_path = summarize_pdf(test_pdf, model="gpt-4o-mini", allow_ocr=False)
            
            # < 100 chars should be a stub
            assert result["sections"]["what_moved_today"] == []
            reason = result["extraction"].get("reason", "")
            assert "no usable text" in reason.lower()
            print("  [PASS] Text < 100 chars produces stub")


def test_degraded_extraction_still_summarizes():
    """extraction_status='degraded' with good text does not create a stub."""
    from summarize_pdf import summarize_pdf
    
    test_text = "Market analysis content. " * 80  # ~2000 chars
    
    with patch('summarize_pdf.extract_text') as mock_extract:
        mock_extract.return_value = (
            test_text,
            {
                "status": "degraded",
                "method_used": "pypdf",
                "pages_total": 10,
                "pages_with_text": 3,  # Low coverage -> degraded
                "chars_total": len(test_text),
                "ocr_used": False,
                "errors": ["invalid xref"],
                "degradation_reasons": ["low_page_coverage (30.0%)"],
            }
        )
        
        with patch('summarize_pdf.llm_summarize_to_json') as mock_llm:
            mock_llm.return_value = {
                "_meta": {"primary_entities": []},
                "fingerprint_quotes": ["Market analysis"],
                "numeric_claims": [],
                "what_moved_today": ["Markets moved"],
                "what_can_move_tomorrow": [],
                "trade_ideas": [],
                "tldr": ["a", "b", "c"],
                "what_occurred": [],
                "forward_watch": [],
                "warnings": [],
                "tips_reminders": [],
                "cross_asset_impacts": [],
                "scenarios": [],
                "volatility_impact": {"expected_volatility": "Medium", "drivers": [], "directional_skew": "Two-sided", "confidence_0_100": 50},
                "sentiment_indicator": {"risk_on_off": "Neutral", "confidence_0_100": 50, "rationale": "Mixed"},
                "explain_like_refresher": "(none)",
                "score_0_10": 6,
                "chart_score_0_3": 0,
                "chart_text_sources_used": [],
                "chart_observations": [],
            }
            
            with patch('summarize_pdf._write_json'), \
                 patch('summarize_pdf._write_txt'), \
                 patch('summarize_pdf.os.path.exists', return_value=True):
                
                test_pdf = Path("test.pdf")
                result, json_path = summarize_pdf(test_pdf, model="gpt-4o-mini", allow_ocr=False)
                
                # Key check: should NOT be a stub (check for stub marker)
                # Stubs have empty sections and a failure reason in extraction
                stub_reason = result["extraction"].get("reason", "")
                is_stub = ("no usable text" in stub_reason.lower() or 
                          "insufficient text" in stub_reason.lower())
                
                assert not is_stub, f"Expected summary, got stub with reason: {stub_reason}"
                # Should have low_confidence from degraded extraction
                assert result["meta"].get("low_confidence") is True
                print("  [PASS] Degraded extraction still produces summary (not stub)")



# ===========================================================================
# Runner
# ===========================================================================

def _run_all():
    """Simple test runner."""
    tests = [
        ("stub_for_empty_text", test_stub_for_empty_text),
        ("stub_for_tiny_text", test_stub_for_tiny_text),
        ("summarize_with_low_text_above_threshold", test_summarize_with_low_text_above_threshold),
        ("stub_for_99_chars", test_stub_for_99_chars),
        ("degraded_extraction_still_summarizes", test_degraded_extraction_still_summarizes),
    ]
    
    print("Running stub threshold tests...\n")
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1
    
    print(f"\nResults: {passed} passed, {failed} failed out of {passed + failed}")
    return failed == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
