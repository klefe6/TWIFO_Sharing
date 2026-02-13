# Benign Parser Warning Fix

**Last Updated:** 2026-02-12

## Problem

Previously, `determine_extraction_status()` treated all errors containing the word "invalid" as **fatal**, causing `extraction_status="failed"` even when extraction succeeded with substantial usable text.

This resulted in "SUMMARY UNAVAILABLE" stubs for PDFs that:
- Extracted 30,000+ chars of clean text
- Had 96%+ page coverage
- But had benign parser warnings like "invalid xref table" or "invalid stream object"

These are **parser warnings**, not extraction failures. The extraction succeeded; the warning just indicates the PDF parser had to work around minor structural issues.

---

## Solution

Updated `determine_extraction_status()` (line ~1400 in `summarize_pdf.py`) to distinguish between:

### Fatal Keywords (always cause `"failed"`)
- `missing` — file or critical data is absent
- `corrupt` — file structure is damaged
- `unreadable` — cannot parse at all

### Benign Keywords (only fatal if extraction actually failed)
- `invalid` — parser warnings (xref table, stream, object, etc.)

**New Logic:**

```python
extraction_succeeded = (
    chars_total >= 1500 and  # >= QUALITY_DEGRADED_CHARS
    (pages_total == 0 or pages_with_text / pages_total >= 0.4)  # >= QUALITY_DEGRADED_PAGE_RATIO
)

if 'invalid' in error:
    if not extraction_succeeded:
        return 'failed'  # Benign error + low output = failed
    else:
        has_benign_errors = True  # Note for degraded check
```

If extraction produced substantial text (>= 1500 chars AND >= 40% page coverage), benign warnings become **degradation factors** instead of fatal errors.

---

## Impact

| Scenario | Before | After |
|----------|--------|-------|
| 30k chars, 96% pages, "invalid xref" | ❌ **failed** | ✅ **degraded** |
| 300 chars, 10% pages, "invalid stream" | ❌ **failed** | ❌ **failed** (correct) |
| 30k chars, 96% pages, "corrupt" | ❌ **failed** | ❌ **failed** (correct) |
| 30k chars, 96% pages, no errors | ✅ **ok** | ✅ **ok** |

**Result:** PDFs with benign parser warnings but successful extraction now get summarized with a warning badge (degraded) instead of producing empty stubs (failed).

---

## Test Coverage

### New tests (9 tests, all passing)

File: `test_extraction_quality_benign_errors.py`

1. ✅ `benign_parser_warning_with_good_extraction` — 30k chars + benign error → degraded (not failed)
2. ✅ `benign_parser_warning_with_poor_extraction` — 300 chars + benign error → failed
3. ✅ `fatal_error_always_fails` — fatal keywords always cause failed
4. ✅ `multiple_benign_warnings_with_good_extraction` — multiple benign → degraded
5. ✅ `benign_warning_at_threshold` — exactly at threshold (1500 chars, 40% pages)
6. ✅ `mixed_fatal_and_benign_errors` — any fatal error → failed
7. ✅ `no_errors_good_extraction` — no errors → ok
8. ✅ `single_benign_warning_good_extraction` — 50k chars + benign → degraded
9. ✅ `no_pages_but_good_text_with_benign_error` — edge case (no page count)

### Existing tests (8 tests, all passing)

File: `test_extraction_quality_simple.py` — all existing tests continue to pass.

---

## Usage

No configuration changes needed. The fix is automatic and applies to all PDF extractions.

To test manually:

```python
from summarize_pdf import compute_extraction_quality

# Good extraction with benign error
meta = {
    'pages_total': 50,
    'pages_with_text': 48,
    'chars_total': 30000,
    'ocr_used': False,
    'errors': ['invalid xref table'],
    'method_used': 'pypdf'
}

score, status = compute_extraction_quality(meta)
# Result: status='degraded', score=73 (not 'failed')
```

---

## Related Files

- **Implementation:** `summarize_pdf.py` — `determine_extraction_status()` (line ~1400)
- **Tests:** `test_extraction_quality_benign_errors.py` (9 new tests)
- **Tests:** `test_extraction_quality_simple.py` (8 existing tests, updated for compatibility)
- **Tests:** `test_extraction_quality.py` (pytest version, 8 new test functions added)

---

## Constants

```python
QUALITY_DEGRADED_CHARS = 1500        # Minimum chars for "extraction succeeded"
QUALITY_DEGRADED_PAGE_RATIO = 0.4   # Minimum page coverage (40%)
```

If `chars_total >= 1500` AND `pages_with_text/pages_total >= 0.4`, benign errors are not fatal.
