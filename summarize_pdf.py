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
    return {
        "schema_version": SCHEMA_SUM_V1,
        "kind": "article",
        "meta": {
            **meta,
            "generated_at_iso": _iso_now(),
            "model": meta.get("model", MODEL),
        },
        "ui": {"header_pills": []},
        "extraction": {**extraction, "status": "failed"},
        "sections": {
            "tldr": [{"text": f"Summary unavailable: {reason}", "sources": [meta.get("provider","O")]}],
            "what_occurred": [],
            "forward_watch": [],
            "trade_ideas": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        }
    }

def render_sum_txt(sum_json: dict) -> str:
    """
    Render summary in new trader-focused format (article template).
    """
    meta = sum_json.get("meta", {})
    title = meta.get("title", "")
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
        "Write like a trader: concise, specific, no generic macro lecture. Prefer numbers, levels, dates, and catalysts over adjectives. "
        "Output MUST be valid JSON only. No markdown, no explanations, just JSON."
    )
    
    user_prompt = (
        "Create a trader-focused summary. Return ONLY valid JSON with this EXACT structure:\n\n"
        "{\n"
        '  "tldr": ["Event → why it matters → impacted assets", ...],\n'
        '  "trade_ideas": {\n'
        '    "ES": {"bias": "Bull/Bear/Neutral", "catalyst": "text", "setup": "If/Then text", "key_levels": "text", "risk": "text", "time_horizon": "text"},\n'
        '    "NQ": {"bias": "Bull/Bear/Neutral", "catalyst": "text", "setup": "If/Then text", "key_levels": "text", "risk": "text", "time_horizon": "text"},\n'
        '    "GC": {"bias": "Bull/Bear/Neutral", "catalyst": "text", "setup": "If/Then text", "key_levels": "text", "risk": "text", "time_horizon": "text"},\n'
        '    "SI": {"bias": "Bull/Bear/Neutral", "catalyst": "text", "setup": "If/Then text", "key_levels": "text", "risk": "text", "time_horizon": "text"},\n'
        '    "VIX": {"bias": "Bull/Bear/Neutral", "catalyst": "text", "setup": "If/Then text", "key_levels": "text", "risk": "text", "time_horizon": "text"}\n'
        "  },\n"
        '  "stocks": ["If/Then trigger + ticker/sector + catalyst", ...],\n'
        '  "other_futures": ["CL: summary text", ...],\n'
        '  "forex": ["levels/conditions", ...],\n'
        '  "other": ["low relevance items", ...],\n'
        '  "score_0_10": 0,\n'
        '  "chart_score_0_3": 0\n'
        "}\n\n"
        "CRITICAL RULES:\n"
        "1. tldr: MAX 3 bullets. ONLY key geopolitical events + key monetary/fiscal policy events. Format: 'Event → why it matters → impacted assets'\n"
        "2. trade_ideas: MUST include ES, NQ, GC, SI, VIX keys (even if Neutral). If article doesn't affect a product, use: {\"bias\": \"Neutral\", \"catalyst\": \"No direct trade idea from this article\", \"setup\": \"\", \"key_levels\": \"\", \"risk\": \"\", \"time_horizon\": \"\"}\n"
        "3. Each trade idea MUST have all 6 fields: bias, catalyst, setup, key_levels, risk, time_horizon\n"
        "4. stocks: 3-8 bullets ONLY if strongly supported. Format: 'If/Then trigger + ticker/sector + key catalyst'\n"
        "5. other_futures: Only if relevant (CL, NG, ZN/ZB, HG, etc). Format: 'ProductName: summary text'\n"
        "6. forex: Only if relevant. 2-6 bullets with levels/conditions\n"
        "7. other: Everything else / lower relevance. Short bullets only\n"
        "8. Write like a trader: concise, specific, numbers/levels/dates over adjectives\n"
        "9. NO generic context paragraphs unless they directly change the trade plan\n"
        "10. If article has no actionable relevance, compress to 1-2 bullets in 'other'\n\n"
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
    
    # Convert API response to new trader-focused schema
    provider = meta.get("provider", "O")
    published_date = meta.get("published_date", "")
    horizon = meta.get("horizon", "")
    
    # Extract from new trader-focused API response
    tldr = api_response.get("tldr", [])
    trade_ideas_dict = api_response.get("trade_ideas", {})
    stocks = api_response.get("stocks", [])
    other_futures = api_response.get("other_futures", [])
    forex = api_response.get("forex", [])
    other = api_response.get("other", [])
    score = api_response.get("score_0_10", 0)
    chart_score = api_response.get("chart_score_0_3", 0)
    
    # Extract products from trade_ideas keys
    products = list(trade_ideas_dict.keys()) if trade_ideas_dict else []
    
    # Generate theme from first TL;DR bullet if needed
    theme = ""
    if tldr and isinstance(tldr, list) and len(tldr) > 0:
        first_tldr = tldr[0] if isinstance(tldr[0], str) else str(tldr[0])
        words = first_tldr.split()
        theme = " ".join(words[:22])
    
    # Convert trade_ideas dict to list format for storage (preserving structure)
    # ALWAYS include ES, NQ, GC, SI, VIX in that exact order, even if not in response
    trade_ideas_list = []
    priority_products = ["ES", "NQ", "GC", "SI", "VIX"]
    other_products = sorted([p for p in trade_ideas_dict.keys() if p not in priority_products])
    
    # Process priority products first (always include them)
    for product in priority_products:
        if product in trade_ideas_dict:
            idea_data = trade_ideas_dict[product]
        else:
            # Create default entry if not present
            idea_data = {"bias": "Neutral", "catalyst": "No direct trade idea from this article"}
        
        if isinstance(idea_data, dict):
            trade_ideas_list.append({
                "product": product,
                "bias": idea_data.get("bias", "Neutral"),
                "catalyst": idea_data.get("catalyst", ""),
                "setup": idea_data.get("setup", ""),
                "key_levels": idea_data.get("key_levels", ""),
                "risk": idea_data.get("risk", ""),
                "time_horizon": idea_data.get("time_horizon", ""),
                "sources": [provider]
            })
    
    # Process other products
    for product in other_products:
        idea_data = trade_ideas_dict[product]
        if isinstance(idea_data, dict):
            trade_ideas_list.append({
                "product": product,
                "bias": idea_data.get("bias", "Neutral"),
                "catalyst": idea_data.get("catalyst", ""),
                "setup": idea_data.get("setup", ""),
                "key_levels": idea_data.get("key_levels", ""),
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
            "tldr": [{"text": t, "sources": [provider]} for t in (tldr[:3] if isinstance(tldr, list) else [])],
            "trade_ideas": trade_ideas_list,
            "stocks": [{"text": t, "sources": [provider]} for t in (stocks[:8] if isinstance(stocks, list) else [])],
            "other_futures": [{"text": t, "sources": [provider]} for t in (other_futures if isinstance(other_futures, list) else [])],
            "forex": [{"text": t, "sources": [provider]} for t in (forex[:6] if isinstance(forex, list) else [])],
            "other": [{"text": t, "sources": [provider]} for t in (other if isinstance(other, list) else [])],
            "what_occurred": [],
            "forward_watch": [],
            "warnings": [],
            "tips_reminders": [],
            "cross_asset_impacts": [],
            "scenarios": []
        },
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

    # Validate and fix format
    try:
        from format_validator import validate_article_summary, fix_summary_format
        is_valid, violations = validate_article_summary(sum_json)
        if violations:
            print(f"[FORMAT] Fixing {len(violations)} format issues...")
            sum_json = fix_summary_format(sum_json)
    except ImportError:
        pass  # Validator not available, skip
    
    _write_json(json_path, sum_json)
    _write_txt(txt_path, render_sum_txt(sum_json))
    return sum_json
