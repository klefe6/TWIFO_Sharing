# Debug: Deduplication failure and "(1)" suffix

## 1. Where PDFs are saved or downloaded

| Location | What happens |
|----------|----------------|
| **db_filter_autorun.py** | Copies from Dropbox (local sync) to export dir via `safe_copy_atomic(src, dst)` → `shutil.copy2(src, tmp)` then `os.replace(tmp, dst)`. |
| **import_dropbox.py** | Downloads from Dropbox API to export dir: `dbx.files_download_to_file(dst, src)` with `dst = os.path.join(export_dir, row["suggested_name"])`. |
| **twifo.py** | No PDF download/copy; has `_save_pdf_cache` for text cache JSON only. |

No `requests.get`, `wget`, or `Path(...).write_bytes` for PDFs in this repo. PDFs are either copied from a local Dropbox folder (db_filter_autorun) or downloaded via Dropbox API (import_dropbox).

---

## 2. What produces the "(1)" suffix

- **Not from our code.**  
  - `safe_copy_atomic` uses `os.replace(tmp, dst)`, which overwrites `dst` if it exists (no "(1)").
  - `files_download_to_file(dst, src)` writes to `dst` (typically overwrites if the path exists).

- **Most likely sources of "(1)":**
  1. **Dropbox desktop sync**  
     `EXPORT_DIR` is under `Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE`. If that path is inside a Dropbox-synced folder, when a file at `dst` is overwritten or updated, Dropbox can keep a “previous version” or conflict copy as `"filename (1).pdf"`.
  2. **Windows Explorer / shell copy**  
     Copying a file into a folder that already has a file with the same name produces `"filename (1).pdf"`.
  3. **Two writers to the same path**  
     If `db_filter_autorun` and `import_dropbox` (or two runs) write the same `suggested_name` and something in the stack (e.g. Dropbox, antivirus) doesn’t allow overwrite, the second write might end up as `"filename (1).pdf"`.

So the "(1)" is almost certainly from **Windows or Dropbox** (filesystem/collision behavior), not from a custom renamer or downloader in this codebase.

---

## 3. Current dedupe check

| Aspect | Detail |
|--------|--------|
| **File** | `db_filter_autorun.py` |
| **Function** | `process_files_for_date()` (loop over `(src, dst)` from `process_day()`). |
| **When** | After deciding to process a pair; **post–copy** in the sense that it checks **existing `dst`** (export dir). |
| **Key** | Effectively **destination path + content identity**: `dst.exists()` then `src_stat.st_size == dst_stat.st_size` and `md5_hash(src) == md5_hash(dst)`. |
| **Behavior** | If `dst` exists and has same size and same MD5 as current `src` → treat as duplicate: skip copy, optionally still run summary if summaries are missing. |

So: **dedupe key = (dst path, size, MD5 of file at dst vs current src).**  
It does **not** dedupe by source path, URL, or content hash before choosing `dst`. It only avoids re-copying when the file already at `dst` is byte-identical to the current `src`.

---

## 4. Concurrency

- **db_filter_autorun**: single process, single-threaded loop over `pairs`. No Celery, no multiprocessing, no threads in the copy/summary path.
- **twifo.py**: uses `ThreadPoolExecutor` only for **PDF search** (`check_single_pdf`), not for copying or downloading.
- **import_dropbox.py**: Streamlit; downloads in a simple loop, no parallel workers.

So the copy/download path is **not** concurrent. There is still a “check then act” pattern (check `dst.exists()` then copy), but with a single process the race would be with **something external** (e.g. Dropbox sync or another run of the script / import_dropbox) rather than with another thread in the same run.

---

## 5. Exact files and functions

| Role | File | Function(s) |
|------|------|-------------|
| **(a) Naming PDFs** | `db_filter_autorun.py` | `process_day()`: builds `suggested = f"{prefix}_{file_base}_{date_str}_{freq}.pdf"`, `dst = EXPORT_DIR / suggested`. `normalize_base_name(prefix, raw_name, year)` produces `file_base` from `raw_name`. |
| **(a) Naming (Streamlit)** | `import_dropbox.py` | Same idea: `suggested_name` from prefix + normalized name + date + freq; `dst = os.path.join(export_dir, row["suggested_name"])`. |
| **(b) Saving PDFs** | `db_filter_autorun.py` | `safe_copy_atomic(src, dst)`: `shutil.copy2(src, tmp)` then `os.replace(tmp, dst)`. |
| **(b) Saving (download)** | `import_dropbox.py` | `dbx.files_download_to_file(dst, src)` in the “Download all remaining rows” loop. |
| **(c) Dedupe check** | `db_filter_autorun.py` | `process_files_for_date()`: for each `(src, dst)`, `if dst.exists()` and `src_stat.st_size == dst_stat.st_size` and `md5_hash(src) == md5_hash(dst)` → `is_duplicate = True`; skip copy (and optionally skip summary if summaries exist). |

---

## 6. Why the dedupe fails (same PDF twice, "(1)" in UI)

- **Same PDF processed twice**
  - `process_day()` can produce **multiple `(src, dst)` pairs with the same `dst`** when two different source PDFs normalize to the same `suggested` (same prefix, `file_base`, date, freq). So the same destination path is used for two different sources.
  - Dedupe only says: “if `dst` already exists and its content (size+MD5) equals current `src`, skip copy.” It does **not** say: “if we’ve already chosen this `dst` for another `src` in this run, skip or rename.”
  - So: first pair copies to `dst`; second pair sees `dst` with different content (different MD5) → not duplicate → **overwrites** `dst`. The same logical “article” can be processed twice (two sources, one destination), and we only keep the second file. We never create "(1)" ourselves, but we do overwrite.

- **"(1)" in the folder**
  - When our code overwrites `dst` (e.g. second pair with same `dst`), or when two runs/processes write the same filename, **Dropbox sync** (if EXPORT_DIR is synced) can create a “previous version” or conflict file named `"filename (1).pdf"`.
  - So the failure you see (same PDF twice, filename with "(1)") is consistent with: **(1) duplicate `dst` in the same run (two sources → same name → overwrite), and (2) Dropbox (or Windows) creating the "(1)" copy when the file at `dst` is replaced or when a second writer hits the same path.**

---

## 7. Recommended fixes

1. **Dedupe by destination when building pairs**  
   In `process_day()`, before appending `(src, dst)`, track seen `dst`. If `dst` was already assigned, either skip the second source or assign a unique suffix (e.g. `dst.stem + "_v2" + dst.suffix`) so we never overwrite and never rely on “second copy overwrites first.”

2. **Optionally dedupe by content (e.g. MD5) before copy**  
   Build a set of `md5_hash(src)` for already-copied files in this run; if a new `src` has the same hash, skip it (same PDF, no need to copy again).

3. **Avoid two writers to the same folder**  
   Don’t run `db_filter_autorun` and `import_dropbox` “Download all” for the same export folder at the same time; or use a single pipeline (e.g. only db_filter_autorun for that folder).

4. **If export is in a Dropbox folder**  
   Consider exporting to a non-synced directory and then copying/syncing only what you need, so Dropbox doesn’t create "(1)" conflict copies when we overwrite.
