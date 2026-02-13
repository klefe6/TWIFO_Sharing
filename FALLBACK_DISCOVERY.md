# Fallback Discovery from Artifacts - Implementation Summary

**Date:** 2026-02-12  
**Author:** Kevin Lefebvre

## Goal
Enable the TWIFO web interface to remain fully functional even when:
- Original PDFs are missing from `originals/` folder
- Naming conventions don't match cleanly between PDFs and artifacts
- Summaries exist but corresponding PDFs were never ingested

## Problem Statement
Previously, the table could only display items when a PDF was found first. If summaries existed in `artifacts/*/sum.json` but the corresponding PDF was missing or had mismatched naming, those summaries would be invisible to users.

## Solution
Implemented a robust **fallback discovery system** that:
1. Triggers when few/zero PDFs are found (threshold: < 5 PDFs)
2. Scans `artifacts/*/sum.json` to build table rows from metadata
3. Deduplicates with PDF-based discovery (skips already-seen basenames)
4. Applies all existing filters (category, date range, title search)
5. Links table rows to `/summary/<basename>` where summary view can load directly from `artifacts/<basename>/sum.json`

## Changes Made

### 1. New Function: `discover_from_artifacts()` (`twifo.py`, lines 413-597)

**Location:** Added after `has_summary_file()` helper

**Purpose:** Scan `artifacts/` directory and build table row candidates from `sum.json` metadata

**Key Features:**
- Extracts metadata from `sum.json`: title, provider, published_date, horizon, products
- Maps provider to category using existing `detect_category()` function
- Applies date range, category, and title search filters
- Computes scores based on content richness (tldr length, trade ideas, products)
- Returns same structure as PDF-based discovery for consistency
- Flags entries with `_discovered_from_artifacts: True` for debugging

**Parameters:**
- `artifacts_dir`: Path to artifacts/ directory
- `files_dir`: Root FILES_DIR for path resolution
- `seen_basenames`: Set of basenames already discovered (avoids duplicates)
- `selected`: Category filter
- `start_date`, `end_date`: Date range filters (ISO format)
- `tt`: Title search term

**Returns:**
- List of candidate dicts (same structure as PDF-discovered candidates)

### 2. Fallback Trigger Logic (`twifo.py`, lines 1877-1891)

**Location:** After initial PDF discovery, before combining with rollups

**Logic:**
```python
if PATH_MANAGER_AVAILABLE and PATH_MANAGER and len(candidate_files) < 5:
    print(f"[FALLBACK] Only {len(candidate_files)} PDFs found, scanning artifacts...")
    fallback_candidates = discover_from_artifacts(
        PATH_MANAGER.artifacts_dir,
        FILES_DIR,
        seen_basenames=set(os.path.splitext(f['fname'])[0] for f in candidate_files),
        selected=selected,
        start_date=start_date,
        end_date=end_date,
        tt=tt
    )
    candidate_files.extend(fallback_candidates)
    print(f"[FALLBACK] Added {len(fallback_candidates)} artifacts-only entries")
```

**Trigger Condition:**
- `PATH_MANAGER` is available (new layout enabled)
- Fewer than 5 PDFs discovered via normal scanning
- Ensures fallback only runs when needed (minimal performance impact)

### 3. Summary View Compatibility (`summary_view.py` - no changes needed)

**Existing Behavior:**
- `load_summary_json()` already works with just `basename`
- Loads from `artifacts/<basename>/sum.json` directly
- Does NOT require original PDF to exist
- This existing design makes fallback discovery seamless

### 4. Table Row Structure

**Fallback-discovered rows include:**
- `path`: Fake path (original PDF may not exist)
- `fname`: Synthetic filename (`<basename>.pdf`)
- `basename`: Artifact folder name (used for `/summary/<basename>` routing)
- `has_summary`: Always `True` (we found `sum.json`)
- `summary_json_filename`: `artifacts/<basename>/sum.json`
- `summary_pdf_filename`: `artifacts/<basename>/sum.pdf` (if exists)
- `_discovered_from_artifacts`: `True` flag for debugging

## Benefits

1. **Resilient to Missing PDFs:** App works even if originals are lost/deleted
2. **Handles Naming Mismatches:** Doesn't rely on PDF filename matching artifact folder name
3. **Smooth Migration:** Works during transition from legacy to new layout
4. **Minimal Performance Impact:** Only triggers when few PDFs found
5. **No Breaking Changes:** Existing PDF-based discovery still works normally
6. **Filter Compatibility:** All filters (date, category, title) work on fallback entries
7. **Consistent UI:** Fallback rows look identical to normal rows in table

## Testing

Created `test_fallback_discovery.py` with 5 comprehensive tests:
1. ✓ Basic fallback discovery from artifacts
2. ✓ Deduplication with PDF-based discovery
3. ✓ Filters applied correctly (date, category, title)
4. ✓ Summary view loads without PDF
5. ✓ Table rows link correctly to `/summary/<basename>`

**All tests pass successfully.**

## Edge Cases Handled

1. **Duplicate Prevention:** Uses `seen_basenames` set to skip artifacts already found via PDF
2. **Missing Metadata:** Gracefully handles missing/invalid `sum.json` fields with defaults
3. **Date Parsing Failures:** Skips entries if date filter active but date unparseable
4. **Empty Artifacts Directory:** Returns empty list (no errors)
5. **Corrupt JSON:** Catches exceptions and logs warnings without crashing

## Usage Example

**Scenario:** User has 100 summaries in `artifacts/` but only 3 PDFs in `originals/` (most originals lost)

**Before Fix:**
- Table shows only 3 items
- 97 summaries are invisible
- Users think processing failed

**After Fix:**
- Table shows 3 PDF-based items + 97 artifact-based items = 100 total
- Clicking any row opens summary view (loads from `artifacts/<basename>/sum.json`)
- Works seamlessly regardless of original PDF presence

## Files Modified

- `twifo.py` (lines 413-597, 1877-1891): Added fallback discovery system

## Files Created

- `test_fallback_discovery.py`: Comprehensive test suite
- `FALLBACK_DISCOVERY.md`: This documentation

## Configuration

**Trigger Threshold:** `< 5 PDFs` (hardcoded in line 1877)

Can be adjusted by changing:
```python
if len(candidate_files) < 5:  # Change threshold here
```

**Recommendation:** Keep threshold low (< 10) to avoid unnecessary scanning on systems with many PDFs.
