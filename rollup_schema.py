"""
Rollup JSON Schema Documentation
Purpose: Define the exact schema for daily and weekly rollups
Author: Kevin Lefebvre
Last Updated: 2026-02-16
Schema: twifo.rollup.v1
"""

# Schema version
ROLLUP_SCHEMA_V1 = "twifo.rollup.v1"

# Schema structure documentation
ROLLUP_SCHEMA_DOC = """
Rollup JSON Schema (twifo.rollup.v1)

Structure:
{
    "schema_version": "twifo.rollup.v1",
    "kind": "rollup",
    "meta": {
        "rollup_kind": "daily" | "weekly",
        "date": "YYYY-MM-DD",  # Single date for daily, Monday date for weekly
        "week_range": null | "YYYY-MM-DD to YYYY-MM-DD",  # null for daily, range string for weekly
        "start_date": "YYYY-MM-DD",  # Only for weekly
        "end_date": "YYYY-MM-DD",  # Only for weekly
        "iso_year": int,  # Only for weekly
        "iso_week": int,  # Only for weekly
        "min_articles_required": int,
        "article_count": int,
        "providers": ["BOA", "DB", ...],  # List of provider codes
            # NOTE: Providers should be canonical firm names or short codes.
            # Single-letter provider codes are rejected except legacy 'O' (Others).
        "provider_detection": {"method": "str", "confidence": int},  # Optional: detection metadata
        "products": ["CT", "EUR", "JPY", ...],  # List of product codes
        "generated_at_iso": "ISO datetime string",
        "model": null | "model-name"
    },
    "ui": {
        "title": "Human-readable title string",
        "header_pills": [
            {"text": "Provider, Provider, ...", "type": "provider"},
            {"text": "Date string", "type": "date"},
            {"text": "Daily" | "Weekly", "type": "timeframe"}
        ],
        "chips_rows": [
            [{"text": "Product1", "type": "product"}, {"text": "Product2", "type": "product"}, ...],
            [{"text": "Source1", "type": "source"}, {"text": "Source2", "type": "source"}, ...]
        ]
    },
    "inputs": {
        "articles": [
            {
                "file": "filename.json",
                "provider": "BOA",
                "title": "Article title",
                "horizon": "w",
                "products": ["CT", "EUR"]
            },
            ...
        ]
    },
    "sections": {
        "tldr": [
            {"text": "TLDR bullet", "ai_context": "Plain-English explanation of macro impact for non-experts", "sources": ["BOA", "DB"]},
            ...
        ],
        "observations": [
            {"text": "Observation", "ai_context": "Plain-English explanation of macro impact for non-experts", "sources": ["BOA"]},
            ...
        ],
        "forward_watch": [
            {"text": "Watch item", "ai_context": "Plain-English explanation of macro impact for non-experts", "sources": ["DB"]},
            ...
        ],
        "trade_ideas": {
            "d_1_3": [
                {
                    "direction": "long" | "short" | "neutral" | "hedge",
                    "instrument": "CT/EUR/JPY/etc",
                    "trigger": "Explicit condition string",
                    "timeframe_bucket": "d_1_3",
                    "horizon": "1-3D",  # Legacy field
                    "invalidation": "Stop/invalidation condition",
                    "rationale": "Why this trade",
                    "sources": ["BOA", "DB"],
                    "related_products": ["CT", "EUR"],
                    "confidence_0_100": 75
                },
                ...
            ],
            "w_1_2": [...],
            "gt_2w": [...],
            "watchlist_only": [...]
        },
        "warnings": [
            {"text": "Warning", "ai_context": "Plain-English explanation of macro impact for non-experts", "sources": ["BOA"]},
            ...
        ],
        "tips_reminders": [
            {"text": "Tip", "ai_context": "Plain-English explanation of macro impact for non-experts", "sources": ["DB"]},
            ...
        ],
        "cross_asset_impacts": [
            {"text": "Impact", "ai_context": "Plain-English explanation of macro impact for non-experts", "sources": ["BOA"]},
            ...
        ],
        "scenarios": [
            {"text": "Scenario", "ai_context": "Plain-English explanation of macro impact for non-experts", "sources": ["DB"]},
            ...
        ],
        "sources": [
            {
                "provider": "BOA",
                "titles": ["Article title 1", "Article title 2"]
            },
            ...
        ]
    }
}

Bullet Fields:
- text: The bullet content (required)
- ai_context: Plain-English 1-2 sentence explanation of macro/product impact for non-experts (optional, added v1.1)
- sources: List of provider codes that support the claim (required)

Equity Tagging:
- Individual stock bullets are suppressed unless the ticker is market-moving
  (AAPL, MSFT, AMZN, NVDA, GOOGL, META, TSLA, BRK.B, JPM, GS, MS, BAC, WFC, C, V)
- Surviving equity bullets are prefixed with [EQUITY: TICKER] in the text field

Trade Idea Timeframe Buckets:
- d_1_3: 1-3 days (tactical)
- w_1_2: 1-2 weeks (swing)
- gt_2w: >2 weeks (position)
- watchlist_only: Watchlist items without specific timeframe

File Naming:
- Daily: ROLLUP_DAILY_YYYYMMDD__sum.json
- Weekly: ROLLUP_WEEKLY_YYYYMMDD__sum.json (YYYYMMDD is Monday date)

Output Files:
- JSON: Always generated
- TXT: Always generated
- PDF: Optional (if summary_render module available)
"""

def get_schema_doc() -> str:
    """Return schema documentation string."""
    return ROLLUP_SCHEMA_DOC

