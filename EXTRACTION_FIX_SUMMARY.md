# Extraction Status Fix Summary

**Date:** 2026-02-12  
**Issue:** Benign PDF parser warnings causing "SUMMARY UNAVAILABLE" stubs  
**Status:** ✅ Fixed and tested

---

## What Changed

### File: `summarize_pdf.py`

**Function:** `determine_extraction_status()` (line ~1400)

**Before:**
```python
critical_error_keywords = ['missing', 'corrupt', 'unreadable', 'invalid']
for error in errors:
    if any(keyword in error_lower for keyword in critical_error_keywords):
        return 'failed'  # "invalid" always caused failed
```

**After:**
```python
fatal_keywords = ['missing', 'corrupt', 'unreadable']
benign_keywords = ['invalid']

extraction_succeeded = (
    chars_total >= 1500 and
    (pages_total == 0 or pages_with_text / pages_total >= 0.4)
)

for error in errors:
    if any(keyword in error for keyword in fatal_keywords):
        return 'failed'
    if any(keyword in error for keyword in benign_keywords):
        if not extraction_succeeded:
            return 'failed'
        else:
            has_benign_errors = True  # Causes 'degraded', not 'failed'
```

---

## The Fix in Plain English

**Benign parser warnings** (like "invalid xref table") are now **only fatal if extraction actually failed**. If the PDF produced substantial text (>= 1500 chars AND >= 40% page coverage), benign warnings result in:

- ✅ Status: `degraded` (summary with warning badge)
- ❌ NOT: `failed` (SUMMARY UNAVAILABLE stub)

**Fatal keywords** (`missing`, `corrupt`, `unreadable`) **always** cause `failed` status, regardless of text output.

---

## Test Results

### New Tests: `test_extraction_quality_benign_errors.py`
```
9/9 passed (0 failed)
```

Key test cases:
- ✅ 30k chars + "invalid xref" → `degraded` (not `failed`)
- ✅ 300 chars + "invalid stream" → `failed` (correct)
- ✅ 30k chars + "corrupt" → `failed` (correct)
- ✅ Multiple benign errors + good text → `degraded`

### Existing Tests: `test_extraction_quality_simple.py`
```
8/8 passed (0 failed)
```

### Critic Pass Tests: `test_critic_pass.py`
```
31/31 passed (0 failed)
```

**Total:** 48/48 tests passing

---

## Validation Command

```bash
cd "c:\Coding Projects\TWIFO_Sharing"

# Run new benign error tests
python test_extraction_quality_benign_errors.py

# Run existing quality tests
python test_extraction_quality_simple.py

# Verify critic pass still works
python test_critic_pass.py
```

---

## Impact Analysis

### Example: Real-world PDF with parser warning

**Scenario:** Financial report PDF with `errors: ["invalid xref table at offset 12345"]`
- Extracted: 30,000 chars
- Pages: 48/50 (96% coverage)
- OCR: Not used

**Before this fix:**
- extraction_status: `failed`
- Result: "SUMMARY UNAVAILABLE" stub
- UI: Hidden from main feed

**After this fix:**
- extraction_status: `degraded`
- Result: Full summary generated
- UI: Summary shown with ⚠️ warning badge
- Meta: `low_confidence: true`, `degradation_reasons: ["parser_warnings (1)"]`

---

## Files Modified

1. ✅ `summarize_pdf.py` — Fixed `determine_extraction_status()`
2. ✅ `test_extraction_quality.py` — Added 8 new test functions (pytest version)
3. ✅ `test_extraction_quality_benign_errors.py` — Created (9 standalone tests)
4. ✅ `test_extraction_quality_simple.py` — Updated (removed Unicode chars)
5. ✅ `BENIGN_ERROR_FIX.md` — Created (detailed documentation)
6. ✅ `EXTRACTION_FIX_SUMMARY.md` — Created (this file)

---

## Linter Status

```
No linter errors found.
```

All imports verified:
```python
from summarize_pdf import (
    compute_extraction_quality,
    determine_extraction_status,
    QUALITY_DEGRADED_CHARS,  # 1500
    QUALITY_DEGRADED_PAGE_RATIO,  # 0.4
)
```

---

## Backward Compatibility

✅ **Fully backward compatible**

- Existing `ok` cases remain `ok`
- Existing truly fatal errors remain `failed`
- **Only change:** Some PDFs that were incorrectly marked `failed` are now correctly marked `degraded`
- No config changes needed
- No schema changes
- No UI changes (degraded status already handled with warning badge)

---

## Quick Reference

| Error Text | Good Extraction (>=1500 chars, >=40% pages) | Poor Extraction |
|------------|---------------------------------------------|-----------------|
| "invalid xref" | `degraded` ⚠️ | `failed` ❌ |
| "invalid stream" | `degraded` ⚠️ | `failed` ❌ |
| "corrupt" | `failed` ❌ | `failed` ❌ |
| "missing" | `failed` ❌ | `failed` ❌ |
| "unreadable" | `failed` ❌ | `failed` ❌ |
| (no errors) | `ok` ✅ | varies by metrics |

---

## Next Steps

None required. The fix is complete and tested. All PDFs will automatically benefit from the improved error handling on their next processing run.

To reprocess existing PDFs that were incorrectly marked as failed:
```bash
cd "c:\Coding Projects\TWIFO_Sharing"
python db_filter_autorun.py 2026-02-01 2026-02-11
```
