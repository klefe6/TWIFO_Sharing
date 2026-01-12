"""
Backfill Rollups Script
Purpose: Generate daily rollups for a date range using existing article summaries ONLY
Author: Kevin Lefebvre
Last Updated: 2026-01-11
ZERO-OCR RULE: This script NEVER touches PDFs or uses OCR
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import List

from rollups import load_json, write_json, write_txt, build_daily_rollup, build_weekly_rollup, render_rollup_txt

# Configuration
FILES_DIR = Path(r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE")
ROLLUPS_DIR = FILES_DIR / "rollups"
DAILY_DIR = ROLLUPS_DIR / "daily"
WEEKLY_DIR = ROLLUPS_DIR / "weekly"

def parse_date(s: str) -> dt.date:
    """Parse date from YYYY-MM-DD or YYYYMMDD format."""
    if len(s) == 8 and s.isdigit():
        return dt.datetime.strptime(s, "%Y%m%d").date()
    return dt.datetime.strptime(s, "%Y-%m-%d").date()

def daterange(start: dt.date, end: dt.date):
    """Generate date range."""
    cur = start
    while cur <= end:
        yield cur
        cur += dt.timedelta(days=1)

def find_article_summaries_for_date(export_dir: Path, date_obj: dt.date) -> List[Path]:
    """
    Assumes your per-article naming contains YYYYMMDD in filename:
      *_20260108_*__sum.json
    """
    ymd = date_obj.strftime("%Y%m%d")
    return sorted(export_dir.glob(f"*_{ymd}_*__sum.json"))

def backfill_daily_rollups(start_date: dt.date, end_date: dt.date, min_articles: int = 1, 
                           overwrite: bool = False, dry_run: bool = False) -> dict:
    """
    Generate daily rollups for a date range using existing __sum.json files ONLY.
    ZERO-OCR RULE: Never touches PDFs.
    """
    stats = {"generated": 0, "skipped": 0, "failed": 0}
    
    print(f"[INFO] Backfilling rollups from {start_date} to {end_date}")
    print(f"[INFO] Min articles: {min_articles}, Overwrite: {overwrite}, Dry run: {dry_run}")
    print()
    
    for d in daterange(start_date, end_date):
        date_str = d.strftime("%Y-%m-%d")
        date_yyyymmdd = d.strftime("%Y%m%d")
        
        # Find article summaries for this date
        paths = find_article_summaries_for_date(FILES_DIR, d)
        
        if len(paths) < min_articles:
            print(f"[SKIP] {date_str}: Only {len(paths)} article summaries (<{min_articles})")
            stats["skipped"] += 1
            continue
        
        # Check if rollup already exists
        out_base = DAILY_DIR / f"ROLLUP_DAILY_{date_yyyymmdd}__sum"
        out_json = Path(str(out_base) + ".json")
        
        if out_json.exists() and not overwrite:
            print(f"[SKIP] {date_str}: Rollup already exists (use --overwrite to regenerate)")
            stats["skipped"] += 1
            continue
        
        if dry_run:
            print(f"[DRY-RUN] Would generate rollup for {date_str} from {len(paths)} articles")
            stats["generated"] += 1
            continue
        
        try:
            # Load article summaries
            article_jsons = []
            for p in paths:
                j = load_json(p)
                # record source file for UI linking
                j.setdefault("meta", {})
                j["meta"]["source_file"] = p.name
                article_jsons.append(j)
            
            # Build rollup
            rollup = build_daily_rollup(d, article_jsons, min_articles_required=min_articles)
            
            # Save JSON and TXT explicitly with separate logging
            out_txt = Path(str(out_base) + ".txt")
            write_json(out_json, rollup)
            print(f"[OK] Rollup JSON created: {out_json.name}")
            
            write_txt(out_txt, render_rollup_txt(rollup))
            print(f"[OK] Rollup TXT created:  {out_txt.name}")
            
            # Generate PDF if available
            try:
                from summary_render import render_rollup_pdf
                pdf_path = Path(str(out_base) + ".pdf")
                render_rollup_pdf(out_json, pdf_path, rollup)
                print(f"[OK] Rollup PDF created:  {pdf_path.name}")
            except ImportError:
                print(f"[WARN] PDF module not available, skipping PDF generation")
            except Exception as e:
                print(f"[WARN] PDF generation error: {e}")
            
            stats["generated"] += 1
        except Exception as e:
            print(f"[ERROR] {date_str}: Failed - {e}")
            stats["failed"] += 1
    
    return stats

def backfill_weekly_rollups(start_date: dt.date, end_date: dt.date, min_articles: int = 3,
                             overwrite: bool = False, dry_run: bool = False) -> dict:
    """
    Generate weekly rollups for Mondays in date range.
    Each weekly rollup covers Mon-Fri of that week.
    ZERO-OCR RULE: Never touches PDFs.
    """
    stats = {"generated": 0, "skipped": 0, "failed": 0}
    
    print(f"[INFO] Backfilling weekly rollups from {start_date} to {end_date}")
    print(f"[INFO] Min articles: {min_articles}, Overwrite: {overwrite}, Dry run: {dry_run}")
    print()
    
    # Find all Mondays in the range
    mondays = []
    current = start_date
    while current <= end_date:
        if current.weekday() == 0:  # Monday
            mondays.append(current)
        current += dt.timedelta(days=1)
    
    for monday in mondays:
        friday = monday + dt.timedelta(days=4)
        date_str = f"{monday} to {friday}"
        date_yyyymmdd = monday.strftime("%Y%m%d")
        
        # Collect all article summaries for Mon-Fri
        all_paths = []
        current_date = monday
        while current_date <= friday:
            all_paths.extend(find_article_summaries_for_date(FILES_DIR, current_date))
            current_date += dt.timedelta(days=1)
        
        if len(all_paths) < min_articles:
            print(f"[SKIP] {date_str}: Only {len(all_paths)} article summaries (<{min_articles})")
            stats["skipped"] += 1
            continue
        
        # Check if rollup already exists
        out_base = WEEKLY_DIR / f"ROLLUP_WEEKLY_{date_yyyymmdd}__sum"
        out_json = Path(str(out_base) + ".json")
        
        if out_json.exists() and not overwrite:
            print(f"[SKIP] {date_str}: Rollup already exists (use --overwrite to regenerate)")
            stats["skipped"] += 1
            continue
        
        if dry_run:
            print(f"[DRY-RUN] Would generate weekly rollup for {date_str} from {len(all_paths)} articles")
            stats["generated"] += 1
            continue
        
        try:
            # Load article summaries
            article_jsons = []
            for p in all_paths:
                j = load_json(p)
                j.setdefault("meta", {})
                j["meta"]["source_file"] = p.name
                article_jsons.append(j)
            
            # Build weekly rollup
            rollup = build_weekly_rollup(monday, friday, article_jsons, min_articles_required=min_articles)
            
            # Save JSON and TXT explicitly with separate logging
            out_txt = Path(str(out_base) + ".txt")
            write_json(out_json, rollup)
            print(f"[OK] Rollup JSON created: {out_json.name}")
            
            write_txt(out_txt, render_rollup_txt(rollup))
            print(f"[OK] Rollup TXT created:  {out_txt.name}")
            
            # Generate PDF if available
            try:
                from summary_render import render_rollup_pdf
                pdf_path = Path(str(out_base) + ".pdf")
                render_rollup_pdf(out_json, pdf_path, rollup)
                print(f"[OK] Rollup PDF created:  {pdf_path.name}")
            except ImportError:
                print(f"[WARN] PDF module not available, skipping PDF generation")
            except Exception as e:
                print(f"[WARN] PDF generation error: {e}")
            
            stats["generated"] += 1
        except Exception as e:
            print(f"[ERROR] {date_str}: Failed - {e}")
            stats["failed"] += 1
    
    return stats

def main():
    """Main entry point for backfill script."""
    global FILES_DIR, DAILY_DIR, WEEKLY_DIR
    
    parser = argparse.ArgumentParser(
        description="Backfill daily and weekly rollups for a date range using existing article summaries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backfill daily rollups for last 7 days
  python backfill_rollups.py --start 2026-01-05 --end 2026-01-11
  
  # Backfill weekly rollups for Mondays in range
  python backfill_rollups.py --start 2026-01-05 --end 2026-01-11 --weekly
  
  # Backfill with overwrite
  python backfill_rollups.py --start 2026-01-01 --end 2026-01-31 --overwrite
  
  # Dry run to see what would be generated
  python backfill_rollups.py --start 2026-01-01 --end 2026-01-07 --dry-run
        """
    )
    
    parser.add_argument(
        "--export-dir",
        type=str,
        default=str(FILES_DIR),
        help=f"Folder containing per-article __sum.json (default: {FILES_DIR})"
    )
    
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Start date (YYYY-MM-DD or YYYYMMDD)"
    )
    
    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="End date (YYYY-MM-DD or YYYYMMDD)"
    )
    
    parser.add_argument(
        "--min",
        type=int,
        default=3,
        dest="min_articles",
        help="Minimum articles required per day (default: 3)"
    )
    
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing rollups"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually generating"
    )
    
    parser.add_argument(
        "--weekly",
        action="store_true",
        help="Generate weekly rollups (for Mondays in range) instead of daily"
    )
    
    args = parser.parse_args()
    
    # Parse dates
    try:
        start_date = parse_date(args.start)
        end_date = parse_date(args.end)
    except ValueError as e:
        print(f"[ERROR] Invalid date format: {e}")
        print("Use YYYY-MM-DD or YYYYMMDD format")
        import sys
        sys.exit(1)
    
    if end_date < start_date:
        print("[ERROR] End date must be after start date")
        sys.exit(1)
    
    # Update FILES_DIR if custom export-dir provided
    if args.export_dir:
        FILES_DIR = Path(args.export_dir)
        ROLLUPS_DIR = FILES_DIR / "rollups"
        DAILY_DIR = ROLLUPS_DIR / "daily"
        WEEKLY_DIR = ROLLUPS_DIR / "weekly"
    
    # Ensure directories exist
    if args.weekly:
        WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
        stats = backfill_weekly_rollups(
            start_date=start_date,
            end_date=end_date,
            min_articles=args.min_articles,
            overwrite=args.overwrite,
            dry_run=args.dry_run
        )
    else:
        DAILY_DIR.mkdir(parents=True, exist_ok=True)
        stats = backfill_daily_rollups(
            start_date=start_date,
            end_date=end_date,
            min_articles=args.min_articles,
            overwrite=args.overwrite,
            dry_run=args.dry_run
        )
    
    # Print summary
    print()
    print("=" * 60)
    print("BACKFILL SUMMARY")
    print("=" * 60)
    print(f"Generated: {stats['generated']}")
    print(f"Skipped:   {stats['skipped']}")
    print(f"Failed:    {stats['failed']}")
    print(f"Total:     {stats['generated'] + stats['skipped'] + stats['failed']}")

if __name__ == "__main__":
    main()

