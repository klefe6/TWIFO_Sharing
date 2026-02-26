# Daily Rollup/Summary Analysis for Futures Trading

## Current Situation Overview

### Existing Infrastructure

**Status:** ✅ Fully operational daily rollup system with recent major upgrade

### Files & Architecture

#### Core System Files

1. **`rollups.py`** (987 lines)
   - Main rollup builder module
   - **Deterministic aggregation** (no LLM)
   - Schema: `twifo.rollup.v1`
   - Recently upgraded with asset-class grouping

2. **`generate_rollup_clean.py`** (481 lines)
   - Wrapper/CLI for generating rollups
   - Commands: `daily`, `weekly`, `daily-range`
   - Supports both deterministic and LLM modes

3. **`rollup_aggregator.py`**
   - LLM-powered rollup generation (alternative approach)
   - Schema: `twifo.rollup.v2`
   - Currently available but not used by default

4. **`rollup_schema.py`**
   - Schema documentation
   - Defines structure for `twifo.rollup.v1`

---

## What the System Currently Provides

### Sections Available in Daily Rollups

Based on the recent upgrade (completed 2026-02-13), the daily rollup includes:

```json
{
  "sections": {
    // 1. WARNINGS (always first - critical for risk management)
    "warnings": [
      {"text": "Warning text", "sources": ["GM", "MS"]}, ...
    ],
    
    // 2. EXECUTIVE SNAPSHOT (NEW - most important insights)
    "executive_snapshot": [
      {"text": "Key insight", "sources": ["GM"]}, ...
    ],  // Max 5 bullets, frequency-weighted (≥2 mentions OR high volatility)
    
    // 3. TLDR (quick overview)
    "tldr": [
      {"text": "TLDR point", "sources": ["GM"]}, ...
    ],  // Max 6 items
    
    // 4. OBSERVATIONS (backward-looking, grouped by asset class)
    "observations": {
      "EQUITIES": [{"text": "...", "sources": [...]}],
      "RATES": [...],
      "COMMODITIES": [...],
      "FX": [...],
      "VOLATILITY": [...],
      "CRYPTO": [...],
      "GENERAL": [...]
    },
    
    // 5. FORWARD WATCH (forward-looking, grouped by asset class)
    "forward_watch": {
      "EQUITIES": [...],
      "RATES": [...],
      "COMMODITIES": [...],
      // ... same structure as observations
    },
    
    // 6. VOLATILITY BY ASSET CLASS (NEW - quantified risk metrics)
    "volatility_by_asset_class": {
      "EQUITIES": {
        "expected_volatility": "Medium",
        "directional_skew": "Bullish",
        "confidence_score": 2.33,
        "sources": ["GM", "MS"]
      },
      "COMMODITIES": {...},
      // ... per asset class
    },
    
    // 7. TRADE IDEAS (structured by product with bias/levels/catalyst)
    "trade_ideas": [
      {
        "product": "ES",
        "bias": "Bullish",
        "catalyst": "Rate cuts + earnings",
        "setup": "Break above 5800",
        "key_levels": "Support 5750, Resistance 5850",
        "risk": "Below 5700",
        "time_horizon": "1-2 weeks",
        "volatility_impact": "Medium",
        "sources": ["GM"]
      }, ...
    ],
    
    // 8. Additional context sections
    "stocks": [...],            // Individual stock mentions (Top 10 + banks only)
    "other_futures": [...],     // Non-standard futures
    "forex": [...],             // FX-specific items
    "other": [...],             // Uncategorized
    "consensus_catalysts": [...],  // Top 3 consensus catalysts
    "conflicts_uncertainties": [...],  // Top 3 conflicts
    "tips_reminders": [...],
    "cross_asset_impacts": [...],
    "scenarios": [...],
    "sources": [...]            // Article metadata
  }
}
```

### Asset Classes (Futures-Focused)

```python
ASSET_CLASSES = [
    "EQUITIES",      # ES, NQ, RTY, Dow
    "RATES",         # ZN, ZB, ZF, ZT, TN, UB
    "COMMODITIES",   # GC, SI, CL, NG, HG, ZC, ZS, ZW, HO, RB
    "FX",            # EUR, GBP, JPY, CHF, AUD, CAD
    "VOLATILITY",    # VIX
    "CRYPTO",        # BTC
    "CREDIT",        # (reserved for future use)
    "GENERAL"        # Uncategorized/macro
]
```

### Product Coverage

**Equity Indices:**
- ES (E-mini S&P 500)
- NQ (Nasdaq 100)
- RTY (Russell 2000)
- Dow (Dow Jones)

**Rates:**
- ZN (10-Year Note)
- ZB (30-Year Bond)
- ZF (5-Year Note)
- ZT (2-Year Note)
- TN, UB

**Commodities:**
- **Metals:** GC (Gold), SI (Silver), HG (Copper)
- **Energy:** CL (Crude Oil), NG (Natural Gas), HO (Heating Oil), RB (RBOB Gas)
- **Agriculture:** ZC (Corn), ZS (Soybeans), ZW (Wheat)

**FX:**
- EUR, GBP, JPY, CHF, AUD, CAD

**Other:**
- VIX (Volatility Index)
- BTC (Bitcoin)

---

## Key Features of Current System

### ✅ Strengths

1. **Asset-Class Grouping**
   - Observations and forward_watch organized by EQUITIES, RATES, COMMODITIES, FX, etc.
   - Makes it easy to focus on specific markets

2. **Executive Snapshot**
   - Auto-generated top 5 most important points
   - Frequency-weighted (≥2 mentions OR high volatility impact)
   - Deduplicates similar content

3. **Volatility Metrics**
   - Per-asset-class volatility aggregation
   - Expected volatility (High/Medium/Low)
   - Directional skew (Bullish/Bearish/Neutral)
   - Confidence score (numeric, weighted)

4. **Warnings Always First**
   - Critical risk information never buried
   - Immediately visible

5. **Equity Suppression**
   - Individual stocks filtered unless Top 10 market cap or large banks
   - Keeps focus on futures/macro

6. **Deterministic**
   - Same inputs → same outputs
   - No LLM variability (unless you opt-in with `--llm`)

7. **Structured Trade Ideas**
   - Product-specific with bias, catalyst, levels, risk, timeframe
   - Sources tracked for credibility

### ⚠️ Current Limitations

1. **No Web UI Yet**
   - Daily view has placeholder: "Daily rollup summary coming soon..."
   - Rollups exist as JSON/PDF files but not rendered in Daily View

2. **Older Rollups Need Regeneration**
   - Rollups from before 2026-02-13 don't have new sections
   - Missing: `executive_snapshot`, `volatility_by_asset_class`, asset-class grouping

3. **Executive Snapshot Sometimes Empty**
   - If no items mentioned ≥2 times AND no high volatility, snapshot is empty
   - Could be enhanced with smarter selection logic

4. **No Visualization**
   - All text-based, no charts/tables for volatility or price levels

---

## Sample Rollup Data (2026-01-05)

**Articles included:** 8  
**Providers:** GM, O, TME  
**Sections present:** tldr, observations, forward_watch, trade_ideas, warnings, tips_reminders, cross_asset_impacts, scenarios, sources

**Note:** This is an older rollup (before the upgrade), so it:
- ❌ Does NOT have `executive_snapshot`
- ❌ Does NOT have `volatility_by_asset_class`
- ❌ Uses old product-code grouping instead of asset-class grouping

---

## How to Generate Current Rollups

### Command-Line Usage

```bash
cd "c:\Coding Projects\TWIFO_Sharing"

# Generate daily rollup for specific date
python generate_rollup_clean.py daily 2026-02-11

# Generate weekly rollup (Monday date)
python generate_rollup_clean.py weekly 2026-02-10

# Batch generate (date range)
python generate_rollup_clean.py daily-range 2026-02-01 2026-02-14
```

### Output Location

```
C:\Users\H&CDanHughes\Hughes & Company\
  Hughes & Company - Documents\
    8_Research\
      FOLDERS_AVAILABLE_ONLINE\
        rollups\
          daily\
            ROLLUP_DAILY_20260211__sum.json
            ROLLUP_DAILY_20260211__sum.txt
            ROLLUP_DAILY_20260211__sum.pdf
```

---

## Recommended Display Strategy for Daily View

### Option 1: Compact Summary Card (Recommended for Trader Focus)

**Layout:**
```
┌────────────────────────────────────────────────┐
│ 📅 Daily Summary - February 11, 2026          │
│ 8 articles • GM, ING, Others                   │
├────────────────────────────────────────────────┤
│ ⚠️ WARNINGS (if any)                          │
│ • Iranian retaliation risk in oil markets      │
│ • Fed blackout period - data-driven moves      │
├────────────────────────────────────────────────┤
│ 🎯 TOP INSIGHTS                                │
│ • Gold rallies on rate cut expectations        │
│ • S&P volatility clustering near support       │
│ • Oil supported by geopolitical uncertainty    │
├────────────────────────────────────────────────┤
│ 📊 VOLATILITY OUTLOOK                          │
│ COMMODITIES: High ↗️ (Bullish, conf 2.8)      │
│ EQUITIES: Medium ↔️ (Neutral, conf 2.1)       │
│ RATES: Low ↘️ (Bearish, conf 1.5)             │
├────────────────────────────────────────────────┤
│ 💡 KEY TRADES                                  │
│ GC (Gold): Long above 2640, target 2680        │
│ ES (S&P): Watch 5750 support, bullish above    │
│ CL (Oil): Range-bound, geopolitical premium    │
└────────────────────────────────────────────────┘
[View Full Rollup →]
```

### Option 2: Tabbed Sections (For Deep Dive)

**Tabs:**
1. **Overview** - Executive snapshot + warnings + volatility
2. **Yesterday** - Observations by asset class
3. **Today's Watch** - Forward watch by asset class
4. **Trade Ideas** - Structured by product with bias/levels
5. **Context** - Cross-asset impacts, scenarios, tips

### Option 3: Asset-Class Focused (For Specialists)

**Filters:**
```
[All] [Equities] [Rates] [Commodities] [FX] [Volatility] [Crypto]
```

Show observations, forward_watch, volatility, and trade ideas filtered by selected asset class.

---

## Implementation Recommendations

### Quick Win: Render Existing Rollup in Daily View

**Steps:**
1. Load existing rollup JSON for the target date
2. Render in right panel when "Daily Summary" button is clicked
3. Use same `render_summary_view` pattern as individual articles

**Code location to modify:**
- File: `twifo.py`
- Function: `display_daily_article_summary()`
- Line: ~3200 (where `__daily_summary__` placeholder is)

**Pseudo-code:**
```python
if folder_key == "__daily_summary__":
    # Load rollup JSON for target date
    rollup_file = DAILY_DIR / f"ROLLUP_DAILY_{date_str}__sum.json"
    
    if rollup_file.exists():
        rollup_json = json.loads(rollup_file.read_text())
        
        # Render using new render function
        content = render_daily_rollup_view(rollup_json)
        return "", content
    else:
        # Show "not generated yet" message with button to generate
        return "", html.Div([...])
```

### Enhanced: Create Dedicated Rollup Renderer

**New file:** `rollup_view.py`

**Functions needed:**
- `render_daily_rollup_view(rollup_json: dict) -> html.Div`
  - Warnings section (if any)
  - Executive snapshot (top insights)
  - Volatility by asset class (visual indicators)
  - Trade ideas (compact table or cards)
  - Expandable sections for observations/forward_watch

**Visual elements:**
- Color-coded volatility indicators (High=red, Medium=yellow, Low=green)
- Asset class icons (📈 EQUITIES, 💰 RATES, 🛢️ COMMODITIES, etc.)
- Directional arrows (↗️ Bullish, ↔️ Neutral, ↘️ Bearish)
- Warning banner (yellow background) if warnings exist

---

## Data Quality Notes

### What's Reliable
✅ Product codes (ES, GC, CL, etc.)  
✅ Asset class mappings  
✅ Provider sources  
✅ Deduplication logic  
✅ Warnings (explicitly flagged by analysts)  

### What Needs Attention
⚠️ Executive snapshot - sometimes empty  
⚠️ Confidence scores - need calibration  
⚠️ Trade idea structured fields - vary by article quality  
⚠️ Older rollups (pre-2026-02-13) - need regeneration  

---

## Next Steps to Display Daily Summary

### Phase 1: Basic Display (1-2 hours)
1. Create `render_daily_rollup_view()` function
2. Hook into existing Daily View callback
3. Show warnings + executive_snapshot + TLDR + trade ideas
4. Simple layout, no fancy UI

### Phase 2: Enhanced UI (4-6 hours)
1. Add volatility visualization
2. Asset-class filtering
3. Expandable sections
4. Color-coded risk indicators
5. Mobile-responsive layout

### Phase 3: Interactive Features (8+ hours)
1. Click trade idea to see underlying articles
2. Toggle between asset classes
3. Export daily summary as PDF
4. Compare multiple days (trend analysis)
5. Customize which sections to show

---

## Testing Strategy

### Test with Recent Rollup
```bash
python generate_rollup_clean.py daily 2026-02-11
```

Then load in Daily View and verify:
- Warnings appear first (if any)
- Executive snapshot shows top insights
- Asset classes correctly grouped
- Trade ideas have all fields
- No suppressed equity tickers appear

### Regenerate Historical Rollups
```bash
python generate_rollup_clean.py daily-range 2026-01-01 2026-02-14
```

This ensures all rollups have the new structure.

---

## Files to Reference

**Core:**
- `rollups.py` - main aggregation logic
- `ROLLUP_UPGRADE_COMPLETE.md` - recent upgrade documentation
- `rollup_schema.py` - schema definition

**Generation:**
- `generate_rollup_clean.py` - CLI wrapper
- `test_rollup_upgrade.py` - validation tests

**Future work:**
- Create `rollup_view.py` - rendering for web UI
- Update `twifo.py` line ~3200 - hook in rollup display

---

## Summary

**Current State:** Excellent deterministic rollup system with professional trader-focused aggregation. Recently upgraded with asset-class grouping, executive snapshot, and volatility metrics.

**Gap:** No web UI display yet - rollups exist as JSON/PDF but not shown in Daily View.

**Best Path Forward:** Create compact "trader's quick view" card showing warnings + top insights + volatility outlook + key trades. Use existing rollup JSON, minimal new code.

**Time Estimate:** 2-4 hours for basic display, 8-12 hours for polished UI with interactivity.
