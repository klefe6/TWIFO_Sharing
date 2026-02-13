"""
Ingest deduplication: stable identity from canonical URL (no PDF content hashing).
Deterministic base filename: {YYYYMMDD}__{source}__{title_slug}__{doc_id}.
Uses SQLite unique index + atomic write to .tmp then rename. No "(1)" on collision: skip/resume.
Author: Kevin Lefebvre
Last Updated: 2026-02-05
"""

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Optional filelock for cross-process mutual exclusion (same machine)
try:
    from filelock import FileLock
    FILELOCK_AVAILABLE = True
except ImportError:
    FILELOCK_AVAILABLE = False
    FileLock = None

# Stale claim TTL: claims older than this are deleted so another worker can retry (e.g. after crash).
# Must be longer than max expected job (OCR + summarization); 4h safe for long-running jobs.
CLAIM_STALE_SECONDS = 4 * 3600  # 4 hours
REQUIRED_ARTIFACTS = ["pdf", "summary_json", "summary_pdf"]

# Document registry status values (single source of truth for "have we processed this doc?")
STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

# Tracking query params to strip (lowercase)
_TRACKING_PARAMS = frozenset(
    "utm_source utm_medium utm_campaign utm_term utm_content utm_id gclid fbclid "
    "msclkid twclid li_fat_id mc_cid mc_eid _ga ref".split()
)
DOC_ID_LENGTH = 10  # sha1 hex truncated to 10 chars (URL identity only, fast)


def canonicalize_url(url: str) -> str:
    """
    Normalize URL for stable identity: scheme/host lowercased, fragment removed,
    common tracking params stripped (utm_*, gclid, fbclid, etc.), whitespace trimmed.
    Safe for paths: normalizes path separators when not a URL.
    """
    s = (url or "").strip()
    if not s:
        return ""
    try:
        parsed = urlparse(s)
        if parsed.scheme or "://" in s or s.startswith("//"):
            scheme = (parsed.scheme or "https").lower()
            netloc = (parsed.netloc or "").lower()
            path = (parsed.path or "").rstrip("/") or "/"
            # Strip tracking params from query
            query_dict = parse_qs(parsed.query, keep_blank_values=True)
            filtered = {k: v for k, v in query_dict.items() if k.lower() not in _TRACKING_PARAMS}
            query = urlencode(filtered, doseq=True) if filtered else ""
            # No fragment
            normalized = urlunparse((scheme, netloc, path, parsed.params, query, ""))
            return normalized.strip()
    except Exception:
        pass
    # Path or opaque string: normalize separators and trim
    return re.sub(r"[/\\]+", "/", s).strip()


def doc_id_from_canonical_url(canonical_url: str) -> str:
    """
    Short stable ID from canonical URL (URL identity hashing only; no PDF content).
    Fast: sha1 of string, hex, truncated to DOC_ID_LENGTH (8-12 chars).
    """
    raw = (canonical_url or "").encode("utf-8")
    h = hashlib.sha1(raw).hexdigest()[:DOC_ID_LENGTH]
    return h or "0" * DOC_ID_LENGTH


def slugify_title(title: str) -> str:
    """
    Produce a safe filename slug from a title: lowercase, alphanumeric and underscores,
    collapse runs of non-slug chars to single underscore, strip leading/trailing.
    """
    if not title:
        return ""
    s = re.sub(r"[^\w\s-]", "", title, flags=re.IGNORECASE)
    s = re.sub(r"[-\s]+", "_", s).strip("_").lower()
    return s[:200] or "untitled"  # cap length for filesystem


def deterministic_base_filename(date_ymd: str, source: str, title_slug: str, doc_id: str) -> str:
    """
    Deterministic base stem for bundle artifacts. Same inputs -> same filename; no (1) ever.
    Format: {YYYYMMDD}__{source}__{title_slug}__{doc_id}
    """
    safe_source = re.sub(r"[^\w-]", "", (source or "").strip())[:32] or "src"
    safe_slug = (title_slug or "untitled").strip()[:180]
    safe_id = (doc_id or "").strip()[:DOC_ID_LENGTH]
    return f"{date_ymd}__{safe_source}__{safe_slug}__{safe_id}"


def normalize_canonical_url(path_or_url: str) -> str:
    """Alias for canonicalize_url; strip tracking params, normalize scheme, trim."""
    return canonicalize_url(path_or_url)


def doc_key_from_canonical(canonical_url: str) -> str:
    """Legacy: 64-char sha256 hex. Prefer doc_id_from_canonical_url for new code."""
    return hashlib.sha256((canonical_url or "").encode("utf-8")).hexdigest()


def doc_key_from_bytes(pdf_bytes: bytes) -> str:
    """Fallback: sha256 of PDF bytes when no URL/path available."""
    return hashlib.sha256(pdf_bytes).hexdigest()


def _db_path(dest_dir: Path) -> Path:
    return dest_dir / ".ingest_dedup.db"


def _tmp_dir(dest_dir: Path) -> Path:
    d = dest_dir / ".tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _claims_key_column(conn: sqlite3.Connection) -> str:
    """Return the primary key column name for ingest_claims (doc_id for new DBs, doc_key for legacy)."""
    cur = conn.execute("PRAGMA table_info(ingest_claims)")
    cols = [row[1] for row in cur.fetchall()]
    return "doc_id" if "doc_id" in cols else "doc_key"


def _documents_columns(conn: sqlite3.Connection) -> set:
    """Return set of column names in documents table (empty if table missing)."""
    cur = conn.execute("PRAGMA table_info(documents)")
    return {row[1] for row in cur.fetchall()}


def _migrate_documents(conn: sqlite3.Connection) -> None:
    """Add registry columns to existing documents table if missing."""
    cols = _documents_columns(conn)
    if not cols:
        return
    # Add new columns; existing rows (from old schema) get status='done' so preflight skips them
    if "status" not in cols:
        try:
            conn.execute("ALTER TABLE documents ADD COLUMN status TEXT DEFAULT 'done'")
        except sqlite3.OperationalError:
            pass
    for c in ("source", "title", "pub_date", "updated_at", "error_msg"):
        if c not in cols:
            try:
                conn.execute(f"ALTER TABLE documents ADD COLUMN {c} TEXT")
            except sqlite3.OperationalError:
                pass
    conn.commit()


def _init_db(conn: sqlite3.Connection) -> None:
    # Document registry: single source of truth for dedupe + metadata
    conn.execute(
        "CREATE TABLE IF NOT EXISTS documents ("
        "doc_id TEXT PRIMARY KEY, "
        "canonical_url TEXT UNIQUE NOT NULL, "
        "source TEXT, "
        "title TEXT, "
        "title_slug TEXT NOT NULL DEFAULT '', "
        "pub_date TEXT, "
        "pdf_path TEXT, "
        "status TEXT NOT NULL DEFAULT 'pending', "
        "created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL, "
        "error_msg TEXT)"
    )
    _migrate_documents(conn)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_canonical_url ON documents(canonical_url)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_pub_date ON documents(pub_date)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)"
    )
    # Claims keyed by doc_id only (not title); atomic INSERT for concurrency safety
    conn.execute(
        "CREATE TABLE IF NOT EXISTS ingest_claims ("
        "doc_id TEXT PRIMARY KEY, "
        "worker_id TEXT, "
        "claimed_at TEXT NOT NULL)"
    )
    conn.commit()


def doc_lookup_by_url(dest_dir: Path, canonical_url: str) -> Optional[dict]:
    """
    Look up document by canonical_url. Returns row as dict (doc_id, status, pdf_path, ...) or None.
    Registry is the single source of truth for "have we processed this doc?"
    """
    db = _db_path(dest_dir)
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(str(db), timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                "SELECT * FROM documents WHERE canonical_url = ? LIMIT 1",
                (canonical_url,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    except Exception:
        return None


def doc_insert_pending(
    dest_dir: Path,
    doc_id: str,
    canonical_url: str,
    source: str,
    title: str,
    pub_date: str,
    title_slug: str,
) -> bool:
    """
    Insert a pending document row. Returns True if inserted, False if conflict (canonical_url or doc_id already exists).
    Uses INSERT ... ON CONFLICT DO NOTHING so dedupe is safe under concurrency.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    db = _db_path(dest_dir)
    conn = sqlite3.connect(str(db), timeout=10)
    try:
        _init_db(conn)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        cur = conn.execute(
            "INSERT INTO documents (doc_id, canonical_url, source, title, title_slug, pub_date, pdf_path, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, ?) ON CONFLICT(doc_id) DO NOTHING",
            (doc_id, canonical_url, source or "", title or "", title_slug or "", pub_date or "", STATUS_PENDING, now, now),
        )
        conn.commit()
        return cur.rowcount == 1
    except sqlite3.IntegrityError:
        conn.rollback()
        return False
    finally:
        conn.close()


def doc_mark_status(
    dest_dir: Path,
    doc_id: str,
    status: str,
    pdf_path: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> None:
    """
    Update document status (and optionally pdf_path, error_msg). Used on completion or failure.
    """
    db = _db_path(dest_dir)
    if not db.exists():
        return
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        conn = sqlite3.connect(str(db), timeout=5)
        try:
            if pdf_path is not None:
                conn.execute(
                    "UPDATE documents SET status = ?, pdf_path = ?, error_msg = COALESCE(?, error_msg), updated_at = ? WHERE doc_id = ?",
                    (status, pdf_path, error_msg, now, doc_id),
                )
            else:
                conn.execute(
                    "UPDATE documents SET status = ?, error_msg = ?, updated_at = ? WHERE doc_id = ?",
                    (status, error_msg or "", now, doc_id),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def preflight_check(
    dest_dir: Path, doc_id: str, canonical_url: str, base: str
) -> Tuple[bool, str]:
    """
    Skip only when registry has this doc with status=done (bundle already complete).
    If status=pending/failed or no row: do not skip (resume and generate missing artifacts).
    Does not skip on final_exists alone; bundle_complete is checked after ensure_original_pdf.
    Returns (should_skip, reason).
    """
    row = doc_lookup_by_url(dest_dir, canonical_url)
    if row is not None:
        s = (row.get("status") or "").strip().lower()
        if s == STATUS_DONE:
            return True, "record_exists"
    return False, ""


def claim_acquire(
    dest_dir: Path, doc_id: str, worker_id: Optional[str] = None
) -> Tuple[bool, Any]:
    """
    Atomic claim keyed by doc_id (not title). INSERT into ingest_claims(doc_id PRIMARY KEY, worker_id, claimed_at).
    On conflict (doc_id already claimed), return (False, None). Stale claims older than CLAIM_STALE_SECONDS
    are deleted before insert so long-running jobs are not evicted. Caller must call claim_release in
    all exit paths (success, skip, except) or in a finally block.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    db = _db_path(dest_dir)
    conn = sqlite3.connect(str(db), timeout=10)
    try:
        _init_db(conn)
        key_col = _claims_key_column(conn)
        now_ts = time.time()
        stale = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ts - CLAIM_STALE_SECONDS))
        conn.execute(
            f"DELETE FROM ingest_claims WHERE {key_col} = ? AND claimed_at < ?",
            (doc_id, stale),
        )
        worker = worker_id or ""
        claimed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ts))
        cur = conn.execute(
            f"INSERT INTO ingest_claims ({key_col}, worker_id, claimed_at) VALUES (?, ?, ?)",
            (doc_id, worker, claimed_at),
        )
        conn.commit()
        if cur.rowcount != 1:
            return False, None
    except sqlite3.IntegrityError:
        return False, None
    finally:
        try:
            conn.close()
        except Exception:
            pass

    lock_handle = None
    if FILELOCK_AVAILABLE and FileLock is not None:
        lock_dir = dest_dir / ".locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / f"{doc_id}.lock"
        lock_handle = FileLock(str(lock_path), timeout=0)
        try:
            lock_handle.acquire()
        except Exception:
            _claim_release_db(dest_dir, doc_id)
            return False, None
    return True, lock_handle


def _claim_release_db(dest_dir: Path, doc_id: str) -> None:
    """Release claim in DB only (idempotent)."""
    db = _db_path(dest_dir)
    if not db.exists():
        return
    try:
        conn = sqlite3.connect(str(db), timeout=5)
        key_col = _claims_key_column(conn)
        conn.execute(f"DELETE FROM ingest_claims WHERE {key_col} = ?", (doc_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def claim_release(dest_dir: Path, doc_id: str, lock_handle: Any = None) -> None:
    """Release claim: release filelock (if any), then delete DB claim row. Safe to call multiple times."""
    if lock_handle is not None:
        try:
            lock_handle.release()
        except Exception:
            pass
    _claim_release_db(dest_dir, doc_id)


def record_success(
    dest_dir: Path,
    doc_id: str,
    canonical_url: str,
    title_slug: str,
    pdf_path: Path,
) -> None:
    """Mark document as done and set pdf_path in registry (single source of truth)."""
    doc_mark_status(dest_dir, doc_id, STATUS_DONE, pdf_path=str(pdf_path))


def ensure_original_pdf_in_export(
    export_dir: Path,
    base_name: str,
    pdf_source_path: Path,
    path_manager=None,
) -> Tuple[Optional[Path], bool]:
    """
    Always transfer original PDF before any OCR/summarization.

    When *path_manager* is provided the destination is
    ``path_manager.original_pdf_path(base_name)`` (i.e. ``originals/``).
    Otherwise falls back to ``export_dir/{base_name}.pdf`` (legacy layout).

    Writes via ``.tmp/{base_name}.pdf.part`` then atomic rename.  If the
    destination already exists, returns ``(final_path, True)``.  Never
    creates ``(1)`` variants.

    Returns:
        ``(final_pdf_path, already_existed)``; ``(None, False)`` on failure.
    """
    import shutil

    export_dir = Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    # Route destination: originals/ when path_manager enabled, else export root
    if path_manager is not None:
        final = path_manager.original_pdf_path(f"{base_name}.pdf")
        final.parent.mkdir(parents=True, exist_ok=True)
    else:
        final = export_dir / f"{base_name}.pdf"

    if final.exists():
        return final, True

    tmp_dir = _tmp_dir(export_dir)
    part = tmp_dir / f"{base_name}.pdf.part"
    try:
        if not Path(pdf_source_path).exists():
            print(f"[ERR] ensure_original_pdf_in_export: source does not exist: {pdf_source_path}")
            return None, False
        if part.exists():
            part.unlink()
        shutil.copy2(str(pdf_source_path), str(part))
        n_bytes = part.stat().st_size
        if n_bytes <= 0:
            if part.exists():
                try:
                    part.unlink()
                except Exception:
                    pass
            print(f"[ERR] ensure_original_pdf_in_export: file size <= 0 after copy")
            return None, False
        os.replace(str(part), str(final))
        print(f"[WRITE_OK] path={final} bytes={n_bytes}")
        return final, False
    except Exception as e:
        if part.exists():
            try:
                part.unlink()
            except Exception:
                pass
        print(f"[ERR] ensure_original_pdf_in_export failed: {e}")
        return None, False


def atomic_write_pdf_from_path(
    dest_dir: Path, base: str, src_path: Path
) -> Tuple[bool, Optional[Path], bool]:
    """
    Copy src_path to dest_dir/.tmp/{base}.pdf.part, then atomic rename to dest_dir/{base}.pdf.
    If dest_dir/{base}.pdf already exists: delete .part and return (True, final_path, True).
    Never creates (1) suffix; deterministic path only. Returns (success, final_path, already_existed).
    Prefer ensure_original_pdf_in_export for "transfer then use stable path" flow.
    """
    import shutil

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = _tmp_dir(dest_dir)
    part = tmp_dir / f"{base}.pdf.part"
    final = dest_dir / f"{base}.pdf"

    if final.exists():
        if part.exists():
            try:
                part.unlink()
            except Exception:
                pass
        return True, final, True  # Already exists -> skip downstream, no rename to (1)

    try:
        if part.exists():
            part.unlink()
        shutil.copy2(str(src_path), str(part))
        n_bytes = part.stat().st_size
        os.replace(str(part), str(final))
        print(f"[WRITE_OK] path={final} bytes={n_bytes}")
        return True, final, False
    except Exception as e:
        if part.exists():
            try:
                part.unlink()
            except Exception:
                pass
        print(f"[ERR] atomic_write_pdf_from_path failed: {e}")
        return False, None, False


def ensure_original_pdf_in_bundle(
    dest_dir: Path, base: str, pdf_source_path: Path
) -> Tuple[bool, Optional[Path], Optional[str]]:
    """
    Copy original PDF from pdf_source_path into bundle at {dest_dir}/{base}.pdf
    using .part + atomic rename. Verifies file size > 0; manifest records sha256.
    Returns (success, final_path, sha256). Never creates (1) suffix.
    """
    import shutil

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = _tmp_dir(dest_dir)
    part = tmp_dir / f"{base}.pdf.part"
    final = dest_dir / f"{base}.pdf"

    try:
        if not Path(pdf_source_path).exists():
            print(f"[ERR] ensure_original_pdf_in_bundle: source does not exist: {pdf_source_path}")
            return False, None, None
        if part.exists():
            part.unlink()
        shutil.copy2(str(pdf_source_path), str(part))
        n_bytes = part.stat().st_size
        if n_bytes <= 0:
            if part.exists():
                try:
                    part.unlink()
                except Exception:
                    pass
            print(f"[ERR] ensure_original_pdf_in_bundle: file size <= 0 after copy")
            return False, None, None
        os.replace(str(part), str(final))
        sha = _file_sha256(final)
        print(f"[WRITE_OK] path={final} bytes={n_bytes} sha256={sha[:16]}...")
        return True, final, sha
    except Exception as e:
        if part.exists():
            try:
                part.unlink()
            except Exception:
                pass
        print(f"[ERR] ensure_original_pdf_in_bundle failed: {e}")
        return False, None, None


def get_suggested_name(dest_dir: Path, doc_id: str) -> Optional[str]:
    """Return title_slug for doc_id from documents table, or None."""
    db = _db_path(dest_dir)
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(str(db), timeout=5)
        try:
            cur = conn.execute(
                "SELECT title_slug FROM documents WHERE doc_id = ? LIMIT 1",
                (doc_id,),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] else None
        finally:
            conn.close()
    except Exception:
        return None


def _file_sha256(path: Path) -> str:
    """SHA256 hex digest of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _artifact_paths(dest_dir: Path, base: str) -> dict:
    """Map artifact key -> path: {base}.pdf, {base}__sum.json, {base}__sum.pdf, etc."""
    return {
        "pdf": dest_dir / f"{base}.pdf",
        "summary_json": dest_dir / f"{base}__sum.json",
        "summary_pdf": dest_dir / f"{base}__sum.pdf",
        "ocr_txt": dest_dir / f"{base}__ocr.txt",
        "ocr_pdf": dest_dir / f"{base}__ocr.pdf",
    }


def bundle_state(
    dest_dir: Path, base: str, required: Optional[List[str]] = None
) -> dict:
    """
    Check which bundle artifacts exist. Returns dict artifact_key -> bool (exists).
    Includes required artifacts (default REQUIRED_ARTIFACTS) plus manifest.
    """
    required = required or REQUIRED_ARTIFACTS
    paths = _artifact_paths(dest_dir, base)
    out = {k: paths[k].exists() for k in required}
    manifest_path = dest_dir / f"{base}.manifest.json"
    out["manifest"] = manifest_path.exists()
    return out


def bundle_complete(
    dest_dir: Path,
    base: str,
    required: Optional[List[str]] = None,
    require_manifest: bool = True,
) -> bool:
    """
    True only when ALL required artifacts exist (pdf + summary_json + summary_pdf)
    and optionally manifest. Use to decide full skip vs resume (generate missing only).
    """
    state = bundle_state(dest_dir, base, required=required)
    req = required or REQUIRED_ARTIFACTS
    if not all(state.get(k, False) for k in req):
        return False
    if require_manifest and not state.get("manifest", False):
        return False
    return True


def collect_artifact_info(dest_dir: Path, base: str) -> dict:
    """
    Build manifest-ready dict: artifact_key -> {path (relative to dest_dir), size, mtime}.
    No sha256 (avoids hashing PDF bytes). Only includes entries for files that exist.
    """
    dest_dir = Path(dest_dir)
    paths = _artifact_paths(dest_dir, base)
    out: dict = {}
    for key, p in paths.items():
        if p.exists():
            try:
                st = p.stat()
                rel = os.path.relpath(str(p), str(dest_dir))
                out[key] = {
                    "path": str(rel),
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                }
            except Exception:
                pass
    return out


def validate_artifacts(
    dest_dir: Path, base: str, required: Optional[List[str]] = None
) -> Tuple[bool, List[str]]:
    """
    Check that all required artifact files exist at bundle paths. Returns (ok, missing_keys).
    Default required = REQUIRED_ARTIFACTS (pdf, summary_json, summary_pdf).
    """
    required = required or REQUIRED_ARTIFACTS
    paths = _artifact_paths(dest_dir, base)
    missing = [k for k in required if not paths[k].exists()]
    return (len(missing) == 0, missing)


def write_manifest(
    dest_dir: Path,
    base: str,
    artifact_info: Optional[dict] = None,
    doc_meta: Optional[dict] = None,
) -> Path:
    """
    Write {base}.manifest.json with artifacts (path relative to dest_dir, size, mtime)
    and optional doc fields (doc_id, canonical_url, source, title, pub_date) for website/debugging.
    No sha256 of PDF bytes. Returns path to manifest file.
    """
    dest_dir = Path(dest_dir)
    if artifact_info is None:
        artifact_info = collect_artifact_info(dest_dir, base)
    manifest_path = dest_dir / f"{base}.manifest.json"
    payload = {
        "base": base,
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "artifacts": artifact_info,
    }
    if doc_meta:
        for k in ("doc_id", "canonical_url", "source", "title", "pub_date"):
            if k in doc_meta and doc_meta[k] is not None:
                payload[k] = doc_meta[k]
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def validate_and_publish(
    dest_dir: Path,
    doc_id: str,
    canonical_url: str,
    title_slug: str,
    base: str,
    pdf_source_path: Path,
    lock_handle: Any = None,
    required: Optional[List[str]] = None,
    source: Optional[str] = None,
    title: Optional[str] = None,
    pub_date: Optional[str] = None,
) -> bool:
    """
    Ensure original PDF is in bundle at {base}.pdf, validate required artifacts, write manifest
    (with doc_id, canonical_url, source, title, pub_date; artifact paths relative, size/mtime only),
    record_success in documents, release claim. Never creates (1) suffix.
    """
    ok_ensure, bundle_pdf_path, _sha = ensure_original_pdf_in_bundle(
        dest_dir, base, pdf_source_path
    )
    if not ok_ensure or bundle_pdf_path is None:
        claim_release(dest_dir, doc_id, lock_handle)
        return False
    ok, missing = validate_artifacts(dest_dir, base, required=required)
    if not ok:
        print(f"[JOB_FAILED] doc_id={doc_id} missing_artifacts={missing}")
        claim_release(dest_dir, doc_id, lock_handle)
        return False
    doc_meta = {
        "doc_id": doc_id,
        "canonical_url": canonical_url,
        "source": source,
        "title": title,
        "pub_date": pub_date,
    }
    write_manifest(dest_dir, base, doc_meta=doc_meta)
    record_success(dest_dir, doc_id, canonical_url, title_slug, bundle_pdf_path)
    claim_release(dest_dir, doc_id, lock_handle)
    return True
