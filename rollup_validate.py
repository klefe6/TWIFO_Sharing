"""
Rollup Validation Script
Purpose: Validate rollup JSON files against schema
Author: Kevin Lefebvre
Last Updated: 2026-01-11
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

def validate_rollup(rollup: Dict[str, Any]) -> tuple[bool, List[str]]:
    """
    Validate rollup JSON against schema.
    Returns (is_valid, list_of_errors).
    """
    errors = []
    
    # Check top-level fields
    if "schema_version" not in rollup:
        errors.append("Missing 'schema_version'")
    elif rollup["schema_version"] != "twifo.rollup.v1":
        errors.append(f"Invalid schema_version: {rollup['schema_version']}")
    
    if "kind" not in rollup:
        errors.append("Missing 'kind'")
    elif rollup["kind"] != "rollup":
        errors.append(f"Invalid kind: {rollup['kind']}")
    
    # Check meta
    if "meta" not in rollup:
        errors.append("Missing 'meta'")
        return False, errors
    
    meta = rollup["meta"]
    required_meta = ["rollup_kind", "date", "article_count", "providers", "products"]
    for field in required_meta:
        if field not in meta:
            errors.append(f"Missing meta.{field}")
    
    rollup_kind = meta.get("rollup_kind")
    if rollup_kind not in ["daily", "weekly"]:
        errors.append(f"Invalid meta.rollup_kind: {rollup_kind}")
    
    if rollup_kind == "weekly":
        required_weekly = ["start_date", "end_date", "week_range", "iso_year", "iso_week"]
        for field in required_weekly:
            if field not in meta:
                errors.append(f"Missing meta.{field} for weekly rollup")
    
    # Check ui
    if "ui" not in rollup:
        errors.append("Missing 'ui'")
        return False, errors
    
    ui = rollup["ui"]
    if "title" not in ui:
        errors.append("Missing ui.title")
    if "header_pills" not in ui:
        errors.append("Missing ui.header_pills")
    if "chips_rows" not in ui:
        errors.append("Missing ui.chips_rows")
    
    # Check sections
    if "sections" not in rollup:
        errors.append("Missing 'sections'")
        return False, errors
    
    sections = rollup["sections"]
    required_sections = ["tldr", "observations", "forward_watch", "trade_ideas", "warnings", "tips_reminders", "cross_asset_impacts", "scenarios", "sources"]
    for section in required_sections:
        if section not in sections:
            errors.append(f"Missing sections.{section}")
    
    # Check trade_ideas structure
    trade_ideas = sections.get("trade_ideas", {})
    if not isinstance(trade_ideas, dict):
        errors.append("sections.trade_ideas must be a dict")
    else:
        required_buckets = ["d_1_3", "w_1_2", "gt_2w", "watchlist_only"]
        for bucket in required_buckets:
            if bucket not in trade_ideas:
                errors.append(f"Missing sections.trade_ideas.{bucket}")
            elif not isinstance(trade_ideas[bucket], list):
                errors.append(f"sections.trade_ideas.{bucket} must be a list")
    
    # Validate trade idea structure (sample first one if exists)
    for bucket in required_buckets:
        ideas = trade_ideas.get(bucket, [])
        if ideas and len(ideas) > 0:
            idea = ideas[0]
            required_fields = ["direction", "instrument", "trigger"]
            for field in required_fields:
                if field not in idea:
                    errors.append(f"Trade idea in {bucket} missing {field}")
                    break  # Only report once
    
    return len(errors) == 0, errors

def validate_file(json_path: Path) -> tuple[bool, List[str]]:
    """Validate a rollup JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            rollup = json.load(f)
        return validate_rollup(rollup)
    except json.JSONDecodeError as e:
        return False, [f"JSON decode error: {e}"]
    except Exception as e:
        return False, [f"Error reading file: {e}"]

def main():
    """Main entry point for validation."""
    if len(sys.argv) < 2:
        print("Usage: python rollup_validate.py <rollup_json_file>")
        print("       python rollup_validate.py --dir <directory>")
        sys.exit(1)
    
    if sys.argv[1] == "--dir":
        if len(sys.argv) < 3:
            print("[ERROR] --dir requires directory path")
            sys.exit(1)
        dir_path = Path(sys.argv[2])
        if not dir_path.is_dir():
            print(f"[ERROR] Not a directory: {dir_path}")
            sys.exit(1)
        
        # Find all rollup JSON files
        json_files = list(dir_path.glob("ROLLUP_*.json"))
        if not json_files:
            print(f"[WARN] No rollup JSON files found in {dir_path}")
            sys.exit(0)
        
        print(f"[INFO] Validating {len(json_files)} rollup file(s)...\n")
        all_valid = True
        for json_file in sorted(json_files):
            is_valid, errors = validate_file(json_file)
            status = "✓" if is_valid else "✗"
            print(f"{status} {json_file.name}")
            if not is_valid:
                all_valid = False
                for error in errors:
                    print(f"    - {error}")
        
        if all_valid:
            print("\n[OK] All rollups are valid")
            sys.exit(0)
        else:
            print("\n[ERROR] Some rollups have validation errors")
            sys.exit(1)
    else:
        json_path = Path(sys.argv[1])
        if not json_path.exists():
            print(f"[ERROR] File not found: {json_path}")
            sys.exit(1)
        
        is_valid, errors = validate_file(json_path)
        if is_valid:
            print(f"[OK] {json_path.name} is valid")
            sys.exit(0)
        else:
            print(f"[ERROR] {json_path.name} has validation errors:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)

if __name__ == "__main__":
    main()

