"""
Unit tests for --no-dedupe flag in db_filter_autorun.py

Purpose: Verify that --no-dedupe bypasses all duplicate/claim checks
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path
import datetime as dt
from unittest.mock import Mock, patch, MagicMock, call

# Add TWIFO_Sharing to path
sys.path.insert(0, r"c:\Coding Projects\TWIFO_Sharing")

# Import the functions we need to test
from db_filter_autorun import process_pairs, safe_copy_atomic

# Test counters
passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    """Check helper for test assertions."""
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        msg = f"  [FAIL] {name}"
        if detail:
            msg += f" -- {detail}"
        print(msg)


def test_no_dedupe_bypasses_preflight_check():
    """When no_dedupe=True, preflight_check should not be called."""
    print("\n--- test_no_dedupe_bypasses_preflight_check ---")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        export_dir = tmpdir / "export"
        export_dir.mkdir()
        
        # Create a dummy source PDF
        src_pdf = tmpdir / "source.pdf"
        src_pdf.write_text("dummy pdf content")
        
        dst_pdf = export_dir / "BOA_Test_20260212_u.pdf"
        pairs = [(src_pdf, dst_pdf)]
        
        # Mock all the imports and functions
        with patch('db_filter_autorun.DEDUPE_AVAILABLE', True), \
             patch('db_filter_autorun.SUMMARIZE_AVAILABLE', False), \
             patch('db_filter_autorun.PATH_MANAGER_AVAILABLE', False), \
             patch('db_filter_autorun.PATH_MANAGER', None), \
             patch('db_filter_autorun.canonicalize_url') as mock_canon, \
             patch('db_filter_autorun.doc_id_from_canonical_url') as mock_docid, \
             patch('db_filter_autorun.slugify_title') as mock_slug, \
             patch('db_filter_autorun.deterministic_base_filename') as mock_base, \
             patch('db_filter_autorun.preflight_check') as mock_preflight, \
             patch('db_filter_autorun.claim_acquire') as mock_claim, \
             patch('db_filter_autorun.ensure_original_pdf_in_export') as mock_ensure:
            
            # Setup mocks
            mock_canon.return_value = "file://test"
            mock_docid.return_value = "test_doc_id"
            mock_slug.return_value = "test-slug"
            mock_base.return_value = "BOA_Test_20260212_u_test123"
            mock_ensure.return_value = (dst_pdf, None)
            
            # Test with no_dedupe=True
            copied, skipped, summary_skipped = process_pairs(
                export_dir, pairs, dt.date(2026, 2, 12), no_dedupe=True
            )
            
            # Verify preflight_check was NOT called
            check("preflight_check not called with no_dedupe", 
                  mock_preflight.call_count == 0,
                  f"preflight_check called {mock_preflight.call_count} times")
            
            # Verify claim_acquire was NOT called
            check("claim_acquire not called with no_dedupe",
                  mock_claim.call_count == 0,
                  f"claim_acquire called {mock_claim.call_count} times")
            
            # Verify file was processed (copied > 0)
            check("file was processed", copied > 0, f"copied={copied}")


def test_dedupe_enabled_calls_preflight():
    """When no_dedupe=False (default), preflight_check should be called."""
    print("\n--- test_dedupe_enabled_calls_preflight ---")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        export_dir = tmpdir / "export"
        export_dir.mkdir()
        
        src_pdf = tmpdir / "source.pdf"
        src_pdf.write_text("dummy pdf content")
        
        dst_pdf = export_dir / "BOA_Test_20260212_u.pdf"
        pairs = [(src_pdf, dst_pdf)]
        
        with patch('db_filter_autorun.DEDUPE_AVAILABLE', True), \
             patch('db_filter_autorun.SUMMARIZE_AVAILABLE', False), \
             patch('db_filter_autorun.PATH_MANAGER_AVAILABLE', False), \
             patch('db_filter_autorun.PATH_MANAGER', None), \
             patch('db_filter_autorun.canonicalize_url') as mock_canon, \
             patch('db_filter_autorun.doc_id_from_canonical_url') as mock_docid, \
             patch('db_filter_autorun.slugify_title') as mock_slug, \
             patch('db_filter_autorun.deterministic_base_filename') as mock_base, \
             patch('db_filter_autorun.preflight_check') as mock_preflight, \
             patch('db_filter_autorun.claim_acquire') as mock_claim, \
             patch('db_filter_autorun.doc_insert_pending') as mock_insert, \
             patch('db_filter_autorun.ensure_original_pdf_in_export') as mock_ensure, \
             patch('db_filter_autorun.bundle_complete') as mock_bundle:
            
            mock_canon.return_value = "file://test"
            mock_docid.return_value = "test_doc_id"
            mock_slug.return_value = "test-slug"
            mock_base.return_value = "BOA_Test_20260212_u_test123"
            mock_preflight.return_value = (False, "no_skip")  # Don't skip
            mock_claim.return_value = (True, "claim_handle")  # Acquired
            mock_ensure.return_value = (dst_pdf, None)
            mock_bundle.return_value = False  # Bundle incomplete
            
            # Test with no_dedupe=False (default behavior)
            copied, skipped, summary_skipped = process_pairs(
                export_dir, pairs, dt.date(2026, 2, 12), no_dedupe=False
            )
            
            # Verify preflight_check WAS called
            check("preflight_check called without no_dedupe",
                  mock_preflight.call_count > 0,
                  f"preflight_check called {mock_preflight.call_count} times")
            
            # Verify claim_acquire WAS called
            check("claim_acquire called without no_dedupe",
                  mock_claim.call_count > 0,
                  f"claim_acquire called {mock_claim.call_count} times")


def test_no_dedupe_forces_regeneration():
    """When no_dedupe=True, summaries should be regenerated even if they exist."""
    print("\n--- test_no_dedupe_forces_regeneration ---")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        export_dir = tmpdir / "export"
        export_dir.mkdir()
        
        src_pdf = tmpdir / "source.pdf"
        src_pdf.write_bytes(b"exact pdf content")
        
        # Use legacy layout (no PATH_MANAGER)
        dst_pdf = export_dir / "BOA_Test_20260212_u.pdf"
        
        # Pre-copy dst to make it a duplicate
        shutil.copy2(src_pdf, dst_pdf)
        
        # Pre-create summary files to simulate existing summaries
        summary_json = export_dir / "BOA_Test_20260212_u__sum.json"
        summary_pdf = export_dir / "BOA_Test_20260212_u__sum.pdf"
        summary_json.write_text('{"meta": {}}')
        summary_pdf.write_text('dummy summary pdf')
        
        pairs = [(src_pdf, dst_pdf)]
        
        # Mock without DEDUPE (legacy path)
        with patch('db_filter_autorun.DEDUPE_AVAILABLE', False), \
             patch('db_filter_autorun.SUMMARIZE_AVAILABLE', False), \
             patch('db_filter_autorun.PATH_MANAGER_AVAILABLE', False), \
             patch('db_filter_autorun.PATH_MANAGER', None):
            
            # Test with no_dedupe=False: should skip (duplicate + summaries exist)
            copied1, skipped1, summary_skipped1 = process_pairs(
                export_dir, pairs, dt.date(2026, 2, 12), no_dedupe=False
            )
            
            # Duplicate exists with summaries -> should skip completely
            check("without no_dedupe, existing duplicate+summaries cause skip",
                  skipped1 > 0 and copied1 == 0,
                  f"copied={copied1}, skipped={skipped1}")
            
            # Test with no_dedupe=True: should NOT skip even though summaries exist
            # The function will copy the file and summaries_exist will be forced to False
            copied2, skipped2, summary_skipped2 = process_pairs(
                export_dir, pairs, dt.date(2026, 2, 12), no_dedupe=True
            )
            
            # With no_dedupe, file should be copied (not skipped as duplicate)
            check("with no_dedupe, file is copied even if duplicate exists",
                  copied2 > 0,
                  f"copied={copied2}")


def test_legacy_duplicate_check_bypassed():
    """Legacy mode (no DEDUPE_AVAILABLE): no_dedupe should bypass MD5 duplicate check."""
    print("\n--- test_legacy_duplicate_check_bypassed ---")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        export_dir = tmpdir / "export"
        export_dir.mkdir()
        
        src_pdf = tmpdir / "source.pdf"
        src_pdf.write_bytes(b"exact pdf content 12345")
        
        dst_pdf = export_dir / "BOA_Test_20260212_u.pdf"
        
        # Pre-copy the file (making it a "duplicate")
        shutil.copy2(src_pdf, dst_pdf)
        
        pairs = [(src_pdf, dst_pdf)]
        
        with patch('db_filter_autorun.DEDUPE_AVAILABLE', False), \
             patch('db_filter_autorun.SUMMARIZE_AVAILABLE', False), \
             patch('db_filter_autorun.PATH_MANAGER_AVAILABLE', False), \
             patch('db_filter_autorun.PATH_MANAGER', None):
            
            # Test without no_dedupe: should detect duplicate and skip
            copied1, skipped1, summary_skipped1 = process_pairs(
                export_dir, pairs, dt.date(2026, 2, 12), no_dedupe=False
            )
            
            check("legacy: duplicate detected, file skipped",
                  skipped1 > 0,
                  f"skipped={skipped1}")
            
            # Test with no_dedupe: should NOT skip (bypass duplicate check)
            copied2, skipped2, summary_skipped2 = process_pairs(
                export_dir, pairs, dt.date(2026, 2, 12), no_dedupe=True
            )
            
            check("legacy: no_dedupe bypasses duplicate check, file copied",
                  copied2 > 0,
                  f"copied={copied2}, skipped={skipped2}")


def test_safe_copy_atomic():
    """Verify safe_copy_atomic works correctly (used for overwrites)."""
    print("\n--- test_safe_copy_atomic ---")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        src = tmpdir / "source.txt"
        dst = tmpdir / "dest.txt"
        
        src.write_text("test content v1")
        
        # First copy
        result1 = safe_copy_atomic(src, dst)
        check("first atomic copy succeeds", result1)
        check("destination file exists", dst.exists())
        check("destination content matches", dst.read_text() == "test content v1")
        
        # Overwrite with new content
        src.write_text("test content v2")
        result2 = safe_copy_atomic(src, dst)
        check("atomic overwrite succeeds", result2)
        check("destination content updated", dst.read_text() == "test content v2")


# ── Run All ──

def run_all():
    global passed, failed
    passed = 0
    failed = 0

    print("=" * 70)
    print("Unit Tests: --no-dedupe Flag in db_filter_autorun.py")
    print("=" * 70)

    test_no_dedupe_bypasses_preflight_check()
    test_dedupe_enabled_calls_preflight()
    test_no_dedupe_forces_regeneration()
    test_legacy_duplicate_check_bypassed()
    test_safe_copy_atomic()

    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
