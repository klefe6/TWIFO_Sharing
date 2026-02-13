# Yesterday Articles Helper - Implementation Summary

**Created:** 2026-02-13  
**File:** `twifo_app.py`

## Overview

Added `get_yesterday_articles()` helper function to retrieve article metadata for yesterday's date.

## Function Signature

```python
def get_yesterday_articles() -> List[Dict[str, str]]:
    """
    Get all articles from yesterday's date.
    
    Returns:
        List of dicts with keys: basename, title, provider, date_fmt, full_path
    """
```

## Implementation Details

### Date Calculation
- Calculates yesterday's date using `date.today() - timedelta(days=1)`
- Formats date as `YYYYMMDD` for file pattern matching
- Formats date as `YYYY-MM-DD` for output

### Article Discovery
- Scans `FILES_DIR` for files matching pattern: `*_{YYYYMMDD}_*__sum.json`
- Loads each JSON file to extract metadata
- Returns list of article metadata dictionaries

### Return Structure

Each article dict contains:
- `basename`: PDF filename (e.g., `JPM_20260212_Markets.pdf`)
- `title`: Article title from metadata
- `provider`: Provider name from metadata (e.g., "JP Morgan")
- `date_fmt`: Formatted date string (`YYYY-MM-DD`)
- `full_path`: Absolute path to the JSON file

### Debug Logging

Controlled by environment variable `TWIFO_DEBUG_DAILY_VIEW`:

```python
import os
os.environ["TWIFO_DEBUG_DAILY_VIEW"] = "1"  # Enable debug output
```

Debug output includes:
- Yesterday's date (both human-readable and YYYYMMDD format)
- Total JSON files discovered
- Successfully matched article count
- Individual file load failures (with error messages)

## Usage Examples

### Basic Usage

```python
from twifo_app import get_yesterday_articles

articles = get_yesterday_articles()
print(f"Found {len(articles)} articles from yesterday")

for article in articles:
    print(f"{article['provider']}: {article['title']}")
```

### With Debug Logging

```python
import os
from twifo_app import get_yesterday_articles

# Enable debug mode
os.environ["TWIFO_DEBUG_DAILY_VIEW"] = "1"

articles = get_yesterday_articles()
# Debug output automatically printed to console
```

### Integration in Dash Layout

```python
from twifo_app import get_yesterday_articles

# In your layout or callback
yesterday_articles = get_yesterday_articles()

layout = html.Div([
    html.H2(f"Yesterday's Articles ({len(yesterday_articles)})"),
    html.Ul([
        html.Li(f"{art['provider']}: {art['title']}")
        for art in yesterday_articles
    ])
])
```

## Testing

Run the included test script:

```bash
python test_yesterday_articles.py
```

## Error Handling

- Silently skips JSON files that fail to load
- Reports failures in debug mode only
- Returns empty list if no articles found (not an error condition)

## Dependencies

- `os` - Environment variable access
- `datetime` - Date calculations
- `pathlib` - File path operations
- `typing` - Type hints
- `json` - JSON file parsing

## Files Created

1. `twifo_app.py` - Main helper module with `get_yesterday_articles()`
2. `test_yesterday_articles.py` - Test script with debug output
3. `YESTERDAY_ARTICLES_HELPER.md` - This documentation

## Notes

- Function uses the same `FILES_DIR` as other TWIFO modules
- Follows existing naming conventions (`*__sum.json`)
- Compatible with both legacy and new file layouts
- Zero-OCR compliant - only reads existing JSON files
