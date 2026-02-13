"""
Tests for --rebuild-missing: re-process DB duplicates when output files are missing.
Purpose: Verify rebuild-missing bypasses dedupe only when files are truly absent.

Run:
    python test_rebuild_missing.py
    python -m pytest test_rebuild_missing.py -v
"""

import tempfile
from pathlib import Path

import pytest

from db_filter_autorun import _outputs_exist_on_disk
from path_manager import TWIFOPathManager


def _create_minimal_pdf(path: Path) -> None:
    """Write a tiny valid PDF for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n%%EOF\n")


def _create_minimal_json(path: Path) -> None:
    """Write a minimal JSON for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"schema_version":"twifo.sum.v1"}', encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════
# _outputs_exist_on_disk — path_manager mode
# ═══════════════════════════════════════════════════════════════════════

def test_outputs_exist_path_manager_all_present():
    """When both PDF and JSON exist in path_manager layout, return True."""
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir)
        pm = TWIFOPathManager(export_dir)
        base = "20260212__TEST__report__abc123"

        # Create originals/base.pdf and artifacts/base/sum.json
        _create_minimal_pdf(pm.original_pdf_path(f"{base}.pdf"))
        pm.ensure_artifact_dir(base)
        _create_minimal_json(pm.artifact_path(base, "sum.json"))

        assert _outputs_exist_on_disk(export_dir, base, path_manager=pm) is True


def test_outputs_missing_path_manager_no_pdf():
    """When PDF is missing from originals/, return False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir)
        pm = TWIFOPathManager(export_dir)
        base = "20260212__TEST__report__abc123"

        # Only create JSON, not PDF
        pm.ensure_artifact_dir(base)
        _create_minimal_json(pm.artifact_path(base, "sum.json"))

        assert _outputs_exist_on_disk(export_dir, base, path_manager=pm) is False


def test_outputs_missing_path_manager_no_json():
    """When sum.json is missing from artifacts/, return False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir)
        pm = TWIFOPathManager(export_dir)
        base = "20260212__TEST__report__abc123"

        # Only create PDF, not JSON
        _create_minimal_pdf(pm.original_pdf_path(f"{base}.pdf"))

        assert _outputs_exist_on_disk(export_dir, base, path_manager=pm) is False


def test_outputs_missing_path_manager_nothing():
    """When both PDF and JSON are missing, return False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir)
        pm = TWIFOPathManager(export_dir)
        base = "20260212__TEST__report__abc123"

        assert _outputs_exist_on_disk(export_dir, base, path_manager=pm) is False


# ═══════════════════════════════════════════════════════════════════════
# _outputs_exist_on_disk — legacy mode (no path_manager)
# ═══════════════════════════════════════════════════════════════════════

def test_outputs_exist_legacy_all_present():
    """Legacy layout: both base.pdf and base__sum.json in export root → True."""
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir)
        base = "20260212__TEST__report__abc123"

        _create_minimal_pdf(export_dir / f"{base}.pdf")
        _create_minimal_json(export_dir / f"{base}__sum.json")

        assert _outputs_exist_on_disk(export_dir, base, path_manager=None) is True


def test_outputs_missing_legacy_no_json():
    """Legacy layout: missing __sum.json → False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir)
        base = "20260212__TEST__report__abc123"

        _create_minimal_pdf(export_dir / f"{base}.pdf")
        # No __sum.json

        assert _outputs_exist_on_disk(export_dir, base, path_manager=None) is False


# ═══════════════════════════════════════════════════════════════════════
# Integration: duplicate in DB + files missing => should proceed
# Integration: duplicate in DB + files exist => should skip
# ═══════════════════════════════════════════════════════════════════════

def test_rebuild_missing_proceeds_when_files_absent():
    """
    Simulates: preflight says skip (status=done), but files are missing on disk.
    With rebuild_missing=True, the skip should be overridden.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir)
        pm = TWIFOPathManager(export_dir)
        base = "20260212__TEST__rebuild__def456"

        # DB says "done" → preflight_check would return (True, "record_exists")
        skip_pre = True
        rebuild_missing = True

        # Files do NOT exist on disk
        files_on_disk = _outputs_exist_on_disk(export_dir, base, path_manager=pm)
        assert files_on_disk is False, "Precondition: files should be absent"

        # Decision logic (mirrors db_filter_autorun logic)
        should_skip = True
        if skip_pre and rebuild_missing and not files_on_disk:
            should_skip = False  # Override: proceed to rebuild

        assert should_skip is False, "Should proceed when files are missing"


def test_rebuild_missing_skips_when_files_present():
    """
    Simulates: preflight says skip (status=done) AND files exist on disk.
    With rebuild_missing=True, the skip should NOT be overridden.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir)
        pm = TWIFOPathManager(export_dir)
        base = "20260212__TEST__rebuild__ghi789"

        # Create all expected output files
        _create_minimal_pdf(pm.original_pdf_path(f"{base}.pdf"))
        pm.ensure_artifact_dir(base)
        _create_minimal_json(pm.artifact_path(base, "sum.json"))

        # DB says "done" → preflight_check would return (True, "record_exists")
        skip_pre = True
        rebuild_missing = True

        files_on_disk = _outputs_exist_on_disk(export_dir, base, path_manager=pm)
        assert files_on_disk is True, "Precondition: files should exist"

        # Decision logic
        should_skip = True
        if skip_pre and rebuild_missing and not files_on_disk:
            should_skip = False

        assert should_skip is True, "Should skip when files exist"


def test_no_rebuild_flag_always_skips():
    """Without --rebuild-missing, preflight skip is always respected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir)
        pm = TWIFOPathManager(export_dir)
        base = "20260212__TEST__noflag__jkl012"

        # Files missing, but rebuild_missing=False
        skip_pre = True
        rebuild_missing = False

        files_on_disk = _outputs_exist_on_disk(export_dir, base, path_manager=pm)
        assert files_on_disk is False

        should_skip = True
        if skip_pre and rebuild_missing and not files_on_disk:
            should_skip = False

        assert should_skip is True, "Without flag, skip should be respected"


if __name__ == "__main__":
    import sys

    tests = [
        test_outputs_exist_path_manager_all_present,
        test_outputs_missing_path_manager_no_pdf,
        test_outputs_missing_path_manager_no_json,
        test_outputs_missing_path_manager_nothing,
        test_outputs_exist_legacy_all_present,
        test_outputs_missing_legacy_no_json,
        test_rebuild_missing_proceeds_when_files_absent,
        test_rebuild_missing_skips_when_files_present,
        test_no_rebuild_flag_always_skips,
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
