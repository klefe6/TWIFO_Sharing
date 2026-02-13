"""
Test: verify_export_structure with temp dirs and path_manager
Purpose: Ensure final export directory contains correct structure with proper counts
Author: Kevin Lefebvre
Last Updated: 2026-02-12

Run:
    python test_export_structure_verification.py
    python -m pytest test_export_structure_verification.py -v
"""

import tempfile
from pathlib import Path
import json
import sys

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from path_manager import TWIFOPathManager
from db_filter_autorun import verify_export_structure


def _create_sample_pdf(path: Path, content: bytes = b"%PDF-test") -> None:
    """Create a minimal PDF for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _create_sample_summary_json(path: Path, title: str = "Test") -> None:
    """Create a minimal summary JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": "twifo.sum.v1",
        "meta": {"title": title},
        "sections": {}
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_verify_export_with_path_manager():
    """
    Test verify_export_structure counts files correctly with path_manager enabled.
    Simulates the full structure after db_filter_autorun.py completes.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "FOLDERS_AVAILABLE_ONLINE"
        export_dir.mkdir()
        
        # Initialize path_manager
        pm = TWIFOPathManager(export_dir)
        
        # Create originals (3 PDFs)
        _create_sample_pdf(pm.originals_dir / "BOA_Report_20260212_w.pdf")
        _create_sample_pdf(pm.originals_dir / "JPM_Analysis_20260211_m.pdf")
        _create_sample_pdf(pm.originals_dir / "DB_Weekly_20260210_w.pdf")
        
        # Create artifacts (2 bundles with summaries)
        basename1 = "20260212__BOA__quarterly_report__abc123"
        art_dir1 = pm.ensure_artifact_dir(basename1)
        _create_sample_summary_json(art_dir1 / "sum.json", "BOA Report")
        (art_dir1 / "sum.pdf").write_bytes(b"%PDF-summary-1")
        (art_dir1 / "extracted.txt").write_text("Extracted text 1")
        
        basename2 = "20260211__JPM__analysis__xyz789"
        art_dir2 = pm.ensure_artifact_dir(basename2)
        _create_sample_summary_json(art_dir2 / "sum.json", "JPM Analysis")
        (art_dir2 / "sum.pdf").write_bytes(b"%PDF-summary-2")
        
        # Create rollups
        rollups_dir = export_dir / "rollups"
        daily_dir = rollups_dir / "daily"
        weekly_dir = rollups_dir / "weekly"
        daily_dir.mkdir(parents=True, exist_ok=True)
        weekly_dir.mkdir(parents=True, exist_ok=True)
        
        # 2 daily rollups
        _create_sample_summary_json(daily_dir / "ROLLUP_DAILY_20260212__sum.json", "Daily 1")
        _create_sample_summary_json(daily_dir / "ROLLUP_DAILY_20260211__sum.json", "Daily 2")
        
        # 1 weekly rollup
        _create_sample_summary_json(weekly_dir / "ROLLUP_WEEKLY_2026W07__sum.json", "Weekly 1")
        
        # Verify structure
        counts = verify_export_structure(export_dir, path_manager=pm)
        
        # Assertions
        assert counts['originals'] == 3, f"Expected 3 originals, got {counts['originals']}"
        assert counts['artifacts'] == 2, f"Expected 2 artifacts, got {counts['artifacts']}"
        assert counts['rollups_daily'] == 2, f"Expected 2 daily rollups, got {counts['rollups_daily']}"
        assert counts['rollups_weekly'] == 1, f"Expected 1 weekly rollup, got {counts['rollups_weekly']}"
        
        print(f"  OK Originals: {counts['originals']}")
        print(f"  OK Artifacts: {counts['artifacts']}")
        print(f"  OK Daily rollups: {counts['rollups_daily']}")
        print(f"  OK Weekly rollups: {counts['rollups_weekly']}")


def test_verify_export_legacy_mode():
    """
    Test verify_export_structure in legacy mode (no path_manager).
    Files should be in export root, not subdirectories.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "export"
        export_dir.mkdir()
        
        # Create PDFs in root (legacy layout)
        _create_sample_pdf(export_dir / "BOA_Report_20260212_w.pdf")
        _create_sample_pdf(export_dir / "JPM_Analysis_20260211_m.pdf")
        
        # Create summary JSONs in root (legacy layout)
        _create_sample_summary_json(export_dir / "BOA_Report_20260212_w__sum.json")
        _create_sample_summary_json(export_dir / "JPM_Analysis_20260211_m__sum.json")
        
        # Create rollups (same structure)
        rollups_dir = export_dir / "rollups"
        daily_dir = rollups_dir / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        _create_sample_summary_json(daily_dir / "ROLLUP_DAILY_20260212__sum.json")
        
        # Verify structure WITHOUT path_manager
        counts = verify_export_structure(export_dir, path_manager=None)
        
        assert counts['originals'] == 2, f"Expected 2 PDFs, got {counts['originals']}"
        assert counts['artifacts'] == 2, f"Expected 2 summaries, got {counts['artifacts']}"
        assert counts['rollups_daily'] == 1, f"Expected 1 daily rollup, got {counts['rollups_daily']}"
        
        print(f"  OK Legacy originals: {counts['originals']}")
        print(f"  OK Legacy artifacts: {counts['artifacts']}")
        print(f"  OK Legacy rollups: {counts['rollups_daily']}")


def test_verify_export_preserves_structure():
    """
    Test that relative paths are preserved correctly.
    originals/*.pdf should stay under originals/
    artifacts/<base>/** should stay under artifacts/<base>/
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "export"
        export_dir.mkdir()
        pm = TWIFOPathManager(export_dir)
        
        # Create structure
        basename = "20260212__TEST__report__abc"
        orig_path = pm.originals_dir / f"{basename}.pdf"
        _create_sample_pdf(orig_path)
        
        art_dir = pm.ensure_artifact_dir(basename)
        _create_sample_summary_json(art_dir / "sum.json")
        (art_dir / "sum.pdf").write_bytes(b"%PDF")
        
        # Verify paths are preserved
        assert orig_path.exists(), "Original should exist under originals/"
        assert orig_path.parent == pm.originals_dir, (
            f"Original parent should be {pm.originals_dir}, got {orig_path.parent}"
        )
        
        assert (art_dir / "sum.json").exists(), "Artifact should exist under artifacts/"
        assert art_dir.parent == pm.artifacts_dir, (
            f"Artifact parent should be {pm.artifacts_dir}, got {art_dir.parent}"
        )
        
        # Verify no files in export root
        root_pdfs = list(export_dir.glob("*.pdf"))
        root_pdfs = [f for f in root_pdfs if f.parent == export_dir]
        assert len(root_pdfs) == 0, f"No PDFs should be in export root: {root_pdfs}"
        
        print("  OK Structure preserved: originals/ and artifacts/ subdirectories intact")


def test_verify_empty_export():
    """Test verify_export_structure on empty directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "empty"
        export_dir.mkdir()
        pm = TWIFOPathManager(export_dir)
        
        counts = verify_export_structure(export_dir, path_manager=pm)
        
        assert counts['originals'] == 0
        assert counts['artifacts'] == 0
        assert counts['rollups_daily'] == 0
        assert counts['rollups_weekly'] == 0
        
        print("  OK Empty export: all counts zero")


def test_verify_export_artifact_without_summaries():
    """
    Test that artifacts without summary files are not counted.
    Only count artifact directories that have at least one sum.* file.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "export"
        export_dir.mkdir()
        pm = TWIFOPathManager(export_dir)
        
        # Create artifact dir with summary
        basename1 = "20260212__BOA__report1__abc"
        art_dir1 = pm.ensure_artifact_dir(basename1)
        _create_sample_summary_json(art_dir1 / "sum.json")
        
        # Create artifact dir WITHOUT summary (should not be counted)
        basename2 = "20260212__BOA__report2__xyz"
        art_dir2 = pm.ensure_artifact_dir(basename2)
        (art_dir2 / "extracted.txt").write_text("no summary")
        
        counts = verify_export_structure(export_dir, path_manager=pm)
        
        # Only 1 should be counted (the one with sum.json)
        assert counts['artifacts'] == 1, (
            f"Expected 1 artifact (with summary), got {counts['artifacts']}"
        )
        
        print("  OK Artifacts without summaries not counted")


def test_full_export_simulation():
    """
    Comprehensive test simulating full db_filter_autorun.py output.
    Tests the complete flow with multiple dates and providers.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        export_dir = Path(tmpdir) / "FOLDERS_AVAILABLE_ONLINE"
        export_dir.mkdir()
        pm = TWIFOPathManager(export_dir)
        
        # Simulate processing 2 dates with multiple providers
        dates = ["20260212", "20260211"]
        providers = ["BOA", "JPM", "DB", "MUFG"]
        
        for date_str in dates:
            for provider in providers:
                basename = f"{date_str}__{provider}__weekly_outlook__{'x' * 10}"
                
                # Original PDF
                _create_sample_pdf(pm.originals_dir / f"{basename}.pdf")
                
                # Artifact bundle
                art_dir = pm.ensure_artifact_dir(basename)
                _create_sample_summary_json(art_dir / "sum.json", f"{provider} {date_str}")
                (art_dir / "sum.pdf").write_bytes(b"%PDF-summary")
                (art_dir / "sum.txt").write_text("Summary text")
                (art_dir / "extracted.txt").write_text("Extracted text")
        
        # Create rollups for both dates
        rollups_dir = export_dir / "rollups"
        daily_dir = rollups_dir / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        
        for date_str in dates:
            _create_sample_summary_json(
                daily_dir / f"ROLLUP_DAILY_{date_str}__sum.json",
                f"Daily rollup {date_str}"
            )
        
        # Verify
        counts = verify_export_structure(export_dir, path_manager=pm)
        
        expected_originals = len(dates) * len(providers)  # 2 * 4 = 8
        expected_artifacts = len(dates) * len(providers)  # 2 * 4 = 8
        expected_rollups = len(dates)  # 2
        
        assert counts['originals'] == expected_originals, (
            f"Expected {expected_originals} originals, got {counts['originals']}"
        )
        assert counts['artifacts'] == expected_artifacts, (
            f"Expected {expected_artifacts} artifacts, got {counts['artifacts']}"
        )
        assert counts['rollups_daily'] == expected_rollups, (
            f"Expected {expected_rollups} daily rollups, got {counts['rollups_daily']}"
        )
        
        print(f"  OK Full simulation: {expected_originals} originals, "
              f"{expected_artifacts} artifacts, {expected_rollups} rollups")


if __name__ == "__main__":
    tests = [
        test_verify_export_with_path_manager,
        test_verify_export_legacy_mode,
        test_verify_export_preserves_structure,
        test_verify_empty_export,
        test_verify_export_artifact_without_summaries,
        test_full_export_simulation,
    ]
    
    passed = 0
    failed = 0
    for fn in tests:
        try:
            print(f"Running {fn.__name__}...")
            fn()
            print(f"[PASS] {fn.__name__}\n")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {fn.__name__}")
            print(f"  Error: {e}\n")
            failed += 1
    
    print(f"{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'='*60}")
    sys.exit(1 if failed else 0)
