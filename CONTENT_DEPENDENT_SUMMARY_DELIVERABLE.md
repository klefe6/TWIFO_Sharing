# Content-Dependent Summary – Deliverable

## Summary of changes

- **Products**: No longer default to full list (ES, NQ, ZN, ZB, GC, SI, BTC, VIX, CL). Products are taken only from LLM response; if empty, inferred from article keywords via `_infer_products_from_text()` or set to `["Macro"]`.
- **ACTIONABLE**: Only trade ideas that have at least one explicit key level (after sanitization) are kept. Generic “No direct trade idea” entries are never added; ideas without explicit levels are omitted from the ACTIONABLE section.
- **Dev logs**: With `DEV_LOGGING=1`, extraction includes `products_inferred_reason` and `actionable_included_reason` and they are printed after filtering.

---

## Modified files

| File | Changes |
|------|--------|
| **TWIFO_Sharing/summary/prompts/article_prompts.py** | PRODUCTS: prompt now requires only explicitly mentioned products; removed “ALL categories MUST exist”. ACTIONABLE: only include product entries when document has both asset and explicit level. |
| **TWIFO_Sharing/summarize_pdf.py** | Added `_infer_products_from_text()`, `_has_explicit_level()`, `_filter_actionable_trade_ideas()`. Products built only from LLM response; if empty, infer or `["Macro"]`. Trade ideas built only from LLM (no default fill). After `sanitize_key_levels`, `sections["trade_ideas"]` is replaced with filtered list (only ideas with explicit levels). Extraction gets `products_inferred_reason` and `actionable_included_reason`; both logged when `DEV_LOGGING=1`. `render_sum_txt` comment updated. |
| **TWIFO_Sharing/tests/test_content_dependent_summary.py** | New test module: infer products, filter ACTIONABLE, assert products ≠ full default, different inputs → different hash, ACTIONABLE empty when no explicit levels. |

---

## Tests to run

From `TWIFO_Sharing`:

```powershell
# If pytest runs without plugin errors:
python -m pytest tests/test_content_dependent_summary.py -v

# Otherwise run assertions inline (no pytest):
python -c "
import sys; sys.path.insert(0, '.')
from summarize_pdf import _infer_products_from_text, _filter_actionable_trade_ideas
assert _infer_products_from_text('') == ([], 'empty_source')
assert 'GC' in _infer_products_from_text('Gold rallied.')[0]
j = {'sections': {'trade_ideas': [{'product':'ES','key_levels':['(not provided in inputs)']}]}}
assert len(_filter_actionable_trade_ideas(j)[0]) == 0
j2 = {'sections': {'trade_ideas': [{'product':'GC','key_levels':['2650'],'bias':'Bullish','catalyst':'Fed'}]}}
assert len(_filter_actionable_trade_ideas(j2)[0]) == 1
print('All checks passed.')
"
```

**Test assertions (from test_content_dependent_summary.py):**

- Two different summary payloads (different tldr / trade_ideas) → `hash(summary_json)` differs.
- Products is NOT equal to `["ES","NQ","ZN","ZB","GC","SI","BTC","VIX","CL"]` when LLM returns no products (infer or Macro used).
- ACTIONABLE is empty when all trade ideas have only placeholder levels (`(not provided in inputs)` / `no explicit levels provided`).
- `_infer_products_from_text` returns [] for empty/no-keyword text and includes expected tickers (e.g. GC for “gold”) when present.
- `_filter_actionable_trade_ideas` keeps only ideas with at least one non-placeholder key level.

---

## Manual verification steps

1. **Products not generic**
   - Run summarization on an article that does not mention specific tickers (e.g. pure macro theme).
   - Check `__sum.json`: `meta.products` should be `["Macro"]` or a short inferred list (e.g. from “rates”, “gold”), not the full list ES, NQ, ZN, ZB, GC, SI, BTC, VIX, CL.

2. **ACTIONABLE only with levels**
   - Run on an article with no explicit price/level mentions.
   - Check `__sum.json`: `sections.trade_ideas` should be `[]`.
   - Run on an article that states a level (e.g. “gold at $2650”): `sections.trade_ideas` should contain only entries that have explicit levels; generated PDF/TXT ACTIONABLE section should match.

3. **Different articles → different summaries**
   - Summarize two clearly different articles (e.g. one rates-focused, one metals-focused).
   - Compare `__sum.json`: `meta.products`, `sections.tldr`, and `sections.trade_ideas` should differ; `hash(json.dumps(sum_json, sort_keys=True))` should differ.

4. **Dev logging**
   - Set `DEV_LOGGING=1` and run summarization.
   - Confirm log lines: `products_inferred_reason=...` and `actionable_included_reason=...` (and existing `[DEV_LOGGING]` input_text lines if used).

---

## Functions involved (quick reference)

- **Products**: `summarize_pdf.llm_summarize_to_json` (products from `api_response["products"]`; if empty, `_infer_products_from_text(text)` or `["Macro"]`). `_infer_products_from_text()` in `summarize_pdf.py`.
- **ACTIONABLE**: `_filter_actionable_trade_ideas(sum_json)` in `summarize_pdf.py`; called in `_summarize_with_quality_retry` after `sanitize_key_levels`; replaces `sections["trade_ideas"]` with the filtered list.
- **Prompt**: `twifo_prompts/prompts/article_prompts.py` – USER_PROMPT and PRODUCTS / ACTIONABLE rules.
