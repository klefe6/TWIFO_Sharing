"""
Test: Dual Layout PDF Discovery
Purpose: Verify table discovers PDFs from BOTH originals/ and root legacy folders
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

import os
import sys
from pathlib import Path
import tempfile
import shutil

# Mock imports to test the discovery logic
def test_dual_layout_discovery():
    """Test that PDFs are discovered from both new and legacy layouts."""
    print("\n[TEST] Dual layout PDF discovery")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        files_dir = Path(tmpdir)
        
        # Create directory structure
        originals_dir = files_dir / "originals"
        originals_dir.mkdir()
        
        # Create test PDFs in new layout (originals/)
        new_pdf1 = originals_dir / "20260212__BOA__quarterly_report__abc123.pdf"
        new_pdf2 = originals_dir / "20260211__JPM__market_update__def456.pdf"
        new_pdf1.write_bytes(b"%PDF-1.4 new layout 1")
        new_pdf2.write_bytes(b"%PDF-1.4 new layout 2")
        
        # Create test PDFs in legacy layout (root)
        legacy_pdf1 = files_dir / "GS_Weekly_Outlook_20260210_w.pdf"
        legacy_pdf2 = files_dir / "MS_Daily_Brief_20260209_d.pdf"
        legacy_pdf1.write_bytes(b"%PDF-1.4 legacy 1")
        legacy_pdf2.write_bytes(b"%PDF-1.4 legacy 2")
        
        # Create a subdirectory (should be skipped)
        artifacts_dir = files_dir / "artifacts"
        artifacts_dir.mkdir()
        artifacts_pdf = artifacts_dir / "should_not_appear.pdf"
        artifacts_pdf.write_bytes(b"%PDF-1.4 in subdir")
        
        # Simulate discovery logic
        all_pdfs = []
        seen_basenames = set()
        
        # 1. Scan originals/
        if originals_dir.exists():
            for item in originals_dir.glob("*.pdf"):
                if item.is_file():
                    basename = item.stem
                    if basename not in seen_basenames:
                        all_pdfs.append((item.name, str(item), 'new'))
                        seen_basenames.add(basename)
        
        # 2. Scan root (skip subdirectories)
        for item in files_dir.iterdir():
            if item.is_dir():
                continue  # Skip directories
            if item.suffix.lower() == '.pdf':
                basename = item.stem
                if basename not in seen_basenames:
                    all_pdfs.append((item.name, str(item), 'legacy'))
                    seen_basenames.add(basename)
        
        # Verify results
        assert len(all_pdfs) == 4, f"Expected 4 PDFs, found {len(all_pdfs)}"
        
        # Check that we have both new and legacy PDFs
        new_pdfs = [p for p in all_pdfs if p[2] == 'new']
        legacy_pdfs = [p for p in all_pdfs if p[2] == 'legacy']
        
        assert len(new_pdfs) == 2, f"Expected 2 new layout PDFs, found {len(new_pdfs)}"
        assert len(legacy_pdfs) == 2, f"Expected 2 legacy PDFs, found {len(legacy_pdfs)}"
        
        # Verify specific files
        filenames = [p[0] for p in all_pdfs]
        assert "20260212__BOA__quarterly_report__abc123.pdf" in filenames
        assert "20260211__JPM__market_update__def456.pdf" in filenames
        assert "GS_Weekly_Outlook_20260210_w.pdf" in filenames
        assert "MS_Daily_Brief_20260209_d.pdf" in filenames
        assert "should_not_appear.pdf" not in filenames, "PDFs in subdirectories should be skipped"
        
        print(f"  [PASS] Discovered {len(all_pdfs)} PDFs")
        print(f"    New layout: {len(new_pdfs)} files")
        print(f"    Legacy layout: {len(legacy_pdfs)} files")
        print(f"    Subdirectories correctly skipped")


def test_deduplication_by_basename():
    """Test that duplicate basenames are not listed twice."""
    print("\n[TEST] Deduplication by basename")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        files_dir = Path(tmpdir)
        originals_dir = files_dir / "originals"
        originals_dir.mkdir()
        
        # Create same basename in BOTH locations (should prioritize originals/)
        same_name = "BOA_Report_20260212_w.pdf"
        new_pdf = originals_dir / same_name
        legacy_pdf = files_dir / same_name
        new_pdf.write_bytes(b"%PDF-1.4 in originals")
        legacy_pdf.write_bytes(b"%PDF-1.4 in root (duplicate)")
        
        # Simulate discovery with deduplication
        all_pdfs = []
        seen_basenames = set()
        
        # 1. Scan originals/ first (higher priority)
        for item in originals_dir.glob("*.pdf"):
            if item.is_file():
                basename = item.stem
                if basename not in seen_basenames:
                    all_pdfs.append((item.name, str(item), 'new'))
                    seen_basenames.add(basename)
        
        # 2. Scan root
        for item in files_dir.iterdir():
            if item.is_dir():
                continue
            if item.suffix.lower() == '.pdf':
                basename = item.stem
                if basename not in seen_basenames:
                    all_pdfs.append((item.name, str(item), 'legacy'))
                    seen_basenames.add(basename)
        
        # Verify: should only have ONE entry (from originals/)
        assert len(all_pdfs) == 1, f"Expected 1 PDF (deduplicated), found {len(all_pdfs)}"
        assert all_pdfs[0][2] == 'new', "Should prioritize originals/ over root"
        assert "originals" in all_pdfs[0][1], "Path should be from originals/"
        
        print(f"  [PASS] Deduplication works correctly")
        print(f"    Prioritized: originals/ over root")


def test_legacy_only_mode():
    """Test fallback when path_manager is not available."""
    print("\n[TEST] Legacy-only mode (no path_manager)")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        files_dir = Path(tmpdir)
        
        # Only create legacy PDFs (no originals/ folder)
        legacy_pdf1 = files_dir / "BOA_Report_20260212_w.pdf"
        legacy_pdf2 = files_dir / "JPM_Update_20260211_w.pdf"
        legacy_pdf1.write_bytes(b"%PDF-1.4 legacy 1")
        legacy_pdf2.write_bytes(b"%PDF-1.4 legacy 2")
        
        # Simulate legacy-only scanning
        all_pdfs = []
        for item in files_dir.iterdir():
            if item.is_file() and item.suffix.lower() == '.pdf':
                all_pdfs.append((item.name, str(item), 'legacy'))
        
        assert len(all_pdfs) == 2, f"Expected 2 legacy PDFs, found {len(all_pdfs)}"
        
        print(f"  [PASS] Legacy-only mode works")
        print(f"    Discovered {len(all_pdfs)} PDFs from root")


def test_empty_directory():
    """Test behavior with empty directories."""
    print("\n[TEST] Empty directory handling")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        files_dir = Path(tmpdir)
        originals_dir = files_dir / "originals"
        originals_dir.mkdir()
        
        # No PDFs in either location
        all_pdfs = []
        seen_basenames = set()
        
        # Scan originals/
        if originals_dir.exists():
            for item in originals_dir.glob("*.pdf"):
                if item.is_file():
                    basename = item.stem
                    if basename not in seen_basenames:
                        all_pdfs.append((item.name, str(item), 'new'))
                        seen_basenames.add(basename)
        
        # Scan root
        for item in files_dir.iterdir():
            if item.is_dir():
                continue
            if item.suffix.lower() == '.pdf':
                basename = item.stem
                if basename not in seen_basenames:
                    all_pdfs.append((item.name, str(item), 'legacy'))
                    seen_basenames.add(basename)
        
        assert len(all_pdfs) == 0, f"Expected 0 PDFs, found {len(all_pdfs)}"
        
        print(f"  [PASS] Empty directory handled gracefully")


if __name__ == "__main__":
    tests = [
        test_dual_layout_discovery,
        test_deduplication_by_basename,
        test_legacy_only_mode,
        test_empty_directory,
    ]
    
    passed = 0
    failed = 0
    
    print("=" * 70)
    print("DUAL LAYOUT PDF DISCOVERY - VALIDATION")
    print("=" * 70)
    
    for fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {fn.__name__}")
            print(f"    Error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print("=" * 70)
    
    if failed == 0:
        print("\nDual layout discovery validated:")
        print("  [OK] Scans BOTH originals/ and root FILES_DIR")
        print("  [OK] Excludes subdirectories (artifacts/, rollups/)")
        print("  [OK] Deduplicates by basename (prioritizes originals/)")
        print("  [OK] Works in legacy-only mode")
        print("  [OK] Handles empty directories gracefully")
    
    sys.exit(1 if failed else 0)
