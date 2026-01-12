"""
Rollup Generator (Wrapper)
Purpose: Generate daily and weekly rollups from article summaries using rollups.py
Author: Kevin Lefebvre
Last Updated: 2026-01-11
ZERO-OCR RULE: This module NEVER touches PDFs or uses OCR
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List
from collections import defaultdict

# Import the core rollup builder
from rollups import (
    build_daily_rollup, build_weekly_rollup, write_json, write_txt, render_rollup_txt,
    load_json as rollup_load_json
)

# Configuration
FILES_DIR = Path(r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE")
ROLLUPS_DIR = FILES_DIR / "rollups"
DAILY_DIR = ROLLUPS_DIR / "daily"
WEEKLY_DIR = ROLLUPS_DIR / "weekly"

# Provider prefix mapping (short codes)
PREFIX_MAP = {
    "BOA_": "BOA", "BA_": "BA", "BR_": "BR", "DB_": "DB", "GM_": "GM",
    "HT_": "HT", "JPM_": "JPM", "MZ_": "MZ", "TSL_": "TSL", "T_": "T",
    "WF_": "WF", "SEB_": "SEB", "R_": "R", "MUFG_": "MUFG", "ANZ_": "ANZ",
    "BCA_": "BCA", "BNPP_": "BNPP", "BNY_": "BNY", "CACIB_": "CACIB",
    "CITI_": "CITI", "HSBC_": "HSBC", "ING_": "ING", "MS_": "MS",
    "NOM_": "NOM", "RBC_": "RBC", "SG_": "SG", "STI_": "STI",
    "TME_": "TME", "UBS_": "UBS", "O_": "O"
}

def detect_provider(fname: str) -> str:
    """Extract provider short code from filename."""
    for prefix, code in PREFIX_MAP.items():
        if fname.startswith(prefix):
            return code
    return "O"

def extract_date_from_filename(fname: str) -> Optional[str]:
    """Extract YYYYMMDD date from filename."""
    match = re.search(r'(\d{8})', fname)
    return match.group(1) if match else None

def parse_date_yyyymmdd(date_str: str) -> date:
    """Parse YYYYMMDD string to date object."""
    return datetime.strptime(date_str, "%Y%m%d").date()

def get_iso_week(date_obj: date) -> tuple[int, int]:
    """Get ISO year and week number."""
    iso = date_obj.isocalendar()
    return iso[0], iso[1]  # year, week

def find_article_summaries_for_date(target_date: date) -> List[Path]:
    """
    Find all article summary JSON files for a specific date.
    Assumes naming: *_YYYYMMDD_*__sum.json
    """
    date_str = target_date.strftime("%Y%m%d")
    return sorted(FILES_DIR.glob(f"*_{date_str}_*__sum.json"))

def collect_daily_articles(target_date: date, min_articles: int = 1) -> List[Dict]:
    """
    Collect all article summaries for a specific date.
    Returns list of summary JSON dicts (not article metadata dicts).
    ZERO-OCR RULE: Only reads from existing JSON files.
    """
    date_str = target_date.strftime("%Y%m%d")
    json_files = find_article_summaries_for_date(target_date)
    
    if len(json_files) < min_articles:
        return []
    
    article_jsons = []
    for json_file in json_files:
        try:
            summary = rollup_load_json(json_file)
            # Ensure meta has source_file for UI linking
            summary.setdefault("meta", {})
            summary["meta"]["source_file"] = json_file.name
            
            # Convert old schema to new if needed
            if "schema_version" not in summary:
                # Legacy schema - try to convert
                summary = _convert_legacy_schema(summary, json_file.name)
            
            article_jsons.append(summary)
        except Exception as e:
            print(f"[WARN] Failed to load {json_file.name}: {e}")
            continue
    
    return article_jsons if len(article_jsons) >= min_articles else []

def _convert_legacy_schema(legacy_summary: dict, filename: str) -> dict:
    """
    Convert old Option B schema to new twifo.sum.v1 schema.
    """
    # Extract provider from filename
    provider = detect_provider(filename)
    
    # Extract date
    date_str = extract_date_from_filename(filename) or ""
    
    # Build new schema
    meta = legacy_summary.get("meta", {})
    scan = legacy_summary.get("scan", {})
    deep_dive = legacy_summary.get("deep_dive", {})
    
    # Convert trade ideas from topic_map
    trade_ideas = []
    topic_map = deep_dive.get("topic_map", [])
    for topic in topic_map:
        trade_implications = topic.get("trade_implications", [])
        if trade_implications:
            # Try to extract structured trade idea
            for impl in trade_implications:
                if isinstance(impl, str):
                    # Simple text - try to parse
                    direction = None
                    if any(w in impl.lower() for w in ["long", "buy", "bullish"]):
                        direction = "long"
                    elif any(w in impl.lower() for w in ["short", "sell", "bearish"]):
                        direction = "short"
                    
                    if direction:
                        trade_ideas.append({
                            "direction": direction,
                            "instrument": topic.get("theme", ""),
                            "setup": topic.get("what_it_means", ""),
                            "trigger": impl,
                            "horizon": "1–3D",  # Default
                            "invalidation": "; ".join(topic.get("risks", [])[:2]),
                            "confidence_0_100": 50,
                            "sources": [provider]
                        })
    
    return {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {
            "title": meta.get("source_pdf", filename).replace("__sum.json", "").replace(".pdf", ""),
            "provider": provider,
            "published_date": date_str,
            "horizon": meta.get("market_framing", {}).get("time_horizon", "u"),
            "products": meta.get("market_framing", {}).get("products", []),
            "generated_at_iso": meta.get("generated_at_iso", ""),
            "model": meta.get("model", "gpt-4o-mini")
        },
        "ui": {
            "header_pills": [
                {"text": provider, "type": "provider"},
                {"text": date_str, "type": "date"},
                {"text": meta.get("market_framing", {}).get("time_horizon", "u"), "type": "horizon"}
            ]
        },
        "extraction": meta.get("extraction", {}),
        "sections": {
            "tldr": [{"text": t, "sources": [provider]} for t in scan.get("tldr", [])],
            "what_occurred": [{"text": t, "sources": [provider]} for t in scan.get("top_actionables", [])[:5]],
            "forward_watch": [{"text": t, "sources": [provider]} for t in scan.get("tips_and_reminders", [])[:5]],
            "trade_ideas": trade_ideas,
            "warnings": [],
            "tips_reminders": [{"text": t, "sources": [provider]} for t in scan.get("tips_and_reminders", [])[5:]],
            "cross_asset_impacts": deep_dive.get("cross_asset_impacts", []),
            "scenarios": deep_dive.get("scenarios", [])
        }
    }

def generate_daily_rollup(target_date: date, min_articles: int = 1) -> Optional[Dict]:
    """
    Generate daily rollup JSON for a specific date using rollups.py module.
    ZERO-OCR RULE: Only reads from existing __sum.json files, never touches PDFs.
    """
    article_jsons = collect_daily_articles(target_date, min_articles)
    
    if not article_jsons:
        print(f"[INFO] Not enough articles for {target_date} (need {min_articles}, found {len(article_jsons)})")
        return None
    
    # Use rollups.py to build the rollup
    try:
        rollup = build_daily_rollup(target_date, article_jsons, min_articles_required=min_articles)
        return rollup
    except ValueError as e:
        print(f"[ERROR] Failed to build rollup: {e}")
        return None

def save_daily_rollup(rollup: Dict, target_date: date, generate_pdf: bool = True) -> Path:
    """
    Save daily rollup to file with proper naming convention.
    Naming: ROLLUP_DAILY_YYYYMMDD__sum.json and ROLLUP_DAILY_YYYYMMDD__sum.txt
    """
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    
    date_yyyymmdd = target_date.strftime("%Y%m%d")
    out_base = DAILY_DIR / f"ROLLUP_DAILY_{date_yyyymmdd}__sum"
    json_path = Path(str(out_base) + ".json")
    txt_path = Path(str(out_base) + ".txt")
    
    # Save JSON and TXT explicitly with separate logging
    write_json(json_path, rollup)
    print(f"[OK] Rollup JSON created: {json_path.name}")
    
    write_txt(txt_path, render_rollup_txt(rollup))
    print(f"[OK] Rollup TXT created:  {txt_path.name}")
    
    # Generate PDF if requested
    if generate_pdf:
        try:
            from summary_render import render_rollup_pdf
            pdf_path = Path(str(out_base) + ".pdf")
            render_rollup_pdf(json_path, pdf_path, rollup)
            print(f"[OK] Rollup PDF created:  {pdf_path.name}")
        except ImportError:
            print(f"[WARN] PDF module not available, skipping PDF generation")
        except Exception as e:
            print(f"[WARN] PDF generation error: {e}")
    
    return json_path

def generate_weekly_rollup(start_date: date, end_date: date, min_articles: int = 3) -> Optional[Dict]:
    """Generate weekly rollup JSON for a date range."""
    # Collect all articles in range
    all_article_jsons = []
    current_date = start_date
    
    while current_date <= end_date:
        articles = collect_daily_articles(current_date, min_articles=1)  # Lower threshold for weekly
        all_article_jsons.extend(articles)
        current_date += timedelta(days=1)
    
    if len(all_article_jsons) < min_articles:
        print(f"[INFO] Not enough articles for week {start_date} to {end_date} (need {min_articles}, found {len(all_article_jsons)})")
        return None
    
    # Use rollups.py to build the weekly rollup
    try:
        rollup = build_weekly_rollup(start_date, end_date, all_article_jsons, min_articles_required=min_articles)
        return rollup
    except ValueError as e:
        print(f"[ERROR] Failed to build weekly rollup: {e}")
        return None

def save_weekly_rollup(rollup: Dict, start_date: date, end_date: date, generate_pdf: bool = True) -> Path:
    """Save weekly rollup to file with proper naming."""
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    
    year = rollup["meta"].get("iso_year")
    week = rollup["meta"].get("iso_week")
    if not year or not week:
        year, week = get_iso_week(start_date)
    
    start_str = start_date.strftime("%Y%m%d")
    out_base = WEEKLY_DIR / f"ROLLUP_WEEKLY_{start_str}__sum"
    json_path = Path(str(out_base) + ".json")
    txt_path = Path(str(out_base) + ".txt")
    
    # Save JSON and TXT explicitly with separate logging
    write_json(json_path, rollup)
    print(f"[OK] Rollup JSON created: {json_path.name}")
    
    write_txt(txt_path, render_rollup_txt(rollup))
    print(f"[OK] Rollup TXT created:  {txt_path.name}")
    
    # Generate PDF if requested
    if generate_pdf:
        try:
            from summary_render import render_rollup_pdf
            pdf_path = Path(str(out_base) + ".pdf")
            render_rollup_pdf(json_path, pdf_path, rollup)
            print(f"[OK] Rollup PDF created:  {pdf_path.name}")
        except ImportError:
            print(f"[WARN] PDF module not available, skipping PDF generation")
        except Exception as e:
            print(f"[WARN] PDF generation error: {e}")
    
    return json_path

def main():
    """Main entry point for rollup generation."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python generate_rollup_clean.py daily YYYY-MM-DD (or YYYYMMDD)")
        print("  python generate_rollup_clean.py daily-range YYYY-MM-DD YYYY-MM-DD  # Generate for date range")
        print("  python generate_rollup_clean.py weekly YYYY-MM-DD [YYYY-MM-DD] (or YYYYMMDD)")
        print("  python generate_rollup_clean.py daily-all  # Generate for all dates with articles")
        print("  python generate_rollup_clean.py weekly-all # Generate for all weeks with articles")
        return
    
    command = sys.argv[1].lower()
    
    if command == "daily":
        if len(sys.argv) < 3:
            print("[ERROR] Please provide date: YYYY-MM-DD or YYYYMMDD")
            return
        
        try:
            date_str = sys.argv[2]
            # Try YYYYMMDD format first (e.g., 20260108)
            if len(date_str) == 8 and date_str.isdigit():
                target_date = datetime.strptime(date_str, "%Y%m%d").date()
            else:
                # Try YYYY-MM-DD format (e.g., 2026-01-08)
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            print("[ERROR] Invalid date format. Use YYYY-MM-DD or YYYYMMDD")
            return
        
        rollup = generate_daily_rollup(target_date)
        if rollup:
            save_daily_rollup(rollup, target_date)
    
    elif command == "daily-range":
        if len(sys.argv) < 4:
            print("[ERROR] Please provide start and end dates: YYYY-MM-DD YYYY-MM-DD (or YYYYMMDD)")
            return
        
        try:
            start_str = sys.argv[2]
            end_str = sys.argv[3]
            
            # Try YYYYMMDD format first
            if len(start_str) == 8 and start_str.isdigit():
                start_date = datetime.strptime(start_str, "%Y%m%d").date()
            else:
                start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            
            if len(end_str) == 8 and end_str.isdigit():
                end_date = datetime.strptime(end_str, "%Y%m%d").date()
            else:
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
        except ValueError:
            print("[ERROR] Invalid date format. Use YYYY-MM-DD or YYYYMMDD")
            return
        
        if end_date < start_date:
            print("[ERROR] End date must be after start date")
            return
        
        # Process each date in the range
        current_date = start_date
        generated = 0
        skipped = 0
        failed = 0
        
        print(f"[INFO] Generating daily rollups from {start_date} to {end_date}")
        print()
        
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            print(f"[INFO] Processing {date_str}...")
            
            rollup = generate_daily_rollup(current_date, min_articles=1)
            if rollup:
                try:
                    save_daily_rollup(rollup, current_date)
                    generated += 1
                    print(f"[OK] {date_str}: Generated successfully\n")
                except Exception as e:
                    print(f"[ERROR] {date_str}: Failed to save - {e}\n")
                    failed += 1
            else:
                skipped += 1
                print(f"[SKIP] {date_str}: Not enough articles or generation failed\n")
            
            current_date += timedelta(days=1)
        
        print(f"[SUMMARY] Generated: {generated}, Skipped: {skipped}, Failed: {failed}")
    
    elif command == "weekly":
        if len(sys.argv) < 3:
            print("[ERROR] Please provide start date: YYYY-MM-DD or YYYYMMDD")
            return
        
        try:
            start_str = sys.argv[2]
            # Try YYYYMMDD format first
            if len(start_str) == 8 and start_str.isdigit():
                start_date = datetime.strptime(start_str, "%Y%m%d").date()
            else:
                start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            
            if len(sys.argv) >= 4:
                end_str = sys.argv[3]
                # Try YYYYMMDD format first
                if len(end_str) == 8 and end_str.isdigit():
                    end_date = datetime.strptime(end_str, "%Y%m%d").date()
                else:
                    end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            else:
                # Default to start_date + 6 days (7 days total: selected date through selected date + 6)
                end_date = start_date + timedelta(days=6)
        except ValueError:
            print("[ERROR] Invalid date format. Use YYYY-MM-DD or YYYYMMDD")
            return
        
        rollup = generate_weekly_rollup(start_date, end_date)
        if rollup:
            save_weekly_rollup(rollup, start_date, end_date)
    
    elif command == "daily-all":
        # Find all unique dates with summaries
        dates = set()
        for json_file in FILES_DIR.glob("*__sum.json"):
            date_str = extract_date_from_filename(json_file.name)
            if date_str:
                dates.add(parse_date_yyyymmdd(date_str))
        
        for target_date in sorted(dates, reverse=True):
            rollup = generate_daily_rollup(target_date)
            if rollup:
                save_daily_rollup(rollup, target_date)
    
    elif command == "weekly-all":
        # Group dates by ISO week
        week_groups = defaultdict(list)
        for json_file in FILES_DIR.glob("*__sum.json"):
            date_str = extract_date_from_filename(json_file.name)
            if date_str:
                d = parse_date_yyyymmdd(date_str)
                year, week = get_iso_week(d)
                week_groups[(year, week)].append(d)
        
        for (year, week), dates in week_groups.items():
            start_date = min(dates)
            end_date = max(dates)
            rollup = generate_weekly_rollup(start_date, end_date)
            if rollup:
                save_weekly_rollup(rollup, start_date, end_date)
    
    else:
        print(f"[ERROR] Unknown command: {command}")

if __name__ == "__main__":
    main()

