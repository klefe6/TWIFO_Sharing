"""
CLI smoke test for single PDF summarization with retry escalation.
Purpose: Run one PDF and print attempt count, status, quality reason.
Author: Kevin Lefebvre
Last Updated: 2026-01-26

Usage:
    python smoke_test_pdf.py path/to/document.pdf
"""

import sys
import json
from pathlib import Path


def smoke_test_single_pdf(pdf_path: str):
    """
    Run summarization on a single PDF and report results.
    """
    pdf = Path(pdf_path)
    if not pdf.exists():
        print(f"[ERROR] PDF not found: {pdf_path}")
        return 1
    
    print("=" * 80)
    print(f"SMOKE TEST: {pdf.name}")
    print("=" * 80)
    print(f"PDF: {pdf}")
    print(f"Size: {pdf.stat().st_size:,} bytes")
    print()
    
    # Import and run summarization
    try:
        from summarize_pdf import summarize_pdf
    except ImportError as e:
        print(f"[ERROR] Could not import summarize_pdf: {e}")
        return 1
    
    try:
        print("[START] Running summarization with quality retry...")
        print()
        
        result = summarize_pdf(pdf, allow_ocr=False)  # No OCR for speed
        
        print()
        print("=" * 80)
        print("RESULTS")
        print("=" * 80)
        
        # Extract key info
        extraction = result.get("extraction", {})
        meta = result.get("meta", {})
        sections = result.get("sections", {})
        
        status = extraction.get("status", "unknown")
        reason = extraction.get("reason", "")
        attempt_count = extraction.get("attempt_count", "not recorded")
        quality_reason = extraction.get("quality_reason", "")
        model = meta.get("model", "unknown")
        
        print(f"Status: {status}")
        print(f"Model: {model}")
        print(f"Attempts: {attempt_count}")
        
        if status != "ok":
            print(f"Failure Reason: {reason}")
        
        if quality_reason:
            print(f"Quality Reason: {quality_reason}")
        
        print()
        print("Section Bullet Counts:")
        for key in ["what_moved_today", "what_can_move_tomorrow", "tldr", 
                    "what_occurred", "forward_watch", "trade_ideas"]:
            items = sections.get(key, [])
            count = len(items) if isinstance(items, list) else 0
            print(f"  {key}: {count}")
        
        print()
        
        # Check for debug artifact
        debug_path = pdf.parent / f"{pdf.stem}__sum_debug_raw.txt"
        if debug_path.exists():
            print(f"[DEBUG] Debug artifact created: {debug_path}")
            size = debug_path.stat().st_size
            print(f"        Size: {size:,} bytes")
        
        # Check for outputs
        json_path = pdf.parent / f"{pdf.stem}__sum.json"
        txt_path = pdf.parent / f"{pdf.stem}__sum.txt"
        pdf_path_out = pdf.parent / f"{pdf.stem}__sum.pdf"
        
        print()
        print("Artifacts Generated:")
        for artifact in [json_path, txt_path, pdf_path_out]:
            if artifact.exists():
                print(f"  ✓ {artifact.name} ({artifact.stat().st_size:,} bytes)")
            else:
                print(f"  ✗ {artifact.name} (missing)")
        
        print()
        print("=" * 80)
        
        if status == "ok":
            print("[SUCCESS] Summary generated successfully")
            if attempt_count == 1:
                print("          (passed quality gate on first attempt)")
            elif attempt_count == 2:
                print("          (passed quality gate after retry with stronger model)")
            return 0
        else:
            print("[FAILURE] Summary failed after all attempts")
            print(f"          Reason: {reason}")
            return 1
            
    except Exception as e:
        print()
        print("=" * 80)
        print(f"[ERROR] Exception during summarization: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        return 1


def main():
    if len(sys.argv) < 2:
        print("Usage: python smoke_test_pdf.py path/to/document.pdf")
        print()
        print("This will:")
        print("  1. Run summarization with quality retry")
        print("  2. Show attempt count (1 or 2)")
        print("  3. Report final status and quality reason")
        print("  4. List all artifacts generated")
        return 1
    
    pdf_path = sys.argv[1]
    return smoke_test_single_pdf(pdf_path)


if __name__ == "__main__":
    sys.exit(main())
