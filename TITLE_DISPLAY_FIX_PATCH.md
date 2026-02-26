# Title Display Fix - Complete Patch

## Problem
Right panel article header showed raw filenames (e.g., `O_weekly-municipal-monitor-seasonal-strength_02_10_20260211_w`) instead of clean titles. Buttons showed correct titles but detail view did not.

## Solution
Created a shared `resolve_display_title()` function used by all views (Buttons, Daily View, Library).

---

## Files Modified

### 1. `twifo_app.py` - Added shared title resolver

**Location:** After `_title_from_folder()` function (line ~143)

```python
def resolve_display_title(artifact_folder: str, meta_title: str = None, sum_json: dict = None) -> str:
    """
    Shared title resolver used across all views (Buttons, Daily View, Library).
    
    Resolution priority:
        1. meta.title if present, non-empty, and looks clean (no underscores/dates)
        2. Derived title from artifact_folder using _title_from_folder
        3. Final fallback to artifact_folder if both fail
    
    Args:
        artifact_folder: Artifact folder name (e.g., "20260211__GM__weekly_municipal...")
        meta_title: Optional title from sum.json meta.title
        sum_json: Optional full sum.json dict (will extract meta.title if provided)
    
    Returns:
        Clean, human-readable title string
    
    Examples:
        >>> resolve_display_title("20260211__O__weekly_municipal_monitor_seasonal_strength_02_10_20260211_w__abc123")
        'Weekly Municipal Monitor Seasonal Strength 02 10'
        
        >>> resolve_display_title("20260211__GM__foo__abc", meta_title="Clean Title from LLM")
        'Clean Title from LLM'
    """
    # Extract meta_title from sum_json if provided
    if sum_json and not meta_title:
        meta_title = sum_json.get("meta", {}).get("title", "")
    
    # Priority 1: Use meta.title if it's clean (no underscores or embedded dates)
    if meta_title and isinstance(meta_title, str):
        meta_title = meta_title.strip()
        if meta_title and "_" not in meta_title and not re.search(r'\d{8}', meta_title):
            return meta_title
    
    # Priority 2: Derive clean title from folder name
    derived_title = _title_from_folder(artifact_folder)
    if derived_title and derived_title != artifact_folder:
        return derived_title
    
    # Priority 3: Fallback to folder name (should rarely happen)
    return artifact_folder
```

---

### 2. `summary_view.py` - Use shared resolver in right panel

**Change 1:** Add import (line ~13)

```diff
 from typing import Optional, Dict, Any
 from dash import html, dcc
+from twifo_app import resolve_display_title
```

**Change 2:** Replace title extraction (line ~162 in `render_summary_view()`)

```diff
-    title = meta.get("title", basename)
+    title = resolve_display_title(basename, sum_json=sum_json)
     provider = meta.get("provider", "Unknown")
     products = meta.get("products", [])
```

---

### 3. `twifo.py` - Use shared resolver for daily view buttons

**Change 1:** Update import (line ~34)

```diff
 try:
-    from twifo_app import get_yesterday_artifacts, get_artifacts_for_date
+    from twifo_app import get_yesterday_artifacts, get_artifacts_for_date, resolve_display_title
     DAILY_VIEW_AVAILABLE = True
 except ImportError as e:
     print(f"[WARN] Daily view helper not available: {e}")
     DAILY_VIEW_AVAILABLE = False
     get_yesterday_artifacts = None
     get_artifacts_for_date = None
+    resolve_display_title = None
```

**Change 2:** Use shared resolver for button titles (line ~3048 in `build_daily_view_artifacts()`)

```diff
-        # Get firm name and clean title using Library logic
+        # Get firm name and clean title using shared resolver
         firm_name = art["provider"]
         
-        # Use the existing clean_title() function from Library
-        # art["title"] is already cleaned by _title_from_folder in twifo_app.py
-        title_cleaned = art["title"]
+        # Use shared resolve_display_title for consistency across all views
+        title_cleaned = resolve_display_title(art["artifact_folder"], meta_title=art.get("title"))
```

---

## Test Coverage

Created `test_title_resolver.py` with 7 test cases:

1. ✅ **Known filename resolves correctly**
   - Input: `20260211__O__weekly_municipal_monitor_seasonal_strength_02_10_20260211_w__abc123`
   - Output: `Weekly Municipal Monitor Seasonal Strength 02 10`

2. ✅ **Clean meta.title is preferred**
   - Input: folder + `meta_title="Clean Title from LLM"`
   - Output: `Clean Title from LLM`

3. ✅ **Dirty meta.title falls back to derived**
   - Input: folder + `meta_title="GM_Report_20260211_u"` (has underscores/date)
   - Output: Derived title from folder (not dirty meta.title)

4. ✅ **sum_json meta extraction**
   - Input: folder + `sum_json={"meta": {"title": "..."}}`
   - Output: Extracts and uses meta.title correctly

5. ✅ **Missing meta.title fallback**
   - Input: folder + `meta_title=""` (empty)
   - Output: Derived title (NOT raw filename)

6. ✅ **Provider prefix removal**
   - Input: `20260211__GM__gm_commodity_analyst...`
   - Output: Removes "gm_" prefix correctly

7. ✅ **Frequency suffix removal**
   - Input: Various folders with `_w`, `_m`, `_q`, `_d` suffixes
   - Output: Suffixes correctly removed

**Test execution:**
```bash
cd "c:\Coding Projects\TWIFO_Sharing"
python test_title_resolver.py
```

All tests pass ✅

---

## Resolution Priority Logic

```
1. meta.title (if clean: no underscores, no embedded YYYYMMDD dates)
   ↓ (if dirty or missing)
2. _title_from_folder(artifact_folder) (derived from folder slug)
   - Removes provider prefix (GM_, ING_, etc.)
   - Removes embedded dates (YYYYMMDD)
   - Removes frequency suffix (_w, _m, _q, etc.)
   - Converts underscores to spaces
   - Title cases
   ↓ (if derivation fails)
3. artifact_folder (raw fallback, rarely used)
```

---

## Before vs After

### Before (Bug)
- **Buttons:** `Weekly Municipal Monitor Seasonal Strength 02 10` ✅
- **Right Panel:** `O_weekly-municipal-monitor-seasonal-strength_02_10_20260211_w` ❌

### After (Fixed)
- **Buttons:** `Weekly Municipal Monitor Seasonal Strength 02 10` ✅
- **Right Panel:** `Weekly Municipal Monitor Seasonal Strength 02 10` ✅
- **Library:** `Weekly Municipal Monitor Seasonal Strength 02 10` ✅

All views now show consistent, clean titles with **no filename fragments, no slugs, no embedded dates**.

---

## Changes Summary

| File | Lines Changed | Purpose |
|------|--------------|---------|
| `twifo_app.py` | +48 | Added shared `resolve_display_title()` function |
| `summary_view.py` | +2 | Import and use shared resolver |
| `twifo.py` | +3 | Import and use shared resolver for buttons |
| `test_title_resolver.py` | +120 (new) | Comprehensive test coverage |

**Total:** 4 files, ~173 lines (including tests)

---

## Validation

Run the following to validate:

1. **Unit tests:**
   ```bash
   python test_title_resolver.py
   ```

2. **Visual check:**
   - Open Daily View in browser
   - Click any article button
   - Verify right panel header shows clean title (no underscores, no dates, no filename fragments)

3. **Consistency check:**
   - Compare button title vs right panel title
   - Should be identical
   - No "O_weekly..." or similar raw filenames anywhere

---

## Edge Cases Handled

✅ Missing `meta.title` → falls back to derived  
✅ Empty `meta.title` → falls back to derived  
✅ Dirty `meta.title` (underscores/dates) → falls back to derived  
✅ Provider prefix in slug → removed  
✅ Frequency suffix in slug → removed  
✅ Embedded dates in slug → removed  
✅ Multiple underscores → converted to single spaces  
✅ Malformed folder names → graceful fallback to folder name  

---

## Migration Notes

- **No data migration needed** - title resolution is runtime only
- **No schema changes** - sum.json remains unchanged
- **No breaking changes** - all existing views continue to work
- **Backward compatible** - works with old and new folder naming conventions

---

**Implementation complete. All tests passing. Ready for deployment.**
