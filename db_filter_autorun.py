import os
import re
import shutil
import datetime as dt
from pathlib import Path
import subprocess

# Import summarization module
try:
    from summarize_pdf import summarize_pdf, create_summary_file
    SUMMARIZE_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] Summarization not available: {e}")
    SUMMARIZE_AVAILABLE = False

# =============================
# CONFIG — EDIT THESE ONCE
# =============================
DROPBOX_ROOT = Path(r"C:\Users\H&CDanHughes\Rdatabase Dropbox\R D")

# Put the *exact* folder names that exist inside DROPBOX_ROOT.
# Example possibilities: "Archives", "Current", "Current Back", "Current_Back"
ROOTS = ["Current", "Archives", "Current Back"]

EXPORT_DIR = Path(
    r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE"
)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

RUN_WEBSITE_UPDATE = True
BAT_PATH = Path(r"C:\Program Files\Coding Projects\TWIFO_Sharing\reboot_twifo.bat")

# If Dropbox sync sometimes lags, set e.g. 600 (10 min). Otherwise 0.
START_DELAY_SECONDS = 0

DEFAULT_KEEP = [
    "Annual","Weekly","Monthly","Quarterly",
    "Commodity","Commodities","Gold","Bitcoin","SOFR","Interest Rates", "CTAs", "CFTC", "CME", "BNY"
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

# Compile KEEP / SKIP
KEEP_PAT = re.compile(r"(?i)\b(" + "|".join(map(re.escape, DEFAULT_KEEP)) + r")(?=\W|$)")
SKIP_PAT = re.compile(r"(?i)\b(" + "|".join(map(re.escape, DEFAULT_SKIP)) + r")\b")

# =============================
# HELPERS
# =============================
def month_candidates(d: dt.date) -> list[str]:
    """
    Dropbox month folder might be "January" or "Jan".
    We support both.
    """
    return [d.strftime("%B"), d.strftime("%b")]

def day_folder_candidates(d: dt.date) -> list[str]:
    """
    Support common day folder variants:
    - "Jan 9"
    - "Jan 09"
    - "January 9"
    - "January 09"
    """
    abbr = d.strftime("%b")
    full = d.strftime("%B")
    day1 = str(d.day)
    day2 = f"{d.day:02d}"
    return [
        f"{abbr} {day1}", f"{abbr} {day2}",
        f"{full} {day1}", f"{full} {day2}",
    ]

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
    # Keep your vendor stripping logic
    orig = re.sub(r"^(BofA|MUFG|ING)[\s_-]+", "", raw_name)

    file_base = orig.rsplit(".", 1)[0]

    # remove repeated prefix at start: "BNY-", "BNY_", "BNY "
    file_base = re.sub(
        rf"^(?:{re.escape(prefix)}[-_\s]+)+",
        "",
        file_base,
        flags=re.IGNORECASE
    )

    # remove year noise (handles 2025, 2026, etc.)
    file_base = re.sub(rf"\b\d*{year}\d*\b", "", file_base)

    file_base = file_base.replace("_", " ").strip()
    file_base = re.sub(r"\s{{2,}}", " ", file_base)
    return orig, file_base

def build_base_paths(root_name: str, d: dt.date) -> list[Path]:
    """
    Creates all plausible base paths for:
      DROPBOX_ROOT / root / year / month / day_folder
    trying month/day variants.
    """
    paths = []
    for m in month_candidates(d):
        for day_folder in day_folder_candidates(d):
            paths.append(DROPBOX_ROOT / root_name / str(d.year) / m / day_folder)
    return paths

def iter_provider_dirs(day_base: Path):
    """
    Under the day folder, provider directories exist.
    """
    for child in day_base.iterdir():
        if child.is_dir():
            yield child

def iter_pdf_files(provider_dir: Path, is_gm: bool):
    """
    If Goldman: include nested PDFs (like S&T).
    If not Goldman: still include nested PDFs (safe & simple).
    """
    # If you want only top-level files for non-GM, change to provider_dir.glob("*.pdf")
    for p in provider_dir.rglob("*.pdf"):
        # optional: if not gm, you could skip deep paths, but no harm keeping it
        yield p

def process_day(d: dt.date) -> list[tuple[Path, Path]]:
    pairs = []
    date_str = d.strftime("%Y%m%d")

    for root in ROOTS:
        # Root must exist
        if not (DROPBOX_ROOT / root).exists():
            print(f"[WARN] Root not found, skipping: {DROPBOX_ROOT / root}")
            continue

        # Find a matching base path among candidates
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

                # optional Goldman skip
                if is_gm and re.search(r"(?i)monthly[\s_]+stats", raw_name):
                    continue

                # SKIP / KEEP
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

def main():
    if START_DELAY_SECONDS > 0:
        import time
        print(f"[INFO] Sleeping {START_DELAY_SECONDS}s to allow Dropbox sync...")
        time.sleep(START_DELAY_SECONDS)

    target_day = dt.date.today() - dt.timedelta(days=1)
    print(f"[INFO] Processing date: {target_day}")

    pairs = process_day(target_day)
    if not pairs:
        print(f"[DONE] No matching files for {target_day}.")
        return

    copied = 0
    skipped = 0
    for src, dst in pairs:
        try:
            # Check if destination exists and is identical
            if dst.exists():
                # Compare file sizes and modification times
                src_stat = src.stat()
                dst_stat = dst.stat()
                
                # If same size and same content (compare file hashes), skip
                if src_stat.st_size == dst_stat.st_size:
                    import hashlib
                    
                    def file_hash(path):
                        h = hashlib.md5()
                        with open(path, 'rb') as f:
                            for chunk in iter(lambda: f.read(4096), b""):
                                h.update(chunk)
                        return h.hexdigest()
                    
                    if file_hash(src) == file_hash(dst):
                        skipped += 1
                        print(f"[SKIP] Duplicate found, no import: {dst.name}")
                        continue
            
            # File doesn't exist or is different, copy it
            shutil.copy2(src, dst)
            copied += 1
            print(f"[OK] {src} -> {dst.name}")
            
            # Generate summary for newly copied files (skip Chart Books)
            if SUMMARIZE_AVAILABLE:
                try:
                    print(f"[INFO] Generating summary for {dst.name}...")
                    summary = summarize_pdf(dst)
                    if summary:
                        summary_file = create_summary_file(dst, summary)
                        print(f"[OK] Summary created: {summary_file.name}")
                    else:
                        print(f"[SKIP] Summary skipped for {dst.name} (Chart Book or other reason)")
                except Exception as e:
                    print(f"[WARN] Failed to create summary for {dst.name}: {e}")
        except Exception as e:
            print(f"[ERR] Failed copy: {src} -> {dst} : {e}")

    if skipped > 0:
        print(f"[DONE] Copied {copied}/{len(pairs)} files ({skipped} duplicates skipped) to {EXPORT_DIR}")
    else:
        print(f"[DONE] Copied {copied}/{len(pairs)} files to {EXPORT_DIR}")

    if RUN_WEBSITE_UPDATE and BAT_PATH.exists():
        try:
            print("[INFO] Running website update bat...")
            subprocess.run([str(BAT_PATH)], shell=True, check=True)
            print("[DONE] Website update ran successfully.")
        except Exception as e:
            print(f"[ERR] Website update failed: {e}")

if __name__ == "__main__":
    main()
