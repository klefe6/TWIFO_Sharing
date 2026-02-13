"""
Tests for format_validator.py: fix_summary_format and validate_article_summary.
Purpose: Ensure the formatter is purely structural — no filler injection.

Run:
    python test_format_validator.py
    python -m pytest test_format_validator.py -v
"""

import copy
import pytest

from format_validator import fix_summary_format, validate_article_summary


# Banned filler phrases that must NEVER appear in output
BANNED_PHRASES = [
    "market data pending analysis",
    "monitor key levels and data releases",
    "monitor key levels",
    "pending analysis",
    "data not available",
]


def _make_summary(
    tldr: list | None = None,
    what_occurred: list | None = None,
    forward_watch: list | None = None,
    trade_ideas: list | None = None,
    tips_reminders: list | None = None,
) -> dict:
    """Build a minimal summary dict for testing."""
    return {
        "meta": {"provider": "TEST", "theme": "Test Theme"},
        "sections": {
            "tldr": tldr if tldr is not None else [
                {"text": "Bullet one"}, {"text": "Bullet two"}, {"text": "Bullet three"}
            ],
            "what_occurred": what_occurred if what_occurred is not None else [],
            "forward_watch": forward_watch if forward_watch is not None else [],
            "trade_ideas": trade_ideas if trade_ideas is not None else [],
            "tips_reminders": tips_reminders if tips_reminders is not None else [],
        },
    }


def _collect_all_texts(summary: dict) -> list[str]:
    """Extract every text string from all sections."""
    texts = []
    for key, items in summary.get("sections", {}).items():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                t = item.get("text", "")
            else:
                t = str(item)
            if t:
                texts.append(t.lower())
    return texts


# ── Empty arrays stay empty ──────────────────────────────────────────────

def test_empty_what_occurred_stays_empty():
    """what_occurred: [] must remain [] after fix — no padding."""
    s = _make_summary(what_occurred=[])
    result = fix_summary_format(s)
    assert result["sections"]["what_occurred"] == []


def test_empty_forward_watch_stays_empty():
    """forward_watch: [] must remain [] after fix — no padding."""
    s = _make_summary(forward_watch=[])
    result = fix_summary_format(s)
    assert result["sections"]["forward_watch"] == []


def test_empty_tips_reminders_stays_empty():
    """tips_reminders: [] must remain [] after fix — no padding."""
    s = _make_summary(tips_reminders=[])
    result = fix_summary_format(s)
    assert result["sections"]["tips_reminders"] == []


def test_empty_trade_ideas_stays_empty():
    """trade_ideas: [] must remain [] after fix — no padding."""
    s = _make_summary(trade_ideas=[])
    result = fix_summary_format(s)
    assert result["sections"]["trade_ideas"] == []


# ── No banned phrases ────────────────────────────────────────────────────

def test_no_banned_phrases_injected_on_empty_sections():
    """When all non-TLDR sections are empty, no banned phrases should appear."""
    s = _make_summary(
        what_occurred=[],
        forward_watch=[],
        trade_ideas=[],
        tips_reminders=[],
    )
    result = fix_summary_format(s)
    all_texts = _collect_all_texts(result)
    for phrase in BANNED_PHRASES:
        for text in all_texts:
            assert phrase not in text, (
                f"Banned phrase '{phrase}' found in output: '{text}'"
            )


def test_no_banned_phrases_injected_on_partial_sections():
    """When sections have 1-2 real bullets, fixer must not pad to minimums."""
    s = _make_summary(
        what_occurred=[{"text": "Fed raised rates 25bps"}],
        forward_watch=[{"text": "CPI data release Friday"}],
    )
    result = fix_summary_format(s)
    all_texts = _collect_all_texts(result)

    # Must still have original content
    assert any("fed raised rates" in t for t in all_texts)
    assert any("cpi data release" in t for t in all_texts)

    # Must NOT have filler
    for phrase in BANNED_PHRASES:
        for text in all_texts:
            assert phrase not in text, (
                f"Banned phrase '{phrase}' found in output: '{text}'"
            )


# ── Existing content preserved ───────────────────────────────────────────

def test_real_bullets_preserved():
    """Sections with real content are passed through unchanged."""
    bullets = [
        {"text": "ES dropped 1.2% on FOMC minutes"},
        {"text": "Gold rallied to 2,050 on safe-haven flows"},
        {"text": "Treasury yields climbed to 4.25%"},
    ]
    s = _make_summary(what_occurred=copy.deepcopy(bullets))
    result = fix_summary_format(s)
    assert len(result["sections"]["what_occurred"]) == 3
    texts = [b["text"] for b in result["sections"]["what_occurred"]]
    assert "ES dropped 1.2% on FOMC minutes" in texts


def test_max_bullets_trimmed():
    """Sections over 8 bullets get trimmed to 8."""
    bullets = [{"text": f"Bullet {i}"} for i in range(12)]
    s = _make_summary(what_occurred=copy.deepcopy(bullets))
    result = fix_summary_format(s)
    assert len(result["sections"]["what_occurred"]) == 8


# ── Type coercion ────────────────────────────────────────────────────────

def test_non_list_what_occurred_coerced_to_empty_list():
    """If what_occurred is not a list, coerce to []."""
    s = _make_summary()
    s["sections"]["what_occurred"] = "not a list"
    result = fix_summary_format(s)
    assert result["sections"]["what_occurred"] == []


def test_non_list_forward_watch_coerced_to_empty_list():
    """If forward_watch is not a list, coerce to []."""
    s = _make_summary()
    s["sections"]["forward_watch"] = None
    result = fix_summary_format(s)
    assert result["sections"]["forward_watch"] == []


# ── Validator allows empty ───────────────────────────────────────────────

def test_validator_allows_empty_what_occurred():
    """validate_article_summary should NOT flag empty what_occurred as a violation."""
    s = _make_summary(what_occurred=[])
    is_valid, violations = validate_article_summary(s)
    count_violations = [v for v in violations if "KEY DATA" in v and "need" in v]
    assert count_violations == [], f"Should not flag empty what_occurred: {violations}"


def test_validator_allows_empty_forward_watch():
    """validate_article_summary should NOT flag empty forward_watch as a violation."""
    s = _make_summary(forward_watch=[])
    is_valid, violations = validate_article_summary(s)
    count_violations = [v for v in violations if "FORWARD WATCH" in v and "need" in v]
    assert count_violations == [], f"Should not flag empty forward_watch: {violations}"


if __name__ == "__main__":
    import sys

    tests = [
        test_empty_what_occurred_stays_empty,
        test_empty_forward_watch_stays_empty,
        test_empty_tips_reminders_stays_empty,
        test_empty_trade_ideas_stays_empty,
        test_no_banned_phrases_injected_on_empty_sections,
        test_no_banned_phrases_injected_on_partial_sections,
        test_real_bullets_preserved,
        test_max_bullets_trimmed,
        test_non_list_what_occurred_coerced_to_empty_list,
        test_non_list_forward_watch_coerced_to_empty_list,
        test_validator_allows_empty_what_occurred,
        test_validator_allows_empty_forward_watch,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"[PASS] {test_fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test_fn.__name__}: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed out of {len(tests)}")
    sys.exit(1 if failed else 0)
