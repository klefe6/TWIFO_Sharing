"""
Test: ensure_original_pdf_in_export writes to originals/ when path_manager enabled.

Verifies that the original PDF is ALWAYS written to path_manager.originals_dir
and NOT to the export root when path_manager is provided.

Purpose: Regression test for path_manager routing correctness
Author: Kevin Lefebvre
Last Updated: 2026-02-12

Run:
    python test_ensure_original_in_originals.py
    python -m pytest test_ensure_original_in_originals.py -v
"""

import tempfile
from pathlib import Path
import pytest

from ingest_dedup import ensure_original_pdf_in_export
from path_manager import TWIFOPathManager


def _create_sample_pdf(path: Path, content: bytes = None) -> None:
    """Create a minimal valid PDF for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if content is None:
        content = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
            b"xref\n0 4\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
        )
    path.write_bytes(content)


def test_original_pdf_written_to_originals_folder():
    """
    CORE REQUIREMENT: Original PDF must be written to originals/ when path_manager enabled.
    Must NOT appear in export root.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "export"
        export_dir.mkdir()
        
        # Enable path_manager
        pm = TWIFOPathManager(export_dir)
        
        # Create source PDF
        src = Path(tmpdir) / "source" / "test_report.pdf"
        _create_sample_pdf(src, b"%PDF-test-content-123")
        
        # Deterministic base name (as used by dedupe pipeline)
        base_name = "20260212__BOA__quarterly_report__abc1234567"
        
        # Call ensure_original_pdf_in_export with path_manager
        final_path, already_existed = ensure_original_pdf_in_export(
            export_dir, base_name, src, path_manager=pm
        )
        
        # ASSERTIONS
        assert final_path is not None, "Copy should succeed"
        assert not already_existed, "Should be a fresh copy"
        
        # 1. PDF MUST exist in originals/
        expected_originals_path = pm.originals_dir / f"{base_name}.pdf"
        assert final_path == expected_originals_path, (
            f"Expected path={expected_originals_path}, got {final_path}"
        )
        assert final_path.exists(), f"PDF must exist at {final_path}"
        assert final_path.parent == pm.originals_dir, (
            f"PDF parent must be originals_dir={pm.originals_dir}, got {final_path.parent}"
        )
        
        # 2. PDF MUST NOT exist in export root
        export_root_path = export_dir / f"{base_name}.pdf"
        assert not export_root_path.exists(), (
            f"PDF MUST NOT exist in export root: {export_root_path}"
        )
        
        # 3. Content integrity check
        assert final_path.read_bytes() == b"%PDF-test-content-123", (
            "PDF content should match source"
        )
        
        # 4. File size check
        assert final_path.stat().st_size > 0, "PDF should not be empty"


def test_original_pdf_multiple_calls_deterministic():
    """
    Test that multiple calls with same base_name are deterministic.
    No (1), (2) suffixes should be created.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "export"
        export_dir.mkdir()
        pm = TWIFOPathManager(export_dir)
        
        src = Path(tmpdir) / "source" / "report.pdf"
        _create_sample_pdf(src)
        
        base_name = "20260212__JPM__analysis__xyz789"
        
        # First call
        final1, already1 = ensure_original_pdf_in_export(
            export_dir, base_name, src, path_manager=pm
        )
        assert final1 is not None
        assert not already1
        
        # Second call with same base_name (should detect existing)
        final2, already2 = ensure_original_pdf_in_export(
            export_dir, base_name, src, path_manager=pm
        )
        assert final2 is not None
        assert already2, "Second call should detect existing file"
        
        # Paths should be identical
        assert final1 == final2
        
        # Only ONE file should exist (no duplicates with (1) suffix)
        originals_files = list(pm.originals_dir.glob(f"{base_name}*.pdf"))
        assert len(originals_files) == 1, (
            f"Expected 1 file in originals/, found {len(originals_files)}: {originals_files}"
        )


def test_legacy_mode_without_path_manager():
    """
    Control test: without path_manager, PDF should go to export root (legacy behavior).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "export"
        export_dir.mkdir()
        
        src = Path(tmpdir) / "source" / "legacy.pdf"
        _create_sample_pdf(src)
        
        base_name = "20260212__DB__legacy_test__leg123"
        
        # Call WITHOUT path_manager
        final_path, already = ensure_original_pdf_in_export(
            export_dir, base_name, src, path_manager=None
        )
        
        assert final_path is not None
        assert not already
        
        # Should be in export root
        expected_legacy_path = export_dir / f"{base_name}.pdf"
        assert final_path == expected_legacy_path
        assert final_path.exists()
        
        # Should NOT create originals/ subdirectory
        originals_dir = export_dir / "originals"
        if originals_dir.exists():
            originals_files = list(originals_dir.glob("*.pdf"))
            assert len(originals_files) == 0, (
                f"Legacy mode should not use originals/: {originals_files}"
            )


def test_path_manager_with_dedupe_style_basename():
    """
    Test with realistic dedupe-style basename from deterministic_base_filename.
    Format: {YYYYMMDD}__{source}__{title_slug}__{doc_id}
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "export"
        export_dir.mkdir()
        pm = TWIFOPathManager(export_dir)
        
        src = Path(tmpdir) / "source" / "report.pdf"
        _create_sample_pdf(src, b"%PDF-dedupe-test")
        
        # Realistic dedupe basename
        base_name = "20260212__MUFG__commodities_weekly_outlook__f8a3bc2d9e"
        
        final_path, _ = ensure_original_pdf_in_export(
            export_dir, base_name, src, path_manager=pm
        )
        
        assert final_path is not None
        assert final_path == pm.originals_dir / f"{base_name}.pdf"
        assert final_path.exists()
        
        # Verify export root is empty
        export_root_files = list(export_dir.glob("*.pdf"))
        # Filter out originals/ and artifacts/ subdirs
        export_root_files = [
            f for f in export_root_files 
            if f.parent == export_dir and f.is_file()
        ]
        assert len(export_root_files) == 0, (
            f"Export root should have no PDFs: {export_root_files}"
        )


def test_failure_on_missing_source():
    """
    Test that missing source returns (None, False) without creating empty files.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "export"
        export_dir.mkdir()
        pm = TWIFOPathManager(export_dir)
        
        nonexistent = Path(tmpdir) / "missing.pdf"
        base_name = "20260212__TEST__missing__xyz"
        
        final_path, already = ensure_original_pdf_in_export(
            export_dir, base_name, nonexistent, path_manager=pm
        )
        
        assert final_path is None
        assert not already
        
        # No file should be created in originals/
        expected_path = pm.originals_dir / f"{base_name}.pdf"
        assert not expected_path.exists()


if __name__ == "__main__":
    import sys
    
    tests = [
        test_original_pdf_written_to_originals_folder,
        test_original_pdf_multiple_calls_deterministic,
        test_legacy_mode_without_path_manager,
        test_path_manager_with_dedupe_style_basename,
        test_failure_on_missing_source,
    ]
    
    passed = 0
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"[PASS] {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {fn.__name__}")
            print(f"  Error: {e}")
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'='*60}")
    sys.exit(1 if failed else 0)
