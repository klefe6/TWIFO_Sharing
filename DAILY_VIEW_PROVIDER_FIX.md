# Daily View Provider & Title Fix

## Issues Fixed

### 1. Provider Code Issue
**Problem:** All articles showed provider "O" (Others) instead of correct provider names like "Goldman Sachs"

**Root causes:**
- `summarize_pdf.py` only had 3 hardcoded provider prefixes (BOA, DB, MUFG)
- Missing all other providers (GM, MS, ING, JPM, etc.)

**Fix (summarize_pdf.py line ~3743):**
- Replaced hardcoded list with full `PROVIDER_PREFIXES` map
- Now detects all 30+ providers from PREFIX_MAP

### 2. Folder Matching Issue
**Problem:** New artifact folders (format: `YYYYMMDD__PROVIDER__slug__hash`) were not being discovered

**Root cause:**
- `twifo_app.py` was looking for old format `_YYYYMMDD_` (underscores on both sides)
- New format uses `YYYYMMDD__` at the start

**Fix (twifo_app.py line ~189):**
```python
# Old: if d.is_dir() and f"_{date_str}_" in d.name
# New: if d.is_dir() and (d.name.startswith(f"{date_str}__") or f"_{date_str}_" in d.name)
```
Now supports both new and legacy formats.

### 3. Title Cleaning Issue  
**Problem:** Titles showed raw filenames with underscores, dates, and provider prefixes

**Root cause:**
- `sum.json` meta.title contained raw filename
- Was overriding the clean title from `_title_from_folder` function

**Fix (twifo_app.py line ~220):**
- Only use sum.json title if it's already clean (no underscores or embedded dates)
- Otherwise use folder-derived clean title

### 4. Frequency Badge Issue
**Problem:** All articles showed "Unknown" frequency when most were known (w, m, q, u)

**Root cause:**
- `sum.json` meta.horizon was "u" (unknown) for all articles
- Was overriding the frequency extracted from folder name suffix (_w, _m, _q, etc.)

**Fix (twifo_app.py line ~229):**
- Only use sum.json horizon if it's not "u"
- Otherwise use frequency code extracted from folder name

## Results

**Before:**
- Provider: O (for all)
- Title: `GM_Commodity Analyst  What the Great Gold Rally..._20260211_u`
- Frequency: Unknown (u for all)

**After:**
- Provider: Goldman Sachs ✅
- Title: `Commodity Analyst What The Great Gold Rally Could Signal...` ✅
- Frequency: Correctly shows w (weekly), m (monthly), q (quarterly), u (unknown) ✅

## Files Modified

1. **`summarize_pdf.py`** - Provider detection expanded to all 30+ providers
2. **`twifo_app.py`** - Folder matching, provider fallback, title cleaning, frequency detection

## Testing

Run:
```bash
cd "c:\Coding Projects\TWIFO_Sharing"
python -c "from twifo_app import get_artifacts_for_date; from datetime import date; [print(f'{a[\"provider\"]:20} | {a[\"frequency_code\"]} | {a[\"title\"][:50]}') for a in get_artifacts_for_date(date(2026, 2, 11))]"
```

Expected output shows clean providers, titles, and frequencies.

## Next Steps

Future summaries will automatically get correct provider codes. Existing sum.json files with "O" will be overridden by folder-derived providers.
