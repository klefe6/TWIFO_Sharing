# Preflight System - Quick Reference

## For: Kevin Lefebvre
## Date: 2026-01-10

---

## What Changed?

Your pipeline that calls `summarize_pdf(dst, generate_pdf=True)` now:
1. **Extracts text with PyMuPDF/pdfplumber** (better quality)
2. **Creates debug files** for every PDF
3. **Runs OCR automatically** when text extraction is poor
4. **Raises clear exceptions** instead of silently failing

**No code changes needed** - but error handling recommended.

---

## New Files Per PDF

For `BOA_Weekly_20260109.pdf`, you'll now see:

```
BOA_Weekly_20260109.pdf                    ← Original
BOA_Weekly_20260109__debug.json            ← NEW: Extraction metrics
BOA_Weekly_20260109__extract_preview.txt   ← NEW: First 5000 chars
BOA_Weekly_20260109__ocr.pdf               ← NEW: OCR'd version (if needed)
BOA_Weekly_20260109__sum.json              ← Summary (as before)
BOA_Weekly_20260109__sum.pdf               ← Rendered summary (as before)
```

---

## Debug Workflow

### When a summary is empty or has 0 score:

**Step 1: Check `__debug.json`**
```bash
cat BOA_file__debug.json
```
Look for:
- `total_chars` - Should be > 3000
- `percent_pages_with_text` - Should be > 40%
- `needs_ocr` - Was OCR needed?
- `ocr_attempted` / `ocr_success` - Did OCR run?

**Step 2: Check `__extract_preview.txt`**
```bash
head -50 BOA_file__extract_preview.txt
```
- Is the text readable?
- Is it garbage characters?
- Does it match what's in the PDF?

**Step 3: Check `__ocr.pdf`** (if exists)
Open the `__ocr.pdf` and verify text is readable.

**Step 4: Check Summary JSON**
```bash
cat BOA_file__sum.json
```
Look at `meta.extraction` section for details.

---

## Error Messages

### Before (Silent Failure)
```
[OK] Summary JSON created: BOA_file__sum.json
# But summary_score_0_10 = 0 and no actual content
```

### After (Clear Error)
```
[ERR] Text extraction critically failed for BOA_file.pdf. 
Reason: Only 45 chars. Total chars: 45, Pages with text: 0/12, OCR used: False
```

**What to do:** Check `__debug.json` and `__extract_preview.txt` to diagnose.

---

## Recommended Code Update

### Current (Still Works)
```python
summary = summarize_pdf(dst, generate_pdf=True)
```

### Recommended (Better Error Handling)
```python
from pathlib import Path

try:
    summary = summarize_pdf(dst, generate_pdf=True)
    print(f"[OK] Score: {summary['summary_score_0_10']}/10")
    
except RuntimeError as e:
    print(f"[ERR] Summarization failed: {e}")
    
    # Debug: Check debug files
    debug_file = Path(dst).parent / f"{Path(dst).stem}__debug.json"
    if debug_file.exists():
        import json
        with open(debug_file) as f:
            debug = json.load(f)
        print(f"  - Total chars: {debug['total_chars']}")
        print(f"  - Extraction method: {debug['extraction_method']}")
        print(f"  - Needs OCR: {debug['needs_ocr']}")
```

---

## Configuration (Optional)

In `summarize_pdf.py`, you can tune:

```python
# When to trigger OCR
PREFLIGHT_MIN_CHARS = 3000         # Lower = OCR triggers easier
PREFLIGHT_MIN_PAGE_COVERAGE = 0.40  # 40% pages must have text

# How much to process
MAX_PAGES_TO_SCAN = 12            # Process first N pages only
MAX_INPUT_CHARS = 50000            # Truncate long documents
```

---

## Performance

| PDF Type | Before | After | Notes |
|----------|--------|-------|-------|
| Normal text | 6-10s | 7-12s | +1-2s for debug files |
| Image-based | Often failed | 35-70s | Now works with OCR |

---

## Testing

### Test Preflight Only
```bash
python test_preflight.py
```
Shows:
- Extraction method used
- Total chars extracted
- Pages with text
- OCR needed?
- Debug files created

### Test Full Summarization
```bash
python test_full_summary.py
```
Runs complete pipeline and shows results.

---

## BOA IEEPA File - What Changed?

The file that was failing should now:

1. **Be extracted with PyMuPDF** (more reliable than PyPDF2)
2. **Trigger OCR if needed** (creates `__ocr.pdf`)
3. **Create debug files** so you can see exactly what was extracted
4. **Raise clear error** if still fails, with diagnostic details

**To diagnose now:**
```bash
# Look for the debug JSON
ls BOA*__debug.json

# Check the metrics
cat "BOA_US Economic Weekly IEEPA D-Day FAQs 20260109_20260109_w__debug.json"
```

---

## Install Optional Dependencies

For better extraction (recommended):
```bash
pip install pymupdf pdfplumber
```

For OCR support (if needed):
- Windows: See `OCR_INSTALL_GUIDE.md`
- Linux: `apt-get install ocrmypdf tesseract-ocr`
- macOS: `brew install ocrmypdf tesseract`

---

## Quick Commands

### Check debug file
```bash
cat filename__debug.json
```

### Check extraction preview
```bash
head -100 filename__extract_preview.txt
```

### Find all debug files
```bash
ls *__debug.json
```

### Find PDFs that needed OCR
```bash
ls *__ocr.pdf
```

### Check summary extraction metadata
```bash
cat filename__sum.json | grep -A 10 '"extraction"'
```

---

## Documentation

- **`PREFLIGHT_README.md`** - Complete guide
- **`PREFLIGHT_IMPLEMENTATION_SUMMARY.md`** - Technical details
- **`test_preflight.py`** - Test extraction only
- **`test_full_summary.py`** - Test full pipeline

---

## Support

If you encounter issues:
1. ✅ Check `__debug.json` first
2. ✅ Review `__extract_preview.txt`
3. ✅ Look for `[ERR]` messages in console
4. ✅ Verify OCR is installed (if `needs_ocr: true`)

All errors now include diagnostic details instead of failing silently.

