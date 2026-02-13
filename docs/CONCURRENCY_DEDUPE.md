# Concurrency and dedupe: how "(1)" and duplicate summaries are prevented

**Purpose:** Short explanation of how the ingest hardening (claim, manifest, validation) prevents duplicate filenames and duplicate summaries under multiple workers and retries.

## Why "(1)" cannot appear

- **Single canonical path per document:** Every ingest is identified by `doc_key` (primary: sha256 of normalized canonical URL; fallback: sha256 of PDF bytes). The **final PDF is always** `{dest}/{doc_key}.pdf`. There is no code path that writes a second file with a different name (e.g. suggested name) into the same directory; the suggested name is stored in the DB and in `meta.title` in `__sum.json` for display only.
- **Atomic write:** Download/copy goes to `{dest}/.tmp/{doc_key}.pdf.part`, then `os.replace` to `{dest}/{doc_key}.pdf`. No intermediate name is ever visible as the final file; Windows/Dropbox-style "(1)" suffixes are never used because we never create a second file with the same base name.
- **Preflight:** If a record exists for `doc_key` or `canonical_url`, or if `{dest}/{doc_key}.pdf` already exists, the job is skipped. So a retry or a second worker never creates a second file.

## How duplicate summaries are prevented under concurrency

- **Atomic claim:** Before processing, a worker calls `claim_acquire(dest_dir, doc_key)`. This does `INSERT INTO ingest_claims (doc_key, ...) ... ON CONFLICT DO NOTHING` (via a single row insert); only one process can insert. Optionally a filelock on `{dest}/.locks/{doc_key}.lock` is acquired so only one process holds the critical section. If claim fails, the worker skips (logs `[DEDUP_SKIP] reason=claim_failed`). So only one worker per `doc_key` runs the pipeline at a time.
- **Publish only after validation:** `record_success` (which writes the row that makes future preflights skip) is **not** called right after the PDF is written. It is called only from `validate_and_publish`, after all required artifacts exist (pdf, summary_json, summary_pdf). If any required artifact is missing, we log `[JOB_FAILED] missing_artifacts=...`, release the claim, and **do not** call `record_success`. So partial runs (e.g. PDF written but summary failed) do not "publish"; another worker or retry can claim and complete.
- **Idempotent retries:** If `{doc_key}.pdf` already exists, `atomic_write_pdf_from_path` returns `(True, path, True)` (already_existed). The worker releases the claim and skips downstream. So retries never create a second PDF or a second set of summaries.
- **Manifest:** On success, `{base}.manifest.json` is written with doc_id, canonical_url, source, title, pub_date and artifact entries: path (relative to EXPORT_DIR), size, and mtime (no sha256 of PDF bytes). Supports website and debugging without hashing large files.

## Summary

| Mechanism | Prevents |
|-----------|----------|
| doc_key-only filenames | "(1)" filenames (no second file with same stem) |
| Preflight (record or final exists) | Duplicate work and duplicate PDFs on retry/second worker |
| Atomic claim (DB + optional filelock) | Two workers processing the same doc_key concurrently |
| Deferred record_success (validate_and_publish) | Publishing partial outputs; ensures only full bundles are "registered" |
| Manifest + validation | Partial/corrupt runs being treated as success |
