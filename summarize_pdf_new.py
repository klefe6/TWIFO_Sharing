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

# Load API key (reuse existing logic)
def load_api_key() -> str | None:
    """Load OPENAI_API_KEY from multiple sources."""
    script_dir = Path(__file__).parent
    
    # Try .env file
    try:
        from dotenv import load_dotenv
        env_file = script_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            key = os.getenv("OPENAI_API_KEY")
            if key:
                return key
    except ImportError:
        pass
    
    # Try .env manually
    env_file = script_dir / ".env"
    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('OPENAI_API_KEY='):
                        key = line.split('=', 1)[1].strip().strip('"').strip("'")
                        if key:
                            return key
        except Exception:
            pass
    
    # Try environment variable
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    
    return None

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = load_api_key()

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

def render_sum_txt(sum_json: dict) -> str:
    """Human-readable TXT mirror of the JSON."""
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
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set")
    
    if not text.strip():
        raise ValueError("No text provided to summarizer")

    import requests
    
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    
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
    
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_output_tokens": 900,
    }
    
    r = requests.post(
        "https://api.openai.com/v1/responses",
        headers=headers,
        json=payload,
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    
    out_text = ""
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                out_text += c.get("text", "")
    
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

    _write_json(json_path, sum_json)
    _write_txt(txt_path, render_sum_txt(sum_json))
    return sum_json

