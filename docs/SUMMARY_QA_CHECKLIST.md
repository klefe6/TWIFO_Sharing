# Summary prompt – manual QA checklist

Use this after prompt or pipeline changes to confirm grounding and no generic filler.

---

## 1. Two different articles → different output

- [ ] Pick **two clearly different** articles (e.g. one rates-focused, one metals/commodities).
- [ ] Run summarization for each (e.g. `smoke_test_pdf.py` or pipeline).
- [ ] Open both `*__sum.json` files.
- [ ] **TL;DR:** The three bullets differ in substance (not just one word).
- [ ] **Key Data / what_occurred / what_moved_today:** Bullets are different; no copy-paste feel.
- [ ] **Canonical hash:** `hash(json.dumps(summary, sort_keys=True))` differs between the two.

---

## 2. No generic ACTIONABLE template

- [ ] Summarize an article that **does not** state explicit price/levels for any asset.
- [ ] In `*__sum.json`, check `sections.trade_ideas`:
  - [ ] Either **empty** `[]`, or
  - [ ] No full list of ES, NQ, ZN, ZB, GC, SI, BTC, VIX, CL with “No direct trade idea” / placeholders.
- [ ] In the generated `*__sum.txt` or PDF, the ACTIONABLE section is either absent or shows “No explicit trade levels provided in the article.” (or equivalent), not a generic block for every product.

---

## 3. Numeric levels only when in source

- [ ] Pick an article that **explicitly states** a price/level (e.g. “gold at $2650” or “10y at 4.25%”).
- [ ] Check `*__sum.json` → `sections.trade_ideas`:
  - [ ] Any idea that has a numeric `key_levels` entry also has a `source_quote` (or equivalent) that contains that number.
- [ ] Pick an article with **no** explicit levels.
- [ ] Check that no trade idea has a numeric level; only placeholders like “(not provided in inputs)” or similar.

---

## 4. Products: no default “all products” list

- [ ] Summarize an article that discusses only **one or two** assets (e.g. only rates, or only gold).
- [ ] In `*__sum.json`, check `meta.products` (and any product list in the payload):
  - [ ] List is **not** exactly `["ES", "NQ", "ZN", "ZB", "GC", "SI", "BTC", "VIX", "CL"]` unless the article explicitly mentions all.
  - [ ] Products listed match what the article discusses (or “Macro” if none).

---

## 5. No generic filler phrases

- [ ] Scan `*__sum.json` and `*__sum.txt` for:
  - [ ] No “monitor key levels”, “data releases”, “await further information”, “to be determined”, “subject to change”, “pending analysis” as standalone bullets.
- [ ] Bullets are specific to the article (events, levels, or catalysts stated in the text).

---

## 6. Grounding: numeric level ↔ source snippet

- [ ] For each trade idea that has a non-placeholder numeric level in `key_levels`:
  - [ ] There is a corresponding `source_quote` (or equivalent) that contains that number verbatim (or normalized in a defined way).
- [ ] If a number appears in the summary but not in the article text, treat as a failure and note for fix.

---

**Sign-off:** Date _________  Tester _________
