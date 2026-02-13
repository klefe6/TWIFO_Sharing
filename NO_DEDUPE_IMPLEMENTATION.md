# --no-dedupe Flag Implementation Summary

## Overview
Added `--no-dedupe` CLI flag to bypass all duplicate/claim checking logic in `db_filter_autorun.py`, allowing regeneration of artifacts even when the database or prior claims indicate they already exist.

## Changes Made

### 1. CLI Argument Parsing (Line 1029-1034)
**Location**: `main()` function, start of function

```python
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="TWIFO database filter and auto-run pipeline")
    parser.add_argument('dates', nargs='*', help='Optional date(s) in YYYY-MM-DD format')
    parser.add_argument('--no-dedupe', action='store_true', 
                        help='Bypass all duplicate/claim checks and regenerate artifacts (ignores DB state)')
    args = parser.parse_args()
```

### 2. Startup Warning (Line 1036-1042)
**Location**: `main()` function, after argument parsing

```python
    # Startup warning for --no-dedupe
    if args.no_dedupe:
        print("[WARN] ═══════════════════════════════════════════════════════════")
        print("[WARN] Dedupe disabled (--no-dedupe flag set)")
        print("[WARN] Will regenerate artifacts and ignore existing-duplicate checks")
        print("[WARN] Output files will be OVERWRITTEN if they exist")
        print("[WARN] ═══════════════════════════════════════════════════════════")
        print()
```

### 3. Bypass Logic - process_pairs() Function Signature (Line 530-540)
**Location**: `process_pairs()` function definition

```python
def process_pairs(
    export_dir: Path, pairs: list[tuple[Path, Path]], target_day: dt.date, no_dedupe: bool = False
) -> tuple[int, int, int]:
    """
    Process a list of (src, dst) pairs into export_dir. Returns (copied_count, skipped_dupes, summary_skipped).
    
    Args:
        export_dir: Export directory path
        pairs: List of (src, dst) tuples
        target_day: Target date
        no_dedupe: If True, bypass all dedupe/claim checks and regenerate artifacts
    """
```

### 4. DEDUPE Path Bypass (Line 564)
**Location**: `process_pairs()`, main dedupe branch

**Changed from**:
```python
if DEDUPE_AVAILABLE:
```

**Changed to**:
```python
if DEDUPE_AVAILABLE and not no_dedupe:
```

This prevents entry into the dedupe/claim acquisition block when `--no-dedupe` is set.

### 5. New --no-dedupe Branch (Line 611-636)
**Location**: `process_pairs()`, after main dedupe block

```python
elif DEDUPE_AVAILABLE and no_dedupe:
    # --no-dedupe mode: setup paths but skip all dedupe/claim checks
    print(f"[NO_DEDUPE] Bypassed duplicate/claim check for {suggested_name}")
    canonical_url = canonicalize_url(str(src))
    doc_id = doc_id_from_canonical_url(canonical_url)
    dedup_doc_id = doc_id
    title_slug = slugify_title(suggested_name)
    base = deterministic_base_filename(published_date, provider_code, title_slug, doc_id)
    
    # Transfer original PDF (with atomic overwrite if exists)
    final_path, _ = ensure_original_pdf_in_export(export_dir, base, src)
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
```

### 6. Legacy Mode Bypass (Line 657-660)
**Location**: `process_pairs()`, legacy (non-DEDUPE) branch

```python
if dst.exists() and not no_dedupe:
    # ... existing duplicate check logic ...
elif dst.exists() and no_dedupe:
    print(f"[NO_DEDUPE] Bypassed duplicate check, will overwrite: {dst.name}")
```

And forced regeneration (Line 678-680):
```python
# Force regeneration when --no-dedupe
if no_dedupe:
    summaries_exist = False
```

### 7. Cache Hit Bypass (Line 695)
**Location**: `process_pairs()`, cache checking logic

**Changed from**:
```python
if summaries_exist and extract_text is not None and _content_hash is not None:
```

**Changed to**:
```python
if summaries_exist and not no_dedupe and extract_text is not None and _content_hash is not None:
```

### 8. Summary Exists Bypass (Line 724, 734)
**Location**: `process_pairs()`, summary existence check

**Changed from**:
```python
elif summaries_exist:
```

**Changed to**:
```python
elif summaries_exist and not no_dedupe:
    # ... skip logic ...
elif summaries_exist and no_dedupe:
    print(f"[NO_DEDUPE] Forcing regeneration even though summaries exist for {pdf_to_use.name}")
```

### 9. Function Call Chain Updates

#### process_files_for_date() (Line 1003)
```python
def process_files_for_date(target_day: dt.date, no_dedupe: bool = False) -> tuple[int, int, int]:
    # ...
    return process_pairs(EXPORT_DIR, pairs, target_day, no_dedupe=no_dedupe)
```

#### main() date parsing (Line 1075)
```python
if len(args.dates) >= 1:
    # ... parse dates from args.dates instead of sys.argv ...
```

#### main() processing loop (Line 1094)
```python
copied, skipped, summary_skipped = process_files_for_date(target_day, no_dedupe=args.no_dedupe)
```

## Usage Examples

### Basic usage (regenerate yesterday's artifacts):
```bash
python db_filter_autorun.py --no-dedupe
```

### With specific date:
```bash
python db_filter_autorun.py 2026-02-10 --no-dedupe
```

### With date range:
```bash
python db_filter_autorun.py 2026-02-01 2026-02-10 --no-dedupe
```

## What Gets Bypassed

When `--no-dedupe` is enabled:

1. ✅ **preflight_check()** - NOT called
2. ✅ **claim_acquire()** - NOT called  
3. ✅ **claim_release()** - NOT called (no claim to release)
4. ✅ **MD5 duplicate check** - Bypassed in legacy mode
5. ✅ **bundle_complete()** - NOT called (treated as incomplete)
6. ✅ **Cache hit checks** - Bypassed (content_hash + prompt_sha256 comparison)
7. ✅ **Summary existence checks** - Forced to False, always regenerate

## What Still Happens

1. ✅ Original PDF is copied (atomic overwrite if exists)
2. ✅ Summarization pipeline runs (PDF extraction + LLM + rendering)
3. ✅ OCR attempted if needed
4. ✅ Summary JSON and PDF are written (overwrites existing)
5. ✅ Daily rollup generation (if enabled)

## Testing

All unit tests pass (14/14):
- ✅ `--no-dedupe` bypasses preflight_check
- ✅ `--no-dedupe` bypasses claim_acquire  
- ✅ Default behavior still calls dedupe functions
- ✅ Forces regeneration even when summaries exist
- ✅ Legacy mode duplicate check bypassed
- ✅ Atomic copy/overwrite works correctly

Run tests:
```bash
python test_no_dedupe_flag.py
```

## Overwrite Policy

- **Atomic writes**: Uses `safe_copy_atomic()` for PDF copies (temp file → rename)
- **Direct overwrites**: Summary JSON/PDF are written directly (existing file replaced)
- **No partial files**: Atomic pattern prevents corrupted files on crash during copy
- **Claim-free**: No database state mutations when `--no-dedupe` is set

## Logging

Sample output with `--no-dedupe`:
```
[WARN] ═══════════════════════════════════════════════════════════
[WARN] Dedupe disabled (--no-dedupe flag set)
[WARN] Will regenerate artifacts and ignore existing-duplicate checks
[WARN] Output files will be OVERWRITTEN if they exist
[WARN] ═══════════════════════════════════════════════════════════

[NO_DEDUPE] Bypassed duplicate/claim check for BOA_Commodities_20260210_w
[NO_DEDUPE] Forcing regeneration even though summaries exist for BOA_Commodities_20260210_w.pdf
[INFO] Generating summary for BOA_Commodities_20260210_w.pdf ...
[OK] Summary created for BOA_Commodities_20260210_w.pdf
```
