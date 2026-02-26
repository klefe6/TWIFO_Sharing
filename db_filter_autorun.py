import os
import re
import shutil
import sys
import datetime as dt
from pathlib import Path
import subprocess
import time
import hashlib
import tempfile
import json
import argparse

# Optional: fast PDF text sniff
try:
    from pypdf import PdfReader  # preferred over PyPDF2
    PYPDF_AVAILABLE = True
except Exception:
    PYPDF_AVAILABLE = False

# Import authentication module (single source-of-truth)
try:
    from auth_env import get_openai_api_key, describe_key, assert_openai_auth_ok
    AUTH_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Auth module not available: {e}")
    AUTH_AVAILABLE = False
    get_openai_api_key = None
    describe_key = None
    assert_openai_auth_ok = None

# Import summarization module
try:
    from summarize_pdf import (
        summarize_pdf,
        summarize_text,
        extract_text,
        _content_hash,
        TRIAGE_ENABLED,
        is_stub,
        SummaryWriteFailedError,
    )
    SUMMARIZE_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Summarization not available: {e}")
    SUMMARIZE_AVAILABLE = False
    summarize_text = None
    extract_text = None
    _content_hash = None
    TRIAGE_ENABLED = False
    SummaryWriteFailedError = Exception  # Fallback to generic Exception

# Ingest dedupe: doc_id + deterministic base filename (no PDF content hashing)
try:
    from ingest_dedup import (
        canonicalize_url,
        doc_id_from_canonical_url,
        slugify_title,
        deterministic_base_filename,
        normalize_canonical_url,
        preflight_check,
        ensure_original_pdf_in_export,
        bundle_complete,
        claim_acquire,
        claim_release,
        validate_and_publish,
        doc_insert_pending,
        doc_mark_status,
        STATUS_FAILED,
    )
    DEDUPE_AVAILABLE = True
except ImportError:
    DEDUPE_AVAILABLE = False
    canonicalize_url = None
    doc_id_from_canonical_url = None
    slugify_title = None
    deterministic_base_filename = None
    normalize_canonical_url = None
    preflight_check = None
    ensure_original_pdf_in_export = None
    bundle_complete = None
    claim_acquire = None
    claim_release = None
    validate_and_publish = None
    doc_insert_pending = None
    doc_mark_status = None
    STATUS_FAILED = None

# Import PDF rendering module
try:
    from summary_render import render_summary_pdf
    PDF_RENDER_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] PDF rendering not available: {e}")
    PDF_RENDER_AVAILABLE = False
    render_summary_pdf = None

# Import rollup generation
try:
    from generate_rollup_clean import generate_daily_rollup, save_daily_rollup
    ROLLUP_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Rollup generation not available: {e}")
    ROLLUP_AVAILABLE = False
    generate_daily_rollup = None
    save_daily_rollup = None

# Import path manager for new file layout
try:
    from path_manager import TWIFOPathManager, get_path_manager
    PATH_MANAGER_AVAILABLE = True
except ImportError:
    PATH_MANAGER_AVAILABLE = False
    TWIFOPathManager = None
    get_path_manager = None

# =============================
# CONFIG — EDIT THESE ONCE
# =============================
DROPBOX_ROOT = Path(r"C:\Users\H&CDanHughes\Rdatabase Dropbox\R D")
ROOTS = ["Current", "Archives", "Current Back"]

EXPORT_DIR = Path(
    r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE"
)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# Initialize path manager for new file layout
if PATH_MANAGER_AVAILABLE:
    PATH_MANAGER = get_path_manager(EXPORT_DIR)
    print("[INFO] Path manager initialized - using new file layout")
    print(f"  Originals: {PATH_MANAGER.originals_dir}")
    print(f"  Artifacts: {PATH_MANAGER.artifacts_dir}")
else:
    PATH_MANAGER = None
    print("[WARN] Path manager not available - using legacy file layout")

RUN_WEBSITE_UPDATE = True
BAT_PATH = Path(r"C:\Program Files\Coding Projects\TWIFO_Sharing\reboot_twifo.bat")

START_DELAY_SECONDS = 0
ENABLE_DATE_RANGE_SELECTION = True

# --- Reliability knobs ---
MAX_READ_RETRIES = 10             # retry opening/reading a file (dropbox lock / partial sync)
READ_RETRY_SLEEP = 2              # seconds between retries
MIN_PDF_TEXT_CHARS = 2000         # if extracted chars <= this, treat as image-only and OCR-needed
FORCE_OCR_ON_LOW_TEXT = True      # attempt OCR (via your summarize_pdf pipeline) for image-only PDFs
SKIP_SUMMARY_IF_UNREADABLE = True # if still unreadable, don't call LLM summarizer

DEFAULT_KEEP = [
    "Annual","Weekly","Monthly","Quarterly",
    "Commodity","Commodities","Gold","Bitcoin","SOFR","Interest Rates", "CTAs", "CFTC", "CME", "BNY",
    "Macro Insight","Metals","Silver",
    # Sector triggers
    "Health Care","Real Estate","XLB","Materials","XLU","Utilities",
    "Consumer Staples","Financials","Consumer Discretionary","Energy","Industrials",
    "Communications","Technology","Consumer Goods",
]
DEFAULT_SKIP = [
    "Earnings", "Daily", "Morning", "Equity", "Stocks", "Briefing", "Brief", "Intell", "Commentary",
    "Oil Data", "Regional",
    "Australia", "New Zealand", "UK", "Germany", "France", "Italy", "Spain",
    "China Property", "Americas Business", "Biotech",
    "Switzerland", "Sweden", "Norway", "Denmark", "Netherlands", "Belgium",
    "Japan", "Taiwan", "India", "Brazil", "Mexico", "Russia", "Turkey", "South Africa",
    "Indonesia", "Malaysia", "Hong Kong", "Singapore", "Philippines", "Vietnam", "Thailand",
]

CATEGORY_PREFIXES = {
    "BOA":   ["BofA"],
    "BA":    ["Barclays","BARC"],
    "BR":    ["BlackRock","BLK"],
    "DB":    ["Deutsche Bank","DB","DBK"],
    "GM":    ["Goldman","Goldman Sachs","GS"],
    "HT":    ["HighTower Research"],
    "JPM":   ["JP Morgan","JPM","JPMorgan"],
    "MZ":    ["Mizuho"],
    "TSL":   ["TSLombard","TS Lombard"],
    "T":     ["TWIFO"],
    "WF":    ["Wells Fargo","WFC"],
    "SEB":   ["SEB Commodities","SEB"],
    "R":     ["Rabobank"],
    "MUFG":  ["MUFG","Macro2Markets","Mitsubishi UFJ"],
    "ANZ":   ["ANZ","Australia & New Zealand Banking Group"],
    "BCA":   ["BCA"],
    "BNPP":  ["BNPP","BNP Paribas"],
    "BNY":   ["BNY","BNY Mellon"],
    "CACIB": ["CACIB","Crédit Agricole CIB"],
    "CITI":  ["Citi","Citigroup","C"],
    "HSBC":  ["HSBC"],
    "ING":   ["ING","ING Group"],
    "MS":    ["Morgan Stanley","MS"],
    "NOM":   ["Nomura"],
    "RBC":   ["RBC","Royal Bank of Canada"],
    "SG":    ["SocGen","Société Générale"],
    "STI":   ["Stifel"],
    "TME":   ["TME"],
    "UBS":   ["UBS"],
    "O":     ["Other","Others","OTHERS"]
}

FREQ_KEYS = {
    "y": re.compile(r"(?i)\bAnnual\b"),
    "q": re.compile(r"(?i)\bQuarterly\b"),
    "m": re.compile(r"(?i)\bMonthly\b"),
    "w": re.compile(r"(?i)\bWeekly\b"),
}

KEEP_PAT = re.compile(r"(?i)\b(" + "|".join(map(re.escape, DEFAULT_KEEP)) + r")(?=\W|$)")
SKIP_PAT = re.compile(r"(?i)\b(" + "|".join(map(re.escape, DEFAULT_SKIP)) + r")\b")


# =============================
# HELPERS (reliability-focused)
# =============================
def check_ocr_env():
    def run(cmd):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, shell=False)
            return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
        except FileNotFoundError:
            return 127, "", "not found"
        except Exception as e:
            return 1, "", str(e)

    checks = {
        "ocrmypdf": ["ocrmypdf", "--version"],
        "tesseract": ["tesseract", "--version"],
        "ghostscript_gswin64c": ["gswin64c", "--version"],
        "ghostscript_gs": ["gs", "--version"],
    }

    print("\n[OCR ENV CHECK]")
    for name, cmd in checks.items():
        rc, out, err = run(cmd)
        status = "OK" if rc == 0 else f"FAIL(rc={rc})"
        print(f"- {name}: {status}")
        if out:
            print(f"  stdout: {out.splitlines()[0]}")
        if err and rc != 0:
            print(f"  stderr: {err.splitlines()[-1]}")
    print()
def md5_hash(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def wait_until_readable(path: Path, retries=MAX_READ_RETRIES, sleep_s=READ_RETRY_SLEEP) -> bool:
    """
    Dropbox can leave files partially synced or locked. This waits until we can open+read a chunk.
    """
    for i in range(retries):
        try:
            if not path.exists():
                time.sleep(sleep_s)
                continue
            # Try reading first 64KB
            with open(path, "rb") as f:
                f.read(65536)
            return True
        except Exception:
            time.sleep(sleep_s)
    return False

def safe_copy_atomic(src: Path, dst: Path) -> bool:
    """
    Copy to a temp file first, then move into place.
    Prevents half-written dst files.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")

    try:
        if tmp.exists():
            tmp.unlink()
        shutil.copy2(src, tmp)
        # Atomic replace
        os.replace(tmp, dst)
        return True
    except Exception as e:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        print(f"[ERR] Atomic copy failed: {src} -> {dst}: {e}")
        return False

def sniff_pdf_text_chars(pdf_path: Path, max_pages=2) -> int:
    """
    Quick check: if PDF has extractable text, pypdf will pull some.
    If it returns near zero, it's likely image-only and needs OCR.
    """
    if not PYPDF_AVAILABLE:
        return MIN_PDF_TEXT_CHARS  # don't block if we can't sniff

    try:
        reader = PdfReader(str(pdf_path))
        chars = 0
        for i, page in enumerate(reader.pages[:max_pages]):
            t = page.extract_text() or ""
            chars += len(t.strip())
        return chars
    except Exception:
        # If even reading fails, treat as unreadable
        return 0

def sniff_pdf_text_chars_pymupdf(pdf_path: Path, max_pages=2) -> int:
    """
    Better sniff than pypdf for many PDFs.
    Returns 0 if PyMuPDF not available.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        chars = 0
        for i in range(min(max_pages, doc.page_count)):
            t = (doc.load_page(i).get_text("text") or "").strip()
            chars += len(t)
        doc.close()
        return chars
    except Exception:
        return 0

def write_failed_summary_stub(dst_pdf: Path, reason: str) -> None:
    """
    Creates a __sum.json that clearly indicates extraction failure so the website can display
    'Needs OCR' instead of hallucinated content.
    
    Returns unified schema matching _failed_stub() from summarize_pdf.py
    """
    stub = {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {
            "source_pdf": dst_pdf.name,
            "generated_at_iso": dt.datetime.now().isoformat(timespec="seconds"),
            "model": None,
            "provider": "O",
            "title": dst_pdf.stem,
            "published_date": "",
            "horizon": "u",
        },
        "ui": {"header_pills": []},
        "extraction": {
            "status": "failed",
            "reason": reason,
        },
        "sections": {
            "what_moved_today": [],
            "what_can_move_tomorrow": [],
            "trade_ideas": [],
            "tldr": [],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }
    summary_json_path = dst_pdf.parent / f"{dst_pdf.stem}__sum.json"
    summary_json_path.write_text(json.dumps(stub, indent=2), encoding="utf-8")

def ocr_pdf_in_place(input_pdf: Path, output_pdf: Path) -> tuple[bool, str]:
    """
    Runs OCR using ocrmypdf -> output_pdf.
    Returns (success, message).
    """
    try:
        # If output exists, replace it
        if output_pdf.exists():
            output_pdf.unlink()

        cmd = [
            "ocrmypdf",
            "--force-ocr",          # always OCR even if it thinks there is text
            "--deskew",
            "--rotate-pages",
            "--output-type", "pdf",
            str(input_pdf),
            str(output_pdf),
        ]

        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode == 0 and output_pdf.exists() and output_pdf.stat().st_size > 0:
            return True, "ocrmypdf ok"
        return False, f"ocrmypdf failed rc={p.returncode} stderr={p.stderr[-500:]}"
    except FileNotFoundError:
        return False, "ocrmypdf not found on PATH"
    except Exception as e:
        return False, f"ocrmypdf exception: {e}"

def ocr_pdf_to_text_fallback(pdf_path: Path, dpi: int = 250, max_pages: int | None = None) -> tuple[bool, str, str]:
    """
    OCR via PyMuPDF render -> pytesseract. Returns (ok, msg, text).
    This bypasses ocrmypdf + ghostscript completely.
    """
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        return False, f"PyMuPDF (fitz) not installed: {e}", ""

    try:
        import pytesseract
        from PIL import Image
        import io
    except Exception as e:
        return False, f"pytesseract/Pillow not installed: {e}", ""

    try:
        doc = fitz.open(str(pdf_path))
        n = doc.page_count
        last = n if max_pages is None else min(n, max_pages)

        chunks = []
        for i in range(last):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            txt = (pytesseract.image_to_string(img) or "").strip()

            if txt:
                chunks.append(f"\n\n--- PAGE {i+1}/{n} ---\n{txt}")

        doc.close()
        text = "\n".join(chunks).strip()
        if not text:
            return False, "OCR fallback produced empty text", ""

        return True, f"OCR fallback OK (pages={last}, chars={len(text)})", text
    except Exception as e:
        return False, f"OCR fallback exception: {e}", ""

def month_candidates(d: dt.date) -> list[str]:
    return [d.strftime("%B"), d.strftime("%b")]

def day_folder_candidates(d: dt.date) -> list[str]:
    abbr = d.strftime("%b")
    full = d.strftime("%B")
    day1 = str(d.day)
    day2 = f"{d.day:02d}"
    return [f"{abbr} {day1}", f"{abbr} {day2}", f"{full} {day1}", f"{full} {day2}"]

def pick_provider_prefix(provider_folder_name: str) -> tuple[str, bool]:
    name_l = provider_folder_name.lower().strip()
    for code, syns in CATEGORY_PREFIXES.items():
        if any(name_l.startswith(s.lower()) for s in syns):
            return code, (code == "GM")
    return "O", False

def frequency_code(filename: str) -> str:
    for k, pat in FREQ_KEYS.items():
        if pat.search(filename):
            return k
    return "u"

def normalize_base_name(prefix: str, raw_name: str, year: int) -> tuple[str, str]:
    orig = re.sub(r"^(BofA|MUFG|ING)[\s_-]+", "", raw_name)
    file_base = orig.rsplit(".", 1)[0]

    file_base = re.sub(
        rf"^(?:{re.escape(prefix)}[-_\s]+)+",
        "",
        file_base,
        flags=re.IGNORECASE
    )
    file_base = re.sub(rf"\b\d*{year}\d*\b", "", file_base)
    file_base = file_base.replace("_", " ").strip()
    file_base = re.sub(r"\s{{2,}}", " ", file_base)
    return orig, file_base

def build_base_paths(root_name: str, d: dt.date) -> list[Path]:
    paths = []
    for m in month_candidates(d):
        for day_folder in day_folder_candidates(d):
            paths.append(DROPBOX_ROOT / root_name / str(d.year) / m / day_folder)
    return paths

def iter_provider_dirs(day_base: Path):
    for child in day_base.iterdir():
        if child.is_dir():
            yield child

def iter_pdf_files(provider_dir: Path, is_gm: bool):
    # Keep rglob for all (safe)
    yield from provider_dir.rglob("*.pdf")


# =============================
# CORE
# =============================
def process_day(d: dt.date) -> list[tuple[Path, Path]]:
    pairs = []
    date_str = d.strftime("%Y%m%d")

    for root in ROOTS:
        base_root = DROPBOX_ROOT / root
        if not base_root.exists():
            print(f"[WARN] Root not found, skipping: {base_root}")
            continue

        possible_bases = build_base_paths(root, d)
        day_base = next((p for p in possible_bases if p.exists()), None)
        if day_base is None:
            print(f"[INFO] No day folder found for {root} on {d} (tried {len(possible_bases)} variants)")
            continue

        print(f"[INFO] Using base: {day_base}")

        for provider_dir in iter_provider_dirs(day_base):
            prefix, is_gm = pick_provider_prefix(provider_dir.name)

            for src in iter_pdf_files(provider_dir, is_gm=is_gm):
                raw_name = src.name

                if is_gm and re.search(r"(?i)monthly[\s_]+stats", raw_name):
                    continue

                if SKIP_PAT.search(raw_name):
                    continue
                if not KEEP_PAT.search(raw_name):
                    continue

                orig, file_base = normalize_base_name(prefix, raw_name, year=d.year)
                freq = frequency_code(orig)

                suggested = f"{prefix}_{file_base}_{date_str}_{freq}.pdf"
                
                # Use path manager for new layout if available
                if PATH_MANAGER_AVAILABLE and PATH_MANAGER:
                    dst = PATH_MANAGER.original_pdf_path(suggested)
                else:
                    dst = EXPORT_DIR / suggested
                    
                pairs.append((src, dst))

    return pairs

def _outputs_exist_on_disk(
    export_dir: Path, base: str, path_manager=None,
) -> bool:
    """Check whether essential output files exist on disk for a given base name.

    Checks original PDF + summary JSON.  Uses path_manager layout when
    available, otherwise legacy flat layout.

    Returns:
        True if all essential outputs exist; False if any are missing.
    """
    if path_manager is not None:
        pdf_ok = path_manager.original_pdf_path(f"{base}.pdf").exists()
        json_ok = path_manager.artifact_path(base, "sum.json").exists()
    else:
        pdf_ok = (export_dir / f"{base}.pdf").exists()
        json_ok = (export_dir / f"{base}__sum.json").exists()
    return pdf_ok and json_ok


def process_pairs(
    export_dir: Path,
    pairs: list[tuple[Path, Path]],
    target_day: dt.date,
    no_dedupe: bool = False,
    rebuild_missing: bool = False,
) -> tuple[int, int, int]:
    """
    Process a list of (src, dst) pairs into export_dir. Returns (copied_count, skipped_dupes, summary_skipped).
    Used by process_files_for_date; also allows tests to inject export_dir and pairs.
    
    Args:
        export_dir: Export directory path
        pairs: List of (src, dst) tuples
        target_day: Target date
        no_dedupe: If True, bypass all dedupe/claim checks and regenerate artifacts
        rebuild_missing: If True, override dedupe skip when output files are missing on disk
    """
    copied = 0
    skipped = 0
    summary_skipped = 0

    for src, dst in pairs:
        dedup_doc_id = None
        dedup_claim_handle = None
        try:
            suggested_name = dst.stem
            # Extract provider/date/horizon from suggested_name for downstream
            provider_code = "O"
            for prefix in ["BOA_", "GM_", "MUFG_", "DB_", "ING_", "TME_", "BA_", "JPM_", "MS_", "HSBC_", "CITI_", "UBS_", "BNY_", "ANZ_", "BCA_", "BNPP_", "CACIB_", "MZ_", "NOM_", "RBC_", "SG_", "STI_", "SEB_", "R_", "TSL_", "HT_", "WF_"]:
                if suggested_name.startswith(prefix):
                    provider_code = prefix.rstrip("_")
                    break
            date_match = re.search(r'(\d{8})', suggested_name)
            published_date = date_match.group(1) if date_match else target_day.strftime("%Y%m%d")
            freq_match = re.search(r'_([wmyqud])\.pdf$', dst.name)
            horizon = freq_match.group(1) if freq_match else "u"

            # 1) Wait for Dropbox file to be readable
            if not wait_until_readable(src):
                print(f"[WARN] Source not readable after retries (Dropbox sync/lock?): {src}")
                summary_skipped += 1
                continue

            # 2) Dedupe: doc_id + deterministic base; preflight, claim, atomic write; never create (1)
            if DEDUPE_AVAILABLE and not no_dedupe:
                canonical_url = canonicalize_url(str(src))
                doc_id = doc_id_from_canonical_url(canonical_url)
                dedup_doc_id = doc_id
                title_slug = slugify_title(suggested_name)
                base = deterministic_base_filename(published_date, provider_code, title_slug, doc_id)
                skip_pre, reason = preflight_check(export_dir, doc_id, canonical_url, base)
                if skip_pre:
                    # --rebuild-missing: override skip when output files are missing on disk
                    if rebuild_missing and not _outputs_exist_on_disk(
                        export_dir, base,
                        path_manager=PATH_MANAGER if PATH_MANAGER_AVAILABLE else None,
                    ):
                        print(
                            f"[REBUILD] doc_id={doc_id} status=done in DB but output files missing — rebuilding"
                        )
                        # Reset DB status so downstream treats this as a fresh run
                        if doc_mark_status is not None:
                            doc_mark_status(export_dir, doc_id, "pending")
                    else:
                        print(f"[DEDUP_SKIP] reason={reason} doc_id={doc_id}")
                        skipped += 1
                        continue
                acquired, dedup_claim_handle = claim_acquire(export_dir, doc_id)
                if not acquired:
                    print(f"[DEDUP_SKIP] reason=claim_failed doc_id={doc_id}")
                    skipped += 1
                    continue
                # Registry: insert pending or confirm existing (resume when pending/failed)
                doc_insert_pending(
                    export_dir, doc_id, canonical_url,
                    source=provider_code, title=suggested_name, pub_date=published_date, title_slug=title_slug,
                )
                # Transfer original PDF into originals/ (path_manager) or export root (legacy)
                final_path, _ = ensure_original_pdf_in_export(
                    export_dir, base, src,
                    path_manager=PATH_MANAGER if PATH_MANAGER_AVAILABLE else None,
                )
                if final_path is None:
                    if doc_mark_status is not None:
                        doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg="ensure_original_pdf_in_export failed")
                    claim_release(export_dir, doc_id, dedup_claim_handle)
                    dedup_claim_handle = None
                    summary_skipped += 1
                    continue
                # Skip only when ALL required artifacts exist (pdf + summary_json + summary_pdf + manifest)
                if bundle_complete(export_dir, base, require_manifest=True):
                    validate_and_publish(
                        export_dir, doc_id, canonical_url, title_slug, base, final_path, dedup_claim_handle,
                        source=provider_code, title=suggested_name, pub_date=published_date,
                    )
                    dedup_claim_handle = None
                    skipped += 1
                    continue
                copied += 1
                summary_json_path = final_path.parent / f"{final_path.stem}__sum.json"
                summary_pdf_path  = final_path.parent / f"{final_path.stem}__sum.pdf"
                summaries_exist = summary_pdf_path.exists() and summary_json_path.exists()
                pdf_to_use = final_path
                stem_to_use = final_path.stem
            elif DEDUPE_AVAILABLE and no_dedupe:
                # --no-dedupe mode: setup paths but skip all dedupe/claim checks
                print(f"[NO_DEDUPE] Bypassed duplicate/claim check for {suggested_name}")
                canonical_url = canonicalize_url(str(src))
                doc_id = doc_id_from_canonical_url(canonical_url)
                dedup_doc_id = doc_id
                title_slug = slugify_title(suggested_name)
                base = deterministic_base_filename(published_date, provider_code, title_slug, doc_id)
                
                # Transfer original PDF into originals/ (path_manager) or export root (legacy)
                final_path, _ = ensure_original_pdf_in_export(
                    export_dir, base, src,
                    path_manager=PATH_MANAGER if PATH_MANAGER_AVAILABLE else None,
                )
                if final_path is None:
                    print(f"[WARN] Failed to copy PDF: {src} -> export")
                    summary_skipped += 1
                    continue
                
                copied += 1
                summary_json_path = final_path.parent / f"{final_path.stem}__sum.json"
                summary_pdf_path  = final_path.parent / f"{final_path.stem}__sum.pdf"
                # Force regeneration: treat as if summaries don't exist
                summaries_exist = False
                pdf_to_use = final_path
                stem_to_use = final_path.stem
            else:
                # Legacy: no dedupe module
                # Check for summaries in new layout first, then legacy
                if PATH_MANAGER_AVAILABLE and PATH_MANAGER:
                    basename = dst.stem
                    has_pdf, has_json, has_txt = PATH_MANAGER.has_summary(basename)
                    summary_json_path = PATH_MANAGER.artifact_path(basename, 'sum.json')
                    summary_pdf_path = PATH_MANAGER.artifact_path(basename, 'sum.pdf')
                    summaries_exist = has_pdf and has_json
                else:
                    summary_json_path = dst.parent / f"{dst.stem}__sum.json"
                    summary_pdf_path  = dst.parent / f"{dst.stem}__sum.pdf"
                    summaries_exist = summary_pdf_path.exists() and summary_json_path.exists()
                
                is_duplicate = False
                if dst.exists() and not no_dedupe:
                    src_stat = src.stat()
                    dst_stat = dst.stat()
                    if src_stat.st_size == dst_stat.st_size and md5_hash(src) == md5_hash(dst):
                        is_duplicate = True
                        skipped += 1
                        print(f"[SKIP] Duplicate found, no import: {dst.name}")
                        if summaries_exist:
                            continue
                        print(f"[INFO] Duplicate detected but summaries missing, will generate summaries for {dst.name}")
                elif dst.exists() and no_dedupe:
                    print(f"[NO_DEDUPE] Bypassed duplicate check, will overwrite: {dst.name}")
                    
                if not is_duplicate:
                    if not safe_copy_atomic(src, dst):
                        summary_skipped += 1
                        continue
                    copied += 1
                    print(f"[OK] {src} -> {dst.name}")
                else:
                    if not dst.exists():
                        print(f"[WARN] Original PDF missing for {dst.name}, cannot generate summaries")
                        summary_skipped += 1
                        continue
                pdf_to_use = dst
                stem_to_use = dst.stem
                
                # Force regeneration when --no-dedupe
                if no_dedupe:
                    summaries_exist = False

            # 5) Summarize (only if needed)
            if not SUMMARIZE_AVAILABLE:
                if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                    if doc_mark_status is not None:
                        doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg="summarize not available")
                    claim_release(export_dir, doc_id, dedup_claim_handle)
                    dedup_claim_handle = None
                continue

            # Cache key = article_id + content_hash + prompt version; skip only if valid hit
            if summaries_exist and not no_dedupe and extract_text is not None and _content_hash is not None:
                try:
                    with open(summary_json_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                    stored_hash = existing.get("extraction", {}).get("content_hash")
                    stored_prompt = existing.get("meta", {}).get("prompt_sha256")
                    from twifo_prompts.prompts import article_prompts
                    current_prompt = article_prompts.prompt_sha256()
                    text_cur, _ = extract_text(pdf_to_use, path_manager=PATH_MANAGER if PATH_MANAGER_AVAILABLE else None)
                    current_hash = _content_hash(text_cur)
                    if (
                        stored_hash is not None
                        and stored_prompt is not None
                        and stored_hash == current_hash
                        and stored_prompt == current_prompt
                    ):
                        cache_key = f"{stem_to_use}:{stored_hash[:16]}:{stored_prompt[:8]}"
                        print(
                            f"[CACHE HIT] cache_key={cache_key} content_hash={stored_hash[:16]}..."
                        )
                        if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                            validate_and_publish(
                                export_dir, doc_id, canonical_url, title_slug, base, final_path, dedup_claim_handle,
                                source=provider_code, title=suggested_name, pub_date=published_date,
                            )
                            dedup_claim_handle = None
                        continue
                except Exception:
                    pass  # Missing keys or load error -> re-summarize
            elif summaries_exist and not no_dedupe:
                print(f"[SKIP] Summary PDF and JSON already exist for {pdf_to_use.name}")
                if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                    validate_and_publish(
                        export_dir, doc_id, canonical_url, title_slug, base, final_path, dedup_claim_handle,
                        source=provider_code, title=suggested_name, pub_date=published_date,
                    )
                    dedup_claim_handle = None
                continue
            elif summaries_exist and no_dedupe:
                print(f"[NO_DEDUPE] Forcing regeneration even though summaries exist for {pdf_to_use.name}")

            # 6) Preflight PDF extractability
            text_chars_pymupdf = sniff_pdf_text_chars_pymupdf(pdf_to_use, max_pages=2)
            text_chars_pypdf   = sniff_pdf_text_chars(pdf_to_use, max_pages=2)
            text_chars = max(text_chars_pymupdf, text_chars_pypdf)
            needs_ocr = text_chars <= MIN_PDF_TEXT_CHARS

            print(f"[INFO] Preflight: {pdf_to_use.name} text_chars={text_chars} (pymupdf={text_chars_pymupdf}, pypdf={text_chars_pypdf}), needs_ocr={needs_ocr}")

            pdf_to_summarize = pdf_to_use

            if needs_ocr:
                if not FORCE_OCR_ON_LOW_TEXT:
                    msg = f"Likely image-only PDF (text_chars={text_chars}). OCR disabled."
                    print(f"[WARN] {msg}")
                    summary_skipped += 1
                    if SKIP_SUMMARY_IF_UNREADABLE:
                        write_failed_summary_stub(pdf_to_use, msg)
                    if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                        if doc_mark_status is not None:
                            doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg=msg)
                        claim_release(export_dir, doc_id, dedup_claim_handle)
                        dedup_claim_handle = None
                    continue

                ocr_out = pdf_to_use.parent / f"{stem_to_use}__ocr.pdf"
                ok, msg = ocr_pdf_in_place(pdf_to_use, ocr_out)
                print(f"[INFO] OCR result for {pdf_to_use.name}: {msg}")

                if ok:
                    # Re-check text after OCR
                    post_chars = max(sniff_pdf_text_chars_pymupdf(ocr_out, 2), sniff_pdf_text_chars(ocr_out, 2))
                    print(f"[INFO] Post-OCR preflight: {ocr_out.name} text_chars={post_chars}")

                    if post_chars >= MIN_PDF_TEXT_CHARS:
                        pdf_to_summarize = ocr_out
                    else:
                        # OCR PDF created but still not extractable -> fallback to OCR->text
                        ok2, msg2, ocr_text = ocr_pdf_to_text_fallback(pdf_to_use, dpi=300)
                        print(f"[INFO] OCR fallback-to-text: {msg2}")
                        if not ok2 or len(ocr_text) < MIN_PDF_TEXT_CHARS:
                            summary_skipped += 1
                            if SKIP_SUMMARY_IF_UNREADABLE:
                                write_failed_summary_stub(pdf_to_use, f"OCR pdf not extractable and OCR-to-text failed. {msg2}")
                            if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                                if doc_mark_status is not None:
                                    doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg=f"OCR-to-text failed: {msg2}")
                                claim_release(export_dir, doc_id, dedup_claim_handle)
                                dedup_claim_handle = None
                            continue

                        # Save extracted text for debugging / optional summarization input
                        txt_path = pdf_to_use.parent / f"{stem_to_use}__ocr.txt"
                        txt_path.write_text(ocr_text, encoding="utf-8")
                        # Summarize via text file (requires summarize_pdf to accept raw text OR create summarize_text)
                        if summarize_text is None:
                            summary_skipped += 1
                            if SKIP_SUMMARY_IF_UNREADABLE:
                                write_failed_summary_stub(pdf_to_use, "OCR-to-text succeeded but summarize_text not available.")
                            if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                                if doc_mark_status is not None:
                                    doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg="summarize_text not available")
                                claim_release(export_dir, doc_id, dedup_claim_handle)
                                dedup_claim_handle = None
                            continue
                        summary, sum_json_path = summarize_text(ocr_text, title=suggested_name, provider=provider_code, published_date=published_date, horizon=horizon, out_dir=pdf_to_use.parent)
                        if not summary:
                            summary_skipped += 1
                            if SKIP_SUMMARY_IF_UNREADABLE:
                                write_failed_summary_stub(pdf_to_use, "OCR-to-text succeeded but summarization from text failed.")
                            if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                                if doc_mark_status is not None:
                                    doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg="summarization from text failed")
                                claim_release(export_dir, doc_id, dedup_claim_handle)
                                dedup_claim_handle = None
                        else:
                            print(f"[OK] Summary created for {pdf_to_use.name} (OCR-to-text path)")
                            
                            # Verify JSON exists at the path returned by summarize_text
                            if not os.path.exists(sum_json_path):
                                print(f"[ERROR] JSON file not found at returned path: {sum_json_path}")
                                summary_skipped += 1
                                if SKIP_SUMMARY_IF_UNREADABLE:
                                    write_failed_summary_stub(pdf_to_use, f"JSON write failed at {sum_json_path}")
                                if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                                    if doc_mark_status is not None:
                                        doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg="JSON write failed")
                                    claim_release(export_dir, doc_id, dedup_claim_handle)
                                    dedup_claim_handle = None
                                continue
                            
                            # Generate PDF from JSON using the real path
                            if PDF_RENDER_AVAILABLE and render_summary_pdf:
                                pdf_path = sum_json_path.parent / f"{sum_json_path.stem}.pdf"
                                try:
                                    if render_summary_pdf(sum_json_path, pdf_path):
                                        print(f"[OK] Summary PDF created: {pdf_path.name}")
                                    else:
                                        print(f"[WARN] PDF render returned False for: {pdf_path.name}")
                                except Exception as pdf_err:
                                    print(f"[ERR] PDF generation failed for {sum_json_path.stem}: {pdf_err}")
                            if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                                validate_and_publish(
                                    export_dir, doc_id, canonical_url, title_slug, base, final_path, dedup_claim_handle,
                                    source=provider_code, title=suggested_name, pub_date=published_date,
                                )
                                dedup_claim_handle = None
                        continue
                else:
                    # ocrmypdf failed -> fallback OCR-to-text
                    ok2, msg2, ocr_text = ocr_pdf_to_text_fallback(pdf_to_use, dpi=300)
                    print(f"[INFO] OCR fallback-to-text: {msg2}")

                    if not ok2 or len(ocr_text) < MIN_PDF_TEXT_CHARS:
                        summary_skipped += 1
                        if SKIP_SUMMARY_IF_UNREADABLE:
                            write_failed_summary_stub(pdf_to_use, f"OCR failed (ocrmypdf + fallback). ocrmypdf: {msg} | fallback: {msg2}")
                        if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                            if doc_mark_status is not None:
                                doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg=f"OCR failed: {msg} | {msg2}")
                            claim_release(export_dir, doc_id, dedup_claim_handle)
                            dedup_claim_handle = None
                        continue

                    txt_path = pdf_to_use.parent / f"{stem_to_use}__ocr.txt"
                    txt_path.write_text(ocr_text, encoding="utf-8")

                    if summarize_text is None:
                        summary_skipped += 1
                        if SKIP_SUMMARY_IF_UNREADABLE:
                            write_failed_summary_stub(pdf_to_use, "OCR-to-text succeeded but summarize_text not available.")
                        if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                            if doc_mark_status is not None:
                                doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg="summarize_text not available")
                            claim_release(export_dir, doc_id, dedup_claim_handle)
                            dedup_claim_handle = None
                        continue
                    summary, sum_json_path = summarize_text(ocr_text, title=suggested_name, provider=provider_code, published_date=published_date, horizon=horizon, out_dir=pdf_to_use.parent)
                    if not summary:
                        summary_skipped += 1
                        if SKIP_SUMMARY_IF_UNREADABLE:
                            write_failed_summary_stub(pdf_to_use, "OCR-to-text succeeded but summarization from text failed.")
                        if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                            if doc_mark_status is not None:
                                doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg="summarization from text failed")
                            claim_release(export_dir, doc_id, dedup_claim_handle)
                            dedup_claim_handle = None
                    else:
                        print(f"[OK] Summary created for {pdf_to_use.name} (OCR-to-text path)")
                        
                        # Verify JSON exists at the path returned by summarize_text
                        if not os.path.exists(sum_json_path):
                            print(f"[ERROR] JSON file not found at returned path: {sum_json_path}")
                            summary_skipped += 1
                            if SKIP_SUMMARY_IF_UNREADABLE:
                                write_failed_summary_stub(pdf_to_use, f"JSON write failed at {sum_json_path}")
                            if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                                if doc_mark_status is not None:
                                    doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg="JSON write failed")
                                claim_release(export_dir, doc_id, dedup_claim_handle)
                                dedup_claim_handle = None
                            continue
                        
                        # Generate PDF from JSON using the real path
                        if PDF_RENDER_AVAILABLE and render_summary_pdf:
                            pdf_path = sum_json_path.parent / f"{sum_json_path.stem}.pdf"
                            try:
                                if render_summary_pdf(sum_json_path, pdf_path):
                                    print(f"[OK] Summary PDF created: {pdf_path.name}")
                                else:
                                    print(f"[WARN] PDF render returned False for: {pdf_path.name}")
                            except Exception as pdf_err:
                                print(f"[ERR] PDF generation failed for {sum_json_path.stem}: {pdf_err}")
                        if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                            validate_and_publish(
                                export_dir, doc_id, canonical_url, title_slug, base, final_path, dedup_claim_handle,
                                source=provider_code, title=suggested_name, pub_date=published_date,
                            )
                            dedup_claim_handle = None
                    continue

            print(f"[INFO] Generating summary for {pdf_to_summarize.name} ...")
            summary, sum_json_path = summarize_pdf(
                pdf_to_summarize, 
                out_dir=pdf_to_use.parent if not PATH_MANAGER else None,
                path_manager=PATH_MANAGER if PATH_MANAGER_AVAILABLE else None
            )

            if not summary:
                msg = "summarize_pdf returned None after OCR/extraction."
                print(f"[WARN] {msg} {pdf_to_summarize.name}")
                summary_skipped += 1
                if SKIP_SUMMARY_IF_UNREADABLE:
                    write_failed_summary_stub(pdf_to_use, msg)
                if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                    if doc_mark_status is not None:
                        doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg=msg)
                    claim_release(export_dir, doc_id, dedup_claim_handle)
                    dedup_claim_handle = None
            elif is_stub(summary):
                stub_reason = summary.get("extraction", {}).get("reason", "(unknown)")
                print(f"[WARN] Stub summary for {pdf_to_use.name}: {stub_reason}")
                summary_skipped += 1
                if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                    if doc_mark_status is not None:
                        doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg=f"stub: {stub_reason}")
                    claim_release(export_dir, doc_id, dedup_claim_handle)
                    dedup_claim_handle = None
            else:
                print(f"[OK] Summary created for {pdf_to_use.name}")
                
                # Verify JSON exists at the path returned by summarize_pdf
                if not os.path.exists(sum_json_path):
                    print(f"[ERROR] JSON file not found at returned path: {sum_json_path}")
                    summary_skipped += 1
                    if SKIP_SUMMARY_IF_UNREADABLE:
                        write_failed_summary_stub(pdf_to_use, f"JSON write failed at {sum_json_path}")
                    if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                        if doc_mark_status is not None:
                            doc_mark_status(export_dir, doc_id, STATUS_FAILED, error_msg="JSON write failed")
                        claim_release(export_dir, doc_id, dedup_claim_handle)
                        dedup_claim_handle = None
                    continue
                
                # Update summary_json_path to use the real path from summarize_pdf
                summary_json_path = sum_json_path
                
                # Patch display title when using doc_key filenames
                if DEDUPE_AVAILABLE and suggested_name and stem_to_use != suggested_name:
                    try:
                        with open(summary_json_path, "r", encoding="utf-8") as f:
                            sum_data = json.load(f)
                        sum_data.setdefault("meta", {})["title"] = suggested_name
                        with open(summary_json_path, "w", encoding="utf-8") as f:
                            json.dump(sum_data, f, indent=2, ensure_ascii=False)
                    except Exception:
                        pass
                # Generate PDF from JSON using the real path
                if not PDF_RENDER_AVAILABLE:
                    print(f"[WARN] PDF rendering not available (reportlab not installed?)")
                elif not render_summary_pdf:
                    print(f"[WARN] render_summary_pdf function is None")
                else:
                    # Use the real JSON path returned by summarize_pdf
                    pdf_path = sum_json_path.parent / f"{sum_json_path.stem}.pdf"
                    
                    try:
                        if render_summary_pdf(sum_json_path, pdf_path):
                            print(f"[OK] Summary PDF created: {pdf_path.name}")
                        else:
                            print(f"[WARN] PDF render returned False for: {pdf_path.name}")
                    except Exception as pdf_err:
                        print(f"[ERR] PDF generation failed for {sum_json_path.stem}: {pdf_err}")
                if DEDUPE_AVAILABLE and dedup_claim_handle is not None:
                    validate_and_publish(
                        export_dir, doc_id, canonical_url, title_slug, base, final_path, dedup_claim_handle,
                        source=provider_code, title=suggested_name, pub_date=published_date,
                    )
                    dedup_claim_handle = None

        except SummaryWriteFailedError as wfe:
            # Hard failure: JSON write failed - do NOT attempt render
            print(f"[ERR] {wfe}")
            summary_skipped += 1
            if DEDUPE_AVAILABLE and dedup_claim_handle is not None and dedup_doc_id is not None:
                if doc_mark_status is not None:
                    doc_mark_status(export_dir, dedup_doc_id, STATUS_FAILED, error_msg="JSON write failed")
                claim_release(export_dir, dedup_doc_id, dedup_claim_handle)
                dedup_claim_handle = None
        except Exception as e:
            print(f"[ERR] Failed processing: {src} -> {dst} : {e}")
            summary_skipped += 1
            if DEDUPE_AVAILABLE and dedup_claim_handle is not None and dedup_doc_id is not None:
                if doc_mark_status is not None:
                    doc_mark_status(export_dir, dedup_doc_id, STATUS_FAILED, error_msg=str(e))
                claim_release(export_dir, dedup_doc_id, dedup_claim_handle)
                dedup_claim_handle = None
        finally:
            # Ensure claim is always released on every exit path (success, continue, or except)
            if DEDUPE_AVAILABLE and dedup_claim_handle is not None and dedup_doc_id is not None:
                claim_release(export_dir, dedup_doc_id, dedup_claim_handle)
                dedup_claim_handle = None

    return copied, skipped, summary_skipped


def verify_export_structure(export_dir: Path, path_manager=None) -> dict:
    """
    Verify and count files in final export directory structure.
    
    When path_manager is enabled, checks:
      - originals/*.pdf
      - artifacts/<base>/sum.json, sum.pdf, etc.
      - rollups/daily/*.json
      - rollups/weekly/*.json
    
    Returns dict with counts per group: {originals, artifacts, rollups}
    """
    counts = {
        "originals": 0,
        "artifacts": 0,
        "rollups_daily": 0,
        "rollups_weekly": 0,
        "rollups_other": 0,
    }
    
    if path_manager is not None:
        # Count originals/*.pdf
        if path_manager.originals_dir.exists():
            counts["originals"] = len(list(path_manager.originals_dir.glob("*.pdf")))
        
        # Count artifacts subdirectories with summaries
        if path_manager.artifacts_dir.exists():
            for art_dir in path_manager.artifacts_dir.iterdir():
                if art_dir.is_dir():
                    # Count if has at least one summary artifact
                    if any(art_dir.glob("sum.*")):
                        counts["artifacts"] += 1
        
        # Count rollups
        rollups_dir = export_dir / "rollups"
        if rollups_dir.exists():
            daily_dir = rollups_dir / "daily"
            if daily_dir.exists():
                counts["rollups_daily"] = len(list(daily_dir.glob("ROLLUP_DAILY_*.json")))
            
            weekly_dir = rollups_dir / "weekly"
            if weekly_dir.exists():
                counts["rollups_weekly"] = len(list(weekly_dir.glob("ROLLUP_WEEKLY_*.json")))
            
            # Count other rollup files in root
            counts["rollups_other"] = len([
                f for f in rollups_dir.glob("ROLLUP_*.json")
                if f.is_file() and f.parent == rollups_dir
            ])
    else:
        # Legacy mode: count root-level files
        if export_dir.exists():
            counts["originals"] = len(list(export_dir.glob("*.pdf")))
            counts["artifacts"] = len(list(export_dir.glob("*__sum.json")))
            
            rollups_dir = export_dir / "rollups"
            if rollups_dir.exists():
                daily_dir = rollups_dir / "daily"
                if daily_dir.exists():
                    counts["rollups_daily"] = len(list(daily_dir.glob("ROLLUP_DAILY_*.json")))
                
                weekly_dir = rollups_dir / "weekly"
                if weekly_dir.exists():
                    counts["rollups_weekly"] = len(list(weekly_dir.glob("ROLLUP_WEEKLY_*.json")))
    
    return counts


def process_files_for_date(
    target_day: dt.date, no_dedupe: bool = False, rebuild_missing: bool = False,
) -> tuple[int, int, int]:
    """
    Returns: (copied_count, skipped_dupes, summary_skipped_unreadable)
    
    Args:
        target_day: Target date
        no_dedupe: If True, bypass all dedupe/claim checks and regenerate artifacts
        rebuild_missing: If True, re-process DB duplicates whose output files are missing
    """
    pairs = process_day(target_day)
    if not pairs:
        print(f"[DONE] No matching files for {target_day}.")
        return 0, 0, 0
    return process_pairs(
        EXPORT_DIR, pairs, target_day, no_dedupe=no_dedupe, rebuild_missing=rebuild_missing,
    )


def get_date_range() -> list[dt.date]:
    if not ENABLE_DATE_RANGE_SELECTION:
        return [dt.date.today() - dt.timedelta(days=3)]

    print("\n[INFO] Date range selection enabled.")
    print("Enter date range (YYYY-MM-DD format)")

    try:
        start_str = input("Start date (YYYY-MM-DD) [default: yesterday]: ").strip()
        start_date = (dt.date.today() - dt.timedelta(days=1)) if not start_str else dt.datetime.strptime(start_str, "%Y-%m-%d").date()

        end_str = input("End date (YYYY-MM-DD) [default: same as start]: ").strip()
        end_date = start_date if not end_str else dt.datetime.strptime(end_str, "%Y-%m-%d").date()

        if end_date < start_date:
            print("[WARN] End date is before start date. Swapping dates.")
            start_date, end_date = end_date, start_date

        date_list = []
        cur = start_date
        while cur <= end_date:
            date_list.append(cur)
            cur += dt.timedelta(days=1)

        print(f"[INFO] Processing {len(date_list)} day(s): {start_date} to {end_date}")
        return date_list

    except ValueError as e:
        print(f"[ERR] Invalid date format. Use YYYY-MM-DD. Error: {e}")
        print("[INFO] Falling back to yesterday only.")
        return [dt.date.today() - dt.timedelta(days=1)]

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="TWIFO database filter and auto-run pipeline")
    parser.add_argument('dates', nargs='*', help='Optional date(s) in YYYY-MM-DD format')
    parser.add_argument('--no-dedupe', action='store_true', 
                        help='Bypass all duplicate/claim checks and regenerate artifacts (ignores DB state)')
    parser.add_argument('--rebuild-missing', action='store_true',
                        help='Re-process documents whose DB status=done but output files are missing on disk')
    args = parser.parse_args()
    
    # Startup warning for --rebuild-missing
    if args.rebuild_missing:
        print("[INFO] ═══════════════════════════════════════════════════════════")
        print("[INFO] --rebuild-missing: will re-process DB duplicates whose output files are missing")
        print("[INFO] Dedupe remains active; only missing-file entries will be rebuilt")
        print("[INFO] ═══════════════════════════════════════════════════════════")
        print()

    # Startup warning for --no-dedupe
    if args.no_dedupe:
        print("[WARN] ═══════════════════════════════════════════════════════════")
        print("[WARN] Dedupe disabled (--no-dedupe flag set)")
        print("[WARN] Will regenerate artifacts and ignore existing-duplicate checks")
        print("[WARN] Output files will be OVERWRITTEN if they exist")
        print("[WARN] ═══════════════════════════════════════════════════════════")
        print()
    
    # Step 1: Load OpenAI API key (single source-of-truth)
    if AUTH_AVAILABLE and SUMMARIZE_AVAILABLE:
        print("[INFO] Loading OpenAI API key...")
        try:
            api_key = get_openai_api_key()
            # Detect source
            from pathlib import Path
            env_file = Path(__file__).parent / ".env"
            if env_file.exists():
                with open(env_file, 'r', encoding='utf-8') as f:
                    if 'OPENAI_API_KEY=' in f.read():
                        source = ".env file"
                    else:
                        source = "environment variable"
            else:
                source = "environment variable"
            
            # Set in os.environ so all child modules use it
            os.environ['OPENAI_API_KEY'] = api_key
            prefix = describe_key(api_key)
            print(f"[INFO] API key loaded from {source} (prefix={prefix})")
        except SystemExit:
            raise
        except Exception as e:
            print(f"[ERROR] Failed to load API key: {e}")
            raise SystemExit(1)
        
        # Step 2: Verify authentication with OpenAI
        print("[INFO] Verifying OpenAI API authentication...")
        base_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        assert_openai_auth_ok(base_model)
        print("[INFO] OpenAI API authentication OK")
    
    check_ocr_env()
    
    if START_DELAY_SECONDS > 0:
        print(f"[INFO] Sleeping {START_DELAY_SECONDS}s to allow Dropbox sync...")
        time.sleep(START_DELAY_SECONDS)

    # Optional: selective day(s) from command line (YYYY-MM-DD)
    date_list = None
    if len(args.dates) >= 1:
        try:
            start_date = dt.datetime.strptime(args.dates[0], "%Y-%m-%d").date()
            end_date = dt.datetime.strptime(args.dates[1], "%Y-%m-%d").date() if len(args.dates) >= 2 else start_date
            if end_date < start_date:
                start_date, end_date = end_date, start_date
            date_list = []
            cur = start_date
            while cur <= end_date:
                date_list.append(cur)
                cur += dt.timedelta(days=1)
            print(f"[INFO] Using date(s) from command line: {start_date} to {end_date}")
        except ValueError:
            print("[WARN] Invalid date in argv (use YYYY-MM-DD). Falling back to interactive/default.")
    if date_list is None:
        date_list = get_date_range()

    # Ask whether to bypass duplicates if not already set by CLI (default: do not bypass)
    no_dedupe = args.no_dedupe
    if not no_dedupe:
        try:
            answer = input(
                "Bypass duplicate checks (regenerate artifacts even if they exist)? [y/N]: "
            ).strip().lower()
            no_dedupe = answer in ("y", "yes")
            if no_dedupe:
                print("[WARN] Dedupe disabled (user chose to bypass). Will regenerate artifacts.")
        except (EOFError, KeyboardInterrupt):
            no_dedupe = False
            print("[INFO] Using default: do not bypass duplicates.")

    total_copied = 0
    total_skipped = 0
    total_summary_skipped = 0

    for target_day in date_list:
        print(f"\n[INFO] Processing date: {target_day}")
        copied, skipped, summary_skipped = process_files_for_date(
            target_day, no_dedupe=no_dedupe, rebuild_missing=args.rebuild_missing,
        )
        total_copied += copied
        total_skipped += skipped
        total_summary_skipped += summary_skipped
        
        # Generate daily rollup for this date (if rollup generation is available)
        if ROLLUP_AVAILABLE and generate_daily_rollup and save_daily_rollup:
            try:
                rollup = generate_daily_rollup(target_day, min_articles=1)
                if rollup:
                    save_daily_rollup(rollup, target_day)
                    print(f"[OK] Daily rollup created for {target_day}")
                else:
                    print(f"[INFO] No daily rollup created for {target_day} (insufficient articles)")
            except Exception as e:
                print(f"[WARN] Failed to generate daily rollup for {target_day}: {e}")

    if total_skipped > 0:
        print(f"\n[DONE] Copied {total_copied} files ({total_skipped} duplicates skipped) to {EXPORT_DIR}")
    else:
        print(f"\n[DONE] Copied {total_copied} files to {EXPORT_DIR}")

    if total_summary_skipped > 0:
        print(f"[INFO] Summaries skipped/failed for {total_summary_skipped} file(s) (unreadable / OCR / other).")

    # Verify and report final export structure
    print("\n[EXPORT STRUCTURE]")
    final_counts = verify_export_structure(
        EXPORT_DIR, 
        path_manager=PATH_MANAGER if PATH_MANAGER_AVAILABLE else None
    )
    print(f"  Originals (PDFs): {final_counts['originals']}")
    print(f"  Artifacts (bundles): {final_counts['artifacts']}")
    print(f"  Rollups (daily): {final_counts['rollups_daily']}")
    print(f"  Rollups (weekly): {final_counts['rollups_weekly']}")
    if final_counts['rollups_other'] > 0:
        print(f"  Rollups (other): {final_counts['rollups_other']}")
    
    total_exports = (
        final_counts['originals'] + 
        final_counts['artifacts'] + 
        final_counts['rollups_daily'] + 
        final_counts['rollups_weekly'] +
        final_counts['rollups_other']
    )
    print(f"  Total items in export: {total_exports}")
    
    if PATH_MANAGER_AVAILABLE and PATH_MANAGER:
        print(f"\n[EXPORT PATHS]")
        print(f"  Root: {EXPORT_DIR}")
        print(f"  Originals: {PATH_MANAGER.originals_dir}")
        print(f"  Artifacts: {PATH_MANAGER.artifacts_dir}")
        print(f"  Rollups: {EXPORT_DIR / 'rollups'}")

    if RUN_WEBSITE_UPDATE and BAT_PATH.exists():
        try:
            print("\n[INFO] Running website update bat...")
            subprocess.run([str(BAT_PATH)], shell=True, check=True)
            print("[DONE] Website update ran successfully.")
        except Exception as e:
            print(f"[ERR] Website update failed: {e}")

if __name__ == "__main__":
    main()
