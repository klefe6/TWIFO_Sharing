# Manifest format (website + debugging, no PDF hashing)

**Purpose:** Manifest supports the website and debugging without hashing PDF bytes. Dedupe does not depend on content hashes.

**Last updated:** 2026-02-05

---

## Required manifest fields

| Field | Type | Description |
|-------|------|-------------|
| **base** | string | Bundle base name (e.g. `20260108__BOA__weekly__abc1234567`). |
| **doc_id** | string | Stable document id (from canonical URL). |
| **canonical_url** | string | Normalized document URL. |
| **source** | string | Provider/source code (e.g. BOA, GM). |
| **title** | string | Display title. |
| **pub_date** | string | Publication date YYYYMMDD. |
| **written_at** | string | ISO8601 UTC when manifest was written. |
| **artifacts** | object | Map artifact_key → { path, size, mtime }. |

### Artifact entry (per file)

| Field | Type | Description |
|-------|------|-------------|
| **path** | string | Path **relative to EXPORT_DIR** (e.g. `20260108__BOA__weekly__x.pdf`). |
| **size** | int | File size in bytes. |
| **mtime** | number | Modification time (Unix timestamp, float). |

No `sha256` in artifact entries (avoids hashing PDF bytes for large files).

### Optional (for backwards compatibility)

- **title_slug** | string | Slug used in base name (can be derived from base).

---

## Dedupe: no content hashes

Confirmed: nothing in dedupe depends on PDF content hashes.

- **doc_id** is from `doc_id_from_canonical_url(canonical_url)` (hash of URL, not file bytes).
- **Preflight** uses registry `status` (done/pending/failed).
- **bundle_state / bundle_complete** use file **existence** only.
- **validate_artifacts** checks required paths exist; no hash comparison.
- **Manifest** is not read by dedupe logic; it is written after validation for website/debugging only.

`_file_sha256` remains only where explicitly used (e.g. optional logging in `ensure_original_pdf_in_bundle`); it is no longer stored in the manifest.

---

## Patch plan

1. **ingest_dedup.py**
   - **collect_artifact_info**: For each artifact, emit `path` (relative to `dest_dir`), `size`, `mtime`. Remove `sha256`. Use `os.path.relpath(p, dest_dir)` or `p.name` for deterministic relative paths (e.g. `{base}.pdf`).
   - **write_manifest**: Add optional `doc_meta: Optional[dict]` with keys `doc_id`, `canonical_url`, `source`, `title`, `pub_date`. Include these in payload when provided. Payload: `base`, `doc_id`, `canonical_url`, `source`, `title`, `pub_date`, `written_at`, `artifacts`.
   - **validate_and_publish**: Add optional `source`, `title`, `pub_date`; pass `doc_meta` into `write_manifest(dest_dir, base, artifact_info=None, doc_meta=...)`.

2. **db_filter_autorun.py**
   - All `validate_and_publish(..., base, final_path, dedup_claim_handle)` calls: add kwargs `source=provider_code`, `title=suggested_name`, `pub_date=published_date` so manifest gets doc metadata.

3. **Tests**
   - **test_manifest_written_after_validation**: Assert artifact entries have `path` (relative), `size`, `mtime`; no `sha256`. Assert top-level `doc_id`, `canonical_url` when `doc_meta` passed.
   - **test_ensure_original_pdf_in_bundle_and_publish_from_temp**: Remove assertion on `data["artifacts"]["pdf"]["sha256"]`; optionally assert `size`/`mtime` or doc fields present.

4. **Docs**
   - **CONCURRENCY_DEDUPE.md**: Update manifest bullet to "path (relative to export), size, mtime; no sha256".

---

## Example manifest (new format)

```json
{
  "base": "20260108__BOA__weekly__abc1234567",
  "doc_id": "abc1234567",
  "canonical_url": "https://example.com/weekly.pdf",
  "source": "BOA",
  "title": "BOA Weekly 20260108",
  "pub_date": "20260108",
  "written_at": "2026-02-05T12:00:00Z",
  "artifacts": {
    "pdf": { "path": "20260108__BOA__weekly__abc1234567.pdf", "size": 102400, "mtime": 1738742400.0 },
    "summary_json": { "path": "20260108__BOA__weekly__abc1234567__sum.json", "size": 2048, "mtime": 1738742410.0 },
    "summary_pdf": { "path": "20260108__BOA__weekly__abc1234567__sum.pdf", "size": 8192, "mtime": 1738742415.0 }
  }
}
```
