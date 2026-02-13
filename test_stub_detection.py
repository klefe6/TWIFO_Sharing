"""
Tests for is_stub() detection and false-success prevention.

Ensures "[OK] Summary created" can never be printed for a stub.

Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from summarize_pdf import is_stub, _failed_stub, _skipped_stub
from pathlib import Path


# ===========================================================================
# Test helpers
# ===========================================================================

def _make_real_summary() -> dict:
    """Build a minimal but valid non-stub summary."""
    return {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {"title": "Test", "provider": "TEST"},
        "extraction": {"status": "ok"},
        "sections": {
            "tldr": [{"text": "Market rallied", "sources": ["TEST"]}],
            "what_moved_today": [{"text": "ES up 1%", "sources": ["TEST"]}],
            "what_can_move_tomorrow": [{"text": "CPI tomorrow", "sources": ["TEST"]}],
            "trade_ideas": [],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": [],
        },
        "fingerprint_quotes": [],
        "numeric_claims": [],
    }


# ===========================================================================
# Tests
# ===========================================================================

def test_failed_stub_detected():
    """_failed_stub() output is detected as a stub."""
    stub = _failed_stub(
        Path("test.pdf"),
        reason="test failure",
        extraction={"status": "ok"},
        meta={"title": "Test"},
    )
    assert is_stub(stub), "Failed stub should be detected by is_stub()"
    assert stub.get("_is_stub") is True, "Failed stub must have _is_stub=True"
    print("  [PASS] _failed_stub detected as stub")


def test_skipped_stub_detected():
    """_skipped_stub() output is detected as a stub."""
    stub = _skipped_stub(
        Path("test.pdf"),
        reason="not market relevant",
        triage_result={"is_market_relevant": False, "priority_score_0_10": 1},
        extraction={"status": "ok"},
        meta={"title": "Test"},
    )
    assert is_stub(stub), "Skipped stub should be detected by is_stub()"
    assert stub.get("_is_stub") is True, "Skipped stub must have _is_stub=True"
    print("  [PASS] _skipped_stub detected as stub")


def test_real_summary_not_stub():
    """A real summary with populated sections is not a stub."""
    real = _make_real_summary()
    assert not is_stub(real), "Real summary should NOT be detected as stub"
    print("  [PASS] real summary is not a stub")


def test_empty_sections_is_stub():
    """Summary with all empty primary sections is a stub even without _is_stub flag."""
    empty = {
        "schema_version": "twifo.sum.v1",
        "extraction": {"status": "ok"},
        "sections": {
            "tldr": [],
            "what_moved_today": [],
            "what_can_move_tomorrow": [],
        },
    }
    assert is_stub(empty), "Empty-sections summary should be detected as stub"
    print("  [PASS] empty sections detected as stub")


def test_extraction_failed_is_stub():
    """extraction.status='failed' is a stub even without _is_stub flag."""
    result = {
        "schema_version": "twifo.sum.v1",
        "extraction": {"status": "failed"},
        "sections": {
            "tldr": [{"text": "something"}],
            "what_moved_today": [],
            "what_can_move_tomorrow": [],
        },
    }
    assert is_stub(result), "extraction.status=failed should be a stub"
    print("  [PASS] extraction.status=failed detected as stub")


def test_ok_status_with_sections_not_stub():
    """extraction.status='ok' + populated tldr is not a stub."""
    result = {
        "schema_version": "twifo.sum.v1",
        "extraction": {"status": "ok"},
        "sections": {
            "tldr": [{"text": "Market rallied"}],
            "what_moved_today": [],
            "what_can_move_tomorrow": [],
        },
    }
    assert not is_stub(result), "ok status + tldr should not be a stub"
    print("  [PASS] ok + populated tldr is not a stub")


def test_degraded_status_with_sections_not_stub():
    """extraction.status='degraded' + populated sections is not a stub."""
    result = {
        "schema_version": "twifo.sum.v1",
        "extraction": {"status": "degraded"},
        "sections": {
            "tldr": [{"text": "Market rallied"}],
            "what_moved_today": [{"text": "ES up"}],
            "what_can_move_tomorrow": [],
        },
    }
    assert not is_stub(result), "degraded + sections should not be a stub"
    print("  [PASS] degraded + sections is not a stub")


def test_false_success_impossible():
    """Prove that the OK message logic cannot fire for a stub.

    This simulates the db_filter_autorun.py logic:
      if not summary:         -> None case
      elif is_stub(summary):  -> stub case
      else:                   -> OK case

    A stub must NEVER reach the 'else' branch.
    """
    # Test every stub variant
    stubs = [
        _failed_stub(Path("t.pdf"), "LLM error", {"status": "ok"}, {"title": "T"}),
        _skipped_stub(Path("t.pdf"), "not relevant", {"is_market_relevant": False, "priority_score_0_10": 1}, {"status": "ok"}, {"title": "T"}),
        {"extraction": {"status": "failed"}, "sections": {"tldr": [], "what_moved_today": [], "what_can_move_tomorrow": []}},
        {"extraction": {"status": "ok"}, "sections": {"tldr": [], "what_moved_today": [], "what_can_move_tomorrow": []}},
    ]

    for i, stub in enumerate(stubs):
        # Simulate the caller logic
        ok_printed = False
        if not stub:
            pass  # None branch
        elif is_stub(stub):
            pass  # Stub branch (correct)
        else:
            ok_printed = True  # False success!

        assert not ok_printed, (
            f"Stub variant {i} reached the OK branch — false success! "
            f"_is_stub={stub.get('_is_stub')}, "
            f"extraction.status={stub.get('extraction', {}).get('status')}"
        )

    # Also verify a real summary DOES reach the OK branch
    real = _make_real_summary()
    ok_for_real = False
    if not real:
        pass
    elif is_stub(real):
        pass
    else:
        ok_for_real = True
    assert ok_for_real, "Real summary must reach the OK branch"

    print("  [PASS] false success impossible for all stub variants")


# ===========================================================================
# Runner
# ===========================================================================

def _run_all():
    tests = [
        ("failed_stub_detected", test_failed_stub_detected),
        ("skipped_stub_detected", test_skipped_stub_detected),
        ("real_summary_not_stub", test_real_summary_not_stub),
        ("empty_sections_is_stub", test_empty_sections_is_stub),
        ("extraction_failed_is_stub", test_extraction_failed_is_stub),
        ("ok_with_sections_not_stub", test_ok_status_with_sections_not_stub),
        ("degraded_with_sections_not_stub", test_degraded_status_with_sections_not_stub),
        ("false_success_impossible", test_false_success_impossible),
    ]

    print("=" * 60)
    print("Running stub detection tests")
    print("=" * 60)
    print()

    passed = 0
    failed = 0

    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed out of {passed + failed}")
    return failed == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
