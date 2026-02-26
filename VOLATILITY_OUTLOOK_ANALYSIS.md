# TASK 1: VOLATILITY OUTLOOK DATA SOURCE ANALYSIS

## Findings

### 1. Is it deterministic or LLM-summarized?

**DETERMINISTIC** - The volatility outlook is computed from structured fields in article sum.json files.

Path: `rollups.py` → `_aggregate_volatility_by_asset_class()` (lines 413-481)

### 2. Current Schema

Each row in `volatility_by_asset_class` has these fields:
```python
{
    "expected_volatility": str,  # "High" | "Medium" | "Low"
    "directional_skew": str,     # "Bullish" | "Bearish" | "Neutral"
    "confidence_score": float,   # Average score (1.0-3.0)
    "sources": list[str]         # Provider names
}
```

### 3. Input Data Source

Source: Individual article `volatility_impact` fields (lines 430-435):
```python
vol = a.get("volatility_impact", {})
expected = vol.get("expected_volatility", "")
skew = vol.get("directional_skew", "")
```

### 4. Asset Class Determination

Asset classes are derived from article `products` metadata (lines 439-443):
- Maps products (ES, NQ, DXY, etc.) to asset classes using `_product_to_asset_class()`
- If no products, defaults to "GENERAL"
- Aggregates across all articles mentioning that asset class

### 5. Aggregation Logic

- **expected_volatility**: Scored (High=3, Medium=2, Low=1), averaged, then mapped back
- **directional_skew**: Mode (most common value) across all articles
- **confidence_score**: Average of volatility scores

### 6. FX Row Specifically

**Problem**: FX is an asset class, not a single instrument.

Current behavior:
- Any article with FX products (EUR, GBP, JPY, CHF, AUD, CAD, DXY) contributes to FX row
- Skew is the mode across all FX mentions
- **No reference instrument is stored** - could be DXY, EURUSD, or mixed

**Implication**: 
- "FX · Medium · Downside" is ambiguous
- Could mean DXY downside (USD weakness) OR EURUSD downside (USD strength)
- These are opposite directions!

## Conclusion

✓ **Fully deterministic** - computed from structured article fields
✓ **No LLM involvement** in aggregation
✓ **Missing field**: reference_symbol (which instrument the bias refers to)
✓ **Safe to extend schema** - add reference_symbol and bias_definition
✓ **Must handle missing fields** - old rollups don't have these fields

## Recommendation

Extend schema with:
1. `reference_symbol`: Canonical instrument for each asset class
2. `bias_definition`: Tooltip text explaining what the bias means
3. Fallback to canonical mapping when field missing (backward compatibility)

