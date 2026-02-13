"""
Tests for TWIFO Path Manager
Purpose: Verify path mapping and migration logic
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

import tempfile
import shutil
from pathlib import Path
import pytest
from path_manager import TWIFOPathManager


def test_path_manager_initialization():
    """Test path manager creates required directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pm = TWIFOPathManager(Path(tmpdir))
        
        assert pm.originals_dir.exists()
        assert pm.artifacts_dir.exists()
        assert pm.originals_dir == Path(tmpdir) / "originals"
        assert pm.artifacts_dir == Path(tmpdir) / "artifacts"


def test_original_pdf_path():
    """Test original PDF path resolution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pm = TWIFOPathManager(Path(tmpdir))
        
        # With .pdf extension
        path1 = pm.original_pdf_path("BOA_Report_20260212_w.pdf")
        assert path1 == pm.originals_dir / "BOA_Report_20260212_w.pdf"
        
        # Without .pdf extension (should add it)
        path2 = pm.original_pdf_path("BOA_Report_20260212_w")
        assert path2 == pm.originals_dir / "BOA_Report_20260212_w.pdf"


def test_artifact_paths():
    """Test artifact path resolution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pm = TWIFOPathManager(Path(tmpdir))
        
        basename = "BOA_Report_20260212_w"
        
        # Test artifact directory
        art_dir = pm.artifact_dir(basename)
        assert art_dir == pm.artifacts_dir / basename
        
        # Test specific artifacts
        assert pm.artifact_path(basename, 'sum.json') == art_dir / 'sum.json'
        assert pm.artifact_path(basename, 'sum.txt') == art_dir / 'sum.txt'
        assert pm.artifact_path(basename, 'sum.pdf') == art_dir / 'sum.pdf'
        assert pm.artifact_path(basename, 'extracted.txt') == art_dir / 'extracted.txt'
        
        # Test with .pdf extension (should strip it)
        assert pm.artifact_path(f"{basename}.pdf", 'sum.json') == art_dir / 'sum.json'


def test_has_summary():
    """Test summary existence checks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pm = TWIFOPathManager(Path(tmpdir))
        basename = "BOA_Report_20260212_w"
        
        # Initially no summaries
        has_pdf, has_json, has_txt = pm.has_summary(basename)
        assert not has_pdf
        assert not has_json
        assert not has_txt
        
        # Create sum.json
        art_dir = pm.ensure_artifact_dir(basename)
        (art_dir / 'sum.json').write_text('{}')
        
        has_pdf, has_json, has_txt = pm.has_summary(basename)
        assert not has_pdf
        assert has_json
        assert not has_txt
        
        # Create sum.pdf
        (art_dir / 'sum.pdf').write_text('fake pdf')
        
        has_pdf, has_json, has_txt = pm.has_summary(basename)
        assert has_pdf
        assert has_json
        assert not has_txt


def test_list_originals():
    """Test listing original PDFs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pm = TWIFOPathManager(Path(tmpdir))
        
        # Initially empty
        assert pm.list_originals() == []
        
        # Create some PDFs
        (pm.originals_dir / "BOA_Report_20260212_w.pdf").write_text('fake')
        (pm.originals_dir / "JPM_Analysis_20260211_m.pdf").write_text('fake')
        (pm.originals_dir / "not_a_pdf.txt").write_text('fake')  # Should be ignored
        
        originals = pm.list_originals()
        assert len(originals) == 2
        assert "BOA_Report_20260212_w.pdf" in originals
        assert "JPM_Analysis_20260211_m.pdf" in originals
        assert "not_a_pdf.txt" not in originals


def test_list_artifacts_with_summaries():
    """Test listing artifacts that have summaries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pm = TWIFOPathManager(Path(tmpdir))
        
        # Create artifact with sum.json only
        basename1 = "BOA_Report_20260212_w"
        art_dir1 = pm.ensure_artifact_dir(basename1)
        (art_dir1 / 'sum.json').write_text('{}')
        
        # Create artifact with sum.pdf and sum.json
        basename2 = "JPM_Analysis_20260211_m"
        art_dir2 = pm.ensure_artifact_dir(basename2)
        (art_dir2 / 'sum.json').write_text('{}')
        (art_dir2 / 'sum.pdf').write_text('fake')
        
        # Create artifact with no summaries (should be excluded)
        basename3 = "Empty_Artifact"
        pm.ensure_artifact_dir(basename3)
        
        artifacts = pm.list_artifacts_with_summaries()
        assert len(artifacts) == 2
        
        # Check first artifact
        art1 = next(a for a in artifacts if a['basename'] == basename1)
        assert not art1['has_sum_pdf']
        assert art1['has_sum_json']
        assert not art1['has_sum_txt']
        
        # Check second artifact
        art2 = next(a for a in artifacts if a['basename'] == basename2)
        assert art2['has_sum_pdf']
        assert art2['has_sum_json']
        assert not art2['has_sum_txt']


def test_migrate_legacy_pdf():
    """Test migrating legacy PDF to originals/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pm = TWIFOPathManager(Path(tmpdir))
        
        # Create legacy PDF in root
        legacy_path = pm.files_dir / "BOA_Report_20260212_w.pdf"
        legacy_path.write_text('fake pdf content')
        
        # Migrate
        new_path = pm.migrate_legacy_file(legacy_path)
        
        assert new_path == pm.originals_dir / "BOA_Report_20260212_w.pdf"
        assert new_path.exists()
        assert not legacy_path.exists()


def test_migrate_legacy_summary_files():
    """Test migrating legacy summary files to artifacts/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pm = TWIFOPathManager(Path(tmpdir))
        
        basename = "BOA_Report_20260212_w"
        
        # Create legacy summary files in root
        legacy_json = pm.files_dir / f"{basename}__sum.json"
        legacy_txt = pm.files_dir / f"{basename}__sum.txt"
        legacy_pdf = pm.files_dir / f"{basename}__sum.pdf"
        
        legacy_json.write_text('{}')
        legacy_txt.write_text('summary text')
        legacy_pdf.write_text('fake pdf')
        
        # Migrate
        pm.migrate_legacy_file(legacy_json)
        pm.migrate_legacy_file(legacy_txt)
        pm.migrate_legacy_file(legacy_pdf)
        
        # Check new locations
        art_dir = pm.artifact_dir(basename)
        assert (art_dir / 'sum.json').exists()
        assert (art_dir / 'sum.txt').exists()
        assert (art_dir / 'sum.pdf').exists()
        
        # Check old locations are gone
        assert not legacy_json.exists()
        assert not legacy_txt.exists()
        assert not legacy_pdf.exists()


def test_migrate_all_legacy_files():
    """Test bulk migration of legacy files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pm = TWIFOPathManager(Path(tmpdir))
        
        # Create legacy files
        (pm.files_dir / "BOA_Report_20260212_w.pdf").write_text('fake')
        (pm.files_dir / "BOA_Report_20260212_w__sum.json").write_text('{}')
        (pm.files_dir / "JPM_Analysis_20260211_m.pdf").write_text('fake')
        (pm.files_dir / "JPM_Analysis_20260211_m__sum.pdf").write_text('fake')
        
        # Migrate all
        counts = pm.migrate_all_legacy_files()
        
        assert counts['originals'] == 2
        assert counts['artifacts'] == 2
        
        # Verify new structure
        assert pm.has_original("BOA_Report_20260212_w.pdf")
        assert pm.has_original("JPM_Analysis_20260211_m.pdf")
        assert pm.artifact_path("BOA_Report_20260212_w", "sum.json").exists()
        assert pm.artifact_path("JPM_Analysis_20260211_m", "sum.pdf").exists()


def test_get_summary_paths():
    """Test getting all summary-related paths for a basename."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pm = TWIFOPathManager(Path(tmpdir))
        basename = "BOA_Report_20260212_w"
        
        # Create original and some artifacts
        orig_path = pm.original_pdf_path(basename)
        orig_path.write_text('fake pdf')
        
        art_dir = pm.ensure_artifact_dir(basename)
        (art_dir / 'sum.json').write_text('{}')
        (art_dir / 'sum.pdf').write_text('fake')
        
        # Get all paths
        paths = pm.get_summary_paths(basename)
        
        assert paths['original_pdf'] == orig_path
        assert paths['sum_json'] == art_dir / 'sum.json'
        assert paths['sum_txt'] is None  # Doesn't exist
        assert paths['sum_pdf'] == art_dir / 'sum.pdf'


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
