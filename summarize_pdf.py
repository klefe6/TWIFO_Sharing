"""
PDF Summarization Module (Redesigned)
Purpose: Summarize PDF research documents - ALWAYS emits JSON + TXT
Author: Kevin Lefebvre
Last Updated: 2026-01-11
Schema: twifo.sum.v1
"""

from __future__ import annotations

import json
import os
import re
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def _write_txt(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")

def _sum_paths(pdf_path: Path, out_dir: Optional[Path] = None) -> Tuple[Path, Path]:
    out_dir = out_dir or pdf_path.parent
    base = out_dir / pdf_path.stem
    return (Path(str(base) + "__sum.json"), Path(str(base) + "__sum.txt"))

def _sum_debug_path(pdf_path: Path, out_dir: Optional[Path] = None) -> Path:
    """
    Build debug artifact path adjacent to the PDF.
    """
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

def _failed_stub(pdf_path: Path, reason: str, extraction: dict, meta: dict) -> dict:
    """
    Unified failure stub with deterministic schema.
    
    Required keys:
    - Primary: what_moved_today, what_can_move_tomorrow, trade_ideas
    - Legacy: tldr, what_occurred, forward_watch, warnings, tips_reminders, cross_asset_impacts, scenarios
    
    All values are lists, no strings, no optional keys.
    """
    return {
        "schema_version": SCHEMA_SUM_V1,
        "kind": "article",
        "meta": {
            **meta,
            "generated_at_iso": _iso_now(),
            "model": meta.get("model", MODEL),
        },
        "ui": {"header_pills": []},
        "extraction": {**extraction, "status": "failed", "reason": reason},
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
        }
    }

def reject_hallucinated_levels(sum_json: dict, source_text: str) -> tuple[bool, str]:
    """
    Post-generation validator: reject price levels that don't exist in source.
    
    Checks if any price level in key_levels (containing $ or numeric patterns)
    actually appears in the source text or source_quote.
    
    Args:
        sum_json: Parsed summary JSON
        source_text: Original document text (for validation)
        
    Returns:
        (has_hallucination: bool, reason: str)
    """
    import re
    
    # Normalize source text for comparison (lowercase, remove extra whitespace)
    source_normalized = re.sub(r'\s+', ' ', source_text.lower())
    
    trade_ideas = sum_json.get("sections", {}).get("trade_ideas", [])
    if not isinstance(trade_ideas, list):
        return False, ""
    
    # Pattern to detect price levels: $ followed by digits, or numeric patterns
    price_pattern = re.compile(r'\$[\d,]+\.?\d*|[\d,]+\.?\d*\s*(?:dollars?|USD|points?|basis\s+points?)', re.IGNORECASE)
    
    for idea in trade_ideas:
        if not isinstance(idea, dict):
            continue
            
        key_levels = idea.get("key_levels", [])
        if not isinstance(key_levels, list):
            continue
            
        source_quote = idea.get("source_quote")
        
        for level in key_levels:
            if not isinstance(level, str):
                continue
                
            # Skip placeholder values
            if level in ["(not provided in inputs)", "no explicit levels provided", ""]:
                continue
            
            # Check if this level contains a price pattern
            if not price_pattern.search(level):
                continue
            
            # Extract the price value from the level for matching
            price_matches = price_pattern.findall(level)
            if not price_matches:
                continue
            
            # Check if source_quote exists and contains the level
            if source_quote:
                source_quote_normalized = re.sub(r'\s+', ' ', str(source_quote).lower())
                # Check if any price match appears in source_quote
                found_in_quote = any(
                    re.sub(r'[,\s]', '', pm.lower()) in re.sub(r'[,\s]', '', source_quote_normalized)
                    for pm in price_matches
                )
                if found_in_quote:
                    continue  # Valid - found in source_quote
            
            # Check if price appears in source text
            found_in_source = any(
                re.sub(r'[,\s]', '', pm.lower()) in re.sub(r'[,\s]', '', source_normalized)
                for pm in price_matches
            )
            
            if not found_in_source:
                # Hallucinated level detected
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
    """
    sections = sum_json.get("sections", {})
    
    # Collect all text bullets from sections (including new fields)
    all_bullets = []
    for key in ["what_moved_today", "what_can_move_tomorrow", "tldr", "what_occurred", "forward_watch", 
                "warnings", "tips_reminders", "cross_asset_impacts", "scenarios"]:
        items = sections.get(key, [])
        if isinstance(items, list):
            for item in items:
                text = _extract_bullet_text(item).lower()
                if text:
                    all_bullets.append(text)
    
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
    unique_bullets = set(all_bullets)
    if len(unique_bullets) < 3:
        return True, f"too_few_unique_bullets: only {len(unique_bullets)} unique bullets found"
    
    # Check 2: Detect repeated bullets (exact duplicates)
    if len(all_bullets) > len(unique_bullets) * 1.5:  # More than 50% duplication
        duplication_rate = (len(all_bullets) - len(unique_bullets)) / len(all_bullets) * 100
        return True, f"excessive_duplication: {duplication_rate:.0f}% of bullets are duplicates"
    
    # Check 3: Generic placeholder phrases
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
    
    # Check 4: Detect suspiciously short bullets (likely low-effort)
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
) -> dict:
    """
    Run a two-stage quality retry with model escalation.
    """
    debug_path = _sum_debug_path(pdf_path, out_dir=out_dir)
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
                "Provide fuller, non-terse bullets that meet the minimum counts. "
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
        
        # Layer 1: Generic quality checks
        is_low_quality, quality_reason = is_low_quality_summary(sum_json)
        
        # Layer 2: Hallucination validator (fail-closed for price levels)
        if not is_low_quality:
            has_hallucination, hallucination_reason = reject_hallucinated_levels(sum_json, text)
            if has_hallucination:
                is_low_quality = True
                quality_reason = hallucination_reason
                print(f"[ANTI-HALLUCINATION] Detected: {hallucination_reason}")
        
        if not is_low_quality:
            print(f"[QUALITY GATE] Passed on attempt {attempt_count}")
            extraction = sum_json.get("extraction", {})
            extraction["attempt_count"] = attempt_count
            extraction["quality_reason"] = ""
            sum_json["extraction"] = extraction
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
    
    # TRADE IDEAS - structured by product (ALWAYS ES, NQ, GC, SI, VIX in that order)
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
"""

# =========================
# Extraction (no OCR by default here; OCR handled separately)
# =========================
def extract_text(pdf_path: Path) -> Tuple[str, dict]:
    errors: List[str] = []

    # pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        parts = []
        pages_with_text = 0
        for p in reader.pages:
            t = (p.extract_text() or "").strip()
            if t:
                pages_with_text += 1
                parts.append(t)
        text = "\n\n".join(parts).strip()
        return text, {
            "status": "ok",
            "method_used": "pypdf",
            "total_chars": len(text),
            "pages_with_text": pages_with_text,
            "errors": errors,
        }
    except Exception as e:
        errors.append(f"pypdf failed: {e}")

    # pdfplumber
    try:
        import pdfplumber
        parts = []
        pages_with_text = 0
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                t = (page.extract_text() or "").strip()
                if t:
                    pages_with_text += 1
                    parts.append(t)
        text = "\n\n".join(parts).strip()
        return text, {
            "status": "ok",
            "method_used": "pdfplumber",
            "total_chars": len(text),
            "pages_with_text": pages_with_text,
            "errors": errors,
        }
    except Exception as e:
        errors.append(f"pdfplumber failed: {e}")

    # pymupdf
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        parts = []
        pages_with_text = 0
        for i in range(doc.page_count):
            t = (doc.load_page(i).get_text("text") or "").strip()
            if t:
                pages_with_text += 1
                parts.append(t)
        doc.close()
        text = "\n\n".join(parts).strip()
        return text, {
            "status": "ok",
            "method_used": "pymupdf",
            "total_chars": len(text),
            "pages_with_text": pages_with_text,
            "errors": errors,
        }
    except Exception as e:
        errors.append(f"pymupdf failed: {e}")

    return "", {
        "status": "failed",
        "method_used": "failed",
        "total_chars": 0,
        "pages_with_text": 0,
        "errors": errors,
    }

# =========================
# OCR (external only - NEVER for rollups/internal)
# =========================
def ocr_to_text(pdf_path: Path, dpi: int = 300, max_pages: Optional[int] = None) -> Tuple[str, dict]:
    """
    OCR to TEXT using PyMuPDF render + pytesseract.
    This avoids ocrmypdf/ghostscript. Requires:
      pip install pymupdf pillow pytesseract
    
    ZERO-OCR RULE: This is ONLY for external PDFs. Rollups NEVER use OCR.
    """
    errors = []
    try:
        import fitz
    except Exception as e:
        return "", {"status":"failed","method_used":"ocr_pymupdf+tesseract","total_chars":0,"pages_with_text":0,"errors":[f"pymupdf missing: {e}"]}

    try:
        import pytesseract
        from PIL import Image
        import io
    except Exception as e:
        return "", {"status":"failed","method_used":"ocr_pymupdf+tesseract","total_chars":0,"pages_with_text":0,"errors":[f"pytesseract/pillow missing: {e}"]}

    doc = fitz.open(str(pdf_path))
    n = doc.page_count
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
    return text, {
        "status": "ok" if text else "failed",
        "method_used": "ocr_pymupdf+tesseract",
        "total_chars": len(text),
        "pages_with_text": pages_with_text,
        "errors": errors,
    }

# =========================
# LLM summarization (integrate existing API call)
# =========================
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
    
    system_prompt = (
        "You are a professional institutional-market research analyst writing summaries for active traders.\n\n"
        "CRITICAL RULES (MANDATORY):\n"
        "1. You MUST NOT invent or assume numerical price levels, targets, strike prices, support/resistance, or entry points unless they are EXPLICITLY stated in the source document.\n"
        "2. You MUST NOT use generic or outdated market prices.\n"
        "3. If a trade idea is IMPLIED directionally but NO price level is stated, you MUST express it as a directional or conditional thesis (e.g., \"bullish bias\", \"relative strength\", \"risk skewed higher\"), NOT as a price trigger.\n"
        "4. If the document contains NO clear implication for a section, explicitly write \"(none)\" for that section.\n\n"
        "ABSOLUTE NUMERIC BAN:\n"
        "- You may NOT output ANY numeric price, level, strike, target, or threshold unless it appears verbatim in the source document.\n"
        "- If a trade idea is directional but has no explicit numeric level, output it WITHOUT numbers (e.g., \"bullish bias on U.S. equities\").\n"
        "- If a trade idea would require inventing a price, OMIT it.\n\n"
        "WHAT COUNTS AS A VALID TRADE IDEA:\n"
        "• Directional bias (bullish / bearish / neutral)\n"
        "• Relative preference (e.g., \"prefer U.S. equities over EM\")\n"
        "• Conditional macro logic (e.g., \"if foreign inflows persist, equities supported\")\n"
        "• Cross-asset implications (rates vs equities, dollar vs metals, etc.)\n\n"
        "WHAT DOES NOT COUNT:\n"
        "• Made-up price levels\n"
        "• Generic technical analysis\n"
        "• Market knowledge outside the document\n"
        "• \"Common sense\" trades not supported by text\n\n"
        "OUTPUT FORMAT (STRICT):\n\n"
        "Title (filename)\n\n"
        "TL;DR\n"
        "• 3 concise bullets summarizing the document's CORE thesis\n\n"
        "TRADE IDEAS\n"
        "• Bullet points ONLY if the document clearly implies a trade or positioning bias\n"
        "• Use words like: \"bullish bias\", \"bearish tilt\", \"supports\", \"headwind\", \"tailwind\", \"relative strength\"\n"
        "• NO prices unless explicitly stated in the document\n"
        "• If none: write \"• (none)\"\n\n"
        "STOCKS\n"
        "• Equities or sectors ONLY if mentioned or clearly implied\n"
        "• Directional or relative language ONLY\n"
        "• If none: write \"• (none)\"\n\n"
        "OTHER FUTURES\n"
        "• Rates, commodities, crypto, volatility, etc.\n"
        "• Directional or relative language ONLY\n"
        "• If none: write \"• (none)\"\n\n"
        "FOREX\n"
        "• Dollar, crosses, EM FX, etc.\n"
        "• Directional or relative language ONLY\n"
        "• If none: write \"• (none)\"\n\n"
        "OTHER\n"
        "• Anything not fitting above (flows, positioning, regime shifts)\n"
        "• If none: write \"• (none)\"\n\n"
        "FINAL SAFETY CHECK (DO NOT SKIP):\n"
        "Before answering, verify:\n"
        "- No invented numbers\n"
        "- No outdated market levels\n"
        "- Every trade idea is traceable to the document text\n\n"
        "Output MUST be valid JSON only. No markdown, no explanations, just JSON."
    )
    
    extra_guidance = ""
    if extra_instructions:
        extra_guidance = f"\nRETRY GUIDANCE:\n{extra_instructions}\n"

    user_prompt = (
        "Create a trader-focused summary. Return ONLY valid JSON with this EXACT structure:\n\n"
        "CRITICAL: The following fields are used downstream by daily rollups. Be concise and deterministic. Use short bullets, no prose paragraphs, consistent phrasing, no stylistic writing.\n\n"
        "{\n"
        '  "what_moved_today": ["Past tense: what happened + numeric impact if stated", ...],\n'
        '  "what_can_move_tomorrow": ["Forward-looking: catalyst + conditional setup", ...],\n'
        '  "products": {\n'
        '    "indices": {\n'
        '      "ES": {"bias": "Bullish/Bearish/Neutral", "catalyst": "why", "setup": "If X then Y", "key_levels": ["exact quote from doc or (not provided in inputs)"], "source_quote": "exact sentence from document containing the level, or null", "risk": "invalidation", "time_horizon": "1-3D/1-2W/>2W"},\n'
        '      "NQ": {...}\n'
        "    },\n"
        '    "rates": {\n'
        '      "ZN": {...},\n'
        '      "ZB": {...}\n'
        "    },\n"
        '    "metals": {\n'
        '      "GC": {...},\n'
        '      "SI": {...}\n'
        "    },\n"
        '    "crypto": {\n'
        '      "BTC": {...}\n'
        "    },\n"
        '    "others": {\n'
        '      "VIX": {...},\n'
        '      "CL": {...}\n'
        "    }\n"
        "  },\n"
        '  "volatility_impact": {\n'
        '    "expected_volatility": "Low/Medium/High",\n'
        '    "drivers": ["rate decision uncertainty", "event clustering", "FX policy divergence"],\n'
        '    "directional_skew": "Upside/Downside/Two-sided",\n'
        '    "confidence_0_100": 70\n'
        "  },\n"
        '  "tldr": ["Event → impact → assets affected", ...],\n'
        '  "what_occurred": ["Factual past events with numbers if stated", ...],\n'
        '  "forward_watch": ["Upcoming catalysts/events", ...],\n'
        '  "warnings": ["Risk factors", ...],\n'
        '  "tips_reminders": ["Educational context", ...],\n'
        '  "cross_asset_impacts": ["How X affects Y", ...],\n'
        '  "scenarios": ["If/Then scenarios", ...],\n'
        '  "sentiment_indicator": {\n'
        '    "risk_on_off": "Risk-On/Risk-Off/Mixed",\n'
        '    "confidence_0_100": 75,\n'
        '    "rationale": "Why this sentiment (reference article only)"\n'
        "  },\n"
        '  "explain_like_refresher": "One key concept from article + how it impacts indices/rates/metals (or \'(not provided in inputs)\' if none)",\n'
        '  "score_0_10": 7,\n'
        '  "chart_score_0_3": 2\n'
        "}\n\n"
        "CRITICAL ANTI-HALLUCINATION RULES (HARD CONSTRAINTS):\n"
        "1. NEVER invent numeric values (prices, yields, %, dates, times). Copy EXACTLY from document or write '(not provided in inputs)'.\n"
        "2. key_levels MUST be a list of exact quotes from document. If none stated, use ['(not provided in inputs)'].\n"
        "3. PRICE LEVELS (CRITICAL): You must NOT invent, estimate, update, or infer numeric price levels.\n"
        "   - You may ONLY include price levels if they appear verbatim in the source document.\n"
        "   - If an actionable idea does NOT contain explicit price levels in the source, you MUST write: 'no explicit levels provided'.\n"
        "   - Do NOT use current market prices or general knowledge.\n"
        "   - Do NOT normalize, modernize, or adjust levels.\n"
        "   - Do NOT interpolate between mentioned levels.\n"
        "   - If the document says '$26.40', write exactly '$26.40' (with dollar sign and decimal).\n"
        "   - If the document mentions no price, write '(not provided in inputs)'.\n"
        "4. what_moved_today: Past tense events ONLY. If numeric impact stated, include it verbatim.\n"
        "5. what_can_move_tomorrow: Forward-looking catalysts. Use conditionals (If/When/Should).\n"
        "\n"
        "PRODUCT STRUCTURE (HARD-ENFORCED ORDER):\n"
        "5. products MUST follow this exact structure: indices (ES, NQ) → rates (ZN, ZB) → metals (GC, SI) → crypto (BTC) → others (VIX, CL).\n"
        "6. ALL categories MUST exist even if empty. If article doesn't affect a product: {\"bias\": \"Neutral\", \"catalyst\": \"No direct trade idea from this article\", \"setup\": \"\", \"key_levels\": [\"(not provided in inputs)\"], \"source_quote\": null, \"risk\": \"\", \"time_horizon\": \"\"}.\n"
        "7. source_quote: REQUIRED field. If key_levels contains a price level (contains $ or numeric), source_quote MUST be the exact sentence from the document that contains that level. If no level exists, source_quote MUST be null. This enables validation that levels are not hallucinated.\n"
        "8. This structure guarantees consistent PDFs, deterministic rollups, zero formatting drift.\n"
        "\n"
        "VOLATILITY IMPACT (CRITICAL FOR IB CLIENTS):\n"
        "9. volatility_impact MUST be present. This is THE MOST IMPORTANT field for clients.\n"
        "10. expected_volatility: Assess Low/Medium/High based on article catalysts, event clustering, uncertainty.\n"
        "11. drivers: List 2-4 specific volatility drivers from article (e.g., 'rate decision uncertainty', 'FX policy divergence').\n"
        "12. directional_skew: Upside (bullish vol), Downside (bearish vol), or Two-sided (uncertain direction).\n"
        "13. confidence_0_100: How confident are you in this volatility assessment based on article content.\n"
        "\n"
        "MACHINE-FRIENDLY OUTPUT (DAILY ROLLUP DEPENDENCY):\n"
        "14. Use SHORT BULLETS only. NO prose paragraphs. Daily aggregation depends on this.\n"
        "15. Use CONSISTENT PHRASING. Avoid stylistic variation. Be deterministic.\n"
        "16. sentiment_indicator: ALWAYS present. Analyze article tone. If unclear, use Mixed + low confidence.\n"
        "17. explain_like_refresher: Pick ONE concept discussed + explain impact. If none, write '(not provided in inputs)'.\n"
        "\n"
        "MINIMUM CONTENT REQUIREMENTS:\n"
        "18. what_moved_today: 3-5 bullets.\n"
        "19. what_can_move_tomorrow: 3-5 bullets.\n"
        "20. tldr: EXACTLY 3 bullets.\n"
        "21. Do NOT reuse the same bullet wording across sections.\n"
        "\n"
        "QUALITY RULES (AVOID GENERIC FILLER):\n"
        "22. NO repeated bullets. Each bullet must be unique.\n"
        "23. NO placeholder phrases: 'pending analysis', 'monitor key levels', 'data releases', 'await further information', 'to be determined', 'subject to change'.\n"
        "24. NO suspiciously short bullets (< 20 chars). Be specific.\n"
        "25. tldr: EXACTLY 3 bullets. Focus on tradable catalysts, not generic macro.\n"
        "26. If article has minimal trading relevance, be honest: compress to 1-2 bullets in 'what_occurred' + set score_0_10 low.\n"
        "27. score_0_10: Rate trading usefulness (0=useless, 10=critical). Be honest.\n"
        "28. chart_score_0_3: Count charts/tables (0=none, 1=few, 2=several, 3=chart-heavy).\n\n"
        f"{extra_guidance}"
        f"DOCUMENT TEXT:\n<<<\n{text}\n>>>"
    )
    
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
    
    # Strip markdown code blocks
    cleaned = out_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    
    api_response = json.loads(cleaned.strip())
    
    # Convert API response to new trader-focused schema
    provider = meta.get("provider", "O")
    published_date = meta.get("published_date", "")
    horizon = meta.get("horizon", "")
    
    # Extract from new trader-focused API response
    what_moved_today = api_response.get("what_moved_today", [])
    what_can_move_tomorrow = api_response.get("what_can_move_tomorrow", [])
    tldr = api_response.get("tldr", [])
    what_occurred = api_response.get("what_occurred", [])
    forward_watch = api_response.get("forward_watch", [])
    warnings = api_response.get("warnings", [])
    tips_reminders = api_response.get("tips_reminders", [])
    cross_asset_impacts = api_response.get("cross_asset_impacts", [])
    scenarios = api_response.get("scenarios", [])
    
    # Extract structured products (new format: indices/rates/metals/crypto/others)
    products_structured = api_response.get("products", {})
    
    # Extract volatility impact (CRITICAL for IB clients)
    volatility_impact = api_response.get("volatility_impact", {
        "expected_volatility": "Medium",
        "drivers": ["(not provided in inputs)"],
        "directional_skew": "Two-sided",
        "confidence_0_100": 50
    })
    
    sentiment_indicator = api_response.get("sentiment_indicator", {
        "risk_on_off": "Neutral",
        "confidence_0_100": 50,
        "rationale": "(not provided in inputs)"
    })
    explain_like_refresher = api_response.get("explain_like_refresher", "(not provided in inputs)")
    score = api_response.get("score_0_10", 0)
    chart_score = api_response.get("chart_score_0_3", 0)
    
    # Flatten products from structured format to list (for backward compatibility)
    all_products = []
    for category in ["indices", "rates", "metals", "crypto", "others"]:
        if category in products_structured:
            all_products.extend(products_structured[category].keys())
    products = all_products
    
    # Generate theme from first TL;DR bullet if needed
    theme = ""
    if tldr and isinstance(tldr, list) and len(tldr) > 0:
        first_tldr = tldr[0] if isinstance(tldr[0], str) else str(tldr[0])
        words = first_tldr.split()
        theme = " ".join(words[:22])
    
    # Convert structured products to list format for storage (preserving hard-enforced order)
    # Order: Indices → Rates → Metals → Crypto → Others
    trade_ideas_list = []
    
    # Define product order (hard-enforced)
    product_order = [
        ("indices", ["ES", "NQ"]),
        ("rates", ["ZN", "ZB"]),
        ("metals", ["GC", "SI"]),
        ("crypto", ["BTC"]),
        ("others", ["VIX", "CL"])
    ]
    
    # Process products in hard-enforced order
    for category, product_list in product_order:
        category_data = products_structured.get(category, {})
        for product in product_list:
            if product in category_data:
                idea_data = category_data[product]
            else:
                # Create default entry if not present (maintain structure)
                idea_data = {
                    "bias": "Neutral",
                    "catalyst": "No direct trade idea from this article",
                    "setup": "",
                    "key_levels": ["(not provided in inputs)"],
                    "source_quote": None,
                    "risk": "",
                    "time_horizon": ""
                }
            
            if isinstance(idea_data, dict):
                # Ensure key_levels is a list
                key_levels = idea_data.get("key_levels", ["(not provided in inputs)"])
                if isinstance(key_levels, str):
                    key_levels = [key_levels] if key_levels else ["(not provided in inputs)"]
                
                # Extract source_quote for validation
                source_quote = idea_data.get("source_quote")
                if source_quote is None or source_quote == "":
                    source_quote = None
                
                trade_ideas_list.append({
                    "product": product,
                    "category": category,
                    "bias": idea_data.get("bias", "Neutral"),
                    "catalyst": idea_data.get("catalyst", ""),
                    "setup": idea_data.get("setup", ""),
                    "key_levels": key_levels,
                    "source_quote": source_quote,
                    "risk": idea_data.get("risk", ""),
                    "time_horizon": idea_data.get("time_horizon", ""),
                    "sources": [provider]
                })
    
    return {
        "schema_version": SCHEMA_SUM_V1,
        "kind": "article",
        "meta": {
            "title": meta.get("title", ""),
            "provider": provider,
            "published_date": published_date,
            "horizon": horizon,
            "products": products,
            "theme": theme,
            "generated_at_iso": _iso_now(),
            "model": model
        },
        "ui": {
            "header_pills": [
                {"text": provider, "type": "provider"},
                {"text": published_date, "type": "date"},
                {"text": horizon, "type": "horizon"},
                {"text": f"{score}/10", "type": "score"}
            ]
        },
        "extraction": meta.get("extraction", {}),
        "sections": {
            "what_moved_today": [{"text": t, "sources": [provider]} for t in (what_moved_today if isinstance(what_moved_today, list) else [])],
            "what_can_move_tomorrow": [{"text": t, "sources": [provider]} for t in (what_can_move_tomorrow if isinstance(what_can_move_tomorrow, list) else [])],
            "trade_ideas": trade_ideas_list,
            "tldr": [{"text": t, "sources": [provider]} for t in (tldr[:3] if isinstance(tldr, list) else [])],
            "what_occurred": [{"text": t, "sources": [provider]} for t in (what_occurred if isinstance(what_occurred, list) else [])],
            "forward_watch": [{"text": t, "sources": [provider]} for t in (forward_watch if isinstance(forward_watch, list) else [])],
            "warnings": [{"text": t, "sources": [provider]} for t in (warnings if isinstance(warnings, list) else [])],
            "tips_reminders": [{"text": t, "sources": [provider]} for t in (tips_reminders if isinstance(tips_reminders, list) else [])],
            "cross_asset_impacts": [{"text": t, "sources": [provider]} for t in (cross_asset_impacts if isinstance(cross_asset_impacts, list) else [])],
            "scenarios": [{"text": t, "sources": [provider]} for t in (scenarios if isinstance(scenarios, list) else [])]
        },
        "volatility_impact": volatility_impact,
        "sentiment_indicator": sentiment_indicator,
        "explain_like_refresher": explain_like_refresher,
        "summary_score_0_10": score,
        "chart_score_0_3": chart_score
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
) -> dict:
    """
    Summarize plain text and ALWAYS emit JSON+TXT.
    Used by rollups and OCR-to-text flows. No OCR here (ZERO-OCR RULE).
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
            "total_chars": len(text),
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
    _write_txt(txt_path, render_sum_txt(sum_json))
    return sum_json

def summarize_pdf(
    pdf_path: Path,
    *,
    out_dir: Optional[Path] = None,
    model: str = "gpt-4o-mini",
    allow_ocr: bool = True,  # ZERO-OCR RULE: False for rollups/internal
) -> dict:
    """
    External ingestion: PDF -> extract text -> (optional OCR) -> summarize -> ALWAYS JSON+TXT.
    
    ZERO-OCR RULE: Set allow_ocr=False for internal summaries/rollups.
    """
    pdf_path = Path(pdf_path)
    out_dir = out_dir or pdf_path.parent
    json_path, txt_path = _sum_paths(pdf_path, out_dir=out_dir)

    # Extract
    text, extraction = extract_text(pdf_path)

    # Optional OCR if extraction insufficient (ONLY for external PDFs)
    used_ocr = False
    if allow_ocr and (len(text) < MIN_TEXT_CHARS):
        ocr_text, ocr_extraction = ocr_to_text(pdf_path, dpi=300, max_pages=None)
        if len(ocr_text) > len(text):
            text = ocr_text
            extraction = ocr_extraction
            used_ocr = True

    # Parse metadata from filename
    filename = pdf_path.stem
    provider = "O"
    for prefix, code in [("BOA_", "BOA"), ("DB_", "DB"), ("MUFG_", "MUFG")]:  # Add more as needed
        if filename.startswith(prefix):
            provider = code
            break
    
    date_match = re.search(r'(\d{8})', filename)
    published_date = date_match.group(1) if date_match else ""
    
    meta = {
        "title": filename,
        "provider": provider,
        "published_date": published_date,
        "horizon": "u",
        "products": [],
        "generated_at_iso": _iso_now(),
        "model": model,
        "used_ocr": used_ocr,
        "extraction": extraction
    }

    if not text.strip() or len(text) < MIN_TEXT_CHARS:
        sum_json = _failed_stub(
            pdf_path,
            reason=f"All extraction methods produced insufficient text (chars={len(text)}).",
            extraction=extraction,
            meta=meta,
        )
        _write_json(json_path, sum_json)
        _write_txt(txt_path, render_sum_txt(sum_json))
        return sum_json

    # Summarize with quality retry (model escalation)
    try:
        sum_json = _summarize_with_quality_retry(
            text,
            meta=meta,
            model=model,
            pdf_path=pdf_path,
            out_dir=out_dir,
            apply_format_fix=True,
        )
    except Exception as e:
        sum_json = _failed_stub(pdf_path, reason=str(e), extraction=extraction, meta=meta)
    
    _write_json(json_path, sum_json)
    _write_txt(txt_path, render_sum_txt(sum_json))
    return sum_json
