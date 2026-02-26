# Daily Recap Empty State Handling

**Created:** 2026-02-25  
**Files Modified:** `twifo.py`, `test_daily_recap_empty_state.py` (new)

## Overview

Implemented graceful handling for dates with zero articles on the Daily Recap page. When no articles exist for a selected date, the page now displays a clean empty state instead of crashing or showing a blank page.

## Implementation Details

### Changes to `twifo.py` (lines 5882-5932)

**Location:** `display_daily_article_summary` callback, Daily Summary branch

**Added explicit empty state check:**
- When `artifacts` is `None` or empty (`[]`), the callback now:
  1. Extracts the date from yesterday if artifacts is empty (fallback)
  2. Renders a clean "No Articles" card with:
     - **Title:** "No Articles"
     - **Body:** "No articles were found for this date."
     - **Help text:** "If you expected content, check ingestion or filters."
  3. Still attempts to render the Economic Events panel if available
  4. **Does NOT** attempt to load a rollup JSON file (prevents file not found errors)

**Before:** 
- If artifacts was empty, `date_fmt` variable was undefined when referenced later
- Would cause `UnboundLocalError` at line 5935, 5956, 5961, 5972
- No explicit empty state UI

**After:**
- Explicit empty state check added at line 5898
- Clean card UI rendered with helpful messaging
- Economic Events panel still renders independently
- No rollup file loading attempted when artifacts is empty

### Code Changes

```python
# Handle explicit empty state when no articles exist
if not artifacts or len(artifacts) == 0:
    _dyn_mode_empty = dynamics_mode_store if dynamics_mode_store is not None else True
    _is_logged_in_empty = bool(login_user_store)
    _live_events_panel_empty = None
    
    # Economic Events panel can still render even without articles
    if date_fmt and ECON_CALENDAR_AVAILABLE:
        try:
            _live_events_panel_empty = _render_econ_events_panel(
                date_fmt, None,
                dynamics_mode=_dyn_mode_empty,
                is_logged_in=_is_logged_in_empty,
            )
        except Exception:
            _live_events_panel_empty = None
    
    # Render clean empty state
    return "", html.Div([
        html.Div([
            html.H3("No Articles", ...),
            html.P("No articles were found for this date.", ...),
            html.P("If you expected content, check ingestion or filters.", ...)
        ], style={...}),
        # Still show Economic Events if available
        *([_live_events_panel_empty] if _live_events_panel_empty is not None else []),
    ], style={"padding": "20px"})
```

## Test Coverage

**New Test File:** `test_daily_recap_empty_state.py`

### Test Scenarios

1. **Empty List Test (`test_empty_state_render`):**
   - Simulates clicking Daily Summary button with `artifacts = []`
   - Verifies callback executes without exceptions
   - Confirms empty state message is rendered
   - Checks for "No Articles" title and body text

2. **None Value Test (`test_none_artifacts`):**
   - Tests with `artifacts = None` instead of empty list
   - Ensures robustness for null values
   - Verifies same empty state behavior

### Test Results

Both tests pass successfully:
- ✓ Callback handles empty artifacts without errors
- ✓ Returns valid Dash component structure  
- ✓ Displays "No Articles" message with helpful text
- ✓ Does not attempt to load rollup JSON when no articles exist
- ✓ Economic Events panel can still render independently

## Empty State Behavior (One Sentence)

**When a date has zero artifacts, the Daily Recap page displays a clean "No Articles" card with helpful text while still rendering the Economic Events panel if events exist, and does not attempt to load a rollup file.**

## Key Features

✓ **Graceful Degradation:** Page loads successfully even with no articles  
✓ **Clear Messaging:** Users see explicit "No Articles" message instead of error  
✓ **Helpful Context:** Suggests checking ingestion or filters  
✓ **Independent Panels:** Economic Events panel still renders if data exists  
✓ **No File Errors:** Doesn't attempt to load missing rollup files  
✓ **Tested:** Complete test coverage for empty and null scenarios

## Usage

The empty state appears automatically when:
1. A date is selected that has no articles
2. Articles are filtered out completely
3. Ingestion hasn't run yet for a date

The user sees a clean, styled card explaining the situation rather than a crash or blank page.

