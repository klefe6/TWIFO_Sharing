# Current Article Summary Prompt

**AUTHORITATIVE:** This is the **only** authoritative prompt doc for TWIFO_Sharing. Do not use archived or other prompt docs for current behavior. The live prompt code is `twifo_prompts/prompts/article_prompts.py`.

**Last Updated:** 2026-02-12

## What the Prompt Is For

The prompt drives **article summarization** — converting research PDFs into structured JSON summaries for active traders. Output is used by:

- Main web app (twifo.py) for display
- Daily and weekly rollups (rollups.py, generate_rollup_clean.py)
- PDF summary rendering (summary_render.py)

---

## Version

| Field | Value |
|-------|-------|
| **PROMPT_VERSION** | `1.2` |
| **Live code path** | `twifo_prompts/prompts/article_prompts.py` |

---

## Changelog

### v1.2 (2026-02-12)

**New features:**

| Feature | Description |
|---------|-------------|
| **Dynamic entities** | No forced product grids. `_meta.primary_entities` lists only tickers central to the article thesis (max 6). |
| **Fingerprint anchoring** | `fingerprint_quotes[]` — 3-6 short verbatim quotes (10-30 words) unique to the document. Reduces "all summaries look the same" problem. |
| **Numeric registry** | `numeric_claims[]` — every number used anywhere in the JSON must appear here with `value`, `context`, and `source_quote`. Single source of truth for numeric grounding. |
| **Chart-only logic** | `chart_score_0_3`, `chart_text_sources_used[]`, `chart_observations[]` — structured chart/table assessment. |
| **Lean placeholders** | Empty arrays = `[]`. Scalar empties = `"(none)"`. Eliminated `"(not provided in inputs)"` and `["(none)"]` patterns. |

**Breaking changes:** None. All v1.1 section keys (`what_moved_today`, `what_can_move_tomorrow`, `trade_ideas`, `tldr`, `what_occurred`, `forward_watch`, `warnings`, `tips_reminders`, `cross_asset_impacts`, `scenarios`) are preserved for rollup compatibility.

**Schema additions (additive only):**
- `_meta.primary_entities` — explicit entities only
- `fingerprint_quotes` — verbatim provenance anchors
- `numeric_claims[]` — `{value, context, source_quote}`
- `chart_text_sources_used[]` — chart extraction methods
- `chart_observations[]` — factual chart observations

### v1.1 (2026-02-05)

- Strict grounding + numeric quote rule
- Anti-hallucination enforcement
- Content-dependent output requirement

### v1.0 (2026-02-04)

- Initial prompt with product grid, volatility impact, sentiment indicator

---

## Critical Rules (Summarized)

### Anti-Hallucination (Strengthened in v1.2)

- No invented numeric price levels, targets, strikes, or support/resistance unless explicitly in the document
- **Every number in the entire JSON must have a matching `numeric_claims[]` entry** with `source_quote`
- If you cannot quote the source snippet, DROP the number entirely
- `fingerprint_quotes[]` must be verbatim — no paraphrasing

### Dynamic Entities (New in v1.2)

- Do NOT output a fixed product grid (ES, NQ, ZN, ZB, GC, SI, BTC, VIX, CL)
- `_meta.primary_entities` contains ONLY tickers central to the article's thesis (max 6)
- Map common names to standard tickers (gold → GC, S&P 500 → ES, 10-year → ZN)
- Omit entire product categories if the article doesn't discuss them

### Fingerprint Anchoring (New in v1.2)

- 3-6 short verbatim quotes (10-30 words each) from the article
- Must be unique to THIS document — captures distinctive voice, key claims, unique data
- Serves as provenance anchors for traceability
- NOT paraphrased — exact text from the source

### Numeric Registry (New in v1.2)

Every number used anywhere in the JSON must appear in `numeric_claims[]`:

```json
{
  "value": "5,450",
  "context": "ES support level",
  "source_quote": "exact sentence from article containing 5,450"
}
```

If `source_quote` cannot be provided, the number must be dropped from the entire output.

### Chart Logic (New in v1.2)

| Field | Description |
|-------|-------------|
| `chart_score_0_3` | 0 = no charts, 1 = minor, 2 = meaningful data, 3 = chart-heavy |
| `chart_text_sources_used` | Which extraction methods produced chart data (e.g. `table_headers`, `axis_labels`) |
| `chart_observations` | 1-3 factual observations from chart/table data |

### Lean Placeholders (New in v1.2)

| Type | Empty value |
|------|-------------|
| Array field | `[]` |
| Scalar string | `"(none)"` |
| Numeric field | `0` or `null` |

**Eliminated:** `"(not provided in inputs)"`, `["(none)"]`, `["(not provided in inputs)"]`

### Volatility Impact (Unchanged)

- `expected_volatility`: Low / Medium / High
- `drivers`: 2-4 specific drivers from the article
- `directional_skew`: Upside / Downside / Two-sided
- `confidence_0_100`: confidence in the assessment

### Machine-Friendly Bullets (Unchanged)

- Short bullets only; no prose paragraphs
- Consistent phrasing; avoid stylistic variation
- Deterministic output for daily rollup aggregation
- No placeholder phrases

---

## Schema Fields Downstream Depends On

### Core Sections (Rollup-Compatible)

| Field | Consumer | Notes |
|-------|----------|-------|
| `what_moved_today` | Rollups | Past-tense observations |
| `what_can_move_tomorrow` | Rollups | Forward-looking catalysts |
| `tldr` | UI, rollups | Exactly 3 bullets |
| `trade_ideas` | PDF renderer, rollups | Per-product structure; dynamic (no forced grid) |
| `what_occurred` | Rollups | Factual events |
| `forward_watch` | Rollups | Upcoming catalysts |
| `warnings` | Rollups | Risk factors |
| `tips_reminders` | Rollups | Educational context |
| `cross_asset_impacts` | Rollups | Cross-asset relationships |
| `scenarios` | Rollups | If/Then scenarios |

### New Fields (v1.2)

| Field | Consumer | Notes |
|-------|----------|-------|
| `_meta.primary_entities` | UI, rollups | Explicit tickers only (max 6) |
| `fingerprint_quotes` | Provenance, dedup | 3-6 verbatim quotes |
| `numeric_claims[]` | Validation, audit | Every number with source_quote |
| `chart_score_0_3` | UI, PDF renderer | Chart content assessment |
| `chart_text_sources_used` | Debugging | Chart extraction methods |
| `chart_observations` | PDF renderer | Factual chart observations |

### Existing Fields (Unchanged)

| Field | Consumer | Notes |
|-------|----------|-------|
| `volatility_impact` | Daily rollups, IB clients | Expected structure |
| `sentiment_indicator` | Rollups | `risk_on_off`, `confidence_0_100`, `rationale` |
| `explain_like_refresher` | UI | Single concept |
| `score_0_10` | UI, sorting | Overall relevance score |
| `chart_score_0_3` | UI | Chart content score (now with supporting fields) |

---

## Full JSON Schema (v1.2)

```json
{
  "_meta": {
    "primary_entities": ["ES", "GC"]
  },
  "fingerprint_quotes": [
    "exact verbatim quote from article",
    "another unique quote",
    "third quote"
  ],
  "numeric_claims": [
    {
      "value": "5,450",
      "context": "ES support level",
      "source_quote": "exact sentence containing 5,450"
    }
  ],
  "what_moved_today": ["Past tense bullet 1", "..."],
  "what_can_move_tomorrow": ["Forward catalyst 1", "..."],
  "trade_ideas": [
    {
      "product": "ES",
      "bias": "Bullish",
      "catalyst": "...",
      "setup": "...",
      "key_levels": ["5,450", "5,500"],
      "source_quote": "...",
      "risk": "...",
      "time_horizon": "1-3d"
    }
  ],
  "volatility_impact": {
    "expected_volatility": "Medium",
    "drivers": ["driver1", "driver2"],
    "directional_skew": "Two-sided",
    "confidence_0_100": 70
  },
  "tldr": ["Bullet 1", "Bullet 2", "Bullet 3"],
  "what_occurred": ["..."],
  "forward_watch": ["..."],
  "warnings": ["..."],
  "tips_reminders": ["..."],
  "cross_asset_impacts": ["..."],
  "scenarios": ["..."],
  "sentiment_indicator": {
    "risk_on_off": "Neutral",
    "confidence_0_100": 50,
    "rationale": "..."
  },
  "chart_score_0_3": 1,
  "chart_text_sources_used": ["table_headers"],
  "chart_observations": ["observation from chart"],
  "explain_like_refresher": "concept explanation",
  "score_0_10": 7
}
```

---

## Rollup Compatibility

All v1.1 section keys are preserved. Rollups (`rollups.py`) consume:

- `sections.what_moved_today` → gathered into observations
- `sections.what_can_move_tomorrow` → gathered into forward_watch
- `sections.trade_ideas` → aggregated by product
- `sections.tldr` → gathered into rollup tldr
- `sections.what_occurred` → gathered into observations
- `sections.forward_watch` → gathered into forward_watch
- `sections.warnings` → gathered
- `sections.tips_reminders` → gathered
- `sections.cross_asset_impacts` → gathered
- `sections.scenarios` → gathered
- `volatility_impact` → aggregated
- `sentiment_indicator` → aggregated

New v1.2 fields (`_meta.primary_entities`, `fingerprint_quotes`, `numeric_claims`, `chart_*`) are additive and ignored by rollups unless explicitly consumed.

---

## Provenance

Each summary includes `meta.prompt_version`, `meta.prompt_source_file`, `meta.prompt_sha256`, and `meta.code_git_commit` for traceability.

---

## Migration Notes

- v1.1 summaries remain fully compatible — no reprocessing required
- v1.2 summaries add new fields but do not remove any existing ones
- Rollup code does not need changes for v1.2 (new fields are additive)
- PDF renderer and UI can optionally display new fields (fingerprint_quotes, chart_observations)
