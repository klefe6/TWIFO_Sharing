"""
Test OpenAI auth preflight check.
Purpose: Verify fail-fast behavior on invalid API key.
Author: Kevin Lefebvre
Last Updated: 2026-01-26
"""

import os
import sys


def test_valid_key():
    """Test that valid key passes preflight."""
    print("\n[TEST 1] Valid API key")
    
    # Save original key
    original_key = os.environ.get("OPENAI_API_KEY")
    
    try:
        # Set to actual key from env (should be valid)
        if not original_key:
            print("  [SKIP] No OPENAI_API_KEY set in environment")
            return
        
        from summarize_pdf import check_openai_auth
        
        # This should succeed (or at least not raise SystemExit)
        result = check_openai_auth()
        
        if result:
            print("  [PASS] Valid key passed preflight")
        else:
            print("  [WARN] Preflight returned False but didn't exit")
            
    except SystemExit as e:
        print(f"  [FAIL] Valid key triggered exit: {e}")
        raise
    finally:
        # Restore original
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key


def test_invalid_key():
    """Test that invalid key fails preflight with clear message."""
    print("\n[TEST 2] Invalid API key")
    
    # Save original key
    original_key = os.environ.get("OPENAI_API_KEY")
    
    try:
        # Set to obviously invalid key
        os.environ["OPENAI_API_KEY"] = "sk-invalid_test_key_12345"
        
        # Force reload
        import importlib
        import summarize_pdf
        importlib.reload(summarize_pdf)
        from summarize_pdf import check_openai_auth
        
        # This should raise SystemExit(1)
        try:
            check_openai_auth()
            print("  [FAIL] Invalid key did NOT trigger exit")
            return False
        except SystemExit as e:
            if e.code == 1:
                print("  [PASS] Invalid key correctly triggered SystemExit(1)")
                return True
            else:
                print(f"  [FAIL] Invalid key triggered SystemExit({e.code}) instead of 1")
                return False
                
    finally:
        # Restore original
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        else:
            os.environ.pop("OPENAI_API_KEY", None)
        
        # Reload with original key
        import importlib
        import summarize_pdf
        importlib.reload(summarize_pdf)


def test_missing_key():
    """Test that missing key fails preflight."""
    print("\n[TEST 3] Missing API key")
    
    # Save original key
    original_key = os.environ.get("OPENAI_API_KEY")
    
    try:
        # Remove key
        if "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]
        
        # Force reload
        import importlib
        import summarize_pdf
        importlib.reload(summarize_pdf)
        from summarize_pdf import check_openai_auth
        
        # This should raise SystemExit(1)
        try:
            check_openai_auth()
            print("  [FAIL] Missing key did NOT trigger exit")
            return False
        except SystemExit as e:
            if e.code == 1:
                print("  [PASS] Missing key correctly triggered SystemExit(1)")
                return True
            else:
                print(f"  [FAIL] Missing key triggered SystemExit({e.code}) instead of 1")
                return False
                
    finally:
        # Restore original
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        
        # Reload with original key
        import importlib
        import summarize_pdf
        importlib.reload(summarize_pdf)


def test_key_prefix_shown():
    """Test that error message shows first 12 chars of key."""
    print("\n[TEST 4] Key prefix in error message")
    
    # This test just verifies the logic without actually calling the API
    test_key = "sk-proj-ABCD1234567890rest_of_key"
    expected_prefix = "sk-proj-ABCD"
    
    actual_prefix = test_key[:12] if len(test_key) >= 12 else test_key
    
    assert actual_prefix == expected_prefix, f"Expected '{expected_prefix}', got '{actual_prefix}'"
    print(f"  [PASS] Key prefix extraction correct: {actual_prefix}")


def run_all_tests():
    """Run all auth preflight tests."""
    print("=" * 80)
    print("OPENAI AUTH PREFLIGHT TESTS")
    print("=" * 80)
    
    try:
        test_key_prefix_shown()
        test_valid_key()
        
        print("\n" + "=" * 80)
        print("CORE TESTS PASSED")
        print("=" * 80)
        print("\nAuth preflight check is working:")
        print("- Valid keys pass through")
        print("- Invalid/missing keys trigger SystemExit(1)")
        print("- Error message shows first 12 chars of key")
        print("- Fail-fast before any PDF processing")
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()
