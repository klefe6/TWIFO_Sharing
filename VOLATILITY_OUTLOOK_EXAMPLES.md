# Volatility Outlook - Before & After Examples

## Problem Statement

**Before:** Rows like "FX · Medium · Downside" were ambiguous because:
- FX is not a single instrument
- "Downside" has no stated reference point
- Could mean DXY down (USD weakness) OR EURUSD down (USD strength) - opposite directions!

## Solution

Add `reference_symbol` and `bias_definition` to disambiguate every row.

---

## Example 1: FX Row

### Before (Ambiguous)
```
FX  |  Medium  |  ↘️ Bearish
```

**Problems:**
- Which currency pair?
- Bearish relative to what?
- DXY down or EURUSD down?

### After (Unambiguous)
```
FX (DXY)  |  Medium  |  ↘️ Bearish ⓘ
```

**Hover tooltip:**
> Bearish bias relative to DXY. If DXY falls, EURUSD tends to rise (USD weakness).

**Benefits:**
- ✓ Clear reference: DXY
- ✓ Explains inverse relationship
- ✓ User understands USD weakness

---

## Example 2: EQUITIES Row

### Before
```
EQUITIES  |  High  |  ↗️ Bullish
```

### After
```
EQUITIES (SPX)  |  High  |  ↗️ Bullish ⓘ
```

**Hover tooltip:**
> Bullish bias relative to SPX. Expected upside movement.

---

## Example 3: RATES Row

### Before
```
RATES  |  Low  |  ↔️ Neutral
```

### After
```
RATES (US10Y)  |  Low  |  ↔️ Neutral ⓘ
```

**Hover tooltip:**
> Neutral bias relative to US10Y. Expected neutral movement.

---

## Example 4: GENERAL Row (No Reference)

### Before
```
GENERAL  |  Medium  |  ↘️ Bearish
```

### After
```
GENERAL  |  Medium  |  ↘️ Bearish ⓘ
```

**Note:** No parenthetical reference (too broad for single instrument)

**Hover tooltip:**
> Bearish bias for GENERAL. No single reference instrument.

---

## Example 5: Old Rollup (Backward Compatibility)

### Scenario
User has an old rollup JSON without `reference_symbol` field.

### JSON (Old Schema)
```json
{
  "FX": {
    "expected_volatility": "Medium",
    "directional_skew": "Bearish",
    "confidence_score": 2.0,
    "sources": ["Provider A"]
  }
}
```

### Rendered Output
```
FX (DXY)  |  Medium  |  ↘️ Bearish ⓘ
```

**Hover tooltip:**
> Bearish bias relative to DXY. If DXY falls, EURUSD tends to rise (USD weakness).

**How it works:**
- UI detects missing `reference_symbol`
- Falls back to canonical mapping (FX → DXY)
- Generates tooltip text automatically
- No crash, no empty label

---

## Complete Volatility Outlook Card Example

```
┌─────────────────────────────────────────────────────────┐
│ 📊 Volatility Outlook                           [▼]     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  FX (DXY)         Medium   ↘️ Bearish ⓘ   conf 2.0    │
│  EQUITIES (SPX)   High     ↗️ Bullish ⓘ   conf 2.8    │
│  RATES (US10Y)    Low      ↔️ Neutral ⓘ   conf 1.2    │
│  COMMODITIES (CL) Medium   ↗️ Bullish ⓘ   conf 2.3    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Tooltips (on hover over ⓘ):**

- **FX (DXY)**: "Bearish bias relative to DXY. If DXY falls, EURUSD tends to rise (USD weakness)."
- **EQUITIES (SPX)**: "Bullish bias relative to SPX. Expected upside movement."
- **RATES (US10Y)**: "Neutral bias relative to US10Y. Expected neutral movement."
- **COMMODITIES (CL)**: "Bullish bias relative to CL. Expected upside movement."

---

## Visual Elements

### Asset Class Label
- **Format**: `{ASSET_CLASS} ({REFERENCE})`
- **Example**: `FX (DXY)`, `EQUITIES (SPX)`
- **No reference**: `GENERAL` (no parenthetical)

### Volatility Level Badge
- **High**: Red badge (#dc3545)
- **Medium**: Yellow badge (#ffc107)
- **Low**: Green badge (#28a745)

### Directional Bias
- **Bullish**: ↗️ Bullish
- **Bearish**: ↘️ Bearish
- **Neutral**: ↔️ Neutral

### Tooltip Icon
- **Symbol**: ⓘ
- **Color**: Blue (#007bff)
- **Style**: Circle border, hoverable
- **Behavior**: Shows bias definition on hover

### Confidence Score
- **Format**: `conf {score}`
- **Range**: 1.0 - 3.0
- **Color**: Gray (#999)
- **Example**: `conf 2.5`

---

## JSON Schema Comparison

### Old Schema (Before)
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

### New Schema (After)
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

**New Fields:**
- `reference_symbol`: Canonical instrument (string | null)
- `bias_definition`: Tooltip explanation text (string)

---

## Key Benefits

1. **Unambiguous**: Every row has a clear reference instrument
2. **Educational**: Tooltips explain what the bias means
3. **FX Special Handling**: Explains DXY ↔ EURUSD inverse relationship
4. **Backward Compatible**: Old rollups work with fallback mapping
5. **No Regeneration**: Existing rollups display correctly
6. **Consistent**: Same reference mapping used everywhere

---

## Implementation Notes

- **Deterministic**: All references computed from structured data, not LLM
- **Canonical Mapping**: Defined in `rollups.py` and `twifo.py`
- **Fallback Logic**: UI generates tooltip if missing from JSON
- **Test Coverage**: 5/5 tests passing, including backward compatibility
- **No Breaking Changes**: All existing fields unchanged

