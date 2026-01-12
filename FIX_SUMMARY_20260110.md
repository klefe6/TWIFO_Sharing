# Fix Summary - Color Coding & BOA File Extraction

## Date: 2026-01-10
## Author: Kevin Lefebvre

---

## Issue 1: Color Coding on Rows Without Scores

### Problem
The DataTable was applying score-based color coding to all rows, including those without summary scores. This made unsummarized files appear colored incorrectly.

### Root Cause
1. Score values for files without summaries were stored as empty strings `""`
2. Dash DataTable filter queries didn't properly handle empty string values
3. Filter conditions like `{summary_score} <= 2` would match rows with empty/null scores

### Fix Applied
1. **Changed data format**: Store scores as `None` instead of `""` when no summary exists
   - Location: `twifo.py`, line ~1285
   - Before: `summary_score if summary_score is not None else ""`
   - After: `summary_score` (passes None directly)

2. **Updated filter queries**: Added `is not blank` condition to all color coding rules
   - Location: `twifo.py`, lines ~724-773
   - Before: `{summary_score} <= 2 && {summary_score} >= 0`
   - After: `{summary_score} is not blank && {summary_score} <= 2 && {summary_score} >= 0`

### Result
- Rows without summary scores will now have default (transparent/no special) background color
- Only rows with valid scores (0-10) will be color-coded according to their score

---

## Issue 2: BOA File Extraction Failures

### Problem
File "BOA_US Economic Weekly IEEPA D-Day FAQs 20260109_20260109_w.pdf" keeps getting misread or skipped with 0 data in the summary.

### Root Cause Analysis
The file likely has one of these issues:
1. **Garbage text extraction**: PyPDF2 extracts characters but they're formatting/junk, not readable text
2. **Low text density**: The PDF might be mostly images/charts with minimal extractable text
3. **Repeated/low-quality text**: Extraction succeeds but text has very low unique word ratio (indicating garbage)

### Fixes Applied

#### 1. Added Unique Word Ratio Check
**Location**: `summarize_pdf.py`, lines ~126-129

Added new threshold:
```python
OCR_MIN_UNIQUE_WORD_RATIO = 0.2  # Minimum ratio of unique words (detects garbage/repeated text)
```

**Logic**: If extracted text has < 20% unique words (e.g., "the the the page page page"), trigger OCR.

#### 2. Enhanced OCR Trigger Logic
**Location**: `summarize_pdf.py`, lines ~457-481

Added check:
```python
if metrics["unique_word_ratio"] < OCR_MIN_UNIQUE_WORD_RATIO and metrics["word_count"] > 0:
    needs_ocr = True
    reasons.append(f"unique_word_ratio={metrics['unique_word_ratio']:.2f} < {OCR_MIN_UNIQUE_WORD_RATIO} (likely garbage)")
```

#### 3. Enhanced Extraction Quality Validation
**Location**: `summarize_pdf.py`, lines ~855-869

Strengthened pre-AI validation:
```python
extraction_quality = calculate_extraction_quality_0_100(extraction_metrics)

is_failed = (
    extraction_status == "failed" 
    or not raw_text 
    or len(raw_text) < 100
    or extraction_quality < 20  # NEW: Reject critically low quality
)
```

**Previous logic**: Only checked status == "failed", empty text, or length < 100  
**New logic**: Also rejects extractions with quality score < 20/100

### Result
1. **More aggressive OCR triggering**: Files with garbage text will now trigger OCR instead of proceeding
2. **Better failure detection**: Files with critically low extraction quality (< 20/100) will get a "failed summary" with score 0, instead of sending garbage to the AI
3. **Detailed logging**: Extraction failures now log status, text length, and quality score for debugging

---

## Testing Recommendations

### Test Color Coding
1. Open twifo website
2. Check that files WITHOUT `__sum.json` have no special background color in Summary/Score columns
3. Check that files WITH summaries have correct colors:
   - 0-2: Dark red
   - 3-4: Orange-red
   - 5: Yellow/gold
   - 6-7: Yellow-green
   - 8-10: Green

### Test BOA File Extraction
1. Delete existing `BOA_US Economic Weekly IEEPA D-Day FAQs 20260109_20260109_w__sum.json` if it exists
2. Run summarization on the BOA file
3. Check console output for:
   - OCR trigger messages
   - Extraction quality score
   - Text length
4. Verify the resulting summary JSON has:
   - `meta.extraction.extraction_quality_0_100` > 0
   - `meta.extraction.ocr_flag` = true (if OCR was used)
   - `scan.score.summary_score_0_10` reflects actual content quality

---

## Files Modified

1. **twifo.py**
   - Fixed color coding filter queries (added `is not blank` checks)
   - Changed score data format from `""` to `None` for missing scores

2. **summarize_pdf.py**
   - Added `OCR_MIN_UNIQUE_WORD_RATIO` threshold
   - Enhanced OCR trigger logic with unique word ratio check
   - Strengthened extraction quality validation before AI call
   - Improved error logging with quality score details

---

## Backward Compatibility

✅ All changes are backward compatible:
- Existing summary JSONs work unchanged
- Old PDFs will be reprocessed with new logic if re-summarized
- No database or schema changes required

