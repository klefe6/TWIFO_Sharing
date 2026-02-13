"""
Integration test: same ingest twice -> one PDF, no duplicate summaries.
Verifies doc_key dedupe, atomic write, claim, manifest, validation.
Author: Kevin Lefebvre
Last Updated: 2026-02-05
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tempfile
import hashlib


def test_canonicalize_url_and_doc_id():
    """canonicalize_url strips tracking params; doc_id is short and stable from URL only."""
    from ingest_dedup import canonicalize_url, doc_id_from_canonical_url

    c1 = canonicalize_url("  https://Example.COM/doc.pdf?utm_source=x&utm_medium=y  ")
    c2 = canonicalize_url("https://example.com/doc.pdf")
    assert c1 == c2 or "utm" not in c1, "Tracking params stripped and host lowercased"
    doc_id1 = doc_id_from_canonical_url(c1)
    doc_id2 = doc_id_from_canonical_url(c2)
    assert doc_id1 == doc_id2, "Same canonical URL -> same doc_id"
    assert 8 <= len(doc_id1) <= 12, "doc_id is short (8-12 chars)"


def test_slugify_title():
    """slugify_title produces safe filename slug."""
    from ingest_dedup import slugify_title

    assert slugify_title("Gold and Silver Bounce") == "gold_and_silver_bounce"
    assert slugify_title("  U.S. Economy  ") == "us_economy"
    assert slugify_title("") == ""


def test_deterministic_base_and_dedupe():
    """Same canonical URL -> same base -> second preflight skips; no (1)."""
    from ingest_dedup import (
        canonicalize_url,
        doc_id_from_canonical_url,
        slugify_title,
        deterministic_base_filename,
        preflight_check,
        doc_insert_pending,
        record_success,
        atomic_write_pdf_from_path,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dest = tmp / "export"
        dest.mkdir(parents=True, exist_ok=True)
        src_pdf = tmp / "source.pdf"
        src_pdf.write_bytes(b"%PDF-1.4 fake content for test\n")

        canonical = canonicalize_url("https://example.com/doc.pdf")
        doc_id = doc_id_from_canonical_url(canonical)
        title_slug = slugify_title("BOA Weekly 20260108")
        base = deterministic_base_filename("20260108", "BOA", title_slug, doc_id)

        skip1, _ = preflight_check(dest, doc_id, canonical, base)
        assert skip1 is False

        ok1, final1, existed1 = atomic_write_pdf_from_path(dest, base, src_pdf)
        assert ok1 and final1 and not existed1
        assert (dest / f"{base}.pdf").exists()
        inserted = doc_insert_pending(dest, doc_id, canonical, "BOA", "BOA Weekly 20260108", "20260108", title_slug)
        assert inserted
        record_success(dest, doc_id, canonical, title_slug, final1)

        skip2, reason2 = preflight_check(dest, doc_id, canonical, base)
        assert skip2 is True
        assert reason2 in ("record_exists", "final_exists")

        ok2, final2, existed2 = atomic_write_pdf_from_path(dest, base, src_pdf)
        assert ok2 and existed2

        pdfs = list(dest.glob("*.pdf"))
        assert len(pdfs) == 1
        assert pdfs[0].name == f"{base}.pdf"
        assert not any("(1)" in p.name for p in pdfs)


def test_same_ingest_twice_one_pdf_no_duplicate_summaries():
    """Run same ingest twice; assert only one PDF (deterministic base), no (1)."""
    from ingest_dedup import (
        canonicalize_url,
        doc_id_from_canonical_url,
        slugify_title,
        deterministic_base_filename,
        preflight_check,
        doc_insert_pending,
        record_success,
        atomic_write_pdf_from_path,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dest = tmp / "export"
        dest.mkdir(parents=True, exist_ok=True)
        src = tmp / "source.pdf"
        src.write_bytes(b"%PDF-1.4 minimal\n" * 50)
        canonical = canonicalize_url(str(src))
        doc_id = doc_id_from_canonical_url(canonical)
        base = deterministic_base_filename("20260108", "BOA", slugify_title("Weekly"), doc_id)

        skip_a, _ = preflight_check(dest, doc_id, canonical, base)
        assert not skip_a
        ok_a, final_a, existed_a = atomic_write_pdf_from_path(dest, base, src)
        assert ok_a and final_a and not existed_a
        doc_insert_pending(dest, doc_id, canonical, "BOA", "Weekly", "20260108", "weekly")
        record_success(dest, doc_id, canonical, "weekly", final_a)

        skip_b, reason_b = preflight_check(dest, doc_id, canonical, base)
        assert skip_b, f"Second preflight must skip (reason={reason_b})"

        ok_b, final_b, existed_b = atomic_write_pdf_from_path(dest, base, src)
        assert ok_b and existed_b

        all_in_dest = list(dest.glob("*.pdf"))
        assert len(all_in_dest) == 1 and all_in_dest[0].name == f"{base}.pdf"
        assert not any("(1)" in p.name for p in all_in_dest)


def test_claim_acquire_only_one_owner():
    """Two simulated workers (A and B): only one can claim same doc_id; after release the other can."""
    from ingest_dedup import (
        doc_id_from_canonical_url,
        canonicalize_url,
        claim_acquire,
        claim_release,
    )

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "export"
        dest.mkdir(parents=True, exist_ok=True)
        canonical = canonicalize_url("https://example.com/doc.pdf")
        doc_id = doc_id_from_canonical_url(canonical)

        acquired_a, lock_a = claim_acquire(dest, doc_id, worker_id="A")
        assert acquired_a is True, "Worker A must get claim"
        acquired_b, _ = claim_acquire(dest, doc_id, worker_id="B")
        assert acquired_b is False, "Worker B must not get claim while A holds it"
        claim_release(dest, doc_id, lock_a)
        acquired_b2, lock_b = claim_acquire(dest, doc_id, worker_id="B")
        assert acquired_b2 is True, "After A releases, worker B can claim"
        claim_release(dest, doc_id, lock_b)


def test_validate_artifacts_requires_all():
    """validate_artifacts returns (False, missing) when required files are absent."""
    from ingest_dedup import validate_artifacts, REQUIRED_ARTIFACTS

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "export"
        dest.mkdir(parents=True, exist_ok=True)
        base = "20260108__BOA__weekly__abc1234567"
        (dest / f"{base}.pdf").write_bytes(b"%PDF-1.4\n")
        ok, missing = validate_artifacts(dest, base, required=REQUIRED_ARTIFACTS)
        assert ok is False
        assert "summary_json" in missing and "summary_pdf" in missing


def test_manifest_written_after_validation():
    """write_manifest produces {base}.manifest.json with path (relative), size, mtime per artifact; optional doc_meta."""
    from ingest_dedup import collect_artifact_info, write_manifest

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "export"
        dest.mkdir(parents=True, exist_ok=True)
        base = "20260108__BOA__weekly__def9876543"
        (dest / f"{base}.pdf").write_bytes(b"%PDF-1.4\n")
        (dest / f"{base}__sum.json").write_text("{}")
        (dest / f"{base}__sum.pdf").write_bytes(b"%PDF summary\n")
        manifest_path = write_manifest(dest, base, doc_meta={"doc_id": "def9876543", "canonical_url": "https://x.com/w.pdf", "source": "BOA", "title": "Weekly", "pub_date": "20260108"})
        assert manifest_path == dest / f"{base}.manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["base"] == base
        assert data["doc_id"] == "def9876543" and data["canonical_url"] == "https://x.com/w.pdf"
        assert "artifacts" in data
        assert "pdf" in data["artifacts"] and "summary_json" in data["artifacts"]
        for v in data["artifacts"].values():
            assert "path" in v and "size" in v and "mtime" in v
            assert "sha256" not in v


def test_validate_and_publish_fails_when_missing():
    """validate_and_publish does not record_success when required artifacts missing."""
    from ingest_dedup import validate_and_publish, get_suggested_name, doc_id_from_canonical_url

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "export"
        dest.mkdir(parents=True, exist_ok=True)
        doc_id = doc_id_from_canonical_url("https://x.com/c.pdf")
        base = "20260108__O__suggested__xyz1111111"
        (dest / f"{base}.pdf").write_bytes(b"%PDF-1.4\n")
        published = validate_and_publish(
            dest, doc_id, "https://x.com/c.pdf", "suggested", base, dest / f"{base}.pdf", None
        )
        assert published is False
        assert get_suggested_name(dest, doc_id) is None


def test_ensure_original_pdf_in_export_temp_to_export():
    """Source PDF in temp folder -> ensure_original_pdf_in_export -> final PDF exists in EXPORT_DIR, no (1)."""
    from ingest_dedup import ensure_original_pdf_in_export, _file_sha256

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        source_dir = tmp / "temp_source"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_pdf = source_dir / "report.pdf"
        pdf_bytes = b"%PDF-1.4 minimal content for export test\n" * 50
        source_pdf.write_bytes(pdf_bytes)
        source_sha = hashlib.sha256(pdf_bytes).hexdigest()

        export_dir = tmp / "export"
        export_dir.mkdir(parents=True, exist_ok=True)
        base_name = "20260205__BOA__report__abcdef1234"

        final_path, already_existed = ensure_original_pdf_in_export(export_dir, base_name, source_pdf)
        assert final_path is not None
        assert already_existed is False
        final_pdf = export_dir / f"{base_name}.pdf"
        assert final_pdf.exists()
        assert final_pdf == final_path
        assert final_pdf.stat().st_size > 0
        assert _file_sha256(final_pdf) == source_sha

        # Second call: already present, reuse; no (1) variant
        final_path2, already_existed2 = ensure_original_pdf_in_export(export_dir, base_name, source_pdf)
        assert final_path2 == final_pdf
        assert already_existed2 is True
        pdfs = list(export_dir.glob("*.pdf"))
        assert len(pdfs) == 1 and pdfs[0].name == f"{base_name}.pdf"
        assert not any("(1)" in p.name for p in pdfs)


def test_ensure_original_pdf_in_bundle_and_publish_from_temp():
    """PDF in temp dir; after validate_and_publish, {dest_dir}/{base}.pdf exists and matches source sha256."""
    from ingest_dedup import (
        doc_id_from_canonical_url,
        ensure_original_pdf_in_bundle,
        validate_and_publish,
        _file_sha256,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        source_dir = tmp / "temp_source"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_pdf = source_dir / "report.pdf"
        pdf_bytes = b"%PDF-1.4 minimal content for sha256 test\n" * 100
        source_pdf.write_bytes(pdf_bytes)
        source_sha = hashlib.sha256(pdf_bytes).hexdigest()

        dest = tmp / "export"
        dest.mkdir(parents=True, exist_ok=True)
        doc_id = doc_id_from_canonical_url("https://example.com/report.pdf")
        base = "20260205__BOA__report__abcdef1234"
        (dest / f"{base}__sum.json").write_text("{}")
        (dest / f"{base}__sum.pdf").write_bytes(b"%PDF summary\n")

        published = validate_and_publish(
            dest, doc_id, "https://example.com/report.pdf", "report", base, source_pdf, None
        )
        assert published is True
        bundle_pdf = dest / f"{base}.pdf"
        assert bundle_pdf.exists()
        bundle_sha = _file_sha256(bundle_pdf)
        assert bundle_sha == source_sha

        manifest_path = dest / f"{base}.manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "artifacts" in data and "pdf" in data["artifacts"]
        assert data["artifacts"]["pdf"]["size"] == len(pdf_bytes)
        assert "mtime" in data["artifacts"]["pdf"] and "path" in data["artifacts"]["pdf"]
        assert "sha256" not in data["artifacts"]["pdf"]


def test_doc_lookup_by_url():
    """doc_lookup_by_url returns row dict by canonical_url or None."""
    from ingest_dedup import (
        doc_lookup_by_url,
        doc_insert_pending,
        doc_id_from_canonical_url,
        doc_mark_status,
        STATUS_DONE,
    )

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "export"
        dest.mkdir(parents=True, exist_ok=True)
        url = "https://example.com/doc.pdf"
        doc_id = doc_id_from_canonical_url(url)
        assert doc_lookup_by_url(dest, url) is None
        doc_insert_pending(dest, doc_id, url, "BOA", "Title", "20260108", "title")
        row = doc_lookup_by_url(dest, url)
        assert row is not None
        assert row["doc_id"] == doc_id
        assert row["canonical_url"] == url
        assert row["status"] == "pending"
        doc_mark_status(dest, doc_id, STATUS_DONE, pdf_path="/path/to.pdf")
        row2 = doc_lookup_by_url(dest, url)
        assert row2["status"] == STATUS_DONE
        assert row2["pdf_path"] == "/path/to.pdf"


def test_doc_insert_pending_unique_canonical_url():
    """First insert succeeds; second insert with same canonical_url returns False (unique constraint)."""
    from ingest_dedup import doc_insert_pending, doc_id_from_canonical_url

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "export"
        dest.mkdir(parents=True, exist_ok=True)
        url = "https://example.com/unique.pdf"
        doc_id = doc_id_from_canonical_url(url)
        ok1 = doc_insert_pending(dest, doc_id, url, "BOA", "Title", "20260108", "title")
        assert ok1 is True
        ok2 = doc_insert_pending(dest, doc_id, url, "BOA", "Title", "20260108", "title")
        assert ok2 is False  # ON CONFLICT DO NOTHING
        # Same URL different doc_id would violate canonical_url UNIQUE
        other_id = "x" * 10
        ok3 = doc_insert_pending(dest, other_id, url, "O", "Other", "20260108", "other")
        assert ok3 is False  # canonical_url already exists


def test_preflight_skips_when_status_done():
    """Preflight returns skip when registry has canonical_url with status=done."""
    from ingest_dedup import (
        canonicalize_url,
        doc_id_from_canonical_url,
        slugify_title,
        deterministic_base_filename,
        doc_insert_pending,
        doc_mark_status,
        preflight_check,
        record_success,
        STATUS_DONE,
    )

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "export"
        dest.mkdir(parents=True, exist_ok=True)
        url = "https://example.com/done.pdf"
        canonical = canonicalize_url(url)
        doc_id = doc_id_from_canonical_url(canonical)
        title_slug = slugify_title("Done Doc")
        base = deterministic_base_filename("20260108", "BOA", title_slug, doc_id)
        doc_insert_pending(dest, doc_id, canonical, "BOA", "Done Doc", "20260108", title_slug)
        doc_mark_status(dest, doc_id, STATUS_DONE, pdf_path=str(dest / f"{base}.pdf"))
        skip, reason = preflight_check(dest, doc_id, canonical, base)
        assert skip is True
        assert reason == "record_exists"


def test_preflight_no_skip_when_pending():
    """Preflight does not skip when registry has status=pending (resume allowed)."""
    from ingest_dedup import (
        canonicalize_url,
        doc_id_from_canonical_url,
        slugify_title,
        deterministic_base_filename,
        doc_insert_pending,
        preflight_check,
    )

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "export"
        dest.mkdir(parents=True, exist_ok=True)
        url = "https://example.com/pending.pdf"
        canonical = canonicalize_url(url)
        doc_id = doc_id_from_canonical_url(canonical)
        title_slug = slugify_title("Pending Doc")
        base = deterministic_base_filename("20260108", "BOA", title_slug, doc_id)
        doc_insert_pending(dest, doc_id, canonical, "BOA", "Pending Doc", "20260108", title_slug)
        skip, reason = preflight_check(dest, doc_id, canonical, base)
        assert skip is False, "Must not skip when status is pending (resume)"


def test_bundle_state_and_complete():
    """bundle_state reports which artifacts exist; bundle_complete only True when all + manifest."""
    from ingest_dedup import bundle_state, bundle_complete, REQUIRED_ARTIFACTS

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "export"
        dest.mkdir(parents=True, exist_ok=True)
        base = "20260108__BOA__weekly__abc1234567"
        (dest / f"{base}.pdf").write_bytes(b"%PDF-1.4\n")
        state = bundle_state(dest, base)
        assert state.get("pdf") is True
        assert state.get("summary_json") is False
        assert state.get("summary_pdf") is False
        assert state.get("manifest") is False
        assert bundle_complete(dest, base, require_manifest=True) is False

        (dest / f"{base}__sum.json").write_text("{}")
        (dest / f"{base}__sum.pdf").write_bytes(b"%PDF\n")
        assert bundle_complete(dest, base, require_manifest=False) is True
        assert bundle_complete(dest, base, require_manifest=True) is False

        (dest / f"{base}.manifest.json").write_text("{}")
        assert bundle_complete(dest, base, require_manifest=True) is True


def test_pdf_exists_summaries_missing_resumes():
    """When PDF exists but summaries missing, bundle_complete is False so autorun resumes (does not skip)."""
    from ingest_dedup import (
        ensure_original_pdf_in_export,
        bundle_complete,
        bundle_state,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        source_pdf = tmp / "source.pdf"
        source_pdf.write_bytes(b"%PDF-1.4\n" * 10)
        export_dir = tmp / "export"
        export_dir.mkdir(parents=True, exist_ok=True)
        base = "20260108__BOA__resume__xyz9876543"
        final_path, _ = ensure_original_pdf_in_export(export_dir, base, source_pdf)
        assert final_path is not None
        state = bundle_state(export_dir, base)
        assert state["pdf"] is True
        assert state["summary_json"] is False
        assert state["summary_pdf"] is False
        assert bundle_complete(export_dir, base, require_manifest=True) is False
        assert bundle_complete(export_dir, base, require_manifest=False) is False


def test_all_artifacts_exist_skip():
    """When all required artifacts + manifest exist, bundle_complete is True (full skip)."""
    from ingest_dedup import bundle_complete, bundle_state

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "export"
        dest.mkdir(parents=True, exist_ok=True)
        base = "20260108__BOA__full__def1111111"
        (dest / f"{base}.pdf").write_bytes(b"%PDF-1.4\n")
        (dest / f"{base}__sum.json").write_text("{}")
        (dest / f"{base}__sum.pdf").write_bytes(b"%PDF\n")
        (dest / f"{base}.manifest.json").write_text('{"base":"' + base + '"}')
        assert bundle_complete(dest, base, require_manifest=True) is True
        state = bundle_state(dest, base)
        assert state["pdf"] and state["summary_json"] and state["summary_pdf"] and state["manifest"]


def test_concurrent_run_one_owner():
    """Two workers racing for same doc_id: only one acquires claim (concurrent run -> one owner)."""
    from ingest_dedup import (
        doc_id_from_canonical_url,
        canonicalize_url,
        claim_acquire,
        claim_release,
    )

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "export"
        dest.mkdir(parents=True, exist_ok=True)
        canonical = canonicalize_url("https://example.com/concurrent.pdf")
        doc_id = doc_id_from_canonical_url(canonical)
        acquired_a, lock_a = claim_acquire(dest, doc_id, worker_id="A")
        acquired_b, _ = claim_acquire(dest, doc_id, worker_id="B")
        assert acquired_a is True
        assert acquired_b is False
        claim_release(dest, doc_id, lock_a)
        acquired_b2, lock_b = claim_acquire(dest, doc_id, worker_id="B")
        assert acquired_b2 is True
        claim_release(dest, doc_id, lock_b)


if __name__ == "__main__":
    test_canonicalize_url_and_doc_id()
    test_slugify_title()
    test_deterministic_base_and_dedupe()
    test_same_ingest_twice_one_pdf_no_duplicate_summaries()
    test_claim_acquire_only_one_owner()
    test_validate_artifacts_requires_all()
    test_manifest_written_after_validation()
    test_validate_and_publish_fails_when_missing()
    test_ensure_original_pdf_in_export_temp_to_export()
    test_ensure_original_pdf_in_bundle_and_publish_from_temp()
    test_doc_lookup_by_url()
    test_doc_insert_pending_unique_canonical_url()
    test_preflight_skips_when_status_done()
    test_preflight_no_skip_when_pending()
    test_bundle_state_and_complete()
    test_pdf_exists_summaries_missing_resumes()
    test_all_artifacts_exist_skip()
    test_concurrent_run_one_owner()
    print("All ingest dedupe tests passed.")
