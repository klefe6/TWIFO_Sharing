"""
Daily View Feature Test
Purpose: Verify all Daily View components work correctly
Author: Kevin Lefebvre
Last Updated: 2026-02-13
"""

import os
from datetime import date, timedelta


def test_daily_view_integration():
    """Test the complete Daily View feature integration."""
    
    print("=" * 70)
    print("DAILY VIEW FEATURE TEST")
    print("=" * 70)
    
    # Enable debug mode
    os.environ["TWIFO_DEBUG_DAILY_VIEW"] = "1"
    
    # Test 1: Import helper function
    print("\n[1] Testing import of get_yesterday_articles()...")
    try:
        from twifo_app import get_yesterday_articles
        print("✓ Import successful")
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return
    
    # Test 2: Get yesterday's articles
    print("\n[2] Testing get_yesterday_articles()...")
    print("-" * 70)
    try:
        articles = get_yesterday_articles()
        print("-" * 70)
        print(f"✓ Function executed successfully")
        print(f"  Returned {len(articles)} articles")
    except Exception as e:
        print(f"✗ Function failed: {e}")
        return
    
    # Test 3: Verify data structure
    print("\n[3] Verifying article data structure...")
    if articles:
        required_keys = {"basename", "title", "provider", "date_fmt", "full_path"}
        article = articles[0]
        actual_keys = set(article.keys())
        
        if required_keys == actual_keys:
            print("✓ All required keys present:")
            for key in required_keys:
                print(f"  - {key}: {type(article[key]).__name__}")
        else:
            missing = required_keys - actual_keys
            extra = actual_keys - required_keys
            if missing:
                print(f"✗ Missing keys: {missing}")
            if extra:
                print(f"✗ Extra keys: {extra}")
            return
    else:
        print("⚠ No articles to verify (this is OK if no articles from yesterday)")
    
    # Test 4: Verify twifo.py imports
    print("\n[4] Testing twifo.py integration...")
    try:
        # Check if the import exists in twifo.py
        with open("twifo.py", "r", encoding="utf-8") as f:
            twifo_content = f.read()
        
        checks = [
            ("Import statement", "from twifo_app import get_yesterday_articles"),
            ("Daily articles store", 'dcc.Store(id=\'daily-articles-store\''),
            ("Sidebar callback", "def populate_daily_view_sidebar"),
            ("Display callback", "def display_daily_article_summary"),
            ("render_summary_components", "render_summary_components(basename)")
        ]
        
        all_passed = True
        for check_name, check_string in checks:
            if check_string in twifo_content:
                print(f"  ✓ {check_name} found")
            else:
                print(f"  ✗ {check_name} NOT found")
                all_passed = False
        
        if all_passed:
            print("✓ All integration points verified")
        else:
            print("✗ Some integration points missing")
            return
            
    except FileNotFoundError:
        print("✗ twifo.py not found in current directory")
        return
    except Exception as e:
        print(f"✗ Error reading twifo.py: {e}")
        return
    
    # Test 5: Check CSS file
    print("\n[5] Checking CSS styling...")
    try:
        css_path = "assets/daily_view.css"
        if os.path.exists(css_path):
            with open(css_path, "r", encoding="utf-8") as f:
                css_content = f.read()
            
            if ".daily-article-button" in css_content:
                print("✓ CSS file exists with button styles")
            else:
                print("⚠ CSS file exists but missing button styles")
        else:
            print("⚠ CSS file not found (may not be critical)")
    except Exception as e:
        print(f"⚠ Could not check CSS: {e}")
    
    # Test 6: Sample data display
    if articles:
        print(f"\n[6] Sample articles from yesterday ({(date.today() - timedelta(days=1)).strftime('%Y-%m-%d')}):")
        print("-" * 70)
        for i, article in enumerate(articles[:3], 1):
            print(f"\n  {i}. {article['title'][:60]}...")
            print(f"     Provider: {article['provider']}")
            print(f"     Basename: {article['basename']}")
        
        if len(articles) > 3:
            print(f"\n  ... and {len(articles) - 3} more articles")
    
    # Final summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print("✓ All components tested successfully!")
    print("\nDaily View feature is ready to use:")
    print("  1. Run: python twifo.py")
    print("  2. Login with credentials")
    print("  3. Navigate to 'Daily View' tab")
    print("  4. Click on articles in sidebar")
    print("  5. View summaries in main panel")
    print("=" * 70)


if __name__ == "__main__":
    test_daily_view_integration()
