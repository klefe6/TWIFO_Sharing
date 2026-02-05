import os
import re
import shutil
import datetime as dt
from pathlib import Path
import subprocess
import time
import hashlib
import tempfile
import json

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
    from summarize_pdf import summarize_pdf, summarize_text
    SUMMARIZE_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Summarization not available: {e}")
    SUMMARIZE_AVAILABLE = False
    summarize_text = None

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

# =============================
# CONFIG — EDIT THESE ONCE
# =============================
DROPBOX_ROOT = Path(r"C:\Users\H&CDanHughes\Rdatabase Dropbox\R D")
ROOTS = ["Current", "Archives", "Current Back"]

EXPORT_DIR = Path(
    r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE"
)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

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
    "Macro Insight","Metals","Silver"
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
            "--skip-text",          # don't OCR pages that already have text (optional; remove if you want full OCR)
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
                dst = EXPORT_DIR / suggested
                pairs.append((src, dst))

    return pairs

def process_files_for_date(target_day: dt.date) -> tuple[int, int, int]:
    """
    Returns: (copied_count, skipped_dupes, summary_skipped_unreadable)
    """
    pairs = process_day(target_day)
    if not pairs:
        print(f"[DONE] No matching files for {target_day}.")
        return 0, 0, 0

    copied = 0
    skipped = 0
    summary_skipped = 0

    for src, dst in pairs:
        try:
            # Parse metadata from destination filename for summarize_text if needed
            dst_stem = dst.stem
            # Extract provider prefix (e.g., "BOA_", "GM_", "MUFG_")
            provider_code = "O"
            for prefix in ["BOA_", "GM_", "MUFG_", "DB_", "ING_", "TME_", "BA_", "JPM_", "MS_", "HSBC_", "CITI_", "UBS_", "BNY_", "ANZ_", "BCA_", "BNPP_", "CACIB_", "MZ_", "NOM_", "RBC_", "SG_", "STI_", "SEB_", "R_", "TSL_", "HT_", "WF_"]:
                if dst_stem.startswith(prefix):
                    provider_code = prefix.rstrip("_")
                    break
            
            # Extract date from filename (YYYYMMDD format)
            date_match = re.search(r'(\d{8})', dst_stem)
            published_date = date_match.group(1) if date_match else target_day.strftime("%Y%m%d")
            
            # Extract frequency/horizon from filename (last character before .pdf)
            freq_match = re.search(r'_([wmyqud])\.pdf$', dst.name)
            horizon = freq_match.group(1) if freq_match else "u"
            
            # 1) Wait for Dropbox file to be readable (prevents partial reads)
            if not wait_until_readable(src):
                print(f"[WARN] Source not readable after retries (Dropbox sync/lock?): {src}")
                summary_skipped += 1
                continue

            # 2) Check if summaries already exist (before duplicate check)
            summary_json_path = dst.parent / f"{dst.stem}__sum.json"
            summary_pdf_path  = dst.parent / f"{dst.stem}__sum.pdf"
            summaries_exist = summary_pdf_path.exists() and summary_json_path.exists()
            
            # 3) Duplicate detection - but still process if summaries are missing
            is_duplicate = False
            if dst.exists():
                src_stat = src.stat()
                dst_stat = dst.stat()
                if src_stat.st_size == dst_stat.st_size:
                    if md5_hash(src) == md5_hash(dst):
                        is_duplicate = True
                        skipped += 1
                        print(f"[SKIP] Duplicate found, no import: {dst.name}")
                        # If duplicate AND summaries exist, skip everything
                        if summaries_exist:
                            continue
                        # If duplicate but summaries missing, still generate summaries (don't re-copy)
                        print(f"[INFO] Duplicate detected but summaries missing, will generate summaries for {dst.name}")
            
            # 4) Copy original PDF (only if not duplicate)
            if not is_duplicate:
                if not safe_copy_atomic(src, dst):
                    summary_skipped += 1
                    continue
                copied += 1
                print(f"[OK] {src} -> {dst.name}")
            else:
                # Duplicate but summaries missing - verify original still exists
                if not dst.exists():
                    print(f"[WARN] Original PDF missing for {dst.name}, cannot generate summaries")
                    summary_skipped += 1
                    continue

            # 5) Summarize (only if needed)
            if not SUMMARIZE_AVAILABLE:
                continue

            if summaries_exist:
                print(f"[SKIP] Summary PDF and JSON already exist for {dst.name}")
                continue

            # 6) Preflight PDF extractability
            text_chars_pymupdf = sniff_pdf_text_chars_pymupdf(dst, max_pages=2)
            text_chars_pypdf   = sniff_pdf_text_chars(dst, max_pages=2)
            text_chars = max(text_chars_pymupdf, text_chars_pypdf)
            needs_ocr = text_chars <= MIN_PDF_TEXT_CHARS

            print(f"[INFO] Preflight: {dst.name} text_chars={text_chars} (pymupdf={text_chars_pymupdf}, pypdf={text_chars_pypdf}), needs_ocr={needs_ocr}")

            pdf_to_summarize = dst

            if needs_ocr:
                if not FORCE_OCR_ON_LOW_TEXT:
                    msg = f"Likely image-only PDF (text_chars={text_chars}). OCR disabled."
                    print(f"[WARN] {msg}")
                    summary_skipped += 1
                    if SKIP_SUMMARY_IF_UNREADABLE:
                        write_failed_summary_stub(dst, msg)
                    continue

                ocr_out = dst.parent / f"{dst.stem}__ocr.pdf"
                ok, msg = ocr_pdf_in_place(dst, ocr_out)
                print(f"[INFO] OCR result for {dst.name}: {msg}")

                if ok:
                    # Re-check text after OCR
                    post_chars = max(sniff_pdf_text_chars_pymupdf(ocr_out, 2), sniff_pdf_text_chars(ocr_out, 2))
                    print(f"[INFO] Post-OCR preflight: {ocr_out.name} text_chars={post_chars}")

                    if post_chars >= MIN_PDF_TEXT_CHARS:
                        pdf_to_summarize = ocr_out
                    else:
                        # OCR PDF created but still not extractable -> fallback to OCR->text
                        ok2, msg2, ocr_text = ocr_pdf_to_text_fallback(dst, dpi=300)
                        print(f"[INFO] OCR fallback-to-text: {msg2}")
                        if not ok2 or len(ocr_text) < MIN_PDF_TEXT_CHARS:
                            summary_skipped += 1
                            if SKIP_SUMMARY_IF_UNREADABLE:
                                write_failed_summary_stub(dst, f"OCR pdf not extractable and OCR-to-text failed. {msg2}")
                            continue

                        # Save extracted text for debugging / optional summarization input
                        txt_path = dst.parent / f"{dst.stem}__ocr.txt"
                        txt_path.write_text(ocr_text, encoding="utf-8")
                        # Summarize via text file (requires summarize_pdf to accept raw text OR create summarize_text)
                        if summarize_text is None:
                            summary_skipped += 1
                            if SKIP_SUMMARY_IF_UNREADABLE:
                                write_failed_summary_stub(dst, "OCR-to-text succeeded but summarize_text not available.")
                            continue
                        summary = summarize_text(ocr_text, title=dst_stem, provider=provider_code, published_date=published_date, horizon=horizon, out_dir=dst.parent)
                        if not summary:
                            summary_skipped += 1
                            if SKIP_SUMMARY_IF_UNREADABLE:
                                write_failed_summary_stub(dst, "OCR-to-text succeeded but summarization from text failed.")
                        else:
                            print(f"[OK] Summary created for {dst.name} (OCR-to-text path)")
                            # Generate PDF from JSON
                            if PDF_RENDER_AVAILABLE and render_summary_pdf:
                                json_path = dst.parent / f"{dst.stem}__sum.json"
                                pdf_path = dst.parent / f"{dst.stem}__sum.pdf"
                                try:
                                    if render_summary_pdf(json_path, pdf_path):
                                        print(f"[OK] Summary PDF created: {pdf_path.name}")
                                    else:
                                        print(f"[WARN] PDF render returned False for: {pdf_path.name}")
                                except Exception as pdf_err:
                                    print(f"[ERR] PDF generation failed for {dst.stem}: {pdf_err}")
                        continue
                else:
                    # ocrmypdf failed -> fallback OCR-to-text
                    ok2, msg2, ocr_text = ocr_pdf_to_text_fallback(dst, dpi=300)
                    print(f"[INFO] OCR fallback-to-text: {msg2}")

                    if not ok2 or len(ocr_text) < MIN_PDF_TEXT_CHARS:
                        summary_skipped += 1
                        if SKIP_SUMMARY_IF_UNREADABLE:
                            write_failed_summary_stub(dst, f"OCR failed (ocrmypdf + fallback). ocrmypdf: {msg} | fallback: {msg2}")
                        continue

                    txt_path = dst.parent / f"{dst.stem}__ocr.txt"
                    txt_path.write_text(ocr_text, encoding="utf-8")

                    if summarize_text is None:
                        summary_skipped += 1
                        if SKIP_SUMMARY_IF_UNREADABLE:
                            write_failed_summary_stub(dst, "OCR-to-text succeeded but summarize_text not available.")
                        continue
                    summary = summarize_text(ocr_text, title=dst_stem, provider=provider_code, published_date=published_date, horizon=horizon, out_dir=dst.parent)
                    if not summary:
                        summary_skipped += 1
                        if SKIP_SUMMARY_IF_UNREADABLE:
                            write_failed_summary_stub(dst, "OCR-to-text succeeded but summarization from text failed.")
                    else:
                        print(f"[OK] Summary created for {dst.name} (OCR-to-text path)")
                        # Generate PDF from JSON
                        if PDF_RENDER_AVAILABLE and render_summary_pdf:
                            json_path = dst.parent / f"{dst.stem}__sum.json"
                            pdf_path = dst.parent / f"{dst.stem}__sum.pdf"
                            try:
                                if render_summary_pdf(json_path, pdf_path):
                                    print(f"[OK] Summary PDF created: {pdf_path.name}")
                                else:
                                    print(f"[WARN] PDF render returned False for: {pdf_path.name}")
                            except Exception as pdf_err:
                                print(f"[ERR] PDF generation failed for {dst.stem}: {pdf_err}")
                    continue

            print(f"[INFO] Generating summary for {pdf_to_summarize.name} ...")
            summary = summarize_pdf(pdf_to_summarize, out_dir=dst.parent)

            if not summary:
                msg = "summarize_pdf returned None after OCR/extraction."
                print(f"[WARN] {msg} {pdf_to_summarize.name}")
                summary_skipped += 1
                if SKIP_SUMMARY_IF_UNREADABLE:
                    write_failed_summary_stub(dst, msg)
            else:
                print(f"[OK] Summary created for {dst.name}")
                # Generate PDF from JSON
                if not PDF_RENDER_AVAILABLE:
                    print(f"[WARN] PDF rendering not available (reportlab not installed?)")
                elif not render_summary_pdf:
                    print(f"[WARN] render_summary_pdf function is None")
                else:
                    json_path = dst.parent / f"{dst.stem}__sum.json"
                    pdf_path = dst.parent / f"{dst.stem}__sum.pdf"
                    try:
                        if render_summary_pdf(json_path, pdf_path):
                            print(f"[OK] Summary PDF created: {pdf_path.name}")
                        else:
                            print(f"[WARN] PDF render returned False for: {pdf_path.name}")
                    except Exception as pdf_err:
                        print(f"[ERR] PDF generation failed for {dst.stem}: {pdf_err}")

        except Exception as e:
            print(f"[ERR] Failed processing: {src} -> {dst} : {e}")
            summary_skipped += 1

    return copied, skipped, summary_skipped

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

    date_list = get_date_range()

    total_copied = 0
    total_skipped = 0
    total_summary_skipped = 0

    for target_day in date_list:
        print(f"\n[INFO] Processing date: {target_day}")
        copied, skipped, summary_skipped = process_files_for_date(target_day)
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
                    print(f"[INFO] No daily rollup created for {target_day} (insufficient articles or already exists)")
            except Exception as e:
                print(f"[WARN] Failed to generate daily rollup for {target_day}: {e}")

    if total_skipped > 0:
        print(f"\n[DONE] Copied {total_copied} files ({total_skipped} duplicates skipped) to {EXPORT_DIR}")
    else:
        print(f"\n[DONE] Copied {total_copied} files to {EXPORT_DIR}")

    if total_summary_skipped > 0:
        print(f"[INFO] Summaries skipped/failed for {total_summary_skipped} file(s) (unreadable / OCR / other).")

    if RUN_WEBSITE_UPDATE and BAT_PATH.exists():
        try:
            print("[INFO] Running website update bat...")
            subprocess.run([str(BAT_PATH)], shell=True, check=True)
            print("[DONE] Website update ran successfully.")
        except Exception as e:
            print(f"[ERR] Website update failed: {e}")

if __name__ == "__main__":
    main()
