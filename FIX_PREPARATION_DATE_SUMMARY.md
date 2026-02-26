# Fix "Preparation for..." Date in Daily View

## Problem
The Daily View title currently shows "Preparation for {article_date}", but it should show the **next trading weekday** instead.

For example:
- Articles from Friday should show "Preparation for Monday"
- Articles from Saturday should show "Preparation for Monday"
- Articles from Monday should show "Preparation for Tuesday"

## Solution

### 1. Added `_next_trading_weekday()` helper function
**File:** `rollups.py`

```python
def _next_trading_weekday(d: dt.date) -> dt.date:
    """
    Compute the next trading weekday after the given date.
    
    Rules:
    - Friday → Monday (skip weekend)
    - Saturday → Monday
    - Sunday → Monday
    - Monday-Thursday → next day
    """
    next_day = d + dt.timedelta(days=1)
    # weekday(): Monday=0, Sunday=6
    # If next_day is Saturday (5) or Sunday (6), jump to Monday
    if next_day.weekday() == 5:  # Saturday
        return next_day + dt.timedelta(days=2)
    elif next_day.weekday() == 6:  # Sunday
        return next_day + dt.timedelta(days=1)
    else:
        return next_day
```

### 2. Updated title generation in `build_daily_rollup()`
**File:** `rollups.py` (line 776)

**Before:**
```python
"title": f"Preparation for {_format_date_human(date_obj)}",
```

**After:**
```python
"title": f"Preparation for {_format_date_human(_next_trading_weekday(date_obj))}",
```

### 3. Created comprehensive test suite
**File:** `test_next_trading_weekday.py`

Tests all weekday transitions:
- ✓ Friday → Monday
- ✓ Saturday → Monday  
- ✓ Sunday → Monday
- ✓ Monday → Tuesday
- ✓ Tuesday → Wednesday
- ✓ Wednesday → Thursday
- ✓ Thursday → Friday

**Test output:**
```
Testing _next_trading_weekday()...

[PASS] Friday -> Monday
[PASS] Saturday -> Monday
[PASS] Sunday -> Monday
[PASS] Monday -> Tuesday
[PASS] Tuesday -> Wednesday
[PASS] Wednesday -> Thursday
[PASS] Thursday -> Friday

[SUCCESS] All tests passed!
```

## Key Points

1. **Underlying date unchanged:** The selected date (used for filtering articles, querying the database, etc.) remains the article date. Only the display title changes.

2. **Rollup generation:** The title is set when `build_daily_rollup()` creates the rollup JSON. Once generated, the rollup JSON is cached and the title persists.

3. **Backward compatible:** Existing rollup JSONs will keep their original titles. Only newly generated rollups will use the new "next trading weekday" logic.

4. **No UI changes needed:** The `render_rollup_summary()` function in `twifo.py` reads the title from `rollup_json["ui"]["title"]` and displays it as-is. No changes required there.

## Files Modified

1. **rollups.py**
   - Added `_next_trading_weekday()` function
   - Updated title generation in `build_daily_rollup()`

2. **test_next_trading_weekday.py** (new file)
   - Comprehensive test suite for the weekday mapping logic

## Testing

Run the test suite:
```bash
cd "c:\Coding Projects\TWIFO_Sharing"
python test_next_trading_weekday.py
```

To regenerate a rollup with the new title:
```bash
python generate_rollup_clean.py daily 2026-02-27
```

## Examples

| Article Date | Day of Week | Title Shows |
|--------------|-------------|-------------|
| 2026-02-27 | Friday | Preparation for March 02, 2026 (Monday) |
| 2026-02-28 | Saturday | Preparation for March 02, 2026 (Monday) |
| 2026-03-01 | Sunday | Preparation for March 02, 2026 (Monday) |
| 2026-03-02 | Monday | Preparation for March 03, 2026 (Tuesday) |
| 2026-03-03 | Tuesday | Preparation for March 04, 2026 (Wednesday) |

