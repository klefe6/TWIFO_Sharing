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
    
    # Method 1: Try .env file with python-dotenv
    try:
        from dotenv import load_dotenv
        env_file = script_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            key = os.getenv("OPENAI_API_KEY")
            if key:
                return key
    except ImportError:
        pass  # python-dotenv not installed, fall through to manual parsing
    except Exception as e:
        print(f"[WARN] Error loading .env with python-dotenv: {e}")
    
    # Method 2: Try .env file manually
    env_file = script_dir / ".env"
    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                found_key_line = False
                for line_num, line in enumerate(f, 1):
                    original_line = line
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    # Try multiple formats: OPENAI_API_KEY=, OPENAI_API_KEY =, etc.
                    if 'OPENAI_API_KEY' in line.upper():
                        found_key_line = True
                        # Handle various formats: OPENAI_API_KEY=value, OPENAI_API_KEY = value, etc.
                        if '=' in line:
                            parts = line.split('=', 1)
                            if len(parts) == 2:
                                key = parts[1].strip().strip('"').strip("'")
                                if key:
                                    return key
                                else:
                                    print(f"[WARN] OPENAI_API_KEY found in .env but value is empty (line {line_num}): {original_line.strip()}")
                        else:
                            print(f"[WARN] OPENAI_API_KEY found in .env but no '=' sign found (line {line_num}): {original_line.strip()}")
                if not found_key_line:
                    print(f"[WARN] .env file exists at {env_file} but no OPENAI_API_KEY line found.")
                    print(f"[DEBUG] First few lines of .env file:")
                    try:
                        with open(env_file, 'r', encoding='utf-8') as f2:
                            for i, debug_line in enumerate(f2, 1):
                                if i <= 5:  # Show first 5 lines
                                    print(f"  Line {i}: {repr(debug_line.strip())}")
                    except:
                        pass
        except Exception as e:
            print(f"[WARN] Error reading .env file at {env_file}: {e}")
    
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
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if 'OPENAI_API_KEY' in line:
                        key = line.split('=', 1)[1].strip().strip('"').strip("'")
                        if key:
                            return key
        except Exception as e:
            print(f"[WARN] Error reading config.txt: {e}")
    
    return None


# Configuration
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_PAGES_TO_SCAN = 12
MAX_OUTPUT_TOKENS = 900
OPENAI_API_KEY = load_api_key()


# Product category mapping with ticker codes
PRODUCT_CATEGORIES = {
    "E": {  # Energy
        "name": "Energy",
        "keywords": ["oil", "crude", "wti", "brent", "natural gas", "nat gas", "gasoline", "heating oil", "diesel", "ng"],
        "specific": ["cl", "b", "rb", "ho", "ng"],
        "ticker_map": {"oil": "CL", "crude": "CL", "wti": "CL", "brent": "B", "natural gas": "NG", "nat gas": "NG", "ng": "NG", "gasoline": "RB", "heating oil": "HO"}
    },
    "M": {  # Metals
        "name": "Metals",
        "keywords": ["gold", "silver", "copper", "platinum", "palladium", "zinc", "aluminum", "aluminium", "nickel", "tin", "lead"],
        "specific": ["xau", "xag", "gc", "si", "hg", "pa", "pl"],
        "ticker_map": {"gold": "GC", "xau": "GC", "silver": "SI", "xag": "SI", "copper": "HG", "platinum": "PL", "palladium": "PA"}
    },
    "C": {  # Crypto
        "name": "Crypto",
        "keywords": ["bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency", "digital asset"],
        "specific": ["btc", "eth", "usdt", "usdc"],
        "ticker_map": {"bitcoin": "BTC", "ethereum": "ETH"}
    },
    "R": {  # Rates
        "name": "Rates",
        "keywords": ["rates", "yield", "treasury", "bond", "sofr", "fed funds", "interest rate", "yield curve"],
        "specific": ["tn", "zn", "zb", "ub", "sofr", "ff"],
        "ticker_map": {"treasury": "ZN", "bond": "ZN", "sofr": "SOFR", "fed funds": "FF"}
    },
    "FX": {  # Forex
        "name": "FX",
        "keywords": ["fx", "forex", "currency", "dollar", "euro", "yen", "pound", "sterling", "dxy"],
        "specific": ["usd", "eur", "jpy", "gbp", "chf", "cad", "aud", "nzd", "dxy"],
        "ticker_map": {"dollar": "USD", "euro": "EUR", "yen": "JPY", "pound": "GBP", "sterling": "GBP", "dxy": "DXY"}
    },
    "I": {  # Indices
        "name": "Indices",
        "keywords": ["s&p", "spx", "sp500", "nasdaq", "dow", "dax", "ftse", "nikkei", "equity", "stock index"],
        "specific": ["es", "nq", "ym", "rt", "rty"],
        "ticker_map": {"s&p": "ES", "spx": "ES", "sp500": "ES", "nasdaq": "NQ", "dow": "YM", "dax": "DAX", "ftse": "FTSE", "nikkei": "NKD"}
    },
    "AG": {  # Agriculture
        "name": "Agriculture",
        "keywords": ["wheat", "corn", "soybean", "cotton", "sugar", "coffee", "cocoa", "livestock", "cattle", "hogs"],
        "specific": ["zw", "zc", "zs", "ct", "sb", "kc", "cc", "lc", "he", "gf"],
        "ticker_map": {"wheat": "ZW", "corn": "ZC", "soybean": "ZS", "cotton": "CT", "sugar": "SB", "coffee": "KC", "cocoa": "CC", "cattle": "LC", "hogs": "HE"}
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
    Categorize products into groups and convert to tickers.
    Returns: {"E": ["CL", "NG"], "M": ["GC", "SI"], ...}
    """
    categorized = {}
    text_lower = " ".join(products).lower()
    
    for category_code, patterns in PRODUCT_CATEGORIES.items():
        found_tickers = set()
        
        # Check keywords and map to tickers
        for keyword in patterns["keywords"]:
            if keyword.lower() in text_lower:
                # Map to ticker if available
                ticker = patterns["ticker_map"].get(keyword.lower(), keyword.upper())
                found_tickers.add(ticker)
        
        # Check specific tickers/symbols
        for symbol in patterns["specific"]:
            # Use word boundaries to avoid false matches
            pattern = r'\b' + re.escape(symbol.lower()) + r'\b'
            if re.search(pattern, text_lower):
                found_tickers.add(symbol.upper())
        
        if found_tickers:
            categorized[category_code] = sorted(list(found_tickers))
    
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


def summarize_pdf(pdf_path: Path, max_pages: int = MAX_PAGES_TO_SCAN, generate_pdf: bool = True) -> Optional[dict]:
    """
    Summarize a PDF file. Returns summary dict or None if skipped/failed.
    
    Args:
        pdf_path: Path to PDF file
        max_pages: Maximum pages to extract text from
        generate_pdf: If True, also generate __sum.pdf from the JSON
    
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
        
        # Categorize products (compact ticker format)
        products = summary.get("products", [])
        if products:
            summary["product_categories"] = categorize_products(products)
        
        # Save JSON summary
        json_path = create_summary_file(pdf_path, summary)
        print(f"[OK] JSON summary created: {json_path.name}")
        
        # Generate PDF summary (if requested)
        if generate_pdf:
            try:
                from summary_render import render_summary_pdf
                pdf_summary_path = render_summary_pdf(json_path)
                print(f"[OK] PDF summary created: {pdf_summary_path.name}")
            except ImportError:
                print(f"[WARN] summary_render module not available. Install reportlab to generate PDF summaries.")
            except Exception as e:
                print(f"[WARN] Failed to generate PDF summary: {e}")
        
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
        "- Detect specific products mentioned: gold, silver, oil, bitcoin, rates, USD, EUR, ES, NQ, etc.\n\n"
        "SCORING REQUIREMENTS:\n"
        "- Assess how useful this summary is for day trading, swing trading, or understanding market conditions.\n"
        "- Assign a summary_score_0_10 (0-10 scale): 0=useless, 5=somewhat helpful, 10=extremely actionable.\n"
        "- Consider: specificity of levels, timing precision, catalyst clarity, risk definition, confidence.\n"
        "- Assign a chart_score_0_3 (0-3 scale) based on chart/visual density:\n"
        "  0 = no charts/visuals\n"
        "  1 = minimal charts (1-2 simple charts)\n"
        "  2 = moderate charts (3-5 charts or some complex visuals)\n"
        "  3 = heavy charts (6+ charts, complex technical analysis, or chart-driven content)"
    )

    user_prompt = (
        "Create a trader-focused summary of the document below.\n\n"
        "Return STRICT JSON with exactly the following structure:\n\n"
        "{\n"
        '  "summary_score_0_10": integer (0-10, how useful for trading),\n'
        '  "chart_score_0_3": integer (0-3, visual/chart density),\n'
        '  "overall_bias": "bullish | bearish | neutral",\n'
        '  "products": [list of specific products: "gold", "silver", "oil", "bitcoin", "rates", "USD", "ES", etc.],\n'
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
        "SCORING GUIDANCE:\n"
        "- summary_score_0_10: Consider specificity, timing, levels, catalysts. 0=no trading value, 10=highly actionable.\n"
        "- chart_score_0_3: Based on chart/figure density: 0=none, 1=few, 2=moderate, 3=heavy.\n\n"
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
