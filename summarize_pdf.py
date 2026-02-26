"""
PDF Summarization Module (Redesigned)
Purpose: Summarize PDF research documents - ALWAYS emits JSON + TXT
Author: Kevin Lefebvre
Last Updated: 2026-02-12
Schema: twifo.sum.v1

File Layout:
  originals/           # Original PDFs (read-only)
  artifacts/<basename>/ # Generated files (extracted.txt, sum.json, sum.txt, sum.pdf)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Import path manager for new file layout
try:
    from path_manager import TWIFOPathManager, get_path_manager
    PATH_MANAGER_AVAILABLE = True
except ImportError:
    PATH_MANAGER_AVAILABLE = False
    TWIFOPathManager = None
    get_path_manager = None


# =========================
# Custom Exceptions
# =========================
class SummaryWriteFailedError(Exception):
    """Raised when sum.json write fails (file missing after write). Callers must NOT attempt render."""
    pass

# =========================
# Config
# =========================
SCHEMA_SUM_V1 = "twifo.sum.v1"
MIN_TEXT_CHARS = 1500  # for external PDFs; tune based on your typical reports
MAX_INPUT_CHARS = 50000
DEBUG_RAW_MAX_CHARS = 12000
RETRY_MODEL = "gpt-4o"
BASE_MAX_OUTPUT_TOKENS = 1100
RETRY_MAX_OUTPUT_TOKENS = 1600

# Load API key from environment (set by db_filter_autorun.py)
# Note: Do NOT read .env directly here to avoid silent overrides
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# =========================
# Utilities
# =========================
def _iso_now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _get_prompt_provenance() -> dict:
    """
    Build prompt provenance for meta: version, source file, sha256, git commit.
    Uses article_prompts as single source of truth.
    """
    from twifo_prompts.prompts import article_prompts
    code_git_commit = "(not available)"
    try:
        repo_dir = Path(__file__).resolve().parent
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            code_git_commit = result.stdout.strip()
    except Exception:
        pass
    return {
        "prompt_version": article_prompts.PROMPT_VERSION,
        "prompt_source_file": article_prompts.prompt_source_file(),
        "prompt_sha256": article_prompts.prompt_sha256(),
        "code_git_commit": code_git_commit,
    }


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def _write_txt(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")

def _sum_paths(pdf_path: Path, out_dir: Optional[Path] = None, path_manager: Optional[TWIFOPathManager] = None) -> Tuple[Path, Path]:
    """
    Get summary output paths (sum.json, sum.txt).
    Uses path_manager if available for new structure, else legacy behavior.
    """
    if PATH_MANAGER_AVAILABLE and path_manager:
        basename = pdf_path.stem
        return (
            path_manager.artifact_path(basename, 'sum.json'),
            path_manager.artifact_path(basename, 'sum.txt')
        )
    
    # Legacy behavior for backward compatibility
    out_dir = out_dir or pdf_path.parent
    base = out_dir / pdf_path.stem
    return (Path(str(base) + "__sum.json"), Path(str(base) + "__sum.txt"))

def _sum_debug_path(pdf_path: Path, out_dir: Optional[Path] = None, path_manager: Optional[TWIFOPathManager] = None) -> Path:
    """
    Build debug/extracted text artifact path.
    Maps to extracted.txt in new structure.
    """
    if PATH_MANAGER_AVAILABLE and path_manager:
        basename = pdf_path.stem
        return path_manager.artifact_path(basename, 'extracted.txt')
    
    # Legacy behavior
    out_dir = out_dir or pdf_path.parent
    base = out_dir / pdf_path.stem
    return Path(str(base) + "__sum_debug_raw.txt")

def _truncate_text(text: str, max_chars: int) -> str:
    """
    Truncate text to a safe max size for debug artifacts.
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[TRUNCATED]..."


def _normalize_text_for_hash(text: str) -> str:
    """Normalize article text for content hash (strip, collapse whitespace)."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip())


def _content_hash(text: str) -> str:
    """SHA256 of normalized article text; used in summary cache key."""
    return hashlib.sha256(_normalize_text_for_hash(text).encode("utf-8")).hexdigest()


# Tickers we recognize for product inference (order preserved for display)
_KNOWN_PRODUCTS = ["ES", "NQ", "ZN", "ZB", "GC", "SI", "BTC", "VIX", "CL"]
# Keywords -> product (first match wins for inference)
_PRODUCT_KEYWORDS = [
    ("es", "ES"), ("e-mini s&p", "ES"), ("s&p 500", "ES"), ("spx", "ES"),
    ("nq", "NQ"), ("nasdaq", "NQ"), ("e-mini nasdaq", "NQ"),
    ("zn", "ZN"), ("zb", "ZB"), ("10y", "ZN"), ("10-year", "ZN"), ("treasury", "ZN"), ("t-note", "ZN"), ("t-bond", "ZB"),
    ("gc", "GC"), ("gold", "GC"), ("si", "SI"), ("silver", "SI"),
    ("btc", "BTC"), ("bitcoin", "BTC"), ("crypto", "BTC"),
    ("vix", "VIX"), ("volatility", "VIX"),
    ("cl", "CL"), ("wti", "CL"), ("crude", "CL"), ("oil", "CL"),
]


def _infer_products_from_text(source_text: str) -> Tuple[List[str], str]:
    """
    Infer product tickers from explicit mentions/keywords in source text.
    Returns (list of tickers found, reason string for dev logging).
    """
    if not source_text or not source_text.strip():
        return [], "empty_source"
    text_lower = source_text.lower()
    found: List[str] = []
    for keyword, ticker in _PRODUCT_KEYWORDS:
        if keyword in text_lower and ticker not in found:
            found.append(ticker)
    # Preserve display order (known order)
    ordered = [p for p in _KNOWN_PRODUCTS if p in found]
    reason = f"inferred_from_keywords:{','.join(ordered)}" if ordered else "no_keywords_found"
    return ordered, reason

def _extract_bullet_text(item: Any) -> str:
    """
    Normalize a bullet item to a text string when possible.
    """
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        if "text" in item and item.get("text") is not None:
            return str(item.get("text")).strip()
        for key in ["bullet", "value", "content", "item", "summary"]:
            if key in item and item.get(key) is not None:
                return str(item.get(key)).strip()
    return ""

def _normalize_sections_in_place(sum_json: dict) -> None:
    """
    Ensure every bullet item is a string or {\"text\": \"...\"}.
    """
    sections = sum_json.get("sections", {})
    if not isinstance(sections, dict):
        return
    for key, items in sections.items():
        if key == "trade_ideas":
            continue
        if not isinstance(items, list):
            continue
        normalized: list[Any] = []
        for item in items:
            if isinstance(item, dict):
                if "text" in item:
                    text_value = item.get("text")
                    item["text"] = str(text_value).strip() if text_value is not None else ""
                    if item["text"]:
                        normalized.append(item)
                    continue
                text = _extract_bullet_text(item)
                if text:
                    item["text"] = text
                    normalized.append(item)
                continue
            text = _extract_bullet_text(item)
            if text:
                normalized.append({"text": text})
        sections[key] = normalized

def _count_section_bullets(sections: dict) -> dict:
    """
    Count non-empty bullets per section for debugging.
    """
    counts: dict[str, int] = {}
    keys = [
        "what_moved_today",
        "what_can_move_tomorrow",
        "trade_ideas",
        "tldr",
        "what_occurred",
        "forward_watch",
        "warnings",
        "tips_reminders",
        "cross_asset_impacts",
        "scenarios",
    ]
    for key in keys:
        items = sections.get(key, [])
        if not isinstance(items, list):
            counts[key] = 0
            continue
        if key == "trade_ideas":
            counts[key] = len(items)
            continue
        counts[key] = sum(1 for item in items if _extract_bullet_text(item))
    return counts

def _write_debug_artifact(
    debug_path: Path,
    *,
    model: str,
    raw_output: str,
    bullet_counts: dict,
    quality_reason: str,
    attempt: int,
) -> None:
    """
    Persist debug info for quality gate failures.
    """
    header = (
        "\n"
        f"===== QUALITY GATE FAILURE (ATTEMPT {attempt}) =====\n"
        f"model: {model}\n"
        f"quality_reason: {quality_reason}\n"
        f"bullet_counts: {json.dumps(bullet_counts, ensure_ascii=False)}\n"
        "raw_output:\n"
    )
    payload = _truncate_text(raw_output or "", DEBUG_RAW_MAX_CHARS)
    with open(debug_path, "a", encoding="utf-8", errors="replace") as handle:
        handle.write(header + payload + "\n")

def is_stub(sum_json: dict) -> bool:
    """Check if a sum_json is a stub (failed/skipped) rather than a real summary.

    A summary is considered a stub if any of:
      - ``_is_stub`` flag is True
      - ``extraction.status`` is ``"failed"``
      - ``skipped`` flag is True
      - All primary section lists are empty
    """
    if sum_json.get("_is_stub"):
        return True
    if sum_json.get("skipped"):
        return True
    ext = sum_json.get("extraction", {})
    if ext.get("status") == "failed":
        return True
    sections = sum_json.get("sections", {})
    if not any(sections.get(k) for k in ("tldr", "what_moved_today", "what_can_move_tomorrow")):
        return True
    return False


def _failed_stub(pdf_path: Path, reason: str, extraction: dict, meta: dict) -> dict:
    """
    Unified failure stub with deterministic schema.
    
    Required keys:
    - Primary: what_moved_today, what_can_move_tomorrow, trade_ideas
    - Legacy: tldr, what_occurred, forward_watch, warnings, tips_reminders, cross_asset_impacts, scenarios
    
    All values are lists, no strings, no optional keys.
    ``_is_stub`` is always True so callers can detect stub vs real summary.
    """
    meta_out = {
        **meta,
        "generated_at_iso": _iso_now(),
        "model": meta.get("model", MODEL),
        **_get_prompt_provenance(),
    }
    return {
        "_is_stub": True,
        "schema_version": SCHEMA_SUM_V1,
        "kind": "article",
        "meta": meta_out,
        "ui": {"header_pills": []},
        "extraction": {**extraction, "status": "failed", "reason": reason},
        "fingerprint_quotes": [],
        "numeric_claims": [],
        "sections": {
            "what_moved_today": [],
            "what_can_move_tomorrow": [],
            "trade_ideas": [],
            "tldr": [],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        },
        "chart_text_sources_used": [],
        "chart_observations": [],
    }

# Pattern to detect price levels (excludes years, ambiguous counts)
_PRICE_PATTERN = re.compile(
    r'\$[\d,]+\.?\d*|[\d,]+\.?\d*\s*(?:dollars?|USD|points?|basis\s+points?|bps)|\b[\d,]+\.?\d*\b',
    re.IGNORECASE
)


def _normalize_for_match(s: str) -> str:
    """Normalize string for substring matching: collapse spaces, remove commas."""
    return re.sub(r'[,\s]+', '', str(s).lower())


def _is_year_like(num_str: str) -> bool:
    """Exclude 4-digit years (1900-2099) from price validation. Comma-separated (2,050) = price."""
    if ',' in num_str:
        return False  # "2,050" style = price, not year
    n = re.sub(r'[,\s]', '', num_str)
    if len(n) == 4 and n.isdigit():
        v = int(n)
        if 1900 <= v <= 2099:
            return True
    return False


def _is_ambiguous_small_num(num_str: str) -> bool:
    """Exclude single-digit numbers (e.g. '5' in '5 key levels') from price validation."""
    n = re.sub(r'[,\s.]', '', num_str)
    return len(n) == 1 and n.isdigit()


def sanitize_key_levels(sum_json: dict, source_text: str) -> List[dict]:
    """
    Drop any numeric level that lacks exact substring match in source.
    Strictly source-grounded: no inference, estimation, or guessing.
    
    Returns list of dropped entries for dev logging:
      [{"field": "key_levels", "product": "GC", "level": "...", "reason": "not_explicit_in_source"}, ...]
    """
    dropped: List[dict] = []
    source_norm = _normalize_for_match(source_text)

    trade_ideas = sum_json.get("sections", {}).get("trade_ideas", [])
    if not isinstance(trade_ideas, list):
        return dropped

    for idea in trade_ideas:
        if not isinstance(idea, dict):
            continue
        key_levels = idea.get("key_levels", [])
        if not isinstance(key_levels, list):
            continue
        source_quote = idea.get("source_quote")
        search_texts = [source_norm]
        if source_quote:
            search_texts.append(_normalize_for_match(str(source_quote)))
        product = idea.get("product", "unknown")

        kept: List[str] = []
        for level in key_levels:
            if not isinstance(level, str):
                kept.append(level)
                continue
            if level in ["(not provided in inputs)", "no explicit levels provided", ""]:
                kept.append(level)
                continue

            matches = _PRICE_PATTERN.findall(level)
            # Filter out year-like numbers (don't treat 2026, etc. as price levels)
            price_values = [m for m in matches if not _is_year_like(m)]
            if not price_values:
                # No price-like number in level (e.g. "near resistance") - keep
                kept.append(level)
                continue

            # Require at least one price value to appear in source
            found = any(
                _normalize_for_match(pv) in st
                for pv in price_values
                for st in search_texts
            )
            if found:
                kept.append(level)
            else:
                dropped.append({
                    "field": "key_levels",
                    "product": product,
                    "level": level,
                    "reason": "not_explicit_in_source",
                })

        idea["key_levels"] = kept

    if dropped and os.getenv("DEV_LOGGING") == "1":
        print(f"[SANITIZE] dropped_inferred_level_count={len(dropped)}")
        for d in dropped[:5]:  # Log first 5
            print(f"  - {d['field']} {d['product']}: {d['level'][:60]}... ({d['reason']})")
        if len(dropped) > 5:
            print(f"  ... and {len(dropped) - 5} more")

    return dropped


_PLACEHOLDER_LEVELS = frozenset({"(not provided in inputs)", "no explicit levels provided", ""})


def _has_explicit_level(key_levels: List[Any]) -> bool:
    """True if key_levels contains at least one non-placeholder level."""
    if not isinstance(key_levels, list):
        return False
    for level in key_levels:
        if isinstance(level, str) and level.strip() and level not in _PLACEHOLDER_LEVELS:
            return True
    return False


def _filter_actionable_trade_ideas(sum_json: dict) -> Tuple[List[dict], str]:
    """
    Keep only trade ideas that have at least one explicit key level (article-grounded).
    ACTIONABLE section must not show generic template entries.
    Returns (filtered list with "text" for display, reason for dev logging).
    """
    sections = sum_json.get("sections", {})
    trade_ideas = sections.get("trade_ideas", [])
    if not isinstance(trade_ideas, list):
        return [], "no_trade_ideas"
    actionable = []
    for idea in trade_ideas:
        if not isinstance(idea, dict):
            continue
        key_levels = idea.get("key_levels", [])
        if not _has_explicit_level(key_levels):
            continue
        # Build display text for PDF/TXT (summary_render uses item.get("text"))
        parts = [f"{idea.get('product', '')}: {idea.get('bias', '')}"]
        if idea.get("catalyst"):
            parts.append(idea["catalyst"])
        if key_levels:
            kl = key_levels if isinstance(key_levels, list) else [key_levels]
            kl_str = ", ".join(str(k) for k in kl if k and str(k).strip() not in _PLACEHOLDER_LEVELS)
            if kl_str:
                parts.append(f"Levels: {kl_str}")
        copy = dict(idea)
        copy["text"] = " | ".join(parts)
        actionable.append(copy)
    reason = f"count={len(actionable)}_of_{len(trade_ideas)}" if trade_ideas else "empty"
    return actionable, reason


def reject_hallucinated_levels(sum_json: dict, source_text: str) -> tuple[bool, str]:
    """
    Post-generation validator: reject price levels that don't exist in source.
    NOTE: Prefer sanitize_key_levels() which DROPS inferred levels instead of rejecting.
    This remains for backward compatibility / secondary checks.
    """
    source_normalized = re.sub(r'\s+', ' ', source_text.lower())
    
    trade_ideas = sum_json.get("sections", {}).get("trade_ideas", [])
    if not isinstance(trade_ideas, list):
        return False, ""

    for idea in trade_ideas:
        if not isinstance(idea, dict):
            continue
        key_levels = idea.get("key_levels", [])
        if not isinstance(key_levels, list):
            continue
        source_quote = idea.get("source_quote")
        search_texts = [_normalize_for_match(source_text)]
        if source_quote:
            search_texts.append(_normalize_for_match(str(source_quote)))

        for level in key_levels:
            if not isinstance(level, str):
                continue
            if level in ["(not provided in inputs)", "no explicit levels provided", ""]:
                continue
            if not _PRICE_PATTERN.search(level):
                continue
            price_matches = _PRICE_PATTERN.findall(level)
            price_values = [
                m for m in price_matches
                if not _is_year_like(m) and not _is_ambiguous_small_num(m)
            ]
            if not price_values:
                continue
            found = any(
                _normalize_for_match(pm) in st for pm in price_values for st in search_texts
            )
            if not found:
                product = idea.get("product", "unknown")
                return True, f"hallucinated_price_level: Product {product} has level '{level}' not found in source"
    return False, ""

def is_low_quality_summary(sum_json: dict) -> tuple[bool, str]:
    """
    Detect low-quality/templated LLM output that should fail.
    
    Returns:
        (is_low_quality: bool, reason: str)
    
    Detects:
    - Repeated bullets (copy-paste behavior)
    - Generic placeholder phrases
    - Too few unique informative bullets
    - Banned filler phrases
    - Section-level repetition (2+ identical bullets in same section)
    """
    sections = sum_json.get("sections", {})
    
    # Collect all text bullets from sections (including new fields)
    all_bullets = []
    section_bullets = {}  # Track bullets per section for repetition check
    
    for key in ["what_moved_today", "what_can_move_tomorrow", "tldr", "what_occurred", "forward_watch", 
                "warnings", "tips_reminders", "cross_asset_impacts", "scenarios"]:
        items = sections.get(key, [])
        section_bullets[key] = []
        if isinstance(items, list):
            for item in items:
                text = _extract_bullet_text(item).lower()
                if text:
                    all_bullets.append(text)
                    section_bullets[key].append(text)
    
    # Also check trade_ideas if they exist
    trade_ideas = sections.get("trade_ideas", [])
    for item in trade_ideas:
        if isinstance(item, dict):
            for field in ["catalyst", "setup", "risk"]:
                text = item.get(field, "").strip().lower()
                if text and text != "(not provided in inputs)":
                    all_bullets.append(text)
            # Check key_levels separately (it's a list)
            key_levels = item.get("key_levels", [])
            if isinstance(key_levels, list):
                for level in key_levels:
                    if isinstance(level, str) and level.strip().lower() != "(not provided in inputs)":
                        all_bullets.append(level.strip().lower())
    
    # Check 1: Too few unique bullets (excluding empty/placeholder content)
    # Note: tldr is required and must have 3 bullets. Other sections can be [].
    # Only fail if there are bullets but they're not unique enough.
    unique_bullets = set(all_bullets)
    
    # Get tldr bullet count
    tldr_bullets = section_bullets.get("tldr", [])
    non_tldr_bullets = [b for b in all_bullets if b not in tldr_bullets]
    
    # If article has tldr + no other content, that's OK (weak article, but valid)
    if len(unique_bullets) > 0 and len(unique_bullets) < 3:
        # Only fail if we have non-tldr content that's too repetitive
        unique_non_tldr = set(non_tldr_bullets)
        if len(unique_non_tldr) > 0 and len(unique_non_tldr) < 3:
            return True, f"too_few_unique_bullets: only {len(unique_bullets)} unique bullets found (excluding tldr)"
    
    # Check 2: Detect repeated bullets (exact duplicates)
    if len(all_bullets) > len(unique_bullets) * 1.5:  # More than 50% duplication
        duplication_rate = (len(all_bullets) - len(unique_bullets)) / len(all_bullets) * 100
        return True, f"excessive_duplication: {duplication_rate:.0f}% of bullets are duplicates"
    
    # Check 2b: Section-level repetition (2+ identical bullets within same section)
    for section_name, bullets in section_bullets.items():
        if len(bullets) >= 2:
            bullet_counts = {}
            for bullet in bullets:
                bullet_counts[bullet] = bullet_counts.get(bullet, 0) + 1
            for bullet, count in bullet_counts.items():
                if count >= 2:
                    return True, f"filler:repeated_bullets_in_{section_name}: '{bullet[:50]}...' appears {count} times"
    
    # Check 3: Banned filler phrases (case-insensitive)
    banned_phrases = [
        "market data pending analysis",
        "monitor key levels and data releases",
    ]
    
    for bullet in all_bullets:
        for phrase in banned_phrases:
            if phrase in bullet:
                return True, f"filler:banned_phrase: '{phrase}' found in bullet"
    
    # Check 4: Generic placeholder phrases
    placeholder_phrases = [
        "pending analysis",
        "monitor key levels",
        "data releases",
        "await further information",
        "to be determined",
        "no specific",
        "not specified",
        "monitor developments",
        "watch for updates",
        "pending clarification",
        "subject to change",
        "more details needed",
        "insufficient information",
        "data not available",
        "no direct trade idea from this article",  # OK for neutral products
    ]
    
    # Count how many bullets are just placeholders
    placeholder_count = 0
    for bullet in all_bullets:
        # Skip the "no direct trade idea" phrase - that's valid for neutral products
        if "no direct trade idea from this article" in bullet:
            continue
        for phrase in placeholder_phrases:
            if phrase in bullet:
                placeholder_count += 1
                break
    
    # If more than 40% of bullets are placeholders, fail
    if len(all_bullets) > 0 and placeholder_count / len(all_bullets) > 0.4:
        placeholder_rate = placeholder_count / len(all_bullets) * 100
        return True, f"excessive_placeholders: {placeholder_rate:.0f}% of bullets are generic placeholders"
    
    # Check 5: Detect suspiciously short bullets (likely low-effort)
    short_bullet_count = sum(1 for b in all_bullets if len(b) < 20)
    if len(all_bullets) > 0 and short_bullet_count / len(all_bullets) > 0.6:
        short_rate = short_bullet_count / len(all_bullets) * 100
        return True, f"excessive_short_bullets: {short_rate:.0f}% of bullets are < 20 chars"
    
    # Passed all checks
    return False, ""

def _summarize_with_quality_retry(
    text: str,
    *,
    meta: dict,
    model: str,
    pdf_path: Path,
    out_dir: Optional[Path],
    apply_format_fix: bool,
    path_manager: Optional[TWIFOPathManager] = None,
) -> dict:
    """
    Run a two-stage quality retry with model escalation.
    """
    debug_path = _sum_debug_path(pdf_path, out_dir=out_dir, path_manager=path_manager)
    if debug_path.exists():
        debug_path.unlink()

    last_quality_reason = ""
    attempt_count = 0
    attempt_models = [model, RETRY_MODEL]

    for attempt_model in attempt_models:
        attempt_count += 1
        print(f"[ATTEMPT {attempt_count}/2] Using model: {attempt_model}")
        
        raw_output_holder: list[str] = []
        meta["model"] = attempt_model

        extra_instructions = None
        max_tokens = BASE_MAX_OUTPUT_TOKENS
        if attempt_count == 2:
            max_tokens = RETRY_MAX_OUTPUT_TOKENS
            extra_instructions = (
                "Prefer [] over generic filler; do not fabricate. "
                "Use distinct wording across sections, grounded in the document."
            )
            print(f"[RETRY] Escalating with stronger prompt and {max_tokens} tokens")

        try:
            sum_json = llm_summarize_to_json(
                text,
                meta=meta,
                model=attempt_model,
                temperature=0.1,
                max_output_tokens=max_tokens,
                extra_instructions=extra_instructions,
                raw_output=raw_output_holder,
            )
        except Exception as e:
            print(f"[ERROR] LLM call failed on attempt {attempt_count}: {e}")
            if attempt_count < len(attempt_models):
                print(f"[RETRY] Will try next model...")
                continue
            raise

        if apply_format_fix:
            try:
                from format_validator import validate_article_summary, fix_summary_format
                is_valid, violations = validate_article_summary(sum_json)
                if violations:
                    print(f"[FORMAT] Fixing {len(violations)} format issues...")
                    sum_json = fix_summary_format(sum_json)
            except ImportError:
                pass  # Validator not available, skip

        _normalize_sections_in_place(sum_json)

        # Layer 2: Sanitize price levels (drop inferred, keep only explicit in source)
        dropped_levels = sanitize_key_levels(sum_json, text)
        extraction = sum_json.get("extraction", {})
        if dropped_levels:
            extraction["dropped_inferred_level_count"] = len(dropped_levels)
            extraction["dropped_inferred_level_details"] = [
                {"field": d["field"], "product": d["product"], "reason": d["reason"]}
                for d in dropped_levels[:20]
            ]

        # Layer 3: ACTIONABLE = only trade ideas with explicit levels (no generic template)
        actionable_list, actionable_reason = _filter_actionable_trade_ideas(sum_json)
        sum_json.setdefault("sections", {})["trade_ideas"] = actionable_list
        extraction["actionable_included_reason"] = actionable_reason
        extraction["content_hash"] = _content_hash(text)
        sum_json["extraction"] = extraction

        if os.getenv("DEV_LOGGING") == "1":
            print(
                f"[DEV_LOGGING] products_inferred_reason={extraction.get('products_inferred_reason', '')!r} "
                f"actionable_included_reason={actionable_reason!r}"
            )

        # Layer 1: Generic quality checks
        is_low_quality, quality_reason = is_low_quality_summary(sum_json)

        if not is_low_quality:
            print(f"[QUALITY GATE] Passed on attempt {attempt_count}")
            extraction = sum_json.get("extraction", {})
            extraction["attempt_count"] = attempt_count
            extraction["quality_reason"] = ""
            sum_json["extraction"] = extraction

            # Step D.5: Post-LLM deterministic numeric verifier
            sum_json = verify_and_scrub_numerics(sum_json, text)

            # Step D.6: Similarity guard (at most one retry, deterministic)
            sum_json = similarity_guard(
                sum_json,
                source_text=text,
                meta=meta,
                model=attempt_model,
                path_manager=path_manager,
                pdf_path=pdf_path,
            )

            # Step D.7: Critic pass (structural cleanup — dedup, quotes, numerics)
            sum_json = critic_pass(sum_json, text)

            # --- Provider validation & detection metadata (wire validate_provider) ---
            try:
                raw_provider = sum_json.get("meta", {}).get("provider", "Unknown")
                from twifo_prompts.prompts.article_prompts import validate_provider

                validated_provider, confidence = validate_provider(raw_provider)

                sum_json.setdefault("meta", {})["provider"] = validated_provider
                sum_json["meta"]["provider_detection"] = {
                    "method": "ai_extraction" if confidence > 0 else "fallback",
                    "confidence": int(confidence),
                    "original_value": raw_provider,
                }
            except Exception as _:
                # If validation fails, keep existing provider and do not block summarization
                pass

            return sum_json

        print(f"[QUALITY GATE] Failed on attempt {attempt_count}: {quality_reason}")
        last_quality_reason = quality_reason
        bullet_counts = _count_section_bullets(sum_json.get("sections", {}))
        raw_text = raw_output_holder[0] if raw_output_holder else ""
        _write_debug_artifact(
            debug_path,
            model=attempt_model,
            raw_output=raw_text,
            bullet_counts=bullet_counts,
            quality_reason=quality_reason,
            attempt=attempt_count,
        )
        print(f"[DEBUG] Debug artifact written to: {debug_path}")

    print(f"[FAIL] All attempts exhausted. Returning failure stub.")
    extraction = meta.get("extraction", {})
    extraction["attempt_count"] = attempt_count
    extraction["quality_reason"] = last_quality_reason
    meta["model"] = RETRY_MODEL
    return _failed_stub(
        pdf_path,
        reason=f"low_quality_output: {last_quality_reason}",
        extraction=extraction,
        meta=meta,
    )


def render_sum_txt(sum_json: dict) -> str:
    """
    Render summary in new trader-focused format (article template).
    Handles both successful summaries and failed extractions.
    """
    meta = sum_json.get("meta", {})
    title = meta.get("title", "")
    extraction = sum_json.get("extraction", {})
    
    # Check if extraction failed
    if extraction.get("status") != "ok":
        reason = extraction.get("reason", "unknown error")
        return f"""{title}

SUMMARY UNAVAILABLE

Extraction Status: FAILED
Reason: {reason}

This document could not be processed. Possible causes:
- Image-only PDF requiring OCR
- Low-quality extraction
- Templated/low-information LLM output
- Insufficient readable text

No summary will be generated for this document.
"""
    
    # Normal rendering for successful summaries
    s = sum_json.get("sections", {})
    
    def bullet_lines(items: list):
        """Format bullets."""
        out = []
        for it in items:
            if isinstance(it, dict):
                text = it.get('text', '').strip()
                if text:
                    out.append(f"• {text}")
            else:
                text = str(it).strip()
                if text:
                    out.append(f"• {text}")
        return "\n".join(out) if out else "• (none)"
    
    # TL;DR (max 3)
    tldr_items = s.get("tldr", [])[:3]
    tldr_text = bullet_lines(tldr_items)
    
    # TRADE IDEAS - content-dependent (only products with explicit levels; order preserved)
    trade_ideas = s.get("trade_ideas", [])
    trade_ideas_text = []
    
    priority_products = ["ES", "NQ", "GC", "SI", "VIX"]
    trade_by_product = {item.get("product"): item for item in trade_ideas if isinstance(item, dict) and item.get("product")}
    other_products = sorted([p for p in trade_by_product.keys() if p not in priority_products])
    
    # Process priority products in exact order
    for product in priority_products:
        if product not in trade_by_product:
            continue  # Skip if not present
        
        item = trade_by_product[product]
        bias = item.get("bias", "Neutral")
        catalyst = item.get("catalyst", "")
        setup = item.get("setup", "")
        key_levels = item.get("key_levels", "")
        risk = item.get("risk", "")
        time_horizon = item.get("time_horizon", "")
        
        if bias == "Neutral" and ("No direct trade idea" in catalyst or not catalyst.strip()):
            trade_ideas_text.append(f"{product}: No direct trade idea from this article")
        else:
            trade_ideas_text.append(f"{product}")
            trade_ideas_text.append(f"  Bias: {bias}")
            if catalyst:
                trade_ideas_text.append(f"  Catalyst: {catalyst}")
            if setup:
                trade_ideas_text.append(f"  Setup: {setup}")
            if key_levels:
                trade_ideas_text.append(f"  Key Levels: {key_levels}")
            if risk:
                trade_ideas_text.append(f"  Risk: {risk}")
            if time_horizon:
                trade_ideas_text.append(f"  Time Horizon: {time_horizon}")
    
    # Process other products
    for product in other_products:
        item = trade_by_product[product]
        bias = item.get("bias", "Neutral")
        catalyst = item.get("catalyst", "")
        setup = item.get("setup", "")
        key_levels = item.get("key_levels", "")
        risk = item.get("risk", "")
        time_horizon = item.get("time_horizon", "")
        
        trade_ideas_text.append(f"{product}")
        trade_ideas_text.append(f"  Bias: {bias}")
        if catalyst:
            trade_ideas_text.append(f"  Catalyst: {catalyst}")
        if setup:
            trade_ideas_text.append(f"  Setup: {setup}")
        if key_levels:
            trade_ideas_text.append(f"  Key Levels: {key_levels}")
        if risk:
            trade_ideas_text.append(f"  Risk: {risk}")
        if time_horizon:
            trade_ideas_text.append(f"  Time Horizon: {time_horizon}")
    
    trade_ideas_output = "\n".join(trade_ideas_text) if trade_ideas_text else "• (none)"
    
    # STOCKS
    stocks_items = s.get("stocks", [])[:8]
    stocks_text = bullet_lines(stocks_items)
    
    # OTHER FUTURES
    other_futures_items = s.get("other_futures", [])
    other_futures_text = bullet_lines(other_futures_items)
    
    # FOREX
    forex_items = s.get("forex", [])[:6]
    forex_text = bullet_lines(forex_items)
    
    # OTHER
    other_items = s.get("other", [])
    other_text = bullet_lines(other_items)
    
    # FINGERPRINT QUOTES (v1.2)
    fingerprint_quotes = sum_json.get("fingerprint_quotes", [])
    fp_text = ""
    if fingerprint_quotes:
        fp_lines = [f'  "{q}"' for q in fingerprint_quotes if isinstance(q, str)]
        fp_text = "\nFINGERPRINT QUOTES\n" + "\n".join(fp_lines) if fp_lines else ""
    
    # CHART OBSERVATIONS (v1.2)
    chart_obs = sum_json.get("chart_observations", [])
    chart_text = ""
    if chart_obs:
        chart_text = "\nCHART OBSERVATIONS\n" + bullet_lines(chart_obs)
    
    return f"""{title}

TL;DR
{tldr_text}

TRADE IDEAS
{trade_ideas_output}

STOCKS
{stocks_text}

OTHER FUTURES
{other_futures_text}

FOREX
{forex_text}

OTHER
{other_text}
{fp_text}{chart_text}
"""

# =========================
# Extraction with caching (SHA256-keyed)
# =========================

# OCR thresholds
MIN_TEXT_CHARS_FOR_EXTRACTION = 1500  # Minimum chars to consider extraction successful
OCR_THRESHOLD_CHARS = 500  # If extraction produces less than this, try OCR
OCR_THRESHOLD_PAGES_RATIO = 0.3  # If less than 30% of pages have text, try OCR


def compute_pdf_sha256(pdf_path: Path) -> str:
    """Compute SHA256 hash of PDF file for cache key."""
    sha256 = hashlib.sha256()
    with open(pdf_path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_extraction_cache(pdf_path: Path, path_manager: Optional[TWIFOPathManager] = None) -> Optional[Tuple[str, dict]]:
    """
    Load cached extraction if available and valid.
    
    Returns:
        Tuple of (text, extraction_metadata) or None if cache invalid/missing
    """
    if not PATH_MANAGER_AVAILABLE or not path_manager:
        return None
    
    basename = pdf_path.stem
    extracted_txt_path = path_manager.artifact_path(basename, 'extracted.txt')
    extraction_json_path = path_manager.artifact_path(basename, 'extraction.json')
    
    # Check if cache files exist
    if not extracted_txt_path.exists() or not extraction_json_path.exists():
        return None
    
    try:
        # Load extraction metadata
        with open(extraction_json_path, 'r', encoding='utf-8') as f:
            extraction_data = json.load(f)
        
        # Verify PDF hasn't changed by comparing SHA256
        cached_sha256 = extraction_data.get('pdf_sha256')
        if not cached_sha256:
            print("[CACHE] No pdf_sha256 in cache, invalidating")
            return None
        
        current_sha256 = compute_pdf_sha256(pdf_path)
        if cached_sha256 != current_sha256:
            print(f"[CACHE] PDF changed (hash mismatch), invalidating cache")
            return None
        
        # Load extracted text
        with open(extracted_txt_path, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Reconstruct extraction metadata for backward compatibility
        extraction_meta = {
            'status': extraction_data.get('status', 'ok'),
            'method_used': extraction_data.get('method_used', 'cached'),
            'chars_total': extraction_data.get('chars_total', len(text)),
            'pages_with_text': extraction_data.get('pages_with_text', 0),
            'errors': extraction_data.get('errors', []),
        }
        
        print(f"[CACHE HIT] Reusing extraction from cache (pdf_sha256={current_sha256[:16]}...)")
        return text, extraction_meta
        
    except Exception as e:
        print(f"[CACHE] Error loading cache: {e}")
        return None


def save_extraction_cache(
    pdf_path: Path,
    text: str,
    extraction_meta: dict,
    pdf_sha256: str,
    duration_ms: int,
    path_manager: Optional[TWIFOPathManager] = None
) -> None:
    """
    Save extraction to cache for future reuse.
    
    Args:
        pdf_path: Path to PDF file
        text: Extracted text
        extraction_meta: Extraction metadata dict
        pdf_sha256: SHA256 hash of PDF
        duration_ms: Extraction duration in milliseconds
        path_manager: Path manager for new layout
    """
    if not PATH_MANAGER_AVAILABLE or not path_manager:
        return
    
    basename = pdf_path.stem
    extracted_txt_path = path_manager.artifact_path(basename, 'extracted.txt')
    extraction_json_path = path_manager.artifact_path(basename, 'extraction.json')
    
    try:
        # Ensure artifact directory exists
        path_manager.ensure_artifact_dir(basename)
        
        # Write extracted text
        _write_txt(extracted_txt_path, text)
        
        # Compute extraction quality and status
        quality_score, status = compute_extraction_quality(extraction_meta)
        
        # Build extraction.json with full metadata
        extraction_data = {
            'pdf_sha256': pdf_sha256,
            'method_used': extraction_meta.get('method_used', 'unknown'),
            'status': status,  # Use computed status
            'extraction_quality_0_100': quality_score,  # Add quality score
            'pages_total': extraction_meta.get('pages_total', 0),
            'pages_with_text': extraction_meta.get('pages_with_text', 0),
            'chars_total': len(text),
            'ocr_used': extraction_meta.get('ocr_used', False),
            'errors': extraction_meta.get('errors', []),
            'created_at': _iso_now(),
            'duration_ms': duration_ms,
        }
        
        # Add degradation reasons if present
        if 'degradation_reasons' in extraction_meta:
            extraction_data['degradation_reasons'] = extraction_meta['degradation_reasons']
        
        _write_json(extraction_json_path, extraction_data)
        print(f"[CACHE] Saved extraction cache: {extracted_txt_path.name} (quality={quality_score}, status={status})")
        
    except Exception as e:
        print(f"[CACHE] Error saving cache: {e}")


def extract_text(pdf_path: Path, path_manager: Optional[TWIFOPathManager] = None) -> Tuple[str, dict]:
    """
    Extract text from PDF with caching support.
    
    Tries methods in order:
    1. Check cache (if path_manager provided)
    2. pypdf
    3. pdfplumber
    4. pymupdf
    
    Args:
        pdf_path: Path to PDF file
        path_manager: Optional path manager for caching
    
    Returns:
        Tuple of (extracted_text, extraction_metadata)
    """
    import time
    start_time = time.time()
    
    # Try to load from cache first
    cached_result = load_extraction_cache(pdf_path, path_manager)
    if cached_result is not None:
        return cached_result
    
    # Compute PDF SHA256 for cache key
    try:
        pdf_sha256 = compute_pdf_sha256(pdf_path)
    except Exception as e:
        print(f"[WARN] Could not compute PDF SHA256: {e}")
        pdf_sha256 = None
    
    errors: List[str] = []
    pages_total = 0

    # pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        pages_total = len(reader.pages)
        parts = []
        pages_with_text = 0
        for p in reader.pages:
            t = (p.extract_text() or "").strip()
            if t:
                pages_with_text += 1
                parts.append(t)
        text = "\n\n".join(parts).strip()
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        extraction_meta = {
            "status": "ok",  # Will be recomputed with quality
            "method_used": "pypdf",
            "chars_total": len(text),
            "pages_total": pages_total,
            "pages_with_text": pages_with_text,
            "errors": errors,
            "ocr_used": False,
        }
        
        # Compute extraction quality and status
        quality_score, status = compute_extraction_quality(extraction_meta)
        extraction_meta['extraction_quality_0_100'] = quality_score
        extraction_meta['status'] = status
        
        # Save to cache if successful
        if pdf_sha256 and path_manager:
            save_extraction_cache(pdf_path, text, extraction_meta, pdf_sha256, duration_ms, path_manager)
        
        return text, extraction_meta
    except Exception as e:
        errors.append(f"pypdf failed: {e}")

    # pdfplumber
    try:
        import pdfplumber
        parts = []
        pages_with_text = 0
        with pdfplumber.open(str(pdf_path)) as pdf:
            if not pages_total:
                pages_total = len(pdf.pages)
            for page in pdf.pages:
                t = (page.extract_text() or "").strip()
                if t:
                    pages_with_text += 1
                    parts.append(t)
        text = "\n\n".join(parts).strip()
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        extraction_meta = {
            "status": "ok",
            "method_used": "pdfplumber",
            "chars_total": len(text),
            "pages_total": pages_total,
            "pages_with_text": pages_with_text,
            "errors": errors,
            "ocr_used": False,
        }
        
        # Compute extraction quality and status
        quality_score, status = compute_extraction_quality(extraction_meta)
        extraction_meta['extraction_quality_0_100'] = quality_score
        extraction_meta['status'] = status
        
        # Save to cache if successful
        if pdf_sha256 and path_manager:
            save_extraction_cache(pdf_path, text, extraction_meta, pdf_sha256, duration_ms, path_manager)
        
        return text, extraction_meta
    except Exception as e:
        errors.append(f"pdfplumber failed: {e}")

    # pymupdf
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        if not pages_total:
            pages_total = doc.page_count
        parts = []
        pages_with_text = 0
        for i in range(doc.page_count):
            t = (doc.load_page(i).get_text("text") or "").strip()
            if t:
                pages_with_text += 1
                parts.append(t)
        doc.close()
        text = "\n\n".join(parts).strip()
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        extraction_meta = {
            "status": "ok",
            "method_used": "pymupdf",
            "chars_total": len(text),
            "pages_total": pages_total,
            "pages_with_text": pages_with_text,
            "errors": errors,
            "ocr_used": False,
        }
        
        # Compute extraction quality and status
        quality_score, status = compute_extraction_quality(extraction_meta)
        extraction_meta['extraction_quality_0_100'] = quality_score
        extraction_meta['status'] = status
        
        # Save to cache if successful
        if pdf_sha256 and path_manager:
            save_extraction_cache(pdf_path, text, extraction_meta, pdf_sha256, duration_ms, path_manager)
        
        return text, extraction_meta
    except Exception as e:
        errors.append(f"pymupdf failed: {e}")

    # All extraction methods failed
    duration_ms = int((time.time() - start_time) * 1000)
    
    extraction_meta = {
        "status": "failed",
        "method_used": "failed",
        "chars_total": 0,
        "pages_total": pages_total,
        "pages_with_text": 0,
        "errors": errors,
        "ocr_used": False,
    }
    
    # Compute extraction quality and status (will be 'failed')
    quality_score, status = compute_extraction_quality(extraction_meta)
    extraction_meta['extraction_quality_0_100'] = quality_score
    extraction_meta['status'] = status
    
    # Save failed extraction to cache to avoid retrying
    if pdf_sha256 and path_manager:
        save_extraction_cache(pdf_path, "", extraction_meta, pdf_sha256, duration_ms, path_manager)
    
    return "", extraction_meta

# =========================
# OCR (external only - NEVER for rollups/internal)
# =========================
def ocr_to_text(pdf_path: Path, dpi: int = 300, max_pages: Optional[int] = None, path_manager: Optional[TWIFOPathManager] = None) -> Tuple[str, dict]:
    """
    OCR to TEXT using PyMuPDF render + pytesseract.
    This avoids ocrmypdf/ghostscript. Requires:
      pip install pymupdf pillow pytesseract
    
    ZERO-OCR RULE: This is ONLY for external PDFs. Rollups NEVER use OCR.
    
    Args:
        pdf_path: Path to PDF file
        dpi: DPI for rendering (default 300)
        max_pages: Maximum pages to OCR (None = all pages)
        path_manager: Optional path manager for caching
    
    Returns:
        Tuple of (extracted_text, extraction_metadata)
    """
    import time
    start_time = time.time()
    
    errors = []
    try:
        import fitz
    except Exception as e:
        return "", {"status":"failed","method_used":"ocr_pymupdf+tesseract","chars_total":0,"pages_with_text":0,"errors":[f"pymupdf missing: {e}"], "ocr_used": True}

    try:
        import pytesseract
        from PIL import Image
        import io
    except Exception as e:
        return "", {"status":"failed","method_used":"ocr_pymupdf+tesseract","chars_total":0,"pages_with_text":0,"errors":[f"pytesseract/pillow missing: {e}"], "ocr_used": True}

    # Compute PDF SHA256 for cache
    try:
        pdf_sha256 = compute_pdf_sha256(pdf_path)
    except Exception as e:
        print(f"[WARN] Could not compute PDF SHA256: {e}")
        pdf_sha256 = None

    doc = fitz.open(str(pdf_path))
    n = doc.page_count
    pages_total = n
    last = n if max_pages is None else min(n, max_pages)
    chunks = []
    pages_with_text = 0

    for i in range(last):
        page = doc.load_page(i)
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        t = (pytesseract.image_to_string(img) or "").strip()
        if t:
            pages_with_text += 1
            chunks.append(t)

    doc.close()
    text = "\n\n".join(chunks).strip()
    
    duration_ms = int((time.time() - start_time) * 1000)
    
    extraction_meta = {
        "status": "ok" if text else "failed",
        "method_used": "ocr_pymupdf+tesseract",
        "chars_total": len(text),
        "pages_total": pages_total,
        "pages_with_text": pages_with_text,
        "errors": errors,
        "ocr_used": True,
    }
    
    # Compute extraction quality and status
    quality_score, status = compute_extraction_quality(extraction_meta)
    extraction_meta['extraction_quality_0_100'] = quality_score
    extraction_meta['status'] = status
    
    # Save OCR result to cache
    if pdf_sha256 and path_manager:
        save_extraction_cache(pdf_path, text, extraction_meta, pdf_sha256, duration_ms, path_manager)
    
    return text, extraction_meta

# =========================
# Extraction Quality Scoring
# =========================

# Quality thresholds
QUALITY_EXCELLENT_CHARS = 10000      # > 10k chars = excellent
QUALITY_GOOD_CHARS = 5000            # > 5k chars = good
QUALITY_DEGRADED_CHARS = 1500        # < 1.5k chars = degraded
QUALITY_DEGRADED_PAGE_RATIO = 0.4   # < 40% pages with text = degraded

# OCR penalty (OCR is less reliable)
OCR_QUALITY_PENALTY = 20             # -20 points for OCR usage


def compute_extraction_quality(extraction_meta: dict) -> tuple[int, str]:
    """
    Compute extraction_quality_0_100 score based on measurable signals.
    
    Scoring factors:
    - pages_with_text ratio (0-40 points)
    - chars_total (0-40 points)
    - OCR penalty (-20 points)
    - Error penalty (0-20 points deduction)
    
    Args:
        extraction_meta: Extraction metadata dict with:
            - pages_total, pages_with_text, chars_total
            - ocr_used, errors
    
    Returns:
        Tuple of (quality_score_0_100, status)
        where status is "ok" | "degraded" | "failed"
    """
    pages_total = extraction_meta.get('pages_total', 0)
    pages_with_text = extraction_meta.get('pages_with_text', 0)
    chars_total = extraction_meta.get('chars_total', 0)
    ocr_used = extraction_meta.get('ocr_used', False)
    errors = extraction_meta.get('errors', [])
    method_used = extraction_meta.get('method_used', 'unknown')
    
    score = 0
    
    # 1. Page coverage score (0-40 points)
    if pages_total > 0:
        page_ratio = pages_with_text / pages_total
        # Linear scaling: 0% -> 0 pts, 100% -> 40 pts
        page_score = min(40, int(page_ratio * 40))
        score += page_score
    else:
        # No pages detected = likely a single-page or corrupt PDF
        page_score = 0 if chars_total < 100 else 20  # Give some credit if we got text
        score += page_score
    
    # 2. Character count score (0-40 points)
    if chars_total >= QUALITY_EXCELLENT_CHARS:
        char_score = 40
    elif chars_total >= QUALITY_GOOD_CHARS:
        # Linear interpolation: 5k-10k -> 30-40 pts
        char_score = 30 + int((chars_total - QUALITY_GOOD_CHARS) / (QUALITY_EXCELLENT_CHARS - QUALITY_GOOD_CHARS) * 10)
    elif chars_total >= QUALITY_DEGRADED_CHARS:
        # Linear interpolation: 1.5k-5k -> 15-30 pts
        char_score = 15 + int((chars_total - QUALITY_DEGRADED_CHARS) / (QUALITY_GOOD_CHARS - QUALITY_DEGRADED_CHARS) * 15)
    elif chars_total >= 500:
        # Linear interpolation: 500-1.5k -> 5-15 pts
        char_score = 5 + int((chars_total - 500) / (QUALITY_DEGRADED_CHARS - 500) * 10)
    else:
        # < 500 chars = very low score
        char_score = max(0, int(chars_total / 100))  # 0-5 pts
    
    score += char_score
    
    # 3. OCR penalty (-20 points)
    if ocr_used:
        score -= OCR_QUALITY_PENALTY
    
    # 4. Error penalty (0-20 points deduction)
    if errors:
        # Deduct 5 points per error, max 20 points
        error_penalty = min(20, len(errors) * 5)
        score -= error_penalty
    
    # 5. Method-specific adjustments
    if method_used == 'failed':
        score = max(0, min(score, 10))  # Cap at 10 for failed extractions
    
    # Clamp to 0-100
    score = max(0, min(100, score))
    
    # Determine status based on score and hard rules
    status = determine_extraction_status(extraction_meta, score)
    
    return score, status


def determine_extraction_status(extraction_meta: dict, quality_score: int) -> str:
    """
    Determine extraction status: ok | degraded | failed.
    
    Rules:
    - failed: method_used == "failed" OR chars_total < 100 OR truly fatal errors
    - degraded: 
        - quality_score < 40 OR
        - pages_with_text/pages_total < 0.4 OR
        - chars_total < 1500 OR
        - Multiple errors OR benign parser warnings
    - ok: Everything else
    
    Benign parser warnings (e.g. "invalid xref table") do NOT cause "failed" status
    if the extraction produced substantial usable text (chars_total >= 1500 and
    pages_with_text/pages_total >= 0.4). They may still cause "degraded" status
    if other quality metrics are low.
    
    Args:
        extraction_meta: Extraction metadata
        quality_score: Computed quality score (0-100)
    
    Returns:
        Status string: "ok" | "degraded" | "failed"
    """
    pages_total = extraction_meta.get('pages_total', 0)
    pages_with_text = extraction_meta.get('pages_with_text', 0)
    chars_total = extraction_meta.get('chars_total', 0)
    errors = extraction_meta.get('errors', [])
    method_used = extraction_meta.get('method_used', 'unknown')
    
    # FAILED: Complete extraction failure
    if method_used == 'failed':
        return 'failed'
    
    if chars_total < 100:
        return 'failed'
    
    # Check for truly fatal errors that indicate complete failure
    # (Only when extraction actually failed — i.e., low text output)
    fatal_keywords = ['missing', 'corrupt', 'unreadable']
    benign_keywords = ['invalid']  # Parser warnings that don't prevent extraction
    
    # If extraction produced substantial text, benign warnings are not fatal
    extraction_succeeded = (
        chars_total >= QUALITY_DEGRADED_CHARS and  # >= 1500 chars
        (pages_total == 0 or pages_with_text / pages_total >= QUALITY_DEGRADED_PAGE_RATIO)  # >= 40% coverage
    )
    
    has_benign_errors = False
    for error in errors:
        error_lower = str(error).lower()
        
        # Check for truly fatal keywords
        if any(keyword in error_lower for keyword in fatal_keywords):
            return 'failed'
        
        # Check for benign keywords (only fatal if extraction didn't succeed)
        if any(keyword in error_lower for keyword in benign_keywords):
            if not extraction_succeeded:
                # Benign error + low output = failed
                return 'failed'
            else:
                # Benign error + good output = note it for degraded check
                has_benign_errors = True
    
    # DEGRADED: Low quality but usable
    degraded_reasons = []
    
    # Rule 1: Low page coverage
    if pages_total > 0:
        page_ratio = pages_with_text / pages_total
        if page_ratio < QUALITY_DEGRADED_PAGE_RATIO:
            degraded_reasons.append(f"low_page_coverage ({page_ratio:.1%})")
    
    # Rule 2: Insufficient text
    if chars_total < QUALITY_DEGRADED_CHARS:
        degraded_reasons.append(f"low_char_count ({chars_total})")
    
    # Rule 3: Low quality score
    if quality_score < 40:
        degraded_reasons.append(f"low_quality_score ({quality_score})")
    
    # Rule 4: Multiple errors or benign parser warnings
    if len(errors) >= 2 or has_benign_errors:
        degraded_reasons.append(f"parser_warnings ({len(errors)})")
    
    if degraded_reasons:
        # Store degradation reasons for debugging
        extraction_meta['degradation_reasons'] = degraded_reasons
        return 'degraded'
    
    # OK: Good quality
    return 'ok'

# =========================
# Step D.5: Post-LLM Numeric Verifier
# =========================

# Regex to extract numeric tokens from strings.
# Matches: integers, decimals, comma-separated numbers, percentages, dates (YYYYMMDD, YYYY-MM-DD).
_NUMERIC_TOKEN_RE = re.compile(
    r"""
    -?                          # optional leading negative
    (?:
        \d{1,3}(?:,\d{3})+     # comma-separated: 1,234 or 1,234,567
        (?:\.\d+)?              # optional decimal part
    |
        \d+\.\d+               # plain decimal: 3.14
    |
        \d+                    # plain integer: 42
    )
    \s?%?                      # optional trailing percent (with optional space)
    """,
    re.VERBOSE,
)

# Keys to skip during numeric extraction (metadata, not LLM content).
_NUMERIC_SKIP_KEYS = frozenset({
    "schema_version", "generated_at_iso", "prompt_sha256", "prompt_version",
    "code_git_commit", "pdf_sha256", "original_pdf_sha256", "content_hash",
    "created_at", "duration_ms", "attempt_count", "extraction_quality_0_100",
    "pages_total", "pages_with_text", "chars_total",
    "products_inferred_reason", "actionable_included_reason",
    "dropped_inferred_level_count", "quality_reason",
    "original_pdf_path", "prompt_source_file",
    # Score fields are set by the LLM but are not "claims about the article"
    "score_0_10", "summary_score_0_10", "chart_score_0_3",
    "confidence_0_100",
})

# Keys whose values are numeric_claims entries themselves (don't double-count).
_NUMERIC_CLAIMS_KEY = "numeric_claims"

# Paths from which we do NOT accept auto-registered numeric_claims (meta/UI/identifiers).
_AUTO_REGISTER_EXCLUDED_PATH_PREFIXES = ("meta.title", "meta.model", "ui.")


def _extract_numerics_from_whitelist_paths(sum_json: dict) -> list[dict]:
    """
    Extract numeric tokens only from whitelist paths: sections.*[].text,
    meta.theme, fingerprint_quotes[]. All other paths (meta.title, meta.model,
    ui.*, filenames, ids, etc.) are not scanned.
    Returns list of {token, normalized, path} dicts.
    """
    results: list[dict] = []

    # sections.<section_name>[i].text
    sections = sum_json.get("sections") or {}
    if isinstance(sections, dict):
        for sec_name, items in sections.items():
            if not isinstance(items, list):
                continue
            for idx, item in enumerate(items):
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        path = f"sections.{sec_name}[{idx}].text"
                        for token in _extract_numeric_tokens_from_value(text):
                            results.append({
                                "token": token,
                                "normalized": _normalize_numeric(token),
                                "path": path,
                            })
                elif isinstance(item, str):
                    path = f"sections.{sec_name}[{idx}]"
                    for token in _extract_numeric_tokens_from_value(item):
                        results.append({
                            "token": token,
                            "normalized": _normalize_numeric(token),
                            "path": path,
                        })

    # meta.theme (scalar string)
    meta = sum_json.get("meta") or {}
    if isinstance(meta, dict):
        theme = meta.get("theme")
        if isinstance(theme, str):
            for token in _extract_numeric_tokens_from_value(theme):
                results.append({
                    "token": token,
                    "normalized": _normalize_numeric(token),
                    "path": "meta.theme",
                })

    # fingerprint_quotes[]
    fp_quotes = sum_json.get("fingerprint_quotes") or []
    if isinstance(fp_quotes, list):
        for idx, q in enumerate(fp_quotes):
            if isinstance(q, str):
                for token in _extract_numeric_tokens_from_value(q):
                    results.append({
                        "token": token,
                        "normalized": _normalize_numeric(token),
                        "path": f"fingerprint_quotes[{idx}]",
                    })

    return results


def _scrub_numeric_from_whitelist_paths(sum_json: dict, token: str, normalized: str) -> dict:
    """
    Remove a numeric token only from whitelist paths (sections.*[].text,
    meta.theme, fingerprint_quotes[]). Does not modify meta.title, meta.model,
    ui.*, or any other excluded path.
    Returns modified sum_json (mutates in place where possible).
    """
    # sections.*[].text
    sections = sum_json.get("sections") or {}
    if isinstance(sections, dict):
        for sec_name, items in list(sections.items()):
            if not isinstance(items, list):
                continue
            for idx, item in enumerate(items):
                if isinstance(item, dict) and "text" in item:
                    text = item.get("text")
                    if isinstance(text, str) and (token in text or normalized.replace("%", "") in text.replace(",", "")):
                        sections[sec_name][idx] = dict(item)
                        sections[sec_name][idx]["text"] = _scrub_token_from_string(text, token)
                elif isinstance(item, str) and (token in item or normalized.replace("%", "") in item.replace(",", "")):
                    sections[sec_name][idx] = _scrub_token_from_string(item, token)

    # meta.theme
    meta = sum_json.get("meta") or {}
    if isinstance(meta, dict) and "theme" in meta:
        theme = meta.get("theme")
        if isinstance(theme, str) and (token in theme or normalized.replace("%", "") in theme.replace(",", "")):
            meta["theme"] = _scrub_token_from_string(theme, token)

    # fingerprint_quotes[]
    fp_quotes = sum_json.get("fingerprint_quotes") or []
    if isinstance(fp_quotes, list):
        new_fp: list[str] = []
        changed = False
        for q in fp_quotes:
            if isinstance(q, str) and (token in q or normalized.replace("%", "") in q.replace(",", "")):
                new_fp.append(_scrub_token_from_string(q, token))
                changed = True
            else:
                new_fp.append(q)
        if changed:
            sum_json["fingerprint_quotes"] = new_fp

    return sum_json


def _is_auto_register_excluded_path(context: str) -> bool:
    """True if context indicates an excluded path (meta.title, meta.model, ui.*)."""
    if not isinstance(context, str) or not context.startswith("auto-registered from "):
        return False
    path = context.replace("auto-registered from ", "").strip()
    return any(path.startswith(prefix) for prefix in _AUTO_REGISTER_EXCLUDED_PATH_PREFIXES)


def _normalize_numeric(raw: str) -> str:
    """
    Normalize a numeric token for fuzzy matching.

    Strips commas, collapses whitespace, normalizes percent spacing.
    '4,250.50' -> '4250.50', '4.25 %' -> '4.25%', ' 1,500 ' -> '1500'
    """
    s = raw.strip()
    s = s.replace(",", "")
    s = re.sub(r"\s+", "", s)  # collapse all whitespace
    # Normalize trailing percent
    s = s.rstrip("%").rstrip() + ("%" if "%" in raw else "")
    return s


def _extract_numeric_tokens_from_value(value: str) -> list[str]:
    """Extract all numeric tokens from a single string value."""
    return _NUMERIC_TOKEN_RE.findall(value)


def _walk_json_for_numerics(
    obj: object,
    *,
    path: str = "",
    skip_keys: frozenset[str] = _NUMERIC_SKIP_KEYS,
    claims_key: str = _NUMERIC_CLAIMS_KEY,
) -> list[dict]:
    """
    Recursively walk a JSON-like object and extract every numeric token.

    Returns list of {token, normalized, path} dicts.
    Skips metadata keys and the numeric_claims array itself.
    """
    results: list[dict] = []

    if isinstance(obj, dict):
        for key, val in obj.items():
            child_path = f"{path}.{key}" if path else key
            # Skip metadata keys
            if key in skip_keys:
                continue
            # Skip the numeric_claims registry itself
            if key == claims_key:
                continue
            results.extend(
                _walk_json_for_numerics(val, path=child_path, skip_keys=skip_keys, claims_key=claims_key)
            )
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            child_path = f"{path}[{idx}]"
            results.extend(
                _walk_json_for_numerics(item, path=child_path, skip_keys=skip_keys, claims_key=claims_key)
            )
    elif isinstance(obj, str):
        for token in _extract_numeric_tokens_from_value(obj):
            results.append({
                "token": token,
                "normalized": _normalize_numeric(token),
                "path": path,
            })
    # int/float: convert to string and extract
    elif isinstance(obj, (int, float)):
        token_str = str(obj)
        # Skip 0 and 1 (trivially common, not "claims")
        if obj not in (0, 1, 0.0, 1.0, True, False):
            results.append({
                "token": token_str,
                "normalized": _normalize_numeric(token_str),
                "path": path,
            })

    return results


def _build_source_index(source_text: str) -> set[str]:
    """
    Build a set of normalized numeric tokens found in the source text.

    Used for O(1) lookup during verification.
    """
    raw_tokens = _NUMERIC_TOKEN_RE.findall(source_text)
    return {_normalize_numeric(t) for t in raw_tokens}


def _verify_token_in_source(normalized: str, source_index: set[str], source_text: str) -> bool:
    """
    Check if a normalized numeric token appears in the source.

    Strategy:
    1. Direct set lookup (fast path).
    2. Substring search on the raw source after stripping commas from both.
    """
    # Fast path: exact normalized match
    if normalized in source_index:
        return True

    # Fallback: substring search with normalization
    bare = normalized.replace(",", "").replace("%", "").strip()
    if not bare:
        return False

    # Search in comma-stripped source
    source_bare = source_text.replace(",", "")
    if bare in source_bare:
        return True

    return False


def _scrub_token_from_string(text: str, token: str) -> str:
    """
    Remove a specific numeric token from a string.

    Tries to remove the token and any surrounding context that would leave
    orphaned punctuation (e.g. "at 5,450" -> "").
    """
    # Build pattern: optional leading context + token + optional trailing %
    escaped = re.escape(token)
    # Try removing "at/near/around/above/below TOKEN" patterns
    pattern = re.compile(
        r"(?:(?:at|near|around|above|below|to|from|by)\s+)?" + escaped + r"\s?%?",
        re.IGNORECASE,
    )
    result = pattern.sub("", text)
    # Clean up orphaned punctuation
    result = re.sub(r"\s{2,}", " ", result)
    result = re.sub(r"\(\s*\)", "", result)
    result = result.strip(" ,;:-")
    return result


def _scrub_numeric_from_json(
    obj: object,
    token: str,
    normalized: str,
    *,
    skip_keys: frozenset[str] = _NUMERIC_SKIP_KEYS,
    claims_key: str = _NUMERIC_CLAIMS_KEY,
) -> object:
    """
    Recursively remove a numeric token from all string values in the JSON.

    Returns the modified object. Skips metadata keys and numeric_claims.
    """
    if isinstance(obj, dict):
        result = {}
        for key, val in obj.items():
            if key in skip_keys or key == claims_key:
                result[key] = val
                continue
            result[key] = _scrub_numeric_from_json(val, token, normalized, skip_keys=skip_keys, claims_key=claims_key)
        return result
    elif isinstance(obj, list):
        scrubbed = []
        for item in obj:
            scrubbed_item = _scrub_numeric_from_json(item, token, normalized, skip_keys=skip_keys, claims_key=claims_key)
            # Drop list items that become empty after scrubbing
            if isinstance(scrubbed_item, dict):
                text_val = scrubbed_item.get("text", "")
                if text_val is not None:  # Keep even if text is empty (preserve structure)
                    scrubbed.append(scrubbed_item)
                else:
                    scrubbed.append(scrubbed_item)
            elif isinstance(scrubbed_item, str):
                scrubbed.append(scrubbed_item)  # Keep even if empty
            else:
                scrubbed.append(scrubbed_item)
        return scrubbed
    elif isinstance(obj, str):
        if token in obj or normalized.replace("%", "") in obj.replace(",", ""):
            return _scrub_token_from_string(obj, token)
        return obj
    else:
        return obj


def verify_and_scrub_numerics(sum_json: dict, source_text: str) -> dict:
    """
    Step D.5: Post-LLM deterministic numeric verifier.

    1. Extract every numeric token from the produced JSON.
    2. Verify each appears verbatim in source_text (with normalization).
    3. Enforce numeric_claims registry: every number used elsewhere must be there.
    4. Remove unverified numbers and record in _meta.unverified_numbers[].
    5. Compute _meta.numeric_coverage_pct.

    Args:
        sum_json: The LLM-produced summary JSON (twifo.sum.v1 schema).
        source_text: The extracted PDF text used as LLM input.

    Returns:
        Modified sum_json with unverified numbers scrubbed and metadata updated.
    """
    # Build source index for fast lookup
    source_index = _build_source_index(source_text)

    # 1. Extract numeric tokens only from whitelist paths (sections.*[].text, meta.theme, fingerprint_quotes[])
    all_tokens = _extract_numerics_from_whitelist_paths(sum_json)

    if not all_tokens:
        # No numeric tokens found — perfect coverage by definition
        meta = sum_json.setdefault("meta", {})
        meta["numeric_coverage_pct"] = 100.0
        meta.setdefault("unverified_numbers", [])
        return sum_json

    # 2. Verify each token against source
    verified: list[dict] = []
    unverified: list[dict] = []

    # Deduplicate by normalized value to avoid double-counting
    seen_normalized: dict[str, bool] = {}

    for entry in all_tokens:
        norm = entry["normalized"]
        if norm in seen_normalized:
            # Already classified
            if seen_normalized[norm]:
                verified.append(entry)
            else:
                unverified.append(entry)
            continue

        is_verified = _verify_token_in_source(norm, source_index, source_text)
        seen_normalized[norm] = is_verified

        if is_verified:
            verified.append(entry)
        else:
            unverified.append(entry)

    # 3. Compute coverage
    unique_total = len(seen_normalized)
    unique_verified = sum(1 for v in seen_normalized.values() if v)
    coverage_pct = round((unique_verified / unique_total) * 100, 1) if unique_total > 0 else 100.0

    # 4. Scrub unverified numbers from the JSON
    unverified_records: list[dict] = []
    scrubbed_normalized: set[str] = set()

    for entry in unverified:
        norm = entry["normalized"]
        if norm in scrubbed_normalized:
            continue  # Already scrubbed this normalized value
        scrubbed_normalized.add(norm)

        unverified_records.append({
            "token": entry["token"],
            "normalized": norm,
            "path": entry["path"],
        })

        # Remove from JSON only in whitelist paths (do not touch meta.title, ui.*, etc.)
        sum_json = _scrub_numeric_from_whitelist_paths(sum_json, entry["token"], norm)

    # 5. Enforce numeric_claims registry
    existing_claims = sum_json.get("numeric_claims", [])
    if not isinstance(existing_claims, list):
        existing_claims = []

    # Drop auto-registered entries from excluded paths (meta.title, meta.model, ui.*)
    existing_claims = [c for c in existing_claims if isinstance(c, dict) and not _is_auto_register_excluded_path(c.get("context", ""))]

    # Build set of values already in claims
    claimed_values: set[str] = set()
    for claim in existing_claims:
        if isinstance(claim, dict):
            val = _normalize_numeric(str(claim.get("value", "")))
            claimed_values.add(val)

    # Check verified tokens (all from whitelist paths): if used in content but not in claims, add stub
    for entry in verified:
        norm = entry["normalized"]
        if norm not in claimed_values:
            # Find source quote from source_text
            bare = norm.replace("%", "").replace(",", "")
            quote = None
            for sentence in re.split(r'[.!?\n]', source_text):
                sentence_bare = sentence.replace(",", "")
                if bare in sentence_bare:
                    quote = sentence.strip()[:200]
                    break
            existing_claims.append({
                "value": entry["token"],
                "context": f"auto-registered from {entry['path']}",
                "source_quote": quote,
            })
            claimed_values.add(norm)

    # Remove claims for unverified numbers
    cleaned_claims = []
    for claim in existing_claims:
        if isinstance(claim, dict):
            val = _normalize_numeric(str(claim.get("value", "")))
            if val not in scrubbed_normalized:
                cleaned_claims.append(claim)
    sum_json["numeric_claims"] = cleaned_claims

    # 6. Update metadata
    meta = sum_json.setdefault("meta", {})
    meta["numeric_coverage_pct"] = coverage_pct
    meta["unverified_numbers"] = unverified_records

    if unverified_records:
        meta["low_confidence"] = True
        if meta.get("low_confidence_reason"):
            meta["low_confidence_reason"] += "; unverified_numerics"
        else:
            meta["low_confidence_reason"] = "unverified_numerics"

    scrubbed_count = len(scrubbed_normalized)
    print(
        f"[NUMERIC VERIFIER] {unique_verified}/{unique_total} verified "
        f"({coverage_pct}%), {scrubbed_count} scrubbed"
    )

    return sum_json


# =========================
# Step D.6: Similarity Guard
# =========================

# Tunables
SIMILARITY_THRESHOLD = 0.55          # Jaccard > 0.55 triggers retry
SIMILARITY_RECENT_N = 50             # Compare against last N summaries
SIMILARITY_MIN_TOKENS = 8            # Ignore very short texts for comparison

# Stop-words stripped before Jaccard (common filler that inflates overlap).
_SIM_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "has", "had", "have", "will", "would", "could", "should", "may", "might",
    "that", "this", "it", "its", "as", "not", "no", "if", "than", "so",
    "up", "down", "out", "into", "over", "more", "less", "also", "very",
})


def _tokenize_for_similarity(text: str) -> set[str]:
    """
    Lowercase, split on non-alphanumeric, drop stop-words and short tokens.

    Returns a set of content tokens suitable for Jaccard comparison.
    """
    tokens = re.split(r"[^a-z0-9%]+", text.lower())
    return {t for t in tokens if t and len(t) > 2 and t not in _SIM_STOPWORDS}


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """
    Compute Jaccard index: |A & B| / |A | B|.

    Returns 0.0 if both sets are empty.
    """
    if not set_a and not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _extract_summary_fingerprint(sum_json: dict) -> str:
    """
    Extract the text that represents a summary's 'identity' for comparison.

    Concatenates: tldr bullets + what_moved_today + what_can_move_tomorrow.
    These are the sections most prone to template sameness.
    """
    parts: list[str] = []
    sections = sum_json.get("sections", {})

    for key in ("tldr", "what_moved_today", "what_can_move_tomorrow"):
        items = sections.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                t = item.get("text", "")
            elif isinstance(item, str):
                t = item
            else:
                continue
            if t:
                parts.append(t)

    return " ".join(parts)


def _load_recent_fingerprints(
    path_manager: Optional[TWIFOPathManager],
    exclude_basename: str = "",
    limit: int = SIMILARITY_RECENT_N,
) -> list[set[str]]:
    """
    Load tokenized fingerprints from the most recent N artifact summaries.

    Args:
        path_manager: TWIFOPathManager instance (None = skip, return []).
        exclude_basename: Skip this basename (the article being summarized).
        limit: Max number of recent summaries to load.

    Returns:
        List of token-sets, most recent first.
    """
    if not path_manager:
        return []

    try:
        artifacts = path_manager.list_artifacts_with_summaries()
    except Exception:
        return []

    fingerprints: list[set[str]] = []

    # Sort by modification time of sum.json (most recent first)
    scored: list[tuple[float, str]] = []
    for art in artifacts:
        basename = art.get("basename", "")
        if basename == exclude_basename:
            continue
        json_path = path_manager.artifact_path(basename, "sum.json")
        if json_path.exists():
            try:
                mtime = json_path.stat().st_mtime
            except OSError:
                mtime = 0.0
            scored.append((mtime, basename))

    scored.sort(reverse=True)

    for _, basename in scored[:limit]:
        json_path = path_manager.artifact_path(basename, "sum.json")
        try:
            with open(json_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            fp_text = _extract_summary_fingerprint(data)
            tokens = _tokenize_for_similarity(fp_text)
            if len(tokens) >= SIMILARITY_MIN_TOKENS:
                fingerprints.append(tokens)
        except Exception:
            continue

    return fingerprints


def compute_max_similarity(
    candidate_tokens: set[str],
    recent_fingerprints: list[set[str]],
) -> tuple[float, int]:
    """
    Compute the maximum Jaccard similarity between candidate and recent summaries.

    Returns:
        (max_similarity, index_of_most_similar) or (0.0, -1) if no comparisons.
    """
    if not recent_fingerprints or len(candidate_tokens) < SIMILARITY_MIN_TOKENS:
        return 0.0, -1

    best_score = 0.0
    best_idx = -1
    for idx, past_tokens in enumerate(recent_fingerprints):
        score = jaccard_similarity(candidate_tokens, past_tokens)
        if score > best_score:
            best_score = score
            best_idx = idx

    return best_score, best_idx


def similarity_guard(
    sum_json: dict,
    source_text: str,
    meta: dict,
    model: str,
    path_manager: Optional[TWIFOPathManager],
    pdf_path: Path,
    *,
    _already_retried: bool = False,
) -> dict:
    """
    Step D.6: Similarity guard — detect template sameness and retry once.

    Compares the new summary's tldr + what_moved_today + what_can_move_tomorrow
    against the last N summaries in artifacts/. If Jaccard similarity exceeds
    the threshold, triggers ONE retry with an anti-sameness instruction.

    Loop prevention: _already_retried flag ensures at most one retry.

    Args:
        sum_json: The post-quality-gate, post-numeric-verifier summary.
        source_text: The extracted PDF text.
        meta: Summary metadata dict.
        model: Model used for the current attempt.
        path_manager: TWIFOPathManager (None = skip guard entirely).
        pdf_path: Path to the original PDF.
        _already_retried: Internal flag — True means this IS the retry, do not retry again.

    Returns:
        sum_json (original or retried).
    """
    # Guard: skip if no path manager or already retried
    if not path_manager or _already_retried:
        return sum_json

    # Extract fingerprint from the candidate summary
    fp_text = _extract_summary_fingerprint(sum_json)
    candidate_tokens = _tokenize_for_similarity(fp_text)

    if len(candidate_tokens) < SIMILARITY_MIN_TOKENS:
        # Too short to compare meaningfully
        return sum_json

    # Load recent fingerprints
    exclude_basename = pdf_path.stem if pdf_path else ""
    recent = _load_recent_fingerprints(path_manager, exclude_basename=exclude_basename)

    if not recent:
        return sum_json

    # Compute similarity
    max_sim, best_idx = compute_max_similarity(candidate_tokens, recent)

    print(f"[SIMILARITY GUARD] max_jaccard={max_sim:.3f} (threshold={SIMILARITY_THRESHOLD})")

    if max_sim <= SIMILARITY_THRESHOLD:
        # Below threshold — no action needed
        meta_out = sum_json.setdefault("meta", {})
        meta_out["similarity_max_jaccard"] = round(max_sim, 4)
        return sum_json

    # ── Threshold exceeded: trigger ONE retry ──
    print(
        f"[SIMILARITY GUARD] Similarity {max_sim:.3f} > {SIMILARITY_THRESHOLD} — "
        f"triggering anti-sameness retry"
    )

    retry_instruction = (
        "ANTI-SAMENESS RETRY: Your previous output was too similar to existing summaries. "
        "Use DIFFERENT evidence quotes and focus on DIFFERENT unique entities/topics from "
        "this specific article. Do NOT reuse generic phrasing like 'markets reacted to', "
        "'key levels to watch', 'data releases ahead'. Extract the most distinctive claims, "
        "numbers, and conclusions from THIS document."
    )

    try:
        from summarize_pdf import llm_summarize_to_json as _llm_call

        raw_holder: list[str] = []
        retry_json = _llm_call(
            source_text,
            meta=meta,
            model=model,
            temperature=0.25,  # Slightly higher temp for diversity
            max_output_tokens=RETRY_MAX_OUTPUT_TOKENS,
            extra_instructions=retry_instruction,
            raw_output=raw_holder,
        )
    except Exception as e:
        print(f"[SIMILARITY GUARD] Retry failed: {e} — keeping original")
        meta_out = sum_json.setdefault("meta", {})
        meta_out["similarity_max_jaccard"] = round(max_sim, 4)
        meta_out["similarity_retry_attempted"] = True
        meta_out["similarity_retry_failed"] = str(e)
        return sum_json

    # Run numeric verifier on the retry output too
    retry_json = verify_and_scrub_numerics(retry_json, source_text)

    # Check if retry is actually better (lower similarity)
    retry_fp = _extract_summary_fingerprint(retry_json)
    retry_tokens = _tokenize_for_similarity(retry_fp)
    retry_sim, _ = compute_max_similarity(retry_tokens, recent)

    print(
        f"[SIMILARITY GUARD] Retry similarity: {retry_sim:.3f} "
        f"(original: {max_sim:.3f})"
    )

    # Use retry if it's better, otherwise keep original
    if retry_sim < max_sim:
        chosen = retry_json
        chosen_sim = retry_sim
        used_retry = True
        print(f"[SIMILARITY GUARD] Using retry (improved from {max_sim:.3f} to {retry_sim:.3f})")
    else:
        chosen = sum_json
        chosen_sim = max_sim
        used_retry = False
        print(f"[SIMILARITY GUARD] Keeping original (retry was not better)")

    # Record audit metadata
    meta_out = chosen.setdefault("meta", {})
    meta_out["similarity_max_jaccard"] = round(chosen_sim, 4)
    meta_out["similarity_retry_attempted"] = True
    meta_out["similarity_retry_used"] = used_retry

    if used_retry:
        # Update retry tracking
        existing_count = meta_out.get("retry_count", 0)
        meta_out["retry_count"] = existing_count + 1
        existing_reason = meta_out.get("retry_reason", "")
        if existing_reason:
            meta_out["retry_reason"] = f"{existing_reason}; similarity_guard"
        else:
            meta_out["retry_reason"] = "similarity_guard"

    return chosen


# =========================
# Step D.7: Critic Pass (Structural Cleanup)
# =========================

# Configuration flag: TWIFO_CRITIC_ENABLED=1 to enable, 0 or unset to disable.
CRITIC_ENABLED = os.getenv("TWIFO_CRITIC_ENABLED", "0") == "1"

# Jaccard threshold for considering two bullets "duplicated".
_CRITIC_DEDUP_JACCARD = 0.70

# Sections checked for cross-section deduplication, in priority order.
# When a duplicate pair is found, the bullet in the LOWER-priority section is removed.
_CRITIC_DEDUP_SECTIONS = [
    "tldr",
    "what_moved_today",
    "what_can_move_tomorrow",
    "what_occurred",
    "forward_watch",
]

# Fuzzy substring match: how much of the quote must appear in source (ratio 0-1).
_CRITIC_QUOTE_MIN_OVERLAP = 0.60


def _critic_tokenize(text: str) -> set[str]:
    """Lowercase, strip punctuation, split into token set for Jaccard."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower())
    return {t for t in cleaned.split() if len(t) > 2}


def _critic_jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _critic_is_near_verbatim(quote: str, source_text: str) -> bool:
    """
    Check if a quote is a near-verbatim excerpt from the source text.

    Strategy: normalize both to lowercase + collapsed whitespace, then check
    if the quote tokens appear as a contiguous-ish window in the source.
    """
    if not quote or not source_text:
        return False

    q_norm = re.sub(r"\s+", " ", quote.lower().strip())
    s_norm = re.sub(r"\s+", " ", source_text.lower())

    # Fast path: exact substring
    if q_norm in s_norm:
        return True

    # Fuzzy: check what fraction of quote words appear in a sliding window
    q_words = q_norm.split()
    if not q_words:
        return False

    s_words = s_norm.split()
    window_size = len(q_words) + 5  # small margin

    best_overlap = 0.0
    q_set = set(q_words)
    for start in range(max(1, len(s_words) - window_size + 1)):
        window_set = set(s_words[start : start + window_size])
        overlap = len(q_set & window_set) / len(q_set) if q_set else 0.0
        if overlap > best_overlap:
            best_overlap = overlap
        if best_overlap >= _CRITIC_QUOTE_MIN_OVERLAP:
            return True

    return best_overlap >= _CRITIC_QUOTE_MIN_OVERLAP


def critic_dedup_sections(sum_json: dict) -> int:
    """
    Remove duplicated bullets across dedup sections.

    Keeps the first occurrence by section priority order.
    Mutates sum_json in-place.

    Returns:
        Number of bullets removed.
    """
    sections = sum_json.get("sections", {})

    # Build a list of (section_name, index, token_set, text) for all bullets
    all_bullets: list[tuple[str, int, set[str], str]] = []
    for sec_name in _CRITIC_DEDUP_SECTIONS:
        items = sections.get(sec_name, [])
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            text = _extract_bullet_text(item)
            if text:
                tokens = _critic_tokenize(text)
                all_bullets.append((sec_name, idx, tokens, text))

    # Find duplicates: compare every pair, mark the lower-priority one for removal
    to_remove: set[tuple[str, int]] = set()
    for i in range(len(all_bullets)):
        if (all_bullets[i][0], all_bullets[i][1]) in to_remove:
            continue
        for j in range(i + 1, len(all_bullets)):
            if (all_bullets[j][0], all_bullets[j][1]) in to_remove:
                continue
            sim = _critic_jaccard(all_bullets[i][2], all_bullets[j][2])
            if sim >= _CRITIC_DEDUP_JACCARD:
                # Remove the one from the lower-priority section (higher index in _CRITIC_DEDUP_SECTIONS)
                sec_i_priority = _CRITIC_DEDUP_SECTIONS.index(all_bullets[i][0])
                sec_j_priority = _CRITIC_DEDUP_SECTIONS.index(all_bullets[j][0])
                if sec_j_priority >= sec_i_priority:
                    to_remove.add((all_bullets[j][0], all_bullets[j][1]))
                else:
                    to_remove.add((all_bullets[i][0], all_bullets[i][1]))

    # Remove marked bullets (iterate in reverse to preserve indices)
    removed = 0
    for sec_name in _CRITIC_DEDUP_SECTIONS:
        indices_to_drop = sorted(
            [idx for (s, idx) in to_remove if s == sec_name], reverse=True
        )
        items = sections.get(sec_name, [])
        for idx in indices_to_drop:
            if 0 <= idx < len(items):
                items.pop(idx)
                removed += 1

    return removed


def critic_validate_quotes(sum_json: dict, source_text: str) -> int:
    """
    Validate that fingerprint_quotes and trade_ideas source_quotes are verbatim.

    Removes quotes that fail validation. Mutates sum_json in-place.

    Returns:
        Number of quotes dropped.
    """
    dropped = 0

    # fingerprint_quotes
    fp_quotes = sum_json.get("fingerprint_quotes", [])
    if isinstance(fp_quotes, list):
        valid_quotes = []
        for q in fp_quotes:
            if isinstance(q, str) and _critic_is_near_verbatim(q, source_text):
                valid_quotes.append(q)
            else:
                dropped += 1
        sum_json["fingerprint_quotes"] = valid_quotes

    # trade_ideas[].source_quote
    sections = sum_json.get("sections", {})
    trade_ideas = sections.get("trade_ideas", [])
    if isinstance(trade_ideas, list):
        for idea in trade_ideas:
            if not isinstance(idea, dict):
                continue
            sq = idea.get("source_quote")
            if sq and isinstance(sq, str):
                if not _critic_is_near_verbatim(sq, source_text):
                    idea["source_quote"] = None
                    dropped += 1

    return dropped


def critic_ensure_numeric_registry(sum_json: dict, source_text: str) -> int:
    """
    Ensure every number used in the JSON appears in numeric_claims[].

    - Numbers present in source but missing from claims: auto-register.
    - Numbers NOT in source and missing from claims: remove from field (scrub).
    - Never adds new numbers that aren't already in the JSON.

    Mutates sum_json in-place.

    Returns:
        Number of auto-registrations performed.
    """
    # Build set of values already in numeric_claims
    claims = sum_json.get("numeric_claims", [])
    if not isinstance(claims, list):
        claims = []
        sum_json["numeric_claims"] = claims

    registered_values: set[str] = set()
    for c in claims:
        if isinstance(c, dict) and "value" in c:
            registered_values.add(_normalize_numeric(str(c["value"])))

    # Walk only whitelist paths (sections.*[].text, meta.theme, fingerprint_quotes[])
    all_tokens = _extract_numerics_from_whitelist_paths(sum_json)

    # Build source index for verification
    source_index = _build_source_index(source_text)

    registrations = 0
    for info in all_tokens:
        norm = info["normalized"]
        token = info["token"]
        path = info["path"]

        if not norm or norm in ("0", "1"):
            continue

        # Already registered
        if norm in registered_values:
            continue

        # Check if the number is in the source text
        if _verify_token_in_source(norm, source_index, source_text):
            # Auto-register with context from the path
            context = path.split(".")[-1] if "." in path else path
            context = context.strip("[]0123456789")
            if not context:
                context = "value"
            claims.append({
                "value": token,
                "context": context,
                "source_quote": None,
            })
            registered_values.add(norm)
            registrations += 1
        else:
            # Number not in source and not registered — scrub it
            sum_json = _scrub_numeric_from_json(
                sum_json, token, norm,
                skip_keys=_NUMERIC_SKIP_KEYS,
                claims_key=_NUMERIC_CLAIMS_KEY,
            )

    return registrations


def critic_pass(
    sum_json: dict,
    source_text: str,
    *,
    enable: Optional[bool] = None,
) -> dict:
    """
    Step D.7: Deterministic critic pass — structural cleanup only.

    1. Remove duplicated bullets across tldr / what_moved_today /
       what_can_move_tomorrow / what_occurred / forward_watch.
    2. Validate fingerprint_quotes and trade_ideas source_quotes are verbatim.
    3. Ensure numeric_claims covers all numbers used (auto-register or scrub).

    This pass NEVER adds new facts, entities, or claims.
    Output is always valid JSON with the same schema.

    Args:
        sum_json: The post-D.5/D.6 summary JSON.
        source_text: The extracted PDF text.
        enable: Override config flag. None = use CRITIC_ENABLED env var.

    Returns:
        The cleaned sum_json (mutated in-place).
    """
    should_run = enable if enable is not None else CRITIC_ENABLED
    if not should_run:
        return sum_json

    print("[CRITIC PASS] Running structural cleanup (Step D.7)")

    # 1. Deduplication
    dedup_count = critic_dedup_sections(sum_json)
    if dedup_count:
        print(f"[CRITIC PASS] Removed {dedup_count} duplicate bullet(s)")

    # 2. Evidence quote validation
    quote_drops = critic_validate_quotes(sum_json, source_text)
    if quote_drops:
        print(f"[CRITIC PASS] Dropped {quote_drops} non-verbatim quote(s)")

    # 3. Numeric claims completeness
    registrations = critic_ensure_numeric_registry(sum_json, source_text)
    if registrations:
        print(f"[CRITIC PASS] Auto-registered {registrations} numeric claim(s)")

    # Stamp metadata
    meta = sum_json.setdefault("meta", {})
    meta["critic_pass"] = True
    meta["critic_dedup_count"] = dedup_count
    meta["critic_quote_drops"] = quote_drops
    meta["critic_numeric_registrations"] = registrations

    # Warn if fingerprint_quotes dropped below 3
    fp_count = len(sum_json.get("fingerprint_quotes", []))
    if fp_count < 3 and quote_drops > 0:
        warnings_list = meta.setdefault("critic_warnings", [])
        warnings_list.append(
            f"fingerprint_quotes dropped to {fp_count} after quote validation"
        )
        print(f"[CRITIC PASS] WARNING: fingerprint_quotes={fp_count} (below 3)")

    if not dedup_count and not quote_drops and not registrations:
        print("[CRITIC PASS] No changes needed")

    return sum_json


# =========================
# Step A: Pre-Summarization Triage
# =========================

# Configuration flag: set via env var or override in code.
# TWIFO_TRIAGE_ENABLED=1 to enable, 0 or unset to disable.
TRIAGE_ENABLED = os.getenv("TWIFO_TRIAGE_ENABLED", "0") == "1"

# How many chars of extracted text to send to the triage model.
TRIAGE_INPUT_CHARS = 4000

# Model for triage (cheap, fast).
TRIAGE_MODEL = "gpt-4o-mini"
TRIAGE_MAX_TOKENS = 200
TRIAGE_TEMPERATURE = 0.0  # Fully deterministic

# Skip threshold: is_market_relevant=false AND priority_score <= this.
TRIAGE_SKIP_PRIORITY_THRESHOLD = 2

TRIAGE_SYSTEM_PROMPT = (
    "You are a document triage classifier for an institutional futures/macro trading desk.\n\n"
    "TASK: Decide whether a document is relevant to active futures/macro traders.\n\n"
    "STRICT GROUNDING:\n"
    "- Base your decision ONLY on the provided text snippet.\n"
    "- reason_quote MUST be a verbatim quote (10-40 words) from the text that supports your decision.\n"
    "- If no supporting quote exists, set reason_quote to \"(none)\".\n"
    "- Do NOT invent claims or use external knowledge.\n\n"
    "RELEVANT means the document discusses ANY of:\n"
    "- Futures, options, derivatives, commodities, FX, rates, equities indices\n"
    "- Macro-economic data, central bank policy, inflation, employment, GDP\n"
    "- Market-moving events, geopolitical risk with market implications\n"
    "- Trading strategies, technical analysis, positioning data\n"
    "- Volatility, risk sentiment, cross-asset flows\n\n"
    "NOT RELEVANT means the document is:\n"
    "- Administrative, compliance, legal, HR, or internal operations\n"
    "- Marketing material with no market content\n"
    "- Unrelated industry (healthcare, real estate, etc.) with no macro angle\n"
    "- Corrupted, unreadable, or empty text\n\n"
    "Output MUST be valid JSON only. No markdown, no explanations."
)

TRIAGE_USER_PROMPT = (
    "Classify this document. Return ONLY valid JSON:\n\n"
    "{\n"
    '  "is_market_relevant": true or false,\n'
    '  "priority_score_0_10": integer 0-10 (0=irrelevant, 10=critical market event),\n'
    '  "reason_quote": "exact verbatim quote from the text supporting your decision, or (none)"\n'
    "}\n\n"
    "RULES:\n"
    "1. reason_quote must be copied verbatim from the text below. If you cannot find a supporting quote, use \"(none)\".\n"
    "2. priority_score: 0-2 = not relevant, 3-4 = marginally relevant, 5-7 = relevant, 8-10 = high priority.\n"
    "3. Err on the side of relevance — if unsure, set is_market_relevant=true.\n\n"
    "DOCUMENT TITLE: <<<TITLE>>>\n\n"
    "DOCUMENT TEXT (first ~4000 chars):\n<<<\n<<<TEXT>>>\n>>>"
)


def _build_triage_prompt(title: str, text_snippet: str) -> str:
    """Build the triage user prompt with title and text inserted."""
    prompt = TRIAGE_USER_PROMPT.replace("<<<TITLE>>>", title)
    prompt = prompt.replace("<<<TEXT>>>", text_snippet)
    return prompt


def triage_document(
    title: str,
    extracted_text: str,
    *,
    model: str = TRIAGE_MODEL,
) -> dict:
    """
    Run a cheap triage classification on a document before full summarization.

    Args:
        title: Document title (usually the PDF filename stem).
        extracted_text: Full extracted text (only first TRIAGE_INPUT_CHARS used).
        model: Model to use for triage.

    Returns:
        Dict with keys: is_market_relevant (bool), priority_score_0_10 (int),
        reason_quote (str), triage_model (str), triage_error (str or None).
    """
    text_snippet = extracted_text[:TRIAGE_INPUT_CHARS]

    if not text_snippet.strip():
        return {
            "is_market_relevant": False,
            "priority_score_0_10": 0,
            "reason_quote": "(none)",
            "triage_model": model,
            "triage_error": "empty_text",
        }

    user_prompt = _build_triage_prompt(title, text_snippet)

    try:
        from openai_client import get_client
        client = get_client()

        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_output_tokens=TRIAGE_MAX_TOKENS,
            temperature=TRIAGE_TEMPERATURE,
        )

        out_text = ""
        for item in response.output:
            for content_item in item.content:
                if content_item.type == "output_text":
                    out_text += content_item.text

        if not out_text:
            raise ValueError("Triage API returned empty output")

        # Strip markdown fences
        cleaned = out_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        result = json.loads(cleaned.strip())

        # Validate and normalize
        is_relevant = bool(result.get("is_market_relevant", True))
        priority = result.get("priority_score_0_10", 5)
        if not isinstance(priority, int):
            try:
                priority = int(priority)
            except (ValueError, TypeError):
                priority = 5
        priority = max(0, min(10, priority))

        reason_quote = str(result.get("reason_quote", "(none)"))
        if not reason_quote.strip():
            reason_quote = "(none)"

        return {
            "is_market_relevant": is_relevant,
            "priority_score_0_10": priority,
            "reason_quote": reason_quote,
            "triage_model": model,
            "triage_error": None,
        }

    except Exception as e:
        # On any triage failure, default to relevant (don't block summarization)
        print(f"[TRIAGE] Error during triage: {e} — defaulting to relevant")
        return {
            "is_market_relevant": True,
            "priority_score_0_10": 5,
            "reason_quote": "(none)",
            "triage_model": model,
            "triage_error": str(e),
        }


def should_skip_summarization(triage_result: dict) -> bool:
    """
    Determine if a document should skip full summarization based on triage.

    Skip when: is_market_relevant=False AND priority_score <= TRIAGE_SKIP_PRIORITY_THRESHOLD.
    """
    if triage_result.get("triage_error"):
        return False  # Never skip on triage errors
    return (
        not triage_result.get("is_market_relevant", True)
        and triage_result.get("priority_score_0_10", 5) <= TRIAGE_SKIP_PRIORITY_THRESHOLD
    )


def _skipped_stub(
    pdf_path: Path,
    reason: str,
    triage_result: dict,
    extraction: dict,
    meta: dict,
) -> dict:
    """
    Build a minimal artifact JSON for documents skipped by triage.

    Preserves the original PDF and extraction cache but records why
    summarization was skipped.
    """
    meta_out = {
        **meta,
        "generated_at_iso": _iso_now(),
        "model": meta.get("model", TRIAGE_MODEL),
        "skipped": True,
        "skip_reason": reason,
        "triage": triage_result,
    }
    meta_out.update(_get_prompt_provenance())

    return {
        "_is_stub": True,
        "schema_version": SCHEMA_SUM_V1,
        "kind": "article",
        "meta": meta_out,
        "ui": {"header_pills": []},
        "extraction": {**extraction, "status": extraction.get("status", "ok")},
        "triage": triage_result,
        "skipped": True,
        "skip_reason": reason,
        "fingerprint_quotes": [],
        "numeric_claims": [],
        "sections": {
            "what_moved_today": [],
            "what_can_move_tomorrow": [],
            "trade_ideas": [],
            "tldr": [],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": [],
        },
        "chart_text_sources_used": [],
        "chart_observations": [],
    }


def extract_first_json_object(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Defensive JSON extractor: finds first complete JSON object in text.
    
    Handles:
    - Extra text before/after JSON
    - Markdown code fences
    - Multiple JSON objects (returns first)
    
    Returns:
        (json_string, error_message)
        - json_string is None if no valid JSON found
        - error_message is None if extraction succeeded
    """
    if not text or not text.strip():
        return None, "Empty input text"
    
    # Strip markdown fences first
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    
    # Find first '{' and matching '}'
    start_idx = cleaned.find('{')
    if start_idx == -1:
        return None, "No opening brace found"
    
    # Track brace depth to find matching closing brace
    depth = 0
    in_string = False
    escape_next = False
    
    for i in range(start_idx, len(cleaned)):
        char = cleaned[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if not in_string:
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    # Found matching closing brace
                    json_str = cleaned[start_idx:i+1]
                    return json_str, None
    
    return None, f"Unterminated JSON object (depth={depth} at end)"


def repair_json_deterministic(json_str: str) -> tuple[Optional[str], Optional[str]]:
    """
    Deterministic JSON repair: fix common recoverable errors.
    
    Only fixes:
    - Trailing commas before } or ]
    - Unmatched quotes at end (simple cases only)
    
    Does NOT fix:
    - Unterminated strings in middle
    - Missing braces
    - Invalid syntax
    
    Returns:
        (repaired_json, error_message)
        - repaired_json is None if unrecoverable
        - error_message describes what was attempted
    """
    if not json_str:
        return None, "Empty JSON string"
    
    original = json_str
    repaired = json_str
    repairs_made = []
    
    # Fix 1: Remove trailing commas before } or ]
    import re
    pattern = r',(\s*[}\]])'
    if re.search(pattern, repaired):
        repaired = re.sub(pattern, r'\1', repaired)
        repairs_made.append("removed_trailing_commas")
    
    # Fix 2: Check for unterminated string at end (simple case only)
    # Only fix if last char is quote and second-to-last is not escape
    stripped = repaired.rstrip()
    if len(stripped) > 2:
        # Count quotes to check if odd number (unterminated)
        quote_count = 0
        escape = False
        for char in stripped:
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
                continue
            if char == '"':
                quote_count += 1
        
        # If odd number of quotes, might be unterminated
        # Only fix if it's at the very end and closing brace follows
        if quote_count % 2 == 1:
            # This is likely unrecoverable - don't guess
            return None, "Unterminated string detected (unrecoverable)"
    
    # Fix 3: Ensure closing brace exists
    open_braces = repaired.count('{')
    close_braces = repaired.count('}')
    if open_braces > close_braces:
        # Try adding missing closing braces (simple case only)
        if open_braces - close_braces <= 2:
            repaired = repaired + ('}' * (open_braces - close_braces))
            repairs_made.append(f"added_{open_braces - close_braces}_closing_braces")
        else:
            return None, f"Too many missing closing braces ({open_braces - close_braces})"
    
    if repairs_made:
        return repaired, f"Repairs: {', '.join(repairs_made)}"
    else:
        return original, "No repairs needed"


def parse_json_with_recovery(
    raw_text: str,
    pdf_path: Optional[Path] = None,
    debug_path: Optional[Path] = None,
) -> tuple[Optional[dict], str]:
    """
    Robust JSON parser with defensive extraction and repair.
    
    Pipeline:
    1. Try direct parse (fast path)
    2. Extract first JSON object (handles extra text)
    3. Repair common issues (trailing commas)
    4. Final parse attempt
    5. Log failure to debug artifact
    
    Args:
        raw_text: Raw LLM output
        pdf_path: Source PDF path (for logging)
        debug_path: Debug artifact path (for logging)
    
    Returns:
        (parsed_dict, status_message)
        - parsed_dict is None if parsing failed
        - status_message describes what happened
    """
    if not raw_text or not raw_text.strip():
        return None, "Empty raw text"
    
    # Fast path: try direct parse
    try:
        result = json.loads(raw_text.strip())
        return result, "Direct parse succeeded"
    except json.JSONDecodeError as e:
        first_error = f"Direct parse failed at pos {e.pos}: {e.msg}"
    
    # Path 2: Extract first JSON object (handles extra text)
    json_str, extract_error = extract_first_json_object(raw_text)
    if json_str is None:
        msg = f"Extraction failed: {extract_error}. Original error: {first_error}"
        _log_parse_failure(raw_text, msg, pdf_path, debug_path)
        return None, msg
    
    # Try parsing extracted JSON
    try:
        result = json.loads(json_str)
        return result, f"Extracted JSON parsed successfully ({extract_error or 'clean extraction'})"
    except json.JSONDecodeError as e:
        extract_parse_error = f"Extracted JSON parse failed at pos {e.pos}: {e.msg}"
    
    # Path 3: Attempt deterministic repair
    repaired_str, repair_msg = repair_json_deterministic(json_str)
    if repaired_str is None:
        msg = f"Repair failed: {repair_msg}. {extract_parse_error}"
        _log_parse_failure(raw_text, msg, pdf_path, debug_path)
        return None, msg
    
    # Try parsing repaired JSON
    try:
        result = json.loads(repaired_str)
        return result, f"Repaired JSON parsed successfully: {repair_msg}"
    except json.JSONDecodeError as e:
        final_error = f"Repaired JSON parse failed at pos {e.pos}: {e.msg}"
        msg = f"All parse attempts exhausted. {final_error}. {repair_msg}"
        _log_parse_failure(raw_text, msg, pdf_path, debug_path)
        return None, msg


def _log_parse_failure(
    raw_text: str,
    error_msg: str,
    pdf_path: Optional[Path],
    debug_path: Optional[Path],
) -> None:
    """Log JSON parse failure to debug artifact."""
    if not debug_path:
        return
    
    try:
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        log_entry = (
            f"\n{'='*70}\n"
            f"JSON PARSE FAILURE\n"
            f"Timestamp: {timestamp}\n"
            f"PDF: {pdf_path.name if pdf_path else 'unknown'}\n"
            f"Error: {error_msg}\n"
            f"{'='*70}\n"
            f"RAW OUTPUT:\n"
            f"{raw_text[:5000]}\n"  # First 5000 chars
            f"{'='*70}\n\n"
        )
        
        # Append to debug file
        with open(debug_path, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        print(f"[JSON_PARSE_FAIL] Logged to {debug_path}")
    except Exception as e:
        print(f"[WARN] Failed to log parse failure: {e}")


def llm_summarize_to_json(
    text: str,
    meta: dict,
    model: str = "gpt-4o-mini",
    temperature: float = 0.1,
    max_output_tokens: int = BASE_MAX_OUTPUT_TOKENS,
    extra_instructions: Optional[str] = None,
    raw_output: Optional[List[str]] = None,
) -> dict:
    """
    Call OpenAI API and convert response to twifo.sum.v1 schema.
    """
    from openai_client import get_client
    from auth_env import describe_key
    
    if not text.strip():
        raise ValueError("No text provided to summarizer")
    
    # Get unified OpenAI client (same instance as preflight)
    client = get_client()
    
    # Debug logging
    key = os.getenv("OPENAI_API_KEY", "")
    prefix = describe_key(key) if key else "<none>"
    base_url = client.base_url if hasattr(client, 'base_url') else "default"
    print(f"[DEBUG] LLM call: model={model}, key_prefix={prefix}, base_url={base_url}, tokens={max_output_tokens}")

    from twifo_prompts.prompts import article_prompts

    system_prompt = article_prompts.SYSTEM_PROMPT
    extra_guidance = ""
    if extra_instructions:
        extra_guidance = f"\nRETRY GUIDANCE:\n{extra_instructions}\n"
    user_prompt = article_prompts.USER_PROMPT.replace(
        article_prompts.DOCUMENT_PLACEHOLDER, text
    )
    if extra_guidance:
        user_prompt = user_prompt.replace(
            "\n\nDOCUMENT TEXT:",
            extra_guidance + "\n\nDOCUMENT TEXT:",
        )

    # DEV_LOGGING: audit whether LLM receives real article text (guard: DEV_LOGGING=1)
    if os.getenv("DEV_LOGGING") == "1":
        article_id = meta.get("title", "<no-title>")
        input_len = len(text)
        first_200 = (text[:200] + ("..." if len(text) > 200 else "")).replace("\n", " ")
        input_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        user_prompt_len = len(user_prompt)
        print(
            f"[DEV_LOGGING] article_id={article_id!r} | input_text_len={input_len} | "
            f"input_sha256={input_sha} | user_prompt_len={user_prompt_len}"
        )
        print(f"[DEV_LOGGING] input_text_first_200={first_200!r}")

    # Call OpenAI API using unified client
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )
    
    # Extract text from response
    out_text = ""
    for item in response.output:
        for content_item in item.content:
            if content_item.type == "output_text":
                out_text += content_item.text
    
    if not out_text:
        raise ValueError("API returned empty output text")

    if raw_output is not None:
        raw_output.append(out_text)
    
    # Robust JSON parsing with recovery
    # Get debug path for logging (if available from meta)
    pdf_path = meta.get("_pdf_path")  # Will be set by caller if available
    debug_path = meta.get("_debug_path")  # Will be set by caller if available
    
    api_response, parse_status = parse_json_with_recovery(
        out_text, 
        pdf_path=pdf_path,
        debug_path=debug_path
    )
    
    if api_response is None:
        raise ValueError(f"JSON parse failed: {parse_status}")
    
    if "extracted" in parse_status.lower() or "repaired" in parse_status.lower():
        print(f"[JSON_PARSE] {parse_status}")
    
    # =================================================================
    # Convert LLM JSON → twifo.sum.v1 internal schema
    # -----------------------------------------------------------------
    # FIELD REGISTRY — every key consumed from the LLM response.
    #
    # Classification:
    #   [REQ]  = required by quality-gate / downstream (D.5-D.7)
    #   [OPT]  = optional, has a safe default
    #   [DEP]  = deprecated (v1.1 legacy), kept for backward compat
    #
    # Fail-safe rule: every access uses .get() + isinstance guard.
    #   - Lists  → default []  (never None)
    #   - Scalars→ default "(none)" or 0 (depending on type)
    #   - Dicts  → default {}
    #   - Unknown types → coerced or replaced with default
    #
    # Schema-drift risks (v1.1 → v1.2):
    #   1. `products` was a nested grid dict; now `trade_ideas` is flat.
    #      → Guarded: flat array tried first, grid used as fallback.
    #   2. `_meta.primary_entities` absent in v1.1.
    #      → Defaults to [].
    #   3. `fingerprint_quotes`, `numeric_claims`, `chart_*` are v1.2-only.
    #      → Default to [].
    #   4. `trade_ideas` as top-level key absent in v1.1.
    #      → raw_trade_ideas defaults to []; v1.1 grid fallback fires.
    #
    # Downstream compatibility proof:
    #   D.5 (verify_and_scrub_numerics): walks entire dict tree, uses
    #        .get() everywhere; needs `meta`, `numeric_claims` as list.  ✓
    #   D.6 (similarity_guard): reads sections.{tldr,what_moved_today,
    #        what_can_move_tomorrow} via .get(); handles str or dict items.  ✓
    #   D.7 (critic_pass): reads sections via .get(), fingerprint_quotes
    #        via .get(), numeric_claims via .get(); all guarded.  ✓
    # =================================================================

    # ── Caller-provided metadata (not from LLM) ──
    provider = meta.get("provider", "O")              # Always str
    published_date = meta.get("published_date", "")   # Always str
    horizon = meta.get("horizon", "")                 # Always str

    # ── Helpers ──
    def _safe_list(key: str) -> list[str]:
        """Extract a list-of-strings from api_response[key].

        Handles: list[str], list[dict] (extracts "text"), bare str, None,
        int, or any other type the LLM might hallucinate.
        Always returns list[str], never None.
        """
        val = api_response.get(key, [])
        if isinstance(val, list):
            out: list[str] = []
            for item in val:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    # LLM sometimes nests {"text": "..."} instead of a bare string
                    t = item.get("text", "")
                    out.append(str(t) if t else str(item))
                else:
                    out.append(str(item))
            return out
        if isinstance(val, str) and val.strip():
            return [val]
        return []

    def _safe_int(key: str, lo: int, hi: int, default: int = 0) -> int:
        """Extract a clamped integer from api_response[key].

        Handles: int, float, str("7"), None, bool.
        Always returns int in [lo, hi].
        """
        raw = api_response.get(key, default)
        if isinstance(raw, bool):
            return default       # True/False must not become 1/0
        if isinstance(raw, (int, float)):
            return max(lo, min(hi, int(raw)))
        try:
            return max(lo, min(hi, int(raw)))
        except (TypeError, ValueError):
            return default

    def _safe_dict(key: str) -> dict:
        """Extract a dict from api_response[key].

        Returns {} if the value is missing or not a dict.
        """
        val = api_response.get(key, {})
        return val if isinstance(val, dict) else {}

    # =================================================================
    # [OPT] _meta — v1.2 envelope; absent in v1.1
    # Fail-safe: {} if missing or non-dict
    # =================================================================
    api_meta = _safe_dict("_meta")

    # [OPT] _meta.primary_entities — v1.2, list[str], max 6
    # Fail-safe: [] if missing, non-list, or contains non-strings
    primary_entities: list[str] = []
    _raw_pe = api_meta.get("primary_entities", [])
    if isinstance(_raw_pe, list):
        primary_entities = [str(e) for e in _raw_pe if e][:6]

    # =================================================================
    # [OPT] fingerprint_quotes — v1.2, list[str], max 6
    # Consumed by: D.7 critic_validate_quotes
    # Fail-safe: [] if missing, non-list, or contains non-strings
    # =================================================================
    fingerprint_quotes: list[str] = []
    _raw_fq = api_response.get("fingerprint_quotes", [])
    if isinstance(_raw_fq, list):
        fingerprint_quotes = [str(q) for q in _raw_fq if q][:6]

    # =================================================================
    # [OPT] numeric_claims — v1.2, list[dict]
    # Consumed by: D.5 verify_and_scrub_numerics, D.7 critic_ensure_numeric_registry
    # Each entry requires "value"; "context" and "source_quote" are optional.
    # Fail-safe: [] if missing, non-list; malformed entries discarded
    # =================================================================
    numeric_claims: list[dict] = []
    _raw_nc = api_response.get("numeric_claims", [])
    if isinstance(_raw_nc, list):
        for _c in _raw_nc:
            if isinstance(_c, dict) and "value" in _c and _c["value"]:
                numeric_claims.append({
                    "value": str(_c.get("value", "")),
                    "context": str(_c.get("context", "")),
                    "source_quote": (
                        str(_c["source_quote"])
                        if _c.get("source_quote") and isinstance(_c.get("source_quote"), str)
                        else None
                    ),
                })

    # =================================================================
    # [OPT] chart_text_sources_used — v1.2, list[str]
    # Fail-safe: [] if missing or non-list; items coerced to str
    # =================================================================
    chart_text_sources_used: list[str] = []
    _raw_ctsu = api_response.get("chart_text_sources_used", [])
    if isinstance(_raw_ctsu, list):
        chart_text_sources_used = [str(s) for s in _raw_ctsu if s]

    # =================================================================
    # [OPT] chart_observations — v1.2, list[str], max 3
    # Fail-safe: [] if missing or non-list; items coerced to str
    # =================================================================
    chart_observations: list[str] = []
    _raw_co = api_response.get("chart_observations", [])
    if isinstance(_raw_co, list):
        chart_observations = [str(o) for o in _raw_co if o][:3]

    # =================================================================
    # [REQ] Core section fields — stable across v1.1 and v1.2
    # Consumed by: D.6 _extract_summary_fingerprint, D.7 critic_dedup_sections
    # Fail-safe: [] via _safe_list (handles list, str, dict, None)
    # =================================================================
    what_moved_today   = _safe_list("what_moved_today")       # [REQ] D.6 fingerprint
    what_can_move_tomorrow = _safe_list("what_can_move_tomorrow")  # [REQ] D.6 fingerprint
    tldr               = _safe_list("tldr")                   # [REQ] D.6 fingerprint, quality gate
    what_occurred      = _safe_list("what_occurred")           # [OPT]
    forward_watch      = _safe_list("forward_watch")           # [OPT]
    warnings           = _safe_list("warnings")                # [OPT]
    tips_reminders     = _safe_list("tips_reminders")          # [OPT]
    cross_asset_impacts = _safe_list("cross_asset_impacts")    # [OPT]
    scenarios          = _safe_list("scenarios")               # [OPT]

    # =================================================================
    # [DEP] products — v1.1 nested grid dict (e.g. products.indices.ES)
    # Replaced in v1.2 by flat trade_ideas + primary_entities.
    # Kept for backward compat: if flat trade_ideas is empty, we fall back
    # to extracting trade ideas from this grid.
    # Fail-safe: {} if missing, non-dict, or contains non-dict categories
    # =================================================================
    products_structured = _safe_dict("products")

    # =================================================================
    # [OPT] volatility_impact — dict with expected inner keys
    # Fail-safe: full default dict if missing/non-dict; inner keys
    # accessed via .get() so partial dicts are safe
    # =================================================================
    _DEFAULT_VOLATILITY = {
        "expected_volatility": "Medium",
        "drivers": [],
        "directional_skew": "Two-sided",
        "confidence_0_100": 50,
    }
    volatility_impact = api_response.get("volatility_impact", None)
    if not isinstance(volatility_impact, dict):
        volatility_impact = dict(_DEFAULT_VOLATILITY)
    else:
        # Ensure all inner keys present (LLM may omit some)
        for _k, _v in _DEFAULT_VOLATILITY.items():
            volatility_impact.setdefault(_k, _v)
        # Coerce drivers to list
        if not isinstance(volatility_impact.get("drivers"), list):
            volatility_impact["drivers"] = []

    # =================================================================
    # [OPT] sentiment_indicator — dict with expected inner keys
    # Fail-safe: same pattern as volatility_impact
    # =================================================================
    _DEFAULT_SENTIMENT = {
        "risk_on_off": "Neutral",
        "confidence_0_100": 50,
        "rationale": "(none)",
    }
    sentiment_indicator = api_response.get("sentiment_indicator", None)
    if not isinstance(sentiment_indicator, dict):
        sentiment_indicator = dict(_DEFAULT_SENTIMENT)
    else:
        for _k, _v in _DEFAULT_SENTIMENT.items():
            sentiment_indicator.setdefault(_k, _v)

    # =================================================================
    # [OPT] explain_like_refresher — scalar str, defaults to "(none)"
    # Fail-safe: coerce non-str to str, empty/None → "(none)"
    # =================================================================
    explain_like_refresher = api_response.get("explain_like_refresher", "(none)")
    if not isinstance(explain_like_refresher, str) or not explain_like_refresher.strip():
        explain_like_refresher = "(none)"

    # =================================================================
    # [OPT] score_0_10 — int 0-10.  [OPT] chart_score_0_3 — int 0-3.
    # Fail-safe: _safe_int clamps and handles str/None/bool
    # =================================================================
    score       = _safe_int("score_0_10",    lo=0, hi=10, default=0)
    chart_score = _safe_int("chart_score_0_3", lo=0, hi=3,  default=0)

    # =================================================================
    # [OPT/DEP] trade_ideas — v1.2: flat list[dict]; v1.1: absent (grid)
    # Consumed by: D.7 critic_validate_quotes (source_quote field)
    # MUST be initialized BEFORE flatten-products which reads it.
    # Fail-safe: [] — supports missing, null, str, malformed entries
    # =================================================================
    trade_ideas_list: list[dict] = []

    raw_trade_ideas = api_response.get("trade_ideas", [])
    if not isinstance(raw_trade_ideas, list):
        raw_trade_ideas = []  # str, None, int, etc. → empty

    # ── Parse v1.2 flat array ──
    for idea in raw_trade_ideas:
        if not isinstance(idea, dict):
            continue                           # skip stray strings / ints
        product = str(idea.get("product", "")).strip()
        if not product:
            continue                           # unnamed idea → discard
        key_levels = idea.get("key_levels", [])
        if isinstance(key_levels, str):
            key_levels = [key_levels] if key_levels else []
        elif not isinstance(key_levels, list):
            key_levels = []                    # int / None / dict → []
        source_quote = idea.get("source_quote")
        if not source_quote or not isinstance(source_quote, str):
            source_quote = None                # empty / non-str → None
        # Determine category from product ticker
        category = "others"
        for cat, tickers in [("indices", ["ES", "NQ", "YM", "RTY"]),
                              ("rates", ["ZN", "ZB", "ZF", "ZT"]),
                              ("metals", ["GC", "SI", "HG", "PL"]),
                              ("crypto", ["BTC", "ETH"]),
                              ("others", ["VIX", "CL", "NG", "DX"])]:
            if product in tickers:
                category = cat
                break
        trade_ideas_list.append({
            "product": product,
            "category": category,
            "bias": str(idea.get("bias", "Neutral")),
            "catalyst": str(idea.get("catalyst", "")),
            "setup": str(idea.get("setup", "")),
            "key_levels": key_levels,
            "source_quote": source_quote,
            "risk": str(idea.get("risk", "")),
            "time_horizon": str(idea.get("time_horizon", "")),
            "sources": [provider],
        })

    # ── Fallback: v1.1 products grid → trade ideas (if flat list empty) ──
    if not trade_ideas_list and products_structured:
        category_order = [
            ("indices", ["ES", "NQ"]),
            ("rates", ["ZN", "ZB"]),
            ("metals", ["GC", "SI"]),
            ("crypto", ["BTC"]),
            ("others", ["VIX", "CL"]),
        ]
        for category, product_list in category_order:
            category_data = products_structured.get(category, {})
            if not isinstance(category_data, dict):
                continue              # Guard: category value may be list/str
            for product in product_list:
                if product not in category_data:
                    continue
                idea_data = category_data[product]
                if not isinstance(idea_data, dict):
                    continue          # Guard: product value may be str/list
                key_levels = idea_data.get("key_levels", [])
                if isinstance(key_levels, str):
                    key_levels = [key_levels] if key_levels else []
                elif not isinstance(key_levels, list):
                    key_levels = []
                source_quote = idea_data.get("source_quote")
                if not source_quote or not isinstance(source_quote, str):
                    source_quote = None
                trade_ideas_list.append({
                    "product": product,
                    "category": category,
                    "bias": str(idea_data.get("bias", "Neutral")),
                    "catalyst": str(idea_data.get("catalyst", "")),
                    "setup": str(idea_data.get("setup", "")),
                    "key_levels": key_levels,
                    "source_quote": source_quote,
                    "risk": str(idea_data.get("risk", "")),
                    "time_horizon": str(idea_data.get("time_horizon", "")),
                    "sources": [provider],
                })

    # =================================================================
    # Flatten products: trade_ideas → primary_entities → grid
    # Fail-safe: all_products starts at []; each source guarded
    # =================================================================
    all_products: list[str] = []
    for idea in trade_ideas_list:
        p = idea.get("product", "")
        if p and p not in all_products:
            all_products.append(p)
    for entity in primary_entities:
        if entity and entity not in all_products:
            all_products.append(entity)
    for cat_key in ["indices", "rates", "metals", "crypto", "others"]:
        cat_val = products_structured.get(cat_key)
        if isinstance(cat_val, dict):
            for p in cat_val:
                if p not in all_products:
                    all_products.append(p)
    products = all_products
    products_inferred_reason = "from_llm:" + ",".join(products) if products else ""

    # If LLM returned no products, infer from source text or use Macro
    if not products:
        inferred, reason = _infer_products_from_text(text)
        products = inferred if inferred else ["Macro"]
        products_inferred_reason = reason if inferred else "empty_llm_fallback_macro"

    # Generate theme from first TL;DR bullet
    theme = ""
    if tldr:
        first_tldr = str(tldr[0]) if tldr[0] else ""
        words = first_tldr.split()
        theme = " ".join(words[:22])

    # =================================================================
    # Assemble output dict — every key is guaranteed present and typed.
    # D.5, D.6, D.7 can safely .get() / .setdefault() on this structure.
    # =================================================================
    meta_out: dict = {
        "title": meta.get("title", ""),
        "provider": provider,
        "published_date": published_date,
        "horizon": horizon,
        "products": products,
        "primary_entities": primary_entities,
        "theme": theme,
        "generated_at_iso": _iso_now(),
        "model": model,
    }
    meta_out.update(_get_prompt_provenance())

    return {
        "schema_version": SCHEMA_SUM_V1,
        "kind": "article",
        "meta": meta_out,
        "ui": {
            "header_pills": [
                {"text": provider, "type": "provider"},
                {"text": published_date, "type": "date"},
                {"text": horizon, "type": "horizon"},
                {"text": f"{score}/10", "type": "score"},
            ]
        },
        "extraction": {
            **meta.get("extraction", {}),
            "products_inferred_reason": products_inferred_reason,
        },
        "fingerprint_quotes": fingerprint_quotes,    # list[str], never None
        "numeric_claims": numeric_claims,             # list[dict], never None
        "sections": {
            "what_moved_today":       [{"text": t, "sources": [provider]} for t in what_moved_today],
            "what_can_move_tomorrow": [{"text": t, "sources": [provider]} for t in what_can_move_tomorrow],
            "trade_ideas":            trade_ideas_list,          # list[dict], never None
            "tldr":                   [{"text": t, "sources": [provider]} for t in tldr[:3]],
            "what_occurred":          [{"text": t, "sources": [provider]} for t in what_occurred],
            "forward_watch":          [{"text": t, "sources": [provider]} for t in forward_watch],
            "warnings":              [{"text": t, "sources": [provider]} for t in warnings],
            "tips_reminders":         [{"text": t, "sources": [provider]} for t in tips_reminders],
            "cross_asset_impacts":    [{"text": t, "sources": [provider]} for t in cross_asset_impacts],
            "scenarios":              [{"text": t, "sources": [provider]} for t in scenarios],
        },
        "volatility_impact": volatility_impact,       # dict, all inner keys present
        "sentiment_indicator": sentiment_indicator,   # dict, all inner keys present
        "explain_like_refresher": explain_like_refresher,  # str, never None
        "summary_score_0_10": score,                  # int 0-10
        "chart_score_0_3": chart_score,               # int 0-3
        "chart_text_sources_used": chart_text_sources_used,  # list[str]
        "chart_observations": [{"text": o, "sources": [provider]} for o in chart_observations],
    }

def summarize_text(
    text: str,
    *,
    title: str,
    provider: str,
    published_date: str,
    horizon: str,
    products: Optional[List[str]] = None,
    out_dir: Optional[Path] = None,
    model: str = "gpt-4o-mini",
) -> Tuple[dict, Path]:
    """
    Summarize plain text and ALWAYS emit JSON+TXT.
    Used by rollups and OCR-to-text flows. No OCR here (ZERO-OCR RULE).
    
    Returns:
        Tuple of (sum_json dict, json_path Path) - the path where JSON was written.
    """
    out_dir = out_dir or Path(".")
    fake_pdf = out_dir / (title.replace(" ", "_") + ".pdf")  # naming anchor only
    json_path, txt_path = _sum_paths(fake_pdf, out_dir=out_dir)

    meta = {
        "title": title,
        "provider": provider,
        "published_date": published_date,
        "horizon": horizon,
        "products": products or [],
        "model": model,
        "extraction": {
            "status": "ok",
            "method_used": "text_input",
            "chars_total": len(text),
            "pages_with_text": 1 if text.strip() else 0,
            "errors": [],
        }
    }

    try:
        sum_json = _summarize_with_quality_retry(
            text,
            meta=meta,
            model=model,
            pdf_path=fake_pdf,
            out_dir=out_dir,
            apply_format_fix=False,
        )
    except Exception as e:
        sum_json = _failed_stub(fake_pdf, reason=str(e), extraction=meta["extraction"], meta=meta)

    _write_json(json_path, sum_json)
    
    # HARD ASSERTION: Verify JSON was actually written - raise if missing
    if not os.path.exists(json_path):
        msg = f"[ERROR] write_failed: sum.json missing after write: {json_path}"
        print(msg)
        raise SummaryWriteFailedError(msg)
    
    _write_txt(txt_path, render_sum_txt(sum_json))
    return (sum_json, json_path)

def summarize_pdf(
    pdf_path: Path,
    *,
    out_dir: Optional[Path] = None,
    model: str = "gpt-4o-mini",
    allow_ocr: bool = True,  # ZERO-OCR RULE: False for rollups/internal
    path_manager: Optional[TWIFOPathManager] = None,
    enable_triage: Optional[bool] = None,
) -> Tuple[dict, Path]:
    """
    External ingestion: PDF -> extract text -> (optional triage) -> (optional OCR) -> summarize -> ALWAYS JSON+TXT.
    
    ZERO-OCR RULE: Set allow_ocr=False for internal summaries/rollups.
    
    Args:
        path_manager: Optional TWIFOPathManager for new file layout.
                     If provided, outputs go to artifacts/<basename>/
                     and original_pdf_path + sha256 are added to metadata.
        enable_triage: Override triage behavior. None = use TRIAGE_ENABLED env var.
                      True = force triage on. False = force triage off.
    
    Returns:
        Tuple of (sum_json dict, json_path Path) - the path where JSON was written.
    """
    pdf_path = Path(pdf_path)
    
    # Compute original PDF SHA256 if using path manager
    original_pdf_sha256 = None
    if PATH_MANAGER_AVAILABLE and path_manager:
        try:
            original_pdf_sha256 = compute_pdf_sha256(pdf_path)
        except Exception as e:
            print(f"[WARN] Could not compute PDF SHA256: {e}")
    
    # Get output paths (uses path_manager if available)
    json_path, txt_path = _sum_paths(pdf_path, out_dir=out_dir, path_manager=path_manager)

    # Extract with caching
    text, extraction = extract_text(pdf_path, path_manager=path_manager)
    
    # Check if extraction is sufficient
    chars_extracted = len(text)
    pages_total = extraction.get('pages_total', 0)
    pages_with_text = extraction.get('pages_with_text', 0)
    pages_ratio = pages_with_text / pages_total if pages_total > 0 else 0
    
    # Determine if OCR is needed based on thresholds
    needs_ocr = (
        allow_ocr and
        not extraction.get('ocr_used', False) and  # Don't OCR if already OCR'd
        (
            chars_extracted < OCR_THRESHOLD_CHARS or  # Too few characters
            (pages_total > 0 and pages_ratio < OCR_THRESHOLD_PAGES_RATIO)  # Too few pages with text
        )
    )
    
    if needs_ocr:
        print(f"[OCR] Extraction insufficient (chars={chars_extracted}, pages_ratio={pages_ratio:.2f}), attempting OCR...")
        ocr_text, ocr_extraction = ocr_to_text(pdf_path, dpi=300, max_pages=None, path_manager=path_manager)
        
        # Use OCR result if it's better
        if len(ocr_text) > chars_extracted:
            print(f"[OCR] OCR produced more text ({len(ocr_text)} chars vs {chars_extracted}), using OCR result")
            text = ocr_text
            extraction = ocr_extraction
        else:
            print(f"[OCR] OCR did not improve extraction ({len(ocr_text)} chars vs {chars_extracted}), keeping original")

    # Parse metadata from filename
    filename = pdf_path.stem
    
    # Provider detection using full prefix map
    PROVIDER_PREFIXES = {
        "BOA_": "BOA", "BA_": "BA", "BR_": "BR", "DB_": "DB", "GM_": "GM",
        "HT_": "HT", "JPM_": "JPM", "MZ_": "MZ", "TSL_": "TSL", "T_": "T",
        "WF_": "WF", "SEB_": "SEB", "R_": "R", "MUFG_": "MUFG", "ANZ_": "ANZ",
        "BCA_": "BCA", "BNPP_": "BNPP", "BNY_": "BNY", "CACIB_": "CACIB",
        "CITI_": "CITI", "HSBC_": "HSBC", "ING_": "ING", "MS_": "MS",
        "NOM_": "NOM", "RBC_": "RBC", "SG_": "SG", "STI_": "STI",
        "TME_": "TME", "UBS_": "UBS",
    }
    
    provider = "O"  # Default to "Others"
    for prefix, code in PROVIDER_PREFIXES.items():
        if filename.startswith(prefix):
            provider = code
            break
    
    date_match = re.search(r'(\d{8})', filename)
    published_date = date_match.group(1) if date_match else ""
    
    # Check extraction status for quality flags
    extraction_status = extraction.get('status', 'unknown')
    extraction_quality = extraction.get('extraction_quality_0_100', None)
    
    meta = {
        "title": filename,
        "provider": provider,
        "published_date": published_date,
        "horizon": "u",
        "products": [],
        "generated_at_iso": _iso_now(),
        "model": model,
        "used_ocr": extraction.get('ocr_used', False),
        "extraction": extraction,
    }
    
    # Add low_confidence flag for degraded extractions
    if extraction_status == 'degraded':
        meta["low_confidence"] = True
        meta["low_confidence_reason"] = "degraded_extraction"
        degradation_reasons = extraction.get('degradation_reasons', [])
        if degradation_reasons:
            meta["degradation_details"] = degradation_reasons
        print(f"[QUALITY] Extraction degraded: {degradation_reasons}")
    
    # Add original PDF metadata if using path manager
    if PATH_MANAGER_AVAILABLE and path_manager:
        meta["original_pdf_path"] = str(pdf_path.resolve())
        if original_pdf_sha256:
            meta["original_pdf_sha256"] = original_pdf_sha256

    # Check for truly unusable extraction (only stub if text is absent or tiny)
    STUB_THRESHOLD_CHARS = 100  # Only stub if text < 100 chars (truly unusable)
    
    if not text.strip() or len(text) < STUB_THRESHOLD_CHARS:
        sum_json = _failed_stub(
            pdf_path,
            reason=f"Extraction produced no usable text (chars={len(text)}).",
            extraction=extraction,
            meta=meta,
        )
        _write_json(json_path, sum_json)
        
        # HARD ASSERTION: Verify JSON was actually written - raise if missing
        if not os.path.exists(json_path):
            msg = f"[ERROR] write_failed: sum.json missing after write: {json_path}"
            print(msg)
            raise SummaryWriteFailedError(msg)
        
        _write_txt(txt_path, render_sum_txt(sum_json))
        
        print(f"[QUALITY] Extraction produced no usable text - creating stub")
        return (sum_json, json_path)
    
    # Low-quality extraction but still has meaningful text (100-1500 chars)
    # OR extraction_status='failed' but text is present
    # → Run LLM summarization but force low_confidence=true
    if extraction_status == 'failed' or len(text) < MIN_TEXT_CHARS:
        print(
            f"[QUALITY] Low-quality extraction (status={extraction_status}, "
            f"chars={len(text)}) - will summarize with low_confidence flag"
        )
        meta["low_confidence"] = True
        if extraction_status == 'failed':
            meta["low_confidence_reason"] = "failed_extraction_but_has_text"
        else:
            meta["low_confidence_reason"] = f"insufficient_text_chars_{len(text)}"

    # Step A: Pre-summarization triage (optional, saves tokens on irrelevant docs)
    triage_active = enable_triage if enable_triage is not None else TRIAGE_ENABLED
    triage_result = None

    if triage_active:
        print(f"[TRIAGE] Running triage on {pdf_path.name} ...")
        triage_result = triage_document(filename, text, model=TRIAGE_MODEL)
        meta["triage"] = triage_result

        print(
            f"[TRIAGE] relevant={triage_result['is_market_relevant']}, "
            f"priority={triage_result['priority_score_0_10']}, "
            f"error={triage_result.get('triage_error')}"
        )

        if should_skip_summarization(triage_result):
            reason = (
                f"Triage: not market-relevant "
                f"(priority={triage_result['priority_score_0_10']}/10, "
                f"quote={triage_result['reason_quote']!r})"
            )
            print(f"[TRIAGE] Skipping summarization: {reason}")

            sum_json = _skipped_stub(
                pdf_path,
                reason=reason,
                triage_result=triage_result,
                extraction=extraction,
                meta=meta,
            )
            _write_json(json_path, sum_json)
            
            # HARD ASSERTION: Verify JSON was actually written - raise if missing
            if not os.path.exists(json_path):
                msg = f"[ERROR] write_failed: sum.json missing after write: {json_path}"
                print(msg)
                raise SummaryWriteFailedError(msg)
            
            _write_txt(txt_path, f"{filename}\n\nSKIPPED: {reason}\n")

            return (sum_json, json_path)

    # Summarize with quality retry (model escalation)
    try:
        sum_json = _summarize_with_quality_retry(
            text,
            meta=meta,
            model=model,
            pdf_path=pdf_path,
            out_dir=out_dir,
            apply_format_fix=True,
            path_manager=path_manager,
        )
    except Exception as e:
        print(f"[ERROR] LLM summarization failed for {pdf_path.name}: {e}")
        sum_json = _failed_stub(pdf_path, reason=str(e), extraction=extraction, meta=meta)

    # Log clearly whether we produced a real summary or a stub
    if is_stub(sum_json):
        stub_reason = sum_json.get("extraction", {}).get("reason", "(unknown)")
        print(f"[STUB] Writing failed/empty summary for {pdf_path.name}: {stub_reason}")
    else:
        sec = sum_json.get("sections", {})
        n_tldr = len(sec.get("tldr", []))
        n_wmt = len(sec.get("what_moved_today", []))
        n_wcmt = len(sec.get("what_can_move_tomorrow", []))
        print(
            f"[OK] Real summary for {pdf_path.name}: "
            f"tldr={n_tldr} wmt={n_wmt} wcmt={n_wcmt}"
        )

    _write_json(json_path, sum_json)
    
    # HARD ASSERTION: Verify JSON was actually written - raise if missing
    if not os.path.exists(json_path):
        msg = f"[ERROR] write_failed: sum.json missing after write: {json_path}"
        print(msg)
        raise SummaryWriteFailedError(msg)
    
    _write_txt(txt_path, render_sum_txt(sum_json))
    
    return (sum_json, json_path)
