# TWIFO Website Current Setup - Context for ChatGPT Prompts

**Purpose:** This document explains the current state of the TWIFO website so ChatGPT can write better implementation prompts for new features.

**Last Updated:** 2026-02-16

---

## Architecture Overview

### Framework Stack
- **Web Framework:** Dash (Plotly) with Flask backend
- **Server Port:** `8065` (hardcoded in `twifo.py` line 3738)
- **Host:** `127.0.0.1` (localhost only)
- **Main Entry Point:** `twifo.py` (~3,739 lines)
- **UI Library:** Dash HTML components (`dash.html`, `dash.dcc`)

### Data Storage Model
**CRITICAL:** TWIFO does NOT use a traditional database (no SQLAlchemy, no migrations, no ORM).

- **Storage Type:** File-based JSON system
- **Article Summaries:** Stored as `*__sum.json` files in `artifacts/` folders
- **Daily Rollups:** Stored as `ROLLUP_DAILY_YYYYMMDD__sum.json` in `rollups/daily/`
- **Weekly Rollups:** Stored as `ROLLUP_WEEKLY_YYYYMMDD__sum.json` in `rollups/weekly/`
- **File Path:** `C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE`

**For Economic Calendar Feature:**
- You will need to ADD a database (SQLite recommended) for structured event data
- The existing codebase has NO database layer to reuse
- You must create new database models, connection handling, and migration scripts from scratch

---

## Daily Summary Page Location & Rendering

### Page Route
- **URL Pattern:** `/` (root) shows table view; `/summary/<basename>` shows individual article
- **Daily View:** Accessed via a "Daily View" tab/section in the main UI
- **Daily Summary Rendering:** Function `render_rollup_summary()` in `twifo.py` (line ~3296)

### How Daily Summary Works
1. **Data Source:** Daily rollup JSON files at `rollups/daily/ROLLUP_DAILY_YYYYMMDD__sum.json`
2. **Loading:** Function `load_rollup_json()` reads the JSON file
3. **Rendering:** `render_rollup_summary()` converts JSON to Dash HTML components
4. **Display Location:** Right panel in Daily View (see callback `display_daily_article_summary` at line ~3521)

### Current Daily Summary Structure
The rollup JSON contains:
- `meta`: date, providers, article_count
- `ui`: title, header_pills, chips_rows
- `sections`: 
  - `warnings` (list of dicts with `text`, `ai_context`, `sources`)
  - `executive_snapshot` (list)
  - `tldr` (list of dicts)
  - `trade_ideas` (dict with buckets: `d_1_3`, `w_1_2`, `gt_2w`, `watchlist_only`)
  - `observations` (dict keyed by asset class or flat list)
  - `forward_watch` (dict keyed by asset class or flat list)
  - `volatility_by_asset_class` (optional)
  - `forward_risks` (optional)

### Rendering Functions
- `render_rollup_summary()`: Main function that renders the rollup (line ~3296)
- `render_rollup_sections_detail()`: Renders expandable detail sections (line ~3477)
- `_render_web_bullet()`: Renders individual bullet items with optional `ai_context` (line ~3240)

---

## Routing Layout

### Current Routes
1. **`/` (root):** Main table view (article listing)
2. **`/summary/<basename>`:** Individual article summary view
3. **`/view?file=<filename>`:** Flask route to serve PDF/view files (line ~2728)
4. **`/download?file=<filename>`:** Flask route to download files (line ~2809)

### Navigation
- **URL Routing:** Uses `dcc.Location` component with `id="url"`
- **Callback:** `display_page()` at line ~2910 handles routing between table and summary views
- **Daily View:** Separate section with its own callbacks (starts at line ~2943)

### Adding New Routes
- **For Admin Pages:** Add new Dash callback that listens to `Input("url", "pathname")`
- **For API Endpoints:** Add Flask routes using `@server.route("/api/...")` (server is the Flask app from Dash)

---

## Backend Framework Details

### Flask Server
- **Access:** `server = app.server` (Flask app from Dash)
- **Current Routes:** Only `/view` and `/download` exist
- **No REST API:** Currently no `/api/*` endpoints exist

### Dash App Structure
- **App Instance:** `app = dash.Dash(__name__)` (line ~270)
- **Layout:** Defined in `app.layout` (starts around line ~1400)
- **Callbacks:** Use `@app.callback()` decorator
- **State Management:** Uses `dcc.Store` components for client-side data

### File System Access
- **FILES_DIR:** Hardcoded path (see `twifo_app.py` line ~17-20)
- **Path Manager:** Optional module `path_manager.py` for new file layout support
- **Legacy Support:** Code handles both old (`*__sum.json` in root) and new (`artifacts/<basename>/sum.json`) layouts

---

## LLM Integration

### Client Setup
- **Module:** `openai_client.py` provides `get_client()` singleton
- **Authentication:** Uses `auth_env.py` for API key management
- **Model Default:** `gpt-4o` (configurable via `TWIFO_ROLLUP_MODEL` env var)

### Current LLM Usage
- **Rollup Generation:** `rollup_aggregator.py` calls LLM to aggregate article summaries
- **Prompt System:** Prompts stored in `twifo_prompts/prompts/rollup_prompts.py`
- **Caching:** No explicit caching layer for LLM responses (would need to be added)

### For Economic Calendar Analysis
- **Reuse:** Use `openai_client.get_client()` for consistency
- **Caching:** You'll need to implement a caching table (see Prompt 4 requirements)
- **Context:** Can access daily rollup JSON to infer macro context for dynamics blurbs

---

## UI Components & Styling

### Component Library
- **Dash HTML:** `html.Div`, `html.H2`, `html.P`, `html.Ul`, `html.Li`, etc.
- **Dash Core:** `dcc.Loading`, `dcc.Store`, `dcc.Location`, `dash_table.DataTable`
- **No Custom CSS Framework:** Uses inline styles only

### Current Styling Patterns
- **Colors:**
  - Header: `#0056B3` (blue)
  - Warnings: `#fff3cd` (yellow background)
  - Success: `#28a745` (green)
  - Danger: `#dc3545` (red)
- **Badges/Pills:** Inline `html.Span` with backgroundColor, padding, borderRadius
- **Cards:** `html.Div` with border, padding, borderRadius
- **Expandable Sections:** Uses `dcc.Checklist` or custom buttons with state toggles

### UI Consistency Rules
- **No External CSS:** All styles are inline dictionaries
- **No Design System:** Ad-hoc styling, but follows color scheme above
- **Responsive:** Basic responsive design via flexbox in inline styles

---

## Current Features & Constraints

### Existing Features
1. **Article Table View:** Lists all articles with filters (provider, date, search)
2. **Individual Article Summary:** Click row → view detailed summary
3. **Daily View:** Shows articles for a selected date with rollup summary
4. **Rollup Display:** Shows warnings, TLDR, trade ideas, observations, forward watch
5. **File Serving:** View/download PDFs and summaries

### Constraints for New Features
1. **No Database:** Must add SQLite (or similar) for Economic Calendar
2. **No API Layer:** Must create Flask routes for `/api/econ-*` endpoints
3. **File-Based Rollups:** Daily summaries come from JSON files, not database queries
4. **No Admin UI:** Currently no admin/tools menu exists (must be added)
5. **Port Fixed:** Server runs on 8065 (don't change)

### Daily Summary Integration Points
- **Location:** Right panel in Daily View (callback `display_daily_article_summary`)
- **Data Flow:** 
  1. User selects date in Daily View
  2. System loads `ROLLUP_DAILY_YYYYMMDD__sum.json`
  3. `render_rollup_summary()` displays it
  4. **New Feature:** Add Economic Events panel below existing sections
- **Modification Point:** `render_rollup_summary()` function - add new panel at end of `children` list

---

## File Structure Reference

### Key Files
- `twifo.py`: Main application (3,739 lines) - contains all UI and routing
- `twifo_app.py`: Helper functions for Daily View (artifact loading)
- `summary_view.py`: Renders individual article summaries
- `rollup_aggregator.py`: LLM-powered rollup generation
- `rollup_schema.py`: Schema documentation for rollup JSON
- `generate_rollup_clean.py`: CLI tool to generate daily/weekly rollups
- `openai_client.py`: OpenAI client singleton
- `path_manager.py`: File layout manager (optional)

### Data Directories
- `artifacts/`: Individual article folders with `sum.json`, `sum.pdf`, original PDF
- `rollups/daily/`: Daily rollup JSON/TXT/PDF files
- `rollups/weekly/`: Weekly rollup JSON/TXT/PDF files

---

## Implementation Notes for Economic Calendar

### Database Setup (NEW)
- **Database Type:** SQLite recommended (simple, no server needed)
- **Location:** Create `twifo.db` or `data/twifo.db` in project root
- **Migration Tool:** Use Alembic or simple SQL scripts (no existing tool to reuse)
- **Connection:** Create new module `database.py` or add to existing file

### API Endpoints (NEW)
- **Pattern:** `@server.route("/api/econ-weeks", methods=["POST"])`
- **Location:** Add to `twifo.py` after existing Flask routes (after line ~2809)
- **JSON Responses:** Use `flask.jsonify()` for responses
- **Error Handling:** Return 400 with JSON error messages

### Admin UI (NEW)
- **Navigation:** Add link/button in main layout 
  - **Location:** In `app.layout` around line 1400-1600, add button near "View Latest Daily Recap" button (line ~1514)
  - **Alternative:** Add as a new row above the title or in a navigation bar
- **Page Route:** Create new route like `/admin/economic-calendar`
  - **Routing:** Add callback that listens to `Input("url", "pathname")` similar to `display_page()` at line ~2910
- **Components:** Reuse existing Dash components (textarea, buttons, tables)
- **Styling:** Match existing inline style patterns
- **No Existing Admin Menu:** Currently no admin/tools section exists - must create from scratch

### Daily Summary Integration
- **Modification Point:** `render_rollup_summary()` function in `twifo.py` (line ~3296)
- **Display Location:** Right panel in Daily View tab
  - **Container ID:** `daily-view-content` (line ~1900-1910)
  - **Layout:** Two-column layout with sidebar (articles) on left, content on right
  - **Current Content:** Rollup summary is rendered when date is selected and rollup exists
- **Data Fetching:** Call new API endpoint `GET /api/econ-events?date=YYYY-MM-DD`
- **Rendering:** Add new panel to `children` list in `render_rollup_summary()` before return statement
  - **Insertion Point:** After existing sections (warnings, TLDR, trade ideas, observations, forward watch)
  - **Format:** Use `html.Div` with similar styling to existing sections
- **LLM Integration:** Use `openai_client.get_client()` for analysis generation
- **Caching:** Store in new `econ_event_analysis` table (part of new database)

---

## Testing Infrastructure

### Current Testing
- **Test Files:** Many `test_*.py` files exist in root directory
- **No Test Framework Specified:** Uses standard `unittest` or pytest
- **Test Patterns:** Look at `test_rollup_*.py` for examples

### For Economic Calendar Tests
- **Unit Tests:** Test parser with sample text blocks
- **Integration Tests:** Test API endpoints with test database
- **UI Tests:** Manual testing (Dash doesn't have great automated UI testing)

---

## Important Gotchas

1. **No Database:** Don't assume SQLAlchemy or migrations exist - you must create them
2. **File-Based:** Daily summaries are JSON files, not database queries
3. **Port 8065:** Don't change the server port
4. **No Admin Menu:** Must create navigation for admin pages
5. **Inline Styles Only:** No external CSS files or design system
6. **Dash Callbacks:** All UI updates happen via Dash callbacks, not direct DOM manipulation
7. **Flask Routes:** API endpoints use Flask (`@server.route`), not Dash callbacks
8. **Path Manager:** Optional module - code must work with or without it
9. **Legacy Support:** Must handle both old and new file layouts
10. **LLM Client:** Always use `openai_client.get_client()` for consistency

---

## Summary for Prompt Writing

When writing prompts for Economic Calendar feature:

1. **Database:** Specify SQLite with Alembic migrations (new, not existing)
2. **API:** Add Flask routes in `twifo.py` after line 2809
3. **Admin UI:** Create new Dash page with route `/admin/economic-calendar`
4. **Daily Summary:** Modify `render_rollup_summary()` to add Economic Events panel
5. **LLM:** Use `openai_client.get_client()` and implement caching table
6. **Styling:** Match existing inline style patterns (no external CSS)
7. **Testing:** Add unit tests for parser, integration tests for API
8. **Port:** Confirm server runs on 8065 (don't change)

---

**End of Document**

