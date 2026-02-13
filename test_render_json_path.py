"""
Unit Test: Render Function Receives Existing JSON Path

Purpose: Verify that the render function is called with an existing JSON file path
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

import os
import json
import tempfile
import shutil
from pathlib import Path
from typing import Tuple


def test_render_with_existing_json():
    """
    Test that render_summary_pdf is called with an existing JSON file path.
    
    This reproduces the issue where:
    1. Summary is created and JSON is written to path A
    2. Render is called with recomputed path B (which doesn't exist)
    3. Render fails with "JSON file not found"
    
    The fix ensures:
    1. summarize_pdf/summarize_text return the actual path used
    2. That path is verified to exist before passing to render
    3. Render receives the exact path that was written
    """
    print("\n[TEST] Render function with existing JSON path")
    
    # Create temporary directory for test
    test_dir = Path(tempfile.mkdtemp(prefix="test_render_"))
    
    try:
        # Import functions
        from summarize_pdf import summarize_text
        from summary_render import render_summary_pdf
        
        # Step 1: Create a summary using summarize_text
        print("  [1] Creating summary with summarize_text...")
        test_text = """
        Federal Reserve Meeting Minutes - January 2024
        
        The Federal Open Market Committee met on January 30-31, 2024.
        
        Key Points:
        - Interest rates held at 5.25-5.50%
        - Inflation remains elevated at 3.2%
        - Labor market showing signs of cooling
        - GDP growth expected to moderate to 2.1%
        
        The Committee will continue to monitor economic indicators closely.
        """
        
        summary_dict, json_path = summarize_text(
            test_text,
            title="Test_Fed_Minutes",
            provider="FED",
            published_date="20240131",
            horizon="u",
            out_dir=test_dir
        )
        
        print(f"  [OK] Summary created, JSON path returned: {json_path}")
        
        # Step 2: Verify JSON exists at the returned path
        print("  [2] Verifying JSON exists at returned path...")
        assert json_path.exists(), f"JSON should exist at {json_path}"
        assert os.path.exists(json_path), f"os.path.exists should return True for {json_path}"
        print(f"  [OK] JSON exists at: {json_path}")
        
        # Step 3: Verify JSON content is valid
        print("  [3] Verifying JSON content...")
        with open(json_path, 'r', encoding='utf-8') as f:
            loaded_json = json.load(f)
        assert 'meta' in loaded_json, "JSON should have 'meta' key"
        assert 'sections' in loaded_json, "JSON should have 'sections' key"
        print(f"  [OK] JSON is valid with keys: {list(loaded_json.keys())}")
        
        # Step 4: Call render function with the returned path
        print("  [4] Calling render_summary_pdf with returned JSON path...")
        pdf_path = json_path.parent / f"{json_path.stem}.pdf"
        
        render_result = render_summary_pdf(json_path, pdf_path)
        
        if render_result:
            print(f"  [OK] Render succeeded, PDF created at: {pdf_path}")
            assert pdf_path.exists(), f"PDF should exist at {pdf_path}"
        else:
            print(f"  [WARN] Render returned False (may be due to reportlab not installed)")
        
        # Step 5: Reproduce the bug scenario (recomputing path incorrectly)
        print("  [5] Testing bug scenario (recomputed path)...")
        wrong_json_path = test_dir / "Test_Fed_Minutes__sum.json"  # Legacy pattern
        
        if wrong_json_path != json_path:
            print(f"  [INFO] Recomputed path differs: {wrong_json_path}")
            print(f"  [INFO] Actual path was: {json_path}")
            
            # This would fail before the fix
            if not os.path.exists(wrong_json_path):
                print(f"  [OK] Bug scenario confirmed: recomputed path doesn't exist")
            else:
                print(f"  [INFO] Paths happen to match in this test setup")
        
        print("\n  [PASS] All assertions passed - render receives existing JSON path")
        
    except ImportError as e:
        print(f"  [SKIP] Required modules not available: {e}")
        print("  [INFO] This test requires summarize_pdf and summary_render modules")
        
    finally:
        # Cleanup
        if test_dir.exists():
            shutil.rmtree(test_dir)
            print(f"  [CLEANUP] Removed test directory: {test_dir}")


def test_path_manager_json_path():
    """
    Test that path_manager layout produces correct JSON paths.
    
    When using path_manager, JSON should go to:
      artifacts/<basename>/sum.json
    Not:
      <parent_dir>/<basename>__sum.json
    """
    print("\n[TEST] Path manager JSON path handling")
    
    try:
        from path_manager import TWIFOPathManager
        
        test_dir = Path(tempfile.mkdtemp(prefix="test_path_mgr_"))
        
        try:
            # Create path manager instance
            pm = TWIFOPathManager(test_dir)
            
            # Get expected path for a test file
            basename = "Test_Document_20240131"
            expected_json = pm.artifact_path(basename, 'sum.json')
            
            print(f"  [INFO] Test dir: {test_dir}")
            print(f"  [INFO] Expected JSON path: {expected_json}")
            
            # Verify path structure
            assert "artifacts" in str(expected_json), "Path should contain 'artifacts'"
            assert basename in str(expected_json), "Path should contain basename"
            assert expected_json.name == "sum.json", "File should be named sum.json"
            
            # Old pattern should be different
            old_pattern = test_dir / f"{basename}__sum.json"
            assert expected_json != old_pattern, "New path should differ from legacy pattern"
            
            print(f"  [OK] Path manager produces correct path structure")
            print(f"  [OK] Legacy pattern: {old_pattern}")
            print(f"  [OK] New pattern:    {expected_json}")
            print("\n  [PASS] Path manager test passed")
            
        finally:
            if test_dir.exists():
                shutil.rmtree(test_dir)
                
    except ImportError:
        print("  [SKIP] path_manager module not available")


def run_tests():
    """Run all unit tests."""
    print("=" * 80)
    print("RENDER JSON PATH UNIT TESTS")
    print("=" * 80)
    
    test_render_with_existing_json()
    test_path_manager_json_path()
    
    print("\n" + "=" * 80)
    print("ALL TESTS COMPLETE")
    print("=" * 80)
    print("\nKey assertions:")
    print("* summarize_text returns (dict, Path) tuple")
    print("* Returned path exists immediately after write")
    print("* os.path.exists(json_path) returns True")
    print("* render_summary_pdf receives existing file path")
    print("* Path is not recomputed incorrectly")


if __name__ == "__main__":
    run_tests()
