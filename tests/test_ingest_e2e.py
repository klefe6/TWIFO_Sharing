"""
E2E integration tests: ingest same document twice, concurrency simulation.
Verifies one PDF, one DB row, no (1) files, DEDUP_SKIP/resume, and single claim under concurrency.
Author: Kevin Lefebvre
Last Updated: 2026-02-05
"""

import datetime as dt
import io
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tempfile


def _make_suggested_name() -> str:
    """Suggested name that yields valid provider/date/freq in db_filter_autorun."""
    return "BOA_Weekly_20260108_w"


def test_e2e_ingest_same_document_twice():
    """
    Ingest the same document twice via process_pairs.
    Assert: only one PDF in EXPORT_DIR; filename contains title_slug and doc_id; no (1) files;
    DB documents table has exactly one row for canonical_url; second run skips or resumes correctly.
    """
    from ingest_dedup import (
        canonicalize_url,
        doc_id_from_canonical_url,
        doc_lookup_by_url,
        slugify_title,
        deterministic_base_filename,
    )

    try:
        from db_filter_autorun import process_pairs
    except ImportError:
        raise ImportError("db_filter_autorun required (ingest_dedup + process_pairs)")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        export_dir = tmp / "export"
        export_dir.mkdir(parents=True, exist_ok=True)
        suggested = _make_suggested_name()
        src = tmp / f"{suggested}.pdf"
        src.write_bytes(b"%PDF-1.4 minimal content for e2e test\n" * 100)
        dst = export_dir / f"{suggested}.pdf"
        target_day = dt.date(2026, 1, 8)
        pairs = [(src, dst)]

        canonical_url = canonicalize_url(str(src))
        doc_id = doc_id_from_canonical_url(canonical_url)
        title_slug = slugify_title(suggested)
        expected_base = deterministic_base_filename("20260108", "BOA", title_slug, doc_id)

        # First ingest
        process_pairs(export_dir, pairs, target_day)
        # Second ingest (same doc)
        process_pairs(export_dir, pairs, target_day)

        # Only one PDF in export dir (deterministic base; no (1))
        pdfs = list(export_dir.glob("*.pdf"))
        assert len(pdfs) == 1, f"Expected 1 PDF, got {len(pdfs)}: {[p.name for p in pdfs]}"
        single_pdf = pdfs[0]
        assert single_pdf.stem == expected_base, f"Filename should be {expected_base}.pdf, got {single_pdf.name}"
        assert title_slug in single_pdf.stem and doc_id in single_pdf.stem

        # No (1) variants
        all_files = list(export_dir.glob("*"))
        assert not any("(1)" in p.name for p in all_files), "No (1) files should exist"

        # DB: exactly one row for this canonical_url
        row = doc_lookup_by_url(export_dir, canonical_url)
        assert row is not None, "Documents table should have one row for canonical_url"
        assert row.get("doc_id") == doc_id


def test_e2e_second_ingest_logs_dedup_skip_when_complete():
    """
    When bundle is complete (status=done), second ingest logs DEDUP_SKIP reason=record_exists.
    """
    from ingest_dedup import (
        canonicalize_url,
        doc_id_from_canonical_url,
        doc_insert_pending,
        doc_mark_status,
        slugify_title,
        STATUS_DONE,
    )

    try:
        from db_filter_autorun import process_pairs
    except ImportError:
        raise ImportError("db_filter_autorun required")

    from ingest_dedup import deterministic_base_filename

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        export_dir = tmp / "export"
        export_dir.mkdir(parents=True, exist_ok=True)
        suggested = _make_suggested_name()
        src = tmp / f"{suggested}.pdf"
        src.write_bytes(b"%PDF-1.4 minimal\n" * 50)
        dst = export_dir / f"{suggested}.pdf"
        target_day = dt.date(2026, 1, 8)
        pairs = [(src, dst)]

        canonical_url = canonicalize_url(str(src))
        doc_id = doc_id_from_canonical_url(canonical_url)
        title_slug = slugify_title(suggested)
        base = deterministic_base_filename("20260108", "BOA", title_slug, doc_id)

        # Simulate completed bundle: one row status=done, and stub artifacts + manifest
        doc_insert_pending(export_dir, doc_id, canonical_url, source="BOA", title=suggested, pub_date="20260108", title_slug=title_slug)
        doc_mark_status(export_dir, doc_id, STATUS_DONE, pdf_path=str(export_dir / f"{base}.pdf"))
        (export_dir / f"{base}.pdf").write_bytes(b"%PDF-1.4\n")
        (export_dir / f"{base}__sum.json").write_text("{}")
        (export_dir / f"{base}__sum.pdf").write_bytes(b"%PDF\n")
        (export_dir / f"{base}.manifest.json").write_text("{}")

        # Capture stdout for second run
        out = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = out
        try:
            process_pairs(export_dir, pairs, target_day)
        finally:
            sys.stdout = old_stdout
        log = out.getvalue()
        assert "DEDUP_SKIP" in log and "record_exists" in log, f"Second ingest should log DEDUP_SKIP record_exists, got: {log!r}"


def test_e2e_concurrent_ingest_same_canonical_url_one_claim_one_artifact_set():
    """
    Two ingestion attempts with same canonical_url at the same time.
    Assert only one claim succeeds and only one set of artifacts is produced.
    """
    from ingest_dedup import (
        canonicalize_url,
        doc_id_from_canonical_url,
        doc_lookup_by_url,
        slugify_title,
    )

    try:
        from db_filter_autorun import process_pairs
    except ImportError:
        raise ImportError("db_filter_autorun required")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        export_dir = tmp / "export"
        export_dir.mkdir(parents=True, exist_ok=True)
        suggested = _make_suggested_name()
        src = tmp / f"{suggested}.pdf"
        src.write_bytes(b"%PDF-1.4 concurrent test\n" * 80)
        dst = export_dir / f"{suggested}.pdf"
        target_day = dt.date(2026, 1, 8)
        pairs = [(src, dst)]

        results = [None, None]
        logs = [io.StringIO(), io.StringIO()]

        def run_worker(worker_id: int) -> None:
            out = logs[worker_id]
            old = sys.stdout
            sys.stdout = out
            try:
                results[worker_id] = process_pairs(export_dir, pairs, target_day)
            finally:
                sys.stdout = old

        t1 = threading.Thread(target=run_worker, args=(0,))
        t2 = threading.Thread(target=run_worker, args=(1,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        log0 = logs[0].getvalue()
        log1 = logs[1].getvalue()
        dedup_skip_count = (1 if "DEDUP_SKIP" in log0 and "claim_failed" in log0 else 0) + (
            1 if "DEDUP_SKIP" in log1 and "claim_failed" in log1 else 0
        )
        assert dedup_skip_count >= 1, "At least one worker should see DEDUP_SKIP reason=claim_failed"

        pdfs = list(export_dir.glob("*.pdf"))
        assert len(pdfs) == 1, f"Only one PDF should exist, got {len(pdfs)}"
        assert not any("(1)" in p.name for p in export_dir.glob("*"))

        canonical_url = canonicalize_url(str(src))
        row = doc_lookup_by_url(export_dir, canonical_url)
        assert row is not None
        assert doc_id_from_canonical_url(canonical_url) == row.get("doc_id")


if __name__ == "__main__":
    test_e2e_ingest_same_document_twice()
    print("[OK] test_e2e_ingest_same_document_twice")
    test_e2e_second_ingest_logs_dedup_skip_when_complete()
    print("[OK] test_e2e_second_ingest_logs_dedup_skip_when_complete")
    test_e2e_concurrent_ingest_same_canonical_url_one_claim_one_artifact_set()
    print("[OK] test_e2e_concurrent_ingest_same_canonical_url_one_claim_one_artifact_set")
    print("All E2E ingest tests passed.")
