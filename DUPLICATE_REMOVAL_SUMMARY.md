# Duplicate _extract_bullet_text Removal Summary

## Issue
Two `_extract_bullet_text` function definitions existed in `summarize_pdf.py`, with the weaker one (line 2389) overriding the stronger one (line 175).

## Resolution

### Removed Duplicate (Line 2389-2395)
**Location**: Between `_critic_validate_quote` and `critic_dedup_sections`

**Weaker implementation removed**:
```python
def _extract_bullet_text(bullet: Any) -> str:
    """Extract text from a bullet (dict with 'text' key or plain string)."""
    if isinstance(bullet, dict):
        return str(bullet.get("text", ""))
    if isinstance(bullet, str):
        return bullet
    return ""
```

**Why it was weaker**:
- Only handled `dict["text"]` key
- No fallback keys
- Limited functionality

### Kept Stronger Implementation (Line 175-187)
**Location**: Before `_normalize_sections_in_place`

**Stronger implementation retained**:
```python
def _extract_bullet_text(item: Any) -> str:
    """
    Normalize a bullet item to a text string when possible.
    """
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        if "text" in item and item.get("text") is not None:
            return str(item.get("text")).strip()
        for key in ["bullet", "value", "content", "item", "summary"]:
            if key in item and item.get(key) is not None:
                return str(item.get(key)).strip()
    return ""
```

**Why it's stronger**:
- Handles plain strings
- Handles `dict["text"]` as primary key
- **Fallback keys**: `bullet`, `value`, `content`, `item`, `summary`
- Strips whitespace from all results
- More robust for various bullet formats

## Supported Bullet Formats

The remaining implementation supports:

1. **Plain strings**: `"This is a bullet"`
2. **Dict with "text"**: `{"text": "Main content"}`
3. **Dict with fallback keys**:
   - `{"bullet": "Content"}` → extracts "Content"
   - `{"value": "Content"}` → extracts "Content"
   - `{"content": "Content"}` → extracts "Content"
   - `{"item": "Content"}` → extracts "Content"
   - `{"summary": "Content"}` → extracts "Content"
4. **Empty/invalid**: Returns `""`

## Test Updates

### Updated Test: test_quality_retry.py (Line 129-145)

**Before** (expected fallback keys to fail):
```python
test_cases = [
    ("string bullet", "string bullet"),
    ({"text": "dict with text"}, "dict with text"),
    ({"bullet": "unsupported key"}, ""),  # Expected empty
    ({"value": "unsupported key"}, ""),   # Expected empty
]
```

**After** (fallback keys now work):
```python
test_cases = [
    ("string bullet", "string bullet"),
    ({"text": "dict with text"}, "dict with text"),
    ({"bullet": "fallback key"}, "fallback key"),  # Now supported
    ({"value": "fallback key"}, "fallback key"),   # Now supported
    ({"content": "another fallback"}, "another fallback"),  # Now supported
    ({"item": "item key"}, "item key"),  # Now supported
    ({"summary": "summary key"}, "summary key"),  # Now supported
    ({}, ""),  # Empty dict returns empty string
    ({"unknown_key": "value"}, ""),  # Unsupported key returns empty string
]
```

### Test Results
All 8 tests in `test_quality_retry.py` **PASS**:
- ✅ Retry structure validation
- ✅ Model escalation metadata
- ✅ Stub on double failure
- ✅ **Bullet normalization** (now with extended fallback key tests)
- ✅ Debug artifact structure
- ✅ Banned phrase triggers retry
- ✅ Section repetition triggers retry
- ✅ Filler failure reason format

## Verification

```bash
cd "c:\Coding Projects\TWIFO_Sharing"
python test_quality_retry.py
# Output: ALL TESTS PASSED
```

No linter errors in either file.

## Impact

✅ **Single source of truth**: Only one `_extract_bullet_text` function exists
✅ **Stronger behavior**: Fallback keys now work throughout the codebase
✅ **Tests updated**: Expectations now match the stronger implementation
✅ **No breaking changes**: The stronger implementation is a superset of the weaker one

## Files Changed

1. **summarize_pdf.py**
   - Removed duplicate at line 2389-2395
   - Kept stronger implementation at line 175-187

2. **test_quality_retry.py**
   - Updated test expectations (line 129-145)
   - Added more comprehensive test cases for fallback keys
