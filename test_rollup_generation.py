"""
Test Rollup Generation
Purpose: Load a few __sum.json files and print the produced rollup JSON
Author: Kevin Lefebvre
Last Updated: 2026-01-11
"""

import json
from pathlib import Path
from datetime import date
from generate_rollup_clean import (
    FILES_DIR, generate_daily_rollup, load_summary_json, detect_provider
)

def test_rollup_for_date(target_date: date):
    """Test rollup generation for a specific date."""
    print(f"\n{'='*60}")
    print(f"Testing rollup generation for {target_date}")
    print(f"{'='*60}\n")
    
    # Find summary files for this date
    date_yyyymmdd = target_date.strftime("%Y%m%d")
    summary_files = list(FILES_DIR.glob(f"*{date_yyyymmdd}*__sum.json"))
    
    print(f"Found {len(summary_files)} summary files:")
    for sf in summary_files[:5]:  # Show first 5
        print(f"  - {sf.name}")
    if len(summary_files) > 5:
        print(f"  ... and {len(summary_files) - 5} more")
    print()
    
    # Generate rollup
    rollup = generate_daily_rollup(target_date, min_articles=1)  # Lower threshold for testing
    
    if not rollup:
        print("[ERROR] Failed to generate rollup")
        return None
    
    # Print rollup structure
    print("Rollup Structure:")
    print(f"  Meta:")
    print(f"    Date: {rollup['meta']['date']}")
    print(f"    Articles: {rollup['meta']['article_count']}")
    print(f"    Providers: {rollup['meta']['providers_included']}")
    print(f"    Products: {rollup['meta']['products_mentioned']}")
    print()
    
    print(f"  UI:")
    print(f"    Title: {rollup['ui']['title']}")
    print(f"    Chips Rows: {len(rollup['ui']['chips_rows'])} rows")
    for i, row in enumerate(rollup['ui']['chips_rows'], 1):
        print(f"      Row {i}: {len(row)} chips")
    print()
    
    print(f"  Sections:")
    print(f"    Categories: {list(rollup['sections']['by_category'].keys())}")
    print(f"    Watchlist items: {len(rollup['sections']['watchlist'])}")
    print()
    
    # Print category details
    for category, cat_data in rollup['sections']['by_category'].items():
        print(f"  {category.upper()}:")
        print(f"    Observations: {len(cat_data.get('observations', []))}")
        print(f"    What to Expect: {len(cat_data.get('what_to_expect', []))}")
        trade_ideas = cat_data.get('trade_ideas', {})
        print(f"    Trade Ideas:")
        print(f"      Tactical (0-3D): {len(trade_ideas.get('tactical_0_3d', []))}")
        print(f"      Swing (1-2W): {len(trade_ideas.get('swing_1_2w', []))}")
        print(f"      Position (2W+): {len(trade_ideas.get('position_2w_plus', []))}")
        
        # Show sample trade ideas
        for time_horizon in ['tactical_0_3d', 'swing_1_2w', 'position_2w_plus']:
            ideas = trade_ideas.get(time_horizon, [])
            if ideas:
                print(f"\n      Sample {time_horizon} trade idea:")
                idea = ideas[0]
                print(f"        Idea: {idea.get('idea', 'N/A')}")
                print(f"        Direction: {idea.get('direction', 'N/A')}")
                print(f"        Instrument: {idea.get('instrument', 'N/A')}")
                print(f"        Trigger: {idea.get('trigger', 'N/A')}")
                print(f"        Time Horizon: {idea.get('time_horizon', 'N/A')}")
        print()
    
    # Save to file for inspection
    output_file = Path(f"test_rollup_{date_yyyymmdd}.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(rollup, f, indent=2, ensure_ascii=False)
    print(f"[OK] Rollup JSON saved to {output_file}")
    
    return rollup

if __name__ == "__main__":
    from datetime import datetime
    
    # Test with today's date
    today = date.today()
    test_rollup_for_date(today)
    
    # Or test with a specific date
    # test_date = datetime.strptime("20260108", "%Y%m%d").date()
    # test_rollup_for_date(test_date)

