"""
Rollup Builder Module
Purpose: Build daily/weekly rollups from existing __sum.json files only
Author: Kevin Lefebvre
Last Updated: 2026-01-11
Schema: twifo.rollup.v1
ZERO-OCR RULE: This module NEVER touches PDFs or uses OCR
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
    return dt.datetime.now().isoformat(timespec="seconds")

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

def _group_by_product(items: List[dict]) -> Dict[str, List[dict]]:
    """
    Group items by product. Items without products go into "Other".
    """
    grouped = defaultdict(list)
    for item in items:
        item_products = item.get("products", [])
        if item_products:
            for product in item_products:
                grouped[product].append(item)
        else:
            grouped["Other"].append(item)
    return dict(grouped)

def build_daily_rollup(date_obj: dt.date, article_sum_jsons: List[dict], min_articles_required: int = 3) -> dict:
    """
    Build rollup JSON with SAME detail style as article summaries:
    tldr, observations, forward_watch, trade_ideas (structured), warnings, tips, cross_asset, scenarios, sources.
    
    ZERO-OCR RULE: Only reads from existing JSON, never touches PDFs.
    """
    if len(article_sum_jsons) < min_articles_required:
        raise ValueError(f"Not enough articles for rollup ({len(article_sum_jsons)} < {min_articles_required})")

    providers = sorted({a.get("meta", {}).get("provider", "O") for a in article_sum_jsons})
    products = sorted({p for a in article_sum_jsons for p in (a.get("meta", {}).get("products") or [])})

    # aggregate bullets - returns list of dicts with text, sources, products
    def gather(section: str, limit: int = 30, filter_trade_ideas: bool = False) -> List[dict]:
        out = []
        for a in article_sum_jsons:
            article_products = a.get("meta", {}).get("products", []) or []
            items = a.get("sections", {}).get(section, []) or []
            for it in items:
                if isinstance(it, dict) and it.get("text"):
                    text = it["text"]
                    # Filter out trade ideas if requested (for observations/what_occurred)
                    if filter_trade_ideas and _looks_like_trade_idea(text):
                        continue
                    provider = a.get("meta", {}).get("provider", "O")
                    sources = it.get("sources", [])
                    if not sources:
                        sources = [provider]
                    out.append({
                        "text": text,
                        "sources": sorted(set(sources)),
                        "products": sorted(set(article_products))
                    })
                elif isinstance(it, str):
                    text = it
                    if filter_trade_ideas and _looks_like_trade_idea(text):
                        continue
                    provider = a.get("meta", {}).get("provider", "O")
                    out.append({
                        "text": text,
                        "sources": [provider],
                        "products": sorted(set(article_products))
                    })
        return out[:limit]
    
    # Helper to gather and group by product for observations/forward_watch
    def gather_grouped(section: str, limit: int = 30) -> Dict[str, List[dict]]:
        items = gather(section, limit=limit, filter_trade_ideas=(section == "what_occurred"))
        return _group_by_product(items)

    # trade ideas - ONLY include if they have direction + trigger + timeframe
    trades = []
    for a in article_sum_jsons:
        for t in (a.get("sections", {}).get("trade_ideas", []) or []):
            if not isinstance(t, dict):
                continue
            # Hard gate: require direction + instrument + trigger + (timeframe_bucket or horizon)
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
            "model": None,  # optional if you use an LLM for narrative synthesis
        },
        "ui": {
            "title": f"{_format_date_human(date_obj)} Daily Recap",
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
            # SAME detail categories as single-article:
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

    # aggregate bullets - returns list of dicts with text, sources, products
    def gather(section: str, limit: int = 30, filter_trade_ideas: bool = False) -> List[dict]:
        out = []
        for a in article_sum_jsons:
            article_products = a.get("meta", {}).get("products", []) or []
            items = a.get("sections", {}).get(section, []) or []
            for it in items:
                if isinstance(it, dict) and it.get("text"):
                    text = it["text"]
                    # Filter out trade ideas if requested (for observations/what_occurred)
                    if filter_trade_ideas and _looks_like_trade_idea(text):
                        continue
                    provider = a.get("meta", {}).get("provider", "O")
                    sources = it.get("sources", [])
                    if not sources:
                        sources = [provider]
                    out.append({
                        "text": text,
                        "sources": sorted(set(sources)),
                        "products": sorted(set(article_products))
                    })
                elif isinstance(it, str):
                    text = it
                    if filter_trade_ideas and _looks_like_trade_idea(text):
                        continue
                    provider = a.get("meta", {}).get("provider", "O")
                    out.append({
                        "text": text,
                        "sources": [provider],
                        "products": sorted(set(article_products))
                    })
        return out[:limit]
    
    # Helper to gather and group by product for observations/forward_watch
    def gather_grouped(section: str, limit: int = 30) -> Dict[str, List[dict]]:
        items = gather(section, limit=limit, filter_trade_ideas=(section == "what_occurred"))
        return _group_by_product(items)

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
            "model": None,
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
    meta = r.get("meta", {})
    ui = r.get("ui", {})
    title = ui.get("title", "")
    providers = " | ".join(meta.get("providers", []))
    products = " | ".join(meta.get("products", []))

    def bullet_lines(items):
        """Format items with products (and sources only if > 1 source)."""
        out = []
        for it in items or []:
            if isinstance(it, dict):
                text = it.get('text','').strip()
                sources = it.get("sources", [])
                item_products = it.get("products", [])
                
                # Build parentheses: products, and sources only if > 1
                paren_parts = []
                if item_products:
                    paren_parts.append(', '.join(item_products))
                if len(sources) > 1:  # Only show sources if multiple
                    paren_parts.append(', '.join(sources))
                
                paren_str = f" ({', '.join(paren_parts)})" if paren_parts else ""
                out.append(f"- {text}{paren_str}")
        return "\n".join(out) if out else "- (none)"
    
    def grouped_bullet_lines(grouped_items):
        """Format items grouped by product category."""
        if not grouped_items or not isinstance(grouped_items, dict):
            return "- (none)"
        
        out = []
        # Sort products alphabetically, but put "Other" last
        sorted_products = sorted([p for p in grouped_items.keys() if p != "Other"])
        if "Other" in grouped_items:
            sorted_products.append("Other")
        
        for product in sorted_products:
            items = grouped_items.get(product, [])
            if items and len(items) > 0:
                out.append(f"{product}")  # Don't add leading newline - handled by join
                for it in items:
                    if isinstance(it, dict):
                        text = it.get('text','').strip()
                        if text:  # Only add if text is not empty
                            sources = it.get("sources", [])
                            
                            # Only show sources if > 1 (no product parentheses - product is already the header)
                            sources_str = f" ({', '.join(sources)})" if len(sources) > 1 else ""
                            out.append(f"  - {text}{sources_str}")
        
        if not out:
            return "- (none)"
        
        # Join with newlines - no leading newline since first item is product name
        return "\n".join(out)

    secs = r.get("sections", {})
    trades = secs.get("trade_ideas", {})
    def trade_lines(lst):
        out = []
        for t in lst or []:
            timeframe = t.get('timeframe_bucket') or t.get('horizon', '')
            out.append(
                f"- {t.get('direction','').upper()} {t.get('instrument','')} | "
                f"{t.get('trigger','')} | timeframe={timeframe} | "
                f"conf={t.get('confidence_0_100','')} | sources={','.join(t.get('sources',[]))}"
            )
        return "\n".join(out) if out else "- (none)"

    return f"""{title}
Products: {products}
Sources: {providers}

TL;DR
{bullet_lines(secs.get("tldr"))}

OBSERVATIONS
{grouped_bullet_lines(secs.get("observations"))}

FORWARD WATCH
{grouped_bullet_lines(secs.get("forward_watch"))}

TRADE IDEAS — 1-3 DAYS
{trade_lines(trades.get("d_1_3"))}

TRADE IDEAS — 1-2 WEEKS
{trade_lines(trades.get("w_1_2"))}

TRADE IDEAS — >2 WEEKS
{trade_lines(trades.get("gt_2w"))}

TRADE IDEAS — WATCHLIST
{trade_lines(trades.get("watchlist_only"))}

WARNINGS
{bullet_lines(secs.get("warnings"))}

TIPS & REMINDERS
{bullet_lines(secs.get("tips_reminders"))}

CROSS-ASSET IMPACTS
{bullet_lines(secs.get("cross_asset_impacts"))}

SCENARIOS
{bullet_lines(secs.get("scenarios"))}
"""

