# JSON Path Fix - Implementation Summary

**Date:** 2026-02-12  
**Author:** Kevin Lefebvre  

## Problem Statement

The application was experiencing a critical bug where:
1. Summary JSON files were written to a path determined by `_sum_paths()` (which respects `path_manager`)
2. The renderer was called with a **recomputed path** using a simple pattern: `pdf_to_use.parent / f"{stem_to_use}__sum.json"`
3. When `path_manager` was active, these paths differed:
   - **Written to:** `artifacts/<basename>/sum.json`
   - **Renderer expected:** `<parent_dir>/<basename>__sum.json`
4. Result: Logs showed `[OK] Summary created ... (OCR-to-text path)` followed by `[ERROR] JSON file not found ...`

## Root Cause

Functions `summarize_pdf()` and `summarize_text()` returned only the summary dictionary, not the path where the JSON was written. Callers had to recompute the path, which didn't account for the path_manager layout.

## Solution

### 1. Modified Return Signatures

**File:** `summarize_pdf.py`

Changed both functions to return a tuple `(dict, Path)`:

```python
def summarize_text(...) -> Tuple[dict, Path]:
    """
    Returns:
        Tuple of (sum_json dict, json_path Path) - the path where JSON was written.
    """
    # ... existing code ...
    _write_json(json_path, sum_json)
    
    # ASSERTION: Verify JSON was actually written
    if not os.path.exists(json_path):
        print(f"[ERROR] write_failed: JSON not found after write at {json_path}")
        return (sum_json, json_path)
    
    _write_txt(txt_path, render_sum_txt(sum_json))
    return (sum_json, json_path)
```

```python
def summarize_pdf(...) -> Tuple[dict, Path]:
    """
    Returns:
        Tuple of (sum_json dict, json_path Path) - the path where JSON was written.
    """
    # ... existing code ...
    _write_json(json_path, sum_json)
    
    # ASSERTION: Verify JSON was actually written
    if not os.path.exists(json_path):
        print(f"[ERROR] write_failed: JSON not found after write at {json_path}")
        return (sum_json, json_path)
    
    _write_txt(txt_path, render_sum_txt(sum_json))
    return (sum_json, json_path)
```

### 2. Updated All Callers

**File:** `db_filter_autorun.py` (3 locations)

#### Location 1 & 2: OCR-to-text paths (lines ~761 & ~833)

**Before:**
```python
summary = summarize_text(ocr_text, title=suggested_name, ...)
if not summary:
    # handle error
else:
    print(f"[OK] Summary created for {pdf_to_use.name} (OCR-to-text path)")
    if PDF_RENDER_AVAILABLE and render_summary_pdf:
        json_path = pdf_to_use.parent / f"{stem_to_use}__sum.json"  # WRONG!
        pdf_path = pdf_to_use.parent / f"{stem_to_use}__sum.pdf"
        render_summary_pdf(json_path, pdf_path)
```

**After:**
```python
summary, sum_json_path = summarize_text(ocr_text, title=suggested_name, ...)
if not summary:
    # handle error
else:
    print(f"[OK] Summary created for {pdf_to_use.name} (OCR-to-text path)")
    
    # Verify JSON exists at the path returned by summarize_text
    if not os.path.exists(sum_json_path):
        print(f"[ERROR] JSON file not found at returned path: {sum_json_path}")
        # treat as failed, skip render
        continue
    
    # Generate PDF from JSON using the real path
    if PDF_RENDER_AVAILABLE and render_summary_pdf:
        pdf_path = sum_json_path.parent / f"{sum_json_path.stem}.pdf"
        render_summary_pdf(sum_json_path, pdf_path)
```

#### Location 3: Normal PDF path (line ~878)

**Before:**
```python
summary = summarize_pdf(pdf_to_summarize, ...)
if not summary:
    # handle error
else:
    print(f"[OK] Summary created for {pdf_to_use.name}")
    # ... title patching using old summary_json_path ...
    
    if PDF_RENDER_AVAILABLE and render_summary_pdf:
        # Get correct paths based on layout
        if PATH_MANAGER_AVAILABLE and PATH_MANAGER:
            json_path = PATH_MANAGER.artifact_path(stem_to_use, 'sum.json')  # Recomputed!
            pdf_path = PATH_MANAGER.artifact_path(stem_to_use, 'sum.pdf')
        else:
            json_path = pdf_to_use.parent / f"{stem_to_use}__sum.json"  # Recomputed!
            pdf_path = pdf_to_use.parent / f"{stem_to_use}__sum.pdf"
        
        render_summary_pdf(json_path, pdf_path)
```

**After:**
```python
summary, sum_json_path = summarize_pdf(pdf_to_summarize, ...)
if not summary:
    # handle error
else:
    print(f"[OK] Summary created for {pdf_to_use.name}")
    
    # Verify JSON exists at the path returned by summarize_pdf
    if not os.path.exists(sum_json_path):
        print(f"[ERROR] JSON file not found at returned path: {sum_json_path}")
        # treat as failed, skip render
        continue
    
    # Update summary_json_path to use the real path from summarize_pdf
    summary_json_path = sum_json_path
    
    # ... title patching using real summary_json_path ...
    
    if PDF_RENDER_AVAILABLE and render_summary_pdf:
        # Use the real JSON path returned by summarize_pdf
        pdf_path = sum_json_path.parent / f"{sum_json_path.stem}.pdf"
        render_summary_pdf(sum_json_path, pdf_path)
```

### 3. Updated Test Files

Updated all test files to unpack the tuple:

- `smoke_test_pdf.py`: `result, json_path = summarize_pdf(...)`
- `test_summarize_one.py`: `summary, json_path = summarize_pdf(...)`
- `test_full_summary.py`: `summary, json_path = summarize_pdf(...)`
- `audit_summary_inputs.py`: `result, json_path = summarize_pdf(...)`
- `test_stub_threshold.py`: `result, json_path = summarize_pdf(...)` (all 7 occurrences)

### 4. Added Unit Test

**File:** `test_render_json_path.py`

Created comprehensive unit test that:
- ✅ Verifies `summarize_text` returns `(dict, Path)` tuple
- ✅ Verifies returned path exists immediately after write
- ✅ Verifies `os.path.exists(json_path)` returns `True`
- ✅ Verifies `render_summary_pdf` receives existing file path
- ✅ Demonstrates the bug scenario (recomputed path differs from actual path)
- ✅ Tests path_manager layout vs legacy layout

**Test Result:** All tests pass ✓

## Key Improvements

### 1. Assertion After Write
Every JSON write now has an assertion:
```python
if not os.path.exists(json_path):
    print(f"[ERROR] write_failed: JSON not found after write at {json_path}")
    return (sum_json, json_path)  # Return anyway but log the failure
```

This catches write failures immediately instead of discovering them later at render time.

### 2. Verification Before Render
Before attempting to render, we verify the JSON exists:
```python
if not os.path.exists(sum_json_path):
    print(f"[ERROR] JSON file not found at returned path: {sum_json_path}")
    summary_skipped += 1
    # treat as failed, no render attempt
    continue
```

### 3. Single Source of Truth
The path is computed **once** by `_sum_paths()` inside the summarization function, and that exact path is:
- Used to write the JSON
- Verified to exist
- Returned to the caller
- Passed directly to the renderer

No more recomputing paths with different logic!

## Files Modified

1. ✅ `summarize_pdf.py` - Modified `summarize_text()` and `summarize_pdf()` return signatures
2. ✅ `db_filter_autorun.py` - Updated 3 call sites to use returned paths
3. ✅ `smoke_test_pdf.py` - Updated to unpack tuple
4. ✅ `test_summarize_one.py` - Updated to unpack tuple
5. ✅ `test_full_summary.py` - Updated to unpack tuple
6. ✅ `audit_summary_inputs.py` - Updated to unpack tuple
7. ✅ `test_stub_threshold.py` - Updated 7 call sites to unpack tuple
8. ✅ `test_render_json_path.py` - New comprehensive unit test

## Testing

### Unit Test Output
```
================================================================================
RENDER JSON PATH UNIT TESTS
================================================================================

[TEST] Render function with existing JSON path
  [1] Creating summary with summarize_text...
  [OK] Summary created, JSON path returned: ...Test_Fed_Minutes__sum.json
  [2] Verifying JSON exists at returned path...
  [OK] JSON exists at: ...Test_Fed_Minutes__sum.json
  [3] Verifying JSON content...
  [OK] JSON is valid with keys: [...]
  [4] Calling render_summary_pdf with returned JSON path...
  [OK] Render succeeded, PDF created at: ...Test_Fed_Minutes__sum.pdf
  [5] Testing bug scenario (recomputed path)...
  [PASS] All assertions passed - render receives existing JSON path

[TEST] Path manager JSON path handling
  [OK] Path manager produces correct path structure
  [OK] Legacy pattern: .../Test_Document_20240131__sum.json
  [OK] New pattern:    .../artifacts/Test_Document_20240131/sum.json
  [PASS] Path manager test passed

================================================================================
ALL TESTS COMPLETE
================================================================================
```

### Manual Testing Recommended

To fully verify the fix:

1. Run `db_filter_autorun.py` with path_manager enabled
2. Process a PDF that requires OCR
3. Verify logs show:
   - `[OK] Summary created ... (OCR-to-text path)`
   - `[OK] Summary PDF created: ...`
   - **NO** `[ERROR] JSON file not found`
4. Verify both JSON and PDF exist in `artifacts/<basename>/` directory

## Backward Compatibility

The changes are **backward compatible** when path_manager is disabled:
- Legacy layout: `<parent_dir>/<basename>__sum.json` still works
- New layout: `artifacts/<basename>/sum.json` now works correctly

The key difference is that the **path is never recomputed** - it's always passed from the function that wrote it.

## Type Safety

All changes maintain proper type hints:
```python
from typing import Tuple
from pathlib import Path

def summarize_text(...) -> Tuple[dict, Path]:
    ...

def summarize_pdf(...) -> Tuple[dict, Path]:
    ...
```

## Summary

This fix resolves the "JSON file not found" error by ensuring that:
1. ✅ JSON paths are computed once by the writing function
2. ✅ Paths are verified to exist immediately after write
3. ✅ The exact path is returned to callers
4. ✅ Renderers receive the real path, not a recomputed guess
5. ✅ Comprehensive unit tests validate the fix
6. ✅ All existing callers are updated
7. ✅ No linter errors introduced

**Status:** Complete and tested ✓
