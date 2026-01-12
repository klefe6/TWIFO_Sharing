"""
Weekly Rollup Automation Script
Purpose: Generate weekly rollup every Monday at 12:05am ET (covers previous Mon-Fri)
Author: Kevin Lefebvre
Last Updated: 2026-01-11
ZERO-OCR RULE: This script NEVER touches PDFs or uses OCR
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

from generate_rollup_clean import generate_weekly_rollup, save_weekly_rollup, FILES_DIR

def get_previous_monday_friday() -> tuple[dt.date, dt.date]:
    """
    Compute previous Monday-Friday range based on America/New_York timezone.
    If today is Monday before 12:05am ET, use the week before last.
    Otherwise use last week (Mon-Fri).
    """
    try:
        import pytz
        # Get current time in ET
        et = pytz.timezone('America/New_York')
        now_et = dt.datetime.now(et)
    except ImportError:
        # Fallback to local time if pytz not available
        now_et = dt.datetime.now()
    
    # If it's Monday and before 12:05am ET, use the week before last
    # Otherwise, use last week
    if now_et.weekday() == 0 and (now_et.hour < 0 or (now_et.hour == 0 and now_et.minute < 5)):
        # It's Monday before 12:05am, go back 7 more days
        target_date = now_et.date() - dt.timedelta(days=7)
    else:
        # Use last week
        target_date = now_et.date()
    
    # Find the most recent Monday (going back)
    days_since_monday = target_date.weekday()
    if days_since_monday == 0:
        # It's Monday, use the Monday from last week
        last_monday = target_date - dt.timedelta(days=7)
    else:
        # Go back to last Monday
        last_monday = target_date - dt.timedelta(days=days_since_monday)
    
    # Friday is 4 days after Monday
    last_friday = last_monday + dt.timedelta(days=4)
    
    return last_monday, last_friday

def main():
    """Main entry point for weekly rollup generation."""
    import sys
    import subprocess
    
    print("[INFO] Starting weekly rollup generation...")
    
    # Get previous Mon-Fri range
    start_date, end_date = get_previous_monday_friday()
    
    print(f"[INFO] Computing rollup for week: {start_date} to {end_date}")
    
    # Generate weekly rollup
    rollup = generate_weekly_rollup(start_date, end_date, min_articles=3)
    
    if not rollup:
        print("[WARN] No rollup generated (insufficient articles)")
        return
    
    # Save rollup
    save_weekly_rollup(rollup, start_date, end_date, generate_pdf=True)
    
    print("[OK] Weekly rollup generated successfully")
    
    # Optionally trigger website update bat if it exists
    bat_path = Path(r"C:\Program Files\Coding Projects\TWIFO_Sharing\reboot_twifo.bat")
    if bat_path.exists():
        try:
            print("[INFO] Running website update...")
            subprocess.run([str(bat_path)], shell=True, check=True)
            print("[OK] Website update completed")
        except Exception as e:
            print(f"[WARN] Website update failed: {e}")

if __name__ == "__main__":
    main()

