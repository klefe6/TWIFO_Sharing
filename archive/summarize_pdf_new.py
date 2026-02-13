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

# Load API key from environment (set by db_filter_autorun.py)
# Note: Do NOT read .env directly here to avoid silent overrides
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
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
    
    # Collect all text bullets from sections
    all_bullets = []
    for key in ["tldr", "what_occurred", "forward_watch", "warnings", "tips_reminders", 
                "cross_asset_impacts", "scenarios", "stocks", "other_futures", "forex", "other"]:
        items = sections.get(key, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    text = item.get("text", "").strip().lower()
                    if text:
                        all_bullets.append(text)
                elif isinstance(item, str):
                    text = item.strip().lower()
                    if text:
                        all_bullets.append(text)
    
    # Also check trade_ideas if they exist
    trade_ideas = sections.get("trade_ideas", [])
    for item in trade_ideas:
        if isinstance(item, dict):
            for field in ["catalyst", "setup", "key_levels", "risk", "trigger"]:
                text = item.get(field, "").strip().lower()
                if text:
                    all_bullets.append(text)
    
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


def render_sum_txt(sum_json: dict) -> str:
    """
    Human-readable TXT mirror of the JSON.
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
    meta = sum_json.get("meta", {})
    prov = meta.get("provider", "")
    date = meta.get("published_date", "")
    horizon = meta.get("horizon", "")
    title = meta.get("title", "")

    def bullet_lines(items: list, prefix="- "):
        out = []
        for it in items:
            if isinstance(it, dict):
                src = it.get("sources", [])
                src_txt = f" ({', '.join(src)})" if src else ""
                out.append(f"{prefix}{it.get('text','').strip()}{src_txt}")
            else:
                out.append(f"{prefix}{str(it).strip()}")
        return "\n".join(out)

    s = sum_json.get("sections", {})
    trade_ideas = s.get("trade_ideas", [])

    trade_lines = []
    for ti in trade_ideas:
        trade_lines.append(
            f"- {ti.get('direction','').upper()} {ti.get('instrument','')} | "
            f"{ti.get('trigger','')} | horizon={ti.get('horizon','')} | "
            f"conf={ti.get('confidence_0_100','')} | sources={','.join(ti.get('sources',[]))}"
        )

    return f"""TITLE: {title}
PROVIDER: {prov}
DATE: {date}
HORIZON: {horizon}

TL;DR
{bullet_lines(s.get("tldr", []))}

WHAT OCCURRED
{bullet_lines(s.get("what_occurred", []))}

FORWARD WATCH
{bullet_lines(s.get("forward_watch", []))}

TRADE IDEAS
{'\n'.join(trade_lines) if trade_lines else '- (none)'}

WARNINGS
{bullet_lines(s.get("warnings", []))}

TIPS & REMINDERS
{bullet_lines(s.get("tips_reminders", []))}

CROSS-ASSET IMPACTS
{bullet_lines(s.get("cross_asset_impacts", []))}

SCENARIOS
{bullet_lines(s.get("scenarios", []))}
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
    print(f"[DEBUG] LLM call: model={model}, key_prefix={prefix}, base_url={base_url}")
    
    system_prompt = (
        "You are a professional sell-side research distillation engine for an active multi-asset trader. "
        "Extract ONLY actionable, market-relevant intelligence. Output MUST be valid JSON only."
    )
    
    user_prompt = (
        "Create a trader-focused summary. Return STRICT JSON with structure:\n"
        '{"core_summary": {"tldr": [], "actionable": [], "tips_and_reminders": []}, '
        '"per_product": {}, "self_evaluation": {"summary_score_0_10": 0, "score_breakdown": {}}, '
        '"time_separation": {}, "market_framing": {"products": []}}\n\n'
        f"DOCUMENT TEXT:\n<<<\n{text}\n>>>"
    )
    
    # Call OpenAI API using unified client
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_output_tokens=900,
    )
    
    # Extract text from response
    out_text = ""
    for item in response.output:
        for content_item in item.content:
            if content_item.type == "output_text":
                out_text += content_item.text
    
    if not out_text:
        raise ValueError("API returned empty output text")
    
    # Strip markdown code blocks
    cleaned = out_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    
    api_response = json.loads(cleaned.strip())
    
    # Convert API response to twifo.sum.v1 schema
    provider = meta.get("provider", "O")
    published_date = meta.get("published_date", "")
    horizon = meta.get("horizon", "")
    products = meta.get("products", [])
    
    # Extract from API response
    core_summary = api_response.get("core_summary", {})
    per_product = api_response.get("per_product", {})
    market_framing = api_response.get("market_framing", {})
    
    # Build trade ideas from per_product
    trade_ideas = []
    for product_name, product_data in per_product.items():
        direction = product_data.get("bias", "neutral")
        if direction == "neutral":
            continue  # Skip neutral - not a trade idea
        
        # Extract trigger from forward_catalysts
        triggers = product_data.get("forward_catalysts", [])
        trigger = triggers[0] if triggers else "Not specified"
        
        # Determine horizon from time_separation or default
        time_sep = api_response.get("time_separation", {})
        horizon_val = horizon or "1–3D"  # Default
        
        trade_ideas.append({
            "direction": "long" if "bull" in direction.lower() else "short",
            "instrument": product_name,
            "setup": "; ".join(product_data.get("past_drivers", [])[:2]),
            "trigger": trigger,
            "horizon": horizon_val,
            "invalidation": "; ".join(product_data.get("risks", [])[:2]),
            "confidence_0_100": product_data.get("confidence_0_100", 50),
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
            "products": products or market_framing.get("products", []),
            "generated_at_iso": _iso_now(),
            "model": model
        },
        "ui": {
            "header_pills": [
                {"text": provider, "type": "provider"},
                {"text": published_date, "type": "date"},
                {"text": horizon, "type": "horizon"}
            ]
        },
        "extraction": meta.get("extraction", {}),
        "sections": {
            "tldr": [{"text": t, "sources": [provider]} for t in core_summary.get("tldr", [])],
            "what_occurred": [{"text": t, "sources": [provider]} for t in core_summary.get("actionable", [])[:5]],
            "forward_watch": [{"text": t, "sources": [provider]} for t in core_summary.get("tips_and_reminders", [])[:5]],
            "trade_ideas": trade_ideas,
            "warnings": [],
            "tips_reminders": [{"text": t, "sources": [provider]} for t in core_summary.get("tips_and_reminders", [])[5:]],
            "cross_asset_impacts": [],
            "scenarios": []
        }
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
        sum_json = llm_summarize_to_json(text, meta=meta, model=model)
    except Exception as e:
        sum_json = _failed_stub(fake_pdf, reason=str(e), extraction=meta["extraction"], meta=meta)

    # Quality gate: detect low-quality/templated output
    is_low_quality, quality_reason = is_low_quality_summary(sum_json)
    if is_low_quality:
        print(f"[QUALITY GATE] Summary failed quality check: {quality_reason}")
        # Preserve meta but mark as failed and use unified failure stub
        sum_json["extraction"]["status"] = "failed"
        sum_json["extraction"]["reason"] = f"low_quality_output: {quality_reason}"
        # Replace sections with empty unified failure stub
        sum_json["sections"] = {
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

    # Summarize
    try:
        sum_json = llm_summarize_to_json(text, meta=meta, model=model)
    except Exception as e:
        sum_json = _failed_stub(pdf_path, reason=str(e), extraction=extraction, meta=meta)

    # Quality gate: detect low-quality/templated output
    is_low_quality, quality_reason = is_low_quality_summary(sum_json)
    if is_low_quality:
        print(f"[QUALITY GATE] Summary failed quality check: {quality_reason}")
        # Preserve meta but mark as failed and use unified failure stub
        sum_json["extraction"]["status"] = "failed"
        sum_json["extraction"]["reason"] = f"low_quality_output: {quality_reason}"
        # Replace sections with empty unified failure stub
        sum_json["sections"] = {
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

    _write_json(json_path, sum_json)
    _write_txt(txt_path, render_sum_txt(sum_json))
    return sum_json

