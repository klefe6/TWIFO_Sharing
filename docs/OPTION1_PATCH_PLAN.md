# Option 1: DB-backed identity + title-based filenames — Audit & Patch Plan

**Goal:** No duplicates, no "(1)", title slug + stable doc_id in PDF filename, dedupe by canonical_url/doc_id in DB, concurrency-safe, original PDF always in EXPORT_DIR bundle.

---

## 1. Exact functions/files: URL, title, dedupe today

### Source / canonical URL

| Where | File | Function/Location | What |
|-------|------|-------------------|------|
| **Created** | `db_filter_autorun.py` | Line 529: `canonical_url = normalize_canonical_url(str(src))` | `src` = source PDF path (Dropbox); path string is normalized as “canonical URL” |
| **Normalized** | `ingest_dedup.py` | `normalize_canonical_url(path_or_url)` (lines 32–48) | Strip query/fragment, lowercase scheme, normalize path separators for local paths |
| **Identity from URL** | `ingest_dedup.py` | `doc_key_from_canonical(canonical_url)` (lines 51–53) | Returns 64-char hex `sha256(canonical_url)` (no PDF bytes) |
| **Stored** | `ingest_dedup.py` | `record_success(..., canonical_url, ...)` → table `ingest_dedup` | Column `canonical_url TEXT UNIQUE NOT NULL` |
| **Preflight** | `ingest_dedup.py` | `preflight_check(dest_dir, doc_key, canonical_url)` (92–116) | Skips if SELECT finds doc_key or canonical_url in `ingest_dedup`, or if `{dest_dir}/{doc_key}.pdf` exists |

There is no separate “article URL” from the web; the only source identity is the **file path** of the PDF in Dropbox, normalized via `normalize_canonical_url`.

### Title / filename (suggested name)

| Where | File | Function/Location | What |
|-------|------|-------------------|------|
| **Derived** | `db_filter_autorun.py` | `normalize_base_name(prefix, raw_name, year)` (416–429) | Returns `(orig, file_base)`; `file_base` = human-readable slug from `raw_name` (strip prefix, year, normalize spaces) |
| **Built** | `db_filter_autorun.py` | `process_day()` (451–491): `suggested = f"{prefix}_{file_base}_{date_str}_{freq}.pdf"`, `dst = EXPORT_DIR / suggested` | Full suggested filename stem = `prefix_file_base_YYYYMMDD_freq` (e.g. `BOA_Weekly_20260108_w`) |
| **Variable** | `db_filter_autorun.py` | Line 509: `suggested_name = dst.stem` | Used as display title and passed to `record_success` / `validate_and_publish` |
| **Display in JSON** | `db_filter_autorun.py` | Lines 786–791: when DEDUPE_AVAILABLE and `stem_to_use != suggested_name`, patch `meta.title = suggested_name` in `__sum.json` | So website sees human title even when on-disk name is `doc_key.pdf` |
| **Stub title** | `db_filter_autorun.py` | `write_failed_summary_stub()` line 297: `"title": dst_pdf.stem` | Failed-summary stub uses PDF stem as title |

So: **title** = `suggested_name` = `dst.stem` = `{prefix}_{file_base}_{date_str}_{freq}`. It is chosen in `process_day()` from provider prefix + normalized base name + date + frequency.

### Current dedupe / claim (ingest_dedup + integration)

| Where | File | What |
|-------|------|------|
| **DB file** | `ingest_dedup.py` | `_db_path(dest_dir)` → `dest_dir / ".ingest_dedup.db"` (line 62) |
| **Tables** | `ingest_dedup.py` | `_init_db(conn)` (70–88): `ingest_dedup` (doc_key PK, canonical_url UNIQUE, suggested_name, pdf_path, created_at); `ingest_claims` (doc_key PK, worker_id, claimed_at) |
| **Preflight** | `ingest_dedup.py` | `preflight_check()` — SELECT by doc_key or canonical_url; also checks `{dest_dir}/{doc_key}.pdf` exists |
| **Claim** | `ingest_dedup.py` | `claim_acquire()` / `claim_release()` — INSERT into `ingest_claims`, optional filelock on `{dest}/.locks/{doc_key}.lock` |
| **Record** | `ingest_dedup.py` | `record_success()` — INSERT OR REPLACE into `ingest_dedup` |
| **Integration** | `db_filter_autorun.py` | Lines 527–558: get canonical_url, doc_key; preflight → skip; claim_acquire → skip if not acquired; `atomic_write_pdf_from_path(EXPORT_DIR, doc_key, src)` → file `{doc_key}.pdf`; then validate_and_publish (which calls ensure_original_pdf_in_bundle, validate_artifacts, write_manifest, record_success, claim_release). All downstream paths use `final_path.stem` (= doc_key) for `__sum.json` / `__sum.pdf`. |

Current artifact naming: **everything uses 64-char `doc_key`** (e.g. `{doc_key}.pdf`, `{doc_key}__sum.json`). Title is **not** in the filename; it is only in DB (`suggested_name`) and in `__sum.json` `meta.title`.

---

## 2. Proposed DB schema (document registry)

Single document registry table; keep claims table keyed by same identity.

**Table: `documents`** (replaces or extends current `ingest_dedup` usage as the source of truth for “published” docs)

```sql
CREATE TABLE documents (
  doc_id TEXT PRIMARY KEY,
  canonical_url TEXT UNIQUE NOT NULL,
  title_slug TEXT NOT NULL,
  pdf_path TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_documents_canonical_url ON documents(canonical_url);
```

- **doc_id:** Short stable identity from canonical URL only (e.g. 8 chars). Used in filenames and for claims. No PDF-content hash.
- **canonical_url:** Normalized source path/URL; dedupe key.
- **title_slug:** Human-readable slug used in the PDF filename (same as current `suggested_name` / stem without `.pdf`).
- **pdf_path:** Full path to the final PDF in EXPORT_DIR (deterministic filename including doc_id).
- **created_at:** For auditing/ordering.

**Claims:** Keep `ingest_claims` keyed by **doc_id** (not 64-char doc_key):

```sql
-- ingest_claims: same as today but key by doc_id
doc_id TEXT PRIMARY KEY,
worker_id TEXT,
claimed_at TEXT NOT NULL
```

**Code paths:**

- **Read:** Preflight (by doc_id and/or canonical_url), get_suggested_name → by doc_id; website/rollups can resolve doc_id → title_slug / pdf_path from `documents`.
- **Write:** On successful publish only: INSERT into `documents` (doc_id, canonical_url, title_slug, pdf_path, created_at). Claim: INSERT into `ingest_claims` (doc_id, ...); DELETE on release.

**Migration:** Existing `ingest_dedup` table can be kept for backward compatibility and populated from the same publish path with doc_id + canonical_url + suggested_name → title_slug + pdf_path, or we rename/repurpose it to `documents` and add `doc_id` + `title_slug` (and keep canonical_url, pdf_path, created_at). Minimal change: add `documents` table; preflight/record write to both during transition, then phase out ingest_dedup if desired.

---

## 3. Deterministic filename template

**Template:**

```text
{date_str}__{title_slug}__{freq}__{doc_id}.pdf
```

- **date_str:** `YYYYMMDD` (e.g. `20260205`).
- **title_slug:** Same as current suggested_name stem (e.g. `BOA_Weekly_20260108_w` or a normalized slug without date/freq if you split them). Must be deterministic for the same source (same provider/date/freq → same title_slug).
- **freq:** One of `w`/`m`/`q`/`y`/`u` (from `frequency_code(orig)`).
- **doc_id:** Short stable id from canonical_url only (e.g. 8 hex chars from sha256(canonical_url), or base32(sha1(canonical_url))[:8]).

**Determinism:** Same canonical_url → same doc_id. Same source file (same path/date/provider) → same date_str, title_slug, freq. So same filename every time; no “pick a new name if exists” → no "(1)".

**Artifact naming (consistent with template):**

- PDF: `{date_str}__{title_slug}__{freq}__{doc_id}.pdf`
- Summary JSON: `{date_str}__{title_slug}__{freq}__{doc_id}__sum.json`
- Summary PDF: `{date_str}__{title_slug}__{freq}__{doc_id}__sum.pdf`
- Manifest: `{date_str}__{title_slug}__{freq}__{doc_id}.manifest.json`
- OCR artifacts: `...__{doc_id}__ocr.txt` / `...__ocr.pdf` as needed.

So the **stem** used everywhere is `{date_str}__{title_slug}__{freq}__{doc_id}`. That stem is the single “bundle base name” for that document.

---

## 4. Step-by-step patch plan

### 4.1 ingest_dedup.py

1. **Add short doc_id (no content hash)**  
   - Add `doc_id_from_canonical(canonical_url: str) -> str` (e.g. last 8 chars of existing sha256 hex, or base32(sha1)[:8]). Keep `doc_key_from_canonical` for internal use or drop in favor of doc_id everywhere.
2. **Add document registry table**  
   - In `_init_db`, add `documents` table and index as above. Keep `ingest_claims` but use `doc_id` as primary key (column name `doc_id`).
3. **Filename from doc_id + title_slug**  
   - Add `bundle_stem(date_str: str, title_slug: str, freq: str, doc_id: str) -> str` returning `f"{date_str}__{title_slug}__{freq}__{doc_id}"`. Add `bundle_pdf_path(dest_dir: Path, stem: str) -> Path` = `dest_dir / f"{stem}.pdf"`.
4. **Preflight by doc_id and canonical_url**  
   - `preflight_check(dest_dir, doc_id, canonical_url)` (and optionally stem): skip if `documents` has doc_id or canonical_url, or if bundle PDF path exists. (If you keep preflight on “final path exists”, use the deterministic bundle path.)
5. **Claims keyed by doc_id**  
   - `claim_acquire(dest_dir, doc_id, ...)` / `claim_release(dest_dir, doc_id, ...)`; lock file `{dest}/.locks/{doc_id}.lock`.
6. **Record in documents**  
   - `record_success(dest_dir, doc_id, canonical_url, title_slug, pdf_path)` → INSERT OR REPLACE into `documents`. Optionally keep writing to `ingest_dedup` for backward compat during transition.
7. **Artifact paths by stem**  
   - `_artifact_paths(dest_dir, stem)` (or keep a single “stem” for the bundle): pdf = `dest_dir / f"{stem}.pdf"`, summary_json = `dest_dir / f"{stem}__sum.json"`, etc. All call sites that currently use `doc_key` for paths switch to `stem`.
8. **ensure_original_pdf_in_bundle**  
   - Signature: `ensure_original_pdf_in_bundle(dest_dir, stem, pdf_source_path)`; writes to `{dest_dir}/{stem}.pdf` via .part + rename; verify size > 0; return (success, path, sha256). No doc_key in filename.
9. **validate_and_publish**  
   - Takes `doc_id`, `canonical_url`, `title_slug`, `stem`, `pdf_source_path`, lock_handle. Calls ensure_original_pdf_in_bundle(dest_dir, stem, pdf_source_path); then validate_artifacts(dest_dir, stem); write_manifest(dest_dir, stem); record_success(..., doc_id, canonical_url, title_slug, bundle_pdf_path); claim_release(dest_dir, doc_id, lock_handle).
10. **get_suggested_name**  
    - Replace or add `get_title_slug(dest_dir, doc_id) -> Optional[str]` reading `title_slug` from `documents`.

### 4.2 db_filter_autorun.py

1. **process_day**  
   - Unchanged: still produces `(src, dst)` with `dst = EXPORT_DIR / suggested`, `suggested = f"{prefix}_{file_base}_{date_str}_{freq}.pdf"`. So you have `date_str`, `prefix`, `file_base`, `freq` and current `suggested_name = dst.stem`. For Option 1, **title_slug** can equal this stem (so filename becomes `{date_str}__{title_slug}__{freq}__{doc_id}.pdf`). If you want to avoid repeating date/freq in title_slug, you could set `title_slug = f"{prefix}_{file_base}"` and then stem = `f"{title_slug}_{date_str}_{freq}__{doc_id}"`; either way, keep it deterministic.
2. **Per-file loop (DEDUPE_AVAILABLE)**  
   - Compute `canonical_url = normalize_canonical_url(str(src))`.  
   - Compute `doc_id = doc_id_from_canonical(canonical_url)` (new).  
   - Compute **stem** = `bundle_stem(date_str, suggested_name, freq, doc_id)` (or suggested_name used as title_slug; suggested_name is currently `prefix_file_base_date_str_freq`, so you may use it as-is and stem = `f"{suggested_name}__{doc_id}"` to keep title visible and add doc_id). So stem = `f"{suggested_name}__{doc_id}"`.  
   - Preflight: `preflight_check(EXPORT_DIR, doc_id, canonical_url)` (and optionally stem).  
   - Claim: `claim_acquire(EXPORT_DIR, doc_id)`.  
   - Copy into bundle: `ensure_original_pdf_in_bundle(EXPORT_DIR, stem, src)` (or keep atomic_write for the initial copy and ensure_original in validate_and_publish; see below).  
   - Downstream: all paths use `stem` (summary_json_path = `EXPORT_DIR / f"{stem}__sum.json"`, etc.).  
   - On success: `validate_and_publish(EXPORT_DIR, doc_id, canonical_url, title_slug=suggested_name, stem=stem, pdf_source_path=final_path, lock_handle=...)`.  
   - Replace every `doc_key` / `final_path.stem` with `stem` and every `record_success`/validate_and_publish call with the new signature.
3. **Legacy branch (not DEDUPE_AVAILABLE)**  
   - Leave as-is (still uses `dst`, `dst.stem`) until you retire it.
4. **write_failed_summary_stub**  
   - Called with the PDF path; stub uses `dst_pdf.stem` for title. When using stems, pass the bundle PDF path so stem = bundle stem (title comes from suggested_name patched into meta.title or from stem).

### 4.3 Order of operations (no "(1)", bundle always in EXPORT_DIR)

1. Preflight by doc_id/canonical_url and, if desired, by presence of bundle PDF at deterministic path.  
2. Claim by doc_id.  
3. Copy original PDF into EXPORT_DIR at deterministic path `{stem}.pdf` (via .part + rename).  
4. Run summarization; write `{stem}__sum.json`, `{stem}__sum.pdf`, etc.  
5. Validate bundle (all required artifacts at paths derived from `stem`).  
6. Write manifest; INSERT into `documents`; release claim.  

Never choose a “new” filename if the target exists; treat as already processed and skip or resume.

### 4.4 Files to touch (summary)

| File | Changes |
|------|--------|
| **ingest_dedup.py** | Add doc_id_from_canonical, documents table + init, bundle_stem + bundle_pdf_path, preflight/claim/record by doc_id, _artifact_paths(dest_dir, stem), ensure_original_pdf_in_bundle(dest_dir, stem, src), validate_and_publish(..., doc_id, title_slug, stem, ...), get_title_slug or get_suggested_name by doc_id |
| **db_filter_autorun.py** | Use doc_id and stem; compute stem = f"{suggested_name}__{doc_id}"; preflight/claim/copy/validate_and_publish with new signatures; all summary paths from stem |
| **tests/test_ingest_dedup.py** | Update tests to use doc_id + stem and new filename template; add test that same canonical_url produces same stem and no "(1)" |

### 4.5 Backward compatibility

- Existing exports with `{doc_key}.pdf` (64-char hex) remain on disk. New ingest uses new template. Website/rollups: can list both patterns during transition; prefer manifest / DB for title and path.
- Optional: one-time migration script that inserts into `documents` from existing `ingest_dedup` rows and renames files to new template (or leave old files and only new files use new naming).

---

## 5. Checklist (hard requirements)

- [ ] No duplicates: preflight + claim + deterministic filename so same doc never gets two files.  
- [ ] No "(1)": never generate a second filename when one exists; skip or treat as already processed.  
- [ ] PDF filename includes title slug + doc_id: `{date_str}__{title_slug}__{freq}__{doc_id}.pdf` (or equivalent with suggested_name and doc_id).  
- [ ] Dedupe by canonical_url and doc_id in DB: documents table + unique index on canonical_url.  
- [ ] Concurrency-safe: claim by doc_id (ingest_claims), optional filelock.  
- [ ] Original PDF always in EXPORT_DIR: ensure_original_pdf_in_bundle (or equivalent) writes to deterministic bundle path; validate_and_publish validates bundle paths only.
