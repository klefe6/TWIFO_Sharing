# Article Summary Prompt Upgrade - Trader-Grade Output

**Purpose:** Upgrade article summarization to produce trader-grade, non-generic output with strict anti-hallucination controls  
**Author:** Kevin Lefebvre  
**Date:** 2026-01-26  

---

## Summary of Changes

### 1. **Rewritten LLM Prompts** (Lines 513-565)

**File:** `summarize_pdf.py`  
**Function:** `llm_summarize_to_json()`

#### New System Prompt (Exact)
```
You are a professional sell-side research distillation engine for ES/NQ futures traders. STRICT ANTI-HALLUCINATION: Copy numbers/levels/dates EXACTLY from document or write '(not provided in inputs)'. NEVER invent prices, yields, percentages, or dates. Prioritize: tradable ideas > volatility drivers > specificity. Output MUST be valid JSON only. No markdown, no explanations, just JSON.
```

#### New User Prompt (Exact - Key Sections)
```
Create a trader-focused summary. Return ONLY valid JSON with this EXACT structure:

{
  "what_moved_today": ["Past tense: what happened + numeric impact if stated", ...],
  "what_can_move_tomorrow": ["Forward-looking: catalyst + conditional setup", ...],
  "trade_ideas": {
    "ES": {"bias": "Bullish/Bearish/Neutral", "catalyst": "why", "setup": "If X then Y", "key_levels": ["exact quote from doc"], "risk": "invalidation", "time_horizon": "1-3D/1-2W/>2W"},
    "NQ": {...},
    "GC": {...},
    "SI": {...},
    "VIX": {...}
  },
  "tldr": ["Event → impact → assets affected", ...],
  "what_occurred": ["Factual past events with numbers if stated", ...],
  "forward_watch": ["Upcoming catalysts/events", ...],
  "warnings": ["Risk factors", ...],
  "tips_reminders": ["Educational context", ...],
  "cross_asset_impacts": ["How X affects Y", ...],
  "scenarios": ["If/Then scenarios", ...],
  "sentiment_indicator": {
    "risk_on_off": "Risk-On/Risk-Off/Mixed",
    "confidence_0_100": 75,
    "rationale": "Why this sentiment (reference article only)"
  },
  "explain_like_refresher": "One key concept from article + how it impacts indices/rates/metals (or '(not provided in inputs)' if none)",
  "score_0_10": 7,
  "chart_score_0_3": 2
}

CRITICAL ANTI-HALLUCINATION RULES:
1. NEVER invent numeric values (prices, yields, %, dates, times). Copy EXACTLY from document or write '(not provided in inputs)'.
2. key_levels MUST be a list of exact quotes from document. If none stated, use ['(not provided in inputs)'].
3. what_moved_today: Past tense events ONLY. If numeric impact stated, include it verbatim.
4. what_can_move_tomorrow: Forward-looking catalysts. Use conditionals (If/When/Should).
5. trade_ideas: MUST include ES, NQ, GC, SI, VIX (even if Neutral).
6. sentiment_indicator: ALWAYS present. Analyze article tone.
7. explain_like_refresher: Pick ONE concept discussed + explain impact.

QUALITY RULES (AVOID GENERIC FILLER):
8. NO repeated bullets. Each bullet must be unique.
9. NO placeholder phrases: 'pending analysis', 'monitor key levels', 'data releases', etc.
10. NO suspiciously short bullets (< 20 chars). Be specific.
11. Prioritize order: Indices (ES/NQ) → Rates (ZN/ZB) → Metals (GC/SI) → Others.
12. tldr: MAX 3 bullets. Focus on tradable catalysts, not generic macro.
13. If article has minimal trading relevance, be honest: compress to 1-2 bullets + set score_0_10 low.
14. score_0_10: Rate trading usefulness (0=useless, 10=critical). Be honest.
15. chart_score_0_3: Count charts/tables (0=none, 1=few, 2=several, 3=chart-heavy).
```

---

### 2. **New Schema Fields** (Lines 613-631, 705-722)

**Added to twifo.sum.v1 schema:**

#### Required Section Keys (Always Present)
- `what_moved_today` - Past tense events with numeric impacts
- `what_can_move_tomorrow` - Forward-looking catalysts
- `trade_ideas` - Structured trade setups (ES, NQ, GC, SI, VIX required)
- `tldr` - Max 3 bullets, tradable catalysts only
- `what_occurred` - Factual past events
- `forward_watch` - Upcoming catalysts
- `warnings` - Risk factors
- `tips_reminders` - Educational context
- `cross_asset_impacts` - Cross-market effects
- `scenarios` - If/Then scenarios

#### New Top-Level Fields
- `sentiment_indicator` (object, always present):
  - `risk_on_off`: "Risk-On" / "Risk-Off" / "Mixed"
  - `confidence_0_100`: Integer confidence score
  - `rationale`: Short explanation referencing article only

- `explain_like_refresher` (string):
  - One important concept + how it impacts markets
  - Must be grounded in article text
  - Use "(not provided in inputs)" if none

#### Scoring Fields (Always Present)
- `score_0_10`: Summary usefulness (0=useless, 10=critical)
- `chart_score_0_3`: Chart density (0=none, 1=few, 2=several, 3=heavy)

---

### 3. **Enhanced Quality Gate** (Lines 132-172)

**Updated to check new fields:**
- Now includes `what_moved_today` and `what_can_move_tomorrow` in bullet collection
- Handles `key_levels` as list (not string)
- Excludes "(not provided in inputs)" from quality checks
- Maintains strict thresholds:
  - Min 3 unique bullets
  - Max 50% duplication
  - Max 40% placeholder phrases
  - Max 60% short bullets (< 20 chars)

---

### 4. **Anti-Hallucination Enforcement**

**Key Changes:**
1. **Prompt-level:** Explicit instruction to copy numbers EXACTLY or write "(not provided in inputs)"
2. **Schema-level:** `key_levels` is now a list of exact quotes (not a string)
3. **Quality gate:** Filters out "(not provided in inputs)" from quality checks
4. **Validation:** All numeric values must be verbatim from document

---

## Testing

### Regression Tests

**File:** `test_article_quality_gate.py`

**Tests:**
1. ✅ Atrocious placeholder summary → FAIL (excessive_placeholders)
2. ✅ Duplicated bullets → FAIL (excessive_duplication)
3. ✅ Trader-grade summary → PASS
4. ✅ Too few unique bullets → FAIL (too_few_unique_bullets)
5. ✅ Schema compatibility → VERIFIED

**Run tests:**
```bash
cd "C:\Coding Projects\TWIFO_Sharing"
python test_article_quality_gate.py
```

**Expected output:**
```
ALL TESTS PASSED

Quality gate is working correctly:
- Placeholder/generic summaries: FAIL [OK]
- Duplicated bullets: FAIL [OK]
- Trader-grade summaries: PASS [OK]
- Schema compatibility: VERIFIED [OK]
```

---

## Files Changed

### Modified Files

1. **`summarize_pdf.py`**
   - Lines 513-565: Rewritten system + user prompts
   - Lines 613-631: Added new field extraction
   - Lines 132-172: Enhanced quality gate for new fields
   - Lines 705-722: Updated schema construction
   - **Total changes:** ~150 lines modified

### New Files

2. **`test_article_quality_gate.py`**
   - Comprehensive regression tests
   - 5 test cases covering all quality gate scenarios
   - **Total:** ~300 lines

3. **`ARTICLE_PROMPT_UPGRADE.md`** (this file)
   - Complete documentation
   - Exact prompts (verbatim)
   - Testing instructions

---

## Exact Prompts (Verbatim)

### System Prompt
```
You are a professional sell-side research distillation engine for ES/NQ futures traders. STRICT ANTI-HALLUCINATION: Copy numbers/levels/dates EXACTLY from document or write '(not provided in inputs)'. NEVER invent prices, yields, percentages, or dates. Prioritize: tradable ideas > volatility drivers > specificity. Output MUST be valid JSON only. No markdown, no explanations, just JSON.
```

**Location:** `summarize_pdf.py`, lines 513-517

### User Prompt (Full)
See lines 519-565 in `summarize_pdf.py` for complete prompt with all 15 critical rules.

**Key sections:**
- Anti-hallucination rules (1-7)
- Quality rules (8-15)
- Schema structure with all required fields
- Explicit "(not provided in inputs)" fallback

---

## How to Run

### 1. Run Tests
```bash
cd "C:\Coding Projects\TWIFO_Sharing"
python test_article_quality_gate.py
```

### 2. Process Articles
```bash
cd "C:\Coding Projects\TWIFO_Sharing"
python db_filter_autorun.py
```
Or use batch file:
```bash
run_db_filter.bat
```

### 3. Verify Output
Check generated files:
- `*__sum.json` - Should have all new fields
- `*__sum.txt` - Should render new sections
- `*__sum.pdf` - Should show new layout

---

## Quality Gate Behavior

### Fails On:
- ❌ Placeholder phrases ("pending analysis", "monitor key levels")
- ❌ Repeated bullets (> 50% duplication)
- ❌ Too few unique bullets (< 3)
- ❌ Suspiciously short bullets (> 60% under 20 chars)

### Passes On:
- ✅ Trader-grade summaries with specific details
- ✅ Unique, informative bullets
- ✅ Proper use of "(not provided in inputs)" for missing data
- ✅ Conditional setups (If/Then) instead of predictions

### When Failed:
1. `extraction.status` set to `"failed"`
2. `extraction.reason` set to `"low_quality_output: <detail>"`
3. Sections replaced with empty unified failure stub
4. TXT/PDF render professional failure page (not normal summary)

---

## Constraints Met

✅ Minimal changes (1 file modified, 2 new test/doc files)  
✅ No new multi-pass LLM calls  
✅ OCR behavior unchanged  
✅ Schema remains compatible with twifo.sum.v1  
✅ Quality gate runs after formatting, before writing  
✅ Strict anti-hallucination enforced  

---

## Example Output

### Good Summary (Passes)
```json
{
  "what_moved_today": [
    "Fed raised rates 25bps to 5.25-5.50% range, citing core PCE at 3.4% vs 3.0% expected",
    "ES dropped 1.2% to 4385 on hawkish Powell comments"
  ],
  "what_can_move_tomorrow": [
    "If NFP Friday prints above 200k, expect further ES downside toward 4350-4320",
    "Watch for Fed speak Thursday - any softening could trigger short covering"
  ],
  "trade_ideas": {
    "ES": {
      "bias": "Bearish",
      "catalyst": "Fed hawkish pivot + sticky inflation",
      "setup": "If ES fails 4420 VWAP and VIX > 18, short to 4350-4320",
      "key_levels": ["4420 resistance (VWAP)", "4385 current", "4350 support"],
      "risk": "Above 4465",
      "time_horizon": "1-3D"
    }
  },
  "sentiment_indicator": {
    "risk_on_off": "Risk-Off",
    "confidence_0_100": 80,
    "rationale": "Fed hawkish pivot + sticky inflation + equity selling"
  },
  "explain_like_refresher": "Terminal rate: Peak interest rate Fed expects to reach. Higher terminal = longer restrictive policy = more pressure on equity valuations. Article suggests moving from 5.25% to 5.75%, compressing P/E multiples.",
  "score_0_10": 9,
  "chart_score_0_3": 1
}
```

### Bad Summary (Fails)
```json
{
  "what_moved_today": [
    "Pending analysis of market conditions",
    "Monitor key levels for breakout"
  ],
  "what_can_move_tomorrow": [
    "Await further information",
    "Subject to change"
  ],
  "trade_ideas": {
    "ES": {
      "catalyst": "Monitor key levels",
      "setup": "Pending analysis"
    }
  }
}
```
**Result:** FAILS with `"excessive_placeholders: 100% of bullets are generic placeholders"`

---

## Next Steps

1. **Monitor production:** Watch for quality gate failures
2. **Tune thresholds:** Adjust if too strict/lenient
3. **Collect feedback:** Trader feedback on usefulness
4. **Iterate prompts:** Refine based on real-world output

---

## Notes

- Quality gate is **always active** (no configuration needed)
- Anti-hallucination is **enforced at prompt level** (LLM instructed explicitly)
- Schema is **backward compatible** (all legacy keys present)
- Tests are **deterministic** (no LLM calls in tests)
