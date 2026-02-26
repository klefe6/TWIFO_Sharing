"""
TWIFO App Helper Functions
Purpose: Artifact-driven helpers for the TWIFO Dash application Daily View
Author: Kevin Lefebvre
Last Updated: 2026-02-13
"""

import os
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import List, Dict


# Configuration
FILES_DIR = Path(
    r"C:\Users\H&CDanHughes\Hughes & Company"
    r"\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE"
)
ARTIFACTS_DIR = FILES_DIR / "artifacts"

# Provider prefix map (folder names use the same prefix convention as PDFs)
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
    "O_":     "Others",
}


def _parse_folder_segments(folder_name: str) -> dict:
    """
    Parse artifact folder name into segments.

    Format: YYYYMMDD__PROVIDER__title_slug__hash
    Example: 20260211__GM__gm_commodity_analyst_20260211_u__677f0794fa

    Returns:
        dict with keys: date_part, provider_code, slug, hash_part
    """
    parts = folder_name.split("__")
    if len(parts) >= 3:
        return {
            "date_part": parts[0],
            "provider_code": parts[1],
            "slug": parts[2] if len(parts) > 2 else "",
            "hash_part": parts[3] if len(parts) > 3 else "",
        }
    # Fallback for unexpected format
    return {
        "date_part": "",
        "provider_code": "",
        "slug": folder_name,
        "hash_part": "",
    }


def _detect_provider(folder_name: str) -> str:
    """Detect human-readable provider name from artifact folder name."""
    seg = _parse_folder_segments(folder_name)
    code = seg["provider_code"]
    if code:
        # Look up "GM_" in PREFIX_MAP for provider code "GM"
        mapped = PREFIX_MAP.get(f"{code}_")
        if mapped:
            return mapped
        # Code itself might already be a full name or unmapped code
        return code
    return "Unknown"


def _extract_frequency_from_slug(slug: str) -> str:
    """
    Extract frequency suffix from slug.
    
    Returns: 'w', 'd', 'm', 'q', 'y', or 'u' (unknown)
    """
    match = re.search(r"[_\-]([wdmuqy])$", slug)
    return match.group(1) if match else "u"


def _title_from_folder(folder_name: str) -> str:
    """
    Derive a human-readable title from an artifact folder name.

    Format: YYYYMMDD__PROVIDER__title_slug__hash
    Extracts the slug segment, strips the provider prefix, date, and
    frequency suffix, then title-cases.
    """
    seg = _parse_folder_segments(folder_name)
    slug = seg["slug"]
    provider_code = seg["provider_code"].lower()

    if not slug:
        return folder_name

    # Remove leading provider code from slug (e.g., "gm_commodity..." → "commodity...")
    if provider_code and slug.lower().startswith(f"{provider_code}_"):
        slug = slug[len(provider_code) + 1:]

    # Remove embedded date tokens (YYYYMMDD)
    slug = re.sub(r"_?\d{8}", "", slug)

    # Remove trailing frequency suffixes (_w, _d, _m, _u, _q)
    slug = re.sub(r"[_\-]([wdmuqy])$", "", slug)

    # Underscore → space, collapse whitespace
    title = slug.replace("_", " ").strip()
    title = re.sub(r"\s+", " ", title)
    
    # Replace single dash with space, but preserve double dash (e.g., "--02-10")
    title = re.sub(r'(?<!-)-(?!-)', ' ', title)
    
    # Title case each word
    return title.title() if title else folder_name


def resolve_display_title(artifact_folder: str, meta_title: str = None, sum_json: dict = None) -> str:
    """
    Shared title resolver used across all views (Buttons, Daily View, Library).
    
    Resolution priority:
        1. meta.title if present, non-empty, and looks clean (no underscores/dates)
        2. Derived title from artifact_folder using _title_from_folder
        3. Final fallback to artifact_folder if both fail
    
    Args:
        artifact_folder: Artifact folder name (e.g., "20260211__GM__weekly_municipal...")
        meta_title: Optional title from sum.json meta.title
        sum_json: Optional full sum.json dict (will extract meta.title if provided)
    
    Returns:
        Clean, human-readable title string
    
    Examples:
        >>> resolve_display_title("20260211__O__weekly_municipal_monitor_seasonal_strength_02_10_20260211_w__abc123")
        'Weekly Municipal Monitor Seasonal Strength 02 10'
        
        >>> resolve_display_title("20260211__GM__foo__abc", meta_title="Clean Title from LLM")
        'Clean Title from LLM'
    """
    # Extract meta_title from sum_json if provided
    if sum_json and not meta_title:
        meta_title = sum_json.get("meta", {}).get("title", "")
    
    # Priority 1: Use meta.title if it's clean (no underscores or embedded dates)
    if meta_title and isinstance(meta_title, str):
        meta_title = meta_title.strip()
        if meta_title and "_" not in meta_title and not re.search(r'\d{8}', meta_title):
            return meta_title
    
    # Priority 2: Derive clean title from folder name
    derived_title = _title_from_folder(artifact_folder)
    if derived_title and derived_title != artifact_folder:
        return derived_title
    
    # Priority 3: Fallback to folder name (should rarely happen)
    return artifact_folder


def get_yesterday_artifacts() -> List[Dict]:
    """
    Scan ARTIFACTS_DIR for artifact folders from yesterday and return structured metadata.
    
    Returns:
        List of dicts with keys:
            artifact_folder  – folder name (stable identifier)
            provider         – human-readable provider name
            title            – article title
            date_fmt         – YYYY-MM-DD formatted date string
            has_sum_json     – bool
            has_sum_pdf      – bool
            sum_json_path    – str path or ""
            sum_pdf_path     – str path or ""
    """
    yesterday = date.today() - timedelta(days=1)
    return get_artifacts_for_date(yesterday)


def get_artifacts_for_date(target_date: date) -> List[Dict]:
    """
    Scan ARTIFACTS_DIR for artifact folders matching a specific date.
    
    Args:
        target_date: The date to search for (as date object)
    
    Returns:
        List of dicts with artifact metadata including frequency
    """
    debug = os.getenv("TWIFO_DEBUG_DAILY_VIEW")

    date_str = target_date.strftime("%Y%m%d")
    date_fmt = target_date.strftime("%Y-%m-%d")

    if debug:
        print(f"[DEBUG daily_view] Target date: {date_fmt} ({date_str})")

    if not ARTIFACTS_DIR.is_dir():
        if debug:
            print(f"[DEBUG daily_view] ARTIFACTS_DIR missing: {ARTIFACTS_DIR}")
        return []

    # Collect all matching sub-folders
    # New convention: YYYYMMDD__PROVIDER__slug__hash
    # Old convention (legacy): folders may contain _YYYYMMDD_ anywhere
    matched_dirs: List[Path] = sorted(
        d for d in ARTIFACTS_DIR.iterdir()
        if d.is_dir() and (d.name.startswith(f"{date_str}__") or f"_{date_str}_" in d.name)
    )

    if debug:
        print(f"[DEBUG daily_view] Folders discovered: {len(matched_dirs)}")

    # Basename collision tracker
    seen_basenames: Dict[str, str] = {}

    results: List[Dict] = []
    for art_dir in matched_dirs:
        folder_name = art_dir.name

        sum_json_path = art_dir / "sum.json"
        sum_pdf_path = art_dir / "sum.pdf"
        has_json = sum_json_path.is_file()
        has_pdf = sum_pdf_path.is_file()

        # Extract provider, title, and frequency from folder name
        provider = _detect_provider(folder_name)
        title = _title_from_folder(folder_name)
        
        # Extract frequency from slug
        seg = _parse_folder_segments(folder_name)
        frequency_code = _extract_frequency_from_slug(seg["slug"])

        # Prefer sum.json meta when available, but fallback to folder-derived for bad values
        if has_json:
            try:
                with open(sum_json_path, "r", encoding="utf-8") as fh:
                    meta = json.load(fh).get("meta", {})
                json_provider = meta.get("provider", "")
                json_title = meta.get("title", "")
                json_horizon = meta.get("horizon", "")
                
                # Use json provider only if it's not "O" (Others), otherwise keep folder-derived
                if json_provider and json_provider != "O":
                    provider = json_provider
                
                # Use json title only if it looks cleaned (no underscores or embedded dates)
                # If it still has underscores or looks like filename, use folder-derived
                if json_title and "_" not in json_title and not re.search(r'\d{8}', json_title):
                    title = json_title
                # else: keep folder-derived title which is already cleaned
                
                # Use horizon from meta if available and not "u", otherwise use extracted frequency
                if json_horizon and json_horizon != "u":
                    frequency_code = json_horizon
            except Exception:
                pass  # fall back to folder-derived values

        # Collision detection (basename = folder_name by convention)
        if folder_name in seen_basenames:
            print(f"Basename collision detected for: {folder_name}")
        seen_basenames[folder_name] = str(art_dir)

        results.append({
            "artifact_folder": folder_name,
            "provider": provider,
            "title": title,
            "frequency_code": frequency_code,  # 'w', 'd', 'm', 'q', 'y', or 'u'
            "date_fmt": date_fmt,
            "has_sum_json": has_json,
            "has_sum_pdf": has_pdf,
            "sum_json_path": str(sum_json_path) if has_json else "",
            "sum_pdf_path": str(sum_pdf_path) if has_json else "",
        })

    if debug:
        print(f"[DEBUG daily_view] Matched artifacts: {len(results)}")

    return results
