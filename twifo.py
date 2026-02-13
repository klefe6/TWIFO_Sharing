import os
import re
import datetime
import json
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from typing import Optional, List, Dict

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
    from twifo_app import get_yesterday_artifacts
    DAILY_VIEW_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Daily view helper not available: {e}")
    DAILY_VIEW_AVAILABLE = False
    get_yesterday_artifacts = None

# compute today's ISO date once:
TODAY = datetime.date.today().isoformat()  # e.g. "2025-05-21"

import urllib.parse

import dash
from dash import dcc, html, dash_table, Input, Output, State, ctx
from dash.exceptions import PreventUpdate
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
                print(f"[ROLLUP DEBUG] ✓ Successfully loaded {rollup_path.name} (schema: {schema})")
                return data
            else:
                print(f"[ROLLUP DEBUG] ✗ Schema mismatch in {rollup_path.name}")
                print(f"  Expected: 'twifo.rollup.v1'")
                print(f"  Found: '{schema}' (type: {type(schema).__name__})")
                print(f"  Top-level keys: {list(data.keys())[:10]}")
                return None
                
    except json.JSONDecodeError as e:
        print(f"[ROLLUP DEBUG] ✗ JSON parse error in {rollup_path.name}")
        print(f"  Error: {e}")
        print(f"  Line {e.lineno}, Column {e.colno}: {e.msg}")
        return None
    except UnicodeDecodeError as e:
        print(f"[ROLLUP DEBUG] ✗ Encoding error in {rollup_path.name}")
        print(f"  Error: {e}")
        return None
    except Exception as e:
        print(f"[ROLLUP DEBUG] ✗ Unexpected error loading {rollup_path.name}")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Error message: {e}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")
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
                    print(f"  ✓ Parsed successfully: date={metadata.get('date')}")
                    rollups.append({
                        "path": file_path,
                        "fname": fname,
                        "kind": "rollup_daily",
                        "date": metadata["date"],
                        "date_yyyymmdd": metadata["date_yyyymmdd"],
                    })
                else:
                    print(f"  ✗ Failed to parse filename (does not match expected pattern)")
                    print(f"    Expected: ROLLUP_DAILY_YYYYMMDD__sum.json")
        except Exception as e:
            print(f"[ROLLUP SCAN] ERROR scanning daily dir: {e}")
            import traceback
            print(traceback.format_exc())
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
                    print(f"  ✓ Parsed successfully: {metadata.get('start_date')} to {metadata.get('end_date')}")
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
                    print(f"  ✗ Failed to parse filename (does not match expected pattern)")
                    print(f"    Expected: ROLLUP_WEEKLY_YYYYMMDD__sum.json")
        except Exception as e:
            print(f"[ROLLUP SCAN] ERROR scanning weekly dir: {e}")
            import traceback
            print(traceback.format_exc())
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
                                                    "width": "300px",
                                                    "minWidth": "300px",
                                                    "overflowY": "auto",
                                                    "borderRight": "1px solid #ddd",
                                                    "paddingRight": "15px"
                                                },
                                                children=[
                                                    html.H3(
                                                        "Yesterday's Articles",
                                                        style={
                                                            "marginBottom": "15px",
                                                            "color": HEADER_BG_COLOR
                                                        }
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
            print(f"  ✗ Filtered out by date range (before start_date: {start_date})")
            continue
        if end_date and rollup_date > datetime.datetime.fromisoformat(end_date).date():
            print(f"  ✗ Filtered out by date range (after end_date: {end_date})")
            continue
        
        # Load rollup JSON for UI data
        rollup_json = load_rollup_json(Path(rollup_info["path"]))
        if rollup_json is None:
            print(f"  ✗ Failed to load JSON - skipping this rollup")
            continue
        
        ui_data = rollup_json.get("ui", {})
        if not ui_data:
            print(f"  ⚠ WARNING: Rollup JSON loaded but 'ui' key is missing or empty")
        else:
            print(f"  ✓ Successfully loaded, UI title: {ui_data.get('title', 'N/A')}")
        
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
# 8) DAILY VIEW CALLBACKS
############################

@app.callback(
    [
        Output("daily-articles-store", "data"),
        Output("daily-view-article-list", "children")
    ],
    [
        Input("login-status", "data"),
        Input("main-tabs", "value")
    ],
    prevent_initial_call=False
)
def populate_daily_view_sidebar(login_status, active_tab):
    """
    Populate the Daily View sidebar from artifact folders.

    Only calls get_yesterday_artifacts() when the user is logged in
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

    try:
        artifacts = get_yesterday_artifacts()
    except Exception as e:
        print(f"[ERROR] get_yesterday_artifacts failed: {e}")
        return [], [
            html.P(
                f"Error loading artifacts: {e}",
                style={"color": "#dc3545"}
            )
        ]

    if not artifacts:
        return [], [
            html.P(
                "No articles found for yesterday.",
                style={
                    "color": "#999",
                    "fontStyle": "italic",
                    "padding": "20px",
                    "textAlign": "center"
                }
            )
        ]

    # --- build sidebar buttons keyed by artifact_folder ---
    sidebar_buttons = [
        html.Button(
            [
                html.Div(
                    "Daily Summary",
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

    for art in artifacts:
        # Availability badge
        if art["has_sum_json"]:
            badge_text = "JSON"
            badge_color = "#28a745"
        elif art["has_sum_pdf"]:
            badge_text = "PDF"
            badge_color = "#007bff"
        else:
            badge_text = "—"
            badge_color = "#999"

        sidebar_buttons.append(
            html.Button(
                [
                    html.Div(
                        style={
                            "display": "flex",
                            "justifyContent": "space-between",
                            "alignItems": "center",
                            "marginBottom": "3px"
                        },
                        children=[
                            html.Span(
                                art["provider"],
                                style={
                                    "fontSize": "11px",
                                    "color": "#666",
                                    "fontWeight": "500"
                                }
                            ),
                            html.Span(
                                badge_text,
                                style={
                                    "fontSize": "10px",
                                    "color": "#fff",
                                    "backgroundColor": badge_color,
                                    "padding": "1px 6px",
                                    "borderRadius": "3px"
                                }
                            )
                        ]
                    ),
                    html.Div(
                        art["title"],
                        style={
                            "fontSize": "13px",
                            "lineHeight": "1.3",
                            "overflow": "hidden",
                            "textOverflow": "ellipsis",
                            "display": "-webkit-box",
                            "WebkitLineClamp": "2",
                            "WebkitBoxOrient": "vertical"
                        }
                    )
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


@app.callback(
    [
        Output("daily-selected-artifact", "data"),
        Output("daily-view-content", "children")
    ],
    Input({"type": "daily-article-btn", "index": dash.dependencies.ALL}, "n_clicks"),
    State("daily-articles-store", "data"),
    prevent_initial_call=True
)
def display_daily_article_summary(n_clicks_list, artifacts):
    """
    Render the right-panel content for the selected artifact folder.

    Rendering strategy:
      1. has_sum_json  → load JSON and render web summary
      2. has_sum_pdf   → embed PDF via iframe
      3. neither       → show clear message with missing paths
    """
    if not ctx.triggered:
        raise PreventUpdate

    triggered_id = ctx.triggered_id
    if not triggered_id:
        raise PreventUpdate

    folder_key = triggered_id.get("index")

    # --- Daily Summary placeholder ---
    if folder_key == "__daily_summary__":
        return "", html.Div([
            html.H2(
                "Daily Summary",
                style={"color": HEADER_BG_COLOR, "marginBottom": "20px"}
            ),
            html.P(
                "Daily rollup summary coming soon...",
                style={"color": "#999", "fontStyle": "italic"}
            ),
            html.P(
                f"Found {len(artifacts)} artifacts for yesterday.",
                style={"marginTop": "15px"}
            )
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
                    content = render_summary_view(art["artifact_folder"], sum_json)
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

        return art["artifact_folder"], content

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

        return art["artifact_folder"], content

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

    return art["artifact_folder"], content


############################
# 9) RUN
############################

if __name__ == "__main__":
    app.run(debug=True, port=8065, host='127.0.0.1')

