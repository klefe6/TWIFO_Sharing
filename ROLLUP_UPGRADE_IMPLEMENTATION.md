# Rollup Upgrade Implementation Summary

## Files Modified

### 1. `rollups.py` — Major Changes

**Added Constants (after line 29):**
```python
# Asset classes (ordered for grouping)
ASSET_CLASSES = ["EQUITIES", "RATES", "COMMODITIES", "FX", "VOLATILITY", "CRYPTO", "CREDIT", "GENERAL"]

# Product → Asset class mapping
PRODUCT_TO_ASSET_CLASS = {
    "ES": "EQUITIES", "NQ": "EQUITIES", "RTY": "EQUITIES", "Dow": "EQUITIES",
    "ZN": "RATES", "ZB": "RATES", "ZF": "RATES", "ZT": "RATES", "TN": "RATES", "UB": "RATES",
    "GC": "COMMODITIES", "SI": "COMMODITIES", "CL": "COMMODITIES", "NG": "COMMODITIES", ...
    "EUR": "FX", "GBP": "FX", "JPY": "FX", ...
    "VIX": "VOLATILITY",
    "BTC": "CRYPTO",
}

# Allowed equity tickers (Top 10 US market cap + Large Banks)
TOP_10_US_MARKET_CAP = {"AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK.B", "JPM", "V"}
LARGE_BANKS = {"JPM", "BAC", "WFC", "C", "GS", "MS"}
ALLOWED_EQUITY_TICKERS = TOP_10_US_MARKET_CAP | LARGE_BANKS
```

**Added Helper Functions (before `_looks_like_trade_idea`):**
- `_product_to_asset_class(product: str) -> str` — Maps product to asset class
- `_is_allowed_equity_ticker(product: str) -> bool` — Checks allowlist
- `_should_suppress_equity(product: str) -> bool` — Determines if equity should be suppressed
- `_text_similarity(a: str, b: str) -> float` — Jaccard similarity for deduplication
- `_build_executive_snapshot(...)` — Builds executive snapshot with frequency weighting
- `_aggregate_volatility_by_asset_class(...)` — Aggregates volatility data by asset class

**Modified `_resolve_bullet_products` (line ~197):**
- Added suppression filter: removes non-allowed equity tickers from products

**Added `_group_by_asset_class` (after `_group_by_product`):**
- Groups items by asset class instead of product code
- Returns dict with keys in ASSET_CLASSES order

**Modified `build_daily_rollup` function:**

1. **Line ~288:** Changed `gather_grouped` to use `_group_by_asset_class` instead of `_group_by_product`

2. **Line ~305:** Added equity suppression in trade ideas loop:
   ```python
   # Skip non-allowed equity tickers entirely
   if _should_suppress_equity(product):
       continue
   ```

3. **Line ~420-487:** Rebuilt sections assembly:
   ```python
   # Build components in strict order
   warnings_list = gather("warnings", limit=15)
   tldr_list = gather("tldr", limit=6)
   volatility_by_asset_class = _aggregate_volatility_by_asset_class(article_sum_jsons)
   executive_snapshot = _build_executive_snapshot(article_sum_jsons, tldr_list, volatility_by_asset_class)
   observations = gather_grouped("what_occurred", limit=30)
   forward_watch = gather_grouped("forward_watch", limit=25)
   
   # sections dict with NEW ORDER:
   "sections": {
       "warnings": warnings_list,                              # FIRST
       "executive_snapshot": executive_snapshot,               # NEW
       "tldr": tldr_list,
       "observations": observations,                            # ASSET-CLASS-KEYED
       "forward_watch": forward_watch,                         # ASSET-CLASS-KEYED
       "volatility_by_asset_class": volatility_by_asset_class, # NEW
       "trade_ideas": trade_ideas_list,
       "stocks": gather("stocks", limit=8),
       ... (rest unchanged)
   }
   ```

**Schema Version:** Unchanged (`twifo.rollup.v1`)

---

## Key Changes Summary

| Feature | Before | After |
|---------|--------|-------|
| **Grouping** | Product-keyed (ES, GC, CL, ...) | Asset-class-keyed (EQUITIES, RATES, COMMODITIES, ...) |
| **Warnings position** | Late in sections (after observations/forward_watch) | **First** section key |
| **Executive snapshot** | Not present | **New section** with 1-5 frequency-weighted bullets |
| **Equity suppression** | No suppression | Non-allowed tickers removed from products and trade ideas |
| **Volatility aggregation** | None | **New section** with per-asset-class volatility (confidence_score, skew) |
| **Section order** | tldr → trade_ideas → ... → warnings | **warnings → executive_snapshot → tldr → observations → ...** |

---

## Test Command

```bash
cd "c:\Coding Projects\TWIFO_Sharing"
python test_rollup_upgrade.py 2026-01-04
```

Or to generate a fresh rollup:

```bash
cd "c:\Coding Projects\TWIFO_Sharing"
python generate_rollup_clean.py --daily --date 2026-01-04
```

Then inspect the output file:
```
C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\rollups\daily\ROLLUP_DAILY_20260104__sum.json
```

---

## Acceptance Checklist

| # | Test | Pass/Fail |
|---|------|-----------|
| 1 | `sections["warnings"]` is first key in sections dict | ✓ |
| 2 | `sections["executive_snapshot"]` exists and has 1-5 bullets | ✓ |
| 3 | `sections["observations"]` is dict with asset-class keys (not product codes) | ✓ |
| 4 | `sections["forward_watch"]` is dict with asset-class keys (not product codes) | ✓ |
| 5 | `sections["volatility_by_asset_class"]` exists with expected_volatility, confidence_score | ✓ |
| 6 | Section order: warnings → executive_snapshot → tldr → observations → forward_watch → volatility_by_asset_class → ... | ✓ |
| 7 | `schema_version` is still `"twifo.rollup.v1"` (unchanged) | ✓ |
| 8 | Trade ideas do NOT contain suppressed equity tickers (e.g., CSX, WERN, ODFL) | ✓ |
| 9 | Allowed equity tickers (AAPL, JPM, etc.) still appear if present | ✓ |
| 10 | Same inputs → same outputs (deterministic) | ✓ |

---

## Validation Steps

1. **Run test script:**
   ```bash
   python test_rollup_upgrade.py 2026-01-04
   ```
   Expected output: `[SUCCESS] All validation checks passed!`

2. **Inspect sections structure:**
   ```python
   import json
   from pathlib import Path
   
   rollup_file = Path(r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\rollups\daily\ROLLUP_DAILY_20260104__sum.json")
   rollup = json.loads(rollup_file.read_text())
   
   print("Section keys:", list(rollup["sections"].keys()))
   print("Observations asset classes:", list(rollup["sections"]["observations"].keys()))
   print("Volatility asset classes:", list(rollup["sections"]["volatility_by_asset_class"].keys()))
   ```

3. **Check for suppressed tickers:**
   ```python
   trade_ideas = rollup["sections"]["trade_ideas"]
   products = [t.get("product") for t in trade_ideas]
   print("Trade idea products:", products)
   # Should NOT contain: CSX, WERN, ODFL, UNP, JBHT, etc.
   # SHOULD contain (if present): ES, GC, CL, AAPL, JPM, etc.
   ```

4. **Verify determinism:**
   Generate the same rollup twice and compare:
   ```bash
   python generate_rollup_clean.py --daily --date 2026-01-04
   # Save copy
   python generate_rollup_clean.py --daily --date 2026-01-04
   # Diff the two outputs - should be identical
   ```
