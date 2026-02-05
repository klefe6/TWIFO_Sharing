# Balanced Anti-Hallucination Prompt - Update

**Purpose:** Allow directional trade ideas while preventing hallucinated price levels  
**Author:** Kevin Lefebvre  
**Date:** 2026-01-26  

---

## Problem with Previous Prompt

**Previous prompt was TOO strict:**
```
"If an actionable idea does not explicitly contain numeric price levels in the document,
you MUST say: 'no explicit levels provided'"
```

**Result:**
- LLM defaulted to `(none)` for everything to avoid mistakes
- Lost trader usefulness
- Summaries became generic and unhelpful

**Example of what we got:**
```
TRADE IDEAS
• (none)

STOCKS
• (none)

OTHER FUTURES
• (none)
```

Even when the document clearly said "Bank of America sees bullish bias on U.S. equities."

---

## What Changed

### Before: Over-Penalized

❌ **Forbade:** Any actionable idea without explicit price level  
❌ **Result:** Everything became `(none)`  
❌ **Lost:** Directional bias, relative preferences, conditional logic  

---

### After: Balanced

✅ **Still forbids:** Invented price levels, generic TA, outdated prices  
✅ **Now allows:** Directional bias, relative preferences, conditional logic  
✅ **Result:** Institutional-style summaries that are actionable AND safe  

---

## New Prompt Philosophy

**Core principle:**
> "If a trade idea is IMPLIED directionally but NO price level is stated, express it as a directional or conditional thesis, NOT as a price trigger."

**What counts as valid trade idea:**
1. **Directional bias** - "bullish bias", "bearish tilt", "neutral stance"
2. **Relative preference** - "prefer U.S. equities over EM", "silver outperforms gold"
3. **Conditional macro logic** - "if foreign inflows persist, equities supported"
4. **Cross-asset implications** - "rates headwind for equities", "dollar tailwind for metals"

**What still does NOT count:**
1. Made-up price levels
2. Generic technical analysis
3. Market knowledge outside the document
4. "Common sense" trades not supported by text

---

## Example Outputs

### ✅ Example 1: Directional Bias (No Price)

**Document:** "Bank of America sees bullish bias on U.S. equities over the next 1-2 weeks, driven by sustained foreign inflows and productivity gains."

**Before (too strict):**
```
TRADE IDEAS
• (none)
```

**After (balanced):**
```
TRADE IDEAS
• Bullish bias toward U.S. equities supported by sustained foreign inflows and productivity gains (1-2W)
```

**Key:** No price invented, but directional idea preserved ✅

---

### ✅ Example 2: Relative Preference

**Document:** "We prefer silver on a relative basis vs gold in scenarios of dollar softness."

**Before (too strict):**
```
TRADE IDEAS
• (none)
```

**After (balanced):**
```
TRADE IDEAS
• Relative tailwind for metals in scenarios of dollar softness
• Prefer silver vs gold on relative value basis
```

**Key:** Directional and relative, but no hallucinated levels ✅

---

### ✅ Example 3: Cross-Asset Implications

**Document:** "Rising real rates create headwinds for equity multiples, while providing support for the dollar."

**Before (too strict):**
```
TRADE IDEAS
• (none)
```

**After (balanced):**
```
TRADE IDEAS
• Rising real rates headwind for equity multiples
• Dollar supported by real rate dynamics
```

**Key:** Cross-asset logic preserved, no prices ✅

---

### ❌ Example 4: Still Rejects Hallucinations

**Document:** "Silver remains attractive on a relative basis."

**LLM (bad attempt):**
```
TRADE IDEAS
• Long silver if breaks above $25
```

**Validator:** ❌ FAIL - `hallucinated_price_level: Product SI has level '$25' not found in source`

**Correct output:**
```
TRADE IDEAS
• Bullish bias on silver based on relative attractiveness
```

**Key:** Directional idea OK, but invented level rejected ✅

---

### ✅ Example 5: Explicit Level Quoted

**Document:** "Long silver if breaks above $26.40."

**Output:**
```
TRADE IDEAS
• Long silver — breaks above "$26.40" (0-3D)
```

**Validator:** ✅ PASS - "$26.40" found in source text

**Key:** When level exists, quote it verbatim ✅

---

## Institutional Language Guide

### ✅ Approved Terms (Use These)

**Directional:**
- "bullish bias"
- "bearish tilt"
- "neutral stance"
- "upside risk"
- "downside skew"

**Relative:**
- "prefer X over Y"
- "relative strength"
- "relative weakness"
- "outperform"
- "underperform"

**Support/Pressure:**
- "supports"
- "tailwind"
- "headwind"
- "pressure"
- "drag"

**Conditional:**
- "if X persists, Y supported"
- "should X continue, Y vulnerable"
- "contingent on"
- "conditional on"

---

### ❌ Forbidden Terms (Never Use)

**Price-related:**
- "breaks above $XX"
- "support at $XX"
- "resistance at $XX"
- "target $XX"
- "entry at $XX"

(Unless the exact number appears in source)

**Generic TA:**
- "oversold"
- "overbought"
- "range-bound"
- "consolidating"

(Unless the document explicitly says so)

---

## Output Format (Strict)

```
Title (filename)

TL;DR
• 3 concise bullets summarizing the document's CORE thesis

TRADE IDEAS
• Bullet points ONLY if the document clearly implies a trade or positioning bias
• Use institutional language: "bullish bias", "relative strength", "supports", etc.
• NO prices unless explicitly stated in the document
• If none: write "• (none)"

STOCKS
• Equities or sectors ONLY if mentioned or clearly implied
• Directional or relative language ONLY
• If none: write "• (none)"

OTHER FUTURES
• Rates, commodities, crypto, volatility, etc.
• Directional or relative language ONLY
• If none: write "• (none)"

FOREX
• Dollar, crosses, EM FX, etc.
• Directional or relative language ONLY
• If none: write "• (none)"

OTHER
• Anything not fitting above (flows, positioning, regime shifts)
• If none: write "• (none)"
```

---

## Safety Checks Still in Place

### Layer 1: Prompt (Updated)
✅ Forbids invented price levels  
✅ Allows directional bias  
✅ Uses institutional language  

### Layer 2: Schema
✅ `source_quote` field required  
✅ Forces LLM to quote or abstain  

### Layer 3: Validator
✅ `reject_hallucinated_levels()` still runs  
✅ Rejects any price not in source  
✅ Fail-closed on hallucination  

---

## What Stays the Same

1. **Quality gate** - Still runs after every attempt
2. **Retry logic** - Still escalates to gpt-4o on failure
3. **Validator** - Still rejects hallucinated levels
4. **Debug artifacts** - Still captures failures
5. **Failure stub** - Still returns on double-fail

**What changed:** Only the prompt instruction to allow directional ideas

---

## Testing Strategy

### Test 1: Directional Bias Without Levels

**Input:** Document with clear directional view but no prices  
**Expected:** Directional bullets using institutional language  
**Validator:** Should pass (no price patterns detected)  

---

### Test 2: Hallucinated Level Detection

**Input:** Document with vague language  
**LLM:** Attempts to add price  
**Expected:** Validator rejects, retry triggered  

---

### Test 3: Explicit Level Quoting

**Input:** Document with explicit price  
**Expected:** Level quoted verbatim with quotes  
**Validator:** Should pass (level found in source)  

---

### Test 4: No Trade Ideas

**Input:** Document with no actionable implications  
**Expected:** `• (none)` for TRADE IDEAS section  
**Validator:** Should pass  

---

## Command to Test

```bash
cd "c:\Coding Projects\TWIFO_Sharing"

# Process a single PDF with the new prompt
python smoke_test_pdf.py path/to/bofa_report.pdf

# Verify:
# 1. Directional ideas appear (not just "(none)")
# 2. No hallucinated price levels
# 3. Institutional language used
# 4. Validator passes
```

---

## Expected Improvement

### Before (Too Strict)

**BOA Report Input:** "We see bullish bias on U.S. equities..."

**Output:**
```
TRADE IDEAS
• (none)

STOCKS
• (none)
```

**Trader reaction:** "Useless. I can't trade this."

---

### After (Balanced)

**BOA Report Input:** "We see bullish bias on U.S. equities..."

**Output:**
```
TRADE IDEAS
• Bullish bias toward U.S. equities supported by sustained foreign inflows and productivity gains (1-2W)

STOCKS
• ES / NQ: Bullish bias (1-2W)
```

**Trader reaction:** "Actionable. I know the direction and timeframe."

---

## Key Differences

| Aspect | Before (Too Strict) | After (Balanced) |
|--------|---------------------|------------------|
| Price levels | ❌ Forbidden | ❌ Still forbidden (unless quoted) |
| Directional bias | ❌ Forbidden | ✅ Allowed |
| Relative preference | ❌ Forbidden | ✅ Allowed |
| Conditional logic | ❌ Forbidden | ✅ Allowed |
| Cross-asset | ❌ Forbidden | ✅ Allowed |
| Institutional language | ❌ Lost | ✅ Required |
| Trader usefulness | ❌ Lost | ✅ Restored |
| Safety | ✅ Safe | ✅ Still safe |

---

## Why This Is The Correct Fix

**Problem:** Previous prompt was over-penalizing to avoid hallucinations  
**Solution:** Distinguish between:
- **Forbidden:** Invented numeric levels
- **Allowed:** Directional ideas grounded in document text

**Result:**
- Zero hallucinated prices (validator still runs)
- Actionable summaries (directional bias preserved)
- Institutional-style output (professional language)

**Quote from user:**
> "This is the correct fix."

---

## Files Modified

| File | Change | Lines |
|------|--------|-------|
| `summarize_pdf.py` | Replaced system prompt | ~60 lines |
| `BALANCED_PROMPT_UPDATE.md` | Documentation | +450 (new) |

**Net change:** ~60 lines (prompt replacement only)

---

## Next Steps (Optional)

**User suggested enhancements:**
1. Add `"Confidence: High / Medium / Low"` tag per section
2. Add `"Document-derived vs Model-derived"` flags
3. Split `Macro Bias` vs `Trade Expression` cleanly

**Current status:** Core fix implemented, enhancements pending

---

## Definition of Done ✅

- [✅] Prompt replaced with balanced version
- [✅] Still forbids hallucinated price levels
- [✅] Now allows directional bias and institutional language
- [✅] Validator still runs (Layer 3 unchanged)
- [✅] Quality gate still active
- [✅] No linter errors
- [✅] Documentation created

---

## Summary

**Before:** Too strict → Everything became `(none)` → Lost usefulness  
**After:** Balanced → Directional ideas allowed → Still safe from hallucinations  

**Three layers remain:**
1. **Prompt:** Now allows directional ideas (updated)
2. **Schema:** Still requires `source_quote` (unchanged)
3. **Validator:** Still rejects hallucinated levels (unchanged)

**Result:** High-signal, trader-useful summaries without inventing price levels.

**Status:** ✅ Implemented, ready for testing
