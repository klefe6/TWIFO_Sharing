"""
Test OpenAI API key source precedence.
Purpose: Verify .env takes precedence over environment, and no silent overrides.
Author: Kevin Lefebvre
Last Updated: 2026-01-26
"""

import os
import sys
import tempfile
from pathlib import Path


def test_env_file_precedence():
    """Test that .env file takes precedence over process environment."""
    print("\n[TEST 1] .env file precedence over environment")
    
    # Save original environment
    original_key = os.environ.get('OPENAI_API_KEY')
    original_cwd = os.getcwd()
    
    try:
        # Create temporary directory with .env file
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            env_file = tmpdir_path / ".env"
            
            # Write fake key to .env
            env_file.write_text("OPENAI_API_KEY=sk-env-file-key-12345678901234567890\n")
            
            # Set different key in environment
            os.environ['OPENAI_API_KEY'] = "sk-process-env-key-12345678901234567890"
            
            # Change to tmpdir and create fake auth_env.py there
            auth_env_code = (tmpdir_path / "auth_env.py")
            auth_env_code.write_text((Path(__file__).parent / "auth_env.py").read_text())
            
            # Import from tmpdir
            sys.path.insert(0, str(tmpdir_path))
            try:
                if 'auth_env' in sys.modules:
                    del sys.modules['auth_env']
                from auth_env import get_openai_api_key
                
                # Change working directory to tmpdir
                os.chdir(tmpdir_path)
                
                # Get key - should use .env file
                key = get_openai_api_key()
                
                assert key == "sk-env-file-key-12345678901234567890", \
                    f"Expected .env key, got: {key[:20]}..."
                
                print(f"  [PASS] .env file takes precedence over environment")
                print(f"         .env key:     {key[:15]}...")
                print(f"         process key:  sk-process-env...")
                
            finally:
                sys.path.remove(str(tmpdir_path))
                if 'auth_env' in sys.modules:
                    del sys.modules['auth_env']
                
    finally:
        # Restore original
        if original_key:
            os.environ['OPENAI_API_KEY'] = original_key
        else:
            os.environ.pop('OPENAI_API_KEY', None)
        os.chdir(original_cwd)


def test_process_env_fallback():
    """Test that process environment is used when .env is absent."""
    print("\n[TEST 2] Process environment fallback")
    
    # Save original environment
    original_key = os.environ.get('OPENAI_API_KEY')
    original_cwd = os.getcwd()
    
    try:
        # Create temporary directory WITHOUT .env file
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Set key in environment only
            os.environ['OPENAI_API_KEY'] = "sk-process-env-key-12345678901234567890"
            
            # Copy auth_env.py to tmpdir
            auth_env_code = (tmpdir_path / "auth_env.py")
            auth_env_code.write_text((Path(__file__).parent / "auth_env.py").read_text())
            
            # Import from tmpdir
            sys.path.insert(0, str(tmpdir_path))
            try:
                if 'auth_env' in sys.modules:
                    del sys.modules['auth_env']
                from auth_env import get_openai_api_key
                
                # Change working directory to tmpdir
                os.chdir(tmpdir_path)
                
                # Get key - should use environment
                key = get_openai_api_key()
                
                assert key == "sk-process-env-key-12345678901234567890", \
                    f"Expected env key, got: {key[:20]}..."
                
                print(f"  [PASS] Process environment used when .env absent")
                print(f"         key: {key[:15]}...")
                
            finally:
                sys.path.remove(str(tmpdir_path))
                if 'auth_env' in sys.modules:
                    del sys.modules['auth_env']
                
    finally:
        # Restore original
        if original_key:
            os.environ['OPENAI_API_KEY'] = original_key
        else:
            os.environ.pop('OPENAI_API_KEY', None)
        os.chdir(original_cwd)


def test_no_silent_override():
    """Test that once set in os.environ, modules don't override it."""
    print("\n[TEST 3] No silent override after setting os.environ")
    
    # Save original environment
    original_key = os.environ.get('OPENAI_API_KEY')
    
    try:
        # Set key in os.environ (simulating db_filter_autorun.py)
        test_key = "sk-set-by-main-12345678901234567890"
        os.environ['OPENAI_API_KEY'] = test_key
        
        # Import summarize_pdf (which should read from os.environ, not .env)
        if 'summarize_pdf' in sys.modules:
            del sys.modules['summarize_pdf']
        
        # Import and check it uses the key from os.environ
        from summarize_pdf import OPENAI_API_KEY
        
        assert OPENAI_API_KEY == test_key, \
            f"Expected key set in os.environ, but summarize_pdf has: {OPENAI_API_KEY[:20] if OPENAI_API_KEY else '<None>'}..."
        
        print(f"  [PASS] summarize_pdf respects os.environ key")
        print(f"         Expected: {test_key[:15]}...")
        print(f"         Got:      {OPENAI_API_KEY[:15]}...")
        
    finally:
        # Restore original
        if original_key:
            os.environ['OPENAI_API_KEY'] = original_key
        else:
            os.environ.pop('OPENAI_API_KEY', None)
        if 'summarize_pdf' in sys.modules:
            del sys.modules['summarize_pdf']


def test_describe_key():
    """Test that describe_key returns safe truncated string."""
    print("\n[TEST 4] describe_key safety")
    
    from auth_env import describe_key
    
    # Long key
    long_key = "sk-proj-1234567890ABCDEFGHIJKLMNOP"
    desc = describe_key(long_key)
    assert desc == "sk-proj-1234…", f"Expected 'sk-proj-1234…', got: {desc}"
    
    # Short key
    short_key = "sk-12"
    desc = describe_key(short_key)
    assert desc == "sk-1…", f"Expected 'sk-1…', got: {desc}"
    
    # Empty key
    desc = describe_key("")
    assert desc == "<empty>", f"Expected '<empty>', got: {desc}"
    
    print(f"  [PASS] describe_key returns safe strings")
    print(f"         Long key:  {describe_key(long_key)}")
    print(f"         Short key: {describe_key(short_key)}")
    print(f"         Empty key: {describe_key('')}")


def run_all_tests():
    """Run all precedence tests."""
    print("=" * 80)
    print("API KEY SOURCE PRECEDENCE TESTS")
    print("=" * 80)
    
    try:
        test_describe_key()
        test_env_file_precedence()
        test_process_env_fallback()
        test_no_silent_override()
        
        print("\n" + "=" * 80)
        print("ALL TESTS PASSED")
        print("=" * 80)
        print("\nKey source precedence is working correctly:")
        print("- .env file takes precedence over environment")
        print("- Environment is used when .env absent")
        print("- No silent overrides after os.environ is set")
        print("- describe_key returns safe truncated strings")
        
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()
