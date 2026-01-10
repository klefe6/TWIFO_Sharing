"""
Verify Summary Generation - Test Script

This script helps verify that summary generation worked correctly by:
1. Checking if summary files exist for PDFs
2. Validating JSON structure
3. Displaying summary contents
4. Checking required fields
"""

import json
import os
from pathlib import Path

FILES_DIR = Path(
    r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE"
)

REQUIRED_FIELDS = [
    "overall_bias",
    "products",
    "per_product",
    "tldr",
    "actionable",
    "time_horizon"
]


def verify_summary_file(pdf_path: Path) -> tuple[bool, dict]:
    """
    Verify a summary file exists and is valid.
    Returns: (is_valid: bool, summary_data: dict or error_message: str)
    """
    # Expected summary filename: originalname__sum.json or originalname.summary.json
    base_name = pdf_path.stem
    summary_json = pdf_path.parent / f"{base_name}.summary.json"
    summary_sum = pdf_path.parent / f"{base_name}__sum.json"
    
    # Check which format exists
    if summary_json.exists():
        summary_path = summary_json
    elif summary_sum.exists():
        summary_path = summary_sum
    else:
        return False, {"error": f"No summary file found for {pdf_path.name}"}
    
    try:
        # Load and validate JSON
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        
        # Check required fields
        missing_fields = [f for f in REQUIRED_FIELDS if f not in data]
        if missing_fields:
            return False, {
                "error": f"Missing required fields: {missing_fields}",
                "data": data
            }
        
        return True, data
        
    except json.JSONDecodeError as e:
        return False, {"error": f"Invalid JSON: {e}"}
    except Exception as e:
        return False, {"error": f"Error reading file: {e}"}


def test_summary(pdf_name: str):
    """Test a specific PDF's summary."""
    pdf_path = FILES_DIR / pdf_name
    
    if not pdf_path.exists():
        print(f"[ERROR] PDF not found: {pdf_name}")
        return
    
    print(f"\n{'='*70}")
    print(f"Testing: {pdf_name}")
    print(f"{'='*70}")
    
    is_valid, result = verify_summary_file(pdf_path)
    
    if is_valid:
        print("[OK] Summary file found and valid!")
        print(f"\n[Summary Contents]")
        print(json.dumps(result, indent=2))
        
        # Quick stats
        print(f"\n[Quick Stats]")
        print(f"  - Overall bias: {result.get('overall_bias', 'N/A')}")
        print(f"  - Products: {result.get('products', [])}")
        print(f"  - TLDR bullets: {len(result.get('tldr', []))}")
        print(f"  - Actionable items: {len(result.get('actionable', []))}")
        print(f"  - Time horizon: {result.get('time_horizon', 'N/A')}")
        
    else:
        print(f"[ERROR] Summary validation failed!")
        print(f"Error: {result.get('error', 'Unknown error')}")
        if 'data' in result:
            print(f"Partial data: {result['data']}")


def list_all_summaries():
    """List all PDFs and their summary status."""
    print(f"\n{'='*70}")
    print(f"Scanning: {FILES_DIR}")
    print(f"{'='*70}\n")
    
    pdfs = sorted(FILES_DIR.glob("*.pdf"))
    summaries_found = 0
    
    for pdf in pdfs[:10]:  # Check first 10 PDFs
        is_valid, result = verify_summary_file(pdf)
        status = "[OK]" if is_valid else "[MISSING]"
        summaries_found += 1 if is_valid else 0
        print(f"{status} {pdf.name[:60]}")
        if not is_valid:
            print(f"     -> {result.get('error', 'Unknown')}")
    
    print(f"\n[Summary] {summaries_found}/{len(pdfs[:10])} PDFs have summaries")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--list" or sys.argv[1] == "-l":
            # List all PDFs and their summary status
            list_all_summaries()
        else:
            # Test specific PDF
            test_summary(sys.argv[1])
    else:
        # Test the one we just created (default)
        test_summary("BA_Barclays - Energy Commodities - Chart Book- More evidence of resilient fundamentals 20251124_20251124_u.pdf")
        print("\n" + "="*70)
        print("Usage:")
        print("   python verify_summary.py                    # Test default PDF")
        print("   python verify_summary.py 'PDF_FILENAME.pdf' # Test specific PDF")
        print("   python verify_summary.py --list             # List all PDFs with summaries")
