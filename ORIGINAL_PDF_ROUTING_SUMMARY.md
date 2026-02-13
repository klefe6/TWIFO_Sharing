# Original PDF Routing Fix - Summary

## Task
Fix the pipeline to ensure the ORIGINAL PDF is always written to `path_manager.originals/` when path_manager is enabled.

## Requirements ✓
1. ✅ In `db_filter_autorun.py`, call `ensure_original_pdf_in_export(...)` with `path_manager=PATH_MANAGER`
2. ✅ In `ingest_dedup.py`, write PDF to `path_manager.original_pdf_path(base + '.pdf')` when provided
3. ✅ Add unit test verifying file in `originals/` and NOT in export root

## Status: ALREADY IMPLEMENTED ✓

The pipeline already implements the correct behavior:

### 1. db_filter_autorun.py (Lines 639-642, 675-678)
**Already passing path_manager correctly:**
```python
final_path, _ = ensure_original_pdf_in_export(
    export_dir, base, src,
    path_manager=PATH_MANAGER if PATH_MANAGER_AVAILABLE else None,
)
```

### 2. ingest_dedup.py (Lines 398-461)
**Already routing to originals/ when path_manager provided:**
```python
# Route destination: originals/ when path_manager enabled, else export root
if path_manager is not None:
    final = path_manager.original_pdf_path(f"{base_name}.pdf")
    final.parent.mkdir(parents=True, exist_ok=True)
else:
    final = export_dir / f"{base_name}.pdf"
```

### 3. Unit Tests ✓
**Two comprehensive test suites:**

#### A. Existing Test: `test_original_pdf_routing.py` (Lines 30-60)
- Tests path_manager routes to `originals/`
- Tests legacy mode routes to export root
- Tests already-exists detection
- Tests missing source handling

**Result: 4/4 tests PASS**

#### B. New Test: `test_ensure_original_in_originals.py` (Created)
- `test_original_pdf_written_to_originals_folder()` - Core requirement verification
- `test_original_pdf_multiple_calls_deterministic()` - No (1) suffixes created
- `test_legacy_mode_without_path_manager()` - Control test
- `test_path_manager_with_dedupe_style_basename()` - Realistic dedupe format
- `test_failure_on_missing_source()` - Error handling

**Result: 5/5 tests PASS**

## Lines Changed
**Zero changes required** - implementation already correct.

## Test Name
- **Primary test:** `test_ensure_original_in_originals.py::test_original_pdf_written_to_originals_folder`
- **Supporting tests:** All 5 tests in `test_ensure_original_in_originals.py`

## Verification
```bash
# Run new test suite
python test_ensure_original_in_originals.py
# Result: 5 passed, 0 failed

# Run existing test suite
python test_original_pdf_routing.py
# Result: 4 passed, 0 failed
```

## Key Behaviors Verified
1. ✅ Original PDF written to `{export_dir}/originals/{base}.pdf` when path_manager enabled
2. ✅ Original PDF written to `{export_dir}/{base}.pdf` when path_manager disabled (legacy)
3. ✅ No files created in export root when path_manager enabled
4. ✅ Deterministic naming (no (1) suffixes on duplicate calls)
5. ✅ Content integrity preserved during copy
6. ✅ Atomic write (.part then rename)

## Conclusion
**The pipeline already works correctly.** No code changes needed. Added comprehensive test suite to prevent regression.
