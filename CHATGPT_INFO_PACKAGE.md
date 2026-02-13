# Information Package for ChatGPT

## 1. Article Prompt Template (Exact String)

### Location
`c:\Coding Projects\TWIFO_Sharing\twifo_prompts\prompts\article_prompts.py`

### Version
**PROMPT_VERSION = "1.2"**

### System Prompt
```python
SYSTEM_PROMPT = (
    "You are a professional institutional-market research analyst writing "
    "structured JSON summaries for active futures/macro traders.\n\n"

    # ── STRICT GROUNDING ──
    "STRICT GROUNDING (MANDATORY):\n"
    "1. Output MUST be strictly grounded in the provided article text only.\n"
    "2. If a detail is not explicitly in the article, OMIT it. "
    "Do not guess, infer, or use external knowledge.\n"
    "3. Every bullet, level, entity, and product MUST be traceable to a "
    "specific phrase or sentence in the document.\n"
    "4. Different articles MUST produce materially different summaries. "
    "No generic template reuse.\n\n"

    # ── ABSOLUTE NUMERIC RULE ──
    "ABSOLUTE NUMERIC RULE:\n"
    "- You may ONLY include a numeric price, level, target, or threshold "
    "if it appears VERBATIM in the source text.\n"
    "- For EVERY such number you output anywhere in the JSON, you MUST "
    "also add an entry to numeric_claims[] with the exact source_quote.\n"
    "- If you cannot quote the snippet, DROP the number entirely.\n"
    "- Do NOT use current market prices, estimates, or general knowledge.\n\n"

    # ── FINGERPRINT ANCHORING ──
    "FINGERPRINT ANCHORING:\n"
    "- You MUST extract 3-6 short verbatim quotes (10-30 words each) from "
    "the article that are unique to THIS document.\n"
    "- These go in fingerprint_quotes[]. They serve as provenance anchors "
    "and must NOT be paraphrased.\n"
    "- Choose quotes that capture the article's distinctive voice, key "
    "claims, or unique data points.\n\n"

    # ── DYNAMIC ENTITIES ──
    "DYNAMIC ENTITIES (NO FORCED GRIDS):\n"
    "- Do NOT output a fixed product grid (ES, NQ, ZN, ZB, GC, SI, BTC, VIX, CL).\n"
    "- Only list entities (tickers, asset names, economic indicators) that the "
    "article explicitly discusses.\n"
    "- primary_entities[] must contain ONLY entities that are central to the "
    "article's thesis. Peripheral mentions go in trade_ideas[] if actionable, "
    "or are omitted.\n"
    "- Map common names to standard tickers where obvious "
    "(e.g. 'gold' -> 'GC', 'S&P 500' -> 'ES', '10-year' -> 'ZN').\n\n"

    # ── CHART-ONLY LOGIC ──
    "CHART-ONLY LOGIC:\n"
    "- chart_score_0_3: 0 = no charts/tables, 1 = minor supporting charts, "
    "2 = charts with meaningful data, 3 = chart-heavy / data-table-driven.\n"
    "- chart_text_sources_used[]: list which text-extraction methods produced "
    "readable chart data (e.g. 'table_headers', 'axis_labels', 'caption_text'). "
    "Use [] if no chart text was extractable.\n"
    "- chart_observations[]: 1-3 factual observations drawn from chart/table "
    "data in the document. Use [] if no charts.\n\n"

    # ── LEAN PLACEHOLDERS ──
    "LEAN PLACEHOLDERS:\n"
    "- For array fields with no content, use [] (empty array). "
    "NEVER use [\"(none)\"] or [\"(not provided in inputs)\"].\n"
    "- For scalar string fields with no content, use \"(none)\".\n"
    "- For numeric fields with no content, use 0 or null as appropriate.\n"
    "- Omit entire product categories if the article does not discuss them.\n\n"

    # ── OUTPUT FORMAT ──
    "OUTPUT: Valid JSON only. No markdown fences, no explanations, just the JSON object."
)
```

### User Prompt
```python
USER_PROMPT = (
    "Create a trader-focused summary from the document below. "
    "Return ONLY valid JSON matching this schema.\n\n"

    # ── SCHEMA ──
    "{\n"

    # -- _meta --
    '  "_meta": {\n'
    '    "primary_entities": ["TICKER1", "TICKER2"],\n'
    '    "primary_entities_rule": "ONLY entities central to the article thesis. '
    'Map common names to tickers (gold->GC, S&P->ES). Max 6."\n'
    "  },\n\n"

    # -- fingerprint_quotes --
    '  "fingerprint_quotes": [\n'
    '    "exact verbatim quote from article (10-30 words)",\n'
    '    "another unique quote that anchors this specific document",\n'
    '    "3-6 total quotes that make this summary unmistakably tied to this article"\n'
    "  ],\n\n"

    # -- numeric_claims --
    '  "numeric_claims": [\n'
    '    {"value": "5,450", "context": "ES support level", '
    '"source_quote": "exact sentence from article containing 5,450"},\n'
    '    "RULE: EVERY number used anywhere in this JSON must have an entry here. '
    'If you cannot provide source_quote, drop the number from the entire output."\n'
    "  ],\n\n"

    # -- what_moved_today --
    '  "what_moved_today": [\n'
    '    "Past tense, only what the document states; include numbers only if verbatim in text",\n'
    '    "3-5 bullets minimum. Use [] if the article is purely forward-looking."\n'
    "  ],\n\n"

    # -- what_can_move_tomorrow --
    '  "what_can_move_tomorrow": [\n'
    '    "Forward-looking catalysts stated in the document only",\n'
    '    "3-5 bullets minimum. Use [] if the article is purely backward-looking."\n'
    "  ],\n\n"

    # -- trade_ideas --
    '  "trade_ideas": [\n'
    "    {\n"
    '      "product": "TICKER",\n'
    '      "bias": "Bullish|Bearish|Neutral",\n'
    '      "catalyst": "Why this trade, from article only",\n'
    '      "setup": "Entry/exit logic if stated",\n'
    '      "key_levels": ["level1", "level2"],\n'
    '      "source_quote": "exact sentence containing the levels",\n'
    '      "risk": "Risk factor if stated",\n'
    '      "time_horizon": "1-3d|1-2w|>2w if stated"\n'
    "    }\n"
    "  ],\n"
    '  "trade_ideas_rule": "Only products with EXPLICIT levels or directional bias '
    "in the article. No forced grid. key_levels must be verbatim numbers with "
    'source_quote. Use [] if no actionable ideas.",\n\n'

    # -- volatility_impact --
    '  "volatility_impact": {\n'
    '    "expected_volatility": "Low|Medium|High",\n'
    '    "drivers": ["specific driver from article", "..."],\n'
    '    "directional_skew": "Upside|Downside|Two-sided",\n'
    '    "confidence_0_100": 70\n'
    "  },\n\n"

    # -- tldr --
    '  "tldr": [\n'
    '    "EXACTLY 3 bullets. Each grounded in document. Different articles must yield different bullets.",\n'
    '    "Second bullet",\n'
    '    "Third bullet"\n'
    "  ],\n\n"

    # -- what_occurred --
    '  "what_occurred": ["Factual events from document; numbers only if verbatim. Use [] if none."],\n'
    '  "forward_watch": ["Upcoming catalysts stated in document. Use [] if none."],\n'
    '  "warnings": ["Risk factors stated in document. Use [] if none."],\n'
    '  "tips_reminders": ["Educational context from document. Use [] if none."],\n'
    '  "cross_asset_impacts": ["How X affects Y, only if stated in document. Use [] if none."],\n'
    '  "scenarios": ["If/Then only if stated in document. Use [] if none."],\n\n'

    # -- sentiment_indicator --
    '  "sentiment_indicator": {\n'
    '    "risk_on_off": "Risk-On|Risk-Off|Neutral",\n'
    '    "confidence_0_100": 70,\n'
    '    "rationale": "From article only. Use (none) if unclear."\n'
    "  },\n\n"

    # -- chart fields --
    '  "chart_score_0_3": 0,\n'
    '  "chart_text_sources_used": ["table_headers", "axis_labels", "caption_text"],\n'
    '  "chart_observations": ["Factual observation from chart/table data. Use [] if no charts."],\n\n'

    # -- explain + score --
    '  "explain_like_refresher": "One concept from article, or (none)",\n'
    '  "score_0_10": 7\n'
    "}\n\n"

    # ── HARD RULES ──
    "HARD RULES:\n"
    "1. numeric_claims[] is the SINGLE REGISTRY of every number in this JSON. "
    "Any number in trade_ideas, what_moved_today, etc. MUST have a matching "
    "numeric_claims entry with source_quote. No quote -> drop the number.\n"
    "2. primary_entities[] = ONLY tickers/assets central to the article. "
    "Max 6. No default lists.\n"
    "3. fingerprint_quotes[] = 3-6 verbatim quotes (10-30 words). "
    "Not paraphrased. Unique to this article.\n"
    "4. trade_ideas[]: Only products with explicit bias or levels in the article. "
    "No forced product grid. Use [] if no actionable ideas.\n"
    "5. chart_score_0_3: Score the document's chart/table content. "
    "chart_observations[] only if charts exist.\n"
    "6. tldr: EXACTLY 3 bullets. what_moved_today: 3-5. what_can_move_tomorrow: 3-5.\n"
    "7. Empty arrays = []. Empty scalars = \"(none)\". "
    "NEVER use [\"(none)\"] or [\"(not provided in inputs)\"].\n"
    "8. Two different articles MUST produce different tldr, different "
    "fingerprint_quotes, different numeric_claims. No template reuse.\n"
    "9. Do not remove the _meta, fingerprint_quotes, or numeric_claims keys. "
    "They are required even if the article has no numbers (numeric_claims: []).\n\n"

    "DOCUMENT TEXT:\n<<<\n<<<PLACEHOLDER>>>\n>>>"
)
```

---

## 2. is_low_quality_summary + _summarize_with_quality_retry

### Location
`c:\Coding Projects\TWIFO_Sharing\summarize_pdf.py`

### is_low_quality_summary (Lines 537-656)
```python
def is_low_quality_summary(sum_json: dict) -> tuple[bool, str]:
    """
    Detect low-quality/templated LLM output that should fail.
    
    Returns:
        (is_low_quality: bool, reason: str)
    
    Detects:
    - Repeated bullets (copy-paste behavior)
    - Generic placeholder phrases
    - Too few unique informative bullets
    - Banned filler phrases
    - Section-level repetition (2+ identical bullets in same section)
    """
    sections = sum_json.get("sections", {})
    
    # Collect all text bullets from sections (including new fields)
    all_bullets = []
    section_bullets = {}  # Track bullets per section for repetition check
    
    for key in ["what_moved_today", "what_can_move_tomorrow", "tldr", "what_occurred", "forward_watch", 
                "warnings", "tips_reminders", "cross_asset_impacts", "scenarios"]:
        items = sections.get(key, [])
        section_bullets[key] = []
        if isinstance(items, list):
            for item in items:
                text = _extract_bullet_text(item).lower()
                if text:
                    all_bullets.append(text)
                    section_bullets[key].append(text)
    
    # Also check trade_ideas if they exist
    trade_ideas = sections.get("trade_ideas", [])
    for item in trade_ideas:
        if isinstance(item, dict):
            for field in ["catalyst", "setup", "risk"]:
                text = item.get(field, "").strip().lower()
                if text and text != "(not provided in inputs)":
                    all_bullets.append(text)
            # Check key_levels separately (it's a list)
            key_levels = item.get("key_levels", [])
            if isinstance(key_levels, list):
                for level in key_levels:
                    if isinstance(level, str) and level.strip().lower() != "(not provided in inputs)":
                        all_bullets.append(level.strip().lower())
    
    # Check 1: Too few unique bullets (excluding empty/placeholder content)
    unique_bullets = set(all_bullets)
    if len(unique_bullets) < 3:
        return True, f"too_few_unique_bullets: only {len(unique_bullets)} unique bullets found"
    
    # Check 2: Detect repeated bullets (exact duplicates)
    if len(all_bullets) > len(unique_bullets) * 1.5:  # More than 50% duplication
        duplication_rate = (len(all_bullets) - len(unique_bullets)) / len(all_bullets) * 100
        return True, f"excessive_duplication: {duplication_rate:.0f}% of bullets are duplicates"
    
    # Check 2b: Section-level repetition (2+ identical bullets within same section)
    for section_name, bullets in section_bullets.items():
        if len(bullets) >= 2:
            bullet_counts = {}
            for bullet in bullets:
                bullet_counts[bullet] = bullet_counts.get(bullet, 0) + 1
            for bullet, count in bullet_counts.items():
                if count >= 2:
                    return True, f"filler:repeated_bullets_in_{section_name}: '{bullet[:50]}...' appears {count} times"
    
    # Check 3: Banned filler phrases (case-insensitive)
    banned_phrases = [
        "market data pending analysis",
        "monitor key levels and data releases",
    ]
    
    for bullet in all_bullets:
        for phrase in banned_phrases:
            if phrase in bullet:
                return True, f"filler:banned_phrase: '{phrase}' found in bullet"
    
    # Check 4: Generic placeholder phrases
    placeholder_phrases = [
        "pending analysis",
        "monitor key levels",
        "data releases",
        "await further information",
        "to be determined",
        "no specific",
        "not specified",
        "monitor developments",
        "watch for updates",
        "pending clarification",
        "subject to change",
        "more details needed",
        "insufficient information",
        "data not available",
        "no direct trade idea from this article",  # OK for neutral products
    ]
    
    # Count how many bullets are just placeholders
    placeholder_count = 0
    for bullet in all_bullets:
        # Skip the "no direct trade idea" phrase - that's valid for neutral products
        if "no direct trade idea from this article" in bullet:
            continue
        for phrase in placeholder_phrases:
            if phrase in bullet:
                placeholder_count += 1
                break
    
    # If more than 40% of bullets are placeholders, fail
    if len(all_bullets) > 0 and placeholder_count / len(all_bullets) > 0.4:
        placeholder_rate = placeholder_count / len(all_bullets) * 100
        return True, f"excessive_placeholders: {placeholder_rate:.0f}% of bullets are generic placeholders"
    
    # Check 5: Detect suspiciously short bullets (likely low-effort)
    short_bullet_count = sum(1 for b in all_bullets if len(b) < 20)
    if len(all_bullets) > 0 and short_bullet_count / len(all_bullets) > 0.6:
        short_rate = short_bullet_count / len(all_bullets) * 100
        return True, f"excessive_short_bullets: {short_rate:.0f}% of bullets are < 20 chars"
    
    # Passed all checks
    return False, ""
```

### _summarize_with_quality_retry (Lines 658-800)
```python
def _summarize_with_quality_retry(
    text: str,
    *,
    meta: dict,
    model: str,
    pdf_path: Path,
    out_dir: Optional[Path],
    apply_format_fix: bool,
    path_manager: Optional[TWIFOPathManager] = None,
) -> dict:
    """
    Run a two-stage quality retry with model escalation.
    """
    debug_path = _sum_debug_path(pdf_path, out_dir=out_dir, path_manager=path_manager)
    if debug_path.exists():
        debug_path.unlink()

    last_quality_reason = ""
    attempt_count = 0
    attempt_models = [model, RETRY_MODEL]

    for attempt_model in attempt_models:
        attempt_count += 1
        print(f"[ATTEMPT {attempt_count}/2] Using model: {attempt_model}")
        
        raw_output_holder: list[str] = []
        meta["model"] = attempt_model

        extra_instructions = None
        max_tokens = BASE_MAX_OUTPUT_TOKENS
        if attempt_count == 2:
            max_tokens = RETRY_MAX_OUTPUT_TOKENS
            extra_instructions = (
                "Provide fuller, non-terse bullets that meet the minimum counts. "
                "Use distinct wording across sections, grounded in the document."
            )
            print(f"[RETRY] Escalating with stronger prompt and {max_tokens} tokens")

        try:
            sum_json = llm_summarize_to_json(
                text,
                meta=meta,
                model=attempt_model,
                temperature=0.1,
                max_output_tokens=max_tokens,
                extra_instructions=extra_instructions,
                raw_output=raw_output_holder,
            )
        except Exception as e:
            print(f"[ERROR] LLM call failed on attempt {attempt_count}: {e}")
            if attempt_count < len(attempt_models):
                print(f"[RETRY] Will try next model...")
                continue
            raise

        if apply_format_fix:
            try:
                from format_validator import validate_article_summary, fix_summary_format
                is_valid, violations = validate_article_summary(sum_json)
                if violations:
                    print(f"[FORMAT] Fixing {len(violations)} format issues...")
                    sum_json = fix_summary_format(sum_json)
            except ImportError:
                pass  # Validator not available, skip

        _normalize_sections_in_place(sum_json)

        # Layer 2: Sanitize price levels (drop inferred, keep only explicit in source)
        dropped_levels = sanitize_key_levels(sum_json, text)
        extraction = sum_json.get("extraction", {})
        if dropped_levels:
            extraction["dropped_inferred_level_count"] = len(dropped_levels)
            extraction["dropped_inferred_level_details"] = [
                {"field": d["field"], "product": d["product"], "reason": d["reason"]}
                for d in dropped_levels[:20]
            ]

        # Layer 3: ACTIONABLE = only trade ideas with explicit levels (no generic template)
        actionable_list, actionable_reason = _filter_actionable_trade_ideas(sum_json)
        sum_json.setdefault("sections", {})["trade_ideas"] = actionable_list
        extraction["actionable_included_reason"] = actionable_reason
        extraction["content_hash"] = _content_hash(text)
        sum_json["extraction"] = extraction

        if os.getenv("DEV_LOGGING") == "1":
            print(
                f"[DEV_LOGGING] products_inferred_reason={extraction.get('products_inferred_reason', '')!r} "
                f"actionable_included_reason={actionable_reason!r}"
            )

        # Layer 1: Generic quality checks
        is_low_quality, quality_reason = is_low_quality_summary(sum_json)

        if not is_low_quality:
            print(f"[QUALITY GATE] Passed on attempt {attempt_count}")
            extraction = sum_json.get("extraction", {})
            extraction["attempt_count"] = attempt_count
            extraction["quality_reason"] = ""
            sum_json["extraction"] = extraction

            # Step D.5: Post-LLM deterministic numeric verifier
            sum_json = verify_and_scrub_numerics(sum_json, text)

            # Step D.6: Similarity guard (at most one retry, deterministic)
            sum_json = similarity_guard(
                sum_json,
                source_text=text,
                meta=meta,
                model=attempt_model,
                path_manager=path_manager,
                pdf_path=pdf_path,
            )

            # Step D.7: Critic pass (structural cleanup — dedup, quotes, numerics)
            sum_json = critic_pass(sum_json, text)

            return sum_json

        print(f"[QUALITY GATE] Failed on attempt {attempt_count}: {quality_reason}")
        last_quality_reason = quality_reason
        bullet_counts = _count_section_bullets(sum_json.get("sections", {}))
        raw_text = raw_output_holder[0] if raw_output_holder else ""
        _write_debug_artifact(
            debug_path,
            model=attempt_model,
            raw_output=raw_text,
            bullet_counts=bullet_counts,
            quality_reason=quality_reason,
            attempt=attempt_count,
        )
        print(f"[DEBUG] Debug artifact written to: {debug_path}")

    print(f"[FAIL] All attempts exhausted. Returning failure stub.")
    extraction = meta.get("extraction", {})
    extraction["attempt_count"] = attempt_count
    extraction["quality_reason"] = last_quality_reason
    meta["model"] = RETRY_MODEL
    return _failed_stub(
        pdf_path,
        reason=f"low_quality_output: {last_quality_reason}",
        extraction=extraction,
        meta=meta,
    )
```

---

## 3. db_filter_autorun.py Output Path Determination

### Location
`c:\Coding Projects\TWIFO_Sharing\db_filter_autorun.py`

### Path Construction Logic (Lines 514-536)
```python
for src in iter_pdf_files(provider_dir, is_gm=is_gm):
    raw_name = src.name

    if is_gm and re.search(r"(?i)monthly[\s_]+stats", raw_name):
        continue

    if SKIP_PAT.search(raw_name):
        continue
    if not KEEP_PAT.search(raw_name):
        continue

    orig, file_base = normalize_base_name(prefix, raw_name, year=d.year)
    freq = frequency_code(orig)

    # Construct suggested filename: PREFIX_base_YYYYMMDD_freq.pdf
    suggested = f"{prefix}_{file_base}_{date_str}_{freq}.pdf"
    
    # Use path manager for new layout if available
    if PATH_MANAGER_AVAILABLE and PATH_MANAGER:
        dst = PATH_MANAGER.original_pdf_path(suggested)
    else:
        dst = EXPORT_DIR / suggested
        
    pairs.append((src, dst))
```

### Example Filename Pattern
- **Input**: `BofA_Commodities_Weekly.pdf` from `2026-02-10`
- **Output**: `BOA_Commodities_Weekly_20260210_w.pdf`
- **Components**:
  - `BOA` = provider prefix
  - `Commodities_Weekly` = normalized base name
  - `20260210` = date in YYYYMMDD format
  - `w` = frequency code (w=weekly, m=monthly, q=quarterly, y=yearly, u=unknown)

### With Dedupe Module (Lines 580-586)
```python
if DEDUPE_AVAILABLE and not no_dedupe:
    canonical_url = canonicalize_url(str(src))
    doc_id = doc_id_from_canonical_url(canonical_url)
    dedup_doc_id = doc_id
    title_slug = slugify_title(suggested_name)
    base = deterministic_base_filename(published_date, provider_code, title_slug, doc_id)
    # ... preflight, claim, etc.
    final_path, _ = ensure_original_pdf_in_export(export_dir, base, src)
```

**Deterministic base format**: `YYYYMMDD__PROVIDER__slug__doc_id_hash.pdf`

Example: `20260210__BOA__boa_commodities_weekly__a1b2c3d4ef.pdf`

---

## 4. Example Stub sum.json + extracted.txt

### Stub sum.json
**File**: `20260206__SG__sg_fixed_income_weekly_overshoot__20260206_w__a03d7c4d93__sum.json`

```json
{
  "schema_version": "twifo.sum.v1",
  "kind": "article",
  "meta": {
    "source_pdf": "20260206__SG__sg_fixed_income_weekly_overshoot__20260206_w__a03d7c4d93.pdf",
    "generated_at_iso": "2026-02-11T22:56:14",
    "model": null,
    "provider": "O",
    "title": "20260206__SG__sg_fixed_income_weekly_overshoot__20260206_w__a03d7c4d93",
    "published_date": "",
    "horizon": "u"
  },
  "ui": {
    "header_pills": []
  },
  "extraction": {
    "status": "failed",
    "reason": "OCR failed (ocrmypdf + fallback). ocrmypdf: ocrmypdf failed rc=1 stderr=Choose only one of --force-ocr, --skip-text, --redo-ocr.\n | fallback: OCR fallback exception: (1, 'Image too large: (1906, 59908) Error during processing.')"
  },
  "sections": {
    "what_moved_today": [],
    "what_can_move_tomorrow": [],
    "trade_ideas": [],
    "tldr": [],
    "what_occurred": [],
    "forward_watch": [],
    "warnings": [],
    "tips_reminders": [],
    "cross_asset_impacts": [],
    "scenarios": []
  }
}
```

### Example extracted.txt (Quality Gate Failure)
**File**: `20260211__GM__gm_commodity_analyst_what_the_great_gold_rally_could_signal_for_the_broader_commodity_outlook_1_20260211_u__677f0794fa\extracted.txt`

```
===== QUALITY GATE FAILURE (ATTEMPT 1) =====
model: gpt-4o-mini
quality_reason: filler:repeated_bullets_in_what_occurred: 'market data pending analysis...' appears 3 times
bullet_counts: {"what_moved_today": 3, "what_can_move_tomorrow": 3, "trade_ideas": 0, "tldr": 3, "what_occurred": 3, "forward_watch": 3, "warnings": 0, "tips_reminders": 0, "cross_asset_impacts": 0, "scenarios": 0}
raw_output:
{
  "_meta": {
    "primary_entities": ["GC", "CU"],
    "primary_entities_rule": "ONLY entities central to the article thesis. Map common names to tickers (gold->GC, S&P->ES). Max 6."
  },
  "fingerprint_quotes": [
    "The key similarity between gold and several other commodities lies in the rise of 'insurance'-type demand.",
    "Insurance-driven demand for gold therefore operates in a market where supply cannot adjust meaningfully.",
    "Recent client feedback suggests that insurance-type demand for several commodities has broadened beyond the public sector."
  ],
  "numeric_claims": [
    {
      "value": "300bn",
      "context": "Russia's reserves",
      "source_quote": "the freezing of roughly $300bn of Russia's reserves—largely US and European sovereign bonds—in 2022"
    },
    {
      "value": "12bn",
      "context": "US strategic mineral stockpile",
      "source_quote": "the US announced 'Project Vault'—a $12bn strategic mineral stockpile including copper, rare earths and lithium"
    }
  ],
  "what_moved_today": [
    "Gold prices have been supported by sustained central bank buying amid geopolitical tensions.",
    "Copper prices have firmed despite an estimated global oversupply due to US stockpiling.",
    "Investor-driven 'insurance' flows have amplified price volatility across several commodities."
  ],
  "what_can_move_tomorrow": [
    "Continued geopolitical tensions may further drive demand for gold as a safe haven.",
    "Changes in US trade policy could impact silver prices significantly.",
    "Regional supply disruptions could lead to increased volatility in commodity markets."
  ],
  "trade_ideas": [],
  "tldr": [
    "Gold's rally is driven by central bank buying amid geopolitical risks.",
    "Copper prices are firming due to US stockpiling despite global oversupply.",
    "Investor demand for commodities is increasing as a hedge against uncertainty."
  ],
  "what_occurred": [
    "Market data pending analysis",
    "Market data pending analysis",
    "Market data pending analysis"
  ],
  "forward_watch": [
    "Monitor key levels and data releases",
    "Monitor key levels and data releases",
    "Monitor key levels and data releases"
  ],
  "volatility_impact": {
    "expected_volatility": "High",
    "drivers": ["Geopolitical tensions", "US trade policy changes"],
    "directional_skew": "Upside",
    "confidence_0_100": 70
  },
  "sentiment_indicator": {
    "risk_on_off": "Risk-On",
    "confidence_0_100": 70,
    "rationale": "Investor-driven demand for hard assets amid uncertainty."
  },
  "chart_score_0_3": 0,
  "chart_text_sources_used": [],
  "chart_observations": [],
  "explain_like_refresher": "(none)",
  "score_0_10": 7
}

===== QUALITY GATE FAILURE (ATTEMPT 2) =====
[Would show attempt 2 with gpt-4o model and similar structure]
```

---

## Summary

This package contains:
1. ✅ Complete prompt template (system + user + schema)
2. ✅ Quality gate function (`is_low_quality_summary`) with all detection rules
3. ✅ Retry mechanism (`_summarize_with_quality_retry`) with 2-stage escalation
4. ✅ Output path construction from `db_filter_autorun.py`
5. ✅ Example stub JSON (OCR failure)
6. ✅ Example quality gate failure (extracted.txt with repeated bullets)

**Models Used**:
- Attempt 1: `gpt-4o-mini`
- Attempt 2: `gpt-4o` (RETRY_MODEL)

**Key Features**:
- Strict grounding (no hallucinations)
- Numeric verification with source quotes
- Fingerprint anchoring (3-6 verbatim quotes)
- Quality gate catches filler/template responses
- Two-stage retry with model escalation
- Deterministic filename structure
