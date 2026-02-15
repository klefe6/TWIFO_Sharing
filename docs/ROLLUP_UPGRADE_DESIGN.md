# Daily Rollup Upgrade — Design Only (No Code)

**Goal:** Upgrade existing daily rollup logic in-place. Keep `schema_version: twifo.rollup.v1`, same file naming, no v2 or parallel architecture. Improve section structure and aggregation only.

**Constraints:** Modify rollup generation logic and section structure only; deterministic behavior; no new files for rollup output.

---

## 1. Current Rollup Build Process (Detail)

### 1.1 Entry point and data flow

- **Invocation:** `generate_rollup_clean.py` → `generate_daily_rollup(target_date, min_articles, use_llm=False)` (default: deterministic path).
- **Article discovery:** `find_article_summaries_for_date(target_date)` globs `FILES_DIR` for `*_YYYYMMDD_*__sum.json` (legacy naming). Returns list of paths. `collect_daily_articles()` loads each JSON, optionally converts legacy schema to twifo.sum.v1, returns `List[dict]` of article `sum.json` objects.
- **Build:** `rollups.build_daily_rollup(date_obj, article_sum_jsons, min_articles_required)` is the single function that produces the daily rollup dict. **No use of `rollup_aggregator.py`** on the default path (aggregator is LLM/v2 and out of scope for this design).

### 1.2 Flow inside `rollups.build_daily_rollup()`

1. **Guard:** `len(article_sum_jsons) < min_articles_required` → raise.
2. **Meta derivation:**  
   `providers = sorted(unique meta.provider)`,  
   `products = sorted(unique meta.products across articles)`.
3. **Bullet gathering (product-agnostic):**
   - **`gather(section, limit, filter_trade_ideas)`:**  
     For each article, reads `sections[section]`; for each bullet (dict with `text` or string), resolves `sources` and **products** via `_resolve_bullet_products(it, text, article_products, section)`. Products come from bullet’s `products`, else `_infer_products_from_text(text, section, article_products)` (keyword regexes against `_KEYWORD_TO_PRODUCT`), else `[]` → later grouped as "General". Appends `{text, sources, products}`; then **`_dedupe_bullets(out)`** (key = normalized text lower, merge sources); returns `out[:limit]`.
   - **`gather_grouped(section, limit)`:**  
     `gather(..., filter_trade_ideas=(section=="what_occurred"))` then **`_group_by_product(items)`** → dict mapping **product code** (or `"General"`) → list of items. So every grouped section is **product-keyed** (e.g. `"ES"`, `"GC"`, `"General"`).
4. **Trade ideas (daily):**  
   Iterate articles’ `sections.trade_ideas`; for each idea with `product`, build per-product entry in `trade_ideas_by_product` (catalyst, setup, key_levels, risk, time_horizon, volatility_impact as lists; merge sources; bias upgrade Neutral→Bull/Bear). Sort products by custom priority (indices → rates → metals → crypto → other). Output **`trade_ideas_list`**: list of `{product, bias, catalyst, setup, key_levels, risk, time_horizon, volatility_impact, sources}` (catalyst/setup/… as semicolon-joined strings).
5. **Consensus/conflicts:**  
   `consensus_catalysts` from trade_ideas catalysts (first 3); `conflicts` left empty.
6. **Sources list:**  
   One dict per article: `{provider, titles}`.
7. **Assembly:**  
   One big `rollup` dict with `meta`, `ui`, `inputs`, **`sections`**. Section order in code:
   - `tldr`, `trade_ideas`, `stocks`, `other_futures`, `forex`, `other`, `consensus_catalysts`, `conflicts_uncertainties`
   - then **`observations`** (product-grouped), **`forward_watch`** (product-grouped), **`warnings`**, `tips_reminders`, `cross_asset_impacts`, `scenarios`, `sources`.

So today: **observations** and **forward_watch** are **product-keyed** (`Dict[product, List[item]]`). **Warnings** are not at the top; they follow observations/forward_watch. There is no executive snapshot, no asset-class grouping, no volatility-by-asset-class, no explicit yesterday vs forward split, and no stock-ticker suppression.

### 1.3 `rollup_aggregator.py` (out of scope)

- Used only when `generate_rollup_clean.py` is called with **`--llm`**.
- Produces a **different schema** (`twifo.rollup.v2`-oriented: `_meta`, `consensus_themes`, `divergences`, `catalysts_calendar`, `risk_framing`, `trade_ideas_synthesis`, `rollup_numeric_claims`, `tldr`). Not used for the default deterministic rollup. **No changes to rollup_aggregator.py** in this design.

### 1.4 Downstream consumption

- **PDF:** `summary_render.render_rollup_pdf()` expects `sections` with: `tldr`; `observations` (dict product→list or list); `trade_ideas` (dict with `d_1_3`/`w_1_2`/`gt_2w`/`watchlist_only` or list); `forward_watch` (dict or list); `warnings`; `tips_reminders`; `cross_asset_impacts`; `scenarios`. So we must keep these keys and either keep dict-of-lists shape (with new keys = asset classes) or add compatibility for asset-class keys.
- **TXT:** `render_rollup_txt()` in rollups.py reads the same `sections` and formats them; it will need to understand the new section order and shapes.

---

## 2. Proposed Exact Modifications

### 2.1 Replace product-keyed grouping with asset-class grouping

- **Define fixed asset classes** (deterministic, ordered):  
  e.g. `EQUITIES`, `RATES`, `COMMODITIES`, `FX`, `VOLATILITY`, `CRYPTO`, `GENERAL`.
- **Mapping:**  
  - From **product codes** (ES, NQ, GC, CL, ZN, EUR, VIX, BTC, etc.) → one asset class.  
  - From **article `meta.products`** and bullet-level `products`: map each product to an asset class; if unknown, use `GENERAL`.  
  - Bullets with `products=[]` or unmapped products → `GENERAL`.
- **New shape for grouped sections:**  
  Instead of `observations: { "ES": [...], "GC": [...], "General": [...] }`, use  
  `observations: { "EQUITIES": [...], "RATES": [...], "COMMODITIES": [...], "GENERAL": [...] }` (only keys that have at least one item). Order of keys fixed (e.g. EQUITIES, RATES, COMMODITIES, FX, VOLATILITY, CRYPTO, GENERAL).
- **Same for `forward_watch`:** asset-class-keyed dict.
- **Implementation note:** Add `_product_to_asset_class(product: str) -> str` and `_group_by_asset_class(items: List[dict]) -> Dict[str, List[dict]]` (reuse existing bullet list; when grouping, map each item’s `products` through `_product_to_asset_class`; if multiple products map to different classes, assign item to the first class or to GENERAL per deterministic rule). Dedupe unchanged (by text) before grouping.

### 2.2 Elevate warnings to top when present

- In **`sections`**, emit **`warnings` first** (before tldr / executive_snapshot / anything else) when `warnings` is non-empty. If empty, still include `warnings: []` and optionally a single sentinel bullet like `{ "text": "None.", "sources": [] }` so the UI can show “No warnings.” (Alternatively leave as `[]` and let UI say “No warnings” when empty; either is fine.)
- **Order of keys** in the rollup `sections` dict:  
  `warnings` → `executive_snapshot` → `tldr` → … (rest). Consumers that iterate dict order (e.g. Python 3.7+ insertion order) will then show warnings first. PDF/text renderer should render in this order.

### 2.3 Add `executive_snapshot` section

- **New section:** `sections.executive_snapshot`: list of 1–5 short bullets (each `{ "text": "...", "sources": [] }`), **synthesized only from existing data** (no LLM, no new APIs).
- **Content rule:**  
  - Take up to 2–3 TLDR bullets (after dedupe) that are most “headline-like” (e.g. first by order, or by length/simplicity).  
  - Add 0–1 bullet per asset class that has volatility data: from articles’ `volatility_impact` (and optionally `sentiment_indicator`) aggregate into one line per asset class, e.g. “Rates: elevated volatility, upside skew (2 sources).”  
  - No invention: only combine/shorten strings that exist in TLDR + volatility/sentiment fields. If nothing available, `executive_snapshot` can be empty list or one bullet “Summary of the day’s themes from N articles.”
- **Deterministic:** Same inputs → same snapshot (e.g. take first K tldr items in stable order, then append fixed-order asset-class volatility lines when present).

### 2.4 Suppress individual stock mentions unless top-10 market cap or large bank

- **Scope:** Any section that contains **bullet text** or **trade idea product/instrument** that is an equity ticker (e.g. AAPL, CSX, WERN). Apply only to **equity tickers**; do not suppress ES, NQ, indices, or futures symbols.
- **Allowlist (deterministic, maintained in code):**  
  - **Top 10 US market cap (example):** AAPL, MSFT, GOOGL, AMZN, NVDA, META, BRK.B, TSLA, UNH, JNJ (or a fixed list you maintain).  
  - **Large banks (example):** JPM, BAC, WFC, C, GS, MS, USB, PNC, TFC, COF (or your list).  
  - Any ticker on this allowlist → **keep** as-is.  
  - Any other ticker that looks like a stock (e.g. 2–5 uppercase letters, or known from `meta.products` as non-futures) → **suppress**: either omit the bullet, or replace the bullet text with a theme/sector summary (e.g. “Transport sector: [rest of message]”) without the ticker. Prefer **aggregate by theme/sector** when suppressing.
- **Implementation approach:**  
  - Add `_is_allowed_equity_ticker(symbol: str) -> bool` (allowlist lookup).  
  - Add `_contains_suppressed_ticker(text: str, products: List[str]) -> Tuple[bool, Optional[str]]` (detect ticker in text or products; return whether to suppress and optional theme).  
  - In `gather()` (or in a post-pass), for each bullet: if it’s equity-only and contains or is tagged with a non-allowed ticker, either drop the bullet or replace with a single aggregated line for that theme. For **trade_ideas**, if `product` is a non-allowed equity ticker, drop that idea or map product to “EQUITIES” and keep only theme-level description. Deterministic: same ticker → same allowlist result.

### 2.5 Separate “yesterday recap” from “forward-looking risk”

- **Yesterday recap:** Content that describes what already happened (e.g. “ISM came in at 52.6”, “Spot truck rates +11% YoY”). Today this is mixed in **what_occurred** / **observations** and in **tldr**.
- **Forward-looking risk:** Content about what to watch, risks, catalysts (e.g. **forward_watch**, **warnings**, parts of **what_can_move_tomorrow**).
- **Proposal:**  
  - **Keep** `observations` (asset-class-keyed) as “what occurred / yesterday recap” only. When gathering, **exclude** bullets that are clearly forward-looking (e.g. “Monitor …”, “Watch for …”). Optionally add a small heuristic: if bullet starts with “Monitor”/“Watch”/“Risk of” → put in forward bucket, not observations.  
  - **Keep** `forward_watch` (asset-class-keyed) as “forward-looking / what to watch”.  
  - **Add** optional explicit section **`forward_risks`** (list of bullets): union of **warnings** plus a subset of **forward_watch** that are risk/catalyst-oriented (e.g. filter by keywords “risk”, “catalyst”, “invalidation”). So we have:  
    - `warnings` (top of doc, unchanged content).  
    - `forward_risks` (optional): warnings + risk-oriented forward_watch bullets, deduped.  
  - **Order:** After `warnings` and `executive_snapshot` and `tldr`, show **yesterday** content (e.g. `observations`), then **forward** content (`forward_watch`, then `forward_risks` if present). So “yesterday” vs “forward” is separated by section placement and optionally by a dedicated `forward_risks` section.

### 2.6 Aggregate volatility bias by asset class

- **Input:** Each article may have top-level `volatility_impact` (e.g. `expected_volatility`, `drivers`, `directional_skew`, `confidence_0_100`) and possibly `sentiment_indicator`. Articles and trade_ideas may also mention volatility per product.
- **New section:** `sections.volatility_by_asset_class`: dict keyed by **asset class** (same set as observations), value = list of one summary object per class, e.g.  
  `{ "EQUITIES": { "expected_volatility": "Medium", "directional_skew": "Upside", "confidence_0_100": 70, "sources": ["GM", "MUFG"] }, "RATES": { ... }, ... }`  
  Only include classes that have at least one article with volatility data for that class.  
- **Aggregation rule (deterministic):** For each asset class, collect all articles that have (a) `volatility_impact` and (b) at least one product in that article mapping to that asset class. Merge: e.g. take most frequent `expected_volatility` (or max if ordering Low < Medium < High), take most frequent `directional_skew`, max confidence, union of drivers, sorted sources. No LLM.

### 2.7 Deterministic behavior

- All new logic: no randomness; no LLM in the default path. Same `article_sum_jsons` (and same order) → same `build_daily_rollup()` output. Use sorted keys and stable iteration order everywhere (e.g. asset class order, product order, bullet order after dedupe).

---

## 3. Modified Sections Structure (Output of `build_daily_rollup`)

Schema version and top-level keys unchanged: `schema_version`, `kind`, `meta`, `ui`, `inputs`, `sections`.

**`sections`** (key order and types):

| Key | Type | Description |
|-----|------|-------------|
| `warnings` | `List[dict]` | Same as today; **first** in section order. Empty list or “None.” when no warnings. |
| `executive_snapshot` | `List[dict]` | New. 1–5 bullets `{ "text", "sources" }` from TLDR + volatility summary. |
| `tldr` | `List[dict]` | Unchanged shape; same gather/dedupe as today. |
| `observations` | `Dict[str, List[dict]]` | **Asset-class-keyed** (e.g. `EQUITIES`, `RATES`, `COMMODITIES`, `FX`, `VOLATILITY`, `CRYPTO`, `GENERAL`). Each value list of `{ "text", "sources", "products" }`. Yesterday-focused only; stock tickers suppressed per allowlist. |
| `forward_watch` | `Dict[str, List[dict]]` | **Asset-class-keyed**; same keys as observations. Forward-looking only. |
| `forward_risks` | `List[dict]` | Optional. Warnings plus risk-oriented forward_watch bullets; deduped. |
| `volatility_by_asset_class` | `Dict[str, dict]` | New. Asset class → `{ expected_volatility, directional_skew, drivers?, confidence_0_100?, sources }`. |
| `trade_ideas` | `List[dict]` | Unchanged (product, bias, catalyst, setup, key_levels, risk, time_horizon, volatility_impact, sources). Equity tickers in `product` suppressed per allowlist (drop or map to EQUITIES theme). |
| `stocks` | `List[dict]` | Only bullets/allowed tickers per allowlist; otherwise aggregated by theme. |
| `other_futures` | `List[dict]` | Unchanged. |
| `forex` | `List[dict]` | Unchanged. |
| `other` | `List[dict]` | Unchanged. |
| `consensus_catalysts` | `List[dict]` | Unchanged. |
| `conflicts_uncertainties` | `List[dict]` | Unchanged. |
| `tips_reminders` | `List[dict]` | Unchanged. |
| `cross_asset_impacts` | `List[dict]` | Unchanged. |
| `scenarios` | `List[dict]` | Unchanged. |
| `sources` | `List[dict]` | Unchanged. |

Legacy keys that the PDF currently supports (`observations`, `forward_watch` as dicts) remain; only the **keys** of those dicts change from product codes to asset classes. PDF/text renderer can treat keys as labels (e.g. “EQUITIES”, “RATES”) instead of “ES”, “GC”.

---

## 4. Minimal Diff Implementation Plan

- **File: `rollups.py` only** (and optionally `summary_render.py` if we need to render `executive_snapshot` and `volatility_by_asset_class` and handle `forward_risks`; and `render_rollup_txt` in rollups.py).
- **No new files.** No changes to `generate_rollup_clean.py` beyond possibly ensuring it still passes the same args to `build_daily_rollup`. No changes to `rollup_aggregator.py`.

**Steps (minimal diff):**

1. **Constants and helpers (rollups.py)**  
   - Add `ASSET_CLASSES` ordered list and `PRODUCT_TO_ASSET_CLASS` map.  
   - Add `ALLOWED_EQUITY_TICKERS` (top 10 + large banks).  
   - Add `_product_to_asset_class(product: str) -> str`.  
   - Add `_is_allowed_equity_ticker(symbol: str) -> bool`.  
   - Add `_group_by_asset_class(items: List[dict]) -> Dict[str, List[dict]]` (reuse existing item shape; map each item’s products to one asset class; deterministic tie-break).  
   - Add optional `_should_suppress_equity_bullet(text, products) -> bool` and `_aggregate_theme_for_suppressed_ticker(...)` (or in-place text replacement) for bullets and trade_ideas.

2. **Gather pipeline (rollups.py)**  
   - Keep `gather(section, limit, filter_trade_ideas)` but add an optional **post-filter**: after dedupe, drop or replace bullets that are equity-only and contain non-allowed tickers.  
   - Replace `gather_grouped` usage for **observations** and **forward_watch** with: gather → (optional equity suppression) → **`_group_by_asset_class`** instead of `_group_by_product`.  
   - When building **observations**, exclude bullets that are clearly forward-looking (simple keyword check). When building **forward_watch**, keep only forward-looking (or leave as-is and rely on section names).

3. **Warnings first**  
   - Build `warnings` list as today (gather("warnings", limit=15)).  
   - When assembling `sections`, **assign `warnings` first** (first key inserted), then `executive_snapshot`, then `tldr`, then observations, forward_watch, forward_risks, volatility_by_asset_class, trade_ideas, stocks, … rest. Python 3.7+ dict order preserves this.

4. **Executive snapshot**  
   - New helper `_build_executive_snapshot(article_sum_jsons, tldr_items, volatility_by_asset_class)` that returns list of 1–5 bullets from tldr + volatility lines. Call it after tldr and volatility_by_asset_class are available; insert result into `sections["executive_snapshot"]`.

5. **Volatility by asset class**  
   - New helper `_aggregate_volatility_by_asset_class(article_sum_jsons)` that returns `Dict[asset_class, {...}]`. Use product→asset_class mapping per article; merge volatility_impact and sentiment_indicator per class (deterministic merge rules). Insert into `sections["volatility_by_asset_class"]`.

6. **Forward risks**  
   - Optional: `forward_risks = warnings + [bullets from forward_watch that match risk keywords]`, dedupe by text. Insert `sections["forward_risks"]`.

7. **Trade ideas and stocks**  
   - When building `trade_ideas_list`, if `product` is an equity ticker and not in allowlist: skip that idea or set product to "EQUITIES" and use a theme-only description.  
   - For `stocks` section, apply same allowlist: keep only allowed tickers; aggregate or drop others.

8. **Renderers**  
   - **rollups.py** `render_rollup_txt()`: output sections in new order; for observations/forward_watch, iterate asset-class keys in fixed order; add executive_snapshot and volatility_by_asset_class and forward_risks to the text template.  
   - **summary_render.py** `render_rollup_pdf()`: ensure it renders `warnings` first if present; add blocks for `executive_snapshot`, `volatility_by_asset_class`, `forward_risks`; when iterating observations/forward_watch, treat keys as asset-class labels (no code change if it just iterates keys and prints them).

9. **Tests**  
   - Extend or add tests in `test_rollup_*.py`: same inputs → same output (determinism); warnings first when non-empty; observations/forward_watch keys are asset classes; executive_snapshot present and ≤5 bullets; no non-allowed equity tickers in stocks/trade_ideas; volatility_by_asset_class structure.

---

## 5. Summary

- **Current flow:** `generate_rollup_clean` collects article JSONs → `rollups.build_daily_rollup()` builds one dict with product-keyed `observations` and `forward_watch`, warnings not first, no executive snapshot, no volatility-by-asset-class, no stock suppression.  
- **Change:** Same entry point and file naming; only `rollups.py` (and renderers) are modified. Sections get **asset-class grouping**, **warnings first**, **executive_snapshot**, **equity ticker suppression** (allowlist), **yesterday vs forward** separation (and optional `forward_risks`), **volatility_by_asset_class**, and **deterministic** behavior throughout.

No v2 schema, no parallel architecture, no file naming changes.
