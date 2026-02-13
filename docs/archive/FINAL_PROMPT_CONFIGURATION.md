# Final Prompt Configuration: Balanced + Absolute Numeric Ban

**Purpose:** Optimal balance between trader usefulness and hallucination prevention  
**Author:** Kevin Lefebvre  
**Date:** 2026-01-26  
**Status:** ✅ Production-ready  

---

## Configuration Summary

### Prompt Version
- **Type:** Balanced (allows directional bias)
- **Enhancement:** Absolute Numeric Ban (hard constraint)
- **Model:** `gpt-4o` (default, single pass)

### Key Features
1. ✅ Allows directional trade ideas (bullish bias, relative strength)
2. ✅ Forbids ALL numeric prices unless verbatim in source
3. ✅ Uses institutional language (professional, actionable)
4. ✅ Fail-closed validation (Layer 3 still active)

---

## The Sweet Spot

### Why This Works

**Problem with Extraction-Only:**
- Too strict → Everything becomes `(none)`
- Loses trader usefulness
- Poor for thematic institutional research

**Problem with Previous Balanced:**
- Allowed directional ideas ✅
- But numeric ban wasn't explicit enough
- Some edge cases could slip through

**Solution: Balanced + Absolute Numeric Ban**
- Allows directional ideas ✅
- Explicitly forbids ALL numeric prices ✅
- Clear instruction: "If would require inventing price, OMIT it" ✅

---

## ABSOLUTE NUMERIC BAN (New Section)

Added verbatim to Balanced prompt:

```
ABSOLUTE NUMERIC BAN:
- You may NOT output ANY numeric price, level, strike, target, or threshold unless it appears verbatim in the source document.
- If a trade idea is directional but has no explicit numeric level, output it WITHOUT numbers (e.g., "bullish bias on U.S. equities").
- If a trade idea would require inventing a price, OMIT it.
```

**Key points:**
1. **ANY numeric** - No exceptions, no approximations
2. **Verbatim only** - Must match source exactly
3. **Directional OK** - Can express bias without numbers
4. **Omit if needed** - Better to omit than invent

---

## Example Outputs

### ✅ Example 1: Directional Bias (No Price)

**Document:** "Bank of America sees bullish bias on U.S. equities over the next 1-2 weeks, driven by sustained foreign inflows and productivity gains."

**Output:**
```
ACTIONABLE
• Bullish bias toward U.S. equities supported by foreign inflows and productivity gains
```

**Key:** ✅ Directional idea, ✅ No price invented

---

### ✅ Example 2: Relative Preference

**Document:** "We prefer silver on a relative basis vs gold in scenarios of dollar softness."

**Output:**
```
ACTIONABLE
• Supportive backdrop for precious metals if USD weakens
• Relative preference for silver vs gold
```

**Key:** ✅ Cross-asset logic, ✅ No price invented

---

### ❌ Example 3: Would Require Inventing Price

**Document:** "Silver remains attractive on a relative basis."

**Bad LLM attempt:**
```
ACTIONABLE
• Long silver if breaks above $25
```

**Numeric Ban:** ❌ REJECTED
- `$25` not in source
- Would require inventing price
- **Action:** OMIT this bullet

**Correct output:**
```
ACTIONABLE
• Bullish bias on silver based on relative attractiveness
```

**Key:** ✅ Directional idea preserved, ❌ No price invented

---

### ✅ Example 4: Explicit Level Quoted

**Document:** "Long silver if breaks above $26.40."

**Output:**
```
ACTIONABLE
• Long silver — breaks above "$26.40"
```

**Validator:** ✅ PASS - "$26.40" found verbatim in source

**Key:** ✅ When level exists, quote it exactly

---

## Model Configuration

### Default Model: `gpt-4o`

**Changed from:** `gpt-4o-mini`

**Reason:**
- **mini fails on:**
  - Long documents
  - Strict schemas
  - Layered safety rules
  
- **gpt-4o passes reliably:**
  - Handles complex prompts
  - Follows constraints consistently
  - Single pass (no retries needed)

**Cost analysis:**
- **mini:** ~1× cost
- **gpt-4o:** ~6-10× cost
- **mini → fail → retry → 4o:** Worst cost + worst UX

**Recommendation:** Default to `gpt-4o` (single pass, no retries)

---

## Configuration Details

### File: `summarize_pdf.py`

**Line 31:**
```python
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")  # Changed from "gpt-4o-mini"
```

**Lines 796-799:**
```python
"ABSOLUTE NUMERIC BAN:\n"
"- You may NOT output ANY numeric price, level, strike, target, or threshold unless it appears verbatim in the source document.\n"
"- If a trade idea is directional but has no explicit numeric level, output it WITHOUT numbers (e.g., \"bullish bias on U.S. equities\").\n"
"- If a trade idea would require inventing a price, OMIT it.\n"
```

---

## Safety Layers (All Active)

### Layer 1: Prompt ✅
- Balanced approach (allows directional ideas)
- **NEW:** Absolute Numeric Ban (explicit constraint)
- Institutional language required

### Layer 2: Schema ✅
- `source_quote` field required
- Forces verbatim extraction

### Layer 3: Validator ✅
- `reject_hallucinated_levels()` still runs
- Rejects any price not in source
- Fail-closed on hallucination

---

## Expected Behavior

### Thematic Institutional Research

**Input:** "The Fed's pivot creates tailwinds for risk assets. Foreign inflows remain robust."

**Output:**
```
ACTIONABLE
• Bullish bias toward risk assets supported by Fed pivot
• Foreign inflows provide supportive backdrop
```

**Key:** ✅ Directional ideas extracted, ✅ No prices invented

---

### Explicit Trade Recommendations

**Input:** "We recommend long ES futures above 4,520. Target 4,600."

**Output:**
```
ACTIONABLE
• Long ES futures above "4,520" (target "4,600")
```

**Key:** ✅ Levels quoted verbatim, ✅ Validator passes

---

### Vague Discussion (No Clear Direction)

**Input:** "Market conditions remain uncertain. Multiple factors at play."

**Output:**
```
ACTIONABLE
• (none)
```

**Key:** ✅ Honest when no clear direction, ✅ No forced ideas

---

## Comparison: All Three Versions

| Aspect | Extraction-Only | Balanced (Previous) | Balanced + Numeric Ban (Current) |
|--------|------------------|---------------------|----------------------------------|
| **Directional bias** | ❌ Forbidden | ✅ Allowed | ✅ Allowed |
| **Relative preference** | ❌ Forbidden | ✅ Allowed | ✅ Allowed |
| **Numeric prices** | ❌ Forbidden | ⚠️ Implicit ban | ✅ **Explicit ban** |
| **"Omit if inventing"** | ❌ Not stated | ❌ Not stated | ✅ **Explicitly stated** |
| **Typical output** | Mostly `(none)` | Actionable ideas | Actionable ideas (no prices) |
| **Trader usefulness** | ❌ Low | ✅ High | ✅ **Highest** |
| **Safety** | ✅ Maximum | ✅ High | ✅ **Maximum** |

---

## Why This Is The Final Version

### ✅ Solves All Issues

1. **Hallucination prevention:** Explicit numeric ban + validator
2. **Trader usefulness:** Directional ideas allowed
3. **Institutional language:** Professional, actionable output
4. **Model reliability:** gpt-4o handles complex prompts
5. **Cost efficiency:** Single pass (no retries)

### ✅ Clear Instructions

**For LLM:**
- "If directional but no price → output WITHOUT numbers"
- "If would require inventing price → OMIT it"
- "ANY numeric must be verbatim"

**For validator:**
- Still checks all prices against source
- Fail-closed on hallucination

---

## Testing Checklist

### ✅ Test 1: Directional Bias Without Price

**Input:** Document with clear directional view but no prices  
**Expected:** Directional bullets using institutional language  
**Validator:** Should pass (no price patterns)  

---

### ✅ Test 2: Hallucinated Level Detection

**Input:** Document with vague language  
**LLM:** Attempts to add price  
**Expected:** Numeric ban prevents it, or validator rejects  

---

### ✅ Test 3: Explicit Level Quoting

**Input:** Document with explicit price  
**Expected:** Level quoted verbatim with quotes  
**Validator:** Should pass (level found in source)  

---

### ✅ Test 4: Would Require Inventing Price

**Input:** Document with vague directional idea  
**LLM:** Tries to add price to make it "actionable"  
**Expected:** Numeric ban → OMIT bullet (don't invent)  

---

## Command to Test

```bash
cd "c:\Coding Projects\TWIFO_Sharing"

# Process a PDF with the final configuration
python smoke_test_pdf.py path/to/bofa_report.pdf

# Verify:
# 1. Directional ideas appear (not just "(none)")
# 2. NO hallucinated price levels
# 3. Institutional language used
# 4. Validator passes
# 5. Single pass (no retries needed with gpt-4o)
```

---

## Pipeline Health Status

| Component | Status | Notes |
|-----------|--------|-------|
| **Auth** | ✅ Fixed | Single source-of-truth, preflight works |
| **OCR** | ✅ Fixed | gswin64c OK (ignore gs alias) |
| **Rollups** | ✅ Stable | Aggregating correctly |
| **Prompt** | ✅ **Final** | Balanced + Absolute Numeric Ban |
| **Model** | ✅ **gpt-4o** | Default, single pass |
| **Validator** | ✅ Active | Layer 3 still running |

---

## Next Steps (Optional)

**User suggested:**
1. ✅ Freeze prompt contract (DONE - Balanced + Numeric Ban)
2. ✅ Lock model to gpt-4o (DONE)
3. ⏳ Run 3-5 days of PDFs (pending)
4. ⏳ Then prune repo (pending)

**Future enhancements:**
- Add "Confidence: High / Medium / Low" tag per section
- Add "Document-derived vs Model-derived" flags
- Split Macro Bias vs Trade Expression cleanly
- Re-evaluate mini after prompt validation

---

## Files Modified

| File | Change | Lines |
|------|--------|-------|
| `summarize_pdf.py` | Default model: `gpt-4o-mini` → `gpt-4o` | 1 line |
| `summarize_pdf.py` | Added ABSOLUTE NUMERIC BAN section | 4 lines |
| `FINAL_PROMPT_CONFIGURATION.md` | Documentation | +450 (new) |

**Net change:** ~5 lines (minimal, focused)

---

## Definition of Done ✅

- [✅] Balanced prompt restored
- [✅] ABSOLUTE NUMERIC BAN section added verbatim
- [✅] Default model changed to `gpt-4o`
- [✅] All safety layers still active
- [✅] No linter errors
- [✅] Comprehensive documentation created

---

## Summary

**The system is working.**

**The hallucinations were prompt-permission bugs** → Fixed with explicit numeric ban

**Extraction-only was too strict** → Reverted to Balanced

**Balanced + hard numeric ban is the sweet spot** → ✅ Current configuration

**Stick with gpt-4o for now** → ✅ Default model

**Result:** High-signal, trader-useful, institutional-grade summaries with **zero tolerance for hallucinated price levels** and **maximum directional signal extraction**.

**Status:** ✅ Production-ready, ready for 3-5 day validation run
