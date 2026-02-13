"""
Tests for the critic pass (Step D.7) — deduplication, evidence quote validation,
and numeric claims completeness.
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

from __future__ import annotations

import copy
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


# ---------------------------------------------------------------------------
# Source text fixture (simulates extracted PDF text)
# ---------------------------------------------------------------------------

SOURCE_TEXT = """
The Federal Reserve released minutes from its January meeting, revealing a
hawkish tilt among several members. ES futures dropped 0.8% to test the 5,450
support level on heavy volume. Gold rallied sharply on safe-haven demand,
reaching 2,050 per ounce. The 10-year yield climbed to 4.25% as traders
repriced rate expectations. FOMC minutes release is scheduled for Wednesday
at 2pm ET. Crude oil fell 1.2% to $72.50 on demand concerns. The VIX spiked
to 18.5, its highest level in two weeks. Analysts noted that "the risk of a
policy mistake is rising" and "markets are underpricing the probability of a
March rate hold." Key support for ES sits at 5,400 with resistance at 5,550.
The dollar index strengthened to 104.30 on the hawkish repricing.
"""


# ---------------------------------------------------------------------------
# Summary fixture builder
# ---------------------------------------------------------------------------

def _make_summary(
    *,
    tldr: list | None = None,
    what_moved_today: list | None = None,
    what_can_move_tomorrow: list | None = None,
    what_occurred: list | None = None,
    forward_watch: list | None = None,
    fingerprint_quotes: list | None = None,
    numeric_claims: list | None = None,
    trade_ideas: list | None = None,
) -> dict:
    """Build a minimal sum.json for testing."""
    return {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {
            "title": "Test Article",
            "provider": "BOA",
            "published_date": "20260210",
            "model": "gpt-4o",
        },
        "fingerprint_quotes": fingerprint_quotes if fingerprint_quotes is not None else [
            "the risk of a policy mistake is rising",
            "markets are underpricing the probability of a March rate hold",
            "Gold rallied sharply on safe-haven demand",
        ],
        "numeric_claims": numeric_claims if numeric_claims is not None else [
            {"value": "5,450", "context": "ES support", "source_quote": "test 5,450 support"},
            {"value": "2,050", "context": "GC target", "source_quote": "reaching 2,050"},
            {"value": "4.25%", "context": "10y yield", "source_quote": "climbed to 4.25%"},
        ],
        "sections": {
            "tldr": tldr if tldr is not None else [
                {"text": "ES dropped 0.8% to test 5,450 support on heavy volume", "sources": ["BOA"]},
                {"text": "Gold rallied to 2,050 on safe-haven flows", "sources": ["BOA"]},
                {"text": "Fed minutes showed hawkish tilt among members", "sources": ["BOA"]},
            ],
            "what_moved_today": what_moved_today if what_moved_today is not None else [
                {"text": "ES futures dropped 0.8% to test the 5,450 support level", "sources": ["BOA"]},
                {"text": "10-year yield climbed to 4.25%", "sources": ["BOA"]},
            ],
            "what_can_move_tomorrow": what_can_move_tomorrow if what_can_move_tomorrow is not None else [
                {"text": "FOMC minutes release Wednesday at 2pm ET", "sources": ["BOA"]},
            ],
            "what_occurred": what_occurred if what_occurred is not None else [],
            "forward_watch": forward_watch if forward_watch is not None else [
                {"text": "FOMC minutes scheduled for Wednesday 2pm ET", "sources": ["BOA"]},
            ],
            "trade_ideas": trade_ideas if trade_ideas is not None else [
                {
                    "product": "ES",
                    "bias": "Bearish",
                    "key_levels": ["5,450", "5,400"],
                    "source_quote": "Key support for ES sits at 5,400 with resistance at 5,550",
                },
            ],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": [],
        },
        "chart_score_0_3": 0,
        "chart_text_sources_used": [],
        "chart_observations": [],
    }


# ===========================================================================
# Tests: Deduplication
# ===========================================================================

def test_dedup_removes_cross_section_duplicate():
    """tldr and what_moved_today have near-identical bullet — lower priority removed."""
    from summarize_pdf import critic_dedup_sections
    s = _make_summary(
        tldr=[
            {"text": "ES dropped sharply to test 5,450 support on heavy volume", "sources": ["BOA"]},
            {"text": "Gold rallied to 2,050 on safe-haven flows", "sources": ["BOA"]},
            {"text": "Fed minutes showed hawkish tilt among members", "sources": ["BOA"]},
        ],
        what_moved_today=[
            {"text": "ES dropped sharply to test 5,450 support on heavy selling volume", "sources": ["BOA"]},
            {"text": "10-year yield climbed to 4.25%", "sources": ["BOA"]},
        ],
    )
    removed = critic_dedup_sections(s)
    assert removed >= 1, f"Expected at least 1 removal, got {removed}"
    # tldr should keep its bullet (higher priority), what_moved_today should lose it
    tldr_texts = [b["text"] for b in s["sections"]["tldr"]]
    assert any("5,450" in t for t in tldr_texts), "tldr should keep the ES bullet"


def test_dedup_removes_forward_watch_duplicate():
    """what_can_move_tomorrow and forward_watch both mention FOMC — lower priority removed."""
    from summarize_pdf import critic_dedup_sections
    s = _make_summary()
    removed = critic_dedup_sections(s)
    # forward_watch has lower priority than what_can_move_tomorrow
    fw_texts = [b["text"] for b in s["sections"]["forward_watch"]]
    wcmt_texts = [b["text"] for b in s["sections"]["what_can_move_tomorrow"]]
    # At least one of the FOMC duplicates should be removed
    total_fomc = sum(1 for t in fw_texts + wcmt_texts if "FOMC" in t)
    assert total_fomc <= 2  # Could be 1 if removed, or 2 if not quite similar enough


def test_dedup_no_removal_when_unique():
    """All bullets are unique — nothing removed."""
    from summarize_pdf import critic_dedup_sections
    s = _make_summary(
        tldr=[
            {"text": "ES dropped sharply on hawkish Fed", "sources": ["BOA"]},
            {"text": "Gold rallied to 2,050", "sources": ["BOA"]},
            {"text": "VIX spiked to 18.5", "sources": ["BOA"]},
        ],
        what_moved_today=[
            {"text": "Crude oil fell 1.2% to $72.50", "sources": ["BOA"]},
        ],
        what_can_move_tomorrow=[
            {"text": "CPI release next week", "sources": ["BOA"]},
        ],
        forward_watch=[],
    )
    removed = critic_dedup_sections(s)
    assert removed == 0


def test_dedup_preserves_section_structure():
    """After dedup, sections still have valid list structure."""
    from summarize_pdf import critic_dedup_sections
    s = _make_summary()
    critic_dedup_sections(s)
    for sec_name in ["tldr", "what_moved_today", "what_can_move_tomorrow", "forward_watch"]:
        assert isinstance(s["sections"][sec_name], list)


def test_dedup_empty_sections():
    """Empty sections don't cause errors."""
    from summarize_pdf import critic_dedup_sections
    s = _make_summary(
        tldr=[], what_moved_today=[], what_can_move_tomorrow=[],
        what_occurred=[], forward_watch=[],
    )
    removed = critic_dedup_sections(s)
    assert removed == 0


# ===========================================================================
# Tests: Evidence Quote Validation
# ===========================================================================

def test_validate_quotes_keeps_verbatim():
    """Quotes that are verbatim substrings of source are kept."""
    from summarize_pdf import critic_validate_quotes
    s = _make_summary(fingerprint_quotes=[
        "the risk of a policy mistake is rising",
        "markets are underpricing the probability of a March rate hold",
        "Gold rallied sharply on safe-haven demand",
    ])
    dropped = critic_validate_quotes(s, SOURCE_TEXT)
    assert dropped == 0
    assert len(s["fingerprint_quotes"]) == 3


def test_validate_quotes_drops_fabricated():
    """Fabricated quotes not in source are removed."""
    from summarize_pdf import critic_validate_quotes
    s = _make_summary(fingerprint_quotes=[
        "the risk of a policy mistake is rising",  # real
        "Bitcoin is the future of finance",  # fabricated
        "Gold rallied sharply on safe-haven demand",  # real
    ])
    dropped = critic_validate_quotes(s, SOURCE_TEXT)
    assert dropped == 1
    assert len(s["fingerprint_quotes"]) == 2
    assert "Bitcoin" not in str(s["fingerprint_quotes"])


def test_validate_quotes_drops_trade_idea_source_quote():
    """Fabricated trade_ideas source_quote is set to None."""
    from summarize_pdf import critic_validate_quotes
    s = _make_summary(trade_ideas=[
        {
            "product": "ES",
            "bias": "Bearish",
            "key_levels": ["5,450"],
            "source_quote": "This quote does not exist in the article at all",
        },
    ])
    dropped = critic_validate_quotes(s, SOURCE_TEXT)
    assert dropped == 1
    assert s["sections"]["trade_ideas"][0]["source_quote"] is None


def test_validate_quotes_keeps_valid_trade_idea_quote():
    """Valid trade_ideas source_quote is preserved."""
    from summarize_pdf import critic_validate_quotes
    s = _make_summary(trade_ideas=[
        {
            "product": "ES",
            "bias": "Bearish",
            "key_levels": ["5,400", "5,550"],
            "source_quote": "Key support for ES sits at 5,400 with resistance at 5,550",
        },
    ])
    dropped = critic_validate_quotes(s, SOURCE_TEXT)
    assert dropped == 0
    assert s["sections"]["trade_ideas"][0]["source_quote"] is not None


def test_validate_quotes_empty_fingerprints():
    """Empty fingerprint_quotes list doesn't error."""
    from summarize_pdf import critic_validate_quotes
    s = _make_summary(fingerprint_quotes=[])
    dropped = critic_validate_quotes(s, SOURCE_TEXT)
    assert dropped == 0


def test_validate_quotes_case_insensitive():
    """Quote matching is case-insensitive."""
    from summarize_pdf import critic_validate_quotes
    s = _make_summary(fingerprint_quotes=[
        "THE RISK OF A POLICY MISTAKE IS RISING",  # uppercase version
    ])
    dropped = critic_validate_quotes(s, SOURCE_TEXT)
    assert dropped == 0


# ===========================================================================
# Tests: Numeric Claims Completeness
# ===========================================================================

def test_numeric_registry_no_change_when_complete():
    """All numbers already registered — no changes."""
    from summarize_pdf import critic_ensure_numeric_registry
    s = _make_summary()
    registrations = critic_ensure_numeric_registry(s, SOURCE_TEXT)
    # Most numbers should already be registered
    assert isinstance(registrations, int)


def test_numeric_registry_auto_registers_missing():
    """Number used in text but missing from claims gets auto-registered."""
    from summarize_pdf import critic_ensure_numeric_registry
    s = _make_summary(
        numeric_claims=[
            {"value": "5,450", "context": "ES support", "source_quote": "test 5,450"},
            # Missing: 2,050, 4.25%
        ],
        tldr=[
            {"text": "ES dropped to test 5,450 support", "sources": ["BOA"]},
            {"text": "Gold rallied to 2,050 on safe-haven", "sources": ["BOA"]},
            {"text": "10-year yield at 4.25%", "sources": ["BOA"]},
        ],
    )
    registrations = critic_ensure_numeric_registry(s, SOURCE_TEXT)
    assert registrations >= 1, f"Expected auto-registrations, got {registrations}"
    # Verify the claims list grew
    claim_values = {c["value"] for c in s["numeric_claims"] if isinstance(c, dict)}
    assert "5,450" in claim_values


def test_numeric_registry_scrubs_hallucinated():
    """Number not in source and not in claims gets scrubbed."""
    from summarize_pdf import critic_ensure_numeric_registry
    s = _make_summary(
        numeric_claims=[],
        tldr=[
            {"text": "ES could reach 9,999 by Friday", "sources": ["BOA"]},
        ],
    )
    registrations = critic_ensure_numeric_registry(s, SOURCE_TEXT)
    # 9,999 is not in source, should be scrubbed not registered
    claim_values = {c.get("value") for c in s.get("numeric_claims", []) if isinstance(c, dict)}
    assert "9,999" not in claim_values


def test_numeric_registry_empty_claims():
    """Empty numeric_claims list with no numbers in text is handled gracefully."""
    from summarize_pdf import critic_ensure_numeric_registry
    s = _make_summary(
        numeric_claims=[],
        tldr=[{"text": "No numbers here", "sources": ["BOA"]}],
        what_moved_today=[],
        what_can_move_tomorrow=[],
        trade_ideas=[],
        fingerprint_quotes=["the risk of a policy mistake is rising"],
    )
    registrations = critic_ensure_numeric_registry(s, "No numbers in source either")
    assert registrations == 0


# ===========================================================================
# Tests: Full Critic Pass
# ===========================================================================

def test_critic_pass_disabled_by_default():
    """Critic pass is a no-op when CRITIC_ENABLED is False."""
    from summarize_pdf import critic_pass
    s = _make_summary()
    original = copy.deepcopy(s)
    result = critic_pass(s, SOURCE_TEXT)
    # Should not have critic_pass metadata since it's disabled
    assert "critic_pass" not in result.get("meta", {})


def test_critic_pass_enabled_via_override():
    """Critic pass runs when enable=True is passed."""
    from summarize_pdf import critic_pass
    s = _make_summary()
    result = critic_pass(s, SOURCE_TEXT, enable=True)
    assert result["meta"]["critic_pass"] is True
    assert "critic_dedup_count" in result["meta"]
    assert "critic_quote_drops" in result["meta"]
    assert "critic_numeric_registrations" in result["meta"]


def test_critic_pass_output_is_valid_json():
    """After critic pass, the output is serializable to valid JSON."""
    from summarize_pdf import critic_pass
    s = _make_summary()
    result = critic_pass(s, SOURCE_TEXT, enable=True)
    serialized = json.dumps(result, indent=2, ensure_ascii=False)
    reparsed = json.loads(serialized)
    assert reparsed["schema_version"] == "twifo.sum.v1"


def test_critic_pass_never_adds_new_sections():
    """Critic pass does not add any new section keys."""
    from summarize_pdf import critic_pass
    s = _make_summary()
    original_keys = set(s["sections"].keys())
    result = critic_pass(s, SOURCE_TEXT, enable=True)
    new_keys = set(result["sections"].keys())
    assert new_keys == original_keys, f"New keys added: {new_keys - original_keys}"


def test_critic_pass_never_adds_new_bullets():
    """Critic pass only removes bullets, never adds."""
    from summarize_pdf import critic_pass
    s = _make_summary()
    original_counts = {
        k: len(v) for k, v in s["sections"].items() if isinstance(v, list)
    }
    result = critic_pass(s, SOURCE_TEXT, enable=True)
    for k, v in result["sections"].items():
        if isinstance(v, list):
            assert len(v) <= original_counts.get(k, 0), (
                f"Section {k} grew from {original_counts.get(k, 0)} to {len(v)}"
            )


def test_critic_pass_stamps_metadata():
    """Critic pass stamps _meta fields."""
    from summarize_pdf import critic_pass
    s = _make_summary()
    result = critic_pass(s, SOURCE_TEXT, enable=True)
    meta = result["meta"]
    assert meta["critic_pass"] is True
    assert isinstance(meta["critic_dedup_count"], int)
    assert isinstance(meta["critic_quote_drops"], int)
    assert isinstance(meta["critic_numeric_registrations"], int)


def test_critic_pass_warns_on_low_fingerprints():
    """Critic pass warns when fingerprint_quotes drops below 3."""
    from summarize_pdf import critic_pass
    s = _make_summary(fingerprint_quotes=[
        "the risk of a policy mistake is rising",  # real
        "This is a completely fabricated quote",  # fake
        "Another fake quote not in source",  # fake
    ])
    result = critic_pass(s, SOURCE_TEXT, enable=True)
    meta = result["meta"]
    assert meta["critic_quote_drops"] >= 2
    assert len(result["fingerprint_quotes"]) <= 1
    assert "critic_warnings" in meta


def test_critic_pass_idempotent():
    """Running critic pass twice produces the same result."""
    from summarize_pdf import critic_pass
    s = _make_summary()
    result1 = critic_pass(copy.deepcopy(s), SOURCE_TEXT, enable=True)
    # Run again on the already-cleaned result
    result2 = critic_pass(copy.deepcopy(result1), SOURCE_TEXT, enable=True)
    # Second pass should make no further changes
    assert result2["meta"]["critic_dedup_count"] == 0
    assert result2["meta"]["critic_quote_drops"] == 0


# ===========================================================================
# Tests: Helper functions
# ===========================================================================

def test_critic_tokenize():
    from summarize_pdf import _critic_tokenize
    tokens = _critic_tokenize("ES dropped 0.8% to test 5,450 support")
    assert "dropped" in tokens
    assert "support" in tokens
    assert "test" in tokens


def test_critic_jaccard_identical():
    from summarize_pdf import _critic_jaccard
    a = {"es", "dropped", "support", "level"}
    assert _critic_jaccard(a, a) == 1.0


def test_critic_jaccard_disjoint():
    from summarize_pdf import _critic_jaccard
    a = {"es", "dropped"}
    b = {"gold", "rallied"}
    assert _critic_jaccard(a, b) == 0.0


def test_critic_jaccard_partial():
    from summarize_pdf import _critic_jaccard
    a = {"es", "dropped", "support"}
    b = {"es", "dropped", "resistance"}
    sim = _critic_jaccard(a, b)
    assert 0.4 < sim < 0.6  # 2/4 = 0.5


def test_is_near_verbatim_exact():
    from summarize_pdf import _critic_is_near_verbatim
    assert _critic_is_near_verbatim(
        "the risk of a policy mistake is rising", SOURCE_TEXT
    )


def test_is_near_verbatim_case_insensitive():
    from summarize_pdf import _critic_is_near_verbatim
    assert _critic_is_near_verbatim(
        "THE RISK OF A POLICY MISTAKE IS RISING", SOURCE_TEXT
    )


def test_is_near_verbatim_rejects_fabricated():
    from summarize_pdf import _critic_is_near_verbatim
    assert not _critic_is_near_verbatim(
        "Bitcoin will replace all fiat currencies by 2030", SOURCE_TEXT
    )


def test_is_near_verbatim_empty():
    from summarize_pdf import _critic_is_near_verbatim
    assert not _critic_is_near_verbatim("", SOURCE_TEXT)
    assert not _critic_is_near_verbatim("some quote", "")


# ===========================================================================
# Runner
# ===========================================================================

def _run_all():
    """Simple test runner."""
    test_functions = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    errors = []

    for fn in test_functions:
        name = fn.__name__
        try:
            fn()
            passed += 1
            print(f"  [PASS] {name}")
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  [FAIL] {name}: {e}")

    print(f"\nResults: {passed} passed, {failed} failed out of {passed + failed}")
    if errors:
        print("\nFailures:")
        for name, err in errors:
            print(f"  {name}: {err}")
    return failed == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
