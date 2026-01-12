"""
Test the new best-effort extraction function.

Purpose: Verify extract_text_best_effort() works correctly and prints method/chars
Author: Kevin Lefebvre
Last Updated: 2026-01-10
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from summarize_pdf import extract_text_best_effort, MIN_CHARS_TO_ACCEPT


def test_extraction(pdf_path: str):
    """Test extraction on a PDF file and print results."""
    pdf_path_obj = Path(pdf_path)
    
    if not pdf_path_obj.exists():
        print(f"ERROR: PDF file not found: {pdf_path}")
        return
    
    print("=" * 80)
    print(f"Testing extraction on: {pdf_path_obj.name}")
    print("=" * 80)
    
    # Set up debug paths
    debug_json_path = pdf_path_obj.parent / f"{pdf_path_obj.stem}__extract_debug.json"
    extract_preview_path = pdf_path_obj.parent / f"{pdf_path_obj.stem}__extract_preview.txt"
    
    # Run extraction
    result = extract_text_best_effort(pdf_path_obj, debug_json_path, extract_preview_path)
    
    # Print results
    print(f"\nExtraction Result:")
    print(f"  Status: {result.status}")
    print(f"  Method: {result.method}")
    print(f"  Total chars: {result.total_chars:,}")
    print(f"  Pages with text: {result.pages_with_text}/{result.page_count}")
    print(f"  MIN_CHARS_TO_ACCEPT: {MIN_CHARS_TO_ACCEPT}")
    
    if result.errors:
        print(f"\nErrors encountered ({len(result.errors)}):")
        for err in result.errors[:5]:  # Show first 5 errors
            print(f"  - {err}")
        if len(result.errors) > 5:
            print(f"  ... and {len(result.errors) - 5} more errors")
    
    if result.status == "ok":
        print(f"\n[PASS] Extraction succeeded using {result.method}")
        print(f"  Text preview (first 200 chars):")
        print(f"  {result.text[:200]}...")
    else:
        print(f"\n[FAIL] Extraction failed - all methods failed or produced insufficient text")
        print(f"  Best result: {result.total_chars} chars (required: {MIN_CHARS_TO_ACCEPT})")
    
    if debug_json_path.exists():
        print(f"\nDebug JSON written to: {debug_json_path.name}")
    if extract_preview_path.exists():
        print(f"Extract preview written to: {extract_preview_path.name}")
    
    print("=" * 80)
    
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_new_extraction.py <path_to_pdf>")
        print("\nExample:")
        print("  python test_new_extraction.py \"path/to/file.pdf\"")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    test_extraction(pdf_path)

