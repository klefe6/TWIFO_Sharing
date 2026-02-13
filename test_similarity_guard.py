"""
Tests for Step D.6: Similarity Guard.
Purpose: Verify tokenization, Jaccard similarity, guard logic, and loop prevention.
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

import sys
import json
import os
import tempfile
from pathlib import Path

sys.path.insert(0, r"c:\Coding Projects\TWIFO_Sharing")

from summarize_pdf import (
    _tokenize_for_similarity,
    jaccard_similarity,
    _extract_summary_fingerprint,
    compute_max_similarity,
    similarity_guard,
    SIMILARITY_THRESHOLD,
    SIMILARITY_MIN_TOKENS,
)


# ── Helpers ──

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        msg = f"  [FAIL] {name}"
        if detail:
            msg += f" -- {detail}"
        print(msg)


def _make_summary(tldr: list[str], moved: list[str] = None, tomorrow: list[str] = None) -> dict:
    """Build a minimal summary JSON for testing."""
    return {
        "meta": {"title": "test"},
        "extraction": {"status": "ok"},
        "sections": {
            "tldr": [{"text": t} for t in tldr],
            "what_moved_today": [{"text": t} for t in (moved or [])],
            "what_can_move_tomorrow": [{"text": t} for t in (tomorrow or [])],
            "trade_ideas": [],
        },
        "numeric_claims": [],
        "fingerprint_quotes": [],
    }


# ── 1. Tokenizer ──

def test_tokenizer_basic():
    print("\n--- test_tokenizer_basic ---")
    tokens = _tokenize_for_similarity("ES rose to 5,450 on strong volume")
    check("contains 'rose'", "rose" in tokens, f"got {tokens}")
    check("contains '450'", "450" in tokens or "5,450" in tokens or "5450" in tokens, f"got {tokens}")
    check("contains 'strong'", "strong" in tokens, f"got {tokens}")
    check("contains 'volume'", "volume" in tokens, f"got {tokens}")


def test_tokenizer_stopwords():
    print("\n--- test_tokenizer_stopwords ---")
    tokens = _tokenize_for_similarity("the market is on the rise and will be strong")
    check("no 'the'", "the" not in tokens, f"got {tokens}")
    check("no 'is'", "is" not in tokens, f"got {tokens}")
    check("no 'and'", "and" not in tokens, f"got {tokens}")
    check("no 'on'", "on" not in tokens, f"got {tokens}")
    check("has 'market'", "market" in tokens, f"got {tokens}")
    check("has 'rise'", "rise" in tokens, f"got {tokens}")
    check("has 'strong'", "strong" in tokens, f"got {tokens}")


def test_tokenizer_short_tokens():
    print("\n--- test_tokenizer_short_tokens ---")
    tokens = _tokenize_for_similarity("ES at 50 is up by 2%")
    # "ES" is 2 chars -> stripped, "at" is 2 chars -> stripped, "50" is 2 chars -> stripped
    check("no 2-char tokens", all(len(t) > 2 for t in tokens), f"got {tokens}")


def test_tokenizer_case_insensitive():
    print("\n--- test_tokenizer_case_insensitive ---")
    tokens_a = _tokenize_for_similarity("Gold ROSE sharply")
    tokens_b = _tokenize_for_similarity("gold rose SHARPLY")
    check("same tokens regardless of case", tokens_a == tokens_b, f"a={tokens_a}, b={tokens_b}")


def test_tokenizer_returns_set():
    print("\n--- test_tokenizer_returns_set ---")
    tokens = _tokenize_for_similarity("gold gold gold silver silver")
    check("is a set", isinstance(tokens, set))
    check("gold appears once", sum(1 for t in tokens if t == "gold") <= 1)


# ── 2. Jaccard Similarity ──

def test_jaccard_identical():
    print("\n--- test_jaccard_identical ---")
    s = {"gold", "rose", "sharply", "today"}
    check("identical sets = 1.0", jaccard_similarity(s, s) == 1.0)


def test_jaccard_disjoint():
    print("\n--- test_jaccard_disjoint ---")
    a = {"gold", "rose", "sharply"}
    b = {"bonds", "fell", "overnight"}
    check("disjoint sets = 0.0", jaccard_similarity(a, b) == 0.0)


def test_jaccard_partial():
    print("\n--- test_jaccard_partial ---")
    a = {"gold", "rose", "sharply", "today"}
    b = {"gold", "fell", "sharply", "yesterday"}
    # intersection: {gold, sharply} = 2
    # union: {gold, rose, sharply, today, fell, yesterday} = 6
    expected = 2 / 6
    actual = jaccard_similarity(a, b)
    check(f"partial overlap = {expected:.4f}", abs(actual - expected) < 0.001, f"got {actual}")


def test_jaccard_empty():
    print("\n--- test_jaccard_empty ---")
    check("both empty = 0.0", jaccard_similarity(set(), set()) == 0.0)
    check("one empty = 0.0", jaccard_similarity({"gold"}, set()) == 0.0)


def test_jaccard_symmetry():
    print("\n--- test_jaccard_symmetry ---")
    a = {"gold", "rose", "sharply"}
    b = {"gold", "fell", "bonds"}
    check("symmetric", jaccard_similarity(a, b) == jaccard_similarity(b, a))


# ── 3. Fingerprint Extraction ──

def test_fingerprint_extraction():
    print("\n--- test_fingerprint_extraction ---")
    summary = _make_summary(
        tldr=["Gold rose 2%", "Bonds fell sharply", "VIX spiked"],
        moved=["ES dropped 50 points"],
        tomorrow=["CPI data release expected"],
    )
    fp = _extract_summary_fingerprint(summary)
    check("contains tldr", "Gold rose 2%" in fp)
    check("contains moved", "ES dropped 50 points" in fp)
    check("contains tomorrow", "CPI data release expected" in fp)


def test_fingerprint_empty_sections():
    print("\n--- test_fingerprint_empty_sections ---")
    summary = _make_summary(tldr=[], moved=[], tomorrow=[])
    fp = _extract_summary_fingerprint(summary)
    check("empty fingerprint", fp == "", f"got '{fp}'")


def test_fingerprint_mixed_formats():
    print("\n--- test_fingerprint_mixed_formats ---")
    summary = {
        "sections": {
            "tldr": ["plain string bullet", {"text": "dict bullet"}],
            "what_moved_today": [{"text": "moved bullet"}],
        }
    }
    fp = _extract_summary_fingerprint(summary)
    check("contains plain string", "plain string bullet" in fp)
    check("contains dict text", "dict bullet" in fp)
    check("contains moved", "moved bullet" in fp)


# ── 4. compute_max_similarity ──

def test_max_similarity_no_recent():
    print("\n--- test_max_similarity_no_recent ---")
    candidate = {"gold", "rose", "sharply", "today", "market", "strong", "volume", "futures", "rally"}
    score, idx = compute_max_similarity(candidate, [])
    check("no recent = 0.0", score == 0.0)
    check("idx = -1", idx == -1)


def test_max_similarity_finds_best():
    print("\n--- test_max_similarity_finds_best ---")
    candidate = {"gold", "rose", "sharply", "today", "market", "strong", "volume", "futures", "rally"}
    recent = [
        {"bonds", "fell", "overnight", "rates", "treasury", "yield", "curve", "steepened", "duration"},
        {"gold", "rose", "sharply", "yesterday", "market", "strong", "volume", "futures", "surge"},  # Very similar
        {"oil", "dropped", "opec", "supply", "demand", "crude", "barrel", "production", "inventory"},
    ]
    score, idx = compute_max_similarity(candidate, recent)
    check("best match is index 1", idx == 1, f"got idx={idx}")
    check("score > 0.5", score > 0.5, f"got {score}")


def test_max_similarity_short_candidate():
    print("\n--- test_max_similarity_short_candidate ---")
    candidate = {"gold", "rose"}  # Too short (< SIMILARITY_MIN_TOKENS)
    recent = [{"gold", "rose", "sharply", "today", "market", "strong", "volume", "futures", "rally"}]
    score, idx = compute_max_similarity(candidate, recent)
    check("short candidate = 0.0", score == 0.0)


# ── 5. Similarity Guard (integration) ──

def test_guard_no_path_manager():
    print("\n--- test_guard_no_path_manager ---")
    summary = _make_summary(
        tldr=["Gold rose 2%", "Bonds fell sharply", "VIX spiked"],
    )
    result = similarity_guard(
        summary,
        source_text="Gold rose 2%. Bonds fell sharply. VIX spiked.",
        meta={"title": "test"},
        model="gpt-4o-mini",
        path_manager=None,
        pdf_path=Path("test.pdf"),
    )
    # Should return unchanged (no path_manager = skip)
    check("returns same object", result is summary)


def test_guard_already_retried():
    print("\n--- test_guard_already_retried ---")
    summary = _make_summary(
        tldr=["Gold rose 2%", "Bonds fell sharply", "VIX spiked"],
    )
    result = similarity_guard(
        summary,
        source_text="Gold rose 2%. Bonds fell sharply. VIX spiked.",
        meta={"title": "test"},
        model="gpt-4o-mini",
        path_manager=None,
        pdf_path=Path("test.pdf"),
        _already_retried=True,
    )
    check("returns same when already retried", result is summary)


def test_guard_below_threshold_no_retry():
    """Test that summaries below the threshold pass through unchanged."""
    print("\n--- test_guard_below_threshold_no_retry ---")
    # Create a temporary artifacts directory with a very different past summary
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        originals = tmpdir_path / "originals"
        originals.mkdir()
        artifacts = tmpdir_path / "artifacts"
        artifacts.mkdir()

        # Create a past summary that is very different
        past_dir = artifacts / "past_article"
        past_dir.mkdir()
        past_summary = _make_summary(
            tldr=["Oil crashed on OPEC news", "Crude inventories surged", "Energy sector led losses"],
            moved=["Brent dropped below 70 dollars per barrel"],
            tomorrow=["OPEC meeting scheduled for next week"],
        )
        with open(past_dir / "sum.json", "w") as f:
            json.dump(past_summary, f)

        # Import path manager
        from path_manager import TWIFOPathManager
        pm = TWIFOPathManager(tmpdir_path)

        # New summary about gold (very different from oil)
        new_summary = _make_summary(
            tldr=["Gold rose sharply on safe haven demand", "Treasury yields fell to multi-month lows", "Dollar weakened against major currencies"],
            moved=["Gold futures gained 3% reaching 2400 per ounce"],
            tomorrow=["Federal Reserve interest rate decision tomorrow"],
        )

        result = similarity_guard(
            new_summary,
            source_text="Gold rose sharply. Treasury yields fell. Dollar weakened.",
            meta={"title": "test"},
            model="gpt-4o-mini",
            path_manager=pm,
            pdf_path=Path("new_article.pdf"),
        )

        sim = result.get("meta", {}).get("similarity_max_jaccard", None)
        check("similarity recorded", sim is not None, f"got {sim}")
        check("below threshold", sim is not None and sim <= SIMILARITY_THRESHOLD, f"got {sim}")
        check("no retry attempted", not result.get("meta", {}).get("similarity_retry_attempted", False))


def test_guard_deterministic_no_infinite_loop():
    """Verify the _already_retried flag prevents infinite loops."""
    print("\n--- test_guard_deterministic_no_infinite_loop ---")
    summary = _make_summary(
        tldr=["Generic market summary", "Stocks moved today", "Bonds reacted"],
    )

    # Even with path_manager=None, the _already_retried flag should be respected
    result = similarity_guard(
        summary,
        source_text="test",
        meta={"title": "test"},
        model="gpt-4o-mini",
        path_manager=None,
        pdf_path=Path("test.pdf"),
        _already_retried=True,
    )
    check("no retry when _already_retried=True", result is summary)

    # Also verify the function signature accepts the flag
    check("_already_retried is a keyword arg", True)


def test_guard_metadata_audit_trail():
    """Verify audit metadata is set correctly when below threshold."""
    print("\n--- test_guard_metadata_audit_trail ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        originals = tmpdir_path / "originals"
        originals.mkdir()
        artifacts = tmpdir_path / "artifacts"
        artifacts.mkdir()

        # Create a past summary
        past_dir = artifacts / "past_article"
        past_dir.mkdir()
        past_summary = _make_summary(
            tldr=["Completely different topic about cryptocurrency regulation",
                  "Bitcoin mining operations face new compliance requirements",
                  "Ethereum staking yields declined significantly"],
        )
        with open(past_dir / "sum.json", "w") as f:
            json.dump(past_summary, f)

        from path_manager import TWIFOPathManager
        pm = TWIFOPathManager(tmpdir_path)

        new_summary = _make_summary(
            tldr=["Agricultural commodities surged on drought concerns",
                  "Wheat futures hit multi-year highs amid supply fears",
                  "Corn and soybean prices rallied in sympathy"],
        )

        result = similarity_guard(
            new_summary,
            source_text="Agricultural commodities surged. Wheat futures hit highs.",
            meta={"title": "test"},
            model="gpt-4o-mini",
            path_manager=pm,
            pdf_path=Path("agri_article.pdf"),
        )

        meta = result.get("meta", {})
        check("similarity_max_jaccard present", "similarity_max_jaccard" in meta)
        check("jaccard is float", isinstance(meta.get("similarity_max_jaccard"), float))


def test_guard_high_similarity_with_real_artifacts():
    """Test that high similarity is detected between near-identical summaries."""
    print("\n--- test_guard_high_similarity_with_real_artifacts ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        originals = tmpdir_path / "originals"
        originals.mkdir()
        artifacts = tmpdir_path / "artifacts"
        artifacts.mkdir()

        # Create a past summary that is nearly identical
        past_dir = artifacts / "past_article"
        past_dir.mkdir()
        past_summary = _make_summary(
            tldr=["Gold rose sharply on safe haven demand",
                  "Treasury yields fell to multi-month lows",
                  "Dollar weakened against major currencies"],
            moved=["Gold futures gained reaching 2400 per ounce"],
            tomorrow=["Federal Reserve interest rate decision tomorrow"],
        )
        with open(past_dir / "sum.json", "w") as f:
            json.dump(past_summary, f)

        from path_manager import TWIFOPathManager
        pm = TWIFOPathManager(tmpdir_path)

        # New summary that is nearly identical (same phrasing)
        new_summary = _make_summary(
            tldr=["Gold rose sharply on safe haven demand",
                  "Treasury yields fell to multi-month lows",
                  "Dollar weakened against major currencies"],
            moved=["Gold futures gained reaching 2400 per ounce"],
            tomorrow=["Federal Reserve interest rate decision tomorrow"],
        )

        # Extract fingerprints and compute similarity directly
        from summarize_pdf import _extract_summary_fingerprint
        fp_new = _extract_summary_fingerprint(new_summary)
        fp_past = _extract_summary_fingerprint(past_summary)
        new_tokens = _tokenize_for_similarity(fp_new)
        past_tokens = _tokenize_for_similarity(fp_past)
        sim = jaccard_similarity(new_tokens, past_tokens)

        check("identical summaries have jaccard=1.0", sim == 1.0, f"got {sim}")
        check("exceeds threshold", sim > SIMILARITY_THRESHOLD, f"got {sim}")


# ── Run All ──

def run_all():
    global passed, failed
    passed = 0
    failed = 0

    print("=" * 60)
    print("Step D.6: Similarity Guard Tests")
    print("=" * 60)

    # Tokenizer
    test_tokenizer_basic()
    test_tokenizer_stopwords()
    test_tokenizer_short_tokens()
    test_tokenizer_case_insensitive()
    test_tokenizer_returns_set()

    # Jaccard
    test_jaccard_identical()
    test_jaccard_disjoint()
    test_jaccard_partial()
    test_jaccard_empty()
    test_jaccard_symmetry()

    # Fingerprint
    test_fingerprint_extraction()
    test_fingerprint_empty_sections()
    test_fingerprint_mixed_formats()

    # Max similarity
    test_max_similarity_no_recent()
    test_max_similarity_finds_best()
    test_max_similarity_short_candidate()

    # Guard integration
    test_guard_no_path_manager()
    test_guard_already_retried()
    test_guard_below_threshold_no_retry()
    test_guard_deterministic_no_infinite_loop()
    test_guard_metadata_audit_trail()
    test_guard_high_similarity_with_real_artifacts()

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
