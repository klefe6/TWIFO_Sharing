# TWIFO_Sharing Smoke Test

**Purpose:** Validate article summarization and rollup pipelines before/after changes  
**Last Updated:** 2026-02-04  
**Do not assume tests exist** — use these commands to establish known-good state.

---

## Prerequisites (Known-Good State)

Before running smoke tests:

1. **Working directory:** `TWIFO_Sharing` (repo root)
2. **Python venv:** Activated (e.g. `.venv13\Scripts\activate` or use batch files)
3. **API key:** `OPENAI_API_KEY` set in `.env` (at repo root) or environment
4. **Dependencies:** `pip install -r requirements.txt`

---

## 1. Article Summarization Pipeline

### 1a. Single-PDF Smoke Test (requires API key + real PDF)

```powershell
cd "c:\Coding Projects\TWIFO_Sharing"
python smoke_test_pdf.py "<path-to-a-real-pdf>"
```

**Example** (if you have article PDFs in the export folder):

```powershell
python smoke_test_pdf.py "C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\BOA_some_report_20260108_w.pdf"
```

**Expected:** Prints `[OK]` or `[FAIL]`, attempt count, quality reason. Creates `__sum.json` and `__sum.txt` next to the PDF.

**Note:** Uses `allow_ocr=False` for speed. Use a text-based PDF (not scanned).

### 1b. Import Pipeline (full Dropbox → export → summarize)

```powershell
cd "c:\Coding Projects\TWIFO_Sharing"
run_db_filter.bat
```

Or directly:

```powershell
python db_filter_autorun.py
```

**Paths (hardcoded in `db_filter_autorun.py`):**
- Dropbox root: `C:\Users\H&CDanHughes\Rdatabase Dropbox\R D`
- Export dir: `C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE`

**Expected:** Copies PDFs from Dropbox, generates summaries, optionally restarts web app.

---

## 2. Rollup Pipeline

### 2a. Generate Daily Rollup (requires ≥3 article summaries for date)

```powershell
cd "c:\Coding Projects\TWIFO_Sharing"
python generate_rollup_clean.py daily YYYY-MM-DD
```

**Example:**

```powershell
python generate_rollup_clean.py daily 2026-01-11
```

**Paths (hardcoded in `generate_rollup_clean.py`):**
- Article summaries: `C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\*_YYYYMMDD_*__sum.json`
- Daily rollups: `...\FOLDERS_AVAILABLE_ONLINE\rollups\daily\`

### 2b. Generate Weekly Rollup (requires ≥3 articles in Mon–Fri range)

```powershell
python generate_rollup_clean.py weekly YYYY-MM-DD [YYYY-MM-DD]
```

**Example:**

```powershell
python generate_rollup_clean.py weekly 2026-01-06 2026-01-10
```

### 2c. Validate Rollup JSON

```powershell
python rollup_validate.py <path-to-rollup.json>
```

**Example (single file):**

```powershell
python rollup_validate.py "C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\rollups\daily\ROLLUP_DAILY_20260111__sum.json"
```

**Example (directory):**

```powershell
python rollup_validate.py --dir "C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\rollups\daily"
```

**Expected:** `[OK]` if valid, `[ERROR]` with error list if invalid.

### 2d. Backfill (dry-run; no writes)

```powershell
python backfill_rollups.py --start 2026-01-01 --end 2026-01-07 --dry-run
```

---

## 3. Web Applications

### 3a. Main Research Directory (Dash)

```powershell
reboot_twifo.bat
```

Or:

```powershell
python twifo.py
```

**URL:** `http://127.0.0.1:8065`  
**Port:** 8065

### 3b. Dropbox Management (Streamlit)

```powershell
reboot_import_dropbox.bat
```

Or:

```powershell
streamlit run import_dropbox.py --server.port 8001
```

**URL:** `http://127.0.0.1:8001`  
**Port:** 8001

---

## Minimal Smoke Sequence (No Tests Required)

To quickly validate pipelines without running unit tests:

1. **Summarization:** `python smoke_test_pdf.py <path-to-pdf>` (or skip if no PDF handy)
2. **Rollup validation:** `python rollup_validate.py --dir <rollups-daily-path>` (validates existing rollups)
3. **Web app:** `python twifo.py` → open `http://127.0.0.1:8065` → confirm page loads

---

## Path Reference

| Purpose            | Path |
|--------------------|------|
| Repo root          | `c:\Coding Projects\TWIFO_Sharing` |
| Article export     | `C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE` |
| Daily rollups      | `...\FOLDERS_AVAILABLE_ONLINE\rollups\daily\` |
| Weekly rollups     | `...\FOLDERS_AVAILABLE_ONLINE\rollups\weekly\` |
| twifo (Dash)       | `http://127.0.0.1:8065` |
| import_dropbox     | `http://127.0.0.1:8001` |
