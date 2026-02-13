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
}


def _detect_provider(folder_name: str) -> str:
    """Detect human-readable provider name from a folder/file name prefix."""
    for prefix, name in PREFIX_MAP.items():
        if folder_name.startswith(prefix):
            return name
    return "Unknown"


def _title_from_folder(folder_name: str) -> str:
    """
    Derive a human-readable title from an artifact folder name.

    Strips the leading provider prefix and trailing date/suffix tokens,
    replaces underscores with spaces, and title-cases the result.
    """
    # Remove provider prefix
    cleaned = folder_name
    for prefix in PREFIX_MAP:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    # Remove date token (YYYYMMDD) that may appear at the start
    cleaned = re.sub(r"^\d{8}_?", "", cleaned)

    # Remove common trailing suffixes
    for suffix in ("_w", "_d", "_m"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break

    # Underscore → space, collapse whitespace, title-case
    title = cleaned.replace("_", " ").strip()
    return title.title() if title else folder_name


def get_yesterday_artifacts() -> List[Dict]:
    """
    Scan ARTIFACTS_DIR for artifact folders whose names start with
    yesterday's YYYYMMDD date prefix and return structured metadata.

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
    debug = os.getenv("TWIFO_DEBUG_DAILY_VIEW")

    yesterday = date.today() - timedelta(days=1)
    date_str = yesterday.strftime("%Y%m%d")
    date_fmt = yesterday.strftime("%Y-%m-%d")

    if debug:
        print(f"[DEBUG daily_view] Yesterday: {date_fmt} ({date_str})")

    if not ARTIFACTS_DIR.is_dir():
        if debug:
            print(f"[DEBUG daily_view] ARTIFACTS_DIR missing: {ARTIFACTS_DIR}")
        return []

    # Collect all matching sub-folders
    # Convention: folder name contains _YYYYMMDD_ somewhere (usually after prefix)
    matched_dirs: List[Path] = sorted(
        d for d in ARTIFACTS_DIR.iterdir()
        if d.is_dir() and f"_{date_str}_" in d.name
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

        # Extract provider and title — prefer sum.json meta when available
        provider = _detect_provider(folder_name)
        title = _title_from_folder(folder_name)

        if has_json:
            try:
                with open(sum_json_path, "r", encoding="utf-8") as fh:
                    meta = json.load(fh).get("meta", {})
                provider = meta.get("provider", provider)
                title = meta.get("title", title)
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
            "date_fmt": date_fmt,
            "has_sum_json": has_json,
            "has_sum_pdf": has_pdf,
            "sum_json_path": str(sum_json_path) if has_json else "",
            "sum_pdf_path": str(sum_pdf_path) if has_pdf else "",
        })

    if debug:
        print(f"[DEBUG daily_view] Matched artifacts: {len(results)}")

    return results
