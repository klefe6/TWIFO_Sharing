"""
Tests for JSON write failure behavior.
Purpose: Verify SummaryWriteFailedError is raised and render is skipped when JSON write fails.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from summarize_pdf import SummaryWriteFailedError, summarize_text


def test_summary_write_failed_error_raised_when_json_missing():
    """If _write_json doesn't actually write, SummaryWriteFailedError must be raised."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        
        # Mock _write_json to do nothing (simulate write failure)
        with patch("summarize_pdf._write_json", MagicMock()):
            # Also mock LLM call to avoid actual API call
            with patch("summarize_pdf._summarize_with_quality_retry") as mock_summarize:
                mock_summarize.return_value = {
                    "schema_version": "twifo.sum.v1",
                    "sections": {"tldr": ["Test"], "what_moved_today": [], "what_can_move_tomorrow": []},
                    "meta": {},
                    "extraction": {"status": "ok"},
                }
                
                with pytest.raises(SummaryWriteFailedError) as exc_info:
                    summarize_text(
                        text="Sample text for testing write failure behavior " * 50,
                        title="TestDoc",
                        provider="TEST",
                        published_date="20260212",
                        horizon="d",
                        out_dir=out_dir,
                    )
                
                assert "write_failed" in str(exc_info.value)
                assert "sum.json missing" in str(exc_info.value)


def test_render_not_called_when_write_fails():
    """Verify render_summary_pdf is NOT called when SummaryWriteFailedError is raised."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        render_mock = MagicMock()
        
        # Mock _write_json to do nothing (simulate write failure)
        with patch("summarize_pdf._write_json", MagicMock()):
            with patch("summarize_pdf._summarize_with_quality_retry") as mock_summarize:
                mock_summarize.return_value = {
                    "schema_version": "twifo.sum.v1",
                    "sections": {"tldr": ["Test"], "what_moved_today": [], "what_can_move_tomorrow": []},
                    "meta": {},
                    "extraction": {"status": "ok"},
                }
                
                # Simulate db_filter_autorun behavior: catch exception, never call render
                try:
                    summarize_text(
                        text="Sample text for testing " * 50,
                        title="TestDoc2",
                        provider="TEST",
                        published_date="20260212",
                        horizon="d",
                        out_dir=out_dir,
                    )
                    # If we get here, render would be called in normal flow
                    render_mock("path_to_json", "path_to_pdf")
                except SummaryWriteFailedError:
                    # Exception caught - render should NOT be called
                    pass
                
        # Assert render was never called
        render_mock.assert_not_called()


def test_successful_write_does_not_raise():
    """Normal write should NOT raise SummaryWriteFailedError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        
        # Mock LLM call but let _write_json work normally
        with patch("summarize_pdf._summarize_with_quality_retry") as mock_summarize:
            mock_summarize.return_value = {
                "schema_version": "twifo.sum.v1",
                "sections": {"tldr": ["Test"], "what_moved_today": [], "what_can_move_tomorrow": []},
                "meta": {},
                "extraction": {"status": "ok"},
            }
            
            # Should complete without raising
            result, json_path = summarize_text(
                text="Sample text for successful write test " * 50,
                title="TestDocSuccess",
                provider="TEST",
                published_date="20260212",
                horizon="d",
                out_dir=out_dir,
            )
            
            assert json_path.exists()
            assert result is not None


if __name__ == "__main__":
    # Run tests directly
    import sys
    
    print("Running test_summary_write_failed_error_raised_when_json_missing...")
    try:
        test_summary_write_failed_error_raised_when_json_missing()
        print("[PASS] test_summary_write_failed_error_raised_when_json_missing")
    except Exception as e:
        print(f"[FAIL] test_summary_write_failed_error_raised_when_json_missing: {e}")
        sys.exit(1)
    
    print("\nRunning test_render_not_called_when_write_fails...")
    try:
        test_render_not_called_when_write_fails()
        print("[PASS] test_render_not_called_when_write_fails")
    except Exception as e:
        print(f"[FAIL] test_render_not_called_when_write_fails: {e}")
        sys.exit(1)
    
    print("\nRunning test_successful_write_does_not_raise...")
    try:
        test_successful_write_does_not_raise()
        print("[PASS] test_successful_write_does_not_raise")
    except Exception as e:
        print(f"[FAIL] test_successful_write_does_not_raise: {e}")
        sys.exit(1)
    
    print("\n[OK] All write failure tests passed.")
