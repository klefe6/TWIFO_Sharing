import os
import json
import re
from pathlib import Path

import requests
from PyPDF2 import PdfReader

# =========================
# CONFIG - Load API Key from multiple sources
# =========================
def load_api_key() -> str:
    """
    Try to load OPENAI_API_KEY from multiple sources (in order):
    1. .env file in script directory
    2. Environment variable (User, then System)
    3. config.txt file in script directory
    """
    script_dir = Path(__file__).parent
    
    # Method 1: Try .env file (if python-dotenv is installed)
    try:
        from dotenv import load_dotenv
        env_file = script_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            key = os.getenv("OPENAI_API_KEY")
            if key:
                return key
    except ImportError:
        pass  # python-dotenv not installed, skip
    
    # Method 2: Try .env file manually (simple key=value format)
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
    
    # Method 3: Try environment variable (User first, then System)
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    
    # Try loading from Windows registry directly (as fallback)
    try:
        import winreg
        # Try User environment variables
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as reg:
                key, _ = winreg.QueryValueEx(reg, "OPENAI_API_KEY")
                if key:
                    return key
        except (FileNotFoundError, OSError):
            pass
        
        # Try System environment variables (requires admin)
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as reg:
                key, _ = winreg.QueryValueEx(reg, "OPENAI_API_KEY")
                if key:
                    return key
        except (FileNotFoundError, PermissionError, OSError):
            pass
    except ImportError:
        pass  # Not Windows or winreg not available
    
    # Method 4: Try config.txt file
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

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

OPENAI_API_KEY = load_api_key()
if not OPENAI_API_KEY:
    raise SystemExit(
        "Missing OPENAI_API_KEY. Please set it in one of these ways:\n"
        "  1. Create .env file in script directory with: OPENAI_API_KEY=your_key_here\n"
        "  2. Set Windows environment variable (User or System)\n"
        "  3. Create config.txt file with: OPENAI_API_KEY=your_key_here\n"
        "  Then restart PowerShell/terminal."
    )

PDF_PATH = (
    Path(r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE")
    / "BA_Barclays - Energy Commodities - Chart Book- More evidence of resilient fundamentals 20251124_20251124_u.pdf"
)

MAX_PAGES = 12           # cap pages to control cost
MAX_OUTPUT_TOKENS = 900  # cap summary size to control cost


# =========================
# DISCLOSURE STRIPPER (drop legal boilerplate at the end)
# =========================
# Common "start of boilerplate" markers found near the end of sell-side PDFs.
DISCLOSURE_MARKERS = [
    r"\bimportant disclosures?\b",
    r"\bdisclosure(s)?\b",
    r"\blegal\b",
    r"\bregulatory\b",
    r"\bdefinitions\b",
    r"\bglossary\b",
    r"\bterms and conditions\b",
    r"\bnotice\b",
    r"\bdisclaimer(s)?\b",
    r"\banalyst certification\b",
    r"\bconflicts of interest\b",
]
DISCLOSURE_REGEX = re.compile("|".join(DISCLOSURE_MARKERS), re.IGNORECASE)


def strip_trailing_boilerplate(text: str) -> str:
    """
    Truncate text at the first boilerplate marker. This is a token-saver and
    usually removes long legal/disclosure sections at the bottom.
    """
    m = DISCLOSURE_REGEX.search(text)
    return text[: m.start()].strip() if m else text.strip()


# =========================
# PDF TEXT EXTRACTION
# =========================
def extract_text(pdf_path: Path, max_pages: int = MAX_PAGES) -> str:
    """Extract text from PDF with error handling for corrupted/unparseable PDFs."""
    try:
        reader = PdfReader(str(pdf_path), strict=False)
        parts: list[str] = []

        for i, page in enumerate(reader.pages[:max_pages]):
            try:
                text = page.extract_text() or ""
                parts.append(text)
            except Exception as e:
                print(f"Warning: Could not extract text from page {i+1}: {e}")
                parts.append("")  # Add empty string for failed pages

        txt = "\n".join(parts)
        txt = re.sub(r"\s+", " ", txt).strip()
        
        if not txt or len(txt) < 50:
            raise ValueError(f"Extracted text too short or empty ({len(txt)} chars). PDF may be image-based or corrupted.")
        
        return txt
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from PDF {pdf_path.name}: {e}")


# =========================
# OPENAI CALL
# =========================
def summarize_trader_brief(text: str) -> dict:
    """
    Summarize research document using OpenAI API with professional trader-focused prompt.
    """
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    # Professional trader-focused system prompt
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
        "- Output MUST be valid JSON only (no markdown, no prose, no code blocks)."
    )

    # Task definition with strict JSON schema
    user_prompt = (
        "Create a trader-focused summary of the document below.\n\n"
        "Return STRICT JSON with exactly the following structure:\n\n"
        "{\n"
        '  "overall_bias": "bullish | bearish | neutral",\n'
        '  "products": [list of products mentioned],\n'
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
        "- Prefer omission over speculation.\n\n"
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

    # Extract the model output text from the Responses API structure
    out_text = ""
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                out_text += c.get("text", "")
    
    # Debug: print what we got
    if not out_text:
        print("ERROR: No output text found in API response")
        print(f"Full response structure: {json.dumps(data, indent=2)}")
        raise ValueError("API returned empty output text")
    
    print(f"Raw output text (first 500 chars): {out_text[:500]}")
    
    # Strip markdown code blocks if present (API sometimes wraps JSON in ```json ... ```)
    cleaned_text = out_text.strip()
    if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text[7:]  # Remove ```json
    elif cleaned_text.startswith("```"):
        cleaned_text = cleaned_text[3:]  # Remove ```
    
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-3]  # Remove closing ```
    
    cleaned_text = cleaned_text.strip()
    
    # Try to parse JSON
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        print(f"JSON Parse Error: {e}")
        print(f"Cleaned output text:\n{cleaned_text}")
        raise ValueError(f"API response is not valid JSON: {e}") from e


def main() -> None:
    if not PDF_PATH.exists():
        raise SystemExit(f"PDF not found: {PDF_PATH}")
    
    # Check if should skip (Chart Books)
    from summarize_pdf import should_skip_summary
    if should_skip_summary(PDF_PATH.name):
        print(f"[SKIP] Chart Book detected, skipping summarization: {PDF_PATH.name}")
        return
    
    # Use the new summarization module
    try:
        from summarize_pdf import summarize_pdf, create_summary_file
        
        print(f"[INFO] Generating summary for {PDF_PATH.name}...")
        summary = summarize_pdf(PDF_PATH, max_pages=MAX_PAGES)
        
        if summary:
            summary_file = create_summary_file(PDF_PATH, summary)
            print(f"[OK] Summary created: {summary_file}")
        else:
            print("[WARN] Summary generation returned None")
            
    except ImportError:
        # Fallback to old method if module not available
        print("[WARN] Using legacy summarization method")
        raw_text = extract_text(PDF_PATH, max_pages=MAX_PAGES)
        clean_text = strip_trailing_boilerplate(raw_text)
        summary = summarize_trader_brief(clean_text)
        
        out_file = PDF_PATH.with_suffix(".summary.json")
        out_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("Wrote:", out_file)


if __name__ == "__main__":
    main()
