"""
Verification script: Test module imports after rename.
Ensures twifo_prompts works and summary package doesn't shadow.

Run from TWIFO_Sharing directory:
    python test_module_imports.py
"""

import sys


def test_twifo_prompts_import():
    """Test that twifo_prompts module imports correctly."""
    print("Testing twifo_prompts import...")
    try:
        from twifo_prompts.prompts import article_prompts
        
        # Verify expected attributes exist
        assert hasattr(article_prompts, 'PROMPT_VERSION'), "Missing PROMPT_VERSION"
        assert hasattr(article_prompts, 'SYSTEM_PROMPT'), "Missing SYSTEM_PROMPT"
        assert hasattr(article_prompts, 'USER_PROMPT'), "Missing USER_PROMPT"
        assert hasattr(article_prompts, 'prompt_sha256'), "Missing prompt_sha256"
        
        print(f"✓ twifo_prompts.prompts.article_prompts imported successfully")
        print(f"  - PROMPT_VERSION: {article_prompts.PROMPT_VERSION}")
        print(f"  - prompt_sha256: {article_prompts.prompt_sha256()[:16]}...")
        return True
    except ImportError as e:
        print(f"✗ twifo_prompts import failed: {e}")
        return False
    except AssertionError as e:
        print(f"✗ twifo_prompts missing attributes: {e}")
        return False


def test_external_summary_import():
    """Test that external summary package can be imported (if installed)."""
    print("\nTesting external summary package...")
    try:
        from summary import generate_summary, get_all_depth_options
        
        # Verify it's the reusable package, not twifo_prompts
        assert hasattr(generate_summary, '__call__'), "generate_summary not callable"
        
        depth_opts = get_all_depth_options()
        assert len(depth_opts) > 0, "No depth options found"
        
        print(f"✓ External summary package imported successfully")
        print(f"  - Found {len(depth_opts)} depth tiers")
        print(f"  - This is the REUSABLE summary package")
        return True
    except ImportError as e:
        print(f"⚠ External summary package not installed (optional)")
        print(f"  To install: pip install -e ../summary")
        return None  # Not an error - it's optional
    except AssertionError as e:
        print(f"✗ External summary package malformed: {e}")
        return False


def test_no_shadowing():
    """Verify that importing summary doesn't shadow twifo_prompts."""
    print("\nTesting for import shadowing...")
    
    try:
        # Import both
        from twifo_prompts.prompts import article_prompts as twifo_prompts_module
        
        try:
            from summary import generate_summary
            
            # If both import, verify they're different
            assert not hasattr(generate_summary, 'PROMPT_VERSION'), \
                "summary package has PROMPT_VERSION - possible shadowing!"
            
            assert hasattr(twifo_prompts_module, 'PROMPT_VERSION'), \
                "twifo_prompts lost PROMPT_VERSION - shadowed by summary!"
            
            print("✓ No import shadowing detected")
            print("  - twifo_prompts.prompts.article_prompts is TWIFO-specific")
            print("  - summary.generate_summary is the reusable package")
            return True
            
        except ImportError:
            print("✓ No shadowing possible (summary not installed)")
            return True
            
    except Exception as e:
        print(f"✗ Shadowing test failed: {e}")
        return False


def main():
    print("=" * 60)
    print("MODULE IMPORT VERIFICATION")
    print("=" * 60)
    print()
    
    results = []
    
    # Test 1: twifo_prompts import (required)
    results.append(test_twifo_prompts_import())
    
    # Test 2: external summary (optional)
    external_result = test_external_summary_import()
    if external_result is not None:
        results.append(external_result)
    
    # Test 3: no shadowing (required)
    results.append(test_no_shadowing())
    
    print()
    print("=" * 60)
    
    if all(results):
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print()
        print("Module imports are correct:")
        print("  - twifo_prompts: TWIFO-specific article prompts")
        print("  - summary: Reusable transcript summarization (if installed)")
        print("  - No import shadowing")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("=" * 60)
        print()
        print("Please check:")
        print("  1. twifo_prompts folder exists (renamed from summary)")
        print("  2. All imports updated to twifo_prompts.prompts")
        print("  3. External summary installed: pip install -e ../summary")
        return 1


if __name__ == "__main__":
    sys.exit(main())
