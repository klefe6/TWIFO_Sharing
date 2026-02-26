import os
import re
import datetime
import json
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from typing import Optional, List, Dict

# Import economic calendar modules
try:
    from econ_calendar_parser import parse_week_block
    from econ_calendar_store import upsert_week_and_events, get_weeks_in_range, get_week_raw_text, get_events_for_date, get_daily_brief, delete_week
    from econ_calendar_db import DB_PATH
    from econ_calendar_analysis import generate_event_analysis, compute_context_hash
    from econ_calendar_ai import generate_for_week
    ECON_CALENDAR_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Economic calendar modules not available: {e}")
    ECON_CALENDAR_AVAILABLE = False
    parse_week_block = None
    upsert_week_and_events = None
    get_weeks_in_range = None
    get_week_raw_text = None
    get_events_for_date = None
    generate_event_analysis = None
    compute_context_hash = None
    generate_for_week = None
    get_daily_brief = None
    delete_week = None
    DB_PATH = None

# Import path manager for new file layout
try:
    from path_manager import TWIFOPathManager, get_path_manager
    PATH_MANAGER_AVAILABLE = True
except ImportError:
    PATH_MANAGER_AVAILABLE = False
    TWIFOPathManager = None
    get_path_manager = None

# Import summary view renderer
try:
    from summary_view import load_summary_json, is_stub_summary, render_failed_summary, render_summary_view
    SUMMARY_VIEW_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Summary view not available: {e}")
    SUMMARY_VIEW_AVAILABLE = False
    load_summary_json = None
    is_stub_summary = None
    render_failed_summary = None
    render_summary_view = None

# Import daily view helper
try:
    from twifo_app import get_yesterday_artifacts, get_artifacts_for_date, resolve_display_title
    DAILY_VIEW_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Daily view helper not available: {e}")
    DAILY_VIEW_AVAILABLE = False
    get_yesterday_artifacts = None
    get_artifacts_for_date = None
    resolve_display_title = None

# compute today's ISO date once:
TODAY = datetime.date.today().isoformat()  # e.g. "2025-05-21"

import urllib.parse

import dash
from dash import dcc, html, dash_table, Input, Output, State, ctx
from dash.exceptions import PreventUpdate
from flask import request, send_from_directory, jsonify, session as flask_session
from PyPDF2 import PdfReader  # for in-PDF keyword search (beta)

# ── new prefix map & detector ──
PREFIX_MAP = {
    "BOA_":   "Bank of America",
    "BA_":    "Barclays",
    "BR_":    "BlackRock",
    "DB_":    "Deutsche Bank",
    "GM_":    "Goldman Sachs",
    "GS_":    "Goldman Sachs",  # Alternative prefix for Goldman Sachs
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
    "O_":     "Others",
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


def parse_pdf_filename(fname: str) -> dict:
    """
    Parse PDF filename in both old and new formats.
    
    Old format: PREFIX_title_YYYYMMDD_f.pdf
        Example: BOA_Market_Update_20260212_w.pdf
    
    New format: YYYYMMDD__PROVIDER__title_slug__docid.pdf
        Example: 20260212__BOA__market-update__abc123.pdf
    
    Returns:
        dict with keys: provider, title_str, date_fmt, frequency, horizon_code, basename
    """
    basename = os.path.splitext(fname)[0]
    
    # Detect format by checking for double underscores (new format)
    if '__' in fname:
        # New deterministic format: YYYYMMDD__PROVIDER__title_slug__docid.pdf
        parts = basename.split('__')
        
        if len(parts) >= 3:
            date_part = parts[0]  # First 8 digits
            provider_code = parts[1]  # PROVIDER between first and second __
            title_slug = parts[2] if len(parts) > 2 else ""  # Title slug
            
            # Map provider code to full name
            provider = PREFIX_MAP.get(f"{provider_code}_", provider_code)
            
            # Convert title_slug to human-readable (replace hyphens/underscores with spaces)
            title_str = title_slug.replace('-', ' ').replace('_', ' ').strip()
            
            # No frequency in new format, default to 'u' (unknown/unspecified)
            horizon_code = 'u'
            frequency = ''
            
            # Parse date
            dt = None
            try:
                dt = datetime.datetime.strptime(date_part, "%Y%m%d")
            except ValueError:
                try:
                    dt = datetime.datetime.strptime(date_part, "%Y-%m-%d")
                except ValueError:
                    try:
                        dt = datetime.datetime.strptime(date_part, "%Y_%m_%d")
                    except ValueError:
                        pass
            
            if dt:
                date_fmt = dt.strftime("%Y-%m-%d")
                is_today = (dt.date() == datetime.date.today())
            else:
                date_fmt = "Unknown"
                is_today = False
            
            return {
                'provider': provider,
                'title_str': title_str,
                'date_fmt': date_fmt,
                'frequency': frequency,
                'horizon_code': horizon_code,
                'basename': basename,
                'is_today': is_today
            }
    
    # Old format: PREFIX_title_YYYYMMDD_f.pdf
    parts = basename.split("_")
    
    if len(parts) >= 4:
        # PREFIX_title_words_YYYYMMDD_f
        prefix = parts[0]
        *title_parts, date_part, fcode = parts[1:]
        title_str = " ".join(title_parts)
    elif len(parts) == 3:
        # PREFIX_title_YYYYMMDD
        prefix = parts[0]
        title_str = parts[1]
        date_part = parts[2]
        fcode = "u"
    else:
        # Fallback for malformed filenames
        prefix = parts[0] if len(parts) > 0 else ""
        title_str = "_".join(parts[1:]) if len(parts) > 1 else fname
        date_part = ""
        fcode = "u"
    
    # Detect provider from prefix
    provider = PREFIX_MAP.get(f"{prefix}_", "Others")
    
    # Parse date
    dt = None
    try:
        dt = datetime.datetime.strptime(date_part, "%Y%m%d")
    except ValueError:
        try:
            dt = datetime.datetime.strptime(date_part, "%Y-%m-%d")
        except ValueError:
            try:
                dt = datetime.datetime.strptime(date_part, "%Y_%m_%d")
            except ValueError:
                pass
    
    if dt:
        date_fmt = dt.strftime("%Y-%m-%d")
        is_today = (dt.date() == datetime.date.today())
    else:
        date_fmt = "Unknown"
        is_today = False
    
    # Map frequency
    fmap = {"y": "Yearly", "q": "Quarterly", "m": "Monthly", "w": "Weekly", "u": ""}
    frequency = fmap.get(fcode.lower(), "unknown")
    
    return {
        'provider': provider,
        'title_str': title_str,
        'date_fmt': date_fmt,
        'frequency': frequency,
        'horizon_code': fcode.lower(),
        'basename': basename,
        'is_today': is_today
    }


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
ORIGINALS_ROOT = Path(FILES_DIR) / "originals"  # Shared originals folder for all PDFs

# Initialize path manager for new file layout
if PATH_MANAGER_AVAILABLE:
    PATH_MANAGER = get_path_manager(Path(FILES_DIR))
    print(f"[INIT] Path manager initialized")
    print(f"  Originals: {PATH_MANAGER.originals_dir}")
    print(f"  Artifacts: {PATH_MANAGER.artifacts_dir}")
else:
    PATH_MANAGER = None
    print("[WARN] Path manager not available - using legacy layout")

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
# Tab styles
TAB_STYLE = {
    'padding': '12px 24px',
    'fontWeight': 'bold',
    'borderBottom': '2px solid #ddd',
    'backgroundColor': '#f8f9fa',
    'color': '#495057'
}

SELECTED_TAB_STYLE = {
    'padding': '12px 24px',
    'fontWeight': 'bold',
    'borderBottom': '3px solid #007BFF',
    'backgroundColor': '#ffffff',
    'color': '#007BFF'
}
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

    # Scan both new layout (originals/) and legacy layout (root) using helper
    try:
        all_pdfs = iter_all_candidate_pdfs(FILES_DIR)
        for fname, full_path, layout_type in all_pdfs:
            # Parse filename to get provider
            parsed = parse_pdf_filename(fname)
            provider = parsed['provider'] if parsed['provider'] else "Others"
            
            # Increment count for this provider
            if provider in counts:
                counts[provider] += 1
            else:
                # New provider not in PREFIX_MAP - add to Others
                counts["Others"] += 1
    except Exception as e:
        # If directory scan fails, return empty counts but still show categories
        print(f"Warning: Could not scan for categories: {e}")

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
    
    Checks both new layout (artifacts/<basename>/) and legacy layout (root).
    Handles both old and new filename formats:
    - Old: PREFIX_title_YYYYMMDD_f.pdf -> artifacts/PREFIX_title_YYYYMMDD_f/sum.json
    - New: YYYYMMDD__PROVIDER__title__docid.pdf -> artifacts/YYYYMMDD__PROVIDER__title__docid/sum.json
    """
    if not filepath.endswith('.pdf'):
        return False, "", ""
    
    # Get basename from filepath
    fname = os.path.basename(filepath)
    base_name = os.path.splitext(fname)[0]
    dir_path = os.path.dirname(filepath)
    
    # Try new layout first if path manager available
    if PATH_MANAGER_AVAILABLE and PATH_MANAGER:
        # Pattern A: Try exact basename match first (handles both old and new formats)
        has_pdf, has_json, has_txt = PATH_MANAGER.has_summary(base_name)
        
        if has_pdf or has_json:
            # Return relative paths for URL generation
            # Format: artifacts/<basename>/sum.pdf
            pdf_filename = f"artifacts/{base_name}/sum.pdf" if has_pdf else ""
            json_filename = f"artifacts/{base_name}/sum.json" if has_json else ""
            return True, pdf_filename, json_filename
        
        # Pattern B: For new format files, also try old-style prefix basename
        # (safety fallback if artifacts used old naming before migration)
        if '__' in base_name:
            # Parse new format to construct old-style basename
            parsed = parse_pdf_filename(fname)
            # Try constructing old-style name: PROVIDER_title_YYYYMMDD_f
            # (This is unlikely but kept for safety during transition)
            pass  # Skip this pattern - artifacts should use deterministic basename
    
    # Fallback to legacy layout (Pattern B: root directory)
    # Check for __sum.pdf (preferred format)
    summary_pdf = os.path.join(dir_path, f"{base_name}__sum.pdf")
    pdf_filename = f"{base_name}__sum.pdf" if os.path.isfile(summary_pdf) else ""
    
    # Check for __sum.json (source for PDF generation)
    summary_json_new = os.path.join(dir_path, f"{base_name}__sum.json")
    json_filename = f"{base_name}__sum.json" if os.path.isfile(summary_json_new) else ""
    
    # Check for legacy .summary.json
    summary_json_legacy = os.path.join(dir_path, f"{base_name}.summary.json")
    if not json_filename and os.path.isfile(summary_json_legacy):
        json_filename = os.path.basename(summary_json_legacy)
    
    has_pdf = bool(pdf_filename)
    has_json = bool(json_filename)
    
    # Return True if we have either PDF or JSON (JSON can be converted to PDF)
    if has_pdf or has_json:
        return True, pdf_filename, json_filename
    
    return False, "", ""


def iter_all_candidate_pdfs(directory: str) -> list[tuple[str, str, str]]:
    """
    Discover all candidate PDFs from both new and legacy layouts.
    
    Returns list of tuples: (filename, full_path, layout_type)
    - Deduplicates by basename (file without extension)
    - Prioritizes new layout (originals/) over legacy (root FILES_DIR)
    - Excludes subdirectories in legacy scan
    - Excludes README.txt
    
    Args:
        directory: Root directory to scan (typically FILES_DIR)
    
    Returns:
        List of (filename, full_path, layout_type) tuples where layout_type is 'new' or 'legacy'
    """
    all_pdfs = []
    seen_basenames = set()
    
    # 1. Scan new layout: originals/ (via PATH_MANAGER)
    if PATH_MANAGER_AVAILABLE and PATH_MANAGER and directory == FILES_DIR:
        try:
            originals = PATH_MANAGER.list_originals()
            for fname in originals:
                if fname.lower().endswith(".pdf") and fname != "README.txt":
                    basename = os.path.splitext(fname)[0]
                    if basename not in seen_basenames:
                        full_path = str(PATH_MANAGER.original_pdf_path(fname))
                        all_pdfs.append((fname, full_path, 'new'))
                        seen_basenames.add(basename)
        except Exception as e:
            print(f"[WARN] Could not scan originals/: {e}")
    
    # 2. Scan legacy layout: root directory (FILES_DIR only, no subdirectories)
    try:
        for item in os.listdir(directory):
            # Only process files directly in root (skip subdirectories like originals/, artifacts/, rollups/)
            full_item_path = os.path.join(directory, item)
            if os.path.isdir(full_item_path):
                continue
            
            # Only PDFs, exclude README.txt
            if item.lower().endswith(".pdf") and item != "README.txt":
                basename = os.path.splitext(item)[0]
                if basename not in seen_basenames:
                    all_pdfs.append((item, full_item_path, 'legacy'))
                    seen_basenames.add(basename)
    except Exception as e:
        print(f"[WARN] Could not scan legacy files in {directory}: {e}")
    
    return sorted(all_pdfs)


def discover_from_artifacts(
    artifacts_dir: Path,
    files_dir: str,
    seen_basenames: set,
    selected: list,
    start_date: str,
    end_date: str,
    tt: str
) -> list:
    """
    Fallback discovery: scan artifacts/*/sum.json and build table rows from metadata.
    
    This ensures the app works even when:
    - Original PDFs are missing
    - Naming conventions don't match cleanly
    - PDFs haven't been copied to originals/ yet
    
    Args:
        artifacts_dir: Path to artifacts/ directory
        files_dir: Root FILES_DIR for path resolution
        seen_basenames: Set of basenames already discovered (to avoid duplicates)
        selected: Category filter
        start_date: Date range start (ISO format)
        end_date: Date range end (ISO format)
        tt: Title search term
    
    Returns:
        List of candidate file dicts (same structure as PDF-based discovery)
    """
    candidates = []
    
    if not artifacts_dir.exists():
        return candidates
    
    try:
        for artifact_dir in artifacts_dir.iterdir():
            if not artifact_dir.is_dir():
                continue
            
            basename = artifact_dir.name
            
            # Skip if already discovered via PDF
            if basename in seen_basenames:
                continue
            
            # Look for sum.json
            sum_json_path = artifact_dir / "sum.json"
            if not sum_json_path.exists():
                continue
            
            # Load metadata from sum.json
            try:
                with open(sum_json_path, 'r', encoding='utf-8') as f:
                    sum_data = json.load(f)
            except Exception as e:
                print(f"[WARN] Could not parse {sum_json_path}: {e}")
                continue
            
            # Extract metadata
            meta = sum_data.get("meta", {})
            provider = meta.get("provider", "Unknown")
            title = meta.get("title", basename)
            published_date = meta.get("published_date", "")
            horizon = meta.get("horizon", "u")
            products = meta.get("products", [])
            
            # Map provider to category
            category = detect_category(f"{provider}_dummy.pdf")
            
            # Apply category filter
            if selected and "All" not in selected and category not in selected:
                continue
            
            # Parse date
            date_fmt = "Unknown"
            is_today = False
            dt = None
            
            if published_date:
                try:
                    dt = datetime.datetime.strptime(published_date, "%Y%m%d")
                    date_fmt = dt.strftime("%Y-%m-%d")
                    is_today = (dt.date() == datetime.date.today())
                except:
                    pass
            
            # Apply date range filter
            if dt:
                if start_date and dt.date() < datetime.datetime.fromisoformat(start_date).date():
                    continue
                if end_date and dt.date() > datetime.datetime.fromisoformat(end_date).date():
                    continue
            elif start_date or end_date:
                # Skip if date filter active but date unparseable
                continue
            
            # Map horizon to frequency
            horizon_map = {"d": "Daily", "w": "Weekly", "m": "Monthly", "q": "Quarterly", "y": "Yearly", "u": ""}
            frequency = horizon_map.get(horizon.lower(), "")
            
            # Apply title search filter
            if tt and tt not in title.lower():
                continue
            
            # Build product categories
            product_categories = {}
            for product in products:
                # Simple grouping (could be enhanced)
                if product in ["GC", "SI", "HG", "PL"]:
                    product_categories.setdefault("Metals", []).append(product)
                elif product in ["CL", "NG", "RB", "HO"]:
                    product_categories.setdefault("Energy", []).append(product)
                elif product in ["ZC", "ZS", "ZW", "ZL"]:
                    product_categories.setdefault("Ags", []).append(product)
                else:
                    product_categories.setdefault("Other", []).append(product)
            
            # Extract scores and extraction status
            extraction = sum_data.get("extraction", {})
            extraction_status = extraction.get("status", "unknown")
            extraction_quality = extraction.get("extraction_quality_0_100", None)
            is_low_confidence = extraction.get("is_low_confidence", False)
            
            # Attempt to compute scores from sections
            sections = sum_data.get("sections", {})
            tldr = sections.get("tldr", [])
            trade_ideas = sections.get("trade_ideas", [])
            
            # Simple score heuristic based on content richness
            summary_score = None
            if extraction_status == "ok" and tldr:
                base_score = 5
                if len(tldr) >= 3:
                    base_score += 2
                if len(trade_ideas) > 0:
                    base_score += 2
                if product_categories:
                    base_score += 1
                summary_score = min(10, base_score)
            
            # Chart score (assume 0 if no extraction)
            chart_score = 0
            
            # Build fake filename for consistency
            fake_fname = f"{basename}.pdf"
            fake_path = str(artifact_dir.parent.parent / "originals" / fake_fname)  # Won't exist, but needed for structure
            
            # Summary filenames (artifacts layout)
            pdf_filename = f"artifacts/{basename}/sum.pdf"
            json_filename = f"artifacts/{basename}/sum.json"
            
            # Check if sum.pdf exists
            has_sum_pdf = (artifact_dir / "sum.pdf").exists()
            summary_filename = pdf_filename if has_sum_pdf else json_filename
            
            candidates.append({
                'path': fake_path,  # Fake path (original PDF may not exist)
                'fname': fake_fname,
                'category': category,
                'summary_type': 'article',
                'title_str': title,
                'date_fmt': date_fmt,
                'is_today': is_today,
                'frequency': frequency,
                'timeframe': horizon,
                'subj': "General",
                'has_summary': True,  # We know it has a summary (we found sum.json)
                'summary_pdf_filename': pdf_filename if has_sum_pdf else "",
                'summary_json_filename': json_filename,
                'summary_filename': summary_filename,
                'product_categories': product_categories,
                'summary_score': summary_score,
                'chart_score': chart_score,
                'extraction_status': extraction_status,
                'extraction_quality': extraction_quality,
                'is_low_confidence': is_low_confidence,
                '_discovered_from_artifacts': True  # Flag to indicate fallback discovery
            })
    
    except Exception as e:
        print(f"[ERROR] Fallback discovery failed: {e}")
        import traceback
        traceback.print_exc()
    
    return candidates


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
    Supports BOTH old and new (Option B) schema formats for backward compatibility.
    
    Args:
        summary_path: Path to JSON file (can be legacy path or new artifacts/ path)
    
    Returns: (summary_score, chart_score) or (None, None) if not found/invalid
    """
    try:
        # Handle both legacy and new paths
        if PATH_MANAGER_AVAILABLE and PATH_MANAGER and 'artifacts/' in summary_path:
            # New layout: artifacts/<basename>/sum.json
            parts = summary_path.split('artifacts/')
            if len(parts) > 1:
                subpath = parts[1]  # <basename>/sum.json
                basename = subpath.split('/')[0]
                json_path = PATH_MANAGER.artifact_path(basename, 'sum.json')
                if not json_path.exists():
                    return None, None
                summary_path = str(json_path)
        
        if not os.path.exists(summary_path):
            return None, None
        
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        
        summary_score = None
        chart_score = None
        
        # Try new Option B schema first (scan.score.summary_score_0_10)
        if "scan" in summary and isinstance(summary["scan"], dict):
            score = summary["scan"].get("score", {})
            if isinstance(score, dict):
                summary_score = score.get("summary_score_0_10")
                chart_score = score.get("chart_score_0_3")
        
        # Fallback to old schema (top-level summary_score_0_10) or backward compat fields
        if summary_score is None:
            summary_score = summary.get("summary_score_0_10")
        if chart_score is None:
            chart_score = summary.get("chart_score_0_3")
        
        # Validate and clamp scores
        if summary_score is not None:
            try:
                summary_score = int(summary_score)
                summary_score = max(0, min(10, summary_score))
            except (ValueError, TypeError):
                summary_score = None
        
        if chart_score is not None:
            try:
                chart_score = int(chart_score)
                chart_score = max(0, min(3, chart_score))
            except (ValueError, TypeError):
                chart_score = None
        
        return summary_score, chart_score
    except Exception:
        return None, None


def load_extraction_status(summary_path: str) -> tuple[str, Optional[int], bool]:
    """
    Load extraction status, quality, and low_confidence flag from summary JSON file.
    
    Returns: (status, quality_score, is_low_confidence) where:
        - status: "ok" | "degraded" | "failed" | "unknown"
        - quality_score: extraction_quality_0_100 (0-100) or None
        - is_low_confidence: bool flag from meta.low_confidence
    """
    try:
        # Handle both legacy and new paths (same as load_summary_score)
        if PATH_MANAGER_AVAILABLE and PATH_MANAGER and 'artifacts/' in summary_path:
            parts = summary_path.split('artifacts/')
            if len(parts) > 1:
                subpath = parts[1]
                basename = subpath.split('/')[0]
                json_path = PATH_MANAGER.artifact_path(basename, 'sum.json')
                if not json_path.exists():
                    return "unknown", None, False
                summary_path = str(json_path)
        
        if not os.path.exists(summary_path):
            return "unknown", None, False
        
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        
        # Check if summary was skipped by triage
        if summary.get("skipped", False):
            return "skipped", None, False
        
        # Check meta.extraction.status
        meta = summary.get("meta", {})
        extraction = meta.get("extraction", {})
        status = extraction.get("status", "unknown")
        quality = extraction.get("extraction_quality_0_100")
        
        # Check low_confidence flag
        is_low_confidence = meta.get("low_confidence", False)
        
        # Validate status (now includes "degraded" and "skipped")
        if status not in ["ok", "degraded", "failed", "skipped", "unknown"]:
            status = "unknown"
        
        # Validate quality
        if quality is not None:
            try:
                quality = int(quality)
                quality = max(0, min(100, quality))
            except (ValueError, TypeError):
                quality = None
        
        return status, quality, is_low_confidence
    except Exception:
        return "unknown", None, False


def load_timeframe_from_summary(json_path: str) -> Optional[str]:
    """
    Load time_horizon/timeframe from summary JSON file.
    Supports both Style B and Option B schemas.
    
    Returns: time_horizon string (e.g., "1-2w", "1-3d") or None if not found
    """
    try:
        if not os.path.exists(json_path):
            return None
        
        with open(json_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        
        # Try Style B schema (market_framing.time_horizon)
        meta = summary.get("meta", {})
        market_framing = meta.get("market_framing", {})
        if market_framing:
            time_horizon = market_framing.get("time_horizon")
            if time_horizon:
                return time_horizon
        
        # Fallback to top-level (for backward compatibility)
        time_horizon = summary.get("time_horizon")
        if time_horizon:
            return time_horizon
        
        return None
    except Exception:
        return None


def load_horizon_from_summary(json_path: str) -> str:
    """
    Load horizon code from summary JSON meta.horizon field.
    Used for new filename format where horizon is not in filename.
    
    Returns: horizon code (e.g., 'w', 'm', 'q', 'y') or 'u' if not found
    """
    try:
        if not os.path.exists(json_path):
            return 'u'
        
        with open(json_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        
        meta = summary.get("meta", {})
        horizon = meta.get("horizon", "u")
        return horizon if horizon else "u"
    except Exception:
        return 'u'


def parse_rollup_filename(fname: str) -> Optional[dict]:
    """
    Parse rollup filename to extract metadata.
    Returns dict with kind, date info, or None if not a rollup.
    New pattern: ROLLUP_DAILY_YYYYMMDD__sum.json and ROLLUP_WEEKLY_YYYYMMDD__sum.json
    """
    # Daily: ROLLUP_DAILY_YYYYMMDD__sum.json
    daily_match = re.match(r'ROLLUP_DAILY_(\d{8})__sum\.json', fname)
    if daily_match:
        date_yyyymmdd = daily_match.group(1)
        try:
            dt = datetime.datetime.strptime(date_yyyymmdd, "%Y%m%d")
            return {
                "kind": "rollup_daily",
                "date": dt.date(),
                "date_yyyymmdd": date_yyyymmdd,
            }
        except ValueError:
            return None
    
    # Weekly: ROLLUP_WEEKLY_YYYYMMDD__sum.json (Monday date)
    weekly_match = re.match(r'ROLLUP_WEEKLY_(\d{8})__sum\.json', fname)
    if weekly_match:
        monday_yyyymmdd = weekly_match.group(1)
        try:
            monday_date = datetime.datetime.strptime(monday_yyyymmdd, "%Y%m%d").date()
            friday_date = monday_date + datetime.timedelta(days=4)
            iso_year, iso_week, _ = monday_date.isocalendar()
            return {
                "kind": "rollup_weekly",
                "start_date": monday_date,
                "end_date": friday_date,
                "date": monday_date,  # For compatibility
                "date_yyyymmdd": monday_yyyymmdd,
                "iso_year": iso_year,
                "iso_week": iso_week,
            }
        except ValueError:
            return None
    
    return None

def load_rollup_json(rollup_path: Path) -> Optional[dict]:
    """Load rollup JSON file and verify schema_version."""
    # Diagnostic: Check if file exists
    if not rollup_path.exists():
        print(f"[ROLLUP DEBUG] File does not exist: {rollup_path}")
        return None
    
    # Diagnostic: Check file size
    try:
        file_size = rollup_path.stat().st_size
        if file_size == 0:
            print(f"[ROLLUP DEBUG] File is empty (0 bytes): {rollup_path}")
            return None
        print(f"[ROLLUP DEBUG] Loading: {rollup_path.name} ({file_size} bytes)")
    except Exception as e:
        print(f"[ROLLUP DEBUG] Cannot stat file {rollup_path}: {e}")
        return None
    
    try:
        with open(rollup_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # Diagnostic: Check top-level structure
            if not isinstance(data, dict):
                print(f"[ROLLUP DEBUG] File {rollup_path.name} does not contain a JSON object (found: {type(data).__name__})")
                return None
            
            # Verify it's actually a rollup by checking schema_version
            schema = data.get("schema_version", "")
            if schema == "twifo.rollup.v1":
                print(f"[ROLLUP DEBUG] [OK] Successfully loaded {rollup_path.name} (schema: {schema})")
                return data
            else:
                print(f"[ROLLUP DEBUG] [X] Schema mismatch in {rollup_path.name}")
                print(f"  Expected: 'twifo.rollup.v1'")
                print(f"  Found: '{schema}' (type: {type(schema).__name__})")
                print(f"  Top-level keys: {list(data.keys())[:10]}")
                return None
                
    except json.JSONDecodeError as e:
        print(f"[ROLLUP DEBUG] [X] JSON parse error in {rollup_path.name}")
        print(f"  Error: {e}")
        print(f"  Line {e.lineno}, Column {e.colno}: {e.msg}")
        return None
    except UnicodeDecodeError as e:
        print(f"[ROLLUP DEBUG] [X] Encoding error in {rollup_path.name}")
        print(f"  Error: {e}")
        return None
    except Exception as e:
        print(f"[ROLLUP DEBUG] [X] Unexpected error loading {rollup_path.name}")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Error message: {e}")
        import traceback
        tb_str = traceback.format_exc()
        print(f"  Traceback: {tb_str.encode('ascii', errors='replace').decode('ascii')}")
        return None

def scan_rollups() -> List[dict]:
    """
    Scan rollups directories and return list of rollup file info.
    Returns list of dicts with path, fname, metadata, etc.
    """
    rollups = []
    rollups_dir = os.path.join(FILES_DIR, "rollups")
    
    print(f"[ROLLUP SCAN] Starting scan...")
    print(f"[ROLLUP SCAN] FILES_DIR: {FILES_DIR}")
    print(f"[ROLLUP SCAN] Rollups base dir: {rollups_dir}")
    print(f"[ROLLUP SCAN] Rollups dir exists: {os.path.exists(rollups_dir)}")
    print(f"[ROLLUP SCAN] Rollups dir is directory: {os.path.isdir(rollups_dir) if os.path.exists(rollups_dir) else 'N/A'}")
    
    # Scan daily rollups
    daily_dir = os.path.join(rollups_dir, "daily")
    print(f"[ROLLUP SCAN] Daily dir: {daily_dir}")
    print(f"[ROLLUP SCAN] Daily dir exists: {os.path.exists(daily_dir)}")
    print(f"[ROLLUP SCAN] Daily dir is directory: {os.path.isdir(daily_dir) if os.path.exists(daily_dir) else 'N/A'}")
    
    if os.path.isdir(daily_dir):
        try:
            all_files = os.listdir(daily_dir)
            json_files = [f for f in all_files if f.endswith(".json")]
            rollup_files = [f for f in json_files if f.startswith("ROLLUP_DAILY")]
            
            print(f"[ROLLUP SCAN] Daily dir contents: {len(all_files)} total files")
            print(f"[ROLLUP SCAN] Daily JSON files: {len(json_files)}")
            print(f"[ROLLUP SCAN] Daily ROLLUP_DAILY files: {len(rollup_files)}")
            
            if json_files and not rollup_files:
                print(f"[ROLLUP SCAN] WARNING: Found JSON files but none start with 'ROLLUP_DAILY'")
                print(f"[ROLLUP SCAN] Sample JSON files: {json_files[:5]}")
            
            for fname in rollup_files:
                file_path = os.path.join(daily_dir, fname)
                print(f"[ROLLUP SCAN] Processing: {fname}")
                
                metadata = parse_rollup_filename(fname)
                if metadata:
                    print(f"  [OK] Parsed successfully: date={metadata.get('date')}")
                    rollups.append({
                        "path": file_path,
                        "fname": fname,
                        "kind": "rollup_daily",
                        "date": metadata["date"],
                        "date_yyyymmdd": metadata["date_yyyymmdd"],
                    })
                else:
                    print(f"  [X] Failed to parse filename (does not match expected pattern)")
                    print(f"    Expected: ROLLUP_DAILY_YYYYMMDD__sum.json")
        except Exception as e:
            print(f"[ROLLUP SCAN] ERROR scanning daily dir: {e}")
            import traceback
            tb_str = traceback.format_exc()
            # Sanitize for Windows cp1252 console (avoid UnicodeEncodeError on ✓/✗ etc.)
            print(tb_str.encode("ascii", errors="replace").decode("ascii"))
    else:
        if not os.path.exists(daily_dir):
            print(f"[ROLLUP SCAN] Daily directory does not exist: {daily_dir}")
        else:
            print(f"[ROLLUP SCAN] Daily path exists but is not a directory: {daily_dir}")
    
    # Scan weekly rollups
    weekly_dir = os.path.join(rollups_dir, "weekly")
    print(f"[ROLLUP SCAN] Weekly dir: {weekly_dir}")
    print(f"[ROLLUP SCAN] Weekly dir exists: {os.path.exists(weekly_dir)}")
    print(f"[ROLLUP SCAN] Weekly dir is directory: {os.path.isdir(weekly_dir) if os.path.exists(weekly_dir) else 'N/A'}")
    
    if os.path.isdir(weekly_dir):
        try:
            all_files = os.listdir(weekly_dir)
            json_files = [f for f in all_files if f.endswith(".json")]
            rollup_files = [f for f in json_files if f.startswith("ROLLUP_WEEKLY")]
            
            print(f"[ROLLUP SCAN] Weekly dir contents: {len(all_files)} total files")
            print(f"[ROLLUP SCAN] Weekly JSON files: {len(json_files)}")
            print(f"[ROLLUP SCAN] Weekly ROLLUP_WEEKLY files: {len(rollup_files)}")
            
            for fname in rollup_files:
                file_path = os.path.join(weekly_dir, fname)
                print(f"[ROLLUP SCAN] Processing: {fname}")
                
                metadata = parse_rollup_filename(fname)
                if metadata:
                    print(f"  [OK] Parsed successfully: {metadata.get('start_date')} to {metadata.get('end_date')}")
                    rollups.append({
                        "path": file_path,
                        "fname": fname,
                        "kind": "rollup_weekly",
                        "start_date": metadata["start_date"],
                        "end_date": metadata["end_date"],
                        "date": metadata.get("date", metadata["start_date"]),
                        "date_yyyymmdd": metadata["date_yyyymmdd"],
                        "iso_year": metadata["iso_year"],
                        "iso_week": metadata["iso_week"],
                    })
                else:
                    print(f"  [X] Failed to parse filename (does not match expected pattern)")
                    print(f"    Expected: ROLLUP_WEEKLY_YYYYMMDD__sum.json")
        except Exception as e:
            print(f"[ROLLUP SCAN] ERROR scanning weekly dir: {e}")
            import traceback
            tb_str = traceback.format_exc()
            print(tb_str.encode("ascii", errors="replace").decode("ascii"))
    else:
        if not os.path.exists(weekly_dir):
            print(f"[ROLLUP SCAN] Weekly directory does not exist: {weekly_dir}")
        else:
            print(f"[ROLLUP SCAN] Weekly path exists but is not a directory: {weekly_dir}")
    
    print(f"[ROLLUP SCAN] Scan complete: Found {len(rollups)} rollup files")
    return rollups

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


def clean_title(title_str: str, provider: str) -> str:
    """
    Clean title by removing everything before the first ' - ' and removing provider prefix and date codes.
    Also strips HTML tags and special formatting characters.
    
    Examples:
    "MUFG Asia FX Weekly - Local factors drive FX dispersion" -> "Local Factors Drive FX Dispersion"
    "BOA US Economic Weekly IEEPA D-Day FAQs" -> "US Economic Weekly IEEPA D-Day FAQs"
    """
    # Strip HTML tags and entities first
    import html
    title = html.unescape(title_str)  # Convert HTML entities to text
    title = re.sub(r'<[^>]+>', '', title)  # Remove HTML tags
    title = re.sub(r'&[a-zA-Z]+;', '', title)  # Remove any remaining HTML entities
    
    # Remove date and provider prefix pattern: -MM-DD-Provider-Title or -YYYY-MM-DD-Provider-Title
    # Pattern: starts with -, then date (MM-DD or YYYY-MM-DD), then provider, then title
    title = re.sub(r'^-\d{1,2}-\d{1,2}-', '', title)  # Remove -MM-DD- or -M-D- at start
    title = re.sub(r'^-\d{4}-\d{2}-\d{2}-', '', title)  # Remove -YYYY-MM-DD- at start
    
    # Remove everything before the first ' - '
    if ' - ' in title:
        title = title.split(' - ', 1)[1]  # Take everything after the first ' - '
    
    # Remove provider prefix (with various separators)
    provider_upper = provider.upper()
    provider_lower = provider.lower()
    
    # Try to remove provider prefix at start
    patterns = [
        f"^{re.escape(provider_upper)}\\s+",
        f"^{re.escape(provider_lower)}\\s+",
        f"^{re.escape(provider)}\\s+",
        f"^{re.escape(provider_upper)}-\\s*",
        f"^{re.escape(provider_lower)}-\\s*",
        f"^{re.escape(provider)}-\\s*",  # Handle "Deutsche Bank-" pattern
        f"^{re.escape(provider_upper)}_",
    ]
    
    for pattern in patterns:
        title = re.sub(pattern, "", title, flags=re.IGNORECASE)
    
    # Remove date patterns (YYYYMMDD, YYYY-MM-DD, etc.)
    title = re.sub(r'\b\d{8}\b', '', title)  # YYYYMMDD
    title = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '', title)  # YYYY-MM-DD
    
    # Remove frequency codes at end (w, m, q, y, u, d, etc.)
    title = re.sub(r'\s+[wmyqud]\s*$', '', title, flags=re.IGNORECASE)
    
    # Remove common suffixes/prefixes that indicate file metadata
    title = re.sub(r'^Weekly\s+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'^Monthly\s+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+Weekly\s*$', '', title, flags=re.IGNORECASE)
    
    # Clean up extra spaces and title case
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Title case (capitalize first letter of each word)
    # But preserve common acronyms (FX, IEEPA, D-Day, etc.)
    words = title.split()
    title_words = []
    for word in words:
        if word.upper() in ['FX', 'USD', 'EUR', 'GBP', 'JPY', 'CNY', 'KRW', 'INR', 'IDR', 'PHP', 'MYR', 'THB', 'SGD']:
            title_words.append(word.upper())
        elif '-' in word:
            # Handle hyphenated words (D-Day, etc.)
            parts = word.split('-')
            title_words.append('-'.join(p.capitalize() for p in parts))
        else:
            title_words.append(word.capitalize())
    
    return ' '.join(title_words)


def create_metadata_pills_html(provider: str, date_str: str, timeframe: str) -> str:
    """
    Create HTML for metadata pills: [Provider] [Date] [Timeframe]
    Uses simpler HTML structure compatible with Dash DataTable markdown renderer.
    
    Args:
        provider: Provider name (e.g., "MUFG")
        date_str: Date string in YYYY-MM-DD format
        timeframe: Timeframe (e.g., "1-3D", "1-2W")
    
    Returns:
        HTML string with styled pills
    
    STYLING CUSTOMIZATION:
    To tweak pill colors and font sizes, modify the inline styles below:
    - Provider pill: background-color (#E9ECEF), color (#495057), font-size (11px)
    - Date pill: background-color (#F8F9FA), color (#6C757D), font-size (11px)
    - Timeframe pill: background-color (#007BFF), color (#FFFFFF), font-size (13px), font-weight (600)
    """
    # Format date for display (Jan 09, 2026)
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        date_display = dt.strftime("%b %d, %Y")
    except:
        date_display = date_str
    
    # Escape HTML entities to prevent issues
    provider_escaped = provider.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    date_escaped = date_display.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    timeframe_escaped = timeframe.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # Provider pill (neutral gray) - using simpler inline style
    provider_html = f'<span style="display:inline-block;background:#E9ECEF;color:#495057;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:500;margin-right:6px">{provider_escaped}</span>'
    
    # Date pill (lighter gray / secondary)
    date_html = f'<span style="display:inline-block;background:#F8F9FA;color:#6C757D;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:400;margin-right:6px">{date_escaped}</span>'
    
    # Timeframe pill (primary color, larger, higher contrast)
    timeframe_html = f'<span style="display:inline-block;background:#007BFF;color:#FFFFFF;padding:4px 12px;border-radius:12px;font-size:13px;font-weight:600">{timeframe_escaped}</span>'
    
    return f'{provider_html}{date_html}{timeframe_html}'


def format_title_with_metadata(clean_title: str, provider: str, date_str: str, timeframe: str) -> str:
    """
    Format title column with cleaned title on first line and simple text metadata on second line.
    Dash DataTable markdown has limitations with complex HTML, so we use simple text format.
    
    Returns: Title with metadata as simple text
    """
    # Format date for display (Jan 09, 2026)
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        date_display = dt.strftime("%b %d, %Y")
    except:
        date_display = date_str
    
    # Use simple text format - DataTable markdown supports basic line breaks
    # Format: Title on first line, metadata on second line as plain text
    return f"{clean_title}<br/>{provider} • {date_display} • {timeframe}"


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
    children=[

        # Title
        html.H1(
            APP_TITLE,
            style={
                "width": "100%",
                "textAlign": "center",
                "color": TITLE_COLOR,
                "marginBottom": "35px",
            },
        ),

        # ── Row 1: Author/Source Filter (3 cols, Others last) ──
        html.Div(
            className="provider-checklist-section",
            style={
                "display": "flex",
                "justifyContent": "center",
                "alignItems": "flex-start",
                "gap": "20px",
                "marginBottom": "25px",
            },
            children=[
                html.Div(
                    className="provider-checklist-wrapper",
                    children=[
                        dcc.Checklist(
                            id="box-dropdown",
                            options=CATEGORY_OPTIONS,
                            value=[opt["value"] for opt in CATEGORY_OPTIONS],  # all selected by default
                            inputStyle={"marginRight": "8px"},
                            labelStyle={"display": "block"},
                        ),
                    ],
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
                        "gap": "10px",
                        "justifyContent": "center",
                    },
                ),
            ],
        ),

        # ── Row 2: Search Bars + Date Range + Counter (horizontal layout) ──
        html.Div(
            className="search-controls-wrapper",
            style={
                "display": "flex",
                "flexWrap": "wrap",
                "justifyContent": "center",
                "alignItems": "center",
                "gap": "15px",
                "marginBottom": "25px",
            },
            children=[
                # Title search
                dcc.Input(
                    id="title-search-input",
                    type="text",
                    placeholder="Search Titles…",
                    debounce=True,
                    style={"width": "250px"},
                ),
                html.Button("×", id="clear-title-search", className="btn btn-link btn-sm"),
                html.Button("Search", id="title-search-btn", className="btn btn-primary btn-sm"),
                
                # Content search
                dcc.Input(
                    id="content-search-input",
                    type="text",
                    placeholder="Search inside PDFs…",
                    debounce=True,
                    style={"width": "250px"},
                ),
                html.Button("×", id="clear-content-search", className="btn btn-link btn-sm"),
                html.Button("Search", id="content-search-btn", className="btn btn-primary btn-sm"),
                
                # Date range
                html.Label(
                    "📅",
                    style={'fontWeight': 'bold', 'fontSize': '16px', 'marginLeft': '10px'}
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
                
                # View Latest buttons
                html.Button(
                    "View Latest Daily Recap",
                    id="btn_view_latest_daily",
                    className="btn btn-sm btn-outline-primary",
                    style={"whiteSpace": "nowrap"}
                ),
                
                # Economic Calendar Admin button
                dcc.Link(
                    html.Button(
                        "📅 Economic Calendar",
                        className="btn btn-sm btn-outline-info",
                        style={"whiteSpace": "nowrap"}
                    ),
                    href="/admin/economic-calendar"
                ),
                
                # Article counter
                html.Div(
                    id='article-counter',
                    children="Loading..."
                ),
            ],
        ),

        # Summary Type Filter Row - Commented out for now
        # html.Div(
        #     style={
        #         "display": "flex",
        #         "justifyContent": "center",
        #         "alignItems": "center",
        #         "gap": "10px",
        #         "marginBottom": "15px",
        #     },
        #     children=[
        #         html.Label("Summary Type:", style={"fontWeight": "500", "marginRight": "5px"}),
        #         dcc.RadioItems(
        #             id="summary_type_filter",
        #             options=[
        #                 {"label": "All", "value": "all"},
        #                 {"label": "Daily Summary", "value": "daily"},
        #                 {"label": "Weekly Summary", "value": "weekly"},
        #             ],
        #             value="all",
        #             inline=True,
        #             inputStyle={"marginRight": "5px", "marginLeft": "10px"},
        #             labelStyle={"marginRight": "15px"},
        #         ),
        #     ],
        # ),

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
        html.Div(
            className="table-container",
            style={"marginTop": "25px"},
            children=[
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
                                {"id": "basename",         "name": "basename", "hideable": True},  # Hidden via hidden_columns property
                            ],
                            data=[],
                            hidden_columns=["basename"],  # Supported way to hide columns
                            filter_action="native",
                            sort_action="native",
                            page_action="native",
                            page_size=20,
                            
                            # Enable row clicks
                            row_selectable=False,  # Don't use checkboxes
                            active_cell=None,  # Track cell clicks


                            # highlight today's rows
                            style_data_conditional=[
                        # 1) odd/even for all the other rows
                        {"if": {"row_index": "odd"},  "backgroundColor": ROW_ODD_COLOR},
                        {"if": {"row_index": "even"}, "backgroundColor": ROW_EVEN_COLOR},

                        # 2) Score column color coding based on score (0-10 scale)
                        # Using text type, so we check for specific string values
                        # Note: Filter queries use exact string matches (no OR support, so we'll use individual rules)
                        # 0-2: Dark red
                        # Removed "summary" column coloring - only Score column has colors now
                        {
                            "if": {"filter_query": '{summary_score} = "0"', "column_id": "summary_score"},
                            "backgroundColor": "#8B0000", "color": "white"
                        },
                        {
                            "if": {"filter_query": '{summary_score} = "1"', "column_id": "summary_score"},
                            "backgroundColor": "#8B0000", "color": "white"
                        },
                        {
                            "if": {"filter_query": '{summary_score} = "2"', "column_id": "summary_score"},
                            "backgroundColor": "#8B0000", "color": "white"
                        },
                        # 3-4: Red-orange
                        {
                            "if": {"filter_query": '{summary_score} = "3"', "column_id": "summary_score"},
                            "backgroundColor": "#FF4500",
                        },
                        {
                            "if": {"filter_query": '{summary_score} = "4"', "column_id": "summary_score"},
                            "backgroundColor": "#FF4500",
                        },
                        # 5: Yellow
                        {
                            "if": {"filter_query": '{summary_score} = "5"', "column_id": "summary_score"},
                            "backgroundColor": "#FFD700",
                        },
                        # 6-7: Yellow-green
                        {
                            "if": {"filter_query": '{summary_score} = "6"', "column_id": "summary_score"},
                            "backgroundColor": "#9ACD32",
                        },
                        {
                            "if": {"filter_query": '{summary_score} = "7"', "column_id": "summary_score"},
                            "backgroundColor": "#9ACD32",
                        },
                        # 8-10: Green
                        {
                            "if": {"filter_query": '{summary_score} = "8"', "column_id": "summary_score"},
                            "backgroundColor": "#228B22", "color": "white"
                        },
                        {
                            "if": {"filter_query": '{summary_score} = "9"', "column_id": "summary_score"},
                            "backgroundColor": "#228B22", "color": "white"
                        },
                        {
                            "if": {"filter_query": '{summary_score} = "10"', "column_id": "summary_score"},
                            "backgroundColor": "#228B22", "color": "white"
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
                        "padding": "12px",
                        "whiteSpace": "nowrap",
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                    },
                    style_cell_conditional=[
                        {"if": {"column_id": "view"}, "width": "80px", "maxWidth": "80px"},
                        {"if": {"column_id": "product_categories"}, "width": "80px", "maxWidth": "80px"},
                    ],
                    style_header={
                        "backgroundColor": HEADER_BG_COLOR,
                        "color": HEADER_TEXT_COLOR,
                        "fontWeight": "bold",
                    },
                )
                    ],
                ),
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
    
    # Stores for daily view
    dcc.Store(id='daily-articles-store', data=[]),
    dcc.Store(id='daily-selected-artifact', data=""),
    dcc.Store(id='daily-selected-date', data=None),  # Stores selected date as YYYY-MM-DD string
    
    # Stores for economic calendar admin page
    dcc.Store(id='econ-dynamics-mode', data=True, storage_type='session'),  # Dynamics on/off
    # Holds the result of a clientside /api/econ/generate-brief fetch.
    # Written by the clientside callback; read by render_generated_brief().
    dcc.Store(id='econ-brief-result-store', data=None),
    
    # Location for navigation
    dcc.Location(id='url', refresh=True),

    

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
            # Hidden store and div for navigation
            dcc.Store(id="nav-url-store", data=""),
            html.Div(id="dummy-nav-output", style={"display": "none"}),

            # Tabs for Daily View and Library
            dcc.Tabs(
                id='main-tabs',
                value='daily-view',  # default tab
                children=[

                    # ---- TAB 1: DAILY VIEW ----
                    dcc.Tab(
                        label='Daily View',
                        value='daily-view',
                        style=TAB_STYLE,
                        selected_style=SELECTED_TAB_STYLE,
                        children=[
                            html.Div(
                                id="daily-view-container",
                                style={"padding": "20px"},
                                children=[
                                    html.Div(
                                        style={
                                            "display": "flex",
                                            "gap": "20px",
                                            "height": "calc(100vh - 200px)"
                                        },
                                        children=[
                                            # Sidebar with article list
                                            html.Div(
                                                id="daily-view-sidebar",
                                                style={
                                                    "width": "360px",
                                                    "minWidth": "360px",
                                                    "overflowY": "auto",
                                                    "borderRight": "1px solid #ddd",
                                                    "paddingRight": "15px"
                                                },
                                                children=[
                                                    html.Div(
                                                        style={
                                                            "display": "flex",
                                                            "justifyContent": "space-between",
                                                            "alignItems": "center",
                                                            "marginBottom": "15px"
                                                        },
                                                        children=[
                                                            html.H3(
                                                                "Articles",
                                                                style={
                                                                    "margin": "0",
                                                                    "color": HEADER_BG_COLOR
                                                                }
                                                            ),
                                                            html.Div(
                                                                style={
                                                                    "display": "flex",
                                                                    "gap": "5px",
                                                                    "alignItems": "center"
                                                                },
                                                                children=[
                                                                    html.Button(
                                                                        "◀",
                                                                        id="daily-view-date-prev",
                                                                        n_clicks=0,
                                                                        style={
                                                                            "padding": "4px 10px",
                                                                            "fontSize": "14px",
                                                                            "backgroundColor": "#f8f9fa",
                                                                            "color": "#495057",
                                                                            "border": "1px solid #ddd",
                                                                            "borderRadius": "4px",
                                                                            "cursor": "pointer",
                                                                            "fontWeight": "bold"
                                                                        }
                                                                    ),
                                                                    dcc.Input(
                                                                        id='daily-view-date-input',
                                                                        type='text',
                                                                        placeholder='YYYY-MM-DD',
                                                                        value=(datetime.date.today() - datetime.timedelta(days=1)).isoformat(),
                                                                        style={
                                                                            "width": "110px",
                                                                            "padding": "4px 8px",
                                                                            "fontSize": "13px",
                                                                            "border": "1px solid #ddd",
                                                                            "borderRadius": "4px"
                                                                        }
                                                                    ),
                                                                    html.Button(
                                                                        "▶",
                                                                        id="daily-view-date-next",
                                                                        n_clicks=0,
                                                                        style={
                                                                            "padding": "4px 10px",
                                                                            "fontSize": "14px",
                                                                            "backgroundColor": "#f8f9fa",
                                                                            "color": "#495057",
                                                                            "border": "1px solid #ddd",
                                                                            "borderRadius": "4px",
                                                                            "cursor": "pointer",
                                                                            "fontWeight": "bold"
                                                                        }
                                                                    ),
                                                                    html.Button(
                                                                        "OK",
                                                                        id="daily-view-date-ok",
                                                                        n_clicks=0,
                                                                        style={
                                                                            "padding": "4px 12px",
                                                                            "fontSize": "13px",
                                                                            "backgroundColor": "#007bff",
                                                                            "color": "white",
                                                                            "border": "none",
                                                                            "borderRadius": "4px",
                                                                            "cursor": "pointer"
                                                                        }
                                                                    )
                                                                ]
                                                            )
                                                        ]
                                                    ),
                                                    
                                                    html.Div(id="daily-view-article-list")
                                                ]
                                            ),
                                            # Main content panel
                                            html.Div(
                                                id="daily-view-main",
                                                style={
                                                    "flex": "1",
                                                    "overflowY": "auto",
                                                    "paddingLeft": "15px"
                                                },
                                                children=[
                                                    html.Div(id="daily-view-content")
                                                ]
                                            )
                                        ]
                                    )
                                ]
                            )
                        ]
                    ),

                    # ---- TAB 2: LIBRARY ----
                    dcc.Tab(
                        label='Library',
                        value='library',
                        style=TAB_STYLE,
                        selected_style=SELECTED_TAB_STYLE,
                        children=[
                            html.Div(
                                id="library-container",
                                style={"padding": "20px"},
                                children=[
                                    # Table view wrapper
                                    html.Div(
                                        id="table-view-container",
                                        style={"display": "block"},
                                        children=[files_layout]
                                    ),
                                    # Summary view wrapper
                                    html.Div(
                                        id="summary-view-container",
                                        style={"display": "none"},
                                        children=[]
                                    )
                                ]
                            )
                        ]
                    ),
                    
                    # ---- TAB 3: ECONOMIC CALENDAR ADMIN ----
                    dcc.Tab(
                        label='Economic Calendar',
                        value='econ-calendar',
                        style=TAB_STYLE,
                        selected_style=SELECTED_TAB_STYLE,
                        children=[
                            html.Div(
                                id="econ-admin-container",
                                style={"padding": "20px", "maxWidth": "1200px", "margin": "0 auto"},
                                children=[
                                    # DB health banner – populated on tab open
                                    html.Div(id="econ-db-health-banner"),

                                    html.H2("Economic Calendar Import", 
                                           style={"color": "#0056B3", "marginBottom": "10px"}),

                                    # Dynamics mode toggle row
                                    html.Div([
                                        html.Label(
                                            "Dynamics mode:",
                                            style={"fontWeight": "bold", "marginRight": "10px",
                                                   "verticalAlign": "middle"}
                                        ),
                                        dcc.RadioItems(
                                            id="econ-dynamics-toggle",
                                            options=[
                                                {"label": " On ", "value": True},
                                                {"label": " Off", "value": False},
                                            ],
                                            value=True,
                                            inline=True,
                                            labelStyle={"marginRight": "12px", "cursor": "pointer"},
                                        ),
                                        html.Span(
                                            "When off, Dynamics explainers are skipped and only Theory is shown.",
                                            style={"fontSize": "12px", "color": "#666",
                                                   "marginLeft": "16px", "fontStyle": "italic"}
                                        ),
                                    ], style={"display": "flex", "alignItems": "center",
                                              "marginBottom": "20px",
                                              "padding": "10px 14px",
                                              "backgroundColor": "#f0f4ff",
                                              "borderRadius": "4px",
                                              "border": "1px solid #c3d0f0"}),
                                    
                                    # Paste area
                                    html.Div([
                                        html.Label("Paste Weekly Calendar Text:",
                                                  style={"fontWeight": "bold", "marginBottom": "5px", "display": "block"}),
                                        dcc.Textarea(
                                            id="econ-textarea",
                                            placeholder="Sunday, February 22 to Saturday, February 28, 2026\n\nMonday, February 23, 2026\n10:00 Event Title",
                                            style={
                                                "width": "100%",
                                                "height": "200px",
                                                "fontFamily": "monospace",
                                                "fontSize": "13px",
                                                "padding": "10px",
                                                "border": "1px solid #ccc",
                                                "borderRadius": "4px"
                                            }
                                        )
                                    ], style={"marginBottom": "15px"}),
                                    
                                    # Buttons
                                    html.Div([
                                        html.Button(
                                            "Parse",
                                            id="econ-parse-btn",
                                            className="btn btn-primary",
                                            style={"marginRight": "10px"}
                                        ),
                                        html.Button(
                                            "Save",
                                            id="econ-save-btn",
                                            className="btn btn-success",
                                            disabled=True,
                                            style={"marginRight": "10px"}
                                        ),
                                        html.Button(
                                            "Clear",
                                            id="econ-clear-btn",
                                            className="btn btn-secondary"
                                        ),
                                    ], style={"marginBottom": "20px"}),
                                    
                                    # Status area
                                    html.Div(id="econ-status", style={"marginBottom": "10px"}),

                                    # AI generation progress area (shown only during generation)
                                    html.Div(
                                        id="econ-gen-progress",
                                        style={"marginBottom": "20px"},
                                        children=[]
                                    ),

                                    # Interval that polls generation progress (disabled by default)
                                    dcc.Interval(
                                        id="econ-gen-interval",
                                        interval=800,       # ms between polls
                                        n_intervals=0,
                                        disabled=True,
                                    ),

                                    # Store: holds generation job state
                                    # {dates, dynamics_mode, completed, total, results, done}
                                    dcc.Store(id="econ-gen-job-store", data=None),
                                    
                                    # Divider
                                    html.Hr(style={"margin": "30px 0"}),
                                    
                                    # Recently imported weeks
                                    html.H3("Recently Imported Weeks",
                                           style={"color": "#0056B3", "marginBottom": "15px"}),
                                    html.Div(id="econ-weeks-list")
                                ]
                            )
                        ]
                    ),
                ]
            )
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
    Output("nav-url-store", "data"),
    [Input("btn_view_latest_daily", "n_clicks")
     # Input("btn_view_latest_weekly", "n_clicks")  # Commented out for now
     ],
    [State("login-user", "data")],
    prevent_initial_call=True
)
def navigate_to_latest_rollup(n_daily, login_user):
    """Find latest rollup URL and store it for clientside navigation."""
    if not login_user:
        raise PreventUpdate
    
    triggered = ctx.triggered_id
    if triggered is None:
        raise PreventUpdate
    
    # Scan for rollups
    rollups_list = scan_rollups()
    
    if triggered == "btn_view_latest_daily":
        # Find latest daily rollup
        daily_rollups = [r for r in rollups_list if r["kind"] == "rollup_daily"]
        if not daily_rollups:
            raise PreventUpdate
        
        # Sort by date descending (most recent first)
        daily_rollups.sort(key=lambda x: x["date"], reverse=True)
        latest = daily_rollups[0]
        filename = latest["fname"].replace('__sum.json', '__sum.pdf')  # Open PDF instead of JSON
        url = f"/view?file=rollups/daily/{urllib.parse.quote(filename)}"
        return url
    
    # elif triggered == "btn_view_latest_weekly":
    #     # Find latest weekly rollup
    #     weekly_rollups = [r for r in rollups_list if r["kind"] == "rollup_weekly"]
    #     if not weekly_rollups:
    #         raise PreventUpdate
    #     
    #     # Sort by start_date descending
    #     weekly_rollups.sort(key=lambda x: x["start_date"], reverse=True)
    #     latest = weekly_rollups[0]
    #     filename = latest["fname"]
    #     url = f"/view?file=rollups/weekly/{urllib.parse.quote(filename)}"
    #     return url
    
    raise PreventUpdate

# Clientside callback to handle navigation when store updates
app.clientside_callback(
    """
    function(url) {
        if (url && url !== '') {
            window.location.href = url;
        }
        return '';
    }
    """,
    Output("dummy-nav-output", "children"),
    Input("nav-url-store", "data"),
    prevent_initial_call=True
)

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
        # Input("summary_type_filter",  "value"),  # Commented out for now
        Input("login-user",           "data"),
    ],
    [
        State("box-dropdown",         "options"),
        State("title-search-input",   "value"),
        State("content-search-input", "value"),
    ],
    prevent_initial_call=False,
)
def update_file_table(
    sel, n_select, n_clear,
    _tbtn, _tenter,
    _cbtn, _center,
    start_date, end_date, _clear_dates,
    # summary_type_filter,  # Commented out for now
    login_user,
    options, title_value, content_value
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

    # 1) Handle Select/Clear All for categories
    triggered = ctx.triggered_id
    if triggered == "select-all":
        sel = [opt["value"] for opt in options]
    elif triggered == "clear-all":
        sel = []

    selected = set(sel or [])
    tt = (title_value or "").strip().lower()
    ct = (content_value or "").strip().lower()

    # 2) Build columns (dynamically - reordered: Firm, Frequency, Date, Title, Categories, View, Summary, Score, Charts)
    cols = [
        {"id": "firm",             "name": "Firm",       "type": "text"},
        {"id": "frequency",        "name": "Frequency",  "type": "text"},
        {"id": "date",             "name": "Date",       "type": "datetime"},
        {"id": "title",            "name": "Title",      "type": "text"},  # Plain text only - no HTML, no metadata
        {"id": "product_categories", "name": "Categories", "type": "text"},
        {"id": "view",             "name": "View",       "presentation": "markdown"},
        {"id": "summary",          "name": "Summary",    "presentation": "markdown"},
        {"id": "summary_score",    "name": "Score",      "type": "text"},
        {"id": "chart_score",      "name": "Charts",     "type": "text"},
    ]
    if login_user == "iwill":
        cols.insert(4, {"id": "subject",  "name": "Subject",  "type": "text"})
        cols.append({"id": "download","name": "Download","presentation": "markdown"})

    # 3) Scan rollups first (separate from regular articles)
    rollup_files = []
    rollups_list = scan_rollups()
    print(f"[ROLLUP PROCESS] Processing {len(rollups_list)} rollup files from scan")
    
    for idx, rollup_info in enumerate(rollups_list, 1):
        print(f"[ROLLUP PROCESS] [{idx}/{len(rollups_list)}] Processing: {rollup_info.get('fname', 'unknown')}")
        # Parse date for filtering
        if rollup_info["kind"] == "rollup_daily":
            rollup_date = rollup_info["date"]
            date_fmt = rollup_date.strftime("%Y-%m-%d")
            is_today = (rollup_date == datetime.date.today())
        else:  # weekly
            rollup_date = rollup_info["end_date"]  # Use end date for sorting/filtering
            date_fmt = f"{rollup_info['start_date'].strftime('%Y-%m-%d')} to {rollup_info['end_date'].strftime('%Y-%m-%d')}"
            is_today = False
        
        # Apply date range filter
        if start_date and rollup_date < datetime.datetime.fromisoformat(start_date).date():
            print(f"  [X] Filtered out by date range (before start_date: {start_date})")
            continue
        if end_date and rollup_date > datetime.datetime.fromisoformat(end_date).date():
            print(f"  [X] Filtered out by date range (after end_date: {end_date})")
            continue
        
        # Load rollup JSON for UI data
        rollup_json = load_rollup_json(Path(rollup_info["path"]))
        if rollup_json is None:
            print(f"  [X] Failed to load JSON - skipping this rollup")
            continue
        
        ui_data = rollup_json.get("ui", {})
        if not ui_data:
            print(f"  ⚠ WARNING: Rollup JSON loaded but 'ui' key is missing or empty")
        else:
            print(f"  [OK] Successfully loaded, UI title: {ui_data.get('title', 'N/A')}")
        
        summary_type = "daily" if rollup_info["kind"] == "rollup_daily" else "weekly"
        # Build relative path for view links
        subdir = "daily" if rollup_info["kind"] == "rollup_daily" else "weekly"
        relative_path = f"rollups/{subdir}/{rollup_info['fname']}"
        
        rollup_files.append({
            'path': rollup_info["path"],
            'fname': rollup_info["fname"],
            'relative_path': relative_path,  # For view links: rollups/daily/ or rollups/weekly/
            'category': "Rollups",  # Special category
            'title_str': ui_data.get("title", "Rollup"),
            'date_fmt': date_fmt,
            'is_today': is_today,
            'frequency': 'D',  # 'D' for daily rollup
            'timeframe': '',
            'subj': "General",
            'has_summary': True,
            'summary_pdf_filename': rollup_info["fname"].replace(".json", ".pdf"),  # May not exist
            'summary_json_filename': rollup_info["fname"],
            'summary_filename': rollup_info["fname"],  # Link to JSON
            'product_categories': {},
            'summary_score': None,
            'chart_score': None,
            'extraction_status': "ok",
            'extraction_quality': None,
            'is_rollup': True,
            'rollup_kind': rollup_info["kind"],
            'rollup_meta': rollup_info,
            'rollup_ui': ui_data,
            'summary_type': summary_type,  # 'daily' or 'weekly'
            'rollup_date': rollup_date  # Store date for sorting
        })
    
    # 4) Scan directories and collect candidate files (regular articles)
    candidate_files = []
    scan = [(FILES_DIR, "General")]
    if login_user == "iwill":
        scan.append((SC, "Small Caps"))

    for dpath, subj in scan:
        if not os.path.isdir(dpath):
            continue

        # Use helper to collect all PDFs from both new and legacy layouts
        # (deduplicates by basename, prioritizes new layout)
        all_pdfs = iter_all_candidate_pdfs(dpath)
        
        # Process all discovered PDFs (both new and legacy)
        for fname, full_path, layout_type in all_pdfs:
            # only PDFs
            if not fname.lower().endswith(".pdf") or fname == "README.txt":
                continue

            # Parse filename using helper (supports both old and new formats)
            parsed = parse_pdf_filename(fname)
            provider = parsed['provider']
            title_str = parsed['title_str']
            date_fmt = parsed['date_fmt']
            frequency = parsed['frequency']
            horizon_code = parsed['horizon_code']
            is_today = parsed['is_today']
            
            # Use provider as category (firm) for filtering
            # This works for both old and new formats
            category = provider if provider else "Others"

            # apply multi-select filter
            if selected and "All" not in selected and category not in selected:
                continue

            # Apply date range filter
            if date_fmt != "Unknown":
                try:
                    dt = datetime.datetime.strptime(date_fmt, "%Y-%m-%d")
                    if start_date and dt.date() < datetime.datetime.fromisoformat(start_date).date():
                        continue  # Skip files before start_date
                    if end_date and dt.date() > datetime.datetime.fromisoformat(end_date).date():
                        continue  # Skip files after end_date
                except:
                    pass
            else:
                # Skip files with unparseable dates if date filter is active
                if start_date or end_date:
                    continue

            # title search filter
            if tt and tt not in title_str.lower():
                continue
            
            # Check for summary (do this ONCE during candidate building, not later)
            has_sum, pdf_filename, json_filename = has_summary_file(full_path)
            
            # Prefer PDF summary, fallback to JSON (which can be converted to PDF)
            summary_filename = pdf_filename if pdf_filename else json_filename
            
            # Load product categories, scores, timeframe, and extraction status from summary JSON if available
            product_categories = {}
            summary_score = None
            chart_score = None
            timeframe = None
            extraction_status = "unknown"
            extraction_quality = None
            is_low_confidence = False
            
            if json_filename:
                # Build full path for JSON (handle both layouts)
                if 'artifacts/' in json_filename:
                    # New layout - json_filename is already a relative path
                    json_path = os.path.join(FILES_DIR, json_filename)
                else:
                    # Legacy layout
                    json_path = os.path.join(dpath, json_filename)
                
                product_categories = load_product_categories_from_summary(json_path)
                summary_score, chart_score = load_summary_score(json_path)
                timeframe = load_timeframe_from_summary(json_path)
                extraction_status, extraction_quality, is_low_confidence = load_extraction_status(json_path)
                
                # Override horizon_code from sum.json if filename didn't have it (new format)
                if horizon_code == 'u':
                    horizon_code = load_horizon_from_summary(json_path)
                    # Map horizon code to frequency
                    fmap = {"y": "Yearly", "q": "Quarterly", "m": "Monthly", "w": "Weekly", "u": ""}
                    frequency = fmap.get(horizon_code.lower(), "")
            # else: pdf_filename only or no summary - use initialized defaults
            
            candidate_files.append({
                'path': full_path,
                'fname': fname,
                'category': category,
                'summary_type': 'article',  # Tag as article
                'title_str': title_str,
                'date_fmt': date_fmt,
                'is_today': is_today,
                'frequency': frequency,
                'timeframe': timeframe,                   # Timeframe from summary JSON (e.g., "1-3d")
                'subj': subj,
                'has_summary': has_sum,
                'summary_pdf_filename': pdf_filename,      # PDF summary (preferred)
                'summary_json_filename': json_filename,    # JSON summary (source)
                'summary_filename': summary_filename,      # Which one to link to (PDF preferred)
                'product_categories': product_categories,
                'summary_score': summary_score,           # Score for color coding (0-10)
                'chart_score': chart_score,               # Chart score (0-3)
                'extraction_status': extraction_status,    # Extraction status: "ok" | "degraded" | "failed" | "unknown"
                'extraction_quality': extraction_quality,  # Extraction quality (0-100) or None
                'is_low_confidence': is_low_confidence     # Low confidence flag
            })

    # 5) FALLBACK DISCOVERY: Scan artifacts/*/sum.json if few/no PDFs found
    # This ensures the app works even if originals are missing or naming mismatches
    if PATH_MANAGER_AVAILABLE and PATH_MANAGER and len(candidate_files) < 5:
        print(f"[FALLBACK] Only {len(candidate_files)} PDFs found, scanning artifacts for orphaned summaries...")
        fallback_candidates = discover_from_artifacts(
            PATH_MANAGER.artifacts_dir,
            FILES_DIR,
            seen_basenames=set(os.path.splitext(f['fname'])[0] for f in candidate_files),
            selected=selected,
            start_date=start_date,
            end_date=end_date,
            tt=tt
        )
        candidate_files.extend(fallback_candidates)
        print(f"[FALLBACK] Added {len(fallback_candidates)} artifacts-only entries")

    # Combine rollups and regular articles
    all_candidates = rollup_files + candidate_files
    
    # Batch process PDF content search if needed (skip rollups, only search regular PDFs)
    if ct and candidate_files:
        # Show progress bar with file count
        total_files = len(candidate_files)
        progress_style = {"visibility": "visible", "marginBottom": "10px"}
        progress_text = f"Searching PDF content in {total_files} file{'s' if total_files != 1 else ''}..."
        progress_bar_style = {"width": "0%", "transition": "width 0.3s ease", "backgroundColor": "#007bff"}
        progress_bar_text = "Starting..."
        
        # Process PDFs in batch (only regular articles, not rollups)
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

    # Combine rollups and regular articles
    all_candidates = rollup_files + candidate_files
    
    # Apply summary type filter - Commented out for now
    # summary_type_filter = "all"  # Default to "all" when filter is disabled
    # if summary_type_filter == "daily":
    #     all_candidates = [f for f in all_candidates if f.get('summary_type') == 'daily']
    # elif summary_type_filter == "weekly":
    #     all_candidates = [f for f in all_candidates if f.get('summary_type') == 'weekly']
    # "all" shows everything, no filtering needed
    
    # Build rows from filtered candidates
    rows = []
    for file_info in all_candidates:
        # Handle rollups differently
        is_rollup = file_info.get('is_rollup', False)
        
        if is_rollup:
            # Rollups: skip PDF content search, use simple title format
            # Format: "Daily Recap YYYY-MM-DD"
            date_display = file_info.get('date_fmt', '')
            
            # For daily rollups, format as "Daily Recap YYYY-MM-DD"
            if file_info.get('summary_type') == 'daily':
                title_with_pills = f"Daily Recap {date_display}"
            else:
                # For weekly rollups (if needed later)
                title_with_pills = f"Weekly Recap {date_display}"
            
            # Link to rollup PDF - use relative_path if available, otherwise construct it
            if 'relative_path' in file_info:
                # Replace .json with .pdf for rollup files
                pdf_path = file_info['relative_path'].replace('__sum.json', '__sum.pdf')
                safe = urllib.parse.quote(pdf_path)
            else:
                # Fallback: construct path from summary_type
                subdir = "daily" if file_info.get('summary_type') == 'daily' else "weekly"
                pdf_fname = file_info['fname'].replace('__sum.json', '__sum.pdf')
                safe = urllib.parse.quote(f"rollups/{subdir}/{pdf_fname}")
            view_md = f"[View](/view?file={safe})"
            summary_md = "--"
            
            row = {
                "firm":              "Rollups",
                "frequency":         file_info.get('frequency', 'D'),  # Use frequency from file_info (should be 'D' for daily)
                "date":              file_info['date_fmt'],
                "title":             title_with_pills,
                "product_categories": "—",
                "view":              view_md,
                "summary":           summary_md,
                "summary_score":     "N/A",
                "chart_score":       "N/A",
                "is_today":          file_info['is_today'],
                "basename":          file_info['fname'].replace('__sum.json', '').replace('.json', '')  # For rollups
            }
        else:
            # Regular articles: apply filters and formatting
            # Skip if PDF content search failed
            if ct and not pdf_results.get(file_info['path'], False):
                continue
            
            # Filter out failed and triage-skipped summaries from main feed
            extraction_status = file_info.get('extraction_status', 'unknown')
            if extraction_status in ('failed', 'skipped'):
                continue  # Skip failed/triage-skipped summaries - do not publish to main feed
            
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
                    
                    # Add warning badge for degraded extractions
                    if file_info.get('is_low_confidence') or extraction_status == 'degraded':
                        summary_md = f"[⚠️ View](/view?file={safe_sum})"
                    else:
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
            
            # Format scores: "N/A" for missing, number string for valid scores
            summary_score_str = "N/A" if summary_score is None else str(summary_score)
            chart_score_str = "N/A" if chart_score is None else str(chart_score)
            
            # Clean title - use ONLY the clean title, no metadata, no HTML tags
            provider = file_info['category']
            clean_title_str = clean_title(file_info['title_str'], provider)
            
            # Use ONLY the clean title - no metadata, no <br/>, no dates, no provider, no frequency
            title_with_pills = clean_title_str
            
            row = {
                "firm":              file_info['category'],
                "frequency":         file_info['frequency'],
                "date":              file_info['date_fmt'],
                "title":             title_with_pills,
                "product_categories": product_categories_str,
                "view":              view_md,
                "summary":           summary_md,
                "summary_score":     summary_score_str,  # "N/A" or number string
                "chart_score":       chart_score_str,    # "N/A" or number string
                "is_today":          file_info['is_today'],
                "basename":          Path(file_info['fname']).stem  # Without .pdf extension
            }
        if login_user == "iwill":
            if not is_rollup:
                row["subject"]  = file_info['subj']
                row["download"] = f"[Download](/download?file={safe})"
            else:
                row["subject"] = "General"
                row["download"] = "—"

        rows.append(row)

    # Sort rows by date (most recent first), ignoring "Unknown"
    def sort_key(r):
        try:
            return datetime.datetime.strptime(r["date"], "%Y-%m-%d")
        except:
            return datetime.datetime.min  # "Unknown" dates go last

    rows.sort(key=sort_key, reverse=True)
    
    # Safety check: ensure rows is always a list (should never fail, but just in case)
    if not isinstance(rows, list):
        rows = []
    
    # Calculate article counts for counter
    total_shown = len(rows)
    total_candidates = len(candidate_files)
    
    # Determine if any filters are active
    all_categories_selected = len(selected) >= len(options) if options else True
    filters_active = (
        ct or tt or 
        (start_date or end_date) or 
        (not all_categories_selected)
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

    # Handle rollups in subdirectories
    if f.startswith("rollups/"):
        rollup_path = os.path.join(FILES_DIR, f)
        if os.path.isfile(rollup_path):
            directory = os.path.dirname(rollup_path)
            filename = os.path.basename(rollup_path)
            return send_from_directory(directory, filename)
        return "Rollup file not found.", 404
    
    # Handle artifacts/ paths (new layout)
    if f.startswith("artifacts/"):
        artifact_path = os.path.join(FILES_DIR, f)
        if os.path.isfile(artifact_path):
            directory = os.path.dirname(artifact_path)
            filename = os.path.basename(artifact_path)
            return send_from_directory(directory, filename)
        return "Artifact file not found.", 404

    # Check originals/ first if path manager available
    if PATH_MANAGER_AVAILABLE and PATH_MANAGER:
        # Try originals/ first
        original_path = PATH_MANAGER.original_pdf_path(f)
        if original_path.exists():
            return send_from_directory(str(original_path.parent), f)
    
    # Check both directories (legacy)
    dirs_to_check = [
        FILES_DIR,
        r"C:\Users\H&CDanHughes\Documents\SC_files"
    ]

    # Special handling for __sum.pdf: generate on-demand if missing
    if f.endswith("__sum.pdf"):
        for directory in dirs_to_check:
            full_path = os.path.join(directory, f)
            
            # If PDF exists, serve it
            if os.path.isfile(full_path):
                return send_from_directory(directory, f)
            
            # If PDF doesn't exist, try to generate from JSON
            json_file = f.replace("__sum.pdf", "__sum.json")
            json_path = os.path.join(directory, json_file)
            
            if os.path.isfile(json_path):
                try:
                    # Try to generate PDF on-demand
                    from pathlib import Path
                    from summarize_pdf import ensure_summary_pdf
                    
                    # Construct original PDF path
                    original_pdf = f.replace("__sum.pdf", ".pdf")
                    original_path = Path(os.path.join(directory, original_pdf))
                    
                    if ensure_summary_pdf(original_path):
                        # PDF was generated, serve it
                        return send_from_directory(directory, f)
                    else:
                        return f"Failed to generate PDF summary for {f}", 500
                        
                except Exception as e:
                    print(f"[ERROR] On-demand PDF generation failed for {f}: {e}")
                    return f"Error generating PDF summary: {str(e)}", 500
        
        return "File not found.", 404

    # Normal file serving for all other files
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
# 8a) ECON BRIEF API
############################

# ---------------------------------------------------------------------------
# POST /api/econ/generate-brief
#
# Request JSON body:
#   { "date_iso": "YYYY-MM-DD", "dynamics_mode": true }
#
# Auth: caller must be logged-in (login-status session cookie is set by Dash).
#       We validate via the Dash session store value that Dash writes to the
#       Flask session under the key "login_user".  If that key is absent or
#       empty, we return 401.
#
# Idempotency:
#   A per-date threading.Lock prevents two simultaneous calls from both
#   reaching the LLM.  The second caller blocks, then reads the row that
#   the first caller already committed and returns it without a second write.
#
# Response JSON (success 200):
#   { "date_iso": "...", "theory_text": "...", "dynamics_text": "..." }
#
# Response JSON (error):
#   { "error": "..." }   with appropriate HTTP status code.
# ---------------------------------------------------------------------------
@server.route("/api/econ/generate-brief", methods=["POST"])
def api_generate_brief():
    """
    Generate (or return cached) economic brief for a given date.

    Only callable by authenticated users.  Uses a per-date lock so that
    N simultaneous requests produce exactly one LLM call and one DB write.
    """
    # ── Auth guard ────────────────────────────────────────────────────────
    # Dash writes the logged-in username into the Flask session under
    # the key "_dash_login_user" via dcc.Store(storage_type='session').
    # We check the raw Flask session; if the user is not logged in the
    # session key will be absent.
    login_user = flask_session.get("login_user", "")
    if not login_user:
        # Fallback: accept if the request carries an X-Login-User header
        # (set by the clientside callback below as a lightweight signal).
        login_user = request.headers.get("X-Login-User", "")
    if not login_user:
        print("[ECON API] /api/econ/generate-brief called without authentication")
        return jsonify({"error": "Authentication required"}), 401

    # ── Parse request body ────────────────────────────────────────────────
    body = request.get_json(silent=True) or {}
    date_iso = (body.get("date_iso") or "").strip()
    dynamics_mode = bool(body.get("dynamics_mode", True))

    if not date_iso:
        return jsonify({"error": "date_iso is required"}), 400

    # Validate date format
    try:
        import datetime as _dt
        _dt.datetime.strptime(date_iso, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": f"Invalid date_iso format: {date_iso!r}. Expected YYYY-MM-DD"}), 400

    print(f"[ECON API] generate-brief requested: date_key={date_iso}, user={login_user}, dynamics_mode={dynamics_mode}")

    if not ECON_CALENDAR_AVAILABLE:
        return jsonify({"error": "Economic calendar module not available"}), 503

    # ── Check if events exist for this date ───────────────────────────────
    try:
        events = get_events_for_date(DB_PATH, date_iso)
    except Exception as exc:
        print(f"[ECON API] get_events_for_date failed for {date_iso}: {exc}")
        return jsonify({"error": "Database error checking events"}), 500

    if not events:
        return jsonify({"error": f"No economic events found for {date_iso}"}), 404

    # ── Acquire per-date lock ─────────────────────────────────────────────
    # This is the idempotency guard.  If two requests arrive simultaneously:
    #   Request A acquires the lock → calls LLM → writes DB → releases lock.
    #   Request B blocks on acquire → lock released → reads the row A wrote
    #   → returns it without calling the LLM a second time.
    date_lock = _get_brief_lock(date_iso)
    acquired = date_lock.acquire(timeout=60)   # max 60 s wait
    if not acquired:
        return jsonify({"error": "Timed out waiting for brief generation lock. Try again."}), 503

    try:
        # ── Re-check after acquiring lock (second caller fast-path) ───────
        # If the first caller already wrote the brief, return it directly.
        try:
            existing = get_daily_brief(DB_PATH, date_iso)
        except Exception:
            existing = None

        _ERROR_PREFIXES = (
            "brief generation unavailable",
            "summary unavailable",
            "summary generation failed",
            "error code:",
        )
        existing_theory = (existing or {}).get("theory_text", "").strip()
        existing_is_valid = existing_theory and not any(
            existing_theory.lower().startswith(p) for p in _ERROR_PREFIXES
        )

        if existing_is_valid:
            print(f"[ECON API] Brief already exists for date_key={date_iso} (written by concurrent request), returning cached")
            return jsonify({
                "date_iso": date_iso,
                "theory_text": existing_theory,
                "dynamics_text": (existing or {}).get("dynamics_text", "").strip(),
                "source": "cache",
            }), 200

        # ── Generate brief (we are the first caller or cache was invalid) ─
        print(f"[ECON API] Starting brief generation for date_key={date_iso}")
        try:
            from econ_calendar_ai import generate_for_date as _gen_for_date
            rollups_dir = Path(FILES_DIR) / "rollups" / "daily"
            gen_result = _gen_for_date(
                date_iso,
                dynamics_mode=dynamics_mode,
                db_path=DB_PATH,
                rollups_daily_dir=rollups_dir,
            )
        except Exception as exc:
            import traceback
            print(f"[ECON API] generate_for_date raised for {date_iso}: {exc}\n{traceback.format_exc()}")
            return jsonify({"error": f"Generation error: {str(exc)[:200]}"}), 500

        if gen_result.get("error"):
            print(f"[ECON API] generate_for_date returned error for {date_iso}: {gen_result['error']}")
            return jsonify({"error": gen_result["error"]}), 500

        # ── Read back what was written ─────────────────────────────────────
        try:
            saved = get_daily_brief(DB_PATH, date_iso)
        except Exception as exc:
            print(f"[ECON API] get_daily_brief after generation failed for {date_iso}: {exc}")
            return jsonify({"error": "Brief generated but could not be read back"}), 500

        if not saved:
            return jsonify({"error": "Brief generation completed but no row found in DB"}), 500

        theory_text = saved.get("theory_text", "").strip()
        dynamics_text = saved.get("dynamics_text", "").strip()

        print(f"[ECON API] Brief generation SUCCESS for date_key={date_iso}: theory_len={len(theory_text)}, dynamics_len={len(dynamics_text)}")
        return jsonify({
            "date_iso": date_iso,
            "theory_text": theory_text,
            "dynamics_text": dynamics_text,
            "source": "generated",
        }), 200

    finally:
        date_lock.release()


############################
# 8) SUMMARY VIEW CALLBACKS
############################

@app.callback(
    Output("url", "pathname"),
    Input("files-table", "active_cell"),
    State("files-table", "data"),
    prevent_initial_call=True
)
def navigate_to_summary(active_cell, table_data):
    """Navigate to summary view when table row is clicked."""
    if not active_cell or not table_data:
        raise PreventUpdate
    
    row_index = active_cell.get('row')
    if row_index is None or row_index >= len(table_data):
        raise PreventUpdate
    
    row = table_data[row_index]
    basename = row.get('basename')
    
    if not basename:
        raise PreventUpdate
    
    # Navigate to /summary/<basename>
    return f"/summary/{basename}"


def render_summary_components(basename: str):
    """
    Render Dash components for a given article's web summary.
    
    Args:
        basename: The article basename (filename without path)
        
    Returns:
        Dash component(s) representing the rendered summary
    """
    if not SUMMARY_VIEW_AVAILABLE:
        return html.Div("Summary view not available", style={"padding": "40px", "textAlign": "center"})
    
    # Load summary JSON
    sum_json = load_summary_json(
        basename,
        Path(FILES_DIR),
        path_manager=PATH_MANAGER if PATH_MANAGER_AVAILABLE else None
    )
    
    if sum_json is None:
        # Summary not found
        return html.Div([
            html.H2("Summary Not Found", style={"color": "#dc3545", "textAlign": "center"}),
            html.P(f"Could not load summary for: {basename}", style={"textAlign": "center"}),
            dcc.Link('← Back to Articles', href='/', style={
                'display': 'inline-block',
                'padding': '10px 20px',
                'backgroundColor': '#007bff',
                'color': 'white',
                'textDecoration': 'none',
                'borderRadius': '4px',
                'marginTop': '20px'
            })
        ], style={"padding": "40px", "textAlign": "center"})
    
    # Check if stub/failed
    if is_stub_summary(sum_json):
        return render_failed_summary(sum_json, basename)
    else:
        return render_summary_view(basename, sum_json)


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
    """Route between table view and summary view based on URL."""
    if not pathname or pathname == "/":
        # Show table view
        return (
            {"display": "block"},  # table-view
            {"display": "none"},   # summary-view
            []                     # summary content
        )
    
    # Check if summary view
    if pathname.startswith("/summary/"):
        basename = pathname.replace("/summary/", "")
        content = render_summary_components(basename)
        
        return (
            {"display": "none"},   # table-view
            {"display": "block"},  # summary-view
            content
        )
    
    # Unknown route - show table
    return (
        {"display": "block"},
        {"display": "none"},
        []
    )


############################
# 8) ECONOMIC CALENDAR CALLBACKS
############################

# ── Dynamics-mode toggle → persist to store ───────────────────────────────────
@app.callback(
    Output("econ-dynamics-mode", "data"),
    Input("econ-dynamics-toggle", "value"),
    prevent_initial_call=True,
)
def update_dynamics_mode(admin_value):
    """Sync RadioItems value to session store from Economic Calendar toggle."""
    return admin_value


# ── On-demand Theory explainer ────────────────────────────────────────────────
@app.callback(
    [
        Output({"type": "econ-theory-content", "index": dash.dependencies.MATCH}, "children"),
        Output({"type": "econ-theory-content", "index": dash.dependencies.MATCH}, "style"),
        Output({"type": "econ-expand-theory", "index": dash.dependencies.MATCH}, "children"),
    ],
    Input({"type": "econ-expand-theory", "index": dash.dependencies.MATCH}, "n_clicks"),
    [
        State({"type": "econ-theory-content", "index": dash.dependencies.MATCH}, "style"),
        State({"type": "econ-rollup-ctx", "index": dash.dependencies.ALL}, "data"),
    ],
    prevent_initial_call=True,
)
def fetch_theory_explainer(n_clicks, current_style, all_ctx_data):
    """Generate Theory blurb on first click; toggle visibility on subsequent clicks."""
    if not n_clicks:
        raise PreventUpdate

    is_visible = (current_style or {}).get("display") != "none"
    
    # Odd clicks = hide, even clicks = show (since content starts visible)
    # But first click should load content, not hide
    # Use n_clicks to determine: first click (n_clicks=1) loads, subsequent toggle
    if n_clicks > 1:
        # Toggle visibility after first load
        if is_visible:
            return dash.no_update, {"paddingLeft": "14px", "display": "none"}, "▶ Theory"
        else:
            return dash.no_update, {"paddingLeft": "14px", "display": "block"}, "▼ Theory"

    # Find rollup context (first non-None entry matching this panel's date)
    ctx_data = next((d for d in all_ctx_data if d), None)
    evt_id = ctx.triggered_id["index"] if ctx.triggered_id else None

    if not ECON_CALENDAR_AVAILABLE or not evt_id:
        content = _econ_blurb_unavailable()
        return content, {"paddingLeft": "14px", "display": "block"}, "▼ Theory"

    # Look up the event row from DB
    try:
        conn = __import__("econ_calendar_db").get_connection(DB_PATH)
        row = conn.execute(
            "SELECT id, title, country_or_region, currency_tag, event_date FROM econ_event WHERE id = ?",
            (evt_id,),
        ).fetchone()
        conn.close()
    except Exception as exc:
        print(f"[ECON] DB read failed for event {evt_id}: {exc}")
        return _econ_db_error_banner(exc), {"paddingLeft": "14px", "display": "block"}, "▼ Theory"

    if not row:
        return _econ_blurb_unavailable(), {"paddingLeft": "14px", "display": "block"}, "▼ Theory"

    evt = dict(row)
    as_of_date = evt.get("event_date", datetime.date.today().isoformat())

    # Rebuild rollup_json shell from stored context text for context_hash
    rollup_json_shell = None
    if ctx_data:
        rollup_json_shell = {"_ctx": ctx_data}  # analysis module uses compute_context_hash which handles this

    try:
        analysis = generate_event_analysis(
            event=evt,
            as_of_date=as_of_date,
            rollup_json=rollup_json_shell,
            db_path=DB_PATH,
            theory_only=True,
        )
        text = analysis.get("theory_text", "Analysis unavailable.")
    except Exception as exc:
        print(f"[ECON] Theory generation failed for {evt_id}: {exc}")
        text = f"Generation error: {exc}"

    content = _econ_blurb_lines(text)
    return content, {"paddingLeft": "14px", "display": "block"}, "▼ Theory"


# ── On-demand Dynamics explainer ──────────────────────────────────────────────
@app.callback(
    [
        Output({"type": "econ-dynamics-content", "index": dash.dependencies.MATCH}, "children"),
        Output({"type": "econ-dynamics-content", "index": dash.dependencies.MATCH}, "style"),
        Output({"type": "econ-expand-dynamics", "index": dash.dependencies.MATCH}, "children"),
    ],
    Input({"type": "econ-expand-dynamics", "index": dash.dependencies.MATCH}, "n_clicks"),
    [
        State({"type": "econ-dynamics-content", "index": dash.dependencies.MATCH}, "style"),
        State({"type": "econ-rollup-ctx", "index": dash.dependencies.ALL}, "data"),
        State("econ-dynamics-mode", "data"),
    ],
    prevent_initial_call=True,
)
def fetch_dynamics_explainer(n_clicks, current_style, all_ctx_data, dynamics_on):
    """Generate Dynamics blurb on first click; toggle visibility on subsequent clicks."""
    if not n_clicks:
        raise PreventUpdate

    if not dynamics_on:
        # Dynamics mode is off – show a brief note instead
        note = html.P(
            "Dynamics mode is currently off. Enable it in the Daily View sidebar or Economic Calendar admin tab.",
            style={"fontSize": "12px", "color": "#6c757d", "fontStyle": "italic", "paddingLeft": "14px"},
        )
        return note, {"display": "block"}, "▼ Dynamics"

    is_visible = (current_style or {}).get("display") != "none"
    
    # First click (n_clicks=1) loads content, subsequent clicks toggle visibility
    if n_clicks > 1:
        if is_visible:
            return dash.no_update, {"paddingLeft": "14px", "display": "none"}, "▶ Dynamics"
        else:
            return dash.no_update, {"paddingLeft": "14px", "display": "block"}, "▼ Dynamics"

    ctx_data = next((d for d in all_ctx_data if d), None)
    evt_id = ctx.triggered_id["index"] if ctx.triggered_id else None

    if not ECON_CALENDAR_AVAILABLE or not evt_id:
        content = _econ_blurb_unavailable()
        return content, {"paddingLeft": "14px", "display": "block"}, "▼ Dynamics"

    try:
        conn = __import__("econ_calendar_db").get_connection(DB_PATH)
        row = conn.execute(
            "SELECT id, title, country_or_region, currency_tag, event_date FROM econ_event WHERE id = ?",
            (evt_id,),
        ).fetchone()
        conn.close()
    except Exception as exc:
        print(f"[ECON] DB read failed for event {evt_id}: {exc}")
        return _econ_db_error_banner(exc), {"paddingLeft": "14px", "display": "block"}, "▼ Dynamics"

    if not row:
        return _econ_blurb_unavailable(), {"paddingLeft": "14px", "display": "block"}, "▼ Dynamics"

    evt = dict(row)
    as_of_date = evt.get("event_date", datetime.date.today().isoformat())
    rollup_json_shell = {"_ctx": ctx_data} if ctx_data else None

    try:
        analysis = generate_event_analysis(
            event=evt,
            as_of_date=as_of_date,
            rollup_json=rollup_json_shell,
            db_path=DB_PATH,
            theory_only=False,
        )
        text = analysis.get("dynamics_text", "Analysis unavailable.")
        no_ctx = analysis.get("no_context", False)
    except Exception as exc:
        print(f"[ECON] Dynamics generation failed for {evt_id}: {exc}")
        text = f"Generation error: {exc}"
        no_ctx = False

    content_parts = _econ_blurb_lines(text)
    if no_ctx:
        content_parts = [
            html.P(
                "ℹ️ No current rollup context available; dynamics are theory-based only.",
                style={"fontSize": "11px", "color": "#856404", "marginBottom": "4px", "fontStyle": "italic"},
            )
        ] + content_parts

    return content_parts, {"paddingLeft": "14px", "display": "block"}, "▼ Dynamics"


def _econ_blurb_lines(text: str) -> list:
    """Convert multi-line blurb text to a list of Dash P elements."""
    return [
        html.P(line, style={"margin": "2px 0", "fontSize": "13px", "lineHeight": "1.5"})
        for line in text.splitlines()
        if line.strip()
    ] or [html.P("No content generated.", style={"fontSize": "13px", "color": "#666"})]


def _econ_blurb_unavailable() -> html.P:
    """Fallback component when analysis cannot be retrieved."""
    return html.P(
        "Analysis unavailable.",
        style={"fontSize": "13px", "color": "#6c757d", "fontStyle": "italic"},
    )


# ── Generate Brief button — clientside fetch → store ──────────────────────────
#
# Flow:
#   1. User clicks "Generate Brief" button.
#   2. Clientside callback fires immediately, sets button to "Generating…"
#      and calls POST /api/econ/generate-brief with the date and login-user.
#   3. On success the API returns { theory_text, dynamics_text }.
#      The clientside callback writes { date, theory_text, dynamics_text }
#      into the hidden dcc.Store("econ-brief-result-store").
#   4. A server-side callback reads the store and replaces the entire
#      econ-brief-status div with the rendered brief text inline.
#      No page refresh required.
#
# Why clientside for the fetch?
#   Dash server-side callbacks cannot call external HTTP endpoints without
#   blocking the Dash worker thread for the full LLM round-trip (~5-30 s).
#   A clientside callback runs in the browser and uses the native fetch API,
#   so the Dash server stays free while the LLM call is in flight.
# ─────────────────────────────────────────────────────────────────────────────

app.clientside_callback(
    """
    async function(n_clicks, login_user) {
        if (!n_clicks) return window.dash_clientside.no_update;

        // Extract date from the triggered button's id
        const triggered = dash_clientside.callback_context.triggered;
        if (!triggered || triggered.length === 0) return window.dash_clientside.no_update;

        let btnId;
        try { btnId = JSON.parse(triggered[0].prop_id.split('.')[0]); }
        catch(e) { return {error: 'Invalid button id'}; }

        const dateIso = btnId.date;
        if (!dateIso) return {error: 'No date in button id'};

        // Disable the button during generation (cosmetic only — no Dash output needed)
        const btnEl = document.querySelector(
            '[id*=\'"type":"econ-gen-brief-btn"\'][id*=\'"date":"' + dateIso + '"\']'
        );
        if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Generating…'; }

        try {
            const resp = await fetch('/api/econ/generate-brief', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Login-User': login_user || ''
                },
                body: JSON.stringify({ date_iso: dateIso, dynamics_mode: true })
            });
            const data = await resp.json();

            if (!resp.ok) {
                return { date: dateIso, error: data.error || ('HTTP ' + resp.status) };
            }
            return {
                date: dateIso,
                theory_text: data.theory_text || '',
                dynamics_text: data.dynamics_text || '',
                source: data.source || 'generated'
            };
        } catch(err) {
            return { date: dateIso, error: String(err) };
        } finally {
            if (btnEl) { btnEl.disabled = false; btnEl.textContent = 'Generate Brief'; }
        }
    }
    """,
    Output("econ-brief-result-store", "data"),
    Input({"type": "econ-gen-brief-btn", "date": dash.dependencies.ALL}, "n_clicks"),
    State("login-user", "data"),
    prevent_initial_call=True,
)


@app.callback(
    Output({"type": "econ-brief-status", "date": dash.dependencies.ALL}, "children"),
    Input("econ-brief-result-store", "data"),
    State({"type": "econ-brief-status", "date": dash.dependencies.ALL}, "id"),
    prevent_initial_call=True,
)
def render_generated_brief(result_data, status_ids):
    """
    Receive the brief returned by the API (via the clientside fetch) and
    replace the 'Summary pending' placeholder with the actual brief text.
    Only the matching date's div is updated; all others get no_update.
    """
    if not result_data:
        raise PreventUpdate

    target_date = result_data.get("date")
    if not target_date:
        raise PreventUpdate

    outputs = []
    for sid in (status_ids or []):
        sid_date = sid.get("date") if isinstance(sid, dict) else None
        if sid_date != target_date:
            outputs.append(dash.no_update)
            continue

        # Error path
        if result_data.get("error"):
            err_msg = result_data["error"]
            print(f"[ECON GEN] Clientside fetch returned error for date_key={target_date}: {err_msg}")
            outputs.append(
                html.Span(
                    f"Generation failed: {err_msg[:120]}",
                    style={"fontSize": "11px", "color": "#dc3545"},
                )
            )
            continue

        theory_text = (result_data.get("theory_text") or "").strip()
        dynamics_text = (result_data.get("dynamics_text") or "").strip()
        source = result_data.get("source", "generated")
        print(f"[ECON GEN] Rendering inline brief for date_key={target_date}: theory_len={len(theory_text)}, source={source}")

        if not theory_text:
            outputs.append(
                html.Span(
                    "Generation returned empty brief. Try again.",
                    style={"fontSize": "11px", "color": "#856404"},
                )
            )
            continue

        # Render the brief inline — same style as _render_econ_daily_brief
        theory_lines = [
            html.P(line, style={"margin": "2px 0", "fontSize": "13px", "lineHeight": "1.55"})
            for line in theory_text.splitlines()
            if line.strip()
        ]
        brief_block = html.Div(
            [
                html.Hr(style={"margin": "16px 0", "border": "none", "borderTop": "1px solid #e0e7ef"}),
                html.H3(
                    "Summary:",
                    style={"fontSize": "17px", "color": "#004080", "marginBottom": "10px"},
                ),
                html.Div(
                    theory_lines,
                    style={
                        "backgroundColor": "#f8f9fa",
                        "padding": "12px 16px",
                        "borderRadius": "4px",
                        "marginBottom": "6px",
                        "borderLeft": "4px solid #004080",
                    },
                ),
            ]
        )
        outputs.append(brief_block)

    return outputs


# ── Admin parse callback ───────────────────────────────────────────────────────
@app.callback(
    [
        Output("econ-status", "children"),
        Output("econ-save-btn", "disabled"),
    ],
    Input("econ-parse-btn", "n_clicks"),
    State("econ-textarea", "value"),
    prevent_initial_call=True
)
def parse_economic_calendar(n_clicks, raw_text):
    """Parse pasted economic calendar text (simplified - no big preview)."""
    if not ECON_CALENDAR_AVAILABLE:
        return (
            html.Div("Economic calendar module not available", 
                    style={"color": "#dc3545", "padding": "10px", "backgroundColor": "#f8d7da", "borderRadius": "4px"}),
            True
        )
    
    if not raw_text or not raw_text.strip():
        return (
            html.Div("Please paste calendar text", 
                    style={"color": "#856404", "padding": "10px", "backgroundColor": "#fff3cd", "borderRadius": "4px"}),
            True
        )
    
    try:
        parsed = parse_week_block(raw_text)
        
        # Success message (minimal)
        status = html.Div([
            html.Span("✓ ", style={"fontSize": "18px"}),
            html.Span(f"Parsed successfully: {parsed.week_start_date} to {parsed.week_end_date}"),
            html.Span(f" ({len(parsed.events)} events)", style={"color": "#666"}),
            html.Br(),
            html.Span("Ready to save.", style={"fontSize": "13px", "color": "#666", "marginTop": "4px"})
        ], style={"color": "#155724", "padding": "10px", "backgroundColor": "#d4edda", "borderRadius": "4px"})
        
        return status, False  # Enable save button
        
    except ValueError as e:
        error_msg = str(e)
        return (
            html.Div([
                html.Span("✗ ", style={"fontSize": "18px"}),
                html.Span("Parse error: ", style={"fontWeight": "bold"}),
                html.Span(error_msg)
            ], style={"color": "#721c24", "padding": "10px", "backgroundColor": "#f8d7da", "borderRadius": "4px"}),
            True
        )


@app.callback(
    [
        Output("econ-status", "children", allow_duplicate=True),
        Output("econ-gen-job-store", "data"),
        Output("econ-gen-interval", "disabled"),
        Output("econ-gen-progress", "children"),
    ],
    Input("econ-save-btn", "n_clicks"),
    [
        State("econ-textarea", "value"),
        State("econ-dynamics-toggle", "value"),
    ],
    prevent_initial_call=True,
)
def save_economic_calendar(n_clicks, raw_text, dynamics_mode):
    """
    Save parsed economic calendar to the DB, then pre-generate ranked event
    lists and daily briefs for every date in the week via the AI pipeline.

    Step 1: Parse + upsert week and events (synchronous, fast).
    Step 2: Collect unique event dates and launch sequential AI generation
            across all dates (Steps A, B, C per date). Progress is polled
            via dcc.Interval so the UI updates without freezing.
    """
    _no_op = (dash.no_update, dash.no_update, dash.no_update, dash.no_update)

    if not ECON_CALENDAR_AVAILABLE or not raw_text or not raw_text.strip():
        return (
            html.Div(
                "No data to save",
                style={"color": "#856404", "padding": "10px",
                       "backgroundColor": "#fff3cd", "borderRadius": "4px"},
            ),
            None, True, [],
        )

    # ── Step 1: Parse + DB upsert ──────────────────────────────────────────
    try:
        parsed = parse_week_block(raw_text)
        print(f"[ECON] Parsed week: {parsed.week_start_date} to {parsed.week_end_date}, {len(parsed.events)} events")
        
        # Add retry logic for database locking
        max_retries = 3
        retry_delay = 0.5
        for attempt in range(max_retries):
            try:
                upsert_week_and_events(
                    DB_PATH,
                    parsed.week_start_date,
                    parsed.week_end_date,
                    raw_text,
                    parsed.events,
                )
                print(f"[ECON] Successfully saved week to database")
                break
            except Exception as db_exc:
                err_str = str(db_exc).lower()
                if "locked" in err_str and attempt < max_retries - 1:
                    print(f"[ECON] Database locked, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    raise  # Re-raise if not a locking issue or out of retries
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        print(f"[ECON] Save error: {exc}\n{tb}")
        err_msg = str(exc)
        if "locked" in err_msg.lower():
            hint = " The database appears locked — close any other connections and retry."
        elif "unable to open" in err_msg.lower() or "no such file" in err_msg.lower():
            hint = f" Database file not found at: {DB_PATH}"
        else:
            hint = ""
        return (
            html.Div(
                [
                    html.Span("✗ ", style={"fontSize": "18px"}),
                    html.Span("Save error: ", style={"fontWeight": "bold"}),
                    html.Span(err_msg + hint),
                ],
                style={"color": "#721c24", "padding": "10px",
                       "backgroundColor": "#f8d7da", "borderRadius": "4px"},
            ),
            None, True, [],
        )

    # Collect unique event dates (sorted ascending)
    unique_dates = sorted({evt.event_date for evt in parsed.events})
    total_dates = len(unique_dates)

    print(
        f"[ECON] Save: {len(parsed.events)} events across {total_dates} dates "
        f"({parsed.week_start_date} to {parsed.week_end_date})"
    )

    # Format week label for UI (no hyphens in date display)
    try:
        s_dt = datetime.datetime.strptime(parsed.week_start_date, "%Y-%m-%d")
        e_dt = datetime.datetime.strptime(parsed.week_end_date, "%Y-%m-%d")
        week_label = f"{s_dt.strftime('%b %d %Y')} to {e_dt.strftime('%b %d %Y')}"
    except Exception:
        week_label = f"{parsed.week_start_date} to {parsed.week_end_date}"

    save_ok_msg = html.Div(
        [
            html.Span("✓ ", style={"fontSize": "16px"}),
            html.Span(f"Saved week {week_label}"),
            html.Span(f" ({len(parsed.events)} events)", style={"color": "#666"}),
        ],
        style={"color": "#155724", "padding": "8px 10px",
               "backgroundColor": "#d4edda", "borderRadius": "4px",
               "marginBottom": "6px"},
    )

    if not unique_dates:
        return save_ok_msg, None, True, []

    # Build rollups daily dir path (same FILES_DIR constant used throughout the app)
    rollups_daily_dir = Path(FILES_DIR) / "rollups" / "daily"

    # ── Step 2: Kick off sequential AI generation ──────────────────────────
    # Run generation in a background thread so Dash can return immediately.
    # Progress is tracked in the job store and polled by the interval callback.
    import threading

    job_store: dict = {
        "dates": unique_dates,
        "dynamics_mode": bool(dynamics_mode),
        "completed": 0,
        "total": total_dates,
        "results": [],
        "done": False,
        "rollups_daily_dir": str(rollups_daily_dir),
    }

    def _run_generation(store: dict) -> None:
        """Run generation for all dates and update the shared store."""
        print(f"[ECON GEN THREAD] Starting generation for {len(store['dates'])} dates")
        dates = store.get("dates", [])
        d_mode = store.get("dynamics_mode", True)
        r_dir_str = store.get("rollups_daily_dir", "")
        
        # Ensure results list exists and is initialized
        if "results" not in store:
            store["results"] = []
        if "completed" not in store:
            store["completed"] = 0
        
        try:
            r_dir = Path(r_dir_str) if r_dir_str else None
            for i, date_iso in enumerate(dates):
                print(f"[ECON GEN THREAD] Processing date {i+1}/{len(dates)}: {date_iso}")
                res = None
                try:
                    from econ_calendar_ai import generate_for_date  # noqa: PLC0415
                    print(f"[ECON GEN THREAD] Calling generate_for_date for {date_iso}...")
                    res = generate_for_date(
                        date_iso,
                        dynamics_mode=d_mode,
                        db_path=DB_PATH,
                        rollups_daily_dir=r_dir,
                    )
                    # Validate result is a dict with required keys
                    if not isinstance(res, dict):
                        print(f"[ECON GEN THREAD] WARNING: generate_for_date returned non-dict: {type(res)}")
                        res = {
                            "date_iso": date_iso,
                            "error": f"Invalid result type: {type(res).__name__}",
                            "skipped_rank": False,
                            "skipped_brief": False,
                            "events_count": 0
                        }
                    else:
                        # Ensure all required keys exist
                        if "date_iso" not in res:
                            res["date_iso"] = date_iso
                        if "error" not in res:
                            res["error"] = None
                        if "skipped_rank" not in res:
                            res["skipped_rank"] = False
                        if "skipped_brief" not in res:
                            res["skipped_brief"] = False
                        if "events_count" not in res:
                            res["events_count"] = 0
                    
                    print(f"[ECON GEN THREAD] Completed {date_iso}: {res}")
                except Exception as exc:  # noqa: BLE001
                    import traceback
                    tb = traceback.format_exc()
                    print(f"[ECON GEN THREAD] ERROR for {date_iso}: {exc}\n{tb}")
                    res = {
                        "date_iso": date_iso,
                        "error": str(exc)[:500],  # Truncate long errors
                        "skipped_rank": False,
                        "skipped_brief": False,
                        "events_count": 0
                    }
                finally:
                    # Always append result and update progress, even on error
                    # Ensure res is a valid dict before appending
                    if res is None:
                        res = {
                            "date_iso": date_iso,
                            "error": "Result was None",
                            "skipped_rank": False,
                            "skipped_brief": False,
                            "events_count": 0
                        }
                    if isinstance(res, dict):
                        store["results"].append(res)
                    else:
                        # Fallback: create a safe dict wrapper
                        print(f"[ECON GEN THREAD] WARNING: Appending non-dict result, wrapping it")
                        store["results"].append({
                            "date_iso": date_iso,
                            "error": f"Invalid result format: {type(res).__name__}",
                            "skipped_rank": False,
                            "skipped_brief": False,
                            "events_count": 0
                        })
                    store["completed"] = i + 1
                    print(f"[ECON GEN THREAD] Progress: {i+1}/{len(dates)} complete")
            store["done"] = True
            print(f"[ECON GEN THREAD] All {len(dates)} dates processed, done=True")
        except Exception as exc:  # noqa: BLE001
            # Catastrophic failure - mark all remaining dates as failed
            import traceback
            tb = traceback.format_exc()
            print(f"[ECON GEN THREAD] CATASTROPHIC ERROR: {exc}\n{tb}")
            # Mark remaining dates as failed
            completed = store.get("completed", 0)
            for i in range(completed, len(dates)):
                store["results"].append({
                    "date_iso": dates[i] if i < len(dates) else "?",
                    "error": f"Thread crashed: {str(exc)[:500]}",
                    "skipped_rank": False,
                    "skipped_brief": False,
                    "events_count": 0
                })
                store["completed"] = i + 1
            store["done"] = True
            store["thread_error"] = str(exc)[:500]

    thread = threading.Thread(target=_run_generation, args=(job_store,), daemon=True)
    thread.start()

    # Store the job object (serialisable snapshot for the Interval callback)
    # We pass a lightweight reference via the store; the thread mutates job_store in-place.
    # To make it accessible across callbacks we stash it in a module-level dict keyed by
    # the week start date (safe — only one save operation runs at a time in practice).
    _active_gen_jobs[parsed.week_start_date] = job_store

    initial_progress = html.Div(
        [
            html.Span("⚙ ", style={"fontSize": "14px"}),
            html.Span(
                f"Generating AI content: 0 of {total_dates} days...",
                style={"fontStyle": "italic", "color": "#555"},
            ),
        ],
        style={"padding": "8px 10px", "backgroundColor": "#f0f4ff",
               "borderRadius": "4px", "border": "1px solid #c3d0f0"},
    )

    # Store a JSON-serialisable snapshot for the interval callback to read
    job_snapshot = {
        "week_start": parsed.week_start_date,
        "total": total_dates,
    }

    return save_ok_msg, job_snapshot, False, initial_progress


# Module-level dict to hold in-flight generation jobs (keyed by week_start date).
# Populated by save_economic_calendar; consumed by the interval progress callback.
_active_gen_jobs: dict = {}

# ---------------------------------------------------------------------------
# Per-date brief generation lock.
# Prevents two simultaneous requests (e.g. two admin tabs) from calling the
# LLM and writing the DB twice for the same date.
#
# Structure: { date_iso (str) -> threading.Lock }
# A lock is created on first use and kept for the process lifetime.
# The lock is acquired before generation starts and released when the DB
# write (or failure) is complete.  Any second caller that finds the lock
# held will block until the first write finishes, then read the result
# that was persisted by the first caller instead of calling the LLM again.
# ---------------------------------------------------------------------------
import threading as _threading

_brief_gen_locks: dict = {}
_brief_gen_locks_meta_lock = _threading.Lock()   # guards _brief_gen_locks itself


def _get_brief_lock(date_iso: str) -> _threading.Lock:
    """Return the per-date Lock, creating it if necessary (thread-safe)."""
    with _brief_gen_locks_meta_lock:
        if date_iso not in _brief_gen_locks:
            _brief_gen_locks[date_iso] = _threading.Lock()
        return _brief_gen_locks[date_iso]


@app.callback(
    [
        Output("econ-textarea", "value"),
        Output("econ-status", "children", allow_duplicate=True),
        Output("econ-gen-progress", "children", allow_duplicate=True),
        Output("econ-gen-job-store", "data", allow_duplicate=True),
        Output("econ-gen-interval", "disabled", allow_duplicate=True),
    ],
    Input("econ-clear-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_economic_calendar(n_clicks):
    """Clear the form and cancel any in-flight generation display."""
    return "", [], [], None, True


# ── AI generation progress polling ────────────────────────────────────────────
@app.callback(
    [
        Output("econ-gen-progress", "children", allow_duplicate=True),
        Output("econ-gen-interval", "disabled", allow_duplicate=True),
        Output("econ-gen-job-store", "data", allow_duplicate=True),
    ],
    Input("econ-gen-interval", "n_intervals"),
    State("econ-gen-job-store", "data"),
    prevent_initial_call=True,
)
def poll_generation_progress(n_intervals, job_snapshot):
    """
    Poll the in-flight generation job and update the progress area.

    The interval fires every 800 ms while enabled. Once the job is done
    the interval is disabled and the job store is cleared.
    """
    if not job_snapshot:
        raise PreventUpdate

    week_start = job_snapshot.get("week_start")
    total = job_snapshot.get("total", 1)

    job = _active_gen_jobs.get(week_start)
    if job is None:
        # Job reference lost (e.g. after server restart) — stop polling
        return [], True, None

    try:
        completed = job.get("completed", 0)
        done = job.get("done", False)
        results = job.get("results", [])
        
        # Defensive: ensure results is a list
        if not isinstance(results, list):
            print(f"[ECON] WARNING: results is not a list, type={type(results)}, value={results}")
            results = []

        # Build per-date status lines with defensive dict access
        status_rows = []
        for res in results:
            try:
                # Ensure res is a dict before calling .get()
                if not isinstance(res, dict):
                    print(f"[ECON] WARNING: result item is not a dict, type={type(res)}, value={res}")
                    date_label = "?"
                    err = "Invalid result format"
                    skipped_rank = False
                    skipped_brief = False
                    n_events = 0
                else:
                    date_label = res.get("date_iso", "?")
                    err = res.get("error")
                    skipped_rank = res.get("skipped_rank", False)
                    skipped_brief = res.get("skipped_brief", False)
                    n_events = res.get("events_count", 0)

                if err:
                    icon, detail = "✗", f"error: {err}"
                    color = "#721c24"
                elif n_events == 0:
                    icon, detail = "–", "no events"
                    color = "#6c757d"
                else:
                    rank_tag = "(cached)" if skipped_rank else "(new)"
                    brief_tag = "(cached)" if skipped_brief else "(new)"
                    icon, detail = "✓", f"{n_events} events | rank {rank_tag} | brief {brief_tag}"
                    color = "#155724"

                status_rows.append(
                    html.Div(
                        f"{icon} {date_label}: {detail}",
                        style={"fontSize": "12px", "color": color, "padding": "2px 0"},
                    )
                )
            except Exception as exc:
                # Skip malformed result items and log the error
                import traceback
                print(f"[ECON] ERROR processing result item: {exc}\n{traceback.format_exc()}")
                status_rows.append(
                    html.Div(
                        f"⚠ Error displaying result: {str(exc)[:100]}",
                        style={"fontSize": "12px", "color": "#721c24", "padding": "2px 0"},
                    )
                )

        if done:
            # All dates processed — stop the interval
            errors = []
            for r in results:
                try:
                    if isinstance(r, dict) and r.get("error"):
                        errors.append(r)
                except Exception:
                    pass  # Skip malformed items
            
            thread_error = job.get("thread_error")
            summary_color = "#721c24" if (errors or thread_error) else "#155724"
            summary_bg = "#f8d7da" if (errors or thread_error) else "#d4edda"
            summary_msg = (
                f"Generation complete: {completed} of {total} days"
                + (f" ({len(errors)} errors)" if errors else "")
                + (f" [Thread error: {thread_error}]" if thread_error else "")
            )
            progress_div = html.Div(
                [
                    html.Div(
                        summary_msg,
                        style={"fontWeight": "bold", "marginBottom": "6px",
                               "fontSize": "13px", "color": summary_color},
                    ),
                    html.Div(status_rows),
                ],
                style={"padding": "10px", "backgroundColor": summary_bg,
                       "borderRadius": "4px", "border": f"1px solid {summary_color}30"},
            )
            # Clean up the job reference
            _active_gen_jobs.pop(week_start, None)
            return progress_div, True, None

        # Still running — show live progress
        progress_div = html.Div(
            [
                html.Div(
                    f"⚙ Generating AI content: {completed} of {total} days...",
                    style={"fontWeight": "bold", "marginBottom": "6px",
                           "fontSize": "13px", "color": "#004080"},
                ),
                html.Div(status_rows),
            ],
            style={"padding": "10px", "backgroundColor": "#f0f4ff",
                   "borderRadius": "4px", "border": "1px solid #c3d0f0"},
        )
        return progress_div, False, job_snapshot
    except Exception as exc:
        # Catastrophic error in progress polling — log and return safe fallback
        import traceback
        print(f"[ECON] CATASTROPHIC ERROR in poll_generation_progress: {exc}\n{traceback.format_exc()}")
        error_div = html.Div(
            [
                html.Div(
                    f"⚠ Progress display error: {str(exc)[:200]}",
                    style={"fontWeight": "bold", "marginBottom": "6px",
                           "fontSize": "13px", "color": "#721c24"},
                ),
                html.Div(
                    "Check server logs for details. Generation may still be running.",
                    style={"fontSize": "12px", "color": "#666"},
                ),
            ],
            style={"padding": "10px", "backgroundColor": "#f8d7da",
                   "borderRadius": "4px", "border": "1px solid #721c24"},
        )
        # Don't stop polling if job is not done — let it retry
        done = job.get("done", False)
        return error_div, done, (None if done else job_snapshot)


@app.callback(
    [
        Output("econ-weeks-list", "children"),
        Output("econ-db-health-banner", "children"),
    ],
    [
        Input("main-tabs", "value"),
        Input({"type": "econ-delete-week", "index": dash.dependencies.ALL}, "n_clicks"),
    ],
    prevent_initial_call=False
)
def load_recent_weeks(tab_value, delete_clicks_list):
    """Load recently imported weeks and DB health status when tab is opened."""
    if tab_value != "econ-calendar" or not ECON_CALENDAR_AVAILABLE:
        return [], []

    # ── Handle delete button clicks ───────────────────────────────────────
    if ctx.triggered and isinstance(ctx.triggered_id, dict) and ctx.triggered_id.get("type") == "econ-delete-week":
        week_id = ctx.triggered_id.get("index")
        if week_id and delete_week is not None:
            try:
                delete_week(DB_PATH, week_id)
            except Exception as exc:
                # Continue to reload list even if delete fails
                print(f"[ECON] Failed to delete week {week_id}: {exc}")

    # ── DB health check ───────────────────────────────────────────────────
    db_banner = []
    try:
        import econ_calendar_db as _ecdb
        conn = _ecdb.get_connection(DB_PATH)
        conn.execute("SELECT 1 FROM econ_week LIMIT 1")
        conn.close()
        # Healthy – no banner
    except Exception as exc:
        db_banner = _econ_db_error_banner(exc)
        return [html.Div("Cannot display weeks — database unavailable.",
                         style={"color": "#6c757d", "fontStyle": "italic"})], db_banner

    # ── Load weeks ────────────────────────────────────────────────────────
    try:
        from_date = (datetime.date.today() - datetime.timedelta(days=180)).isoformat()
        to_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
        weeks = get_weeks_in_range(DB_PATH, from_date, to_date)

        if not weeks:
            return [html.Div("No weeks imported yet",
                             style={"color": "#666", "fontStyle": "italic"})], []

        weeks = sorted(weeks, key=lambda w: w["week_start_date"], reverse=True)[:10]

        week_cards = []
        for week in weeks:
            week_cards.append(
                html.Div([
                    html.Div([
                        html.Span(
                            f"{week['week_start_date']} to {week['week_end_date']}",
                            style={"fontWeight": "bold", "fontSize": "14px"}
                        ),
                        html.Span(
                            f" (imported {week['created_at'][:10]})",
                            style={"color": "#666", "fontSize": "12px", "marginLeft": "10px"}
                        ),
                    ], style={"marginBottom": "8px"}),
                    html.Div([
                        html.Button(
                            "Load for Editing",
                            id={"type": "econ-load-week", "index": week["id"]},
                            className="btn btn-sm btn-outline-primary",
                            n_clicks=0,
                            style={"marginRight": "8px"}
                        ),
                        html.Button(
                            "Delete",
                            id={"type": "econ-delete-week", "index": week["id"]},
                            className="btn btn-sm btn-outline-danger",
                            n_clicks=0
                        )
                    ], style={"display": "flex", "alignItems": "center"})
                ], style={
                    "padding": "12px",
                    "marginBottom": "10px",
                    "backgroundColor": "#f8f9fa",
                    "borderRadius": "4px",
                    "border": "1px solid #dee2e6"
                })
            )

        return week_cards, []

    except Exception as exc:
        return [_econ_db_error_banner(exc)], []


@app.callback(
    Output("econ-textarea", "value", allow_duplicate=True),
    Input({"type": "econ-load-week", "index": dash.dependencies.ALL}, "n_clicks"),
    prevent_initial_call=True
)
def load_week_for_editing(n_clicks_list):
    """Load a week's raw text into the textarea."""
    if not ctx.triggered or not ECON_CALENDAR_AVAILABLE:
        raise PreventUpdate
    
    triggered_id = ctx.triggered_id
    if not triggered_id or triggered_id.get("type") != "econ-load-week":
        raise PreventUpdate
    
    week_id = triggered_id.get("index")
    if not week_id:
        raise PreventUpdate
    
    try:
        raw_text = get_week_raw_text(DB_PATH, week_id)
        return raw_text if raw_text else ""
    except Exception:
        raise PreventUpdate


############################
# 9) DAILY VIEW CALLBACKS
############################

@app.callback(
    Output("daily-view-date-input", "value"),
    [
        Input("daily-view-date-prev", "n_clicks"),
        Input("daily-view-date-next", "n_clicks")
    ],
    State("daily-view-date-input", "value"),
    prevent_initial_call=True
)
def navigate_daily_date(prev_clicks, next_clicks, current_date):
    """
    Handle date navigation arrows (previous/next day).
    Uses proper date arithmetic to handle month/year boundaries.
    """
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    # Parse current date (default to yesterday if invalid)
    try:
        if current_date and current_date.strip():
            date_obj = datetime.datetime.strptime(current_date.strip(), "%Y-%m-%d").date()
        else:
            date_obj = datetime.date.today() - datetime.timedelta(days=1)
    except (ValueError, TypeError):
        date_obj = datetime.date.today() - datetime.timedelta(days=1)
    
    # Navigate based on which arrow was clicked
    if trigger_id == "daily-view-date-prev":
        date_obj -= datetime.timedelta(days=1)
    elif trigger_id == "daily-view-date-next":
        date_obj += datetime.timedelta(days=1)
    
    return date_obj.isoformat()


@app.callback(
    [
        Output("daily-articles-store", "data"),
        Output("daily-view-article-list", "children")
    ],
    [
        Input("login-status", "data"),
        Input("main-tabs", "value"),
        Input("daily-view-date-ok", "n_clicks")
    ],
    State("daily-view-date-input", "value"),
    prevent_initial_call=False
)
def populate_daily_view_sidebar(login_status, active_tab, n_clicks, date_input):
    """
    Populate the Daily View sidebar from artifact folders for the selected date.

    Only calls get_artifacts_for_date() when the user is logged in
    AND the active tab is 'daily-view'.
    """
    if not DAILY_VIEW_AVAILABLE:
        return [], [
            html.P(
                "Daily view not available",
                style={"color": "#999", "fontStyle": "italic"}
            )
        ]

    if not login_status or active_tab != "daily-view":
        return [], []

    # Parse date input (YYYY-MM-DD format)
    # Default to yesterday if empty or invalid
    if date_input and date_input.strip():
        try:
            target_date = datetime.datetime.strptime(date_input.strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            target_date = datetime.date.today() - datetime.timedelta(days=1)
    else:
        target_date = datetime.date.today() - datetime.timedelta(days=1)

    try:
        artifacts = get_artifacts_for_date(target_date)
    except Exception as e:
        print(f"[ERROR] get_artifacts_for_date failed: {e}")
        return [], [
            html.P(
                f"Error loading artifacts: {e}",
                style={"color": "#dc3545"}
            )
        ]

    if not artifacts:
        return [], [
            html.P(
                f"No articles found for {target_date.strftime('%B %d, %Y')}.",
                style={
                    "color": "#999",
                    "fontStyle": "italic",
                    "padding": "20px",
                    "textAlign": "center"
                }
            )
        ]

    # --- build sidebar buttons keyed by artifact_folder ---
    # Format the date for the summary title
    day = target_date.day
    suffix = "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    date_label = f"{target_date.strftime('%B')} {day}{suffix}"
    summary_title = f"Summary for {date_label} & Prep for Today"
    sidebar_buttons = [
        html.Button(
            [
                html.Div(
                    summary_title,
                    style={"fontWeight": "bold", "marginBottom": "3px"}
                ),
                html.Div(
                    f"{len(artifacts)} articles",
                    style={"fontSize": "11px", "color": "#666"}
                )
            ],
            id={"type": "daily-article-btn", "index": "__daily_summary__"},
            n_clicks=0,
            style={
                "width": "100%",
                "padding": "12px",
                "marginBottom": "10px",
                "backgroundColor": "#e3f2fd",
                "border": "1px solid #90caf9",
                "borderRadius": "6px",
                "cursor": "pointer",
                "textAlign": "left",
                "transition": "all 0.2s"
            },
            className="daily-article-button"
        ),
        html.Hr(
            style={
                "margin": "15px 0",
                "border": "none",
                "borderTop": "1px solid #ddd"
            }
        )
    ]

    # Debug counter
    debug_count = 0
    
    # Frequency mapping for display
    frequency_map = {
        'w': 'Weekly',
        'd': 'Daily',
        'm': 'Monthly',
        'q': 'Quarterly',
        'y': 'Yearly',
        'u': 'Unknown'
    }
    
    for art in artifacts:
        # Extract products and warnings from sum.json if available
        products_display = ""
        has_warnings = False
        if art["has_sum_json"]:
            try:
                with open(art["sum_json_path"], "r", encoding="utf-8") as fh:
                    sum_data = json.load(fh)
                    products = sum_data.get("meta", {}).get("products", [])
                    if products:
                        products_display = ", ".join(products) if isinstance(products, list) else str(products)
                    warnings = sum_data.get("sections", {}).get("warnings", []) or []
                    has_warnings = bool(warnings) and (isinstance(warnings, list) and len(warnings) > 0)
            except Exception:
                pass  # leave blank if can't access

        # Get firm name and clean title using shared resolver
        firm_name = art["provider"]
        
        # Use shared resolve_display_title for consistency across all views
        title_cleaned = resolve_display_title(art["artifact_folder"], meta_title=art.get("title"))
        
        # Get frequency display
        frequency_code = art.get("frequency_code", "u")
        frequency_display = frequency_map.get(frequency_code, "Unknown")

        # Debug first 3 articles
        if debug_count < 3:
            print(f"\n[DAILY VIEW DEBUG] Article {debug_count + 1}:")
            print(f"  artifact_folder: {art['artifact_folder']}")
            print(f"  firm_name: {firm_name}")
            print(f"  title_cleaned: {title_cleaned}")
            print(f"  frequency: {frequency_display} ({frequency_code})")
            print(f"  products: {products_display}")
            debug_count += 1

        sidebar_buttons.append(
            html.Button(
                [
                    # Line 1: Firm name (blue badge) + Frequency (green badge) + warning indicator if present
                    html.Div(
                        [
                            html.Span(
                                firm_name,
                                style={
                                    "display": "inline-block",
                                    "fontSize": "11px",
                                    "color": "#004080",
                                    "fontWeight": "bold",
                                    "backgroundColor": "#e3f2fd",
                                    "padding": "2px 8px",
                                    "borderRadius": "8px",
                                    "marginRight": "8px"
                                }
                            ),
                            html.Span(
                                frequency_display,
                                style={
                                    "display": "inline-block",
                                    "fontSize": "11px",
                                    "color": "white",
                                    "fontWeight": "500",
                                    "backgroundColor": "#28a745",
                                    "padding": "2px 8px",
                                    "borderRadius": "8px",
                                    "marginRight": "8px" if has_warnings else None
                                }
                            ),
                            html.Span(
                                "⚠️",
                                style={
                                    "display": "inline-block",
                                    "fontSize": "14px",
                                    "lineHeight": "1"
                                }
                            ) if has_warnings else html.Span()
                        ],
                        style={
                            "marginBottom": "4px",
                            "display": "flex",
                            "alignItems": "center"
                        }
                    ),
                    # Line 2: Article title
                    html.Div(
                        title_cleaned,
                        style={
                            "fontSize": "13px",
                            "lineHeight": "1.3",
                            "fontWeight": "500",
                            "marginBottom": "3px",
                            "overflow": "hidden",
                            "textOverflow": "ellipsis",
                            "display": "-webkit-box",
                            "WebkitLineClamp": "2",
                            "WebkitBoxOrient": "vertical"
                        }
                    ),
                    # Line 3: Products (turquoise pill, same as article view on the right)
                    html.Div(
                        products_display,
                        style={
                            "display": "inline-block",
                            "fontSize": "11px",
                            "color": "white",
                            "fontWeight": "500",
                            "backgroundColor": "#17a2b8",
                            "padding": "2px 8px",
                            "borderRadius": "8px",
                            "lineHeight": "1.2",
                            "overflow": "hidden",
                            "textOverflow": "ellipsis",
                            "whiteSpace": "nowrap"
                        }
                    ) if products_display else html.Div()
                ],
                id={
                    "type": "daily-article-btn",
                    "index": art["artifact_folder"]
                },
                n_clicks=0,
                style={
                    "width": "100%",
                    "padding": "10px",
                    "marginBottom": "8px",
                    "backgroundColor": "#fff",
                    "border": "1px solid #ddd",
                    "borderRadius": "4px",
                    "cursor": "pointer",
                    "textAlign": "left",
                    "transition": "all 0.2s"
                },
                className="daily-article-button"
            )
        )

    return artifacts, sidebar_buttons


def _render_web_bullet(item: dict, base_style: dict = None) -> list:
    """Build Dash components for a bullet with optional [EQUITY] badge and ai_context.

    Args:
        item: Bullet dict with text, ai_context (optional), sources.
        base_style: Override style for the Li element.

    Returns:
        List of Dash components (Li + optional P for ai_context).
    """
    import re as _re
    text = item.get("text", str(item)) if isinstance(item, dict) else str(item)
    ai_context = item.get("ai_context", "") if isinstance(item, dict) else ""
    li_style = base_style or {"marginBottom": "6px", "lineHeight": "1.4", "fontSize": "14px"}

    parts: list = []

    eq_match = _re.match(r"\[EQUITY:\s*([A-Z.]+)\]\s*", text)
    if eq_match:
        ticker = eq_match.group(1)
        text = text[eq_match.end():]
        parts.append(html.Span(
            f"EQUITY: {ticker}",
            style={
                "display": "inline-block",
                "padding": "1px 6px",
                "borderRadius": "3px",
                "fontSize": "10px",
                "fontWeight": "600",
                "backgroundColor": "#E8DAEF",
                "color": "#6C3483",
                "marginRight": "6px",
                "verticalAlign": "middle",
            }
        ))

    parts.append(html.Span(text))
    elements = [html.Li(parts, style=li_style)]

    if ai_context:
        elements.append(html.P(
            ai_context,
            style={
                "fontSize": "13px",
                "fontStyle": "italic",
                "color": "#5A6A7A",
                "marginLeft": "12px",
                "marginTop": "2px",
                "marginBottom": "8px",
                "lineHeight": "1.4",
            }
        ))

    return elements


# ─────────────────────────────────────────────────────────────────────────────
# DAILY RECAP LAYOUT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

# Inline tag colours per asset class
_TAG_COLORS: dict = {
    "EQUITIES":    {"bg": "#E8DAEF", "fg": "#6C3483"},
    "RATES":       {"bg": "#D6EAF8", "fg": "#1A5276"},
    "COMMODITIES": {"bg": "#FDEBD0", "fg": "#784212"},
    "FX":          {"bg": "#D5F5E3", "fg": "#1E8449"},
    "VOLATILITY":  {"bg": "#FDEDEC", "fg": "#922B21"},
    "CRYPTO":      {"bg": "#EBF5FB", "fg": "#1F618D"},
    "CREDIT":      {"bg": "#F9EBEA", "fg": "#78281F"},
    "GENERAL":     {"bg": "#F2F3F4", "fg": "#566573"},
}

_COUNTRY_FLAGS: dict = {
    "US": "🇺🇸", "USA": "🇺🇸", "United States": "🇺🇸",
    "EU": "🇪🇺", "Euro Area": "🇪🇺", "Eurozone": "🇪🇺",
    "UK": "🇬🇧", "United Kingdom": "🇬🇧",
    "JP": "🇯🇵", "Japan": "🇯🇵",
    "CN": "🇨🇳", "China": "🇨🇳",
    "DE": "🇩🇪", "Germany": "🇩🇪",
    "FR": "🇫🇷", "France": "🇫🇷",
    "CA": "🇨🇦", "Canada": "🇨🇦",
    "AU": "🇦🇺", "Australia": "🇦🇺",
    "NZ": "🇳🇿", "New Zealand": "🇳🇿",
    "CH": "🇨🇭", "Switzerland": "🇨🇭",
    "SE": "🇸🇪", "Sweden": "🇸🇪",
    "NO": "🇳🇴", "Norway": "🇳🇴",
    "DK": "🇩🇰", "Denmark": "🇩🇰",
    "NL": "🇳🇱", "Netherlands": "🇳🇱",
    "IT": "🇮🇹", "Italy": "🇮🇹",
    "ES": "🇪🇸", "Spain": "🇪🇸",
    "KR": "🇰🇷", "South Korea": "🇰🇷",
    "SG": "🇸🇬", "Singapore": "🇸🇬",
    "HK": "🇭🇰", "Hong Kong": "🇭🇰",
    "IN": "🇮🇳", "India": "🇮🇳",
    "BR": "🇧🇷", "Brazil": "🇧🇷",
    "MX": "🇲🇽", "Mexico": "🇲🇽",
}

_CARD_BODY_STYLE = {
    "padding": "14px 16px 10px 16px",
    "borderTop": "1px solid #e9ecef",
}

_CARD_STYLE = {
    "border": "1px solid #dee2e6",
    "borderRadius": "6px",
    "marginBottom": "14px",
    "backgroundColor": "#fff",
    "boxShadow": "0 1px 3px rgba(0,0,0,.06)",
    "overflow": "hidden",
}

_CARD_HEADER_STYLE = {
    "display": "flex",
    "justifyContent": "space-between",
    "alignItems": "center",
    "padding": "10px 14px",
    "cursor": "pointer",
    "userSelect": "none",
    "backgroundColor": "#f8f9fa",
}


def _inline_tag(label: str) -> html.Span:
    """Render a small coloured [LABEL] tag inline."""
    colors = _TAG_COLORS.get(label.upper(), _TAG_COLORS["GENERAL"])
    return html.Span(
        f"[{label}]",
        style={
            "display": "inline-block",
            "padding": "1px 5px",
            "borderRadius": "3px",
            "fontSize": "10px",
            "fontWeight": "700",
            "backgroundColor": colors["bg"],
            "color": colors["fg"],
            "marginRight": "6px",
            "verticalAlign": "middle",
            "letterSpacing": "0.03em",
        }
    )


def _chip(text: str, color: str = "#e9ecef", text_color: str = "#343a40") -> html.Span:
    """Render a small pill/chip."""
    return html.Span(
        text,
        style={
            "display": "inline-block",
            "padding": "2px 9px",
            "borderRadius": "12px",
            "fontSize": "12px",
            "fontWeight": "500",
            "backgroundColor": color,
            "color": text_color,
            "marginRight": "6px",
            "marginBottom": "4px",
            "whiteSpace": "nowrap",
        }
    )


def _build_card(
    card_id: str,
    title: str,
    body_children: list,
    default_collapsed: bool = True,
    title_icon: str = "",
) -> html.Div:
    """
    Collapsible card.  Collapse state is toggled via a clientside callback
    registered once at module level (see _register_card_callbacks).
    The card body div has id ``card_id + '-body'``.
    The toggle button has id ``card_id + '-toggle'``.
    """
    chevron_id = f"{card_id}-chevron"
    body_id = f"{card_id}-body"
    toggle_id = f"{card_id}-toggle"

    initial_body_style = dict(_CARD_BODY_STYLE)
    initial_chevron = "▲" if not default_collapsed else "▼"
    if default_collapsed:
        initial_body_style["display"] = "none"

    header = html.Div(
        [
            html.Span(
                f"{title_icon} {title}".strip(),
                style={"fontWeight": "600", "fontSize": "14px", "color": "#212529"},
            ),
            html.Span(
                initial_chevron,
                id=chevron_id,
                style={"fontSize": "11px", "color": "#6c757d"},
            ),
        ],
        id=toggle_id,
        style=_CARD_HEADER_STYLE,
        n_clicks=0,
    )
    body = html.Div(
        body_children,
        id=body_id,
        style=initial_body_style,
    )
    return html.Div([header, body], style=_CARD_STYLE)


def _build_tagged_bullet_list(
    grouped: dict,
    card_id: str,
    preview_per_group: int = 3,
) -> list:
    """
    Render a flat list where each bullet is prefixed with a [TAG] label.
    Each asset-class group shows ``preview_per_group`` items by default,
    with a 'Show all N' link to reveal the rest.

    Args:
        grouped: Dict mapping asset-class label → list of bullet dicts.
        card_id: Unique prefix for generated IDs (must be stable across renders).
        preview_per_group: How many bullets to show before the Show-all link.

    Returns:
        List of Dash components to place inside a card body.
    """
    children: list = []
    for group_label, items in grouped.items():
        if not items:
            continue
        visible = items[:preview_per_group]
        hidden = items[preview_per_group:]
        group_slug = group_label.lower().replace(" ", "_")
        overflow_id = f"{card_id}-{group_slug}-overflow"
        showall_id = f"{card_id}-{group_slug}-showall"

        rows: list = []
        for item in visible:
            text = item.get("text", str(item)) if isinstance(item, dict) else str(item)
            rows.append(html.Div(
                [_inline_tag(group_label), html.Span(text, style={"fontSize": "13px", "lineHeight": "1.45"})],
                style={"marginBottom": "6px"},
            ))

        hidden_rows: list = []
        for item in hidden:
            text = item.get("text", str(item)) if isinstance(item, dict) else str(item)
            hidden_rows.append(html.Div(
                [_inline_tag(group_label), html.Span(text, style={"fontSize": "13px", "lineHeight": "1.45"})],
                style={"marginBottom": "6px"},
            ))

        children.extend(rows)

        if hidden_rows:
            children.append(html.Div(
                hidden_rows,
                id=overflow_id,
                style={"display": "none"},
            ))
            children.append(html.Div(
                html.A(
                    f"Show all {len(items)} →",
                    id=showall_id,
                    href="#",
                    style={"fontSize": "12px", "color": "#007bff", "textDecoration": "none"},
                    n_clicks=0,
                ),
                style={"marginBottom": "10px"},
            ))

    return children


def _build_risk_flags_card(warnings: list, card_id: str = "risk-flags") -> html.Div:
    """
    Risk Flags card: each item shows asset class, products, horizon, direction, and text.
    Includes backward compatibility for old-format warnings (plain text or missing fields).
    """
    if not warnings:
        return html.Div()

    def _normalize_warning(w):
        """Backward compatibility adapter: convert old format to new format."""
        if isinstance(w, str):
            # Old format: plain string
            return {
                "text": w,
                "asset_class": "general",
                "products": [],
                "horizon": "today",
                "direction": "unknown",
                "confidence": None,
                "sources": []
            }
        elif isinstance(w, dict):
            # Ensure all required fields exist (backward compatibility)
            return {
                "text": w.get("text", str(w)),
                "asset_class": w.get("asset_class", "general"),
                "products": w.get("products", []),
                "horizon": w.get("horizon", "today"),
                "direction": w.get("direction", "unknown"),
                "confidence": w.get("confidence"),
                "sources": w.get("sources", [])
            }
        else:
            # Fallback for unexpected format
            return {
                "text": str(w),
                "asset_class": "general",
                "products": [],
                "horizon": "today",
                "direction": "unknown",
                "confidence": None,
                "sources": []
            }

    bullet_rows: list = []
    for w in warnings:
        norm = _normalize_warning(w)
        text = norm["text"]
        asset_class = norm["asset_class"].upper()
        products = norm["products"]
        horizon = norm["horizon"]
        direction = norm["direction"]
        
        # Build context tags row
        context_tags: list = []
        
        # Primary tag: asset class
        ac_colors = _TAG_COLORS.get(asset_class, _TAG_COLORS["GENERAL"])
        context_tags.append(html.Span(
            asset_class,
            style={
                "display": "inline-block",
                "padding": "2px 7px",
                "borderRadius": "3px",
                "fontSize": "10px",
                "fontWeight": "700",
                "backgroundColor": ac_colors["bg"],
                "color": ac_colors["fg"],
                "marginRight": "5px",
                "letterSpacing": "0.03em",
            }
        ))
        
        # Secondary tag: products or "General"
        if products:
            products_text = ", ".join(products[:3])  # Show first 3
            if len(products) > 3:
                products_text += f" +{len(products) - 3}"
            context_tags.append(html.Span(
                products_text,
                style={
                    "display": "inline-block",
                    "padding": "2px 7px",
                    "borderRadius": "3px",
                    "fontSize": "10px",
                    "fontWeight": "600",
                    "backgroundColor": "#e9ecef",
                    "color": "#495057",
                    "marginRight": "5px",
                }
            ))
        else:
            context_tags.append(html.Span(
                "General",
                style={
                    "display": "inline-block",
                    "padding": "2px 7px",
                    "borderRadius": "3px",
                    "fontSize": "10px",
                    "fontWeight": "600",
                    "backgroundColor": "#f8f9fa",
                    "color": "#6c757d",
                    "marginRight": "5px",
                    "fontStyle": "italic",
                }
            ))
        
        # Horizon and direction suffix
        suffix_parts = []
        if horizon and horizon != "today":
            suffix_parts.append(horizon)
        if direction and direction not in ["unknown", "mixed"]:
            suffix_parts.append(direction)
        elif direction == "mixed":
            suffix_parts.append("two-sided")
        
        if suffix_parts:
            context_tags.append(html.Span(
                " | ".join(suffix_parts),
                style={
                    "fontSize": "10px",
                    "color": "#999",
                    "fontStyle": "italic",
                    "marginLeft": "3px",
                }
            ))
        
        # Build the row
        bullet_rows.append(html.Div(
            [
                # Context tags row
                html.Div(
                    context_tags,
                    style={"marginBottom": "3px", "display": "flex", "alignItems": "center", "flexWrap": "wrap"}
                ),
                # Warning text
                html.Div(
                    [
                        html.Span("⚠", style={"color": "#856404", "marginRight": "7px", "fontSize": "13px"}),
                        html.Span(text, style={"fontSize": "13px", "lineHeight": "1.5", "color": "#495057"}),
                    ],
                    style={"display": "flex", "alignItems": "flex-start"},
                ),
            ],
            style={"marginBottom": "12px"},
        ))

    return _build_card(
        card_id=card_id,
        title="Risk Flags",
        body_children=bullet_rows,
        default_collapsed=True,
        title_icon="⚠️",
    )


def _build_briefing_strip(sections: dict, meta: dict) -> html.Div:
    """
    Single horizontal strip shown at the very top of the Daily Recap page.
    Sticky on desktop (position:sticky), inline on mobile.

    Segments rendered (only when data exists):
      • Volatility tone  – derived from volatility_by_asset_class
      • Top catalysts    – from consensus_catalysts (first 2)
      • Liquidity/holidays – from econ events (all_day=True items)
      • Risk themes      – from warnings (first 3 unique topic words)
    """
    chips: list = []

    # ── Volatility tone ───────────────────────────────────────────────────
    vol_by_ac = sections.get("volatility_by_asset_class", {})
    if vol_by_ac:
        # Aggregate: find the most common expected_volatility
        from collections import Counter as _Counter
        vol_labels = [v.get("expected_volatility", "") for v in vol_by_ac.values() if v.get("expected_volatility")]
        skew_labels = [v.get("directional_skew", "") for v in vol_by_ac.values() if v.get("directional_skew")]
        if vol_labels:
            top_vol = _Counter(vol_labels).most_common(1)[0][0]
            top_skew = _Counter(skew_labels).most_common(1)[0][0] if skew_labels else ""
            vol_text = f"{top_vol} · {top_skew}" if top_skew else top_vol
            vol_color = (
                "#dc3545" if top_vol == "High" else
                "#fd7e14" if top_vol == "Medium" else
                "#28a745"
            )
            chips.append(_chip(f"📊 {vol_text}", color=vol_color + "22", text_color=vol_color))

    # ── Top catalysts ─────────────────────────────────────────────────────
    catalysts = sections.get("consensus_catalysts", [])
    if catalysts:
        cat_texts = []
        for c in catalysts[:2]:
            t = c.get("text", str(c)) if isinstance(c, dict) else str(c)
            # Shorten: first clause before comma/semicolon
            short = t.split(",")[0].split(";")[0].strip()
            if len(short) > 50:
                short = short[:48] + "…"
            cat_texts.append(short)
        if cat_texts:
            chips.append(_chip("📌 " + " · ".join(cat_texts), color="#e8f4f8", text_color="#0c5460"))

    # ── Primary risk themes (from warnings) ───────────────────────────────
    warnings = sections.get("warnings", [])
    if warnings:
        # Extract bracketed tags like [Political] or leading topic words
        import re as _re2
        theme_words: list = []
        for w in warnings[:6]:
            t = w.get("text", str(w)) if isinstance(w, dict) else str(w)
            m = _re2.search(r"\[([A-Za-z][A-Za-z ]{1,20})\]", t)
            if m:
                word = m.group(1).strip()
            else:
                # Fallback: first capitalised word that isn't a stop-word
                words = t.split()
                word = next(
                    (wd.rstrip(".,;:") for wd in words
                     if wd[0:1].isupper() and len(wd) > 3
                     and wd.lower() not in {"the", "this", "that", "with", "from", "amid"}),
                    ""
                )
            if word and word not in theme_words:
                theme_words.append(word)
            if len(theme_words) >= 3:
                break
        if theme_words:
            chips.append(_chip("🚩 " + " · ".join(theme_words), color="#fdf3f3", text_color="#842029"))

    if not chips:
        return html.Div()

    return html.Div(
        html.Div(
            chips,
            style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "6px",
                "alignItems": "center",
                "padding": "8px 16px",
            }
        ),
        style={
            "backgroundColor": "#f8f9fa",
            "borderBottom": "1px solid #dee2e6",
            "position": "sticky",
            "top": "0",
            "zIndex": "100",
            # Mobile: override sticky via media-query class (see inline style note)
        },
        className="daily-briefing-strip",
    )


def _build_econ_events_structured(events: list) -> html.Div:
    """
    Structured event rows: flag · name · [CCY] · [Holiday|Event] badge.
    Replaces the old monospace text list.
    """
    rows: list = []
    for evt in events:
        country = evt.get("country_or_region", "")
        title = evt.get("title", "")
        currency = evt.get("currency_tag", "")
        is_all_day = bool(evt.get("all_day"))
        time_label = evt.get("time_local", "")

        flag = _COUNTRY_FLAGS.get(country, country[:2].upper() if country else "")

        badge_text = "Holiday" if is_all_day else "Event"
        badge_color = "#d1ecf1" if is_all_day else "#e2e3e5"
        badge_fg = "#0c5460" if is_all_day else "#383d41"

        time_span = html.Span(
            "All day" if is_all_day else (time_label or ""),
            style={
                "display": "inline-block",
                "minWidth": "52px",
                "fontSize": "11px",
                "color": "#28a745" if is_all_day else "#007bff",
                "fontWeight": "600",
                "marginRight": "6px",
            }
        )
        flag_span = html.Span(
            flag,
            style={"marginRight": "5px", "fontSize": "14px"}
        ) if flag else None
        name_span = html.Span(title, style={"fontSize": "13px", "marginRight": "6px"})
        ccy_span = html.Span(
            currency,
            style={
                "display": "inline-block",
                "padding": "1px 5px",
                "borderRadius": "3px",
                "fontSize": "10px",
                "fontWeight": "600",
                "backgroundColor": "#e9ecef",
                "color": "#495057",
                "marginRight": "5px",
            }
        ) if currency else None
        badge_span = html.Span(
            badge_text,
            style={
                "display": "inline-block",
                "padding": "1px 6px",
                "borderRadius": "3px",
                "fontSize": "10px",
                "fontWeight": "600",
                "backgroundColor": badge_color,
                "color": badge_fg,
            }
        )

        row_children = [time_span]
        if flag_span:
            row_children.append(flag_span)
        row_children.append(name_span)
        if ccy_span:
            row_children.append(ccy_span)
        row_children.append(badge_span)

        rows.append(html.Div(row_children, style={"marginBottom": "6px", "display": "flex", "alignItems": "center", "flexWrap": "wrap"}))

    return html.Div(rows)


def _econ_db_error_banner(error: Exception) -> html.Div:
    """
    Return a descriptive, styled error banner for SQLite failures.

    Args:
        error: The exception raised when accessing the database.

    Returns:
        Dash Div error component.
    """
    msg = str(error)
    if "locked" in msg.lower():
        detail = "The database is locked by another process. Close any other connections and retry."
    elif "no such table" in msg.lower():
        detail = "Schema is missing. The database file may be corrupt or incomplete."
    elif "unable to open" in msg.lower() or "no such file" in msg.lower():
        detail = f"Database file not found at: {DB_PATH}"
    else:
        detail = msg

    return html.Div(
        [
            html.Strong("⚠️ Economic Calendar database error: "),
            html.Span(detail),
            html.Br(),
            html.Span(
                f"Expected location: {DB_PATH}",
                style={"fontSize": "11px", "color": "#856404"},
            ),
        ],
        style={
            "padding": "10px 14px",
            "backgroundColor": "#fff3cd",
            "border": "1px solid #ffc107",
            "borderRadius": "4px",
            "color": "#856404",
            "marginBottom": "12px",
        },
    )


def _render_econ_events_panel(date_str: str, rollup_json: Optional[dict], dynamics_mode: bool = True, is_logged_in: bool = False):
    """
    Build the Economic Events panel for one rollup date.

    Returns a collapsible card (html.Div) or None when no events exist.

    Args:
        date_str: Date in YYYYMMDD or YYYY-MM-DD format.
        rollup_json: Parsed rollup dict (unused here, kept for API compat).
        dynamics_mode: Whether to render the dynamics brief section.
        is_logged_in: Whether the current viewer is authenticated.
                      Forwarded to _render_econ_daily_brief to control
                      "Generate Brief" button visibility.

    Returns:
        html.Div card, or None.
    """
    if not ECON_CALENDAR_AVAILABLE:
        return None

    # ── Normalise date_str to YYYY-MM-DD ──────────────────────────────────
    try:
        if date_str and len(date_str) == 8 and date_str.isdigit():
            date_iso = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        else:
            date_iso = (date_str or "").strip()
        datetime.datetime.strptime(date_iso, "%Y-%m-%d")
        print(f"[ECON] Panel called for date_iso: {date_iso}")
    except (ValueError, AttributeError) as e:
        print(f"[ECON] Failed to parse date_str='{date_str}': {e}")
        return None

    # ── Query events ──────────────────────────────────────────────────────
    try:
        events = get_events_for_date(DB_PATH, date_iso)
        print(f"[ECON] Daily View events loaded: {len(events)} events for {date_iso}")
    except Exception as exc:
        print(f"[ECON] get_events_for_date failed for {date_iso}: {exc}")
        return _build_card(
            card_id="econ-events-error",
            title="Economic Events",
            body_children=[_econ_db_error_banner(exc)],
            default_collapsed=True,
            title_icon="📅",
        )

    if not events:
        print(f"[ECON] No events found for {date_iso}, panel hidden")
        return None

    # ── Build structured event rows ────────────────────────────────────────
    event_rows = _build_econ_events_structured(events)

    # ── Pre-generated brief ────────────────────────────────────────────────
    # is_logged_in is threaded from the Dash callback via the login-user store.
    # Regular visitors (is_logged_in=False) never see the Generate Brief button,
    # so a page load by N anonymous users never triggers N AI calls.
    brief_div = _render_econ_daily_brief(date_iso, dynamics_mode, is_logged_in=is_logged_in)

    body_children: list = [
        html.Div(
            html.Span(
                "Educational only. Not financial advice. · Events live from SQLite",
                style={"fontSize": "11px", "color": "#999", "fontStyle": "italic"},
            ),
            style={"marginBottom": "10px"},
        ),
        html.Div(
            event_rows,
            style={
                "backgroundColor": "#f8f9fa",
                "padding": "10px 14px",
                "borderRadius": "4px",
                "marginBottom": "10px",
            },
        ),
    ]
    if brief_div is not None:
        body_children.append(brief_div)

    return _build_card(
        card_id="econ-events",
        title=f"Economic Events  ({len(events)})",
        body_children=body_children,
        default_collapsed=True,
        title_icon="📅",
    )


def _render_econ_daily_brief(date_iso: str, dynamics_mode: bool, is_logged_in: bool = False) -> html.Div:
    """
    Render the pre-generated Economic Brief section for one date.

    Reads only from the database — never calls the LLM or any AI function.

    Rules:
    - If no events exist for the date, return None (section hidden).
    - If no brief row or theory_text is empty:
        * Show a one-line "Summary pending" status (hidden to regular users).
        * If is_logged_in is True, also render a "Generate Brief" button that
          calls POST /api/econ/generate-brief via a clientside fetch callback.
          The button is NEVER shown to unauthenticated visitors, so a page
          load by N regular users never triggers N AI calls.
    - If dynamics_mode is True and dynamics_text is populated, render it below theory.

    Args:
        date_iso: ISO date YYYY-MM-DD.
        dynamics_mode: Whether to render the dynamics section.
        is_logged_in: Whether the current viewer is authenticated.
                      Controls "Generate Brief" button visibility.

    Returns:
        html.Div with the brief section, or None if no events exist.
    """
    if not ECON_CALENDAR_AVAILABLE:
        return None

    # Guard: only show section when events exist for this date
    try:
        events = get_events_for_date(DB_PATH, date_iso)
    except Exception:
        events = []

    if not events:
        return None

    # Query the pre-generated brief (read-only, no LLM)
    brief_row = None
    try:
        if get_daily_brief is not None:
            brief_row = get_daily_brief(DB_PATH, date_iso)
            print(f"[ECON READ] get_daily_brief for date_key={date_iso}: found={brief_row is not None}")
    except Exception as e:
        print(f"[ECON READ] get_daily_brief FAILED for date_key={date_iso}: {e}")
        brief_row = None

    theory_text = (brief_row or {}).get("theory_text", "").strip() if brief_row else ""
    dynamics_text = (brief_row or {}).get("dynamics_text", "").strip() if brief_row else ""

    # Log what we found
    if brief_row:
        print(f"[ECON READ] Brief for date_key={date_iso}: theory_len={len(theory_text)}, dynamics_len={len(dynamics_text)}")

    # Detect error messages stored as theory_text (legacy bug - error messages were saved as content)
    # Error messages typically start with "Brief generation unavailable:" or similar
    _ERROR_PREFIXES = (
        "brief generation unavailable",
        "summary unavailable",
        "summary generation failed",
        "error code:",
    )
    brief_is_error = theory_text and any(theory_text.lower().startswith(p) for p in _ERROR_PREFIXES)

    if brief_is_error:
        print(f"[ECON READ] Detected error message in brief for date_key={date_iso}, treating as missing")
        theory_text = ""  # Treat as missing
        dynamics_text = ""

    # ── Brief is missing or invalid ───────────────────────────────────────
    # Regular users see nothing (section stays hidden).
    # Logged-in users see a one-line status + a "Generate Brief" button.
    # The button triggers a clientside fetch to /api/econ/generate-brief;
    # the result is rendered inline without a page reload.
    if not theory_text:
        status_children: list = [
            html.P(
                f"Summary pending for {date_iso}",
                style={
                    "fontSize": "12px",
                    "color": "#6c757d",
                    "fontStyle": "italic",
                    "marginTop": "16px",
                    "marginBottom": "8px",
                },
            ),
        ]

        if is_logged_in:
            # The button id carries the date so the clientside callback knows
            # which date to request.  The econ-gen-brief-status div receives
            # the inline brief (or error) from render_generated_brief().
            status_children.append(
                html.Button(
                    "Generate Brief",
                    id={"type": "econ-gen-brief-btn", "date": date_iso},
                    className="btn btn-sm btn-outline-primary",
                    style={"fontSize": "11px", "padding": "4px 12px"},
                )
            )

        # econ-brief-status is the target for render_generated_brief() output
        return html.Div(
            status_children,
            id={"type": "econ-brief-status", "date": date_iso},
        )

    # Valid brief found - render the Summary section
    section_children = [
        html.Hr(style={"margin": "24px 0", "border": "none", "borderTop": "1px solid #e0e7ef"}),
        html.H3(
            "Summary:",
            style={"fontSize": "17px", "color": "#004080", "marginBottom": "10px"},
        ),
    ]

    # Single summary block (was "Theory")
    theory_lines = [
        html.P(line, style={"margin": "2px 0", "fontSize": "13px", "lineHeight": "1.55"})
        for line in theory_text.splitlines()
        if line.strip()
    ]
    section_children.append(
        html.Div(
            theory_lines,
            style={
                "backgroundColor": "#f8f9fa", "padding": "12px 16px",
                "borderRadius": "4px", "marginBottom": "10px",
                "borderLeft": "4px solid #004080",
            },
        )
    )

    return html.Div(section_children, style={"marginTop": "6px"})


def render_rollup_summary(rollup_json: dict, article_count: int, dynamics_mode: bool = True, is_logged_in: bool = False) -> html.Div:
    """
    Render the Daily Recap page in a professional, trading-audience layout.

    Section order (matches spec):
      1. Briefing Strip  (sticky desktop / inline mobile)
      2. Today in Bullets  (TLDR — default expanded)
      3. Catalysts & Calendar  (consensus_catalysts + econ events — default expanded)
      4. Volatility Outlook  (default collapsed)
      5. Risk Flags  (warnings chips — default collapsed)
      6. Yesterday  (observations — default collapsed)
      7. Forward Watch  (forward_watch — default collapsed)
      8. Articles list  (trade ideas / sources — default collapsed)

    Desktop ≥ xl: two-column grid.
    All cards are collapsible with localStorage persistence.
    """
    meta = rollup_json.get("meta", {})
    sections = rollup_json.get("sections", {})
    ui = rollup_json.get("ui", {})

    title = ui.get("title", "Preparation for Today")
    providers = meta.get("providers", [])
    date_str = meta.get("date", "")

    # Normalise date_str → YYYY-MM-DD
    if date_str and len(date_str) == 8 and date_str.isdigit():
        date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    print(f"[ECON] render_rollup_summary date_str: {date_str}")

    # Resolve date_iso for econ panel
    date_iso: Optional[str] = None
    if date_str:
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
            date_iso = date_str
        except ValueError:
            pass

    # ── 1. Briefing Strip ─────────────────────────────────────────────────
    briefing_strip = _build_briefing_strip(sections, meta)

    # ── Page header ───────────────────────────────────────────────────────
    page_header = html.Div(
        [
            html.H2(title, style={"color": HEADER_BG_COLOR, "marginBottom": "4px", "fontSize": "22px"}),
            html.P(
                f"{article_count} articles • {', '.join(providers)}",
                style={"color": "#6c757d", "marginBottom": "10px", "fontSize": "13px"},
            ),
            # Expand all / Collapse all controls
            html.Div(
                [
                    html.A(
                        "Expand all",
                        id="recap-expand-all",
                        href="#",
                        n_clicks=0,
                        style={"fontSize": "12px", "color": "#007bff", "marginRight": "12px", "textDecoration": "none"},
                    ),
                    html.A(
                        "Collapse all",
                        id="recap-collapse-all",
                        href="#",
                        n_clicks=0,
                        style={"fontSize": "12px", "color": "#6c757d", "textDecoration": "none"},
                    ),
                ],
                style={"marginBottom": "12px"},
            ),
        ],
        style={"padding": "14px 16px 0 16px"},
    )

    # ── 2. Today in Bullets (TLDR) ─────────────────────────────────────
    tldr = sections.get("tldr", [])
    tldr_body: list = []
    if tldr:
        for item in tldr[:3]:
            text = item.get("text", str(item)) if isinstance(item, dict) else str(item)
            tldr_body.append(html.Div(
                [
                    html.Span("•", style={"color": HEADER_BG_COLOR, "fontWeight": "700", "marginRight": "8px", "fontSize": "16px"}),
                    html.Span(text, style={"fontSize": "14px", "lineHeight": "1.5"}),
                ],
                style={"marginBottom": "8px", "display": "flex", "alignItems": "flex-start"},
            ))
        if len(tldr) > 3:
            extra_id = "tldr-extra"
            extra_rows = []
            for item in tldr[3:]:
                text = item.get("text", str(item)) if isinstance(item, dict) else str(item)
                extra_rows.append(html.Div(
                    [
                        html.Span("•", style={"color": HEADER_BG_COLOR, "fontWeight": "700", "marginRight": "8px", "fontSize": "16px"}),
                        html.Span(text, style={"fontSize": "14px", "lineHeight": "1.5"}),
                    ],
                    style={"marginBottom": "8px", "display": "flex", "alignItems": "flex-start"},
                ))
            tldr_body.append(html.Div(extra_rows, id=extra_id, style={"display": "none"}))
            tldr_body.append(html.A(
                f"Show all {len(tldr)} →",
                id="tldr-showall",
                href="#",
                n_clicks=0,
                style={"fontSize": "12px", "color": "#007bff", "textDecoration": "none"},
            ))
    else:
        # Missing brief status line
        tldr_body.append(html.P(
            "Brief unavailable for this date",
            style={"fontSize": "13px", "color": "#6c757d", "fontStyle": "italic"},
        ))

    card_today = _build_card(
        card_id="card-today",
        title="Today in Bullets",
        body_children=tldr_body,
        default_collapsed=False,
        title_icon="📝",
    )

    # ── 3. Catalysts & Calendar ───────────────────────────────────────────
    catalysts_body: list = []

    # Consensus catalysts
    catalysts = sections.get("consensus_catalysts", [])
    if catalysts:
        catalysts_body.append(html.P(
            "Near-term catalysts",
            style={"fontSize": "11px", "fontWeight": "600", "color": "#6c757d",
                   "textTransform": "uppercase", "letterSpacing": "0.05em", "marginBottom": "6px"},
        ))
        for c in catalysts:
            text = c.get("text", str(c)) if isinstance(c, dict) else str(c)
            catalysts_body.append(html.Div(
                [
                    html.Span("📌", style={"marginRight": "6px"}),
                    html.Span(text, style={"fontSize": "13px", "lineHeight": "1.45"}),
                ],
                style={"marginBottom": "5px"},
            ))

    # Economic events panel (structured rows)
    if date_iso:
        print(f"[ECON] render_rollup_summary: Adding events panel for {date_iso}")
        econ_card = _render_econ_events_panel(date_iso, rollup_json, dynamics_mode=dynamics_mode, is_logged_in=is_logged_in)
        if econ_card is not None:
            catalysts_body.append(html.Div(style={"marginTop": "12px"}))
            catalysts_body.append(econ_card)

    if not catalysts_body:
        catalysts_body.append(html.P(
            "No catalyst data available.",
            style={"fontSize": "13px", "color": "#6c757d", "fontStyle": "italic"},
        ))

    card_catalysts = _build_card(
        card_id="card-catalysts",
        title="Catalysts & Calendar",
        body_children=catalysts_body,
        default_collapsed=False,
        title_icon="📅",
    )

    # ── 4. Volatility Outlook ─────────────────────────────────────────────
    vol_by_ac = sections.get("volatility_by_asset_class", {})
    vol_body: list = []
    if vol_by_ac:
        # Canonical reference mapping for backward compatibility with old rollups
        # that don't have reference_symbol field
        FALLBACK_REFERENCE = {
            "EQUITIES": "SPX",
            "FX": "DXY",
            "RATES": "US10Y",
            "COMMODITIES": "CL",
            "METALS": "GC",
            "ENERGY": "CL",
            "CRYPTO": "BTC",
            "VOLATILITY": "VIX",
            "GENERAL": None,
            "CREDIT": None,
        }
        
        for ac, vol_data in vol_by_ac.items():
            ev = vol_data.get("expected_volatility", "?")
            skew = vol_data.get("directional_skew", "Neutral")
            conf = vol_data.get("confidence_score", 0)
            reference_symbol = vol_data.get("reference_symbol")  # NEW field
            bias_definition = vol_data.get("bias_definition", "")  # NEW field
            
            # Fallback to canonical mapping if reference_symbol missing (old rollups)
            if reference_symbol is None and ac in FALLBACK_REFERENCE:
                reference_symbol = FALLBACK_REFERENCE[ac]
                # Build fallback bias definition
                if reference_symbol:
                    if ac == "FX" and reference_symbol == "DXY":
                        if skew == "Bearish":
                            bias_definition = "Bearish bias relative to DXY. If DXY falls, EURUSD tends to rise (USD weakness)."
                        elif skew == "Bullish":
                            bias_definition = "Bullish bias relative to DXY. If DXY rises, EURUSD tends to fall (USD strength)."
                        else:
                            bias_definition = "Neutral bias relative to DXY. Mixed signals across currency pairs."
                    else:
                        direction_text = {"Bearish": "downside", "Bullish": "upside", "Neutral": "neutral"}.get(skew, "mixed")
                        bias_definition = f"{skew} bias relative to {reference_symbol}. Expected {direction_text} movement."
                else:
                    bias_definition = f"{skew} bias for {ac}. No single reference instrument."
            
            ev_color = (
                "#dc3545" if ev == "High" else
                "#ffc107" if ev == "Medium" else
                "#28a745"
            )
            skew_arrow = "↗️" if skew == "Bullish" else ("↘️" if skew == "Bearish" else "↔️")
            
            # Build asset class label with reference symbol
            ac_label = f"{ac} ({reference_symbol})" if reference_symbol else ac
            
            vol_body.append(html.Div(
                [
                    html.Span(ac_label, style={"fontWeight": "600", "minWidth": "140px", "display": "inline-block", "fontSize": "13px"}),
                    html.Span(
                        ev,
                        style={
                            "display": "inline-block", "padding": "2px 8px", "borderRadius": "4px",
                            "fontSize": "11px", "fontWeight": "600", "marginRight": "8px",
                            "backgroundColor": ev_color, "color": "white",
                        }
                    ),
                    html.Span(f"{skew_arrow} {skew}", style={"fontSize": "13px", "marginRight": "8px"}),
                    html.Span(f"conf {conf:.1f}", style={"fontSize": "11px", "color": "#999"}),
                ],
                style={"marginBottom": "8px", "display": "flex", "alignItems": "center", "flexWrap": "wrap"},
            ))
    else:
        vol_body.append(html.P(
            "No volatility data available.",
            style={"fontSize": "13px", "color": "#6c757d", "fontStyle": "italic"},
        ))

    card_vol = _build_card(
        card_id="card-vol",
        title="Volatility Outlook",
        body_children=vol_body,
        default_collapsed=True,
        title_icon="📊",
    )

    # ── 5. Risk Flags (warnings chips) ───────────────────────────────────
    warnings = sections.get("warnings", [])
    card_risk = _build_risk_flags_card(warnings, card_id="risk-flags")

    # ── 6. Yesterday (observations) ──────────────────────────────────────
    observations = sections.get("observations", {})
    obs_body: list = []
    if observations:
        obs_body = _build_tagged_bullet_list(observations, card_id="obs", preview_per_group=3)
    else:
        obs_body.append(html.P(
            "No observations available.",
            style={"fontSize": "13px", "color": "#6c757d", "fontStyle": "italic"},
        ))

    card_yesterday = _build_card(
        card_id="card-yesterday",
        title="Yesterday",
        body_children=obs_body,
        default_collapsed=True,
        title_icon="🕐",
    )

    # ── 7. Forward Watch ─────────────────────────────────────────────────
    forward_watch = sections.get("forward_watch", {})
    fw_body: list = []
    if forward_watch:
        fw_body = _build_tagged_bullet_list(forward_watch, card_id="fw", preview_per_group=3)
    else:
        fw_body.append(html.P(
            "No forward watch items available.",
            style={"fontSize": "13px", "color": "#6c757d", "fontStyle": "italic"},
        ))

    card_forward = _build_card(
        card_id="card-forward",
        title="Forward Watch",
        body_children=fw_body,
        default_collapsed=True,
        title_icon="🔭",
    )

    # ── 8. Articles / Trade Ideas ─────────────────────────────────────────
    raw_trade_ideas = sections.get("trade_ideas", {})
    _bucket_labels = {
        "d_1_3": "1-3 Day (Tactical)",
        "w_1_2": "1-2 Week (Swing)",
        "gt_2w": ">2 Week (Position)",
        "watchlist_only": "Watchlist Only",
    }
    _flat_ideas: list = []
    if isinstance(raw_trade_ideas, dict):
        for bucket_key, label in _bucket_labels.items():
            for idea in raw_trade_ideas.get(bucket_key, []):
                if isinstance(idea, dict):
                    _flat_ideas.append((label, idea))
    elif isinstance(raw_trade_ideas, list):
        for idea in raw_trade_ideas:
            if isinstance(idea, dict):
                _flat_ideas.append((None, idea))

    articles_body: list = []
    if _flat_ideas:
        for bucket_label, idea in _flat_ideas:
            direction = (idea.get("direction", "") or "").upper()
            instrument = idea.get("instrument", idea.get("product", "?"))
            bias_color = "#28a745" if direction in ("LONG", "BULLISH") else (
                "#dc3545" if direction in ("SHORT", "BEARISH") else "#6c757d"
            )
            card_children: list = [
                html.Div([
                    html.Span(f"{direction} {instrument}", style={"fontWeight": "bold", "fontSize": "15px", "marginRight": "10px"}),
                    html.Span(
                        bucket_label or idea.get("bias", ""),
                        style={"display": "inline-block", "padding": "2px 8px", "borderRadius": "4px",
                               "fontSize": "11px", "backgroundColor": bias_color, "color": "white"}
                    ) if bucket_label or idea.get("bias") else None,
                ], style={"marginBottom": "5px"}),
            ]
            trigger = idea.get("trigger", idea.get("catalyst", ""))
            if trigger:
                card_children.append(html.Div([
                    html.Span("Trigger: ", style={"fontWeight": "500", "fontSize": "13px"}),
                    html.Span(trigger, style={"fontSize": "13px"})
                ], style={"marginBottom": "3px"}))
            rationale = idea.get("rationale", "")
            if rationale:
                card_children.append(html.Div([
                    html.Span("Rationale: ", style={"fontWeight": "500", "fontSize": "13px"}),
                    html.Span(rationale, style={"fontSize": "13px"})
                ], style={"marginBottom": "3px"}))
            sources = idea.get("sources", [])
            if sources:
                card_children.append(html.Div(
                    html.Span(f"Sources: {', '.join(sources)}", style={"fontSize": "12px", "color": "#666"}),
                    style={"marginTop": "4px"}
                ))
            articles_body.append(html.Div(card_children, style={
                "backgroundColor": "#f8f9fa", "padding": "10px 12px", "borderRadius": "4px",
                "marginBottom": "8px", "borderLeft": f"3px solid {bias_color}",
            }))

    sources_list = sections.get("sources", [])
    if sources_list:
        articles_body.append(html.P(
            "Sources",
            style={"fontSize": "11px", "fontWeight": "600", "color": "#6c757d",
                   "textTransform": "uppercase", "letterSpacing": "0.05em",
                   "marginTop": "12px", "marginBottom": "6px"},
        ))
        for src in sources_list:
            provider = src.get("provider", "")
            titles = src.get("titles", [])
            if provider and titles:
                articles_body.append(html.Div(
                    [
                        html.Span(provider, style={"fontWeight": "600", "fontSize": "12px", "marginRight": "6px"}),
                        html.Span(" · ".join(titles), style={"fontSize": "12px", "color": "#6c757d"}),
                    ],
                    style={"marginBottom": "4px"},
                ))

    # Only render the Trade Ideas card when there are actual ideas.
    # When empty, hide the card entirely so it does not clutter the page.
    # Sources remain implicit via the article sidebar.
    if _flat_ideas:
        card_articles = _build_card(
            card_id="card-articles",
            title="Macro Trade Ideas",
            body_children=articles_body,
            default_collapsed=True,
            title_icon="💡",
        )
    else:
        card_articles = None  # hidden when no ideas

    # ── Layout assembly ───────────────────────────────────────────────────
    # Left column (actionable today): cards 2, 3, 4, 8
    # card_articles (Macro Trade Ideas) goes directly under Volatility Outlook,
    # inside the left column — it must NOT span both columns.
    left_col_children = [card_today, card_catalysts, card_vol]
    if card_articles is not None:
        left_col_children.append(card_articles)

    left_col = html.Div(
        left_col_children,
        style={"flex": "1", "minWidth": "0"},
    )
    # Right column (context): cards 5, 6, 7
    right_col = html.Div(
        [card_risk, card_yesterday, card_forward],
        style={"flex": "1", "minWidth": "0"},
    )

    # Two-column grid on xl screens (via inline style + CSS class for responsive override)
    two_col = html.Div(
        [left_col, right_col],
        className="daily-recap-grid",
        style={
            "display": "flex",
            "gap": "14px",
            "alignItems": "flex-start",
        },
    )

    # Inline <style> for responsive behaviour and sticky strip on desktop
    # Dash has no html.Style component; use dcc.Markdown with dangerously_allow_html instead
    responsive_css = dcc.Markdown(
        """
        <style>
        .daily-briefing-strip { position: sticky; top: 0; z-index: 100; }
        .daily-recap-grid { flex-direction: row; }
        @media (max-width: 1199px) {
            .daily-briefing-strip { position: static; }
            .daily-recap-grid { flex-direction: column; }
        }
        </style>
        """,
        dangerously_allow_html=True,
    )

    return html.Div(
        [
            responsive_css,
            briefing_strip,
            html.Div(
                [
                    page_header,
                    two_col,
                ],
                style={"padding": "0 16px 20px 16px"},
            ),
        ]
    )


def render_rollup_sections_detail(sections: dict, date_str: str = "", rollup_json: Optional[dict] = None, dynamics_mode: bool = True) -> html.Div:
    """
    Legacy helper — kept for any callers outside the main rollup view.
    Renders observations and forward_watch as tagged bullet lists.
    """
    children: list = []

    observations = sections.get("observations", {})
    if observations:
        children.append(html.H4("What Happened Yesterday", style={"marginTop": "15px", "marginBottom": "10px", "color": "#004080"}))
        children.extend(_build_tagged_bullet_list(observations, card_id="legacy-obs"))

    forward_watch = sections.get("forward_watch", {})
    if forward_watch:
        children.append(html.H4("What to Watch Today", style={"marginTop": "20px", "marginBottom": "10px", "color": "#004080"}))
        children.extend(_build_tagged_bullet_list(forward_watch, card_id="legacy-fw"))

    return html.Div(children)


# ── Daily View Split-Screen Helpers ──────────────────────────────────────────


def resolve_original_pdf(artifact_folder: str) -> Optional[str]:
    """
    Resolve the original PDF file for an article using priority-based search.
    
    Priority:
      A. Check artifact folder for original PDF
      B. Check ORIGINALS_ROOT using deterministic filename mapping
      C. Return None if not found (caller can show fallback)
    
    Args:
        artifact_folder: Artifact folder name (e.g., "20260211__GM__title__hash")
    
    Returns:
        Relative path to original PDF (e.g., "artifacts/folder/original.pdf" or "originals/file.pdf"), or None
    """
    try:
        artifacts_base = Path(FILES_DIR) / "artifacts"
        art_dir = artifacts_base / artifact_folder
        
        # Priority A: Check artifact folder for original PDF
        if art_dir.exists():
            # Try common original PDF names
            for pdf_name in ["original.pdf", "source.pdf", "article.pdf"]:
                pdf_path = art_dir / pdf_name
                if pdf_path.is_file():
                    print(f"[ORIGINAL_PDF] id={artifact_folder} tried=artifact/{pdf_name} found=yes")
                    return f"artifacts/{artifact_folder}/{pdf_name}"
            
            # Try finding any PDF that's not sum.pdf
            for pdf_file in art_dir.glob("*.pdf"):
                if pdf_file.name != "sum.pdf":
                    print(f"[ORIGINAL_PDF] id={artifact_folder} tried=artifact/{pdf_file.name} found=yes")
                    return f"artifacts/{artifact_folder}/{pdf_file.name}"
        
        # Priority B: Check ORIGINALS_ROOT using deterministic filename
        # Artifact folder format: YYYYMMDD__PROVIDER__title_slug__hash
        # Original PDF should have same basename: YYYYMMDD__PROVIDER__title_slug__hash.pdf
        original_filename = f"{artifact_folder}.pdf"
        original_path = ORIGINALS_ROOT / original_filename
        
        if original_path.is_file():
            print(f"[ORIGINAL_PDF] id={artifact_folder} tried=artifact found=no tried=originals/{original_filename} found=yes")
            return f"originals/{original_filename}"
        
        # Not found in either location
        print(f"[ORIGINAL_PDF] id={artifact_folder} tried=artifact found=no tried=originals/{original_filename} found=no")
        return None
        
    except Exception as e:
        print(f"[ERROR] resolve_original_pdf failed for {artifact_folder}: {e}")
        return None


def _render_original_article_pane(artifact_folder: str, original_pdf_path: Optional[str]) -> html.Div:
    """
    Render the right pane showing the original article.
    
    Strategy:
      1. If original_pdf_path exists → embed PDF in iframe
      2. Else → show message "Original not available" with fallback
    """
    if original_pdf_path:
        return html.Div([
            html.Div([
                html.H4(
                    "Original Article",
                    style={
                        "margin": "0 0 10px 0",
                        "fontSize": "16px",
                        "color": HEADER_BG_COLOR,
                        "fontWeight": "600"
                    }
                ),
                html.A(
                    "↗ Open in New Tab",
                    href=f"/view?file={original_pdf_path}",
                    target="_blank",
                    style={
                        "fontSize": "12px",
                        "color": "#007bff",
                        "textDecoration": "none",
                        "marginLeft": "10px"
                    }
                )
            ], style={
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "space-between",
                "marginBottom": "8px",
                "paddingBottom": "8px",
                "borderBottom": "1px solid #dee2e6"
            }),
            html.Iframe(
                src=f"/view?file={original_pdf_path}",
                style={
                    "width": "100%",
                    "height": "75vh",
                    "display": "block",
                    "border": "1px solid #ddd",
                    "borderRadius": "4px"
                }
            )
        ], style={
            "height": "100%",
            "padding": "10px",
            "backgroundColor": "#f8f9fa"
        })
    else:
        return html.Div([
            html.Div([
                html.H4(
                    "Original Article",
                    style={
                        "margin": "0 0 10px 0",
                        "fontSize": "16px",
                        "color": HEADER_BG_COLOR,
                        "fontWeight": "600"
                    }
                )
            ], style={
                "marginBottom": "15px",
                "paddingBottom": "8px",
                "borderBottom": "1px solid #dee2e6"
            }),
            html.Div([
                html.P(
                    "📄 Original article not available",
                    style={
                        "fontSize": "14px",
                        "color": "#6c757d",
                        "marginBottom": "10px",
                        "fontStyle": "italic"
                    }
                ),
                html.P(
                    "The original PDF was not found in the artifact folder. Only the AI-generated summary is available.",
                    style={
                        "fontSize": "13px",
                        "color": "#999",
                        "lineHeight": "1.5"
                    }
                )
            ], style={
                "backgroundColor": "#fff3cd",
                "padding": "15px",
                "borderRadius": "4px",
                "border": "1px solid #ffc107"
            })
        ], style={
            "height": "100%",
            "padding": "10px",
            "backgroundColor": "#f8f9fa"
        })


def _build_split_screen_layout(summary_content: html.Div, artifact_folder: str) -> html.Div:
    """
    Wrap summary content in a split-screen layout with original article on the right.
    
    Layout:
      - Desktop: Left 45%, Right 55% (flex)
      - Mobile: Stacked vertically (media query handled by flex-wrap)
    
    Args:
        summary_content: The existing summary view content (left pane)
        artifact_folder: The artifact folder name to find original PDF
    
    Returns:
        Split-screen container with summary on left, original on right
    """
    # Resolve original PDF (checks artifact folder, then ORIGINALS_ROOT)
    original_pdf_path = resolve_original_pdf(artifact_folder)
    
    # Build right pane
    right_pane = _render_original_article_pane(artifact_folder, original_pdf_path)
    
    # Build split-screen container
    return html.Div([
        # Left pane: summary
        html.Div(
            summary_content,
            style={
                "flex": "1",
                "minWidth": "0",
                "height": "calc(100vh - 200px)",
                "overflowY": "auto",
                "paddingRight": "10px",
                "borderRight": "1px solid #dee2e6"
            }
        ),
        # Right pane: original
        html.Div(
            right_pane,
            style={
                "flex": "1",
                "minWidth": "0",
                "height": "calc(100vh - 200px)",
                "overflowY": "auto",
                "paddingLeft": "10px"
            }
        )
    ], style={
        "display": "flex",
        "flexDirection": "row",
        "gap": "16px",
        "width": "100%",
        "padding": "10px"
    })


@app.callback(
    [
        Output("daily-selected-artifact", "data"),
        Output("daily-view-content", "children")
    ],
    [
        Input({"type": "daily-article-btn", "index": dash.dependencies.ALL}, "n_clicks"),
        Input("daily-articles-store", "data")
    ],
    [
        State("login-user", "data"),
        State("daily-view-date-input", "value")
    ],
    prevent_initial_call=True
)
def display_daily_article_summary(n_clicks_list, artifacts, login_user_store, date_input):
    """
    Render the right-panel content for the selected artifact folder.

    Rendering strategy:
      1. has_sum_json  → load JSON and render web summary
      2. has_sum_pdf   → embed PDF via iframe
      3. neither       → show clear message with missing paths
    
    Also clears the right panel when artifacts store updates with empty data.
    """
    if not ctx.triggered:
        raise PreventUpdate

    triggered_id = ctx.triggered_id
    if not triggered_id:
        raise PreventUpdate

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
    
    folder_key = triggered_id.get("index")

    # --- Daily Summary - load and render rollup ---
    if folder_key == "__daily_summary__":
        # Extract date from artifacts (they all share the same date)
        if artifacts and len(artifacts) > 0:
            date_fmt = artifacts[0].get("date_fmt", "")
            try:
                target_date = datetime.datetime.strptime(date_fmt, "%Y-%m-%d").date()
                date_str = target_date.strftime("%Y%m%d")
            except:
                date_str = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y%m%d")
        else:
            # No artifacts - determine date from default (yesterday)
            target_date = datetime.date.today() - datetime.timedelta(days=1)
            date_fmt = target_date.strftime("%Y-%m-%d")
            date_str = target_date.strftime("%Y%m%d")
        
        # Handle explicit empty state when no articles exist
        if not artifacts or len(artifacts) == 0:
            _is_logged_in_empty = bool(login_user_store)
            _live_events_panel_empty = None
            
            # Economic Events panel can still render even without articles
            # Daily View always renders with dynamics ON (no toggle)
            if date_fmt and ECON_CALENDAR_AVAILABLE:
                try:
                    _live_events_panel_empty = _render_econ_events_panel(
                        date_fmt, None,
                        dynamics_mode=True,
                        is_logged_in=_is_logged_in_empty,
                    )
                except Exception:
                    _live_events_panel_empty = None
            
            # Render clean empty state
            return "", html.Div([
                html.Div([
                    html.H3("No Articles", style={"color": HEADER_BG_COLOR, "marginBottom": "10px"}),
                    html.P(
                        "No articles were found for this date.",
                        style={"fontSize": "15px", "marginBottom": "5px"}
                    ),
                    html.P(
                        "If you expected content, check ingestion or filters.",
                        style={"fontSize": "13px", "color": "#666", "fontStyle": "italic"}
                    )
                ], style={
                    "backgroundColor": "#f9f9f9",
                    "padding": "20px",
                    "borderRadius": "4px",
                    "border": "1px solid #ddd",
                    "marginBottom": "20px"
                }),
                # Still show Economic Events if available
                *([_live_events_panel_empty] if _live_events_panel_empty is not None else []),
            ], style={"padding": "20px"})
        
        # Try to load rollup JSON
        rollup_dir = Path(r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\rollups\daily")
        rollup_file = rollup_dir / f"ROLLUP_DAILY_{date_str}__sum.json"
        
        if rollup_file.exists():
            try:
                with open(rollup_file, "r", encoding="utf-8") as fh:
                    rollup_json = json.load(fh)
                
                # Ensure date is in rollup_json meta if not present
                if "meta" not in rollup_json:
                    rollup_json["meta"] = {}
                if "date" not in rollup_json["meta"] or not rollup_json["meta"]["date"]:
                    # Convert YYYYMMDD to YYYY-MM-DD
                    try:
                        target_date = datetime.datetime.strptime(date_fmt, "%Y-%m-%d").date()
                        rollup_json["meta"]["date"] = date_fmt  # Already in YYYY-MM-DD format
                    except:
                        rollup_json["meta"]["date"] = date_fmt
                
                # Render rollup summary (Daily View always uses dynamics ON)
                _is_logged_in = bool(login_user_store)
                content = render_rollup_summary(
                    rollup_json, len(artifacts),
                    dynamics_mode=True,
                    is_logged_in=_is_logged_in,
                )
                return "", content
                
            except Exception as e:
                # Format title as "Preparation for {date}"
                try:
                    date_display = datetime.datetime.strptime(date_fmt, "%Y-%m-%d").strftime("%B %d, %Y")
                    error_title = f"Preparation for {date_display}"
                except:
                    error_title = "Preparation for Today"
                
                return "", html.Div([
                    html.H2(error_title, style={"color": HEADER_BG_COLOR, "marginBottom": "20px"}),
                    html.P(f"Error loading rollup: {e}", style={"color": "#dc3545"}),
                    html.P(f"File: {rollup_file.name}", style={"fontSize": "12px", "color": "#999"})
                ], style={"padding": "20px"})
        else:
            # Rollup doesn't exist — show helpful message plus live events from SQLite.
            # The events panel is a pure DB read; no LLM is called here.
            # Daily View always renders with dynamics ON (no toggle)
            _date_iso_no_rollup = date_fmt if date_fmt else None
            _is_logged_in_no_rollup = bool(login_user_store)
            _live_events_panel = None
            if _date_iso_no_rollup and ECON_CALENDAR_AVAILABLE:
                try:
                    _live_events_panel = _render_econ_events_panel(
                        _date_iso_no_rollup, None,
                        dynamics_mode=True,
                        is_logged_in=_is_logged_in_no_rollup,
                    )
                except Exception:
                    _live_events_panel = None

            # Format title as "Preparation for {date}"
            try:
                date_display = datetime.datetime.strptime(date_fmt, "%Y-%m-%d").strftime("%B %d, %Y")
                no_rollup_title = f"Preparation for {date_display}"
            except:
                no_rollup_title = "Preparation for Today"
            
            return "", html.Div([
                html.H2(no_rollup_title, style={"color": HEADER_BG_COLOR, "marginBottom": "20px"}),
                html.Div([
                    html.P(
                        "📊 Daily rollup not yet generated for this date.",
                        style={"fontSize": "16px", "marginBottom": "15px"}
                    ),
                    html.P(
                        f"Found {len(artifacts)} articles from {date_fmt}.",
                        style={"color": "#666", "marginBottom": "20px"}
                    ),
                    html.H4("Generate rollup:", style={"marginTop": "20px", "marginBottom": "10px"}),
                    html.Pre(
                        f'cd "c:\\Coding Projects\\TWIFO_Sharing"\npython generate_rollup_clean.py daily {date_fmt}',
                        style={
                            "backgroundColor": "#f5f5f5",
                            "padding": "15px",
                            "borderRadius": "4px",
                            "fontSize": "13px",
                            "fontFamily": "Consolas, monospace",
                            "border": "1px solid #ddd"
                        }
                    ),
                    html.P(
                        f"Looking for: {rollup_file.name}",
                        style={"fontSize": "11px", "color": "#999", "marginTop": "15px"}
                    )
                ], style={"backgroundColor": "#f9f9f9", "padding": "20px", "borderRadius": "4px"}),
                # Live events panel — queried fresh from SQLite on every render.
                # This section is completely independent of the snapshot above.
                *([_live_events_panel] if _live_events_panel is not None else []),
            ], style={"padding": "20px"})

    # --- Locate the selected artifact dict ---
    art = next(
        (a for a in artifacts if a["artifact_folder"] == folder_key),
        None
    )
    if art is None:
        return "", html.Div(
            f"Artifact folder not found: {folder_key}",
            style={"padding": "20px", "color": "#dc3545"}
        )

    # --- Strategy 1: render from sum.json ---
    if art["has_sum_json"]:
        try:
            with open(art["sum_json_path"], "r", encoding="utf-8") as fh:
                sum_json = json.load(fh)

            if SUMMARY_VIEW_AVAILABLE:
                if is_stub_summary(sum_json):
                    content = render_failed_summary(sum_json, art["artifact_folder"])
                else:
                    content = render_summary_view(
                        art["artifact_folder"],
                        sum_json,
                        display_provider=art.get("provider"),
                    )
            else:
                content = html.Div(
                    "Summary renderer not available.",
                    style={"padding": "40px", "textAlign": "center"}
                )
        except Exception as e:
            content = html.Div([
                html.H3("Error loading summary", style={"color": "#dc3545"}),
                html.P(str(e)),
                html.Code(art["sum_json_path"], style={"fontSize": "12px"})
            ], style={"padding": "20px"})

        # Wrap in split-screen layout for Daily View articles
        split_view = _build_split_screen_layout(content, art["artifact_folder"])
        return art["artifact_folder"], split_view

    # --- Strategy 2: embed sum.pdf in iframe ---
    if art["has_sum_pdf"]:
        # Build a relative artifacts/ URL the /view route already serves
        relative_pdf = f"artifacts/{art['artifact_folder']}/sum.pdf"
        content = html.Div([
            html.Div(
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "marginBottom": "10px"
                },
                children=[
                    html.H3(
                        art["title"],
                        style={"margin": "0", "color": HEADER_BG_COLOR}
                    ),
                    html.Span(
                        art["provider"],
                        style={"fontSize": "13px", "color": "#666"}
                    )
                ]
            ),
            html.Iframe(
                src=f"/view?file={relative_pdf}",
                style={
                    "width": "100%",
                    "height": "calc(100vh - 280px)",
                    "border": "1px solid #ddd",
                    "borderRadius": "4px"
                }
            )
        ], style={"padding": "10px"})

        # Wrap in split-screen layout for Daily View articles
        split_view = _build_split_screen_layout(content, art["artifact_folder"])
        return art["artifact_folder"], split_view

    # --- Strategy 3: nothing available ---
    artifacts_base = (
        Path(FILES_DIR) / "artifacts"
        if PATH_MANAGER_AVAILABLE and PATH_MANAGER
        else Path(FILES_DIR) / "artifacts"
    )
    expected_json = str(artifacts_base / art["artifact_folder"] / "sum.json")
    expected_pdf = str(artifacts_base / art["artifact_folder"] / "sum.pdf")

    content = html.Div([
        html.H3(
            "No Summary Available",
            style={"color": "#dc3545", "marginBottom": "15px"}
        ),
        html.P([
            "Neither ",
            html.Code("sum.json"),
            " nor ",
            html.Code("sum.pdf"),
            " was found for this article."
        ]),
        html.Div([
            html.P(
                "Expected paths:",
                style={"fontWeight": "bold", "marginBottom": "5px"}
            ),
            html.Code(
                expected_json,
                style={
                    "display": "block",
                    "marginBottom": "4px",
                    "fontSize": "12px",
                    "color": "#666"
                }
            ),
            html.Code(
                expected_pdf,
                style={
                    "display": "block",
                    "fontSize": "12px",
                    "color": "#666"
                }
            )
        ], style={
            "backgroundColor": "#f8f9fa",
            "padding": "15px",
            "borderRadius": "4px",
            "marginTop": "15px"
        })
    ], style={"padding": "20px"})

    # Wrap in split-screen layout for Daily View articles
    split_view = _build_split_screen_layout(content, art["artifact_folder"])
    return art["artifact_folder"], split_view


############################
# 9b) DAILY RECAP INTERACTIVE CALLBACKS
############################

# ── Card collapse toggle (clientside) ─────────────────────────────────────────
# One generic clientside callback handles ALL collapsible cards.
# It reads/writes localStorage under key "recap_card_<card_id>".
# The toggle button id pattern is  "<card_id>-toggle"
# The body div id pattern is        "<card_id>-body"
# The chevron span id pattern is    "<card_id>-chevron"

_CARD_IDS = [
    "card-today",
    "card-catalysts",
    "card-vol",
    "risk-flags",
    "card-yesterday",
    "card-forward",
    "card-articles",
    "econ-events",
]

for _cid in _CARD_IDS:
    app.clientside_callback(
        f"""
        function(n_clicks) {{
            var bodyId   = '{_cid}-body';
            var chevId   = '{_cid}-chevron';
            var storeKey = 'recap_card_{_cid}';

            var body  = document.getElementById(bodyId);
            var chev  = document.getElementById(chevId);
            if (!body) return window.dash_clientside.no_update;

            var isHidden = (body.style.display === 'none');
            // Toggle
            body.style.display = isHidden ? 'block' : 'none';
            if (chev) chev.innerText = isHidden ? '▲' : '▼';

            // Persist to localStorage
            try {{ localStorage.setItem(storeKey, isHidden ? 'open' : 'closed'); }} catch(e) {{}}

            return window.dash_clientside.no_update;
        }}
        """,
        Output(f"{_cid}-body", "style"),
        Input(f"{_cid}-toggle", "n_clicks"),
        prevent_initial_call=True,
    )

# ── Restore collapse state from localStorage on page load (clientside) ────────
app.clientside_callback(
    """
    function(children) {
        var cardIds = """ + str(_CARD_IDS).replace("'", '"') + """;
        cardIds.forEach(function(cid) {
            var storeKey = 'recap_card_' + cid;
            var saved;
            try { saved = localStorage.getItem(storeKey); } catch(e) { return; }
            if (!saved) return;
            var body = document.getElementById(cid + '-body');
            var chev = document.getElementById(cid + '-chevron');
            if (!body) return;
            if (saved === 'open')   { body.style.display = 'block'; if (chev) chev.innerText = '▲'; }
            if (saved === 'closed') { body.style.display = 'none';  if (chev) chev.innerText = '▼'; }
        });
        return window.dash_clientside.no_update;
    }
    """,
    Output("daily-view-content", "data-restored"),
    Input("daily-view-content", "children"),
    prevent_initial_call=True,
)

# ── Expand all / Collapse all (clientside) ────────────────────────────────────
app.clientside_callback(
    """
    function(n_expand, n_collapse) {
        var cardIds = """ + str(_CARD_IDS).replace("'", '"') + """;
        var triggered = dash_clientside.callback_context.triggered;
        if (!triggered || triggered.length === 0) return window.dash_clientside.no_update;
        var prop_id = triggered[0].prop_id;
        var doExpand = prop_id.includes('recap-expand-all');

        cardIds.forEach(function(cid) {
            var body = document.getElementById(cid + '-body');
            var chev = document.getElementById(cid + '-chevron');
            if (!body) return;
            body.style.display = doExpand ? 'block' : 'none';
            if (chev) chev.innerText = doExpand ? '▲' : '▼';
            try { localStorage.setItem('recap_card_' + cid, doExpand ? 'open' : 'closed'); } catch(e) {}
        });
        return window.dash_clientside.no_update;
    }
    """,
    Output("daily-view-content", "data-expand"),
    Input("recap-expand-all", "n_clicks"),
    Input("recap-collapse-all", "n_clicks"),
    prevent_initial_call=True,
)

# ── TLDR Show-all (clientside) ────────────────────────────────────────────────
app.clientside_callback(
    """
    function(n) {
        var el = document.getElementById('tldr-extra');
        var link = document.getElementById('tldr-showall');
        if (!el) return window.dash_clientside.no_update;
        var hidden = (el.style.display === 'none');
        el.style.display = hidden ? 'block' : 'none';
        if (link) link.innerText = hidden ? '← Show fewer' : 'Show all →';
        return window.dash_clientside.no_update;
    }
    """,
    Output("daily-view-content", "data-tldr"),
    Input("tldr-showall", "n_clicks"),
    prevent_initial_call=True,
)


# ── Tagged-list Show-all links (clientside — delegated) ──────────────────────
app.clientside_callback(
    """
    function(children) {
        if (window._taggedListHandlerAttached) return window.dash_clientside.no_update;
        document.addEventListener('click', function(e) {
            var el = e.target;
            if (!el || !el.id) return;
            // Pattern: <card_id>-<group_slug>-showall
            if (!el.id.endsWith('-showall')) return;
            e.preventDefault();
            // Derive overflow id by replacing -showall with -overflow
            var overflowId = el.id.replace('-showall', '-overflow');
            var overflow = document.getElementById(overflowId);
            if (!overflow) return;
            var hidden = (overflow.style.display === 'none');
            overflow.style.display = hidden ? 'block' : 'none';
            el.innerText = hidden ? '← Show fewer' : el.dataset.originalText || 'Show all →';
            if (!el.dataset.originalText) el.dataset.originalText = el.innerText;
        });
        window._taggedListHandlerAttached = true;
        return window.dash_clientside.no_update;
    }
    """,
    Output("daily-view-content", "data-taglist"),
    Input("daily-view-content", "children"),
    prevent_initial_call=True,
)


############################
# 10) RUN
############################

if __name__ == "__main__":
    app.run(debug=True, port=8065, host='127.0.0.1')

