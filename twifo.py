import os
import datetime
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from typing import Optional

# compute today's ISO date once:
TODAY = datetime.date.today().isoformat()  # e.g. "2025-05-21"

import urllib.parse

import dash
from dash import dcc, html, dash_table, Input, Output, State, ctx
from flask import request, send_from_directory
from PyPDF2 import PdfReader  # for in-PDF keyword search (beta)

# ── new prefix map & detector ──
PREFIX_MAP = {
    "BOA_":   "Bank of America",
    "BA_":    "Barclays",
    "BR_":    "BlackRock",
    "DB_":    "Deutsche Bank",
    "GM_":    "Goldman Sachs",
    "HT_":    "HighTower Research",
    "JPM_":   "JP Morgan",
    "MZ_":    "Mizuho",
    "TSL_":   "TSLombard",
    "T_":     "TWIFO",
    "WF_":    "Wells Fargo",
    "SEB_":   "SEB Commodities",
    "R_":     "Rabobank",
    "MUFG_":  "MUFG",
    "ANZ_":   "ANZ",
    "BCA_":   "BCA",
    "BNPP_":  "BNPP",
    "BNY_":   "Bank of New York Melon",
    "CACIB_": "CACIB",
    "CITI_":  "Citi",
    "HSBC_":  "HSBC",
    "ING_":   "ING",
    "MS_":    "Morgan Stanley",
    "NOM_":   "Nomura",
    "RBC_":   "RBC",
    "SG_":    "SocGen",
    "STI_":   "Stifel",
    "TME_":   "TME",
    "UBS_":   "UBS",
}

# ── product list & names ──
PRODUCT_MAP = {
    "NQ": "Nasdaq 100",
    "Dow": "Dow Jones",
    "ES": "E-mini S&P 500",
    "GC": "Gold",
    "SI": "Silver",
    "ZN": "10-Year Note",
    "BTC": "Bitcoin",
    "CL": "Crude Oil",
    "NG": "Natural Gas",
    "HG": "Copper",
    "ZC": "Corn",
    "ZS": "Soybeans",
    "ZW": "Wheat",
    "HO": "Heating Oil",
    "RB": "Gasoline",
    "RTY": "Russell 2000",
    "VIX": "Volatility Index",
    "EUR": "Euro",
    "GBP": "British Pound",
    "JPY": "Japanese Yen",
    "CHF": "Swiss Franc",
    "AUD": "Australian Dollar",
    "CAD": "Canadian Dollar",
    "ZB": "30-Year Bond",
    "ZF": "5-Year Note",
    "ZT": "2-Year Note",
    "TN": "10-Year Ultra",
    "UB": "Ultra Bond",
}

PRODUCT_LIST = list(PRODUCT_MAP.keys())

def detect_category(fname: str) -> str:
    """Return the matching category from PREFIX_MAP, or 'Others'."""
    for pfx, cat in PREFIX_MAP.items():
        if fname.startswith(pfx):
            return cat
    return "Others"


def detect_products(text: str) -> list[str]:
    """Return list of product codes found in text (case-insensitive)."""
    import re
    text_upper = text.upper()
    found = []
    for prod in PRODUCT_LIST:
        # Match product as whole word (surrounded by word boundaries)
        pattern = r'\b' + re.escape(prod) + r'\b'
        if re.search(pattern, text_upper):
            found.append(prod)
    return found


############################
# 1) CONFIGURATION
############################

APP_TITLE = "H&C Internal Research Directory"
FILES_DIR = os.path.normpath(
    r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE"
)

# PDF search cache configuration
PDF_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".pdf_cache")
PDF_CACHE_FILE = os.path.join(PDF_CACHE_DIR, "pdf_text_cache.json")
MAX_PAGES_TO_SCAN = 10  # Only scan first N pages for faster search
MAX_WORKERS = 4  # Number of parallel PDF processors

# Two user credentials
CREDENTIALS = {
    "jlu":      {"password": "jlu25%^&",    "greeting": "Hello James,"},
    "dhughes":  {"password": "RV&",  "greeting": ""},
    "iwill":    {"password": "win",  "greeting": "Hello Winner,"}
}
LOG_FILE = os.path.expanduser("~/Documents/login_log.txt")

# Corporate colors
HEADER_BG_COLOR   = "#004080"
HEADER_TEXT_COLOR = "white"
ROW_ODD_COLOR     = "#f2f2f2"
ROW_EVEN_COLOR    = "white"
APP_BG_COLOR      = "#f7f9fa"
TITLE_COLOR       = "#004080"

############################
# 2) HELPERS
############################

def get_category_options():
    """Build sorted list of all categories with file counts."""
    # build a sorted list of all categories + "Others"
    categories = sorted(set(PREFIX_MAP.values()) | {"Others"})
    counts = {cat: 0 for cat in categories}

    # scan your FILES_DIR with error handling
    try:
        if os.path.isdir(FILES_DIR):
            for fname in os.listdir(FILES_DIR):
                if not fname.lower().endswith(".pdf") or fname == "README.txt":
                    continue
                cat = detect_category(fname)
                counts[cat] += 1
    except Exception as e:
        # If directory scan fails, return empty counts but still show categories
        print(f"Warning: Could not scan FILES_DIR: {e}")

    return [
        {"label": f"{cat} ({counts[cat]})", "value": cat}
        for cat in categories
    ]


def get_product_options():
    """Build sorted list of all products with file counts and names."""
    counts = {prod: 0 for prod in PRODUCT_LIST}

    # scan FILES_DIR for product mentions
    try:
        if os.path.isdir(FILES_DIR):
            for fname in os.listdir(FILES_DIR):
                if not fname.lower().endswith(".pdf") or fname == "README.txt":
                    continue
                # detect products in filename
                products = detect_products(fname)
                for prod in products:
                    counts[prod] += 1
    except Exception as e:
        print(f"Warning: Could not scan FILES_DIR for products: {e}")

    return [
        {"label": f"{prod} - {PRODUCT_MAP[prod]} ({counts[prod]})", "value": prod}
        for prod in PRODUCT_LIST
    ]

# ── 0b) Precompute sorted category/product options ──
try:
    _raw_opts = get_category_options()
    _base = sorted([o for o in _raw_opts if o["value"] != "Others"],
                   key=lambda o: o["label"])
    _others = [o for o in _raw_opts if o["value"] == "Others"]
    CATEGORY_OPTIONS = _base + _others
except Exception as e:
    # Fallback to basic category list if initialization fails
    print(f"Warning: Could not initialize category options: {e}")
    CATEGORY_OPTIONS = [
        {"label": f"{cat} (0)", "value": cat}
        for cat in sorted(set(PREFIX_MAP.values()) | {"Others"})
    ]

try:
    PRODUCT_OPTIONS = get_product_options()
except Exception as e:
    print(f"Warning: Could not initialize product options: {e}")
    PRODUCT_OPTIONS = [
        {"label": f"{prod} (0)", "value": prod}
        for prod in PRODUCT_LIST
    ]

def _extract_pdf_text(filepath: str, max_pages: int = MAX_PAGES_TO_SCAN) -> str:
    """Extract text from first N pages of PDF."""
    try:
        reader = PdfReader(filepath)
        text_parts = []
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                break
            text = page.extract_text() or ""
            text_parts.append(text)
        return " ".join(text_parts).lower()
    except Exception as e:
        print(f"Error extracting text from {filepath}: {e}")
        return ""


def _get_file_hash(filepath: str) -> str:
    """Get file modification time hash for cache invalidation."""
    try:
        mtime = os.path.getmtime(filepath)
        size = os.path.getsize(filepath)
        return hashlib.md5(f"{filepath}_{mtime}_{size}".encode()).hexdigest()
    except Exception:
        return ""


def _load_pdf_cache() -> dict:
    """Load PDF text cache from disk."""
    try:
        if os.path.exists(PDF_CACHE_FILE):
            with open(PDF_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load PDF cache: {e}")
    return {}


def _save_pdf_cache(cache: dict) -> None:
    """Save PDF text cache to disk."""
    try:
        os.makedirs(PDF_CACHE_DIR, exist_ok=True)
        with open(PDF_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save PDF cache: {e}")


@lru_cache(maxsize=1)
def _get_cache() -> dict:
    """Get cached PDF text with file-level caching."""
    return _load_pdf_cache()


def pdf_contains_cached(filepath: str, term_lower: str) -> bool:
    """Check if PDF contains term using cached text extraction."""
    cache = _get_cache()
    file_hash = _get_file_hash(filepath)
    
    # Check if we have cached text for this file
    cache_key = os.path.normpath(filepath)
    cached_entry = cache.get(cache_key)
    
    if cached_entry and cached_entry.get('hash') == file_hash:
        # Use cached text
        cached_text = cached_entry.get('text', '')
        return term_lower in cached_text
    else:
        # Extract and cache text
        text = _extract_pdf_text(filepath)
        if text:
            cache[cache_key] = {'hash': file_hash, 'text': text}
            _save_pdf_cache(cache)
            _get_cache.cache_clear()  # Clear LRU cache to reload
            return term_lower in text
    return False


def pdf_contains_batch(filepaths: list, term_lower: str) -> dict:
    """Check multiple PDFs in parallel for term presence."""
    results = {}
    total = len(filepaths)
    
    def check_single_pdf(filepath: str) -> tuple[str, bool]:
        return filepath, pdf_contains_cached(filepath, term_lower)
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {executor.submit(check_single_pdf, fp): fp for fp in filepaths}
        completed = 0
        for future in as_completed(future_to_file):
            try:
                filepath, found = future.result()
                results[filepath] = found
                completed += 1
                # Log progress (can be used for future real-time updates)
                if completed % max(1, total // 10) == 0 or completed == total:
                    print(f"PDF search progress: {completed}/{total} files ({100*completed//total}%)")
            except Exception as e:
                filepath = future_to_file[future]
                print(f"Error processing {filepath}: {e}")
                results[filepath] = False
                completed += 1
    
    return results


# Legacy function for backwards compatibility
def pdf_contains(filepath: str, term_lower: str) -> bool:
    """Legacy wrapper - use pdf_contains_cached for better performance."""
    return pdf_contains_cached(filepath, term_lower)


def has_summary_file(filepath: str) -> tuple[bool, str, str]:
    """
    Check if summary file exists for given PDF.
    Returns: (has_pdf: bool, pdf_filename: str, json_filename: str)
    
    Prefers PDF summaries over JSON. Returns both filenames so we can:
    - Link to PDF if it exists
    - Generate PDF from JSON if JSON exists but PDF doesn't
    
    Note: Returns just the filenames (not full paths) for URL generation.
    """
    if not filepath.endswith('.pdf'):
        return False, "", ""
    
    # Build summary paths (same directory as source)
    base_path = filepath[:-4]  # Remove .pdf extension
    dir_path = os.path.dirname(filepath)
    base_name = os.path.basename(base_path)
    
    # Check for __sum.pdf (preferred format)
    summary_pdf = os.path.join(dir_path, f"{base_name}__sum.pdf")
    pdf_filename = f"{base_name}__sum.pdf" if os.path.isfile(summary_pdf) else ""
    
    # Check for __sum.json (source for PDF generation)
    summary_json_new = os.path.join(dir_path, f"{base_name}__sum.json")
    json_filename = f"{base_name}__sum.json" if os.path.isfile(summary_json_new) else ""
    
    # Check for legacy .summary.json
    summary_json_legacy = f"{base_path}.summary.json"
    if not json_filename and os.path.isfile(summary_json_legacy):
        json_filename = os.path.basename(summary_json_legacy)
    
    has_pdf = bool(pdf_filename)
    has_json = bool(json_filename)
    
    # Return True if we have either PDF or JSON (JSON can be converted to PDF)
    if has_pdf or has_json:
        return True, pdf_filename, json_filename
    
    return False, "", ""


def load_product_categories_from_summary(summary_path: str) -> dict:
    """
    Load product categories from summary JSON file.
    Returns: {"Metals": ["gold", "silver"], "Energy": ["oil"], ...} or empty dict
    """
    try:
        if not os.path.exists(summary_path):
            return {}
        
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        
        # Return product_categories if present
        return summary.get("product_categories", {})
    except Exception:
        return {}


def load_summary_score(summary_path: str) -> tuple[Optional[int], Optional[int]]:
    """
    Load summary_score_0_10 and chart_score_0_3 from summary JSON file.
    Returns: (summary_score, chart_score) or (None, None) if not found/invalid
    """
    try:
        if not os.path.exists(summary_path):
            return None, None
        
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        
        # Get summary score (0-10)
        summary_score = summary.get("summary_score_0_10")
        if summary_score is not None:
            try:
                summary_score = int(summary_score)
                summary_score = max(0, min(10, summary_score))
            except (ValueError, TypeError):
                summary_score = None
        
        # Get chart score (0-3)
        chart_score = summary.get("chart_score_0_3")
        if chart_score is not None:
            try:
                chart_score = int(chart_score)
                chart_score = max(0, min(3, chart_score))
            except (ValueError, TypeError):
                chart_score = None
        
        return summary_score, chart_score
    except Exception:
        return None, None


def format_product_categories(categories: dict) -> str:
    """
    Format product categories dict as compact display string.
    Example: {"E": ["CL", "NG"], "M": ["GC"]} -> "E (CL, NG), M (GC)"
    """
    if not categories:
        return "—"
    
    parts = []
    for cat_code, tickers in sorted(categories.items()):
        if isinstance(tickers, list) and tickers:
            tickers_str = ", ".join(tickers)
            parts.append(f"{cat_code} ({tickers_str})")
        elif tickers:
            parts.append(f"{cat_code} ({tickers})")
    
    return ", ".join(parts) if parts else "—"

############################
# 3) INITIALIZE APP
############################

app = dash.Dash(
    __name__,
    external_stylesheets=["https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css"],
    suppress_callback_exceptions=True
)
app.title = APP_TITLE
server = app.server

############################
# 4a) FILES LAYOUT
############################
files_layout = html.Div(
    id="files-section",
    style={"backgroundColor": APP_BG_COLOR, "padding": "40px 20px", "minHeight": "100vh"},
    children=[

        # Title
        html.H1(
            APP_TITLE,
            style={
                "width": "100%",
                "textAlign": "center",
                "color": TITLE_COLOR,
                "marginBottom": "20px",
                "fontFamily": "Arial, sans-serif",
            },
        ),

        # ── Row 1: Author/Source Filter (3 cols, Others last) ──
        html.Div(
            style={
                "display": "flex",
                "justifyContent": "center",
                "alignItems": "flex-start",
                "gap": "20px",
                "marginBottom": "20px",
            },
            children=[
                html.Div(
                    dcc.Checklist(
                        id="box-dropdown",
                        options=CATEGORY_OPTIONS,
                        value=[opt["value"] for opt in CATEGORY_OPTIONS],  # all selected by default
                        inputStyle={"marginRight": "6px"},
                        labelStyle={"display": "block"},
                    ),
                    style={
                        "columnCount": 3,
                        "columnGap": "1em",
                        "border": "1px solid #ccc",
                        "borderRadius": "4px",
                        "padding": "10px",
                        "maxHeight": "260px",
                        "overflowY": "auto",
                        "width": "80%",
                        "margin": "0 auto",
                    },
                ),
                html.Div(
                    [
                        html.Button(
                            "Select All", id="select-all", n_clicks=0,
                            className="btn btn-sm btn-outline-primary"
                        ),
                        html.Button(
                            "Clear All",  id="clear-all",  n_clicks=0,
                            className="btn btn-sm btn-outline-secondary"
                        ),
                    ],
                    style={
                        "display": "flex",
                        "flexDirection": "column",
                        "gap": "8px",
                        "justifyContent": "center",
                    },
                ),
            ],
        ),

        # ── Row 2: Product Filter (3 cols) ──
        html.Div(
            style={
                "display": "flex",
                "justifyContent": "center",
                "alignItems": "flex-start",
                "gap": "20px",
                "marginBottom": "20px",
            },
            children=[
                html.Div(
                    dcc.Checklist(
                        id="product-dropdown",
                        options=PRODUCT_OPTIONS,
                        value=[opt["value"] for opt in PRODUCT_OPTIONS],  # all selected by default
                        inputStyle={"marginRight": "6px"},
                        labelStyle={"display": "block"},
                    ),
                    style={
                        "columnCount": 3,
                        "columnGap": "1em",
                        "border": "1px solid #ccc",
                        "borderRadius": "4px",
                        "padding": "10px",
                        "maxHeight": "200px",
                        "overflowY": "auto",
                        "width": "70%",
                        "margin": "0 auto",
                    },
                ),
                html.Div(
                    [
                        html.Button(
                            "Select All", id="select-all-products", n_clicks=0,
                            className="btn btn-sm btn-outline-primary"
                        ),
                        html.Button(
                            "Clear All",  id="clear-all-products",  n_clicks=0,
                            className="btn btn-sm btn-outline-secondary"
                        ),
                    ],
                    style={
                        "display": "flex",
                        "flexDirection": "column",
                        "gap": "8px",
                        "justifyContent": "center",
                    },
                ),
            ],
        ),

        # ── Row 3: Search Bars + Date Range + Counter (horizontal layout) ──
        html.Div(
            style={
                "display": "flex",
                "flexWrap": "wrap",
                "justifyContent": "center",
                "alignItems": "center",
                "gap": "15px",
                "marginBottom": "20px",
                "padding": "15px",
                "backgroundColor": "#f8f9fa",
                "borderRadius": "8px",
                "border": "1px solid #dee2e6",
            },
            children=[
                # Title search
                dcc.Input(
                    id="title-search-input",
                    type="text",
                    placeholder="Search Titles…",
                    debounce=True,
                    style={"width": "250px", "padding": "6px"},
                ),
                html.Button("×", id="clear-title-search", className="btn btn-link btn-sm"),
                html.Button("Search", id="title-search-btn", className="btn btn-primary btn-sm"),
                
                # Content search
                dcc.Input(
                    id="content-search-input",
                    type="text",
                    placeholder="Search inside PDFs…",
                    debounce=True,
                    style={"width": "250px", "padding": "6px"},
                ),
                html.Button("×", id="clear-content-search", className="btn btn-link btn-sm"),
                html.Button("Search", id="content-search-btn", className="btn btn-primary btn-sm"),
                
                # Date range
                html.Label(
                    "📅",
                    style={'fontWeight': 'bold', 'fontSize': '14px', 'marginLeft': '10px'}
                ),
                dcc.DatePickerRange(
                    id='date-range-picker',
                    start_date=None,
                    end_date=None,
                    display_format='YYYY-MM-DD',
                    style={'fontSize': '13px'},
                    clearable=True
                ),
                html.Button(
                    "Clear",
                    id="clear-dates-btn",
                    className="btn btn-sm btn-outline-secondary",
                ),
                
                # Article counter
                html.Div(
                    id='article-counter',
                    style={
                        'fontSize': '15px',
                        'color': '#495057',
                        'fontWeight': '500',
                        'marginLeft': '10px'
                    },
                    children="Loading..."
                ),
            ],
        ),

        # Row 4: Progress bar section
        html.Div(
            style={
                'display': 'flex',
                'justifyContent': 'center',
                'alignItems': 'center',
                'gap': '20px',
                'marginBottom': '20px',
            },
            children=[
                html.Div(
                    id="progress-container",
                    style={"visibility": "hidden", "marginBottom": "10px"},
                    children=[
                        html.Div(
                            id="progress-text",
                            style={"textAlign": "center", "marginBottom": "5px", "fontSize": "14px", "color": "#666"},
                            children=""
                        ),
                        html.Div(
                            className="progress",
                            style={"height": "25px"},
                            children=[
                                html.Div(
                                    id="progress-bar",
                                    className="progress-bar progress-bar-striped progress-bar-animated",
                                    role="progressbar",
                                    style={"width": "0%", "transition": "width 0.3s ease"},
                                    children="0%"
                                )
                            ],
                        ),
                    ],
                ),
            ],
        ),

        # Row 5: DataTable
        dcc.Loading(
            id="loading-table",
            type="default",
            style={"width": "100%"},
            children=[
                    dash_table.DataTable(
                    id="files-table",
                    columns=[
                        {"id": "firm",             "name": "Firm"},
                        {"id": "frequency",        "name": "Frequency"},
                        {"id": "date",             "name": "Date"},
                        {"id": "title",            "name": "Title"},
                        {"id": "product_categories", "name": "Categories"},
                        {"id": "view",             "name": "View",    "presentation": "markdown"},
                        {"id": "summary",          "name": "Summary", "presentation": "markdown"},
                        {"id": "summary_score",    "name": "Score",   "type": "numeric"},
                        {"id": "chart_score",      "name": "Charts",  "type": "numeric"},
                    ],
                    data=[],
                    filter_action="native",
                    sort_action="native",
                    page_action="native",
                    page_size=20,


                    # highlight today's rows
                    style_data_conditional=[
                        # 1) odd/even for all the other rows
                        {"if": {"row_index": "odd"},  "backgroundColor": ROW_ODD_COLOR},
                        {"if": {"row_index": "even"}, "backgroundColor": ROW_EVEN_COLOR},

                        # 2) Summary/Score column color coding based on score (0-10 scale)
                        # 0-2: Dark red
                        {
                            "if": {"filter_query": "{summary_score} <= 2 && {summary_score} >= 0", "column_id": "summary"},
                            "backgroundColor": "#8B0000",  # Dark red
                        },
                        {
                            "if": {"filter_query": "{summary_score} <= 2 && {summary_score} >= 0", "column_id": "summary_score"},
                            "backgroundColor": "#8B0000",
                            "color": "white"
                        },
                        # 3-4: Red-orange
                        {
                            "if": {"filter_query": "{summary_score} > 2 && {summary_score} <= 4", "column_id": "summary"},
                            "backgroundColor": "#FF4500",  # Orange-red
                        },
                        {
                            "if": {"filter_query": "{summary_score} > 2 && {summary_score} <= 4", "column_id": "summary_score"},
                            "backgroundColor": "#FF4500",
                        },
                        # 5: Yellow
                        {
                            "if": {"filter_query": "{summary_score} = 5", "column_id": "summary"},
                            "backgroundColor": "#FFD700",  # Gold/Yellow
                        },
                        {
                            "if": {"filter_query": "{summary_score} = 5", "column_id": "summary_score"},
                            "backgroundColor": "#FFD700",
                        },
                        # 6-7: Yellow-green
                        {
                            "if": {"filter_query": "{summary_score} > 5 && {summary_score} <= 7", "column_id": "summary"},
                            "backgroundColor": "#9ACD32",  # Yellow-green
                        },
                        {
                            "if": {"filter_query": "{summary_score} > 5 && {summary_score} <= 7", "column_id": "summary_score"},
                            "backgroundColor": "#9ACD32",
                        },
                        # 8-10: Green
                        {
                            "if": {"filter_query": "{summary_score} > 7 && {summary_score} <= 10", "column_id": "summary"},
                            "backgroundColor": "#228B22",  # Forest green
                        },
                        {
                            "if": {"filter_query": "{summary_score} > 7 && {summary_score} <= 10", "column_id": "summary_score"},
                            "backgroundColor": "#228B22",
                            "color": "white"
                        },

                        # 3) then your today‐rule *last* (overrides summary colors)
                        {
                            "if": {"filter_query": f'{{date}} eq "{TODAY}"'},
                            "backgroundColor": "#e6f7ff",
                        },
                    ],

                    style_table={"width": "100%", "overflowX": "auto"},
                    style_cell={
                        "textAlign": "left",
                        "padding": "8px",
                        "fontFamily": "Arial, sans-serif",
                        "whiteSpace": "nowrap",
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                    },
                    style_header={
                        "backgroundColor": HEADER_BG_COLOR,
                        "color": HEADER_TEXT_COLOR,
                        "fontWeight": "bold",
                    },
                )
            ],
        ),
    ],
)


############################
# 4) APP LAYOUT (with LOGIN + MAIN)
############################
app.layout = html.Div([

    # store to track login status
    dcc.Store(id='login-status', storage_type='session', data=False),
        # store to track which user is logged in
    dcc.Store(id='login-user',   storage_type='session', data=""),

    

    # dummy div for clientside scroll callback
    html.Div(id='dummy-output', style={'display': 'none'}),

    # --- LOGIN SECTION ---
    html.Div(
        id='login-section',
        style={
            'display': 'flex',
            'flexDirection': 'column',
            'alignItems': 'center',
            'justifyContent': 'center',
            'height': '100vh'
        },
        children=[
            html.Div(
                style={
                    'backgroundColor': '#fff',
                    'padding': '40px',
                    'borderRadius': '8px',
                    'boxShadow': '0 2px 5px rgba(0,0,0,0.15)',
                    'textAlign': 'center',
                    'maxWidth': '400px'
                },
                children=[
                    html.H1(APP_TITLE, style={'marginBottom': '20px', 'color': '#333'}),

                    # Disclaimer
                    html.Div(
                        style={'textAlign': 'left', 'marginBottom': '20px', 'fontSize': '14px'},
                        children=[
                            html.P(
                                "Disclaimer: This directory is for authorized Hughes & Company users only. "
                                "Articles here may not be redistributed without permission."
                            )
                            
                        ]
                    ),

                    # Username + Password
                    dcc.Input(
                        id='login-username', type='text', placeholder='Username',
                        style={
                            'marginBottom': '10px',
                            'width': '100%',
                            'padding': '8px',
                            'border': '1px solid #ccc',
                            'borderRadius': '4px'
                        }
                    ),
                    dcc.Input(
                        id='login-password', type='password', placeholder='Password',
                        style={
                            'marginBottom': '10px',
                            'width': '100%',
                            'padding': '8px',
                            'border': '1px solid #ccc',
                            'borderRadius': '4px'
                        },
                        n_submit=0
                    ),
                    html.Button(
                        'Login',
                        id='login-button',
                        style={
                            'width': '100%',
                            'padding': '10px',
                            'backgroundColor': '#007BFF',
                            'color': '#fff',
                            'border': 'none',
                            'borderRadius': '4px',
                            'fontWeight': 'bold',
                            'cursor': 'pointer'
                        }
                    ),

                    # Feedback message
                    html.Div(
                        id='login-message',
                        style={'color': 'red', 'marginTop': '10px', 'minHeight': '20px'}
                    )
                ]
            )
        ]
    ),

    # --- MAIN SECTION (hidden until login) ---
    html.Div(
        id='main-section',
        style={'display': 'none', 'opacity': '0', 'transition': 'opacity 0.8s'},
        children=[

            # Greeting + Logout
            html.Div(
                style={
                    'display': 'flex',
                    'justifyContent': 'space-between',
                    'alignItems': 'center',
                    'padding': '20px',
                    'backgroundColor': HEADER_BG_COLOR
                },
                children=[
                    html.H3(id='greeting', style={'color': HEADER_TEXT_COLOR, 'margin': '0'}),
                    html.Button(
                        "Logout",
                        id="logout-button",
                        style={
                            'backgroundColor': '#dc3545',
                            'color': '#fff',
                            'border': 'none',
                            'padding': '8px 16px',
                            'borderRadius': '4px',
                            'cursor': 'pointer'
                        }
                    )
                ]
            ),

            # file-browser UI!
            files_layout
        ]
    )
])

# ── 4b) "Select All / Clear All" for the category dropdown ──
@app.callback(
    Output("box-dropdown", "value"),
    Input("select-all", "n_clicks"),
    Input("clear-all",  "n_clicks"),
    State("box-dropdown", "options"),
    prevent_initial_call=True,
)
def select_clear_all(n_select, n_clear, options):
    triggered = ctx.triggered_id
    all_vals = [opt["value"] for opt in options]
    if triggered == "select-all":
        return all_vals
    elif triggered == "clear-all":
        return []
    return dash.no_update


# ── 4c) "Select All / Clear All" for the product dropdown ──
@app.callback(
    Output("product-dropdown", "value"),
    Input("select-all-products", "n_clicks"),
    Input("clear-all-products",  "n_clicks"),
    State("product-dropdown", "options"),
    prevent_initial_call=True,
)
def select_clear_all_products(n_select, n_clear, options):
    triggered = ctx.triggered_id
    all_vals = [opt["value"] for opt in options]
    if triggered == "select-all-products":
        return all_vals
    elif triggered == "clear-all-products":
        return []
    return dash.no_update



############################
# 5) SEARCH / TABLE CALLBACKS
############################

@app.callback(
    [Output("title-search-input","value"), Output("title-search-btn","n_clicks")],
    Input("clear-title-search","n_clicks"),
    State("title-search-btn","n_clicks"),
    prevent_initial_call=True,
)
def clear_title_and_search(n_clear, n_search):
    return "", (n_search or 0) + 1

@app.callback(
    [Output("content-search-input","value"), Output("content-search-btn","n_clicks")],
    Input("clear-content-search","n_clicks"),
    State("content-search-btn","n_clicks"),
    prevent_initial_call=True,
)
def clear_content_and_search(n_clear, n_search):
    return "", (n_search or 0) + 1

@app.callback(
    [Output("date-range-picker", "start_date"),
     Output("date-range-picker", "end_date")],
    Input("clear-dates-btn", "n_clicks"),
    prevent_initial_call=True
)
def clear_date_range(n_clicks):
    """Clear date range filter."""
    return None, None

@app.callback(
    [
        Output("files-table", "columns"),
        Output("files-table", "data"),
        Output("article-counter", "children"),
        Output("progress-container", "style"),
        Output("progress-text", "children"),
        Output("progress-bar", "style"),
        Output("progress-bar", "children"),
    ],
    [
        Input("product-dropdown",     "value"),
        Input("select-all-products",  "n_clicks"),
        Input("clear-all-products",   "n_clicks"),
        Input("box-dropdown",         "value"),
        Input("select-all",           "n_clicks"),
        Input("clear-all",            "n_clicks"),
        Input("title-search-btn",     "n_clicks"),
        Input("title-search-input",   "n_submit"),
        Input("content-search-btn",   "n_clicks"),
        Input("content-search-input", "n_submit"),
        Input("date-range-picker",    "start_date"),
        Input("date-range-picker",    "end_date"),
        Input("clear-dates-btn",      "n_clicks"),
        Input("login-user",           "data"),
    ],
    [
        State("product-dropdown",     "options"),
        State("box-dropdown",         "options"),
        State("title-search-input",   "value"),
        State("content-search-input", "value"),
    ],
    prevent_initial_call=False,
)
def update_file_table(
    sel_products, n_select_prod, n_clear_prod,
    sel, n_select, n_clear,
    _tbtn, _tenter,
    _cbtn, _center,
    start_date, end_date, _clear_dates,
    login_user,
    product_options, options, title_value, content_value
):
    # Return empty data if not logged in (main-section is hidden anyway)
    if not login_user:
        cols = [
            {"id": "firm", "name": "Firm", "type": "text"},
            {"id": "frequency", "name": "Frequency", "type": "text"},
            {"id": "date", "name": "Date", "type": "datetime"},
            {"id": "title", "name": "Title", "type": "text"},
            {"id": "product_categories", "name": "Categories", "type": "text"},
            {"id": "view", "name": "View", "presentation": "markdown"},
            {"id": "summary", "name": "Summary", "presentation": "markdown"},
            {"id": "summary_score", "name": "Score", "type": "numeric"},
            {"id": "chart_score", "name": "Charts", "type": "numeric"},
        ]
        return cols, [], "", {"visibility": "hidden"}, "", {"width": "0%"}, "0%"
    
    # path to "Small Caps" folder
    SC = r"C:\Users\H&CDanHughes\Documents\SC_files"

    # 1) Handle Select/Clear All for both products and categories
    triggered = ctx.triggered_id
    if triggered == "select-all-products":
        sel_products = [opt["value"] for opt in product_options]
    elif triggered == "clear-all-products":
        sel_products = []
    elif triggered == "select-all":
        sel = [opt["value"] for opt in options]
    elif triggered == "clear-all":
        sel = []

    selected_products = set(sel_products or [])
    selected = set(sel or [])
    tt = (title_value or "").strip().lower()
    ct = (content_value or "").strip().lower()
    
    # Check if all products are selected (if so, skip product filtering)
    # Handle case where product_options might not be initialized yet
    if product_options:
        total_products = len(product_options)
        all_products_selected = len(selected_products) >= total_products
    else:
        # Fallback: if no options yet, assume all selected (show everything)
        all_products_selected = True

    # 2) Build columns (dynamically - reordered: Firm, Frequency, Date, Title, Categories, View, Summary, Score, Charts)
    cols = [
        {"id": "firm",             "name": "Firm",       "type": "text"},
        {"id": "frequency",        "name": "Frequency",  "type": "text"},
        {"id": "date",             "name": "Date",       "type": "datetime"},
        {"id": "title",            "name": "Title",      "type": "text"},
        {"id": "product_categories", "name": "Categories", "type": "text"},
        {"id": "view",             "name": "View",       "presentation": "markdown"},
        {"id": "summary",          "name": "Summary",    "presentation": "markdown"},
        {"id": "summary_score",    "name": "Score",      "type": "numeric"},
        {"id": "chart_score",      "name": "Charts",     "type": "numeric"},
    ]
    if login_user == "iwill":
        cols.insert(4, {"id": "subject",  "name": "Subject",  "type": "text"})
        cols.append({"id": "download","name": "Download","presentation": "markdown"})

    # 3) Scan directories and collect candidate files
    candidate_files = []
    scan = [(FILES_DIR, "General")]
    if login_user == "iwill":
        scan.append((SC, "Small Caps"))

    for dpath, subj in scan:
        if not os.path.isdir(dpath):
            continue

        for fname in sorted(os.listdir(dpath)):
            # only PDFs
            if not fname.lower().endswith(".pdf") or fname == "README.txt":
                continue

            # now `fname` is bound—detect its category:
            category = detect_category(fname)

            # apply multi-select filter
            if selected and "All" not in selected and category not in selected:
                continue

            # parse Title / Date / Frequency
            core, _ = os.path.splitext(fname)
            parts = core.split("_")
            if len(parts) >= 4:
                _, *tp, date_part, fcode = parts
                title_str = " ".join(tp).replace("_", " ")
            elif len(parts) == 3:
                _, title_str, date_part = parts
                title_str = title_str.replace("_", " ")
                fcode = "u"
            else:
                title_str = "_".join(parts[1:])
                date_part = ""
                fcode = "u"

            # apply product filter (only if NOT all products are selected)
            # If all products selected, show everything (including files with no products)
            if not all_products_selected:
                file_products = detect_products(fname)
                # File must contain at least one selected product, OR have no products (show all unlabeled)
                if file_products and not any(prod in selected_products for prod in file_products):
                    continue

            # extract date + flag if it's today
            try:
                dt = datetime.datetime.strptime(date_part, "%Y%m%d")
                date_fmt = dt.strftime("%Y-%m-%d")
                is_today = (dt.date() == datetime.date.today())
                
                # Apply date range filter (uses already-parsed dt object)
                if start_date and dt.date() < datetime.datetime.fromisoformat(start_date).date():
                    continue  # Skip files before start_date
                if end_date and dt.date() > datetime.datetime.fromisoformat(end_date).date():
                    continue  # Skip files after end_date
                    
            except:
                date_fmt = "Unknown"
                is_today = False
                
                # Skip files with unparseable dates if date filter is active
                if start_date or end_date:
                    continue

            # map frequency
            fmap = {"y":"Yearly","q":"Quarterly","m":"Monthly","w":"Weekly","u":""}
            frequency = fmap.get(fcode.lower(), "unknown")

            # title search filter
            if tt and tt not in title_str.lower():
                continue
            
            # Collect file info for batch PDF search
            full_path = os.path.join(dpath, fname)
            
            # Check for summary (do this ONCE during candidate building, not later)
            has_sum, pdf_filename, json_filename = has_summary_file(full_path)
            
            # Prefer PDF summary, fallback to JSON (which can be converted to PDF)
            summary_filename = pdf_filename if pdf_filename else json_filename
            
            # Load product categories and scores from summary JSON if available
            product_categories = {}
            summary_score = None
            chart_score = None
            if json_filename:
                json_path = os.path.join(dpath, json_filename)
                product_categories = load_product_categories_from_summary(json_path)
                summary_score, chart_score = load_summary_score(json_path)
            elif pdf_filename:
                # If only PDF exists, try to load from corresponding JSON
                json_path = os.path.join(dpath, json_filename)  # This will be empty, so skip
                # We can't load score from PDF easily, so leave it None
            
            candidate_files.append({
                'path': full_path,
                'fname': fname,
                'category': category,
                'title_str': title_str,
                'date_fmt': date_fmt,
                'is_today': is_today,
                'frequency': frequency,
                'subj': subj,
                'has_summary': has_sum,
                'summary_pdf_filename': pdf_filename,      # PDF summary (preferred)
                'summary_json_filename': json_filename,    # JSON summary (source)
                'summary_filename': summary_filename,      # Which one to link to (PDF preferred)
                'product_categories': product_categories,
                'summary_score': summary_score,           # Score for color coding (0-10)
                'chart_score': chart_score                # Chart score (0-3)
            })

    # Batch process PDF content search if needed
    if ct and candidate_files:
        # Show progress bar with file count
        total_files = len(candidate_files)
        progress_style = {"visibility": "visible", "marginBottom": "10px"}
        progress_text = f"Searching PDF content in {total_files} file{'s' if total_files != 1 else ''}..."
        progress_bar_style = {"width": "0%", "transition": "width 0.3s ease", "backgroundColor": "#007bff"}
        progress_bar_text = "Starting..."
        
        # Process PDFs in batch
        pdf_paths = [f['path'] for f in candidate_files]
        pdf_results = pdf_contains_batch(pdf_paths, ct)
        
        # Update progress to 100% after completion
        matches_found = sum(1 for v in pdf_results.values() if v)
        progress_bar_style = {"width": "100%", "transition": "width 0.3s ease", "backgroundColor": "#28a745"}
        progress_bar_text = "100%"
        progress_text = f"Search complete! Found {matches_found} matching file{'s' if matches_found != 1 else ''} out of {total_files}"
    else:
        pdf_results = {}
        progress_style = {"visibility": "hidden", "marginBottom": "10px"}
        progress_text = ""
        progress_bar_style = {"width": "0%", "transition": "width 0.3s ease"}
        progress_bar_text = "0%"

    # Build rows from filtered candidates
    rows = []
    for file_info in candidate_files:
        # Skip if PDF content search failed
        if ct and not pdf_results.get(file_info['path'], False):
            continue
        
        # build the single row (with is_today flag)
        safe = urllib.parse.quote(file_info['fname'])
        view_md = f"[View](/view?file={safe})"
        
        # Summary link - link to PDF summary (__sum.pdf)
        summary_score = file_info.get('summary_score')  # 0-10 or None
        chart_score = file_info.get('chart_score')      # 0-3 or None
        
        if file_info['has_summary']:
            # Prefer PDF summary
            if file_info.get('summary_pdf_filename'):
                safe_sum = urllib.parse.quote(file_info['summary_pdf_filename'])
                summary_md = f"[📄 View](/view?file={safe_sum})"
            elif file_info.get('summary_json_filename'):
                # Only JSON exists - link to JSON (but this shouldn't happen with new autorun)
                safe_sum = urllib.parse.quote(file_info['summary_json_filename'])
                summary_md = f"[📋 JSON](/view?file={safe_sum})"
            else:
                summary_md = "—"
        else:
            summary_md = "—"
        
        # Format product categories for display (compact ticker format)
        product_categories_str = format_product_categories(file_info.get('product_categories', {}))
        
        row = {
            "firm":              file_info['category'],
            "frequency":         file_info['frequency'],
            "date":              file_info['date_fmt'],
            "title":             file_info['title_str'],
            "product_categories": product_categories_str,
            "view":              view_md,
            "summary":           summary_md,
            "summary_score":     summary_score if summary_score is not None else "",  # Empty if no summary
            "chart_score":       chart_score if chart_score is not None else "",      # Empty if no summary
            "is_today":          file_info['is_today']
        }
        if login_user == "iwill":
            row["subject"]  = file_info['subj']
            row["download"] = f"[Download](/download?file={safe})"

        rows.append(row)

    # Sort rows by date (most recent first), ignoring "Unknown"
    def sort_key(r):
        try:
            return datetime.datetime.strptime(r["date"], "%Y-%m-%d")
        except:
            return datetime.datetime.min  # "Unknown" dates go last

    rows.sort(key=sort_key, reverse=True)

    # Calculate article counts for counter
    total_shown = len(rows)
    total_candidates = len(candidate_files)
    
    # Determine if any filters are active
    all_categories_selected = len(selected) >= len(options) if options else True
    filters_active = (
        ct or tt or 
        (start_date or end_date) or 
        (not all_categories_selected) or
        (not all_products_selected)
    )
    
    # Build counter text
    if filters_active:
        counter_text = f"📊 Showing {total_shown} article{'s' if total_shown != 1 else ''} (filtered from {total_candidates} candidates)"
    else:
        counter_text = f"📊 Showing {total_shown} article{'s' if total_shown != 1 else ''}"

    # Return progress info (already set above if PDF search was performed)
    if not ct or not candidate_files:
        progress_style = {"visibility": "hidden", "marginBottom": "10px"}
        progress_text = ""
        progress_bar_style = {"width": "0%", "transition": "width 0.3s ease"}
        progress_bar_text = "0%"
    
    return cols, rows, counter_text, progress_style, progress_text, progress_bar_style, progress_bar_text


############################
# 6) LOGIN / LOGOUT CALLBACK
############################

@app.callback(
    Output('login-message','children'),
    Output('main-section','style'),
    Output('login-section','style'),
    Output('greeting','children'),
    Output('login-status','data'),
    Output('login-user','data'),         
    Input('login-button','n_clicks'),
    Input('login-password','n_submit'),
    Input('logout-button','n_clicks'),
    State('login-username','value'),
    State('login-password','value'),
    State('login-status','data'),
    prevent_initial_call=True
)

def handle_login_logout(login_clicks, pw_enter, logout_clicks,
                        username, password, login_status):
    """Handle login and logout actions."""
    triggered = ctx.triggered_id

    # Logout
    if triggered == "logout-button":
        return (
            "",
            {'display':'none','opacity':'0'},
            {'display':'flex','flexDirection':'column','alignItems':'center',
             'justifyContent':'center','height':'100vh'},
            "",
            False,
            ""
        )

    # Validate
    success = username in CREDENTIALS and password == CREDENTIALS[username]['password']
    greeting = CREDENTIALS.get(username,{}).get('greeting',"") if success else ""

    # Log attempt
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip = request.remote_addr if request else "unknown"
    status = "SUCCESS" if success else "FAIL"
    try:
        with open(LOG_FILE,'a') as f:
            f.write(f"{now} | IP: {ip} | user={username} | {status}\n")
    except Exception:
        pass

    if success:
        return (
            "",
            {'display':'block','opacity':'1','transition':'opacity 0.8s'},
            {'display':'none'},
            greeting,
            True,
            username
        )
    else:
        return (
            "Invalid credentials.",
            {'display':'none','opacity':'0'},
            {'display':'flex','flexDirection':'column','alignItems':'center',
             'justifyContent':'center','height':'100vh'},
            "",
            False,
            ""
        )


############################
# 7) CLIENTSIDE SCROLL
############################

app.clientside_callback(
    """
    function(loginSuccess) {
        if (loginSuccess) {
            document
              .getElementById('main-section')
              .scrollIntoView({ behavior: 'smooth' });
        }
        return '';
    }
    """,
    Output('dummy-output', 'children'),
    Input('login-status', 'data')
)


############################
# 8) FILE VIEW / DOWNLOAD
############################

@server.route("/view")
def view_file():
    f = request.args.get("file")
    if not f:
        return "No file specified.", 400

    # Check both directories
    dirs_to_check = [
        FILES_DIR,
        r"C:\Users\H&CDanHughes\Documents\SC_files"
    ]

    for directory in dirs_to_check:
        full_path = os.path.join(directory, f)
        if os.path.isfile(full_path):
            return send_from_directory(directory, f)

    return "File not found.", 404


@server.route("/download")
def download_file():
    f = request.args.get("file")
    if not f:
        return "No file specified.", 400

    # Check both directories
    dirs_to_check = [
        FILES_DIR,
        r"C:\Users\H&CDanHughes\Documents\SC_files"
    ]

    for directory in dirs_to_check:
        full_path = os.path.join(directory, f)
        if os.path.isfile(full_path):
            return send_from_directory(directory, f, as_attachment=True)

    return "File not found.", 404


############################
# 9) RUN
############################

if __name__ == "__main__":
    app.run(debug=True, port=8065, host='127.0.0.1')

