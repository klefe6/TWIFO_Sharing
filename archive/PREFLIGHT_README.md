# Preflight Extraction + OCR System

## Purpose
Robust PDF text extraction with OCR fallback and comprehensive debugging for empty/failed summaries.

**Author:** Kevin Lefebvre  
**Last Updated:** 2026-01-10

---

## Overview

The new preflight system prevents silent empty summaries by:
1. **Preflight extraction** - Tests text extraction quality before summarization
2. **Debug file generation** - Creates `__debug.json` and `__extract_preview.txt` for every PDF
3. **Automatic OCR** - Runs ocrmypdf when extraction quality is insufficient
4. **Strict error handling** - Raises clear exceptions instead of silently failing

---

## Files Created Per PDF

For each PDF processed (e.g., `BOA_Weekly_20260109.pdf`), the system creates:

1. **`BOA_Weekly_20260109__debug.json`** - Full extraction metrics
   ```json
   {
     "timestamp": "2026-01-10T21:00:00",
     "pdf_file": "BOA_Weekly_20260109.pdf",
     "extraction_method": "pymupdf",
     "page_count": 12,
     "total_chars": 5432,
     "pages_with_text": 10,
     "percent_pages_with_text": 83.33,
     "chars_per_page": [450, 520, ...],
     "needs_ocr": false,
     "error": null
   }
   ```

2. **`BOA_Weekly_20260109__extract_preview.txt`** - First 5000 chars of extracted text
   - Useful for visually inspecting extraction quality
   - Shows what the AI will receive

3. **`BOA_Weekly_20260109__ocr.pdf`** - OCR'd version (only if OCR was needed)
   - Original PDF is preserved
   - OCR version is used for summarization

4. **`BOA_Weekly_20260109__sum.json`** - Summary (as before)

5. **`BOA_Weekly_20260109__sum.pdf`** - Rendered summary (optional)

---

## Extraction Methods

The system tries extraction methods in order of quality:

### 1. PyMuPDF (fitz) - **Preferred**
- Fastest and most reliable
- Best for text-based PDFs
- Install: `pip install pymupdf`

### 2. pdfplumber - **Fallback #1**
- Better for table-heavy documents
- Preserves table structure
- Install: `pip install pdfplumber`

### 3. PyPDF2 - **Fallback #2**
- Always available (already installed)
- Basic text extraction

---

## OCR Trigger Thresholds

OCR is automatically triggered when:

| Condition | Threshold | Why |
|-----------|-----------|-----|
| `total_chars < 3000` | 3000 chars | Too little text extracted |
| `percent_pages_with_text < 40%` | 40% | Most pages appear empty |

These thresholds are configurable in `summarize_pdf.py`:
```python
PREFLIGHT_MIN_CHARS = 3000
PREFLIGHT_MIN_PAGE_COVERAGE = 0.40  # 40%
```

---

## OCR Process

When OCR is needed:

1. **Run ocrmypdf:**
   ```bash
   ocrmypdf --force-ocr --skip-text "input.pdf" "output__ocr.pdf"
   ```

2. **Re-extract from OCR'd PDF:**
   - Uses same extraction methods (PyMuPDF → pdfplumber → PyPDF2)
   - Updates `__debug.json` with post-OCR stats

3. **Continue summarization:**
   - Proceeds with OCR'd text
   - `meta.extraction.ocr_flag` set to `true` in summary JSON

---

## Error Handling

The new system **raises exceptions** instead of silently failing:

### Example: Empty Text After Extraction
```python
RuntimeError: Text extraction critically failed for BOA_file.pdf. 
Reason: Only 45 chars. Total chars: 45, Pages with text: 0/12, OCR used: False
```

### Example: API Failure
```python
RuntimeError: API call failed: Connection timeout after 30s
```

### Example: OCR Failure
```python
RuntimeError: OCR failed: ocrmypdf not installed
```

All errors are logged to console with `[ERR]` prefix and include diagnostic details.

---

## Usage

### Basic Usage (Unchanged)
```python
from summarize_pdf import summarize_pdf

# Accepts str or Path
summary = summarize_pdf("path/to/file.pdf", generate_pdf=True)
```

### Programmatic Usage with Error Handling
```python
from summarize_pdf import summarize_pdf
from pathlib import Path

pdf_path = Path("exports/BOA_Weekly_20260109.pdf")

try:
    summary = summarize_pdf(pdf_path, generate_pdf=True)
    print(f"Success! Score: {summary['summary_score_0_10']}/10")
    
except RuntimeError as e:
    print(f"Failed: {e}")
    # Check __debug.json for details
    debug_file = pdf_path.parent / f"{pdf_path.stem}__debug.json"
    if debug_file.exists():
        import json
        with open(debug_file) as f:
            debug_data = json.load(f)
        print(f"Extraction method: {debug_data['extraction_method']}")
        print(f"Total chars: {debug_data['total_chars']}")
        print(f"Pages with text: {debug_data['pages_with_text']}/{debug_data['page_count']}")
```

---

## Debugging Failed Summaries

### Step 1: Check `__debug.json`
```bash
cat BOA_file__debug.json
```

Look for:
- `total_chars` - Should be > 3000
- `percent_pages_with_text` - Should be > 40%
- `needs_ocr` - If true, was OCR attempted?
- `error` - Any extraction errors?

### Step 2: Check `__extract_preview.txt`
```bash
head -50 BOA_file__extract_preview.txt
```

Visual inspection:
- Is the text readable?
- Is it garbage/formatting characters?
- Are there repeated patterns?

### Step 3: Check OCR Status
If `needs_ocr: true` in debug JSON:
- Does `__ocr.pdf` exist?
- Check `ocr_attempted`, `ocr_success` in debug JSON
- Look for `ocr_error` field

### Step 4: Check Summary JSON
```bash
cat BOA_file__sum.json
```

Look at `meta.extraction`:
```json
{
  "method": "pymupdf_ocr",
  "ocr_flag": true,
  "total_chars": 5432,
  "errors": []
}
```

---

## Testing

### Test Preflight System Only
```bash
python test_preflight.py
```

This tests:
- Extraction methods
- Debug file creation
- OCR triggering

### Test Full Summarization
```bash
python test_full_summary.py
```

This tests:
- End-to-end summarization
- API integration
- JSON/PDF generation

---

## Dependencies

### Required
- `PyPDF2` - Already installed
- `requests` - Already installed

### Optional (Recommended)
```bash
# For better extraction
pip install pymupdf pdfplumber

# For OCR support
# Windows: See OCR_INSTALL_GUIDE.md
# Linux/Mac:
apt-get install ocrmypdf tesseract-ocr  # Debian/Ubuntu
brew install ocrmypdf tesseract          # macOS
```

---

## Configuration

All thresholds are configurable in `summarize_pdf.py`:

```python
# Preflight thresholds
PREFLIGHT_MIN_CHARS = 3000
PREFLIGHT_MIN_PAGE_COVERAGE = 0.40  # 40%

# API limits
MAX_PAGES_TO_SCAN = 12
MAX_INPUT_CHARS = 50000
MAX_OUTPUT_TOKENS = 900

# OCR quality thresholds (legacy, still used for validation)
OCR_MIN_CHAR_COUNT = 1500
OCR_MIN_WORD_COUNT = 250
OCR_MIN_ALPHA_RATIO = 0.4
OCR_MIN_PAGE_COVERAGE = 0.5
OCR_MIN_CHARS_PER_PAGE = 50
OCR_MIN_UNIQUE_WORD_RATIO = 0.2
```

---

## Summary Schema Updates

The `meta.extraction` section now includes:

```json
{
  "meta": {
    "extraction": {
      "method": "pymupdf_ocr",
      "ocr_flag": true,
      "extraction_quality_0_100": 85,
      "pages_scanned": 12,
      "total_chars": 5432,
      "errors": []
    }
  }
}
```

**New fields:**
- `total_chars` - Raw character count from extraction
- `errors` - List of any extraction/processing errors

---

## Common Issues

### Issue: "All extraction methods failed"
**Cause:** PDF is corrupted or password-protected  
**Solution:** Check PDF can be opened in Adobe Reader

### Issue: "OCR timed out after 5 minutes"
**Cause:** Large PDF or slow OCR processing  
**Solution:** Reduce `MAX_PAGES_TO_SCAN` or increase timeout in `run_ocr_on_pdf()`

### Issue: "OCR failed with code 1"
**Cause:** ocrmypdf not installed or PDF already has text layer  
**Solution:** Install ocrmypdf or check `__debug.json` for details

### Issue: Empty summary after OCR
**Cause:** OCR produced unreadable text  
**Solution:** Check `__extract_preview.txt` after OCR, may need manual review

---

## Performance

Typical processing times:

| Step | Time | Notes |
|------|------|-------|
| Preflight extraction | 1-2s | Fast with PyMuPDF |
| OCR (if needed) | 30-60s | Depends on page count |
| AI summarization | 5-10s | Depends on text length |
| **Total (no OCR)** | **6-12s** | Most PDFs |
| **Total (with OCR)** | **36-72s** | Image-based PDFs |

---

## Migration from Old System

The new system is **backward compatible**:

- Old `extract_text_with_fallback()` still exists (but deprecated)
- Old summary JSONs are still valid
- No changes needed to calling code

**Recommended migration:**
1. Update imports to use new `summarize_pdf()`
2. Add error handling for `RuntimeError`
3. Check debug files for failed PDFs

---

## Support

For issues or questions:
1. Check `__debug.json` first
2. Review `__extract_preview.txt`
3. Check console output for `[ERR]` messages
4. See `OCR_INSTALL_GUIDE.md` for OCR setup

