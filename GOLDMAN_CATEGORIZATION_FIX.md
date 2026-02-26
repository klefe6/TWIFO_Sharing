# Goldman Sachs Categorization Fix

## Problem

Goldman Sachs articles were being labeled as category "Others" in Daily View buttons and Daily Summary instead of showing "Goldman Sachs" or "GS".

## Root Cause

The `PREFIX_MAP` in both `twifo.py` and `twifo_app.py` only had the `GM_` prefix mapped to "Goldman Sachs". However, some Goldman files use the `GS_` prefix instead, which was not in the map, causing them to fall through to the default "Others" category.

## Solution

Added `GS_` prefix to `PREFIX_MAP` in both files, mapping it to "Goldman Sachs".

---

## Detection Rule

**Rule**: Files with prefix `GS_` or `GM_` are categorized as "Goldman Sachs"

**Implementation**:
- `PREFIX_MAP["GS_"] = "Goldman Sachs"`
- `PREFIX_MAP["GM_"] = "Goldman Sachs"`
- `detect_category()` checks if filename starts with `GS_` or `GM_`
- `_detect_provider()` extracts provider code from folder name and maps via `PREFIX_MAP`

---

## Changes Made

### File 1: `twifo.py` (line ~84)

**Before**:
```python
PREFIX_MAP = {
    "BOA_":   "Bank of America",
    "BA_":    "Barclays",
    "BR_":    "BlackRock",
    "DB_":    "Deutsche Bank",
    "GM_":    "Goldman Sachs",
    "HT_":    "HighTower Research",
    ...
}
```

**After**:
```python
PREFIX_MAP = {
    "BOA_":   "Bank of America",
    "BA_":    "Barclays",
    "BR_":    "BlackRock",
    "DB_":    "Deutsche Bank",
    "GM_":    "Goldman Sachs",
    "GS_":    "Goldman Sachs",  # Alternative prefix for Goldman Sachs
    "HT_":    "HighTower Research",
    ...
}
```

### File 2: `twifo_app.py` (line ~30)

**Before**:
```python
PREFIX_MAP = {
    "BOA_":   "Bank of America",
    "BA_":    "Barclays",
    "BR_":    "BlackRock",
    "DB_":    "Deutsche Bank",
    "GM_":    "Goldman Sachs",
    "HT_":    "HighTower Research",
    ...
}
```

**After**:
```python
PREFIX_MAP = {
    "BOA_":   "Bank of America",
    "BA_":    "Barclays",
    "BR_":    "BlackRock",
    "DB_":    "Deutsche Bank",
    "GM_":    "Goldman Sachs",
    "GS_":    "Goldman Sachs",  # Alternative prefix for Goldman Sachs
    "HT_":    "HighTower Research",
    ...
}
```

---

## How It Works

### Daily View (Article List)

1. `get_artifacts_for_date()` in `twifo_app.py` scans artifact folders
2. For each folder (e.g., `20260211__GS__commodities_weekly__abc123`):
   - `_parse_folder_segments()` extracts provider code: `"GS"`
   - `_detect_provider()` looks up `"GS_"` in `PREFIX_MAP` → `"Goldman Sachs"`
3. Provider is stored in artifact metadata: `art["provider"] = "Goldman Sachs"`
4. `populate_daily_view_sidebar()` uses `art["provider"]` for button label

### Daily Summary (Rollup Display)

1. Rollup JSON includes article metadata with provider field
2. UI renders provider/category pills using the provider value
3. Provider is already set to "Goldman Sachs" from ingestion

### Main Table (Legacy PDFs)

1. `detect_category()` in `twifo.py` checks filename prefix
2. For `GS_commodities_weekly_20260211_w.pdf`:
   - Checks if starts with `"GS_"` → Yes
   - Returns `PREFIX_MAP["GS_"]` → `"Goldman Sachs"`
3. Category is used for filtering and display

---

## Test Results

**File**: `test_goldman_categorization.py`

```
TEST 1: PREFIX_MAP includes GS_ prefix
  [OK] GS_ -> Goldman Sachs
  [OK] GM_ -> Goldman Sachs

TEST 2: detect_category() recognizes GS_ files
  [OK] GS_commodities_weekly_20260211_w.pdf -> Goldman Sachs
  [OK] GM_commodities_weekly_20260211_w.pdf -> Goldman Sachs
  [OK] GS_rates_daily_20260211_d.pdf -> Goldman Sachs
  [OK] GM_rates_daily_20260211_d.pdf -> Goldman Sachs

TEST 3: _detect_provider() recognizes Goldman folders
  [OK] 20260211__GS__commodities_weekly__abc123 -> Goldman Sachs
  [OK] 20260211__GM__commodities_weekly__abc123 -> Goldman Sachs

TEST 4: _parse_folder_segments() extracts provider code
  [OK] 20260211__GS__commodities_weekly__abc123 -> provider_code=GS
  [OK] 20260211__GM__commodities_weekly__abc123 -> provider_code=GM

TEST 5: Goldman files are NOT categorized as 'Others'
  [OK] GS_commodities_weekly_20260211_w.pdf -> Goldman Sachs (NOT Others)
  [OK] GM_commodities_weekly_20260211_w.pdf -> Goldman Sachs (NOT Others)

ALL TESTS PASSED
```

---

## Verification

### Daily View

**Before Fix**:
- Goldman article button shows: `Others | Weekly | Feb 11`

**After Fix**:
- Goldman article button shows: `Goldman Sachs | Weekly | Feb 11`

### Daily Summary

**Before Fix**:
- Article pill shows: `Others`

**After Fix**:
- Article pill shows: `Goldman Sachs`

---

## Files Changed

**Modified**:
1. `twifo.py` (line ~84) - Added `"GS_": "Goldman Sachs"` to `PREFIX_MAP`
2. `twifo_app.py` (line ~30) - Added `"GS_": "Goldman Sachs"` to `PREFIX_MAP`

**Added**:
3. `test_goldman_categorization.py` - Test fixture for Goldman categorization

**NOT Modified**:
- UI components (no changes needed - they already use provider field)
- Rollup generation logic (already uses provider from metadata)
- Daily Summary rendering (already uses provider from rollup JSON)

---

## Impact

✅ **Daily View**: Goldman articles now show "Goldman Sachs" instead of "Others"
✅ **Daily Summary**: Goldman articles now show "Goldman Sachs" pill
✅ **Main Table**: Goldman PDFs now categorized correctly
✅ **Filtering**: Goldman articles now appear in "Goldman Sachs" filter, not "Others"
✅ **Backward Compatible**: Existing `GM_` prefix still works
✅ **No UI Changes**: Fix is upstream in metadata mapping only

---

## Deployment

✅ No database migrations
✅ No new dependencies
✅ No configuration changes
✅ Backward compatible (both `GM_` and `GS_` work)
✅ No restart required (Dash hot-reloads)

---

**Status**: ✅ COMPLETE - Goldman Sachs articles now categorized correctly

