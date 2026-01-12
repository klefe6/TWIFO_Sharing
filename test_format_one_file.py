"""
Test script: Load one existing __sum.json and output reformatted __sum.txt in Egypt-format.
Does NOT touch PDFs or OCR.

Usage:
    python test_format_one_file.py <path_to__sum.json>
"""

import sys
import json
from pathlib import Path

# Import the validator and fixer
from format_validator import validate_article_summary, fix_summary_format
from summarize_pdf import render_sum_txt


def test_format_one_file(json_path: Path):
    """Load, validate, fix, and output reformatted TXT."""
    
    if not json_path.exists():
        print(f"[ERROR] File not found: {json_path}")
        return False
    
    print(f"Loading: {json_path.name}")
    print("=" * 80)
    
    # Load JSON
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON: {e}")
        return False
    
    # Validate
    is_valid, violations = validate_article_summary(summary)
    
    if violations:
        print("\n[VALIDATION] Found issues:")
        for v in violations:
            print(f"  - {v}")
        print()
    else:
        print("\n[VALIDATION] [OK] No issues found\n")
    
    # Fix
    print("[FIX] Applying Egypt-format fixes...")
    fixed_summary = fix_summary_format(summary)
    
    # Re-validate
    is_valid_after, violations_after = validate_article_summary(fixed_summary)
    
    if violations_after:
        print("\n[VALIDATION AFTER FIX] Remaining issues:")
        for v in violations_after:
            print(f"  - {v}")
        print()
    else:
        print("[VALIDATION AFTER FIX] [OK] All issues resolved\n")
    
    # Render TXT
    print("[RENDER] Generating Egypt-format TXT...")
    txt_content = render_sum_txt(fixed_summary)
    
    # Output to console
    print("=" * 80)
    print("REFORMATTED TXT OUTPUT:")
    print("=" * 80)
    print(txt_content)
    print("=" * 80)
    
    # Optionally save to file
    output_path = json_path.parent / f"{json_path.stem}_REFORMATTED.txt"
    output_path.write_text(txt_content, encoding='utf-8')
    print(f"\n[SAVED] {output_path.name}")
    
    return True


def main():
    if len(sys.argv) < 2:
        # Default test file
        default_file = Path(r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\BOA_on USA Weekly spending update through Jan 3_20260108_w__sum.json")
        
        if default_file.exists():
            print(f"Using default test file: {default_file.name}\n")
            test_format_one_file(default_file)
        else:
            print("Usage: python test_format_one_file.py <path_to__sum.json>")
            print(f"\nDefault test file not found: {default_file}")
            sys.exit(1)
    else:
        json_path = Path(sys.argv[1])
        test_format_one_file(json_path)


if __name__ == "__main__":
    main()

