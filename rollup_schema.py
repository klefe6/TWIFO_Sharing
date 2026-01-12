"""
Rollup JSON Schema Documentation
Purpose: Define the exact schema for daily and weekly rollups
Author: Kevin Lefebvre
Last Updated: 2026-01-11
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
            {"text": "TLDR bullet", "sources": ["BOA", "DB"]},
            ...
        ],
        "observations": [
            {"text": "Observation", "sources": ["BOA"]},
            ...
        ],
        "forward_watch": [
            {"text": "Watch item", "sources": ["DB"]},
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
            {"text": "Warning", "sources": ["BOA"]},
            ...
        ],
        "tips_reminders": [
            {"text": "Tip", "sources": ["DB"]},
            ...
        ],
        "cross_asset_impacts": [
            {"text": "Impact", "sources": ["BOA"]},
            ...
        ],
        "scenarios": [
            {"text": "Scenario", "sources": ["DB"]},
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

