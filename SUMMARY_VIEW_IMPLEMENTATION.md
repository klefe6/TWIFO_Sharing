# Summary View Implementation - Complete Guide

## Overview
Added a beautiful article Summary view to twifo.py that renders articles from sum.json (not PDF). Clicking any row in the table opens a detailed single-article view.

---

## Features Implemented

### 1. **Beautiful Article Rendering**
- Title + provider + date + extraction status/quality
- Low-confidence banner (when confidence < 70%)
- TL;DR (3 bullets, always shown)
- What moved today / can move tomorrow (if non-empty)
- Trade ideas as cards with product/bias/catalyst/setup/key_levels/risk/time_horizon
- Optional sections (what_occurred, forward_watch, warnings, tips, cross-asset, scenarios)
- Fingerprint quotes (collapsible)
- Numeric claims (collapsible table)
- Back button to return to articles list

### 2. **Failed/Stub Summary Handling**
- Clear "Failed Summary" message with warning icon
- Shows failure reason from extraction.reason
- Red/yellow color scheme
- Back button

### 3. **Dual Layout Support**
- Works with path_manager: `artifacts/<basename>/sum.json`
- Works with legacy: `<root>/<basename>__sum.json`

### 4. **Interactive Navigation**
- Click any table row → navigate to summary view
- URL routing: `/` (table) vs `/summary/<basename>`
- Browser back/forward buttons work correctly

---

## Implementation Details

### New Files

#### **`summary_view.py`** (382 lines)
Core rendering module with 6 functions:

1. **`load_summary_json(basename, files_dir, path_manager)`**
   - Loads sum.json from correct location
   - Returns parsed dict or None

2. **`is_stub_summary(sum_json)`**
   - Detects failed/stub summaries
   - Checks: `_is_stub` flag, `extraction.status == "failed"`, empty sections

3. **`render_failed_summary(sum_json, basename)`**
   - Renders failure view with warning icon
   - Shows extraction reason
   - Yellow/red warning colors

4. **`render_summary_view(basename, sum_json)`**
   - Main rendering function
   - Renders all sections in order
   - Handles empty sections gracefully

5. **`render_section(title, bullets, icon, bg_color, border_color)`**
   - Generic section renderer
   - Icon + title + bullet list
   - Customizable colors

6. **`render_trade_ideas(trade_ideas)`**
   - Renders trade ideas as cards
   - Color-codes bias: Bullish (green), Bearish (red), Neutral (gray)
   - Shows all fields: product, bias, catalyst, setup, key_levels, risk, time_horizon

---

### Modified Files

#### **`twifo.py`** (4 key changes)

##### **Change 1: Import Summary View Module** (Lines 19-29)
```python
# Import summary view renderer
try:
    from summary_view import load_summary_json, is_stub_summary, render_failed_summary, render_summary_view
    SUMMARY_VIEW_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Summary view not available: {e}")
    SUMMARY_VIEW_AVAILABLE = False
```

##### **Change 2: Update DataTable** (Lines 1185-1204)
Added hidden `basename` column for routing:
```python
columns=[
    {"id": "firm",             "name": "Firm"},
    # ... other columns ...
    {"id": "basename",         "name": "basename", "hidden": True},  # For routing
],
# Enable row clicks
row_selectable=False,
active_cell=None,  # Track cell clicks
```

##### **Change 3: Add Basename to Table Rows** (Lines 2030, 2095)
Rollup rows:
```python
"basename": file_info['fname'].replace('__sum.json', '').replace('.json', '')
```

Article rows:
```python
"basename": Path(file_info['fname']).stem  # Without .pdf extension
```

##### **Change 4: Update Layout Structure** (Lines 1426-1434)
Wrapped content in switchable containers:
```python
html.Div(id="main-content-container", children=[
    # Table view (default)
    html.Div(id="table-view-container", children=[files_layout], style={"display": "block"}),
    
    # Summary view (hidden by default)
    html.Div(id="summary-view-container", style={"display": "none"})
])
```

##### **Change 5: Add Callbacks** (Lines 2348-2438, new section 8)

**Callback 1: `navigate_to_summary`**
- **Trigger:** User clicks table row (`active_cell`)
- **Action:** Navigate to `/summary/<basename>`
- **Implementation:**
```python
@app.callback(
    Output("url", "pathname"),
    Input("files-table", "active_cell"),
    State("files-table", "data"),
    prevent_initial_call=True
)
def navigate_to_summary(active_cell, table_data):
    # Extract basename from clicked row
    # Navigate to /summary/<basename>
```

**Callback 2: `display_page`**
- **Trigger:** URL pathname changes
- **Action:** Show/hide table vs summary view, render content
- **Routes:**
  - `/` → Show table view
  - `/summary/<basename>` → Load and render summary view
- **Implementation:**
```python
@app.callback(
    [
        Output("table-view-container", "style"),
        Output("summary-view-container", "style"),
        Output("summary-view-container", "children"),
    ],
    Input("url", "pathname"),
    prevent_initial_call=False
)
def display_page(pathname):
    # Route between views
    # Load summary JSON
    # Check if stub → render_failed_summary
    # Else → render_summary_view
```

---

## User Flow

### Table → Summary View

1. **User clicks any row** in files table
   
2. **`navigate_to_summary` callback fires:**
   - Extracts `basename` from clicked row
   - Updates URL to `/summary/<basename>`

3. **`display_page` callback fires:**
   - Detects `/summary/` route
   - Calls `load_summary_json(basename, FILES_DIR, PATH_MANAGER)`
   - Checks if stub → calls `render_failed_summary()`
   - Else → calls `render_summary_view()`
   - Hides table view, shows summary view

4. **User sees rendered summary**
   - Beautiful layout with sections
   - Scrollable content
   - "Back to Articles" link

5. **User clicks "Back to Articles"**
   - URL changes to `/`
   - `display_page` callback hides summary, shows table

---

## Visual Design

### Color Scheme
- **Primary:** `#004080` (Hughes & Company blue)
- **Success:** `#28a745` (green for bullish/high confidence)
- **Warning:** `#ffc107` (yellow for degraded/neutral)
- **Danger:** `#dc3545` (red for failed/bearish)
- **Gray:** `#6c757d` (neutral elements)

### Layout Components

#### **Header**
- H1 title (28px, bold, blue)
- Metadata pills: Provider (blue), Date (gray), Horizon (green)
- Status line: Extraction status + confidence %
- Low confidence banner (if < 70%)

#### **Sections**
- H3 section title with icon
- Background color + border
- Bullet lists with spacing
- Responsive padding

#### **Trade Idea Cards**
- Product name (H4, blue)
- Bias badge (colored: green/red/gray)
- Catalyst, setup, key levels, risk, time horizon
- Box shadow + rounded corners

#### **Collapsible Sections**
- `<details>` + `<summary>` HTML elements
- Gray header bar
- Cursor pointer on hover
- Content appears below when expanded

---

## Test Coverage

### **`test_summary_view_integration.py`** (8 tests, all passing)

1. ✅ `test_load_summary_with_path_manager` - New layout loading
2. ✅ `test_load_summary_legacy` - Legacy layout loading
3. ✅ `test_is_stub_detection` - Stub/failed detection
4. ✅ `test_render_failed_summary` - Failed summary view
5. ✅ `test_render_full_summary` - Full summary with all sections
6. ✅ `test_render_minimal_summary` - Minimal summary (tldr only)
7. ✅ `test_low_confidence_banner` - Low confidence warning
8. ✅ `test_trade_idea_bias_colors` - Bias color coding

**Test Results:** 8/8 PASS ✅

---

## Code Locations

### Main Implementation
1. **`summary_view.py`** (NEW, 382 lines)
   - All rendering functions
   - Layout composition
   - Section formatting

2. **`twifo.py`** (5 modifications)
   - Lines 19-29: Import summary_view module
   - Lines 1185-1204: Add `basename` column + `active_cell`
   - Lines 2030, 2095: Add basename to table rows
   - Lines 1426-1434: Update layout with view containers
   - Lines 2348-2438: Add 2 new callbacks (section 8)

### Table Links to Summary View

**Mechanism:** DataTable `active_cell` property

**Flow:**
```
User clicks row
  ↓
active_cell = {row: 5, column: 0, column_id: "firm"}
  ↓
navigate_to_summary callback
  ↓
Extract basename from table_data[5]["basename"]
  ↓
Set url.pathname = "/summary/<basename>"
  ↓
display_page callback
  ↓
Render summary view
```

**Key Properties:**
- `active_cell`: Tracks which cell was clicked
- `basename` column: Hidden column with routing key
- `dcc.Location`: Enables URL-based routing
- `dcc.Link`: Back button for navigation

---

## How to Use

### As a User
1. Log in to twifo.py (port 8065)
2. Browse articles in table
3. **Click any row** (not just the link columns)
4. See beautiful summary view
5. Click "← Back to Articles" to return

### As a Developer
```python
# Load summary programmatically
from summary_view import load_summary_json
from path_manager import get_path_manager

pm = get_path_manager(FILES_DIR)
basename = "20260212__BOA__report__abc123"
sum_json = load_summary_json(basename, FILES_DIR, path_manager=pm)

# Render summary
if is_stub_summary(sum_json):
    layout = render_failed_summary(sum_json, basename)
else:
    layout = render_summary_view(basename, sum_json)
```

---

## Section Rendering Order

1. **Title + Metadata** (always shown)
2. **TL;DR** (always shown, required 3 bullets)
3. **What Moved Today** (if non-empty)
4. **What Can Move Tomorrow** (if non-empty)
5. **Trade Ideas** (if non-empty, rendered as cards)
6. **What Occurred** (if non-empty)
7. **Forward Watch** (if non-empty)
8. **Warnings** (if non-empty, yellow background)
9. **Tips & Reminders** (if non-empty)
10. **Cross-Asset Impacts** (if non-empty)
11. **Scenarios** (if non-empty)
12. **Fingerprint Quotes** (collapsible)
13. **Numeric Claims** (collapsible table)
14. **Back Button**

Empty sections are simply not displayed (no "No data" placeholders).

---

## Browser Compatibility

- Modern browsers with CSS3 support
- `<details>` / `<summary>` HTML5 elements
- Font Awesome icons (CDN loaded)
- Responsive layout (max-width: 900px)

---

## Files Summary

**New Files:** 2
- `summary_view.py` (382 lines) - Rendering module
- `test_summary_view_integration.py` (340 lines) - Integration tests

**Modified Files:** 1
- `twifo.py` - Added imports, layout containers, table column, callbacks

**Total Lines Added:** ~850
**Tests Added:** 8 (all passing)

---

## Next Steps (Optional Enhancements)

1. Add PDF viewer side-by-side with summary
2. Add "Edit Summary" button for corrections
3. Add social sharing buttons
4. Add print-friendly view
5. Add summary export (copy to clipboard)
6. Add keyboard shortcuts (← back, → next article)
