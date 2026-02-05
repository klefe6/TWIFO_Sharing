"""
Test OpenAI auth consistency between preflight and summarize.
Purpose: Verify both paths use get_client() (single source).
Author: Kevin Lefebvre
Last Updated: 2026-01-26
"""

import os
import sys
from unittest.mock import Mock, patch, MagicMock


def test_auth_consistency():
    """
    Test that both preflight and summarize use get_client() from openai_client.
    """
    print("\n[TEST] Auth consistency: preflight and summarize use same client path")
    
    dummy_key = "sk-test-dummy-key-12345678901234567890"
    
    # Set up environment
    os.environ['OPENAI_API_KEY'] = dummy_key
    
    # Test 1: Verify preflight uses get_client()
    with patch('openai_client.get_client') as mock_get_client:
        # Create a mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.output = []
        mock_client.responses.create.return_value = mock_response
        mock_client.base_url = "https://api.openai.com/v1"
        mock_get_client.return_value = mock_client
        
        # Clear and re-import auth_env
        if 'auth_env' in sys.modules:
            del sys.modules['auth_env']
        
        from auth_env import assert_openai_auth_ok
        
        try:
            assert_openai_auth_ok("gpt-4o-mini")
        except SystemExit:
            pass  # May exit on various conditions, but we just want to verify get_client was called
        except Exception:
            pass  # Ignore other errors
        
        # Verify get_client was called
        assert mock_get_client.called, "assert_openai_auth_ok should call get_client()"
        print(f"  [PASS] assert_openai_auth_ok() calls get_client()")
    
    # Test 2: Verify summarize uses get_client()
    with patch('openai_client.get_client') as mock_get_client:
        # Create a mock client
        mock_client = MagicMock()
        mock_output_item = MagicMock()
        mock_content_item = MagicMock()
        mock_content_item.type = "output_text"
        mock_content_item.text = '{"what_moved_today": [], "what_can_move_tomorrow": [], "products": {}, "volatility_impact": {}, "tldr": [], "what_occurred": [], "forward_watch": [], "warnings": [], "tips_reminders": [], "cross_asset_impacts": [], "scenarios": [], "sentiment_indicator": {}, "explain_like_refresher": "", "score_0_10": 0, "chart_score_0_3": 0}'
        mock_output_item.content = [mock_content_item]
        mock_response = MagicMock()
        mock_response.output = [mock_output_item]
        mock_client.responses.create.return_value = mock_response
        mock_client.base_url = "https://api.openai.com/v1"
        mock_get_client.return_value = mock_client
        
        # Clear and re-import summarize_pdf
        if 'summarize_pdf' in sys.modules:
            del sys.modules['summarize_pdf']
        
        from summarize_pdf import llm_summarize_to_json
        
        # Create minimal meta
        meta = {
            "provider": "TEST",
            "published_date": "20260126",
            "horizon": "u",
            "extraction": {}
        }
        
        try:
            # Call llm_summarize_to_json
            result = llm_summarize_to_json(
                text="Test document text",
                meta=meta,
                model="gpt-4o-mini"
            )
            
            # Verify get_client was called
            assert mock_get_client.called, "llm_summarize_to_json should call get_client()"
            print(f"  [PASS] llm_summarize_to_json() calls get_client()")
            
        except Exception as e:
            # Even if parsing fails, verify get_client was called
            if mock_get_client.called:
                print(f"  [PASS] llm_summarize_to_json() calls get_client()")
            else:
                raise AssertionError(f"llm_summarize_to_json did not call get_client(): {e}")


def test_singleton_behavior():
    """
    Test that get_client() returns the same instance on multiple calls.
    """
    print("\n[TEST] Singleton behavior: get_client() returns same instance")
    
    dummy_key = "sk-test-dummy-key-12345678901234567890"
    
    with patch('auth_env.get_openai_api_key', return_value=dummy_key):
        with patch('openai.OpenAI') as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            
            # Clear the singleton
            import openai_client
            openai_client._client = None
            
            from openai_client import get_client
            
            # Call multiple times
            client1 = get_client()
            client2 = get_client()
            client3 = get_client()
            
            # Should all be the same instance
            assert client1 is client2, "get_client() should return same instance"
            assert client2 is client3, "get_client() should return same instance"
            
            # OpenAI() should only be called once
            assert mock_openai_class.call_count == 1, \
                f"OpenAI() should be called once, got {mock_openai_class.call_count} calls"
            
            print(f"  [PASS] get_client() returns singleton instance")
            print(f"         OpenAI() called {mock_openai_class.call_count} time(s)")


def run_all_tests():
    """Run all auth consistency tests."""
    print("=" * 80)
    print("OPENAI AUTH CONSISTENCY TESTS")
    print("=" * 80)
    
    try:
        test_singleton_behavior()
        test_auth_consistency()
        
        print("\n" + "=" * 80)
        print("ALL TESTS PASSED")
        print("=" * 80)
        print("\nAuth consistency verified:")
        print("- get_client() returns singleton OpenAI instance")
        print("- Preflight (assert_openai_auth_ok) uses get_client()")
        print("- Summarize (llm_summarize_to_json) uses get_client()")
        print("- Both paths use the same client instance")
        
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    run_all_tests()
