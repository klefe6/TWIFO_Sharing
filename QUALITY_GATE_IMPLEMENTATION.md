# Quality Gate Implementation

**Purpose:** Prevent low-quality/templated LLM summaries from being written as normal outputs  
**Author:** Kevin Lefebvre  
**Date:** 2026-01-26  

## Overview

A strict post-LLM quality gate has been implemented to detect and fail templated, low-information, or garbage summaries before they are written to disk. This prevents the TWIFO pipeline from producing normal-looking but useless summaries.

## Implementation Details

### 1. Quality Detection Function

**Location:** `summarize_pdf.py` and `summarize_pdf_new.py`

```python
def is_low_quality_summary(sum_json: dict) -> tuple[bool, str]
```

**Detects:**
- **Too few unique bullets**: Less than 3 unique informative bullets
- **Excessive duplication**: More than 50% of bullets are exact duplicates
- **Generic placeholders**: More than 40% contain phrases like "pending analysis", "monitor key levels", "data releases", etc.
- **Suspiciously short bullets**: More than 60% are under 20 characters

**Returns:** `(is_low_quality: bool, reason: str)`

### 2. Pipeline Integration

**Location:** Both `summarize_pdf()` and `summarize_text()` functions

The quality gate is called **after** format validation but **before** writing JSON/TXT/PDF:

```python
# Summarize (or load from failed stub on exception)
sum_json = llm_summarize_to_json(text, meta=meta, model=model)

# Quality gate: detect low-quality/templated output
is_low_quality, quality_reason = is_low_quality_summary(sum_json)
if is_low_quality:
    print(f"[QUALITY GATE] Summary failed quality check: {quality_reason}")
    # Mark as failed
    sum_json["extraction"]["status"] = "failed"
    sum_json["extraction"]["reason"] = f"low_quality_output: {quality_reason}"
    # Replace sections with empty unified failure stub
    sum_json["sections"] = {
        "what_moved_today": [],
        "what_can_move_tomorrow": [],
        "trade_ideas": [],
        "tldr": [],
        "what_occurred": [],
        "forward_watch": [],
        "warnings": [],
        "tips_reminders": [],
        "cross_asset_impacts": [],
        "scenarios": []
    }

# Write files (will render as failure if status != "ok")
_write_json(json_path, sum_json)
_write_txt(txt_path, render_sum_txt(sum_json))
```

### 3. Failure Rendering

**TXT Rendering** (`summarize_pdf.py`, `summarize_pdf_new.py`):
- `render_sum_txt()` checks `extraction.status`
- If status != "ok", renders clear failure message instead of normal summary
- Shows extraction status, reason, and possible causes

**PDF Rendering** (`summary_render.py`):
- `render_summary_pdf()` checks `extraction.status` early
- Calls `_render_failed_summary_pdf()` for failed extractions
- Creates professional failure page with:
  - Red "SUMMARY UNAVAILABLE" title
  - Highlighted error box with status and reason
  - List of possible causes
  - Clear statement that no summary will be generated

### 4. Unified Failure Schema

All failures (OCR, extraction, quality gate) now use the **same deterministic schema**:

**Required keys (all empty lists):**
- Primary: `what_moved_today`, `what_can_move_tomorrow`, `trade_ideas`
- Legacy: `tldr`, `what_occurred`, `forward_watch`, `warnings`, `tips_reminders`, `cross_asset_impacts`, `scenarios`

**Extraction metadata:**
```json
{
  "extraction": {
    "status": "failed",
    "reason": "low_quality_output: excessive_placeholders: 100% of bullets are generic placeholders"
  }
}
```

## Testing

### Regression Tests

**File:** `test_quality_gate.py`

**Tests:**
1. Too few unique bullets (< 3 unique items)
2. Excessive duplication (> 50% duplicates)
3. Excessive placeholders (> 40% generic phrases)
4. Excessive short bullets (> 60% under 20 chars)
5. Valid summary passes gate
6. Neutral products with "no direct trade idea" allowed
7. Completely empty summary fails

**Run:** `python test_quality_gate.py`

**Result:** All 7 tests pass ✅

### Integration Tests

**File:** `test_quality_gate_integration.py`

**Tests:**
1. Quality gate integration in summarization pipeline
2. Failed extraction TXT rendering

**Run:** `python test_quality_gate_integration.py`

**Result:** Integration tests pass ✅

## Files Modified

1. **`summarize_pdf.py`**
   - Added `is_low_quality_summary()` function (~95 lines)
   - Updated `render_sum_txt()` to handle failed extractions (~25 lines)
   - Integrated quality gate in `summarize_text()` and `summarize_pdf()` (~20 lines each)

2. **`summarize_pdf_new.py`**
   - Added `is_low_quality_summary()` function (~95 lines)
   - Updated `render_sum_txt()` to handle failed extractions (~25 lines)
   - Integrated quality gate in `summarize_text()` and `summarize_pdf()` (~20 lines each)

3. **`summary_render.py`**
   - Added `_render_failed_summary_pdf()` function (~100 lines)
   - Updated `render_summary_pdf()` to check extraction status (~2 lines)

4. **`test_quality_gate.py`** (new file)
   - 7 regression tests for quality detection (~300 lines)

5. **`test_quality_gate_integration.py`** (new file)
   - 2 integration tests (~100 lines)

## Behavior Changes

### Before
- Low-quality LLM outputs were written as normal summaries
- Users received professional-looking but useless summaries
- No detection of templated/placeholder content

### After
- Low-quality outputs are **detected and failed**
- `extraction.status` set to `"failed"`
- `extraction.reason` contains detailed failure reason (e.g., `"low_quality_output: excessive_placeholders: 100%"`)
- TXT files show clear "SUMMARY UNAVAILABLE" message
- PDF files render professional failure page
- Sections replaced with empty unified failure stub

## Quality Thresholds

**Current settings:**
- Minimum unique bullets: 3
- Maximum duplication rate: 50%
- Maximum placeholder rate: 40%
- Maximum short bullet rate: 60%

These can be tuned based on production feedback.

## Special Cases

### Neutral Products
Neutral trade ideas with `"No direct trade idea from this article"` are **allowed** and don't trigger placeholder detection. This is valid for products not mentioned in the article.

### Empty Summaries
Completely empty summaries (all sections empty) fail with `"too_few_unique_bullets: only 0 unique bullets found"`.

## Production Usage

Quality gate runs automatically on **every** summary:
1. External PDFs via `db_filter_autorun.py`
2. Text summaries via `summarize_text()`
3. Rollup generation (inherits from article summaries)

No configuration required - it's always active.

## Future Enhancements

Potential improvements:
1. Configurable thresholds via environment variables
2. Machine learning-based quality scoring
3. Detection of hallucinated price levels
4. Semantic similarity checks for duplicate content
5. Quality metrics dashboard

## Constraints Met

✅ Minimal file changes (only 5 files modified)  
✅ No new folders created  
✅ No new multi-stage LLM passes  
✅ TOON/OCR behavior unchanged  
✅ Fail-closed by default  
✅ Unified failure schema across all failure paths  
✅ Regression tests included  
