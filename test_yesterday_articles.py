"""
Test script for get_yesterday_articles() function
Purpose: Verify the helper function works correctly
Author: Kevin Lefebvre
Last Updated: 2026-02-13
"""

import os
from twifo_app import get_yesterday_articles


def test_get_yesterday_articles():
    """Test the get_yesterday_articles function with debug output."""
    # Enable debug logging
    os.environ["TWIFO_DEBUG_DAILY_VIEW"] = "1"
    
    print("Testing get_yesterday_articles()...")
    print("-" * 60)
    
    articles = get_yesterday_articles()
    
    print("-" * 60)
    print(f"\nReturned {len(articles)} articles")
    
    if articles:
        print("\nFirst 3 articles:")
        for i, article in enumerate(articles[:3], 1):
            print(f"\n{i}. {article['title']}")
            print(f"   Provider: {article['provider']}")
            print(f"   Date: {article['date_fmt']}")
            print(f"   Basename: {article['basename']}")
            print(f"   Path: {article['full_path'][:80]}...")
    else:
        print("\nNo articles found for yesterday.")
        print("This is normal if no articles were processed yesterday.")
    
    # Verify structure
    if articles:
        required_keys = {"basename", "title", "provider", "date_fmt", "full_path"}
        actual_keys = set(articles[0].keys())
        assert required_keys == actual_keys, f"Missing keys: {required_keys - actual_keys}"
        print("\n✓ All required keys present in returned dicts")
    
    print("\n✓ Test passed!")


if __name__ == "__main__":
    test_get_yesterday_articles()
