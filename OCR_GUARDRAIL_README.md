# OCR Guardrail Implementation

**Purpose:** Prevent empty/garbage text from reaching OpenAI API by detecting image-based PDFs and applying OCR intelligently.

**Author:** Kevin Lefebvre  
**Date:** 2026-01-10

---

## Problem Statement

PDF summarization was failing silently when PDFs contained only images (scanned documents). PyPDF2 would extract minimal or no text, leading to:
- Empty/garbage text sent to OpenAI API
- Wasted API calls
- Summaries with Score 0/10 and "Not provided" values
- No visibility into why summaries failed

---

## Solution Overview

Implemented a **multi-stage extraction pipeline** with quality detection:

1. **Preflight Check** - Analyze text quality before sending to AI
2. **OCR Fallback** - Run OCR only when needed
3. **Quality Scoring** - Surface extraction status and metrics
4. **Graceful Failure** - Create explicit failure summaries instead of silent failures

---

## Implementation Details

### 1. Preflight Quality Detection

**Function:** `preflight_pdf_text_quality(pdf_path, max_pages) -> dict`

Extracts text from first N pages and computes:
- `char_count` - Total characters
- `word_count` - Total words  
- `unique_word_ratio` - Unique words / total words
- `alpha_ratio` - Alphabetic chars / total chars
- `pages_with_text` - Pages with meaningful text
- `scanned_pages` - Total pages analyzed

**Triggers OCR if ANY of these are true:**
- `char_count < 1500`
- `word_count < 250`
- `pages_with_text / scanned_pages < 0.5`
- `alpha_ratio < 0.4`

### 2. OCR Extraction Pipeline

**Function:** `extract_text_with_fallback(pdf_path, max_pages) -> (text, status, metrics)`

**Returns:**
- `text` - Extracted text string
- `status` - One of: `"ok"`, `"ocr_used"`, `"failed"`
- `metrics` - Quality metrics dict

**OCR Tool Priority:**
1. **ocrmypdf** (preferred) - Best quality, preserves PDF structure
2. **pytesseract + pdf2image** (fallback) - Pure Python solution
3. **None available** - Returns `status="failed"` with reason `"ocr_tool_missing"`

### 3. OCR Caching

**Directory:** `.ocr_cache/`

**Cache Key:** MD5 hash of `{filepath}:{size}:{mtime}`

**Benefits:**
- Avoid re-running expensive OCR on same file
- Cache survives across runs
- Automatically invalidates when PDF changes

### 4. Failed Extraction Handling

When extraction fails (OCR unavailable or yields low-quality text), creates a **failed summary JSON**:

```json
{
  "extraction_status": "failed",
  "extraction_reason": "ocr_failed_or_low_text",
  "extraction_metrics": { /* metrics */ },
  "summary_score_0_10": 0,
  "chart_score_0_3": 0,
  "overall_bias": "neutral",
  "products": [],
  "per_product": {},
  "tldr": ["Extraction failed - PDF may be image-based or corrupted"],
  "actionable": [],
  "time_horizon": "N/A",
  "product_categories": {}
}
```

This ensures:
- Downstream code doesn't break (all expected fields present)
- Failures are visible in the UI (red score = 0)
- Reason is logged for debugging

---

## Updated JSON Schema

All summary JSON files now include:

```json
{
  "extraction_status": "ok" | "ocr_used" | "failed",
  "extraction_metrics": {
    "char_count": 12500,
    "word_count": 2100,
    "unique_word_ratio": 0.45,
    "alpha_ratio": 0.82,
    "pages_with_text": 11,
    "scanned_pages": 12
  },
  /* ... rest of summary fields ... */
}
```

### extraction_status Values

| Value | Meaning |
|-------|---------|
| `"ok"` | Normal PyPDF2 extraction succeeded |
| `"ocr_used"` | OCR was required and succeeded |
| `"failed"` | Extraction failed (OCR unavailable or low quality) |

---

## PDF Rendering Updates

**File:** `summary_render.py`

When `extraction_status == "ocr_used"`, adds orange notice at top of PDF:

```
⚠ OCR was used to extract text from this PDF
```

When `extraction_status == "failed"`, adds red notice:

```
⚠ Text extraction failed - Summary may be incomplete or unavailable
```

---

## Configuration (Tuneable)

**File:** `summarize_pdf.py` (lines 115-120)

```python
OCR_MIN_CHAR_COUNT = 1500        # Minimum total characters
OCR_MIN_WORD_COUNT = 250          # Minimum total words
OCR_MIN_ALPHA_RATIO = 0.4         # Min alphabetic ratio
OCR_MIN_PAGE_COVERAGE = 0.5       # Min fraction of pages with text
OCR_MIN_CHARS_PER_PAGE = 50       # Min chars/page to count as "has text"
```

**Tuning Guidelines:**
- **More aggressive OCR:** Lower thresholds (e.g., `OCR_MIN_CHAR_COUNT = 1000`)
- **Less aggressive OCR:** Raise thresholds (e.g., `OCR_MIN_CHAR_COUNT = 2500`)
- **Chart-heavy PDFs:** May need lower `OCR_MIN_PAGE_COVERAGE` (e.g., `0.3`)

---

## Dependencies

### Core (Required)
- `PyPDF2` - Already installed
- `requests` - Already installed

### OCR Tools (Optional)

**Option A: ocrmypdf (Recommended)**
```bash
pip install ocrmypdf
# Requires Tesseract OCR engine (system dependency)
# Windows: https://github.com/UB-Mannheim/tesseract/wiki
# macOS: brew install tesseract
# Linux: apt-get install tesseract-ocr
```

**Option B: pytesseract + pdf2image (Fallback)**
```bash
pip install pytesseract pdf2image
# Also requires Tesseract OCR engine (see above)
# Also requires poppler (for pdf2image)
# Windows: https://github.com/oschwartz10612/poppler-windows/releases/
```

**Note:** If neither is available, extraction will return `status="failed"` with reason `"ocr_tool_missing"`. The system will still generate a valid JSON summary with score=0.

---

## Testing

**Test Script:** `test_ocr_guardrail.py`

```bash
cd "C:\Program Files\Coding Projects\TWIFO_Sharing"
python test_ocr_guardrail.py
```

**Tests:**
1. OCR tool availability detection
2. Preflight quality check on sample PDF
3. Full extraction pipeline with fallback

---

## Integration Points

### 1. summarize_pdf.py
- **Modified:** `summarize_pdf()` - Uses `extract_text_with_fallback()`
- **Added:** `preflight_pdf_text_quality()`, `extract_text_with_fallback()`, OCR functions
- **Removed:** Old `extract_text()` function (superseded)

### 2. summary_render.py
- **Modified:** `render_summary_pdf()` - Reads `extraction_status` and displays indicator

### 3. twifo.py
- **No changes required** - Already reads `summary_score_0_10` and colors failed summaries red
- Failed extractions will automatically show as score=0 (dark red)

### 4. test_summarize_one.py
- **No changes required** - Already imports from `summarize_pdf` module
- Will automatically use new extraction pipeline

---

## Usage Examples

### Example 1: Normal PDF (Text-Based)
```python
from pathlib import Path
from summarize_pdf import extract_text_with_fallback

pdf_path = Path("normal_research_report.pdf")
text, status, metrics = extract_text_with_fallback(pdf_path)

# Result:
# status = "ok"
# metrics = {"char_count": 12500, "word_count": 2100, ...}
# Text extraction succeeded with PyPDF2
```

### Example 2: Image-Based PDF (OCR Needed)
```python
pdf_path = Path("scanned_document.pdf")
text, status, metrics = extract_text_with_fallback(pdf_path)

# Result:
# status = "ocr_used"
# metrics = {"char_count": 8500, "word_count": 1400, ...}
# OCR was run and succeeded
```

### Example 3: OCR Tools Not Available
```python
pdf_path = Path("scanned_document.pdf")
text, status, metrics = extract_text_with_fallback(pdf_path)

# Result:
# status = "failed"
# metrics = {"char_count": 0, "word_count": 0, ...}
# text = ""
# Failed summary JSON will be created with score=0
```

---

## Backward Compatibility

✅ **Fully backward compatible** with existing code:
- All existing JSON fields preserved
- New fields added (not removed)
- twifo.py requires no changes
- Existing summary JSONs without `extraction_status` still work

---

## Performance Considerations

### Speed
- **Preflight check:** ~1-2 seconds (PyPDF2 extraction)
- **ocrmypdf:** ~30-120 seconds depending on PDF size/complexity
- **pytesseract:** ~20-60 seconds depending on PDF size/complexity

### Optimization
- Only runs OCR when preflight detects poor quality
- Caches OCR results (subsequent runs are instant)
- Skips OCR for text-based PDFs (99% of inputs)

### Memory
- OCR can use 200-500 MB RAM during processing
- Cache files: ~10-50 KB per PDF (compressed text)

---

## Monitoring & Debugging

### Check OCR Cache
```bash
ls -lh .ocr_cache/
# Each file is named by hash: a1b2c3d4e5f6...txt
```

### Clear OCR Cache
```bash
rm -rf .ocr_cache/
# Or manually delete specific cache files
```

### Enable Verbose Logging
All OCR operations print to console:
- `[INFO] OCR needed for {filename}: {reason}`
- `[INFO] Running ocrmypdf on {filename}...`
- `[OK] OCR successful: {char_count} chars, {word_count} words`
- `[WARN] ocrmypdf failed, trying pytesseract...`
- `[ERROR] OCR failed or tools unavailable`

---

## Troubleshooting

### Issue: "OCR failed or tools unavailable"
**Solution:** Install OCR dependencies:
```bash
pip install ocrmypdf
# or
pip install pytesseract pdf2image
# Then install Tesseract system binary (see Dependencies section)
```

### Issue: "ocrmypdf command not found"
**Solution:** Tesseract not installed or not in PATH
- Windows: Add Tesseract to PATH after installing
- macOS: `brew install tesseract`
- Linux: `apt-get install tesseract-ocr`

### Issue: Extracted text is garbage after OCR
**Solution:** Check these:
1. Is PDF extremely low quality / heavily compressed?
2. Is PDF in non-English language? (Add `-l <lang>` to ocrmypdf command)
3. Try lowering quality thresholds in config

### Issue: OCR is too slow
**Solutions:**
1. Reduce `MAX_PAGES_TO_SCAN` (default 12)
2. Use faster OCR engine (ocrmypdf with `--fast` flag)
3. Pre-process PDFs externally and skip OCR

---

## Future Enhancements

Potential improvements (not implemented):
1. **Parallel OCR** - Process multiple PDFs simultaneously
2. **Cloud OCR** - Use Google Cloud Vision API or AWS Textract
3. **Language Detection** - Auto-detect PDF language for better OCR
4. **Quality-Based Scoring** - Lower summary scores for OCR'd documents
5. **OCR Confidence** - Surface per-page confidence scores from Tesseract

---

## Summary

**Implementation Status:** ✅ Complete

**Key Benefits:**
- ✅ No more empty/garbage summaries sent to AI
- ✅ Failed extractions are explicit and visible (score=0, red)
- ✅ OCR runs automatically only when needed
- ✅ OCR results are cached for speed
- ✅ Extraction quality metrics surfaced in JSON
- ✅ OCR indicator visible in PDF summaries
- ✅ Fully backward compatible
- ✅ Minimal performance impact (only OCR when needed)

**Files Modified:**
- `summarize_pdf.py` - Core OCR pipeline (~300 lines added)
- `summary_render.py` - OCR indicator in PDF rendering (~20 lines)
- `test_ocr_guardrail.py` - Validation test script (new file)
- `OCR_GUARDRAIL_README.md` - This documentation (new file)

**Files Unchanged:**
- `twifo.py` - No changes needed (already handles score=0)
- `test_summarize_one.py` - No changes needed (uses summarize_pdf module)

---

## Questions?

Contact: Kevin Lefebvre  
Last Updated: 2026-01-10

