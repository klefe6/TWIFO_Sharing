"""
Rollup Builder Module
Purpose: Build daily/weekly rollups from existing __sum.json files only
Author: Kevin Lefebvre
Last Updated: 2026-02-05
Schema: twifo.rollup.v1
ZERO-OCR RULE: This module NEVER touches PDFs or uses OCR

Product tagging: Never default to ALL_PRODUCTS. Bullets use item.products, inference
from text (tickers/keywords), or [] → General bucket. Dedupe by text.
"""

from __future__ import annotations

import json
import datetime as dt
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

ROLLUP_SCHEMA_V1 = "twifo.rollup.v1"

# Product codes for filtering and grouping
PRODUCT_CODES = [
    "NQ", "Dow", "ES", "GC", "SI", "ZN", "BTC", "CL", "NG", "HG",
    "ZC", "ZS", "ZW", "HO", "RB", "RTY", "VIX", "EUR", "GBP", "JPY",
    "CHF", "AUD", "CAD", "ZB", "ZF", "ZT", "TN", "UB"
]

# Asset classes (ordered for grouping)
ASSET_CLASSES = [
    "EQUITIES", "RATES", "COMMODITIES", "FX",
    "VOLATILITY", "CRYPTO", "CREDIT", "GENERAL"
]

# Product → Asset class mapping
PRODUCT_TO_ASSET_CLASS = {
    # Equities / Indices (futures + cash indices)
    "ES": "EQUITIES", "NQ": "EQUITIES", "RTY": "EQUITIES", "Dow": "EQUITIES",
    "SPX": "EQUITIES",   # S&P 500 cash index — NOT an equity ticker
    "NDX": "EQUITIES",   # Nasdaq-100 cash index
    "SPY": "EQUITIES",   # S&P 500 ETF — treated as index exposure
    # Rates
    "ZN": "RATES", "ZB": "RATES", "ZF": "RATES", "ZT": "RATES", "TN": "RATES", "UB": "RATES",
    "TIPS": "RATES",     # US TIPS index / ETF — macro rates instrument
    "UST": "RATES",      # Generic US Treasury reference
    # Commodities (futures + widely-used commodity ETFs)
    "GC": "COMMODITIES", "SI": "COMMODITIES", "CL": "COMMODITIES", "NG": "COMMODITIES",
    "HG": "COMMODITIES", "ZC": "COMMODITIES", "ZS": "COMMODITIES", "ZW": "COMMODITIES",
    "HO": "COMMODITIES", "RB": "COMMODITIES",
    "SLV": "COMMODITIES",  # Silver ETF — NOT an equity
    "GLD": "COMMODITIES",  # Gold ETF — NOT an equity
    "USO": "COMMODITIES",  # Oil ETF — NOT an equity
    # FX
    "EUR": "FX", "GBP": "FX", "JPY": "FX", "CHF": "FX", "AUD": "FX", "CAD": "FX",
    "DXY": "FX",         # Dollar Index
    "USD": "FX",         # Generic USD reference
    # Volatility
    "VIX": "VOLATILITY",
    "VVIX": "VOLATILITY",
    # Crypto
    "BTC": "CRYPTO",
    "ETH": "CRYPTO",
}

# Allowed equity tickers (Top 10 US market cap + Large Banks)
TOP_10_US_MARKET_CAP = {"AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK.B", "JPM", "V"}
LARGE_BANKS = {"JPM", "BAC", "WFC", "C", "GS", "MS"}
ALLOWED_EQUITY_TICKERS = TOP_10_US_MARKET_CAP | LARGE_BANKS

def _product_to_asset_class(product: str) -> str:
    """Map product code to asset class. Unknown → GENERAL."""
    if product in PRODUCT_TO_ASSET_CLASS:
        return PRODUCT_TO_ASSET_CLASS[product]
    if product in ALLOWED_EQUITY_TICKERS:
        return "EQUITIES"
    # If looks like equity ticker (2-5 uppercase) but not allowed → EQUITIES (suppressed)
    if product and len(product) <= 5 and product.isupper() and product.isalpha():
        return "EQUITIES"
    return "GENERAL"


def _is_allowed_equity_ticker(product: str) -> bool:
    """Return True if product is an allowed equity ticker."""
    return product in ALLOWED_EQUITY_TICKERS


def _should_suppress_equity(product: str) -> bool:
    """Return True if product is equity-like but NOT allowed."""
    if product in PRODUCT_TO_ASSET_CLASS:
        return False  # Known futures/indices are never suppressed
    if product in ALLOWED_EQUITY_TICKERS:
        return False  # Allowed equities are kept
    # Check if looks like equity ticker
    if product and len(product) <= 5 and product.isupper() and product.isalpha():
        return True  # Suppress non-allowed equity tickers
    return False


def _text_similarity(a: str, b: str) -> float:
    """Jaccard similarity on word sets (simple, deterministic)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union > 0 else 0.0


def _looks_like_trade_idea(text: str) -> bool:
    """
    Detect if text looks like a trade idea (should be filtered from observations).
    Looks for patterns like: "buy X", "sell Y", "long Z", "short W", "consider buying", etc.
    """
    text_lower = text.lower()
    trade_patterns = [
        r'\b(buy|sell|long|short|go long|go short)\s+\w+',
        r'consider\s+(buying|selling|going long|going short)',
        r'take\s+(a\s+)?(long|short)\s+position',
        r'enter\s+(a\s+)?(long|short)',
    ]
    for pattern in trade_patterns:
        if re.search(pattern, text_lower):
            return True
    return False

def _iso_now() -> str:
    """Return timezone-aware ISO-8601 (UTC) e.g. 2026-02-04T21:37:36Z."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _model_from_articles(article_sum_jsons: List[dict]) -> str:
    """Derive meta.model from source articles; never return null/empty."""
    for a in article_sum_jsons:
        m = a.get("meta", {}).get("model") or a.get("meta", {}).get("summary_model_name")
        if m and str(m).strip():
            return str(m).strip()
    return "aggregated"


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))

def write_json(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def write_txt(p: Path, text: str) -> None:
    p.write_text(text.strip() + "\n", encoding="utf-8")

def _format_date_human(d: dt.date) -> str:
    return d.strftime("%B %d, %Y")

def _pill(text: str, typ: str = "tag") -> dict:
    return {"text": text, "type": typ}

def _dedupe_trade_ideas(trades: List[dict]) -> List[dict]:
    """
    Merge ideas with same (direction,instrument,timeframe,trigger). Combine sources, keep max confidence.
    Only sets confidence_0_100 if at least one of the merged ideas has it.
    """
    merged: Dict[Tuple[str,str,str,str], dict] = {}
    for t in trades:
        key = (
            (t.get("direction") or "").lower().strip(),
            (t.get("instrument") or "").strip(),
            (t.get("timeframe_bucket") or t.get("horizon") or "").strip(),
            (t.get("trigger") or "").strip(),
        )
        if key not in merged:
            merged[key] = {**t}
            merged[key]["sources"] = sorted(set(t.get("sources", [])))
            continue
        m = merged[key]
        m["sources"] = sorted(set(m.get("sources", [])) | set(t.get("sources", [])))
        # Only merge confidence if at least one has it - don't set to 0 if missing
        conf_m = m.get("confidence_0_100")
        conf_t = t.get("confidence_0_100")
        if conf_m is not None and conf_t is not None:
            m["confidence_0_100"] = max(int(conf_m), int(conf_t))
        elif conf_m is not None:
            m["confidence_0_100"] = int(conf_m)
        elif conf_t is not None:
            m["confidence_0_100"] = int(conf_t)
        # If neither has it, don't set the field (leave it missing)
    return list(merged.values())

def _bucket_trades(trades: List[dict]) -> dict:
    """
    Buckets: d_1_3, w_1_2, gt_2w, watchlist_only
    Maps timeframe_bucket or horizon field to correct bucket.
    """
    buckets = {"d_1_3": [], "w_1_2": [], "gt_2w": [], "watchlist_only": []}
    for t in trades:
        # Check timeframe_bucket first, then horizon
        bucket = t.get("timeframe_bucket") or t.get("horizon", "")
        if isinstance(bucket, str):
            h = bucket.lower()
            if "watchlist" in h or "watch" in h:
                buckets["watchlist_only"].append(t)
            elif any(x in h for x in ["1–3", "1-3", "3d", "0-3d", "tactical", "d_1_3"]):
                buckets["d_1_3"].append(t)
            elif any(x in h for x in ["1–2", "1-2", "2w", "1-2w", "swing", "w_1_2"]):
                buckets["w_1_2"].append(t)
            elif any(x in h for x in [">2", "gt", "2w+", "position", "gt_2w"]):
                buckets["gt_2w"].append(t)
            else:
                # Default to d_1_3 for unclear timeframes
                buckets["d_1_3"].append(t)
        else:
            buckets["d_1_3"].append(t)
    return buckets

def _rank_trade_ideas(trades: List[dict]) -> List[dict]:
    """
    Rank trade ideas by (confidence + number of sources + recency).
    """
    def score(t: dict) -> float:
        conf = int(t.get("confidence_0_100", 50))
        source_count = len(t.get("sources", []))
        # Simple scoring: confidence * 0.6 + sources * 20 + base
        return conf * 0.6 + source_count * 20
    return sorted(trades, key=score, reverse=True)

# Bucket for unassigned bullets (products=[]). Never use ALL_PRODUCTS.
GENERAL_BUCKET = "General"

# Keyword → product mapping for inferring products from bullet text
_KEYWORD_TO_PRODUCT: List[Tuple[str, str]] = [
    (r"\boil\b|\bcrude\b", "CL"),
    (r"\bgold\b", "GC"),
    (r"\bsilver\b", "SI"),
    (r"\bbonds?\b|\bTreasury\b|\byields?\b|\b10[- ]?[yY]ear\b|\b2[- ]?[yY]ear\b", "ZN"),
    (r"\bZB\b|\b30[- ]?[yY]ear\b", "ZB"),
    (r"\bequities?\b|\bS&P\b|\bSPX\b|\bES\b", "ES"),
    (r"\bNasdaq\b|\bNQ\b", "NQ"),
    (r"\bvolatility\b|\bVIX\b", "VIX"),
    (r"\bbitcoin\b|\bcrypto\b|\bBTC\b", "BTC"),
    (r"\bCL\b", "CL"),
    (r"\bGC\b", "GC"),
    (r"\bSI\b", "SI"),
    (r"\bZN\b", "ZN"),
    (r"\bES\b", "ES"),
    (r"\bNQ\b", "NQ"),
]


def _infer_products_from_text(text: str, section: str, article_products: List[str]) -> List[str]:
    """
    Infer minimal product set from bullet text. Never returns ALL_PRODUCTS.
    Uses: explicit tickers, section context, keyword mapping.
    Returns [] if unknown (→ General bucket).
    """
    if not text or not isinstance(text, str):
        return []
    text_lower = text.lower()
    found: set[str] = set()
    for pattern, product in _KEYWORD_TO_PRODUCT:
        if re.search(pattern, text_lower, re.IGNORECASE):
            if product in PRODUCT_CODES:
                found.add(product)
    # Section hints: metals→GC/SI, energy→CL, rates→ZN/ZB, vol→VIX, crypto→BTC
    if "metals" in section.lower() or "metal" in section.lower():
        for p in ("GC", "SI"):
            if p in article_products and any(k in text_lower for k in ["gold", "silver", "gc", "si"]):
                found.add(p)
    if "energy" in section.lower() and any(k in text_lower for k in ["oil", "crude", "cl"]):
        if "CL" in article_products:
            found.add("CL")
    if "rates" in section.lower() or "bonds" in section.lower():
        for p in ("ZN", "ZB"):
            if p in article_products and any(k in text_lower for k in ["yield", "bond", "zn", "zb"]):
                found.add(p)
    return sorted(found) if found else []


def _resolve_bullet_products(
    it: dict,
    text: str,
    article_products: List[str],
    section: str,
) -> List[str]:
    """
    Resolve products for a bullet. NEVER default to article_products (ALL_PRODUCTS).
    Suppress non-allowed equity tickers.
    Priority: item.products → infer from text → [] (General).
    """
    item_products = it.get("products", []) if isinstance(it, dict) else []
    if item_products and isinstance(item_products, list):
        valid = [p for p in item_products if p in PRODUCT_CODES and not _should_suppress_equity(p)]
        if valid:
            return sorted(set(valid))
    inferred = _infer_products_from_text(text, section, article_products)
    # Filter suppressed from inferred
    inferred = [p for p in inferred if not _should_suppress_equity(p)]
    return inferred if inferred else []


def _dedupe_bullets(items: List[dict]) -> List[dict]:
    """Dedupe by normalized text; merge sources."""
    seen: Dict[str, dict] = {}
    for it in items:
        text = (it.get("text", "") if isinstance(it, dict) else str(it)).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            existing = seen[key]
            sources = set(existing.get("sources", [])) | set(it.get("sources", []) if isinstance(it, dict) else [])
            existing["sources"] = sorted(sources)
        else:
            seen[key] = dict(it) if isinstance(it, dict) else {"text": text, "sources": [], "products": []}
    return list(seen.values())


def _group_by_product(items: List[dict]) -> Dict[str, List[dict]]:
    """
    Group items by product. Items with products=[] go into General (never all products).
    """
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for item in items:
        item_products = item.get("products", [])
        if item_products:
            for product in item_products:
                if product in PRODUCT_CODES:
                    grouped[product].append(item)
        else:
            grouped[GENERAL_BUCKET].append(item)
    return dict(grouped)


def _group_by_asset_class(items: List[dict]) -> Dict[str, List[dict]]:
    """
    Group items by asset class. Items with products=[] → GENERAL.
    Order keys by ASSET_CLASSES order.
    """
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for item in items:
        item_products = item.get("products", [])
        if item_products:
            # Determine asset class from first non-suppressed product
            asset_class = "GENERAL"
            for p in item_products:
                if not _should_suppress_equity(p):
                    asset_class = _product_to_asset_class(p)
                    break
            grouped[asset_class].append(item)
        else:
            grouped["GENERAL"].append(item)
    
    # Return in fixed ASSET_CLASSES order (only keys that have items)
    return {ac: grouped[ac] for ac in ASSET_CLASSES if ac in grouped}

def _build_executive_snapshot(
    article_sum_jsons: List[dict],
    tldr_items: List[dict],
    volatility_by_asset_class: Dict[str, dict],
) -> List[dict]:
    """
    Build executive_snapshot from TLDR + volatility + recurring themes.
    Frequency-weighted: include if mentioned in ≥2 articles OR volatility High.
    Max 5 bullets. Dedupe by similarity ≥0.85.
    """
    candidates = []
    
    # Count TLDR text frequency across articles
    text_counts: Dict[str, int] = defaultdict(int)
    text_sources: Dict[str, set] = defaultdict(set)
    for a in article_sum_jsons:
        provider = a.get("meta", {}).get("provider", "O")
        for item in a.get("sections", {}).get("tldr", []):
            text = item.get("text", "") if isinstance(item, dict) else str(item)
            text = text.strip()
            if text:
                text_counts[text] += 1
                text_sources[text].add(provider)
    
    # Include if count ≥ 2
    for text, count in text_counts.items():
        if count >= 2:
            candidates.append({"text": text, "sources": sorted(text_sources[text]), "_score": count})
    
    # Add volatility lines for High expected_volatility
    for asset_class, vol_data in volatility_by_asset_class.items():
        if vol_data.get("expected_volatility") == "High":
            skew = vol_data.get("directional_skew", "Neutral")
            text = f"{asset_class}: High volatility expected, {skew} skew."
            candidates.append({"text": text, "sources": vol_data.get("sources", []), "_score": 3})
    
    # Also add top TLDR from tldr_items if underrepresented
    for item in tldr_items[:3]:
        text = item.get("text", "")
        if text and text not in text_counts:
            candidates.append({"text": text, "sources": item.get("sources", []), "_score": 1})
    
    # Sort by score descending
    candidates.sort(key=lambda x: -x.get("_score", 0))
    
    # Dedupe by similarity ≥ 0.85
    final = []
    for c in candidates:
        text = c["text"]
        is_dup = any(_text_similarity(text, f["text"]) >= 0.85 for f in final)
        if not is_dup:
            final.append({"text": text, "sources": c["sources"]})
        if len(final) >= 5:
            break
    
    return final


def _aggregate_volatility_by_asset_class(article_sum_jsons: List[dict]) -> Dict[str, dict]:
    """
    Aggregate volatility_impact and sentiment_indicator by asset class.
    Score: High=3, Medium=2, Low=1. Average across articles.
    
    Extended schema (2026-02-25): Adds reference_symbol and bias_definition
    to disambiguate directional bias for broad asset classes like FX.
    """
    from collections import Counter
    
    VOL_SCORE = {"High": 3, "Medium": 2, "Low": 1}
    
    # Canonical reference instrument mapping
    # Used when no specific instrument is identified from source data.
    # FX uses DXY because it is the most common vol surface anchor in macro research.
    # Note: DXY downside implies EURUSD upside (inverse relationship).
    REFERENCE_MAPPING = {
        "EQUITIES": "SPX",
        "FX": "DXY",
        "RATES": "US10Y",
        "COMMODITIES": "CL",  # Crude oil as most liquid commodity
        "METALS": "GC",       # Gold
        "ENERGY": "CL",
        "CRYPTO": "BTC",
        "VOLATILITY": "VIX",
        "GENERAL": None,      # Too broad for single instrument
        "CREDIT": None,       # Too broad for single instrument
    }
    
    # Collect per asset class
    ac_data: Dict[str, dict] = defaultdict(lambda: {
        "vol_scores": [], "skews": [], "sources": set()
    })
    
    for a in article_sum_jsons:
        provider = a.get("meta", {}).get("provider", "O")
        products = a.get("meta", {}).get("products", []) or []
        vol = a.get("volatility_impact", {})
        if not vol or not isinstance(vol, dict):
            continue
        
        expected = vol.get("expected_volatility", "")
        skew = vol.get("directional_skew", "")
        
        # Determine asset classes for this article
        asset_classes_for_article = set()
        for p in products:
            if not _should_suppress_equity(p):
                asset_classes_for_article.add(_product_to_asset_class(p))
        if not asset_classes_for_article:
            asset_classes_for_article.add("GENERAL")
        
        for ac in asset_classes_for_article:
            if expected in VOL_SCORE:
                ac_data[ac]["vol_scores"].append(VOL_SCORE[expected])
            if skew:
                ac_data[ac]["skews"].append(skew)
            ac_data[ac]["sources"].add(provider)
    
    # Build result
    result = {}
    for ac in ASSET_CLASSES:
        if ac not in ac_data:
            continue
        data = ac_data[ac]
        if not data["vol_scores"]:
            continue
        
        avg_score = sum(data["vol_scores"]) / len(data["vol_scores"])
        # Map score back to label
        if avg_score >= 2.5:
            expected_vol = "High"
        elif avg_score >= 1.5:
            expected_vol = "Medium"
        else:
            expected_vol = "Low"
        
        # Mode for skew
        skew_counter = Counter(data["skews"])
        directional_skew = skew_counter.most_common(1)[0][0] if skew_counter else "Neutral"
        
        # Determine reference symbol and bias definition
        reference_symbol = REFERENCE_MAPPING.get(ac)
        bias_definition = _build_bias_definition(ac, reference_symbol, directional_skew)
        
        result[ac] = {
            "expected_volatility": expected_vol,
            "directional_skew": directional_skew,
            "confidence_score": round(avg_score, 2),
            "sources": sorted(data["sources"]),
            "reference_symbol": reference_symbol,  # NEW: canonical instrument
            "bias_definition": bias_definition,    # NEW: tooltip text
        }
    
    return result


def _build_bias_definition(asset_class: str, reference_symbol: Optional[str], skew: str) -> str:
    """
    Build tooltip text explaining what the directional bias means.
    
    Special handling for FX: DXY downside implies EURUSD upside (inverse).
    """
    if not reference_symbol:
        return f"{skew} bias for {asset_class}. No single reference instrument."
    
    if asset_class == "FX" and reference_symbol == "DXY":
        if skew == "Bearish":
            return "Bearish bias relative to DXY. If DXY falls, EURUSD tends to rise (USD weakness)."
        elif skew == "Bullish":
            return "Bullish bias relative to DXY. If DXY rises, EURUSD tends to fall (USD strength)."
        else:
            return "Neutral bias relative to DXY. Mixed signals across currency pairs."
    
    # Generic definition for other asset classes
    direction_text = {
        "Bearish": "downside",
        "Bullish": "upside",
        "Neutral": "neutral"
    }.get(skew, "mixed")
    
    return f"{skew} bias relative to {reference_symbol}. Expected {direction_text} movement."


def build_daily_rollup(date_obj: dt.date, article_sum_jsons: List[dict], min_articles_required: int = 3) -> dict:
    """
    Build rollup JSON with SAME detail style as article summaries:
    tldr, observations, forward_watch, trade_ideas (structured), warnings, tips, cross_asset, scenarios, sources.
    
    ZERO-OCR RULE: Only reads from existing JSON, never touches PDFs.
    """
    if len(article_sum_jsons) < min_articles_required:
        raise ValueError(f"Not enough articles for rollup ({len(article_sum_jsons)} < {min_articles_required})")

    # Safety: normalize provider fields from article metadata to avoid single-letter codes
    for a in article_sum_jsons:
        meta = a.setdefault("meta", {})
        prov = meta.get("provider", "") or ""
        if isinstance(prov, str):
            prov = prov.strip()
            if prov == "Unknown" or prov == "":
                meta["provider"] = "Others"
            elif len(prov) == 1 and prov != "O":
                # Reject single-letter accidental providers; mark as Others
                meta["provider"] = "Others"
        else:
            meta["provider"] = "Others"

    providers = sorted({a.get("meta", {}).get("provider", "O") for a in article_sum_jsons})
    products = sorted({p for a in article_sum_jsons for p in (a.get("meta", {}).get("products") or [])})

    def gather(section: str, limit: int = 30, filter_trade_ideas: bool = False) -> List[dict]:
        """Gather bullets; never default to ALL_PRODUCTS. products=[] → General."""
        out = []
        for a in article_sum_jsons:
            article_products = a.get("meta", {}).get("products", []) or []
            items = a.get("sections", {}).get(section, []) or []
            for it in items:
                if isinstance(it, dict) and it.get("text"):
                    text = it["text"]
                    if filter_trade_ideas and _looks_like_trade_idea(text):
                        continue
                    provider = a.get("meta", {}).get("provider", "O")
                    sources = it.get("sources", []) or [provider]
                    prods = _resolve_bullet_products(it, text, article_products, section)
                    out.append({"text": text, "sources": sorted(set(sources)), "products": prods})
                elif isinstance(it, str):
                    text = it
                    if filter_trade_ideas and _looks_like_trade_idea(text):
                        continue
                    provider = a.get("meta", {}).get("provider", "O")
                    prods = _resolve_bullet_products({"text": text}, text, article_products, section)
                    out.append({"text": text, "sources": [provider], "products": prods})
        out = _dedupe_bullets(out)
        return out[:limit]

    def gather_grouped(section: str, limit: int = 30) -> Dict[str, List[dict]]:
        items = gather(section, limit=limit, filter_trade_ideas=(section == "what_occurred"))
        return _group_by_asset_class(items)

    # Aggregate trade ideas by product (new structure)
    # Trade ideas now structured by product with: product, bias, catalyst, setup, key_levels, risk, time_horizon, volatility_impact
    # HARD RULE: Only extract exact strings from article JSON - NO HALLUCINATION
    trade_ideas_by_product = {}
    _ti_raw_count = 0      # ideas seen before suppression filter
    _ti_suppressed = 0     # ideas dropped by _should_suppress_equity
    for a in article_sum_jsons:
        article_trades = a.get("sections", {}).get("trade_ideas", []) or []
        provider = a.get("meta", {}).get("provider", "O")
        
        # Extract volatility_impact from article if present
        article_volatility = a.get("volatility_impact", "") or a.get("sections", {}).get("volatility_impact", "")
        
        for t in article_trades:
            if not isinstance(t, dict):
                continue
            product = t.get("product", "")
            if not product:
                continue
            
            _ti_raw_count += 1
            # Skip non-allowed equity tickers entirely
            if _should_suppress_equity(product):
                _ti_suppressed += 1
                continue
            
            # Initialize product entry if needed
            if product not in trade_ideas_by_product:
                trade_ideas_by_product[product] = {
                    "product": product,
                    "bias": t.get("bias", "Neutral"),
                    "catalyst": [],
                    "setup": [],
                    "key_levels": [],
                    "risk": [],
                    "time_horizon": [],
                    "volatility_impact": [],
                    "sources": []
                }
            
            # Aggregate fields (collect unique values) - ONLY from article JSON, no invention
            prod_entry = trade_ideas_by_product[product]
            
            # Extract catalyst - only if present in article
            catalyst = t.get("catalyst", "")
            if catalyst and isinstance(catalyst, str) and catalyst.strip() and catalyst not in prod_entry["catalyst"]:
                prod_entry["catalyst"].append(catalyst.strip())
            
            # Extract setup - only if present in article
            setup = t.get("setup", "")
            if setup and isinstance(setup, str) and setup.strip() and setup not in prod_entry["setup"]:
                prod_entry["setup"].append(setup.strip())
            
            # Extract key_levels - CRITICAL: only exact strings from article, no hallucination
            key_levels = t.get("key_levels", "")
            if key_levels and isinstance(key_levels, str) and key_levels.strip() and key_levels not in prod_entry["key_levels"]:
                prod_entry["key_levels"].append(key_levels.strip())
            
            # Extract risk - only if present in article
            risk = t.get("risk", "")
            if risk and isinstance(risk, str) and risk.strip() and risk not in prod_entry["risk"]:
                prod_entry["risk"].append(risk.strip())
            
            # Extract time_horizon - only if present in article
            time_horizon = t.get("time_horizon", "")
            if time_horizon and isinstance(time_horizon, str) and time_horizon.strip() and time_horizon not in prod_entry["time_horizon"]:
                prod_entry["time_horizon"].append(time_horizon.strip())
            
            # Extract volatility_impact - only if present in article or trade idea
            vol_impact = t.get("volatility_impact", "") or article_volatility
            if vol_impact and isinstance(vol_impact, str) and vol_impact.strip() and vol_impact not in prod_entry["volatility_impact"]:
                prod_entry["volatility_impact"].append(vol_impact.strip())
            
            if provider not in prod_entry["sources"]:
                prod_entry["sources"].append(provider)
            
            # Update bias if more specific (Bull/Bear > Neutral)
            bias = t.get("bias", "Neutral")
            if bias != "Neutral" and prod_entry["bias"] == "Neutral":
                prod_entry["bias"] = bias
    
    # Global product ordering: Indices → Rates → Metals → Crypto → Others
    def _product_sort_key(product: str) -> tuple:
        """Sort products by category priority, then alphabetically within category."""
        # Indices (priority 1)
        indices = ["ES", "NQ", "RTY", "Dow", "VIX"]
        # Rates (priority 2)
        rates = ["ZN", "ZB", "ZF", "ZT", "TN", "UB", "2Y", "10Y", "30Y"]
        # Metals (priority 3)
        metals = ["GC", "SI", "HG", "PL", "PA"]
        # Crypto (priority 4)
        crypto = ["BTC", "ETH"]
        
        if product in indices:
            return (1, indices.index(product))
        elif product in rates:
            return (2, rates.index(product))
        elif product in metals:
            return (3, metals.index(product))
        elif product in crypto:
            return (4, crypto.index(product))
        else:
            return (5, product)  # Others, alphabetically
    
    # Sort products by global ordering
    sorted_products = sorted(trade_ideas_by_product.keys(), key=_product_sort_key)
    
    trade_ideas_list = []
    for product in sorted_products:
        entry = trade_ideas_by_product[product]
        # Deduplicate and combine lists into strings - only use exact strings from articles
        trade_ideas_list.append({
            "product": product,
            "bias": entry["bias"],
            "catalyst": "; ".join(entry["catalyst"]) if entry["catalyst"] else "",
            "setup": "; ".join(entry["setup"]) if entry["setup"] else "",
            "key_levels": "; ".join(entry["key_levels"]) if entry["key_levels"] else "",
            "risk": "; ".join(entry["risk"]) if entry["risk"] else "",
            "time_horizon": "; ".join(entry["time_horizon"]) if entry["time_horizon"] else "",
            "volatility_impact": "; ".join(entry["volatility_impact"]) if entry["volatility_impact"] else "",
            "sources": sorted(entry["sources"])
        })

    # Visibility log — always emitted, explains future emptiness without re-investigation
    print(
        f"[TRADE_IDEAS] date={date_obj.isoformat()} articles={len(article_sum_jsons)}"
        f" extracted={_ti_raw_count} suppressed={_ti_suppressed}"
        f" after_filter={len(trade_ideas_list)}"
    )

    # Derive consensus catalysts (from common catalysts in trade ideas)
    all_catalysts = []
    for entry in trade_ideas_list:
        catalyst = entry.get("catalyst", "")
        if catalyst:
            all_catalysts.append(catalyst)
    # Simple approach: take most common catalysts (could be enhanced)
    consensus_catalysts = [{"text": c, "sources": []} for c in all_catalysts[:3]]
    
    # Derive conflicts/uncertainties (from conflicting biases on same products)
    conflicts = []
    # For now, use empty list - can be enhanced later to detect conflicting biases

    # sources list
    sources = []
    for a in article_sum_jsons:
        m = a.get("meta", {})
        sources.append({
            "provider": m.get("provider", "O"),
            "titles": [m.get("title", "")] if m.get("title") else []
        })

    # Build components in strict order
    warnings_list = gather("warnings", limit=15)
    tldr_list = gather("tldr", limit=6)
    
    # Volatility aggregation (before executive_snapshot)
    volatility_by_asset_class = _aggregate_volatility_by_asset_class(article_sum_jsons)
    
    # Executive snapshot (needs tldr_list and volatility_by_asset_class)
    executive_snapshot = _build_executive_snapshot(
        article_sum_jsons, tldr_list, volatility_by_asset_class
    )
    
    # Grouped sections (asset-class-keyed)
    observations = gather_grouped("what_occurred", limit=30)
    forward_watch = gather_grouped("forward_watch", limit=25)

    rollup = {
        "schema_version": ROLLUP_SCHEMA_V1,
        "kind": "rollup",
        "meta": {
            "rollup_kind": "daily",
            "date": date_obj.isoformat(),
            "week_range": None,
            "min_articles_required": min_articles_required,
            "article_count": len(article_sum_jsons),
            "providers": providers,
            "products": products,
            "generated_at_iso": _iso_now(),
            "model": _model_from_articles(article_sum_jsons),
        },
        "ui": {
            "title": f"Preparation for {_format_date_human(date_obj)}",
            "header_pills": [
                _pill(", ".join(providers), "provider"),
                _pill(date_obj.strftime("%b %d, %Y"), "date"),
                _pill("Daily", "timeframe"),
            ],
            "chips_rows": [
                [{"text": p, "type": "product"} for p in products],
                [{"text": s, "type": "source"} for s in providers],
            ],
        },
        "inputs": {
            "articles": [
                {
                    "file": a.get("meta", {}).get("source_file", None),
                    "provider": a.get("meta", {}).get("provider", "O"),
                    "title": a.get("meta", {}).get("title", ""),
                    "horizon": a.get("meta", {}).get("horizon", ""),
                    "products": a.get("meta", {}).get("products", []) or []
                }
                for a in article_sum_jsons
            ]
        },
        "sections": {
            "warnings": warnings_list,
            "executive_snapshot": executive_snapshot,
            "tldr": tldr_list,
            "observations": observations,
            "forward_watch": forward_watch,
            "volatility_by_asset_class": volatility_by_asset_class,
            "trade_ideas": trade_ideas_list,
            "stocks": gather("stocks", limit=8),
            "other_futures": gather("other_futures", limit=20),
            "forex": gather("forex", limit=6),
            "other": gather("other", limit=15),
            "consensus_catalysts": consensus_catalysts[:3],
            "conflicts_uncertainties": conflicts[:3],
            "tips_reminders": gather("tips_reminders", limit=10),
            "cross_asset_impacts": gather("cross_asset_impacts", limit=15),
            "scenarios": gather("scenarios", limit=8),
            "sources": sources,
        }
    }
    return rollup

def build_weekly_rollup(start_date: dt.date, end_date: dt.date, article_sum_jsons: List[dict], min_articles_required: int = 3) -> dict:
    """
    Build weekly rollup JSON for Mon-Fri range.
    Same schema as daily, but rollup_kind="weekly" and week_range set.
    ZERO-OCR RULE: Only reads from existing JSON.
    """
    if len(article_sum_jsons) < min_articles_required:
        raise ValueError(f"Not enough articles for weekly rollup ({len(article_sum_jsons)} < {min_articles_required})")

    providers = sorted({a.get("meta", {}).get("provider", "O") for a in article_sum_jsons})
    products = sorted({p for a in article_sum_jsons for p in (a.get("meta", {}).get("products") or [])})

    # Get ISO week info
    iso_year, iso_week, _ = start_date.isocalendar()

    def gather(section: str, limit: int = 30, filter_trade_ideas: bool = False) -> List[dict]:
        """Gather bullets; never default to ALL_PRODUCTS. products=[] → General."""
        out = []
        for a in article_sum_jsons:
            article_products = a.get("meta", {}).get("products", []) or []
            items = a.get("sections", {}).get(section, []) or []
            for it in items:
                if isinstance(it, dict) and it.get("text"):
                    text = it["text"]
                    if filter_trade_ideas and _looks_like_trade_idea(text):
                        continue
                    provider = a.get("meta", {}).get("provider", "O")
                    sources = it.get("sources", []) or [provider]
                    prods = _resolve_bullet_products(it, text, article_products, section)
                    out.append({"text": text, "sources": sorted(set(sources)), "products": prods})
                elif isinstance(it, str):
                    text = it
                    if filter_trade_ideas and _looks_like_trade_idea(text):
                        continue
                    provider = a.get("meta", {}).get("provider", "O")
                    prods = _resolve_bullet_products({"text": text}, text, article_products, section)
                    out.append({"text": text, "sources": [provider], "products": prods})
        out = _dedupe_bullets(out)
        return out[:limit]

    def gather_grouped(section: str, limit: int = 30) -> Dict[str, List[dict]]:
        items = gather(section, limit=limit, filter_trade_ideas=(section == "what_occurred"))
        return _group_by_asset_class(items)

    # trade ideas - emphasize w_1_2 and gt_2w for weekly
    trades = []
    for a in article_sum_jsons:
        for t in (a.get("sections", {}).get("trade_ideas", []) or []):
            if not isinstance(t, dict):
                continue
            if not t.get("direction") or not t.get("instrument") or not t.get("trigger"):
                continue
            if not (t.get("timeframe_bucket") or t.get("horizon")):
                continue
            trades.append(t)

    trades = _dedupe_trade_ideas(trades)
    trades = _rank_trade_ideas(trades)
    trade_buckets = _bucket_trades(trades)

    # sources list
    sources = []
    for a in article_sum_jsons:
        m = a.get("meta", {})
        sources.append({
            "provider": m.get("provider", "O"),
            "titles": [m.get("title", "")] if m.get("title") else []
        })

    week_range_str = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"

    rollup = {
        "schema_version": ROLLUP_SCHEMA_V1,
        "kind": "rollup",
        "meta": {
            "rollup_kind": "weekly",
            "date": start_date.isoformat(),  # Monday date
            "week_range": week_range_str,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "iso_year": iso_year,
            "iso_week": iso_week,
            "min_articles_required": min_articles_required,
            "article_count": len(article_sum_jsons),
            "providers": providers,
            "products": products,
            "generated_at_iso": _iso_now(),
            "model": _model_from_articles(article_sum_jsons),
        },
        "ui": {
            "title": f"Week of {start_date.strftime('%B %d')} Weekly Recap",
            "header_pills": [
                _pill(", ".join(providers), "provider"),
                _pill(week_range_str, "date"),
                _pill("Weekly", "timeframe"),
            ],
            "chips_rows": [
                [{"text": p, "type": "product"} for p in products],
                [{"text": s, "type": "source"} for s in providers],
            ],
        },
        "inputs": {
            "articles": [
                {
                    "file": a.get("meta", {}).get("source_file", None),
                    "provider": a.get("meta", {}).get("provider", "O"),
                    "title": a.get("meta", {}).get("title", ""),
                    "horizon": a.get("meta", {}).get("horizon", ""),
                    "products": a.get("meta", {}).get("products", []) or []
                }
                for a in article_sum_jsons
            ]
        },
        "sections": {
            "tldr": gather("tldr", limit=8),
            "observations": gather_grouped("what_occurred", limit=30),  # Grouped by product
            "forward_watch": gather_grouped("forward_watch", limit=25),  # Grouped by product
            "trade_ideas": trade_buckets,
            "warnings": gather("warnings", limit=15),
            "tips_reminders": gather("tips_reminders", limit=10),
            "cross_asset_impacts": gather("cross_asset_impacts", limit=15),
            "scenarios": gather("scenarios", limit=8),
            "sources": sources,
        }
    }
    return rollup

def render_rollup_txt(r: dict) -> str:
    """
    Render rollup in new trader-focused format with word limits.
    """
    meta = r.get("meta", {})
    ui = r.get("ui", {})
    title = ui.get("title", "")
    secs = r.get("sections", {})
    
    def bullet_lines(items, max_items=None):
        """Format bullets from text items."""
        out = []
        items_to_process = items[:max_items] if max_items and isinstance(items, list) else items
        for it in items_to_process or []:
            if isinstance(it, dict):
                text = it.get('text', '').strip()
                if text:
                    out.append(f"• {text}")
            elif isinstance(it, str):
                text = it.strip()
                if text:
                    out.append(f"• {text}")
        return "\n".join(out) if out else "• (none)"
    
    # TL;DR (max 6)
    tldr_items = secs.get("tldr", [])[:6]
    tldr_text = bullet_lines(tldr_items)
    
    # TRADE IDEAS - structured by product
    trade_ideas = secs.get("trade_ideas", [])
    trade_ideas_text = []
    
    priority_products = ["ES", "NQ", "GC", "SI", "VIX"]
    trade_by_product = {item.get("product"): item for item in trade_ideas if isinstance(item, dict) and item.get("product")}
    other_products = [p for p in trade_by_product.keys() if p not in priority_products]
    ordered_products = [p for p in priority_products if p in trade_by_product] + sorted(other_products)
    
    for product in ordered_products:
        item = trade_by_product[product]
        bias = item.get("bias", "Neutral")
        catalyst = item.get("catalyst", "")
        setup = item.get("setup", "")
        key_levels = item.get("key_levels", "")
        risk = item.get("risk", "")
        time_horizon = item.get("time_horizon", "")
        volatility_impact = item.get("volatility_impact", "")
        
        if bias == "Neutral" and not catalyst:
            continue  # Skip products with no meaningful trade ideas
        
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
        if volatility_impact:
            trade_ideas_text.append(f"  Volatility Impact: {volatility_impact}")
    
    trade_ideas_output = "\n".join(trade_ideas_text) if trade_ideas_text else "• (none)"
    
    # STOCKS
    stocks_items = secs.get("stocks", [])[:8]
    stocks_text = bullet_lines(stocks_items)
    
    # OTHER FUTURES
    other_futures_items = secs.get("other_futures", [])
    other_futures_text = bullet_lines(other_futures_items)
    
    # FOREX
    forex_items = secs.get("forex", [])[:6]
    forex_text = bullet_lines(forex_items)
    
    # OTHER
    other_items = secs.get("other", [])
    other_text = bullet_lines(other_items)
    
    # CONSENSUS CATALYSTS (daily only)
    consensus_catalysts_items = secs.get("consensus_catalysts", [])[:3]
    consensus_catalysts_text = bullet_lines(consensus_catalysts_items)
    
    # CONFLICTS/UNCERTAINTIES (daily only)
    conflicts_items = secs.get("conflicts_uncertainties", [])[:3]
    conflicts_text = bullet_lines(conflicts_items)
    
    # Build output
    output = f"""{title}

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

CONSENSUS CATALYSTS TODAY
{consensus_catalysts_text}

CONFLICTS/UNCERTAINTIES
{conflicts_text}
"""
    
    # Enforce word limit (250-450 target, 600 hard max)
    word_count = len(output.split())
    if word_count > 600:
        # Truncate sections starting from the least important
        # This is a simple approach - could be more sophisticated
        output = output[:output[:output.rfind('\n\nOTHER\n')].rfind('\n\n')]
        output += "\n\n[Truncated to meet 600 word limit]"
    
    return output

