"""
Tests for Step A: Pre-Summarization Triage.
Purpose: Verify triage prompt building, skip logic, stub generation, and config flag.
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, r"c:\Coding Projects\TWIFO_Sharing")

from summarize_pdf import (
    _build_triage_prompt,
    should_skip_summarization,
    _skipped_stub,
    TRIAGE_SYSTEM_PROMPT,
    TRIAGE_USER_PROMPT,
    TRIAGE_INPUT_CHARS,
    TRIAGE_SKIP_PRIORITY_THRESHOLD,
    TRIAGE_ENABLED,
    SCHEMA_SUM_V1,
    _iso_now,
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


# ── 1. Prompt Building ──

def test_prompt_contains_placeholders():
    print("\n--- test_prompt_contains_placeholders ---")
    check("TITLE placeholder in template", "<<<TITLE>>>" in TRIAGE_USER_PROMPT)
    check("TEXT placeholder in template", "<<<TEXT>>>" in TRIAGE_USER_PROMPT)


def test_build_triage_prompt():
    print("\n--- test_build_triage_prompt ---")
    prompt = _build_triage_prompt("BOA_Report_20260212_w", "Gold rose sharply today.")
    check("title inserted", "BOA_Report_20260212_w" in prompt)
    check("text inserted", "Gold rose sharply today." in prompt)
    check("no leftover TITLE placeholder", "<<<TITLE>>>" not in prompt)
    check("no leftover TEXT placeholder", "<<<TEXT>>>" not in prompt)


def test_build_triage_prompt_truncation():
    print("\n--- test_build_triage_prompt_truncation ---")
    # The function itself doesn't truncate (triage_document does), but verify it handles long text
    long_text = "A" * 10000
    prompt = _build_triage_prompt("test", long_text)
    check("long text accepted", len(prompt) > 10000)


def test_system_prompt_grounding():
    print("\n--- test_system_prompt_grounding ---")
    check("grounding rule present", "STRICT GROUNDING" in TRIAGE_SYSTEM_PROMPT)
    check("verbatim rule present", "verbatim" in TRIAGE_SYSTEM_PROMPT.lower())
    check("JSON output rule", "valid JSON" in TRIAGE_SYSTEM_PROMPT)


# ── 2. Skip Logic ──

def test_should_skip_irrelevant_low_priority():
    print("\n--- test_should_skip_irrelevant_low_priority ---")
    result = {
        "is_market_relevant": False,
        "priority_score_0_10": 1,
        "reason_quote": "This is an HR document",
        "triage_model": "gpt-4o-mini",
        "triage_error": None,
    }
    check("skip irrelevant + low priority", should_skip_summarization(result) is True)


def test_should_skip_at_threshold():
    print("\n--- test_should_skip_at_threshold ---")
    result = {
        "is_market_relevant": False,
        "priority_score_0_10": TRIAGE_SKIP_PRIORITY_THRESHOLD,
        "reason_quote": "(none)",
        "triage_model": "gpt-4o-mini",
        "triage_error": None,
    }
    check(
        f"skip at threshold ({TRIAGE_SKIP_PRIORITY_THRESHOLD})",
        should_skip_summarization(result) is True,
    )


def test_should_not_skip_above_threshold():
    print("\n--- test_should_not_skip_above_threshold ---")
    result = {
        "is_market_relevant": False,
        "priority_score_0_10": TRIAGE_SKIP_PRIORITY_THRESHOLD + 1,
        "reason_quote": "(none)",
        "triage_model": "gpt-4o-mini",
        "triage_error": None,
    }
    check(
        f"no skip above threshold ({TRIAGE_SKIP_PRIORITY_THRESHOLD + 1})",
        should_skip_summarization(result) is False,
    )


def test_should_not_skip_relevant():
    print("\n--- test_should_not_skip_relevant ---")
    result = {
        "is_market_relevant": True,
        "priority_score_0_10": 1,
        "reason_quote": "(none)",
        "triage_model": "gpt-4o-mini",
        "triage_error": None,
    }
    check("no skip when relevant (even low priority)", should_skip_summarization(result) is False)


def test_should_not_skip_on_error():
    print("\n--- test_should_not_skip_on_error ---")
    result = {
        "is_market_relevant": False,
        "priority_score_0_10": 0,
        "reason_quote": "(none)",
        "triage_model": "gpt-4o-mini",
        "triage_error": "API timeout",
    }
    check("no skip on triage error", should_skip_summarization(result) is False)


def test_should_not_skip_relevant_high_priority():
    print("\n--- test_should_not_skip_relevant_high_priority ---")
    result = {
        "is_market_relevant": True,
        "priority_score_0_10": 8,
        "reason_quote": "Fed announced rate cut",
        "triage_model": "gpt-4o-mini",
        "triage_error": None,
    }
    check("no skip for high priority relevant", should_skip_summarization(result) is False)


def test_skip_edge_case_zero_priority():
    print("\n--- test_skip_edge_case_zero_priority ---")
    result = {
        "is_market_relevant": False,
        "priority_score_0_10": 0,
        "reason_quote": "Company picnic announcement",
        "triage_model": "gpt-4o-mini",
        "triage_error": None,
    }
    check("skip at priority 0", should_skip_summarization(result) is True)


# ── 3. Skipped Stub ──

def test_skipped_stub_structure():
    print("\n--- test_skipped_stub_structure ---")
    triage_result = {
        "is_market_relevant": False,
        "priority_score_0_10": 1,
        "reason_quote": "Internal memo about office supplies",
        "triage_model": "gpt-4o-mini",
        "triage_error": None,
    }
    extraction = {"status": "ok", "method_used": "pypdf", "chars_total": 5000}
    meta = {"title": "test_doc", "provider": "O", "published_date": "20260212"}

    stub = _skipped_stub(
        Path("test_doc.pdf"),
        reason="Triage: not market-relevant",
        triage_result=triage_result,
        extraction=extraction,
        meta=meta,
    )

    check("has schema_version", stub.get("schema_version") == SCHEMA_SUM_V1)
    check("kind is article", stub.get("kind") == "article")
    check("skipped flag", stub.get("skipped") is True)
    check("skip_reason present", "not market-relevant" in stub.get("skip_reason", ""))
    check("triage result stored", stub.get("triage") == triage_result)
    check("meta.skipped", stub.get("meta", {}).get("skipped") is True)
    check("meta.triage present", stub.get("meta", {}).get("triage") is not None)
    check("extraction preserved", stub.get("extraction", {}).get("status") == "ok")


def test_skipped_stub_has_empty_sections():
    print("\n--- test_skipped_stub_has_empty_sections ---")
    triage_result = {
        "is_market_relevant": False,
        "priority_score_0_10": 0,
        "reason_quote": "(none)",
        "triage_model": "gpt-4o-mini",
        "triage_error": None,
    }
    stub = _skipped_stub(
        Path("test.pdf"),
        reason="test",
        triage_result=triage_result,
        extraction={"status": "ok"},
        meta={"title": "test"},
    )

    sections = stub.get("sections", {})
    expected_keys = [
        "what_moved_today", "what_can_move_tomorrow", "trade_ideas",
        "tldr", "what_occurred", "forward_watch", "warnings",
        "tips_reminders", "cross_asset_impacts", "scenarios",
    ]
    for key in expected_keys:
        check(f"sections.{key} is empty list", sections.get(key) == [], f"got {sections.get(key)}")

    check("fingerprint_quotes empty", stub.get("fingerprint_quotes") == [])
    check("numeric_claims empty", stub.get("numeric_claims") == [])
    check("chart_observations empty", stub.get("chart_observations") == [])


def test_skipped_stub_serializable():
    print("\n--- test_skipped_stub_serializable ---")
    triage_result = {
        "is_market_relevant": False,
        "priority_score_0_10": 1,
        "reason_quote": "test quote",
        "triage_model": "gpt-4o-mini",
        "triage_error": None,
    }
    stub = _skipped_stub(
        Path("test.pdf"),
        reason="test",
        triage_result=triage_result,
        extraction={"status": "ok"},
        meta={"title": "test"},
    )
    try:
        serialized = json.dumps(stub, ensure_ascii=False)
        deserialized = json.loads(serialized)
        check("JSON round-trip", deserialized.get("skipped") is True)
    except Exception as e:
        check("JSON serializable", False, str(e))


# ── 4. Configuration Flag ──

def test_config_flag_default():
    print("\n--- test_config_flag_default ---")
    # Default should be False (disabled) unless env var is set
    check("TRIAGE_ENABLED default is False", TRIAGE_ENABLED is False)


def test_config_constants():
    print("\n--- test_config_constants ---")
    check("TRIAGE_INPUT_CHARS is 4000", TRIAGE_INPUT_CHARS == 4000)
    check("TRIAGE_SKIP_PRIORITY_THRESHOLD is 2", TRIAGE_SKIP_PRIORITY_THRESHOLD == 2)


# ── 5. triage_document (offline/mock) ──

def test_triage_document_empty_text():
    print("\n--- test_triage_document_empty_text ---")
    from summarize_pdf import triage_document
    result = triage_document("test_doc", "")
    check("empty text -> not relevant", result["is_market_relevant"] is False)
    check("empty text -> priority 0", result["priority_score_0_10"] == 0)
    check("empty text -> error flag", result["triage_error"] == "empty_text")


def test_triage_document_whitespace_only():
    print("\n--- test_triage_document_whitespace_only ---")
    from summarize_pdf import triage_document
    result = triage_document("test_doc", "   \n\t  ")
    check("whitespace -> not relevant", result["is_market_relevant"] is False)
    check("whitespace -> priority 0", result["priority_score_0_10"] == 0)
    check("whitespace -> error flag", result["triage_error"] == "empty_text")


# ── 6. Integration: summarize_pdf enable_triage parameter ──

def test_summarize_pdf_accepts_enable_triage():
    print("\n--- test_summarize_pdf_accepts_enable_triage ---")
    import inspect
    from summarize_pdf import summarize_pdf
    sig = inspect.signature(summarize_pdf)
    params = list(sig.parameters.keys())
    check("enable_triage in signature", "enable_triage" in params, f"params: {params}")
    # Check default is None
    param = sig.parameters["enable_triage"]
    check("default is None", param.default is None, f"default: {param.default}")


# ── Run All ──

def run_all():
    global passed, failed
    passed = 0
    failed = 0

    print("=" * 60)
    print("Step A: Pre-Summarization Triage Tests")
    print("=" * 60)

    # Prompt building
    test_prompt_contains_placeholders()
    test_build_triage_prompt()
    test_build_triage_prompt_truncation()
    test_system_prompt_grounding()

    # Skip logic
    test_should_skip_irrelevant_low_priority()
    test_should_skip_at_threshold()
    test_should_not_skip_above_threshold()
    test_should_not_skip_relevant()
    test_should_not_skip_on_error()
    test_should_not_skip_relevant_high_priority()
    test_skip_edge_case_zero_priority()

    # Skipped stub
    test_skipped_stub_structure()
    test_skipped_stub_has_empty_sections()
    test_skipped_stub_serializable()

    # Config
    test_config_flag_default()
    test_config_constants()

    # triage_document (offline)
    test_triage_document_empty_text()
    test_triage_document_whitespace_only()

    # Integration
    test_summarize_pdf_accepts_enable_triage()

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
