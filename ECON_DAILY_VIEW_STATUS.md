# Economic Calendar - Daily View Integration Status

## Database Storage & Retrieval ✓ WORKING

Tested with `test_db_manual.py`:
```
OK Saved week 2026-02-22 to 2026-02-28 (ID: 26c1edbf-90d4-4b46-889e-87c715b37da8)

OK Events on 2026-02-24: 2
   10:00    CB Consumer Confidence (Feb)
   21:00    U.S. President Trump Speaks

OK Events on 2026-02-23: 2
   All-day  Emperor's Birthday
   All-day  Chinese New Year
```

- ✓ `upsert_week_and_events` persists correctly
- ✓ `get_events_for_date` returns correct events for each date
- ✓ Database file `data/twifo_econ.db` created and populated

---

## Admin Page - Simplified ✓ DONE

Changes made:
1. **Parse button** - validates only, shows "Parsed successfully, ready to save"
2. **Save button** - re-parses inline, upserts to DB, shows toast
3. **Removed**: Preview table, parsed-data store
4. **Kept**: Recently imported weeks list with Load buttons
5. **Kept**: Dynamics mode toggle (persists in session store)

---

## Daily View Integration - TO TEST

### Current Implementation

`_render_econ_events_panel(date_str, rollup_json)` is called from:
- `render_rollup_summary()` at line 4380

Date flow:
1. Daily View callback loads `ROLLUP_DAILY_YYYYMMDD__sum.json`
2. Extracts `meta.date` (format: `YYYY-MM-DD`)
3. Passes to `render_rollup_summary(rollup_json, article_count)`
4. Panel function extracts `date_str = meta.get("date", "")`
5. Calls `get_events_for_date(DB_PATH, date_iso)`
6. Renders events if found, returns `None` if empty

### Debug Logging Added

```python
print(f"[ECON] Panel called for date_iso: {date_iso}")
print(f"[ECON] Found {len(events)} events for {date_iso}")
print(f"[ECON] No events found for {date_iso}, panel hidden")
```

Watch console output when viewing Daily View to trace execution.

---

## Manual Test Plan

### Step 1: Paste and Save Week
1. Navigate to **Economic Calendar** tab
2. Paste:
```
Sunday, February 22 to Saturday, February 28, 2026

Tuesday, February 24, 2026
10:00 CB Consumer Confidence (Feb)
21:00 U.S. President Trump Speaks

Monday, February 23, 2026
All China - Chinese New Year - CHINA*
All Japan - Emperor's Birthday - JPY*
```
3. Click **Parse** → Should show "Parsed successfully, ready to save"
4. Click **Save** → Should show "Saved week 2026-02-22 to 2026-02-28 (4 events)"

### Step 2: View Tuesday Feb 24
1. Go to **Daily View** tab
2. Enter date `2026-02-24` or select artifact from that date
3. Click "Summary for February 24th & Prep for Today"
4. Scroll to bottom → Should see **📅 Economic Events (2 events)**
5. Should list:
   - `10:00 CB Consumer Confidence (Feb)`
   - `21:00 U.S. President Trump Speaks`
6. Click **▶ Theory** on one event → Loading spinner → Text appears
7. Click **▶ Dynamics** → Loading spinner → Text appears

### Step 3: View Monday Feb 23
1. Change date to `2026-02-23`
2. Scroll to bottom → Should see **📅 Economic Events (2 events)**
3. Should list:
   - `All-day Chinese New Year [China] CHINA`
   - `All-day Emperor's Birthday [Japan] JPY`

### Step 4: View Date with No Events
1. Change date to `2026-02-25`
2. Scroll to bottom → **No** Economic Events panel (hidden)

---

## Expected Console Output

When viewing a date with events:
```
[ECON] Panel called for date_iso: 2026-02-24
[ECON] Found 2 events for 2026-02-24
```

When viewing a date without events:
```
[ECON] Panel called for date_iso: 2026-02-25
[ECON] Found 0 events for 2026-02-25, panel hidden
```

---

## Next Steps if Panel Doesn't Appear

1. Check console logs for `[ECON]` messages
2. Verify `meta.date` field exists in the rollup JSON
3. Confirm `date_str` is being passed correctly to the panel function
4. Check that `ECON_CALENDAR_AVAILABLE` is `True`
5. Verify DB file exists and has data: `python test_db_manual.py`

---

## Dynamics Toggle Behavior

- **Admin page toggle** persists to `econ-dynamics-mode` session store
- **fetch_dynamics_explainer callback** reads this store
- When **Off**: Dynamics button shows "Dynamics mode is currently off" instead of generating
- **Theory always works** regardless of toggle state

**TODO**: Add toggle to Daily View UI itself (not just admin) per user request.

