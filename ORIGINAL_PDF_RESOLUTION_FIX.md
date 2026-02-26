# Original PDF Resolution Fix - Daily View

## Problem

Daily View split-screen showed "Original article not available" for most articles because it only searched the artifact folder. Original PDFs actually live in the shared `originals/` folder.

## Solution

Implemented priority-based PDF resolution that checks:
1. **Artifact folder** (for embedded originals)
2. **ORIGINALS_ROOT** (shared originals folder)

---

## Implementation

### 1. Added Config Constant

**File**: `twifo.py` (line ~298)

```python
ORIGINALS_ROOT = Path(FILES_DIR) / "originals"  # Shared originals folder for all PDFs
```

**Location**: Placed with other path config constants (`FILES_DIR`, `PATH_MANAGER`)

**Value**: `C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\originals`

---

### 2. Replaced `_find_original_pdf()` with `resolve_original_pdf()`

**File**: `twifo.py` (lines ~5909-5961)

#### Old Function (Limited)

```python
def _find_original_pdf(artifact_folder: str) -> Optional[str]:
    # Only checked artifact folder
    # Returned None for most articles
```

#### New Function (Comprehensive)

```python
def resolve_original_pdf(artifact_folder: str) -> Optional[str]:
    """
    Resolve the original PDF file for an article using priority-based search.
    
    Priority:
      A. Check artifact folder for original PDF
      B. Check ORIGINALS_ROOT using deterministic filename mapping
      C. Return None if not found (caller can show fallback)
    """
```

---

### 3. Resolution Strategy

#### Priority A: Artifact Folder

**Checks**:
1. `artifacts/{folder}/original.pdf`
2. `artifacts/{folder}/source.pdf`
3. `artifacts/{folder}/article.pdf`
4. Any PDF in folder except `sum.pdf`

**Example**:
```
artifacts/20260211__GM__report__abc123/original.pdf
→ Returns: "artifacts/20260211__GM__report__abc123/original.pdf"
```

#### Priority B: ORIGINALS_ROOT

**Mapping**: Uses deterministic filename based on artifact folder name

**Format**: `{artifact_folder}.pdf`

**Example**:
```
Artifact folder: 20260211__GM__commodity_analyst_20260211_u__677f0794fa
Original PDF:    20260211__GM__commodity_analyst_20260211_u__677f0794fa.pdf
Full path:       originals/20260211__GM__commodity_analyst_20260211_u__677f0794fa.pdf
→ Returns: "originals/20260211__GM__commodity_analyst_20260211_u__677f0794fa.pdf"
```

**Why This Works**:
- Artifact folders use deterministic naming: `YYYYMMDD__PROVIDER__title_slug__hash`
- Original PDFs use same basename in `originals/` folder
- Direct 1:1 mapping, no parsing needed

#### Priority C: Not Found

**Returns**: `None`

**Caller**: Shows fallback message "Original article not available"

---

### 4. Logging

**Format**: Single line per resolution attempt

**Examples**:

```
[ORIGINAL_PDF] id=20260211__GM__report__abc123 tried=artifact/original.pdf found=yes
```

```
[ORIGINAL_PDF] id=20260211__BOA__weekly__def456 tried=artifact found=no tried=originals/20260211__BOA__weekly__def456.pdf found=yes
```

```
[ORIGINAL_PDF] id=20260211__JPM__daily__ghi789 tried=artifact found=no tried=originals/20260211__JPM__daily__ghi789.pdf found=no
```

**Benefits**:
- Easy to debug which path was tried
- Shows exactly where PDF was found
- No spam (one line per article)

---

### 5. Updated Split-Screen Layout

**File**: `twifo.py` (line ~6025)

**Changed**:
```python
# OLD:
original_pdf_path = _find_original_pdf(artifact_folder)

# NEW:
original_pdf_path = resolve_original_pdf(artifact_folder)
```

**Impact**: Split-screen now shows original PDFs from `originals/` folder

---

## Example Path Resolution

### Scenario: Goldman Sachs Commodity Report

**Artifact Folder**: `20260211__GM__gm_commodity_analyst_20260211_u__677f0794fa`

**Resolution Steps**:

1. **Check artifact folder**:
   - `artifacts/20260211__GM__gm_commodity_analyst_20260211_u__677f0794fa/original.pdf` → Not found
   - `artifacts/20260211__GM__gm_commodity_analyst_20260211_u__677f0794fa/source.pdf` → Not found
   - `artifacts/20260211__GM__gm_commodity_analyst_20260211_u__677f0794fa/*.pdf` (except sum.pdf) → Not found

2. **Check ORIGINALS_ROOT**:
   - `originals/20260211__GM__gm_commodity_analyst_20260211_u__677f0794fa.pdf` → **FOUND**

3. **Return**: `"originals/20260211__GM__gm_commodity_analyst_20260211_u__677f0794fa.pdf"`

**Log Output**:
```
[ORIGINAL_PDF] id=20260211__GM__gm_commodity_analyst_20260211_u__677f0794fa tried=artifact found=no tried=originals/20260211__GM__gm_commodity_analyst_20260211_u__677f0794fa.pdf found=yes
```

**Result**: PDF loads in right pane of split-screen view

---

## Manual Test Steps

### Test 1: Article with Original in ORIGINALS_ROOT

**Setup**:
1. Find an article where artifact folder has `sum.json` but no `original.pdf`
2. Verify corresponding PDF exists in `originals/` folder

**Steps**:
1. Start Twifo application
2. Navigate to Daily View
3. Select date with articles
4. Click on an individual article (e.g., Goldman Sachs commodity report)

**Expected**:
- ✅ Split-screen appears
- ✅ Left pane shows AI summary
- ✅ Right pane shows original PDF (loaded from `originals/`)
- ✅ Console log shows: `tried=artifact found=no tried=originals/...pdf found=yes`
- ✅ PDF renders correctly in iframe

**Pass Criteria**:
- Original PDF displays (not fallback message)
- Log confirms PDF found in `originals/`

---

### Test 2: Article with Original in Artifact Folder

**Setup**:
1. Find an article where artifact folder has embedded `original.pdf`

**Steps**:
1. Navigate to Daily View
2. Click on article with embedded original

**Expected**:
- ✅ Split-screen appears
- ✅ Right pane shows original PDF (loaded from artifact folder)
- ✅ Console log shows: `tried=artifact/original.pdf found=yes`
- ✅ No attempt to check `originals/` (early return)

**Pass Criteria**:
- Original PDF displays from artifact folder
- Log confirms artifact folder was used

---

### Test 3: Article with No Original Anywhere

**Setup**:
1. Find an article where:
   - Artifact folder has no original PDF
   - No corresponding PDF in `originals/` folder

**Steps**:
1. Navigate to Daily View
2. Click on article without original

**Expected**:
- ✅ Split-screen appears
- ✅ Left pane shows AI summary
- ✅ Right pane shows fallback message: "📄 Original article not available"
- ✅ Console log shows: `tried=artifact found=no tried=originals/...pdf found=no`

**Pass Criteria**:
- Fallback message displays (not broken iframe)
- Log confirms both locations checked

---

### Test 4: Daily Summary Unchanged

**Steps**:
1. Navigate to Daily View
2. Click "Summary for {date} & Prep for Today" button

**Expected**:
- ✅ Full-width rollup renders (no split-screen)
- ✅ No PDF resolution attempted
- ✅ No console logs about original PDFs
- ✅ All sections render normally

**Pass Criteria**:
- Daily Summary completely unchanged
- No impact from PDF resolution changes

---

## Files Changed

### Modified

1. **twifo.py**:
   - Line ~298: Added `ORIGINALS_ROOT` constant
   - Lines ~5909-5961: Replaced `_find_original_pdf()` with `resolve_original_pdf()`
   - Line ~6025: Updated call to use `resolve_original_pdf()`

### NOT Modified

- **rollups.py** - unchanged
- **twifo_app.py** - unchanged
- **path_manager.py** - unchanged
- **All other Python files** - unchanged

---

## Technical Details

### Filename Mapping

**Artifact Folder Format**: `YYYYMMDD__PROVIDER__title_slug__hash`

**Original PDF Format**: `YYYYMMDD__PROVIDER__title_slug__hash.pdf`

**Mapping**: Direct 1:1 (folder name = PDF basename)

**Example**:
```
Folder: 20260211__GM__commodity_analyst_20260211_u__677f0794fa
PDF:    20260211__GM__commodity_analyst_20260211_u__677f0794fa.pdf
```

### Why This Works

1. **Deterministic**: Same naming convention for folders and PDFs
2. **No Parsing**: Simple string concatenation (`{folder}.pdf`)
3. **Reliable**: Based on existing pipeline conventions
4. **Fast**: Single file check (no directory scanning)

### Path Resolution Flow

```
resolve_original_pdf(artifact_folder)
    ↓
Check: artifacts/{folder}/original.pdf
    ↓ Not found
Check: artifacts/{folder}/source.pdf
    ↓ Not found
Check: artifacts/{folder}/*.pdf (except sum.pdf)
    ↓ Not found
Check: originals/{folder}.pdf
    ↓ FOUND
Return: "originals/{folder}.pdf"
```

---

## Security

✅ **Path Validation**: Uses `Path` objects (safe)
✅ **No User Input**: `artifact_folder` from trusted source (artifacts store)
✅ **No Path Traversal**: Direct path construction, no string manipulation
✅ **File Existence Check**: Uses `.is_file()` before returning

---

## Performance

✅ **Fast**: Simple file existence checks (no directory scanning)
✅ **Early Return**: Stops at first match (artifact folder checked first)
✅ **No Overhead**: Only runs when user clicks article
✅ **Cached by Browser**: PDF loaded once, then cached

---

## Backward Compatibility

✅ **Artifact Folder Priority**: Existing embedded originals still work
✅ **Fallback Message**: Graceful handling when PDF not found
✅ **No Breaking Changes**: All existing paths still work
✅ **Daily Summary Unchanged**: No impact on rollup rendering

---

## Future Enhancements

### Priority 1: Source URL Fallback

When PDF not found in either location, check for `source_url` in metadata:
```python
if not original_pdf_path and source_url:
    # Show "Open original" link instead of iframe
    return html.A("Open original article →", href=source_url, target="_blank")
```

### Priority 2: Multiple Filename Patterns

Support additional filename patterns:
```python
# Try variations
patterns = [
    f"{artifact_folder}.pdf",  # Exact match
    f"{date}_{provider}_{title_slug}.pdf",  # Alternative format
    f"{provider}_{title_slug}_{date}.pdf",  # Legacy format
]
```

### Priority 3: Metadata-Based Lookup

Store original filename in `sum.json` metadata:
```json
{
  "meta": {
    "original_filename": "20260211__GM__commodity_analyst_20260211_u__677f0794fa.pdf"
  }
}
```

---

## Rollback Plan

If issues arise:

1. Revert `resolve_original_pdf()` to old `_find_original_pdf()`:
   ```python
   def _find_original_pdf(artifact_folder: str) -> Optional[str]:
       # Only check artifact folder (old behavior)
   ```

2. Remove `ORIGINALS_ROOT` constant

3. Update call site back to `_find_original_pdf()`

---

## Deployment

✅ No database migrations
✅ No new dependencies
✅ No configuration changes
✅ Backward compatible
✅ No restart required (Dash hot-reloads)

---

**Status**: ✅ COMPLETE - Ready for Testing

