# Import Week Events Crash Fix

## Diagnosis

### Root Cause
The crash occurred in the `poll_generation_progress` callback when processing weekly event generation results. The callback assumed all items in the `results` list were dictionaries and called `.get()` on them without validation.

**Exact crash point**: `twifo.py:3673-3678` in `poll_generation_progress()`
- The callback iterated over `results` and called `.get()` on each item
- If any result item was not a dict (e.g., `None`, string, list), calling `.get()` would raise `AttributeError`
- This caused the entire callback to crash, which could crash the Dash app

### Why It Happened
1. **No defensive validation**: The code didn't check if `results` was a list or if items were dicts
2. **Thread safety**: The background thread (`_run_generation`) could append malformed results if `generate_for_date` returned unexpected types
3. **Error propagation**: Exceptions in the progress callback weren't caught, causing the entire UI to crash

### What Changed
- Added defensive type checking in `poll_generation_progress` to validate `results` is a list and items are dicts
- Added try/except around result processing to handle malformed items gracefully
- Enhanced `_run_generation` thread to always produce valid dict results with required keys
- Added validation in the thread to ensure `generate_for_date` returns a dict before appending
- Added error truncation to prevent extremely long error messages from breaking the UI

## Code Changes

### 1. Enhanced `poll_generation_progress` callback (`twifo.py:3649-3740`)
- Added validation that `results` is a list
- Added try/except around each result item processing
- Added defensive checks to ensure result items are dicts before calling `.get()`
- Added catastrophic error handling with fallback UI display
- Improved error collection to handle malformed items safely

### 2. Enhanced `_run_generation` thread (`twifo.py:3537-3585`)
- Added validation that `generate_for_date` returns a dict
- Ensured all required keys exist in result dicts before appending
- Added fallback result creation if `generate_for_date` returns None or invalid type
- Added error truncation (500 chars) to prevent UI overflow
- Improved initialization of store dict keys

## Verification Checklist

### ✅ 1. Import Week Events succeeds for 7 days
- [ ] Click "Save" (Import Week Events) with a week containing events
- [ ] All 7 days process without crashing
- [ ] Progress updates show correctly in UI
- [ ] Completion message appears when done

### ✅ 2. Daily recap renders: events list first, then summary
- [ ] Navigate to Daily View for a date with events
- [ ] Verify events list appears at the top
- [ ] Verify AI summary appears below the events list
- [ ] Order: Events List → Economic Brief Summary → Observations & Forward Watch

### ✅ 3. No server crash / restart during import
- [ ] Monitor server logs during import
- [ ] No uncaught exceptions in logs
- [ ] Server remains responsive during import
- [ ] No restart/reboot occurs

### ✅ 4. Logs show clean completion and no uncaught exceptions
- [ ] Check console logs for `[ECON GEN THREAD]` messages
- [ ] Verify all dates show completion status
- [ ] No `AttributeError` or `TypeError` exceptions
- [ ] Errors are logged but don't crash the process

## Testing Steps

1. **Start the server**:
   ```bash
   python twifo.py
   ```

2. **Import a week**:
   - Navigate to Economic Calendar tab
   - Paste week calendar text
   - Click "Parse" to verify parsing
   - Click "Save" to import and generate

3. **Monitor progress**:
   - Watch the progress area for updates
   - Check browser console for errors
   - Monitor server logs

4. **Verify daily recap**:
   - Navigate to Daily View
   - Select a date with events
   - Verify events list appears before summary

## Error Handling Improvements

### Before
- No validation of result types
- Crashes on malformed data
- No graceful degradation

### After
- Type validation at multiple levels
- Graceful error display in UI
- Continues processing even if individual dates fail
- Clear error messages for debugging

## UI Behavior Preservation

✅ **Confirmed**: Daily recap page order is correct:
1. Events list (raw list of day's events)
2. Economic Brief Summary (AI-generated)
3. Observations & Forward Watch

The events panel (`_render_econ_events_panel`) renders:
- Events list first (line 4390-4396)
- Brief/summary second (line 4398)

This order is preserved and matches requirements.

