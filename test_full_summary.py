"""
End-to-end test of the new summarize_pdf with preflight system.
"""
import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from summarize_pdf import summarize_pdf

def test_full_summarization():
    """Test full summarization with preflight + OCR."""
    print("=" * 80)
    print("FULL SUMMARIZATION TEST")
    print("=" * 80)
    print()
    
    # Find a small test PDF
    search_dirs = [
        r"C:\Users\H&CDanHughes\Documents\SC_files",
        r"C:\Program Files\Coding Projects\TWIFO_Sharing\test_files",
    ]
    
    test_pdf = None
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
        for file in os.listdir(search_dir):
            if file.endswith(".pdf") and not file.endswith("__ocr.pdf"):
                test_pdf = os.path.join(search_dir, file)
                break
        if test_pdf:
            break
    
    if not test_pdf:
        print("[ERROR] No PDF files found for testing")
        return
    
    print(f"Testing: {Path(test_pdf).name}")
    print(f"Path: {test_pdf}")
    print()
    
    try:
        # Run summarization
        print("-" * 80)
        print("RUNNING SUMMARIZATION...")
        print("-" * 80)
        
        summary = summarize_pdf(test_pdf, generate_pdf=False)  # Skip PDF gen for speed
        
        if summary:
            print()
            print("=" * 80)
            print("SUMMARIZATION SUCCESSFUL!")
            print("=" * 80)
            print()
            print("Summary schema:")
            print(f"  - meta.source_pdf: {summary['meta']['source_pdf']}")
            print(f"  - meta.extraction.method: {summary['meta']['extraction']['method']}")
            print(f"  - meta.extraction.ocr_flag: {summary['meta']['extraction']['ocr_flag']}")
            print(f"  - meta.extraction.total_chars: {summary['meta']['extraction']['total_chars']}")
            print(f"  - summary_score_0_10: {summary['summary_score_0_10']}")
            print(f"  - chart_score_0_3: {summary['chart_score_0_3']}")
            print()
            
            if summary['scan'].get('tldr'):
                print("TL;DR:")
                for item in summary['scan']['tldr']:
                    print(f"  • {item}")
                print()
            
            # Check for debug files
            pdf_path = Path(test_pdf)
            debug_json = pdf_path.parent / f"{pdf_path.stem}__debug.json"
            preview_txt = pdf_path.parent / f"{pdf_path.stem}__extract_preview.txt"
            sum_json = pdf_path.parent / f"{pdf_path.stem}__sum.json"
            
            print("Files created:")
            print(f"  - __debug.json: {debug_json.exists()}")
            print(f"  - __extract_preview.txt: {preview_txt.exists()}")
            print(f"  - __sum.json: {sum_json.exists()}")
            print()
            
        else:
            print("[WARN] Summarization returned None (likely skipped)")
    
    except Exception as e:
        print()
        print("=" * 80)
        print("SUMMARIZATION FAILED")
        print("=" * 80)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_full_summarization()

