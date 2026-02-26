# Volatility Outlook Reference Symbol - Deliverables

**Date:** 2026-02-25  
**Task:** Fix ambiguity in Volatility Outlook section by adding reference instruments

---

## 1. Diff Patch

**File:** `volatility_outlook_reference.patch`

### Changes Summary

**rollups.py:**
- Added `REFERENCE_MAPPING` dictionary with canonical instruments for each asset class
- Extended `_aggregate_volatility_by_asset_class()` to add `reference_symbol` and `bias_definition` fields
- Created `_build_bias_definition()` helper function with special FX handling

**twifo.py:**
- Added `FALLBACK_REFERENCE` mapping for backward compatibility
- Updated Volatility Outlook rendering to show reference symbol in label (e.g., "FX (DXY)")
- Added tooltip icon (ⓘ) with bias definition text
- Graceful fallback for old rollups without new fields

**Total Changes:**
- 2 files modified
- ~120 lines added
- New schema fields: `reference_symbol`, `bias_definition`

---

## 2. FX Reference Choice Explanation

**Chosen Reference: DXY (US Dollar Index)**

### Rationale:

1. **Most Common Vol Surface Anchor**: DXY is the standard reference for FX volatility in macro research and options markets

2. **Inverse Relationship Clarity**: The tooltip explicitly explains that:
   - DXY downside = EURUSD upside (USD weakness)
   - DXY upside = EURUSD downside (USD strength)

3. **Broad Market Coverage**: DXY represents a basket of major currencies (EUR, JPY, GBP, CAD, SEK, CHF), making it suitable for aggregate FX volatility

4. **Deterministic Source**: The volatility data is computed from structured article fields, not LLM-derived, so we can confidently assign a canonical reference

5. **Backward Compatible**: Old rollups without `reference_symbol` automatically fall back to DXY for FX rows

### Alternative Considered:

EURUSD was considered but rejected because:
- DXY is more commonly cited in macro research
- DXY better represents broad USD strength/weakness
- Articles may mention multiple pairs (GBP, JPY, etc.) which DXY encompasses

---

## 3. Example Rendered Output

```
// FX (DXY)  |  Medium  |  ↘️ Bearish ⓘ
// Tooltip: "Bearish bias relative to DXY. If DXY falls, EURUSD tends to rise (USD weakness)."
```

**Visual Elements:**
- **Asset Class Label**: "FX (DXY)" - shows reference instrument in parentheses
- **Volatility Level**: "Medium" - color-coded badge (yellow)
- **Directional Bias**: "↘️ Bearish" - arrow icon + text
- **Tooltip Icon**: "ⓘ" - blue circle with info icon, hoverable
- **Tooltip Text**: Full explanation of what the bias means

**For GENERAL asset class** (no single reference):
```
// GENERAL  |  Low  |  ↔️ Neutral ⓘ
// Tooltip: "Neutral bias for GENERAL. No single reference instrument."
```

---

## 4. JSON Schema Extension

### Before (Old Schema):
```json
{
  "volatility_by_asset_class": {
    "FX": {
      "expected_volatility": "Medium",
      "directional_skew": "Bearish",
      "confidence_score": 2.0,
      "sources": ["Provider A", "Provider B"]
    }
  }
}
```

### After (Extended Schema):
```json
{
  "volatility_by_asset_class": {
    "FX": {
      "expected_volatility": "Medium",
      "directional_skew": "Bearish",
      "confidence_score": 2.0,
      "sources": ["Provider A", "Provider B"],
      "reference_symbol": "DXY",
      "bias_definition": "Bearish bias relative to DXY. If DXY falls, EURUSD tends to rise (USD weakness)."
    }
  }
}
```

### New Fields:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `reference_symbol` | string \| null | Canonical instrument for the asset class | "DXY", "SPX", "US10Y", null |
| `bias_definition` | string | Tooltip text explaining the directional bias | "Bearish bias relative to DXY..." |

---

## 5. Regeneration Requirement

### ✅ **NO REGENERATION REQUIRED**

**Backward Compatibility Confirmed:**

1. **Old rollups work correctly**: UI falls back to canonical mapping when `reference_symbol` is missing
2. **No breaking changes**: All existing fields remain unchanged
3. **Graceful degradation**: Missing fields trigger fallback logic, not errors
4. **Tests confirm**: Test 4 (Backward Compatibility) passes with old schema

**When to regenerate:**
- **Optional**: Regenerate rollups to get the new tooltip text in the JSON
- **Not required**: Old rollups display correctly with fallback tooltips

---

## Complete Reference Mapping

```python
REFERENCE_MAPPING = {
    "EQUITIES": "SPX",      # S&P 500 index
    "FX": "DXY",            # US Dollar Index
    "RATES": "US10Y",       # 10-Year Treasury Yield
    "COMMODITIES": "CL",    # Crude Oil (most liquid)
    "METALS": "GC",         # Gold
    "ENERGY": "CL",         # Crude Oil
    "CRYPTO": "BTC",        # Bitcoin
    "VOLATILITY": "VIX",    # VIX Index
    "GENERAL": None,        # Too broad for single instrument
    "CREDIT": None,         # Too broad for single instrument
}
```

---

## Test Coverage

**File:** `test_volatility_outlook_reference.py`

### Tests Passed (5/5):

1. ✓ **Reference Mapping**: Canonical mapping defined correctly
2. ✓ **Aggregation**: New fields added to rollup JSON
3. ✓ **UI Rendering**: Reference symbol and tooltip display correctly
4. ✓ **Backward Compatibility**: Old rollups work without errors
5. ✓ **GENERAL Asset Class**: No reference shown (correct behavior)

**Example Test Output:**
```
Test 1 (Reference Mapping):        PASS
Test 2 (Aggregation):               PASS
Test 3 (UI Rendering):              PASS
Test 4 (Backward Compatibility):    PASS
Test 5 (GENERAL No Reference):      PASS
```

---

## Files Modified/Created

### Modified:
1. `rollups.py` - Schema extension and bias definition builder
2. `twifo.py` - UI rendering with reference symbols and tooltips

### Created:
1. `test_volatility_outlook_reference.py` - Comprehensive test suite
2. `volatility_outlook_reference.patch` - Diff patch
3. `VOLATILITY_OUTLOOK_ANALYSIS.md` - Data source analysis
4. `VOLATILITY_OUTLOOK_DELIVERABLES.md` - This file

---

## Summary

✅ **Task Complete**: All Volatility Outlook rows are now unambiguous

**Key Improvements:**
- Asset class labels show reference instrument (e.g., "FX (DXY)")
- Tooltip explains what directional bias means
- Special handling for FX inverse relationship (DXY ↔ EURUSD)
- Backward compatible with old rollups
- No regeneration required

**Result:** Users can now understand exactly what instrument the volatility bias refers to and what the directional lean means, eliminating ambiguity like "FX · Medium · Downside".

