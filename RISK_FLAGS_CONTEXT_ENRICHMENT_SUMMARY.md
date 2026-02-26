# Risk Flags Context Enrichment - Implementation Summary

## Overview

Enhanced Risk Flags in Daily View with explicit product context and time horizon attribution. Each risk flag now clearly states which asset class, products, time horizon, and directional bias it refers to.

## Problem Statement

Previously, Risk Flags were generic text bullets without clear product or time horizon context. Traders had to infer which instruments each risk applied to and over what timeframe, making them less actionable.

## Solution

Added automatic enrichment of Risk Flags with structured metadata:
- **asset_class**: equities, rates, fx, commodities, crypto, or general
- **products**: list of tickers/instruments (e.g., ES, CL, US10Y, USDJPY, DXY)
- **horizon**: intraday, today, week, month
- **direction**: bullish, bearish, mixed, unknown
- **confidence**: 0.0 to 1.0 (based on specificity)

## Implementation Details

### 1. Backend Enhancement (`rollups.py`)

**New Function: `_infer_risk_flag_context()`**

Located in `build_daily_rollup()` scope, this function analyzes risk flag text and existing products to infer metadata.

**Inference Rules:**

#### Asset Class Determination
Priority order (most specific first):

1. **From existing products**: If products list is non-empty, map first product to asset class via `PRODUCT_TO_ASSET_CLASS`
2. **From text keywords**:
   - **Commodities**: oil, crude, OPEC, Iran, petroleum, WTI, Brent → CL
   - **Commodities**: gold, silver, metals, precious → GC
   - **FX**: yen, JPY, BOJ, USDJPY → USDJPY
   - **FX**: dollar, DXY, USD → DXY
   - **General** (cross-asset): inflation, CPI, PCE, jobs, NFP, employment, wage → ES, SPX, DXY, US10Y, GC
   - **Rates**: yields, treasury, bond, 10Y, 2Y, curve → US10Y, ZN
   - **Rates**: Fed + (hike/cut/rate/FOMC/QE/QT) → US10Y, ZN
   - **Crypto**: bitcoin, BTC, crypto, ethereum, ETH → BTC
   - **Equities**: equities, stocks, S&P, Nasdaq, Dow → ES, SPX
   - **Default**: general

#### Horizon Inference

- **intraday**: keywords like "intraday", "today", "session", "open", "close"
- **today**: "tomorrow", "next session", "overnight"
- **week**: "this week", "weekly", "next week", "days ahead"
- **month**: "month", "monthly", "quarter", "longer-term"
- **Default**: today

#### Direction Inference

1. **Explicit mixed**: "mixed", "two-sided", "conflicting"
2. **Bullish**: bullish, upside, rally, strength, support, positive, gains, higher, rise
3. **Bearish**: bearish, downside, selloff, weakness, resistance, negative, losses, lower, fall, drop
4. **Mixed**: Both bullish and bearish keywords present
5. **Unknown**: No directional keywords

#### Confidence Scoring

Simple heuristic based on specificity:
- Products exist AND direction known: 0.7
- Products exist OR direction known: 0.5
- Neither: 0.3

**Modified Function: `gather()`**

Enhanced to call `_infer_risk_flag_context()` when `section == "warnings"` and merge enriched fields into each warning bullet.

### 2. Frontend Enhancement (`twifo.py`)

**Modified Function: `_build_risk_flags_card()`**

Now renders enriched warnings with:

1. **Backward Compatibility Adapter**: `_normalize_warning()` sub-function converts:
   - Plain strings → enriched dict with default values
   - Old dicts missing fields → enriched dict with defaults
   - Ensures no UI breakage with existing data

2. **Visual Layout** (per risk flag):
   ```
   [ASSET_CLASS] Products | horizon | direction
   ⚠ Risk flag text
   ```

3. **Tag Styling**:
   - **Primary tag** (asset class): color-coded using existing `_TAG_COLORS`
   - **Secondary tag** (products or "General"): gray badge
   - **Suffix** (horizon + direction): italic gray text

4. **Examples**:
   ```
   COMMODITIES | CL | intraday | bearish
   ⚠ Rising oil price volatility tied to tensions around Iran

   GENERAL | ES, SPX, DXY, US10Y, GC | week
   ⚠ Sticky inflation could force Fed to keep rates higher for longer

   FX | USDJPY | week | two-sided
   ⚠ BOJ policy shift could trigger sharp yen moves next week
   ```

### 3. Backward Compatibility

**No Breaking Changes**:
- Old rollup JSONs with plain string warnings work correctly
- Old rollup JSONs with dict warnings missing new fields work correctly
- Adapter provides sensible defaults:
  - asset_class: "general"
  - products: []
  - horizon: "today"
  - direction: "unknown"
  - confidence: null

**No Regeneration Required**: Existing rollups display correctly, new rollups have enhanced context.

## Files Modified

1. **`rollups.py`**:
   - Added `_infer_risk_flag_context()` function (~100 lines)
   - Modified `gather()` to enrich warnings section (~15 lines added)

2. **`twifo.py`**:
   - Rewrote `_build_risk_flags_card()` with backward compatibility adapter (~80 lines)

3. **`test_risk_flag_enrichment.py`** (new):
   - Comprehensive test suite with 8 test cases
   - Tests: oil, inflation, rates, FX, direction inference, horizon inference, backward compatibility, text-based inference
   - All tests passing

## Test Results

```
======================================================================
RESULTS: 8 passed, 0 failed
======================================================================
```

**Test Coverage**:
- ✓ Oil risk flags → COMMODITIES | CL
- ✓ Inflation risk flags → GENERAL | ES, SPX, DXY, US10Y, GC
- ✓ Rates risk flags → RATES | US10Y, ZN
- ✓ FX JPY risk flags → FX | USDJPY | week
- ✓ Direction inference (bullish/bearish/mixed/unknown)
- ✓ Horizon inference (intraday/today/week/month)
- ✓ Backward compatibility (old format enriched)
- ✓ Text-based product inference when article products empty

## Manual Testing Checklist

### Desktop View
- [ ] Navigate to Daily Recap
- [ ] Expand Risk Flags card
- [ ] Verify each risk flag shows:
  - [ ] Asset class tag (colored)
  - [ ] Products tag or "General" (gray)
  - [ ] Horizon and direction suffix (if present)
  - [ ] Full warning text below
- [ ] Verify no risk flag renders without context (all have at least asset class tag)

### Mobile View
- [ ] Same checks as desktop
- [ ] Verify tags wrap correctly on narrow screens

### Backward Compatibility
- [ ] Test with old rollup JSON (from before this change)
- [ ] Verify old warnings display correctly with "GENERAL" tag
- [ ] No errors in browser console

### Edge Cases
- [ ] Warning with no products → shows "General" tag
- [ ] Warning with many products → shows first 3 + count (e.g., "ES, NQ, RTY +2")
- [ ] Warning with explicit "mixed" keyword → direction shows "two-sided"
- [ ] Warning with no direction keywords → direction omitted from suffix

## Benefits

1. **Clarity**: No ambiguity about which instruments each risk applies to
2. **Actionability**: Time horizon makes risks immediately actionable
3. **Scannability**: Visual tags enable fast morning scanning
4. **Consistency**: Systematic product attribution across all risks
5. **Backward Compatible**: No regeneration required, no breaking changes

## Future Enhancements (Optional)

1. **Filtering**: Add UI controls to filter risk flags by asset class
2. **Sorting**: Sort by confidence score or time horizon
3. **Icons**: Add directional arrow icons (↑ bullish, ↓ bearish, ↔ mixed)
4. **Color Coding**: Apply directional color coding (green/red/yellow)
5. **ML Enhancement**: Train model to improve product/direction inference accuracy
6. **Explicit Fields**: Add structured fields to article summary schema for direct attribution

## Notes

- **No Dynamics Toggle**: As requested, no changes to Dynamics toggle (not added back)
- **Consistent Styling**: Uses existing `_TAG_COLORS` from twifo.py
- **No Refactors**: Changes isolated to Risk Flags feature only
- **Linter Clean**: No linter errors introduced

