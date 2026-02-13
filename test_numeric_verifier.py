"""
Tests for Step D.5: Post-LLM Deterministic Numeric Verifier.
Purpose: Verify numeric extraction, normalization, source matching, and scrubbing.
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

import sys
import json

sys.path.insert(0, r"c:\Coding Projects\TWIFO_Sharing")

from summarize_pdf import (
    _normalize_numeric,
    _extract_numeric_tokens_from_value,
    _walk_json_for_numerics,
    _extract_numerics_from_whitelist_paths,
    _build_source_index,
    _verify_token_in_source,
    verify_and_scrub_numerics,
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


# ── 1. Normalization ──

def test_normalize_commas():
    print("\n--- test_normalize_commas ---")
    check("strip commas", _normalize_numeric("1,234,567") == "1234567")
    check("strip commas decimal", _normalize_numeric("4,250.50") == "4250.50")
    check("no commas passthrough", _normalize_numeric("500") == "500")


def test_normalize_percentages():
    print("\n--- test_normalize_percentages ---")
    check("pct no space", _normalize_numeric("4.25%") == "4.25%")
    check("pct with space", _normalize_numeric("4.25 %") == "4.25%")
    check("pct whitespace collapse", _normalize_numeric(" 3.5  % ") == "3.5%")
    check("no pct passthrough", _normalize_numeric("100") == "100")


def test_normalize_whitespace():
    print("\n--- test_normalize_whitespace ---")
    check("leading trailing", _normalize_numeric("  500  ") == "500")
    check("inner whitespace", _normalize_numeric("1 000") == "1000")


# ── 2. Token Extraction ──

def test_extract_tokens_basic():
    print("\n--- test_extract_tokens_basic ---")
    tokens = _extract_numeric_tokens_from_value("ES rose to 5,450 from 5,400")
    norms = [_normalize_numeric(t) for t in tokens]
    check("finds 5450", "5450" in norms, f"got {norms}")
    check("finds 5400", "5400" in norms, f"got {norms}")


def test_extract_tokens_percentages():
    print("\n--- test_extract_tokens_percentages ---")
    tokens = _extract_numeric_tokens_from_value("Yield rose 4.25% to 4.50%")
    norms = [_normalize_numeric(t) for t in tokens]
    check("finds 4.25%", "4.25%" in norms, f"got {norms}")
    check("finds 4.50%", "4.50%" in norms, f"got {norms}")


def test_extract_tokens_dates():
    print("\n--- test_extract_tokens_dates ---")
    tokens = _extract_numeric_tokens_from_value("Published on 20260212")
    norms = [_normalize_numeric(t) for t in tokens]
    check("finds date 20260212", "20260212" in norms, f"got {norms}")


def test_extract_tokens_negative():
    print("\n--- test_extract_tokens_negative ---")
    tokens = _extract_numeric_tokens_from_value("Dropped -2.5% on the day")
    norms = [_normalize_numeric(t) for t in tokens]
    check("finds negative", any("2.5" in n for n in norms), f"got {norms}")


def test_extract_tokens_mixed():
    print("\n--- test_extract_tokens_mixed ---")
    tokens = _extract_numeric_tokens_from_value(
        "Gold at 2,350.50, silver at 28.75, VIX at 15"
    )
    norms = [_normalize_numeric(t) for t in tokens]
    check("finds gold price", "2350.50" in norms, f"got {norms}")
    check("finds silver price", "28.75" in norms, f"got {norms}")
    check("finds VIX", "15" in norms, f"got {norms}")


# ── 3. JSON Walking ──

def test_walk_json_sections():
    print("\n--- test_walk_json_sections ---")
    test_json = {
        "meta": {"title": "test", "score_0_10": 7},  # score_0_10 is skipped
        "sections": {
            "what_moved_today": [
                {"text": "ES rose to 5,450 on strong volume"}
            ],
            "tldr": [
                {"text": "Gold hit 2,350 as yields fell to 4.25%"}
            ],
        },
        "numeric_claims": [  # Should be skipped entirely
            {"value": "5,450", "context": "ES", "source_quote": "..."}
        ],
        "summary_score_0_10": 7,  # Should be skipped
    }
    tokens = _walk_json_for_numerics(test_json)
    norms = [t["normalized"] for t in tokens]
    check("finds 5450 from sections", "5450" in norms, f"got {norms}")
    check("finds 2350 from tldr", "2350" in norms, f"got {norms}")
    check("finds 4.25% from tldr", "4.25%" in norms, f"got {norms}")
    # Should NOT find score_0_10 or summary_score_0_10
    check("skips score_0_10", "7" not in norms, f"got {norms}")


def test_walk_json_trade_ideas():
    print("\n--- test_walk_json_trade_ideas ---")
    test_json = {
        "sections": {
            "trade_ideas": [
                {
                    "product": "ES",
                    "key_levels": ["5,450", "5,500"],
                    "source_quote": "ES support at 5,450 and resistance at 5,500",
                }
            ]
        }
    }
    tokens = _walk_json_for_numerics(test_json)
    norms = [t["normalized"] for t in tokens]
    check("finds 5450 from key_levels", "5450" in norms, f"got {norms}")
    check("finds 5500 from key_levels", "5500" in norms, f"got {norms}")


# ── 4. Source Verification ──

def test_verify_exact_match():
    print("\n--- test_verify_exact_match ---")
    source = "ES traded at 5,450 today. Gold hit 2,350.50."
    idx = _build_source_index(source)
    check("5450 found", _verify_token_in_source("5450", idx, source))
    check("2350.50 found", _verify_token_in_source("2350.50", idx, source))
    check("9999 not found", not _verify_token_in_source("9999", idx, source))


def test_verify_comma_normalization():
    print("\n--- test_verify_comma_normalization ---")
    source = "The index reached 1,234,567 points."
    idx = _build_source_index(source)
    check("comma-stripped match", _verify_token_in_source("1234567", idx, source))


def test_verify_percent_normalization():
    print("\n--- test_verify_percent_normalization ---")
    source = "Yield rose to 4.25% from 4.10 %."
    idx = _build_source_index(source)
    check("4.25% found", _verify_token_in_source("4.25%", idx, source))
    check("4.10% found (space normalized)", _verify_token_in_source("4.10%", idx, source))


def test_verify_date_in_source():
    print("\n--- test_verify_date_in_source ---")
    source = "Report dated 20260212 shows improvement."
    idx = _build_source_index(source)
    check("date found", _verify_token_in_source("20260212", idx, source))
    check("wrong date not found", not _verify_token_in_source("20260213", idx, source))


# ── 5. Full Pipeline: verify_and_scrub_numerics ──

def test_full_pipeline_all_verified():
    print("\n--- test_full_pipeline_all_verified ---")
    source_text = "ES rose to 5,450 from 5,400. Gold hit 2,350."
    sum_json = {
        "meta": {"title": "test"},
        "extraction": {"status": "ok"},
        "sections": {
            "what_moved_today": [
                {"text": "ES rose to 5,450 from 5,400"}
            ],
            "tldr": [
                {"text": "Gold hit 2,350"}
            ],
        },
        "numeric_claims": [
            {"value": "5,450", "context": "ES level", "source_quote": "ES rose to 5,450"},
            {"value": "5,400", "context": "ES level", "source_quote": "from 5,400"},
            {"value": "2,350", "context": "Gold", "source_quote": "Gold hit 2,350"},
        ],
        "fingerprint_quotes": [],
    }
    result = verify_and_scrub_numerics(sum_json, source_text)
    meta = result["meta"]
    check("coverage 100%", meta["numeric_coverage_pct"] == 100.0, f"got {meta.get('numeric_coverage_pct')}")
    check("no unverified", len(meta.get("unverified_numbers", [])) == 0)
    check("no low_confidence", not meta.get("low_confidence", False))


def test_full_pipeline_hallucinated_number():
    print("\n--- test_full_pipeline_hallucinated_number ---")
    source_text = "ES rose to 5,450 today."
    sum_json = {
        "meta": {"title": "test"},
        "extraction": {"status": "ok"},
        "sections": {
            "what_moved_today": [
                {"text": "ES rose to 5,450 with target 5,600"}  # 5,600 is hallucinated
            ],
        },
        "numeric_claims": [
            {"value": "5,450", "context": "ES", "source_quote": "ES rose to 5,450"},
            {"value": "5,600", "context": "ES target", "source_quote": "target 5,600"},
        ],
        "fingerprint_quotes": [],
    }
    result = verify_and_scrub_numerics(sum_json, source_text)
    meta = result["meta"]
    check("low_confidence set", meta.get("low_confidence") is True)
    check("has unverified", len(meta.get("unverified_numbers", [])) > 0)
    unverified_norms = [u["normalized"] for u in meta["unverified_numbers"]]
    check("5600 is unverified", "5600" in unverified_norms, f"got {unverified_norms}")
    # 5,600 should be scrubbed from the text
    bullet_text = result["sections"]["what_moved_today"][0]["text"]
    check("5600 scrubbed from text", "5,600" not in bullet_text, f"got: {bullet_text}")
    # 5,600 should be removed from numeric_claims
    claim_values = [_normalize_numeric(str(c.get("value", ""))) for c in result["numeric_claims"]]
    check("5600 removed from claims", "5600" not in claim_values, f"claims: {claim_values}")
    check("5450 still in claims", "5450" in claim_values, f"claims: {claim_values}")


def test_full_pipeline_missing_claim_auto_registered():
    print("\n--- test_full_pipeline_missing_claim_auto_registered ---")
    source_text = "ES rose to 5,450. Gold hit 2,350."
    sum_json = {
        "meta": {"title": "test"},
        "extraction": {"status": "ok"},
        "sections": {
            "what_moved_today": [
                {"text": "ES rose to 5,450"},
                {"text": "Gold hit 2,350"},
            ],
        },
        "numeric_claims": [
            # Only 5,450 is claimed; 2,350 is missing from registry
            {"value": "5,450", "context": "ES", "source_quote": "ES rose to 5,450"},
        ],
        "fingerprint_quotes": [],
    }
    result = verify_and_scrub_numerics(sum_json, source_text)
    claim_values = [_normalize_numeric(str(c.get("value", ""))) for c in result["numeric_claims"]]
    check("2350 auto-registered", "2350" in claim_values, f"claims: {claim_values}")
    check("5450 still present", "5450" in claim_values, f"claims: {claim_values}")
    check("no unverified (both in source)", len(result["meta"].get("unverified_numbers", [])) == 0)


def test_full_pipeline_no_numbers():
    print("\n--- test_full_pipeline_no_numbers ---")
    source_text = "The Fed signaled a dovish stance."
    sum_json = {
        "meta": {"title": "test"},
        "extraction": {"status": "ok"},
        "sections": {
            "tldr": [{"text": "Fed signaled dovish stance"}],
        },
        "numeric_claims": [],
        "fingerprint_quotes": [],
    }
    result = verify_and_scrub_numerics(sum_json, source_text)
    check("coverage 100% with no numbers", result["meta"]["numeric_coverage_pct"] == 100.0)
    check("no unverified", len(result["meta"].get("unverified_numbers", [])) == 0)


def test_full_pipeline_percentage_verification():
    print("\n--- test_full_pipeline_percentage_verification ---")
    source_text = "The 10-year yield rose to 4.25% from 4.10%."
    sum_json = {
        "meta": {"title": "test"},
        "extraction": {"status": "ok"},
        "sections": {
            "what_moved_today": [
                {"text": "10-year yield rose to 4.25% from 4.10%"}
            ],
        },
        "numeric_claims": [
            {"value": "4.25%", "context": "10Y yield", "source_quote": "rose to 4.25%"},
            {"value": "4.10%", "context": "10Y yield", "source_quote": "from 4.10%"},
        ],
        "fingerprint_quotes": [],
    }
    result = verify_and_scrub_numerics(sum_json, source_text)
    check("coverage 100%", result["meta"]["numeric_coverage_pct"] == 100.0)
    check("no unverified", len(result["meta"].get("unverified_numbers", [])) == 0)
    # Both percentages should remain in text
    bullet = result["sections"]["what_moved_today"][0]["text"]
    check("4.25% preserved", "4.25%" in bullet, f"got: {bullet}")
    check("4.10% preserved", "4.10%" in bullet, f"got: {bullet}")


def test_full_pipeline_coverage_pct_partial():
    print("\n--- test_full_pipeline_coverage_pct_partial ---")
    source_text = "ES at 5,450."
    sum_json = {
        "meta": {"title": "test"},
        "extraction": {"status": "ok"},
        "sections": {
            "what_moved_today": [
                {"text": "ES at 5,450 with target 5,600 and stop 5,300"}
            ],
        },
        "numeric_claims": [],
        "fingerprint_quotes": [],
    }
    result = verify_and_scrub_numerics(sum_json, source_text)
    coverage = result["meta"]["numeric_coverage_pct"]
    # 1 of 3 unique numbers verified -> ~33.3%
    check("partial coverage", 30 <= coverage <= 40, f"got {coverage}%")
    check("has unverified", len(result["meta"]["unverified_numbers"]) > 0)


# ── 6. Path-scoped verification (whitelist only) ──

def test_numbers_in_meta_title_do_not_count():
    """
    Numbers in meta.title must NOT be scanned, verified, or trigger low_confidence.
    Only sections.*[].text, meta.theme, fingerprint_quotes[] are scanned.
    """
    print("\n--- test_numbers_in_meta_title_do_not_count ---")
    source_text = "The Fed held rates steady."  # no numbers
    sum_json = {
        "meta": {"title": "Q4 2025 Report", "model": "gpt-4"},
        "sections": {
            "what_moved_today": [{"text": "Rates were unchanged."}],
        },
        "numeric_claims": [],
        "fingerprint_quotes": [],
    }
    result = verify_and_scrub_numerics(sum_json, source_text)
    meta = result["meta"]
    # 2025 is in meta.title but we do not scan it -> no tokens from whitelist -> coverage 100%, no low_confidence
    check("no unverified (meta.title not scanned)", len(meta.get("unverified_numbers", [])) == 0, f"got {meta.get('unverified_numbers')}")
    check("no low_confidence (no scanned numerics)", not meta.get("low_confidence", False))
    claim_values = [_normalize_numeric(str(c.get("value", ""))) for c in result.get("numeric_claims", [])]
    check("2025 not in numeric_claims", "2025" not in claim_values, f"claims: {claim_values}")
    check("meta.title unchanged", result["meta"]["title"] == "Q4 2025 Report", "meta.title must not be scrubbed")


def test_numbers_in_sections_what_moved_today_count():
    """
    Numbers in sections.what_moved_today[].text MUST be scanned, verified,
    and can trigger low_confidence if unverified.
    """
    print("\n--- test_numbers_in_sections_what_moved_today_count ---")
    source_text = "ES closed at 5,450."  # only 5450 in source
    sum_json = {
        "meta": {"title": "test"},
        "sections": {
            "what_moved_today": [
                {"text": "ES at 5,450 with target 5,600"}  # 5600 not in source
            ],
        },
        "numeric_claims": [],
        "fingerprint_quotes": [],
    }
    result = verify_and_scrub_numerics(sum_json, source_text)
    meta = result["meta"]
    check("low_confidence set (unverified in section text)", meta.get("low_confidence") is True)
    unverified_norms = [u["normalized"] for u in meta.get("unverified_numbers", [])]
    check("5600 unverified", "5600" in unverified_norms, f"got {unverified_norms}")
    check("reason includes unverified_numerics", "unverified_numerics" in (meta.get("low_confidence_reason") or ""))
    bullet = result["sections"]["what_moved_today"][0]["text"]
    check("5600 scrubbed from section text", "5,600" not in bullet, f"got: {bullet}")


# ── Run All ──

def run_all():
    global passed, failed
    passed = 0
    failed = 0

    print("=" * 60)
    print("Step D.5: Numeric Verifier Tests")
    print("=" * 60)

    # Normalization
    test_normalize_commas()
    test_normalize_percentages()
    test_normalize_whitespace()

    # Token extraction
    test_extract_tokens_basic()
    test_extract_tokens_percentages()
    test_extract_tokens_dates()
    test_extract_tokens_negative()
    test_extract_tokens_mixed()

    # JSON walking
    test_walk_json_sections()
    test_walk_json_trade_ideas()

    # Source verification
    test_verify_exact_match()
    test_verify_comma_normalization()
    test_verify_percent_normalization()
    test_verify_date_in_source()

    # Full pipeline
    test_full_pipeline_all_verified()
    test_full_pipeline_hallucinated_number()
    test_full_pipeline_missing_claim_auto_registered()
    test_full_pipeline_no_numbers()
    test_full_pipeline_percentage_verification()
    test_full_pipeline_coverage_pct_partial()

    # Path-scoped (whitelist) verification
    test_numbers_in_meta_title_do_not_count()
    test_numbers_in_sections_what_moved_today_count()

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
