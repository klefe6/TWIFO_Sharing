"""
Reusable PDF summarization module for TWIFO research files.

This module provides functions to:
- Check if a PDF should be summarized (skips Chart Books)
- Extract text from PDFs
- Generate trader-focused summaries
- Detect and categorize products (Metals, Energy, Crypto, etc.)
"""

import os
import json
import re
from pathlib import Path
from typing import Optional

import requests
from PyPDF2 import PdfReader

# Load API key using the same method as test_summarize_one.py
def load_api_key() -> str:
    """Load OPENAI_API_KEY from .env, environment variables, or config.txt"""
    script_dir = Path(__file__).parent
    
    # Method 1: Try .env file
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
    
    # Method 2: Try .env file manually
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
    
    # Method 3: Environment variable
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    
    # Method 4: config.txt
    config_file = script_dir / "config.txt"
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if 'OPENAI_API_KEY' in line:
                        key = line.split('=', 1)[1].strip().strip('"').strip("'")
                        if key:
                            return key
        except Exception:
            pass
    
    return None


# Configuration
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_PAGES_TO_SCAN = 12
MAX_OUTPUT_TOKENS = 900
OPENAI_API_KEY = load_api_key()


# Product category mapping
PRODUCT_CATEGORIES = {
    "Metals": {
        "keywords": ["gold", "silver", "copper", "platinum", "palladium", "zinc", "aluminum", "aluminium", "nickel", "tin", "lead"],
        "specific": ["xau", "xag", "gc", "si", "hg", "hg", "pa", "pl"]
    },
    "Energy": {
        "keywords": ["oil", "crude", "wti", "brent", "natural gas", "nat gas", "gasoline", "heating oil", "diesel", "ng"],
        "specific": ["cl", "b", "rb", "ho", "ng"]
    },
    "Crypto": {
        "keywords": ["bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency", "digital asset"],
        "specific": ["btc", "eth", "usdt", "usdc"]
    },
    "Rates": {
        "keywords": ["rates", "yield", "treasury", "bond", "sofr", "fed funds", "interest rate", "yield curve"],
        "specific": ["tn", "zn", "zb", "ub", "sofr", "ff"]
    },
    "FX": {
        "keywords": ["fx", "forex", "currency", "dollar", "euro", "yen", "pound", "sterling", "dxy", "usd", "eur", "jpy", "gbp", "chf", "cad"],
        "specific": ["usd", "eur", "jpy", "gbp", "chf", "cad", "aud", "nzd", "dxy"]
    },
    "Equity Indices": {
        "keywords": ["s&p", "spx", "sp500", "nasdaq", "dow", "dax", "ftse", "nikkei", "equity", "stock index", "es", "nq", "ym"],
        "specific": ["es", "nq", "ym", "rt", "rty"]
    },
    "Agriculture": {
        "keywords": ["wheat", "corn", "soybean", "cotton", "sugar", "coffee", "cocoa", "livestock", "cattle", "hogs"],
        "specific": ["zw", "zc", "zs", "ct", "sb", "kc", "cc", "lc", "he", "gf"]
    }
}


def should_skip_summary(filename: str) -> bool:
    """
    Check if a PDF should be skipped for summarization.
    Returns True if filename contains "Chart Book" or "Chartbook" (case-insensitive).
    Handles spaces, underscores, and other separators.
    """
    filename_lower = filename.lower()
    # Normalize separators (spaces, underscores, hyphens) to spaces for matching
    normalized = filename_lower.replace("_", " ").replace("-", " ")
    # Check for "chart book" or "chartbook" (without separator)
    return "chart book" in normalized or "chartbook" in normalized or "chartbook" in filename_lower


def categorize_products(products: list[str]) -> dict[str, list[str]]:
    """
    Categorize products into groups (Metals, Energy, Crypto, etc.).
    Returns: {"Metals": ["gold", "silver"], "Energy": ["oil"], ...}
    """
    categorized = {}
    text_lower = " ".join(products).lower()
    
    for category, patterns in PRODUCT_CATEGORIES.items():
        found_products = []
        
        # Check keywords
        for keyword in patterns["keywords"]:
            if keyword.lower() in text_lower:
                found_products.append(keyword)
        
        # Check specific tickers/symbols
        for symbol in patterns["specific"]:
            # Use word boundaries to avoid false matches
            pattern = r'\b' + re.escape(symbol.lower()) + r'\b'
            if re.search(pattern, text_lower):
                found_products.append(symbol.upper())
        
        if found_products:
            categorized[category] = list(set(found_products))  # Remove duplicates
    
    return categorized


def strip_trailing_boilerplate(text: str) -> str:
    """Strip legal disclaimers and boilerplate from end of text."""
    # Common "start of boilerplate" markers
    markers = [
        r"\bnotice\b",
        r"\bdisclaimer\b",
        r"\bconfidential\b",
        r"\bfor\s+institutional\s+investors\b",
        r"\banalyst\s+certification\b",
        r"\bimportant\s+disclosures\b",
        r"\brisk\s+warnings?\b",
    ]
    
    combined_pattern = "|".join(markers)
    match = re.search(combined_pattern, text, re.IGNORECASE)
    if match:
        text = text[:match.start()].rstrip()
    
    return text


def extract_text(pdf_path: Path, max_pages: int = MAX_PAGES_TO_SCAN) -> str:
    """Extract text from first N pages of PDF with error handling."""
    try:
        reader = PdfReader(str(pdf_path), strict=False)
        parts = []

        for i, page in enumerate(reader.pages[:max_pages]):
            try:
                text = page.extract_text() or ""
                parts.append(text)
            except Exception as e:
                print(f"Warning: Could not extract text from page {i+1}: {e}")
                parts.append("")

        txt = "\n".join(parts)
        txt = re.sub(r"\s+", " ", txt).strip()
        
        if not txt or len(txt) < 50:
            raise ValueError(f"Extracted text too short or empty ({len(txt)} chars). PDF may be image-based or corrupted.")
        
        return txt
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from PDF {pdf_path.name}: {e}")


def summarize_pdf(pdf_path: Path, max_pages: int = MAX_PAGES_TO_SCAN) -> Optional[dict]:
    """
    Summarize a PDF file. Returns summary dict or None if skipped/failed.
    
    Args:
        pdf_path: Path to PDF file
        max_pages: Maximum pages to extract text from
    
    Returns:
        Summary dictionary with product categories, or None if skipped/error
    """
    # Check if should skip (Chart Books)
    if should_skip_summary(pdf_path.name):
        print(f"[SKIP] Chart Book detected, skipping summarization: {pdf_path.name}")
        return None
    
    if not OPENAI_API_KEY:
        print(f"[ERROR] OPENAI_API_KEY not found. Cannot summarize {pdf_path.name}")
        return None
    
    try:
        # Extract and clean text
        raw_text = extract_text(pdf_path, max_pages)
        clean_text = strip_trailing_boilerplate(raw_text)
        
        # Generate summary
        summary = _call_openai_api(clean_text)
        
        # Categorize products
        products = summary.get("products", [])
        if products:
            summary["product_categories"] = categorize_products(products)
        
        return summary
        
    except Exception as e:
        print(f"[ERROR] Failed to summarize {pdf_path.name}: {e}")
        return None


def _call_openai_api(text: str) -> dict:
    """Call OpenAI API to generate summary."""
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "You are a professional sell-side research distillation engine for an active multi-asset trader "
        "(futures, rates, FX, commodities, equity indices).\n\n"
        "Your job is to extract ONLY actionable, market-relevant intelligence from the provided text.\n\n"
        "STRICT RULES:\n"
        "- Use ONLY the supplied text. Do not infer, assume, or hallucinate.\n"
        "- IGNORE and EXCLUDE any legal, regulatory, compliance, analyst certification, "
        "disclaimer, definitions, glossary, or boilerplate sections.\n"
        "- If the text does not explicitly support a claim, omit it.\n"
        "- Be concise, numeric where possible, and trader-focused.\n"
        "- Prefer levels, flows, positioning, supply/demand, timing, and catalysts.\n"
        "- Do NOT repeat the document title.\n"
        "- Do NOT explain methodology.\n"
        "- Do NOT include commentary outside the requested JSON.\n"
        "- Output MUST be valid JSON only (no markdown, no prose, no code blocks).\n"
        "- Detect specific products mentioned: gold, silver, oil, bitcoin, rates, USD, EUR, ES, NQ, etc.\n"
        "- Include product categories: Metals, Energy, Crypto, Rates, FX, Equity Indices, Agriculture."
    )

    user_prompt = (
        "Create a trader-focused summary of the document below.\n\n"
        "Return STRICT JSON with exactly the following structure:\n\n"
        "{\n"
        '  "overall_bias": "bullish | bearish | neutral",\n'
        '  "products": [list of specific products mentioned: "gold", "silver", "oil", "bitcoin", "rates", "USD", "ES", etc.],\n'
        '  "per_product": {\n'
        '    "PRODUCT_NAME": {\n'
        '      "bias": "bullish | bearish | neutral",\n'
        '      "confidence_0_100": integer,\n'
        '      "key_levels": [price levels or ranges explicitly mentioned],\n'
        '      "catalysts": [concrete drivers or upcoming events],\n'
        '      "risks": [explicit downside or invalidation risks]\n'
        "    }\n"
        "  },\n"
        '  "tldr": [\n'
        '    "Max 5 bullets. One sentence each. Pure signal, no fluff."\n'
        "  ],\n"
        '  "actionable": [\n'
        '    "Max 7 bullets. Trade-relevant ideas or positioning implications."\n'
        "  ],\n"
        '  "time_horizon": "intraday | 1-3d | 1-2w"\n'
        "}\n\n"
        "CONSTRAINTS:\n"
        "- If a field cannot be supported by the text, return an empty array or null.\n"
        "- Do not fabricate levels, products, or catalysts.\n"
        "- Keep total verbosity LOW.\n"
        "- Prefer omission over speculation.\n"
        "- List ALL specific products mentioned (gold, silver, oil, bitcoin, rates, etc.).\n\n"
        f"DOCUMENT TEXT:\n<<<\n{text}\n>>>"
    )

    payload = {
        "model": MODEL,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_output_tokens": MAX_OUTPUT_TOKENS,
    }

    r = requests.post(
        "https://api.openai.com/v1/responses",
        headers=headers,
        json=payload,
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()

    # Extract output text
    out_text = ""
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                out_text += c.get("text", "")
    
    if not out_text:
        raise ValueError("API returned empty output text")
    
    # Strip markdown code blocks
    cleaned_text = out_text.strip()
    if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text[7:]
    elif cleaned_text.startswith("```"):
        cleaned_text = cleaned_text[3:]
    
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-3]
    
    cleaned_text = cleaned_text.strip()
    
    # Parse JSON
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"API response is not valid JSON: {e}\nResponse: {cleaned_text[:500]}")


def create_summary_file(pdf_path: Path, summary: dict) -> Path:
    """
    Save summary to JSON file.
    Returns path to created summary file.
    """
    # Save as filename__sum.json (matching the pattern expected by twifo.py)
    summary_file = pdf_path.parent / f"{pdf_path.stem}__sum.json"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary_file
