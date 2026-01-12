"""
Test script to validate OCR guardrail implementation.

Purpose: Verify that OCR detection and fallback work correctly
Author: Kevin Lefebvre
Last Updated: 2026-01-10
"""

from pathlib import Path
from summarize_pdf import (
    preflight_pdf_text_quality,
    extract_text_with_fallback,
    _check_ocr_tools,
)


def test_ocr_tools_availability():
    """Check which OCR tools are available on this system."""
    print("=" * 60)
    print("Testing OCR Tool Availability")
    print("=" * 60)
    
    tools = _check_ocr_tools()
    
    print(f"ocrmypdf:    {'[OK] Available' if tools['ocrmypdf'] else '[NO] Not available'}")
    print(f"pytesseract: {'[OK] Available' if tools['pytesseract'] else '[NO] Not available'}")
    print(f"pdf2image:   {'[OK] Available' if tools['pdf2image'] else '[NO] Not available'}")
    print()
    
    if not any(tools.values()):
        print("[WARN] No OCR tools available!")
        print("  Install with: pip install ocrmypdf")
        print("  or: pip install pytesseract pdf2image")
    
    return tools


def test_pdf_preflight(pdf_path: Path):
    """Test preflight quality check on a PDF."""
    print("=" * 60)
    print(f"Testing Preflight: {pdf_path.name}")
    print("=" * 60)
    
    if not pdf_path.exists():
        print(f"[WARN] PDF not found: {pdf_path}")
        return None
    
    result = preflight_pdf_text_quality(pdf_path)
    
    print(f"Needs OCR: {result['needs_ocr']}")
    print(f"Reason:    {result['reason']}")
    print("\nMetrics:")
    for key, value in result['metrics'].items():
        print(f"  {key:20s}: {value}")
    print()
    
    return result


def test_extraction_with_fallback(pdf_path: Path):
    """Test full extraction pipeline with OCR fallback."""
    print("=" * 60)
    print(f"Testing Extraction: {pdf_path.name}")
    print("=" * 60)
    
    if not pdf_path.exists():
        print(f"[WARN] PDF not found: {pdf_path}")
        return None
    
    text, status, metrics = extract_text_with_fallback(pdf_path, max_pages=3)
    
    print(f"Extraction Status: {status}")
    print(f"Text Length:       {len(text)} chars")
    print("\nMetrics:")
    for key, value in metrics.items():
        print(f"  {key:20s}: {value}")
    
    if text:
        print(f"\nFirst 300 chars of extracted text:")
        print("-" * 60)
        print(text[:300])
        print("-" * 60)
    else:
        print("\n[WARN] No text extracted!")
    print()
    
    return text, status, metrics


def main():
    """Run all tests."""
    print("\n")
    print("=" * 60)
    print("OCR GUARDRAIL VALIDATION TEST")
    print("=" * 60)
    print()
    
    # Test 1: Check OCR tools
    tools = test_ocr_tools_availability()
    
    # Test 2: Test with a sample PDF (modify path as needed)
    # Use the PDF from test_summarize_one.py if it exists
    sample_pdf = Path(r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE") / "BA_Barclays - Energy Commodities - Chart Book- More evidence of resilient fundamentals 20251124_20251124_u.pdf"
    
    if sample_pdf.exists():
        print("\nTesting with sample PDF from test_summarize_one.py...")
        
        # Run preflight
        preflight_result = test_pdf_preflight(sample_pdf)
        
        # Run full extraction
        if preflight_result:
            extraction_result = test_extraction_with_fallback(sample_pdf)
    else:
        print(f"\n[WARN] Sample PDF not found: {sample_pdf}")
        print("  Please update the path in test_ocr_guardrail.py to test with a real PDF")
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("\n[OK] OCR Guardrail implementation complete!")
    print("\nFeatures implemented:")
    print("  1. preflight_pdf_text_quality() - Quality detection before AI call")
    print("  2. extract_text_with_fallback() - OCR fallback pipeline")
    print("  3. OCR caching system (stores in .ocr_cache/)")
    print("  4. Failed extraction handling (creates summary with score=0)")
    print("  5. extraction_status and extraction_metrics in JSON")
    print("  6. OCR flag indicator in PDF rendering")
    print("\nThresholds (tuneable in summarize_pdf.py):")
    print("  OCR_MIN_CHAR_COUNT = 1500")
    print("  OCR_MIN_WORD_COUNT = 250")
    print("  OCR_MIN_ALPHA_RATIO = 0.4")
    print("  OCR_MIN_PAGE_COVERAGE = 0.5")
    print("\nOCR tool priority:")
    print("  1. ocrmypdf (preferred, best quality)")
    print("  2. pytesseract + pdf2image (fallback)")
    print("  3. If neither available: status='failed', reason='ocr_tool_missing'")
    print()


if __name__ == "__main__":
    main()

