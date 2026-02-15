"""
Test script for rollup upgrade validation.
Tests the upgraded daily rollup with asset-class grouping and new sections.
"""
import sys
from pathlib import Path
from datetime import date
from generate_rollup_clean import generate_daily_rollup, ROLLUPS_DIR, DAILY_DIR

def test_rollup_upgrade(target_date_str: str = "2026-01-04"):
    """
    Generate a daily rollup and validate the upgrade features.
    
    Args:
        target_date_str: Date in YYYY-MM-DD format
    """
    target_date = date.fromisoformat(target_date_str)
    
    print(f"[TEST] Generating daily rollup for {target_date_str}")
    
    try:
        rollup_data = generate_daily_rollup(target_date, min_articles=1, use_llm=False)
        
        if not rollup_data:
            print("[FAIL] No rollup generated (not enough articles)")
            return False
        
        # Validation checks
        sections = rollup_data.get("sections", {})
        
        # Check 1: warnings is first key
        section_keys = list(sections.keys())
        if section_keys[0] != "warnings":
            print(f"[FAIL] warnings not first key. First key: {section_keys[0]}")
            return False
        print(f"[PASS] warnings is first section key")
        
        # Check 2: executive_snapshot exists
        if "executive_snapshot" not in sections:
            print("[FAIL] executive_snapshot section missing")
            return False
        exec_snap = sections["executive_snapshot"]
        if not isinstance(exec_snap, list) or len(exec_snap) > 5:
            print(f"[FAIL] executive_snapshot invalid: {len(exec_snap)} items")
            return False
        print(f"[PASS] executive_snapshot present with {len(exec_snap)} items (<=5)")
        
        # Check 3: observations and forward_watch are asset-class-keyed dicts
        for key in ["observations", "forward_watch"]:
            section = sections.get(key, {})
            if not isinstance(section, dict):
                print(f"[FAIL] {key} is not a dict")
                return False
            # Check if keys are asset classes, not product codes
            for sk in section.keys():
                if sk in ["ES", "GC", "CL", "ZN"]:  # Old product codes
                    print(f"[FAIL] {key} has product code '{sk}' instead of asset class")
                    return False
            print(f"[PASS] {key} is asset-class-keyed: {list(section.keys())}")
        
        # Check 4: volatility_by_asset_class exists
        if "volatility_by_asset_class" not in sections:
            print("[FAIL] volatility_by_asset_class section missing")
            return False
        vol_ac = sections["volatility_by_asset_class"]
        if not isinstance(vol_ac, dict):
            print("[FAIL] volatility_by_asset_class is not a dict")
            return False
        # Check structure
        for ac, data in vol_ac.items():
            if "expected_volatility" not in data or "confidence_score" not in data:
                print(f"[FAIL] volatility_by_asset_class[{ac}] missing required fields")
                return False
        print(f"[PASS] volatility_by_asset_class present with {len(vol_ac)} asset classes")
        
        # Check 5: Section order
        expected_early = ["warnings", "executive_snapshot", "tldr", "observations", "forward_watch", "volatility_by_asset_class"]
        for i, key in enumerate(expected_early):
            if i >= len(section_keys):
                break
            if section_keys[i] != key:
                print(f"[FAIL] Section order wrong at position {i}: expected {key}, got {section_keys[i]}")
                return False
        print(f"[PASS] Section order correct: {section_keys[:6]}")
        
        # Check 6: Schema version unchanged
        if rollup_data.get("schema_version") != "twifo.rollup.v1":
            print(f"[FAIL] schema_version changed: {rollup_data.get('schema_version')}")
            return False
        print(f"[PASS] schema_version is twifo.rollup.v1")
        
        # Check 7: Trade ideas don't have suppressed equity tickers
        trade_ideas = sections.get("trade_ideas", [])
        suppressed_found = False
        # Quick check: CSX, WERN, ODFL are examples of non-allowed tickers
        for idea in trade_ideas:
            product = idea.get("product", "")
            if product in ["CSX", "WERN", "ODFL", "UNP", "JBHT"]:
                print(f"[FAIL] Suppressed equity ticker found in trade_ideas: {product}")
                suppressed_found = True
        if not suppressed_found:
            print(f"[PASS] No suppressed equity tickers in trade_ideas")
        
        print("\n[SUCCESS] All validation checks passed!")
        print(f"\nSections present: {list(sections.keys())}")
        print(f"\nAsset classes in observations: {list(sections.get('observations', {}).keys())}")
        print(f"Asset classes in forward_watch: {list(sections.get('forward_watch', {}).keys())}")
        print(f"Asset classes in volatility: {list(vol_ac.keys())}")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Exception during test: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "2026-01-04"
    success = test_rollup_upgrade(target)
    sys.exit(0 if success else 1)
