# Extraction-Only Prompt (Ultra-Strict Version)

**Purpose:** Maximum strictness - only extract explicitly stated information  
**Author:** Kevin Lefebvre  
**Date:** 2026-01-26  

---

## ⚠️ WARNING: This is MORE restrictive than the previous balanced version

This prompt version requires trade ideas to be **explicitly stated** in the document.

**Difference from previous "balanced" prompt:**
- **Balanced version:** Allowed directional bias if implied (e.g., "bullish bias on equities")
- **This version:** Requires trade ideas to be explicitly written in document, otherwise outputs `(none)`

---

## Core Rules

### 1. Extraction Only
- ONLY extract information that is EXPLICITLY stated
- NO inference, NO interpretation, NO filling gaps

### 2. Absolute Price Rule
- If price NOT in source → MUST NOT output any price
- Do NOT substitute round numbers
- Do NOT guess
- Do NOT "help"

### 3. Explicit Trade Ideas Only
- ONLY include trade ideas that are explicitly written in the document
- Extract them verbatim (light paraphrase allowed, NO numeric changes)
- If document contains ZERO explicit trade ideas → output `• (none)`

### 4. No Inference
- Cannot infer directional bias from macro discussion
- Cannot generate "bullish bias" from positive tone
- Cannot create conditional logic from implications

### 5. "(none)" Default
- If section has no explicit content in source → output `(none)` exactly

---

## What This Means in Practice

### Example 1: Macro Discussion Without Explicit Trade Idea

**Document:** "Bank of America notes that sustained foreign inflows and productivity gains are supporting U.S. equity markets."

**Previous balanced output:**
```
ACTIONABLE
• Bullish bias toward U.S. equities supported by sustained foreign inflows and productivity gains
```

**This extraction-only output:**
```
ACTIONABLE
• (none)
```

**Why:** No explicit trade idea stated (e.g., "We recommend long equities")

---

### Example 2: Relative Value Discussion

**Document:** "Silver appears more attractive than gold on a relative basis given current dynamics."

**Previous balanced output:**
```
ACTIONABLE
• Prefer silver vs gold on relative value basis
```

**This extraction-only output:**
```
ACTIONABLE
• (none)
```

**Why:** No explicit trade recommendation stated

---

### Example 3: Explicit Trade Idea

**Document:** "We recommend long silver if it breaks above $26.40."

**Previous balanced output:**
```
ACTIONABLE
• Long silver — breaks above "$26.40" (0-3D)
```

**This extraction-only output:**
```
ACTIONABLE
• Long silver if breaks above "$26.40"
```

**Why:** Trade idea explicitly stated ✅

---

## When This Approach Is Appropriate

### ✅ Use Extraction-Only When:
1. Legal/compliance requires verbatim extraction
2. Source documents already contain explicit trade recommendations
3. Risk of over-interpretation is high
4. Downstream systems expect only explicit ideas

### ❌ Avoid Extraction-Only When:
1. Documents discuss macro themes without explicit trade ideas
2. Institutional research uses directional language but not explicit recommendations
3. Traders need actionable summaries from thematic research
4. Output would be mostly "(none)" and lose usefulness

---

## Comparison: Three Prompt Versions

| Aspect | Version 1: Too Strict | Version 2: Balanced | Version 3: Extraction-Only (Current) |
|--------|----------------------|---------------------|-------------------------------------|
| **Price levels** | ❌ Forbidden | ❌ Forbidden (unless quoted) | ❌ Forbidden (unless quoted) |
| **Directional bias (implied)** | ❌ Forbidden | ✅ Allowed | ❌ Forbidden |
| **Explicit trade ideas** | ✅ Required | ✅ Allowed | ✅ Required |
| **Relative preference (implied)** | ❌ Forbidden | ✅ Allowed | ❌ Forbidden |
| **Conditional logic (derived)** | ❌ Forbidden | ✅ Allowed | ❌ Forbidden |
| **Typical output** | Mostly `(none)` | Actionable ideas | Mostly `(none)` unless explicit |
| **Trader usefulness** | ❌ Low | ✅ High | ❌ Low (for thematic research) |
| **Safety** | ✅ Maximum | ✅ High | ✅ Maximum |
| **Best for** | Unknown | Institutional research | Explicit recommendations only |

---

## Expected Behavior

### Document Type: Thematic Research (No Explicit Trades)

**Sample:** "The Fed's pivot creates tailwinds for risk assets. Foreign inflows remain robust. Productivity gains continue."

**Output:**
```
TL;DR
• Fed pivot creates tailwinds for risk assets
• Foreign inflows remain robust
• Productivity gains continue

ACTIONABLE
• (none)
```

**Reason:** No explicit trade recommendation stated

---

### Document Type: Trade Recommendation Report

**Sample:** "We recommend long ES futures above 4,520. Target 4,600. Stop 4,480."

**Output:**
```
TL;DR
• Recommendation to long ES futures above 4,520
• Target 4,600, stop 4,480

ACTIONABLE
• Long ES futures above 4,520 (target 4,600, stop 4,480)
```

**Reason:** Explicit trade idea with levels ✅

---

## Structure Enforced

```
TITLE

TL;DR
• bullet
• bullet
• bullet

KEY DATA / CONTEXT
• bullet
• bullet

FORWARD WATCH / EXPECTATIONS
• bullet
• bullet

ACTIONABLE
• (none OR extracted ideas only)

TIPS & REMINDERS
• bullet
```

**Note:** Simpler structure than previous versions (fewer sections)

---

## Validation Check (Built Into Prompt)

Before finalizing output, LLM must verify:
- ✅ No numeric price appears unless present in source
- ✅ No ticker has an invented level
- ✅ No trade idea is implied rather than stated

If any violation detected → REMOVE the offending line

---

## Safety Layers Still Active

### Layer 1: Prompt ✅ (Updated to Ultra-Strict)
- Extraction only, no inference
- Explicit trade ideas required
- "(none)" if not stated

### Layer 2: Schema ✅ (Unchanged)
- `source_quote` field still required
- Forces verbatim extraction

### Layer 3: Validator ✅ (Unchanged)
- `reject_hallucinated_levels()` still runs
- Rejects any price not in source
- Fail-closed on hallucination

---

## Trade-offs

### ✅ Advantages
1. **Maximum safety** - Zero risk of over-interpretation
2. **Legally defensible** - Verbatim extraction only
3. **No hallucination risk** - Cannot infer anything
4. **Clear attribution** - Every bullet traceable to source

### ❌ Disadvantages
1. **Low trader usefulness** - Most thematic research → `(none)`
2. **Misses directional signals** - Cannot extract bias from macro discussion
3. **Loses institutional context** - Cannot translate themes to positioning
4. **Poor signal-to-noise** - Verbose PDFs → minimal actionable output

---

## When to Use Each Version

### Use Extraction-Only (This Version) If:
- Source documents contain explicit trade recommendations
- Compliance requires verbatim extraction
- Risk tolerance for interpretation is zero
- Downstream systems expect only explicit ideas

### Use Balanced Version If:
- Source documents are thematic institutional research
- Traders need actionable directional signals
- "Bullish bias" is useful even without price levels
- Interpretation of macro themes is acceptable

### Use Previous Strict Version If:
- Testing maximum safety constraints
- (Not recommended - over-penalizes)

---

## Expected Output Patterns

### Most Institutional Research
```
ACTIONABLE
• (none)
```

**Why:** Institutional research discusses themes, doesn't explicitly state "We recommend long ES"

---

### Explicit Trade Recommendation Reports
```
ACTIONABLE
• Long silver breaks above "$26.40"
• Short crude if closes below "$68"
```

**Why:** Document explicitly states trade setups with levels

---

## Files Modified

| File | Change | Lines |
|------|--------|-------|
| `summarize_pdf.py` | Replaced system prompt (lines 779-856) | ~50 lines |
| `EXTRACTION_ONLY_PROMPT.md` | Documentation | +450 (new) |

**Net change:** ~50 lines (prompt replacement only)

---

## Recommendation

**For typical institutional research (thematic, macro-focused):**
→ Use the **Balanced version** (previous implementation)

**For explicit trade recommendation reports:**
→ Use this **Extraction-Only version**

**Current state:** Extraction-Only is active

**To revert to Balanced:** Replace system_prompt with balanced version from `BALANCED_PROMPT_UPDATE.md`

---

## Status

- [✅] Extraction-only prompt implemented
- [✅] Ultra-strict rules enforced
- [✅] Validator still active
- [✅] Quality gate still runs
- [⚠️] **Warning:** Output will be mostly `(none)` for thematic research

**User should decide:** Which prompt version to use based on document type.
