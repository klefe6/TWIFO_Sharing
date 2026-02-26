# Daily View Title & Frequency Badge Fixes

**Date:** 2026-02-14  
**Purpose:** Fix frequency badge and title formatting in Daily View sidebar

## Issues Fixed

### 1. Frequency Badge Always Showing "Unknown"

**Problem:**  
The green frequency badge always displayed "Unknown" even when filenames contained frequency codes like `_w`, `_d`, etc.

**Root Cause:**  
- `sum.json` files had `meta.horizon = "u"` (unknown)
- No fallback logic to extract frequency from filename/folder name
- `twifo_app.py` didn't extract frequency from folder slug
- `summary_view.py` didn't fallback to basename when `meta.horizon` was missing

**Solution:**  
1. **twifo_app.py** - Added `_extract_frequency_from_slug()` to extract frequency suffix from artifact folder slug
2. **twifo_app.py** - Modified `get_artifacts_for_date()` to return `frequency_code` in artifact dict
3. **summary_view.py** - Added fallback regex to extract frequency from basename when `meta.horizon == "u"`
4. **twifo.py** - Updated Daily View callback to map frequency code to display text and render green badge

**Result:**  
- `O_weekly-municipal-monitor-seasonal-strength--02-10_20260211_w` → Green badge shows **"Weekly"**
- `_d` suffix → **"Daily"**
- `_m` suffix → **"Monthly"**
- `_q` suffix → **"Quarterly"**
- `_y` suffix → **"Yearly"**

---

### 2. Title Formatting Inconsistent with Library

**Problem:**  
Daily View titles were raw and ugly:
```
O_weekly-municipal-monitor-seasonal-strength--02-10_20260211_w
```

Should be clean like Library:
```
Weekly Municipal Monitor Seasonal Strength--02-10
```

**Root Cause:**  
Daily View used separate title cleaning logic that didn't match Library's `clean_title()` function.

**Solution:**  
Modified `_title_from_folder()` in `twifo_app.py` to:
1. Remove provider prefix from slug
2. Remove date tokens (`_20260211`)
3. Remove frequency suffix (`_w`, `_d`, etc.)
4. Replace underscores with spaces
5. **Preserve double dashes** (e.g., `--02-10`) using negative lookahead regex
6. Apply title case

**Result:**  
Titles now match Library formatting exactly:
- Underscores → spaces
- Single dashes → spaces
- Double dashes preserved (e.g., `--02-10`)
- Proper title case

---

## Implementation Details

### Files Modified

1. **twifo_app.py**
   - Added `_extract_frequency_from_slug()` helper
   - Enhanced `_title_from_folder()` to preserve double dashes
   - Modified `get_artifacts_for_date()` to return `frequency_code`

2. **summary_view.py**
   - Added fallback frequency extraction from basename when `meta.horizon == "u"`

3. **twifo.py**
   - Updated Daily View callback to display frequency badge
   - Removed duplicate title cleaning logic
   - Added frequency_map for display text

### Frequency Badge Rendering

The Daily View sidebar now shows:

```
[Firm Badge (Blue)]  [Frequency Badge (Green)]
Article Title (Clean, Title-Cased)
Product1, Product2, Product3
```

- **Firm badge:** Blue background, provider name
- **Frequency badge:** Green background (#28a745), "Weekly"/"Daily"/etc.
- **Title:** Clean, matches Library formatting
- **Products:** From `sum.json` meta.products

---

## Testing

Example filenames and expected output:

| Filename/Folder | Frequency Badge | Title Display |
|----------------|-----------------|---------------|
| `O_weekly-municipal-monitor-seasonal-strength--02-10_20260211_w` | **Weekly** | Weekly Municipal Monitor Seasonal Strength--02-10 |
| `GM_commodity_analyst_20260211_d` | **Daily** | Commodity Analyst |
| `MUFG_asia_fx_weekly_20260210_w` | **Weekly** | Asia Fx Weekly |
| `BOA_us_economic_weekly_ieepa_d_day_faqs_20260209_w` | **Weekly** | Us Economic Weekly Ieepa D Day Faqs |

---

## Backward Compatibility

- If `sum.json` already has correct `meta.horizon`, it will be used (no regression)
- If `meta.horizon == "u"`, fallback extracts from filename
- If no frequency suffix found, displays "Unknown" (same as before)
- Existing Library title formatting unchanged

---

## Related Files

- `twifo_app.py` - Artifact metadata extraction
- `summary_view.py` - Web summary renderer (requires `import re` for frequency fallback)
- `twifo.py` - Daily View callback and UI
- `PREFIX_MAP` - Firm code → name mapping (shared across all modules)
- `test_frequency_extraction.py` - Test harness for frequency extraction logic

---

## Regression Fix (2026-02-14)

**Issue:** Runtime error `name 're' is not defined` in Daily View when loading summaries.

**Root Cause:** Missing `import re` in `summary_view.py` after adding frequency fallback regex.

**Fix:** Added `import re` at top of `summary_view.py`.

**Verification:** Created `test_frequency_extraction.py` to validate regex logic works correctly.
