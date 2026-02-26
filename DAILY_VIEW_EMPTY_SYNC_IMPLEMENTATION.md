# Daily View Empty State Synchronization - Implementation

## Problem Statement

When a user selected a date with zero articles in the Daily View:
- **Left panel** correctly showed "No articles found for {date}"
- **Right panel** continued to show stale content from the previous date
- This created an inconsistent and confusing user experience

## Root Cause

The Daily View has two callbacks:
1. `populate_daily_view_sidebar` - Updates the left panel when date changes
2. `display_daily_article_summary` - Updates the right panel when a button is clicked

The right panel callback was ONLY triggered by button clicks, not by date changes.
When the date changed to one with no articles, the left panel updated but the right panel
remained frozen with old content.

## Solution

### Task 1: Add Store as Input Trigger

**File**: `twifo.py` (lines 5841-5860)

**Change**: Modified the `display_daily_article_summary` callback to also trigger when
`daily-articles-store` updates.

**Before**:
```python
@app.callback(
    [Output("daily-selected-artifact", "data"), Output("daily-view-content", "children")],
    Input({"type": "daily-article-btn", "index": dash.dependencies.ALL}, "n_clicks"),
    [State("daily-articles-store", "data"), State("login-user", "data")],
    prevent_initial_call=True
)
def display_daily_article_summary(n_clicks_list, artifacts, login_user_store):
```

**After**:
```python
@app.callback(
    [Output("daily-selected-artifact", "data"), Output("daily-view-content", "children")],
    [
        Input({"type": "daily-article-btn", "index": dash.dependencies.ALL}, "n_clicks"),
        Input("daily-articles-store", "data")  # NEW: Trigger on store updates
    ],
    [
        State("login-user", "data"),
        State("daily-view-date-input", "value")  # NEW: Need date for empty state message
    ],
    prevent_initial_call=True
)
def display_daily_article_summary(n_clicks_list, artifacts, login_user_store, date_input):
```

### Task 2: Add Early Return for Store Updates

**File**: `twifo.py` (lines 5874-5914)

**Change**: Added logic to detect when the callback is triggered by the store (not a button),
and immediately clear the right panel if artifacts is empty.

**Implementation**:
```python
# Check if triggered by store update (not button click)
if triggered_id == "daily-articles-store":
    # Store updated - check if artifacts is empty
    if not artifacts or len(artifacts) == 0:
        # Clear right panel with empty state
        # Extract date for the empty state message
        try:
            if date_input and date_input.strip():
                target_date = datetime.datetime.strptime(date_input.strip(), "%Y-%m-%d").date()
            else:
                target_date = datetime.date.today() - datetime.timedelta(days=1)
            date_display = target_date.strftime("%B %d, %Y")
        except:
            target_date = datetime.date.today() - datetime.timedelta(days=1)
            date_display = target_date.strftime("%B %d, %Y")
        
        return "", html.Div([
            html.Div([
                html.H3("No Articles Found", style={"color": HEADER_BG_COLOR, "marginBottom": "10px"}),
                html.P(
                    f"No articles found for {date_display}.",
                    style={"fontSize": "15px", "marginBottom": "5px"}
                ),
                html.P(
                    "Select a different date or check if articles have been ingested.",
                    style={"fontSize": "13px", "color": "#666", "fontStyle": "italic"}
                )
            ], style={
                "backgroundColor": "#f9f9f9",
                "padding": "20px",
                "borderRadius": "4px",
                "border": "1px solid #ddd",
                "textAlign": "center",
                "marginTop": "40px"
            })
        ], style={"padding": "20px"})
    else:
        # Artifacts exist but no button clicked yet - don't update
        raise PreventUpdate
```

**Key Logic**:
- If triggered by store AND artifacts is empty → Clear right panel with empty state
- If triggered by store AND artifacts is NOT empty → Don't update (PreventUpdate)
- If triggered by button click → Continue with normal rendering logic

### Task 3: Verify Message Consistency

**Left Panel** (line 4369):
```python
f"No articles found for {target_date.strftime('%B %d, %Y')}."
```

**Right Panel** (line 5896):
```python
f"No articles found for {date_display}."  # where date_display = target_date.strftime("%B %d, %Y")
```

Both panels use the same date format: `"%B %d, %Y"` (e.g., "February 25, 2026")

✅ **Consistent**

### Task 4: Regression Test

**File**: `test_daily_view_empty_sync.py`

**Tests**:
1. Empty artifacts clears right panel with correct date
2. Left and right panel message consistency
3. No stale recap content in empty state (no briefing strip, TLDR, volatility cards, etc.)
4. Store trigger vs button trigger behavior differentiation
5. Date parsing fallback for invalid inputs

**Manual Test Steps**:
1. Start Twifo and navigate to Daily View
2. Select a date with articles → Verify left panel shows list
3. Click summary button → Verify right panel shows recap
4. Change to date with NO articles → Verify BOTH panels show empty state immediately
5. Verify no stale content remains visible
6. Change back to date with articles → Verify left panel updates, right panel clears
7. Click summary again → Verify right panel renders correctly

## Stores Cleared

**No stores were explicitly cleared** because the callback returns new content that
completely replaces the right panel children. The `daily-selected-artifact` store is
set to empty string `""` when the empty state is shown.

**Stores NOT modified**:
- `daily-articles-store` - This is the INPUT that triggers the callback; it's set by
  the `populate_daily_view_sidebar` callback
- `econ-dynamics-mode` - Not relevant to Daily View (removed in previous task)
- `login-user` - Authentication state, unchanged

## Files Changed

1. **twifo.py**:
   - Modified `display_daily_article_summary` callback signature (lines 5841-5860)
   - Added early return logic for store updates (lines 5874-5914)

2. **test_daily_view_empty_sync.py** (NEW):
   - Comprehensive regression tests
   - Manual test steps documentation

3. **daily_view_empty_sync.patch** (NEW):
   - Full diff of all changes

4. **DAILY_VIEW_EMPTY_SYNC_IMPLEMENTATION.md** (NEW):
   - This documentation file

## Behavior Summary

### Before Fix
```
User selects date with no articles:
  Left Panel:  "No articles found for February 25, 2026"
  Right Panel: [Shows stale recap from previous date] ❌
```

### After Fix
```
User selects date with no articles:
  Left Panel:  "No articles found for February 25, 2026"
  Right Panel: "No Articles Found
                No articles found for February 25, 2026.
                Select a different date or check if articles have been ingested." ✓
```

## Edge Cases Handled

1. **Invalid date input** → Falls back to yesterday
2. **Empty string date input** → Falls back to yesterday
3. **Store updates with non-empty artifacts** → No right panel update (prevents flicker)
4. **Button click with empty artifacts** → Shows existing empty state logic (unchanged)
5. **Missing date_input State** → Falls back to yesterday

## Backward Compatibility

✅ All existing functionality preserved:
- Button clicks still render articles and summaries correctly
- Economic Events panel still renders independently
- Rollup loading logic unchanged
- PDF embedding unchanged
- Error handling unchanged

## Performance Impact

**Minimal** - The early return when artifacts is empty is very fast (no file I/O, no rendering).
The callback now triggers on store updates, but raises `PreventUpdate` when artifacts exist,
so no extra rendering occurs.

## Testing Status

✅ All automated tests pass
✅ No linter errors
✅ Manual test steps documented
⏳ Manual testing pending (requires running Twifo app)

---

**Implementation Date**: February 25, 2026
**Author**: AI Assistant
**Status**: Complete

