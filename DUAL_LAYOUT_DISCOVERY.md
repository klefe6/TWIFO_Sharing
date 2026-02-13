# Dual Layout PDF Discovery - Implementation Summary

**Date:** 2026-02-12  
**Author:** Kevin Lefebvre

## Goal
Enable the TWIFO web interface table to list PDFs from BOTH:
1. New layout: `originals/` folder (managed by `TWIFOPathManager`)
2. Legacy layout: Root `FILES_DIR` (old files not yet migrated)

## Changes Made

### 1. Updated File Discovery Logic (`twifo.py`, lines 1724-1875)

**Before:**
- If `PATH_MANAGER` enabled → only scan `originals/`
- Else → only scan root folder
- **Problem:** New layout files were invisible; legacy files disappeared after migration

**After:**
- If `PATH_MANAGER` enabled:
  1. Scan `PATH_MANAGER.list_originals()` (new layout)
  2. Scan root `FILES_DIR` for `.pdf` files (legacy layout)
  3. Skip subdirectories (`artifacts/`, `rollups/`, etc.)
  4. Deduplicate by basename (prefer `originals/` if same file exists in both)
- Else (fallback):
  - Legacy-only scanning for backward compatibility

### 2. Key Features

#### Deduplication
- Uses `seen_basenames` set to track unique basenames
- If same basename exists in BOTH `originals/` and root:
  - Prioritize `originals/` version (processed first)
  - Skip root version (already seen)

#### Subdirectory Exclusion
- Only scans **files** in root `FILES_DIR`
- Skips directories using `os.path.isdir()` check
- Prevents duplicate scanning of `originals/`, `artifacts/`, `rollups/`

#### Stable Basename Computation
- Uses `os.path.splitext(fname)[0]` for deterministic basename
- Works for both naming conventions:
  - New: `20260212__BOA__report__abc123.pdf` → basename: `20260212__BOA__report__abc123`
  - Legacy: `BOA_Report_20260212_w.pdf` → basename: `BOA_Report_20260212_w`

### 3. Testing

Created `test_dual_layout_discovery.py` with 4 test cases:

1. **Dual layout discovery** - Finds PDFs in both locations
2. **Deduplication** - Prioritizes `originals/` over root
3. **Legacy-only mode** - Fallback when `path_manager` not available
4. **Empty directories** - Handles gracefully with no errors

**Results:** All 4 tests pass ✓

## Benefits

1. **Smooth Migration Path:** New files go to `originals/`, legacy files remain visible
2. **No Breaking Changes:** Path manager mode and legacy mode both work
3. **Automatic Deduplication:** No duplicate entries if same file exists in both locations
4. **Correct Artifact Resolution:** Respects both layout conventions for summary lookups

## Files Modified

- `twifo.py` (lines 1724-1875): Updated file discovery loop

## Files Created

- `test_dual_layout_discovery.py`: Comprehensive test suite

## Compatibility

- ✓ Works with `PATH_MANAGER` enabled (dual scanning)
- ✓ Works without `PATH_MANAGER` (legacy-only mode)
- ✓ Preserves existing filters (category, date, title search, product)
- ✓ Maintains batch PDF content search functionality
- ✓ Compatible with summary view routing (basename still available)
