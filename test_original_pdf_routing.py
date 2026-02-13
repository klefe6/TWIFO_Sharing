"""
Tests for original PDF routing: ensure_original_pdf_in_export writes to originals/
when path_manager is enabled, and to export root when disabled.

Run:
    python test_original_pdf_routing.py
    python -m pytest test_original_pdf_routing.py -v
"""

import tempfile
from pathlib import Path

import pytest

from ingest_dedup import ensure_original_pdf_in_export
from path_manager import TWIFOPathManager


def _create_source_pdf(path: Path) -> None:
    """Create a minimal valid PDF for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"xref\n0 4\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
    )


def test_path_manager_routes_to_originals():
    """With path_manager enabled, PDF lands in originals/ subdirectory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "export"
        export_dir.mkdir()
        pm = TWIFOPathManager(export_dir)

        src = Path(tmpdir) / "source" / "sample.pdf"
        _create_source_pdf(src)

        base_name = "20260212__TEST__report__abc123"
        final, already = ensure_original_pdf_in_export(
            export_dir, base_name, src, path_manager=pm,
        )

        # Must succeed
        assert final is not None, "Copy should succeed"
        assert not already, "Should not be pre-existing"

        # Must be inside originals/
        assert final.parent == pm.originals_dir, (
            f"Expected parent={pm.originals_dir}, got {final.parent}"
        )
        assert final.exists(), f"File should exist at {final}"
        assert final.stat().st_size > 0, "File should not be empty"

        # Must NOT be in the export root
        root_candidate = export_dir / f"{base_name}.pdf"
        assert not root_candidate.exists(), (
            f"File should NOT exist in export root: {root_candidate}"
        )


def test_legacy_routes_to_export_root():
    """Without path_manager, PDF lands in export root (legacy behavior)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "export"
        export_dir.mkdir()

        src = Path(tmpdir) / "source" / "sample.pdf"
        _create_source_pdf(src)

        base_name = "20260212__TEST__report__abc123"
        final, already = ensure_original_pdf_in_export(
            export_dir, base_name, src, path_manager=None,
        )

        assert final is not None, "Copy should succeed"
        assert not already

        # Must be in export root
        assert final == export_dir / f"{base_name}.pdf"
        assert final.exists()
        assert final.stat().st_size > 0

        # originals/ should not even be consulted
        originals_dir = export_dir / "originals"
        if originals_dir.exists():
            originals_files = list(originals_dir.iterdir())
            assert len(originals_files) == 0, (
                f"No files should be in originals/ for legacy mode: {originals_files}"
            )


def test_already_exists_returns_true():
    """If the PDF already exists in originals/, return (path, True) without re-copying."""
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "export"
        export_dir.mkdir()
        pm = TWIFOPathManager(export_dir)

        src = Path(tmpdir) / "source" / "sample.pdf"
        _create_source_pdf(src)

        base_name = "20260212__TEST__existing__xyz"

        # Pre-populate originals/
        dest = pm.original_pdf_path(f"{base_name}.pdf")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"%PDF-preexisting")

        final, already = ensure_original_pdf_in_export(
            export_dir, base_name, src, path_manager=pm,
        )

        assert final is not None
        assert already is True, "Should detect pre-existing file"
        # Content should be the old file (not overwritten)
        assert final.read_bytes() == b"%PDF-preexisting"


def test_missing_source_returns_none():
    """If source PDF doesn't exist, return (None, False)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "export"
        export_dir.mkdir()
        pm = TWIFOPathManager(export_dir)

        bogus_src = Path(tmpdir) / "nonexistent.pdf"
        final, already = ensure_original_pdf_in_export(
            export_dir, "test_base", bogus_src, path_manager=pm,
        )

        assert final is None
        assert already is False


if __name__ == "__main__":
    import sys

    tests = [
        test_path_manager_routes_to_originals,
        test_legacy_routes_to_export_root,
        test_already_exists_returns_true,
        test_missing_source_returns_none,
    ]

    passed = 0
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"[PASS] {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {fn.__name__}: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed out of {len(tests)}")
    sys.exit(1 if failed else 0)
