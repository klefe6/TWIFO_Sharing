# Safe Cleanup Patch Set — TWIFO_Sharing

**Purpose:** Prevent prompt confusion and reduce repo clutter while preserving behavior  
**Date:** 2026-02-04

---

## Section A: Proposed Final Folder Structure Tree

```
TWIFO_Sharing/
├── summary/
│   ├── __init__.py
│   └── prompts/
│       ├── __init__.py
│       ├── article_prompts.py          # SINGLE SOURCE OF TRUTH for prompts
│       └── README.md
├── docs/
│   ├── README.md                       # Points to CURRENT_PROMPT as authoritative
│   ├── CURRENT_PROMPT.md               # ONLY authoritative prompt doc
│   └── archive/
│       ├── ANTI_HALLUCINATION_IMPLEMENTATION.md
│       ├── ARTICLE_FINAL_IMPLEMENTATION.md
│       ├── ARTICLE_PROMPT_UPGRADE.md
│       ├── BALANCED_PROMPT_UPDATE.md
│       ├── EXTRACTION_ONLY_PROMPT.md
│       └── FINAL_PROMPT_CONFIGURATION.md
├── archive/                            # Root archive (unused/historical files)
│   ├── testing.py
│   ├── summarize_pdf_new.py
│   └── [27 implementation .md files]
├── auth_env.py
├── backfill_rollups.py
├── build_summaries.py
├── db_filter_autorun.py
├── format_validator.py
├── generate_rollup_clean.py
├── import_dropbox.py
├── openai_client.py
├── rollups.py
├── rollup_schema.py
├── rollup_validate.py
├── run_db_filter.bat
├── run_weekly_rollup.py
├── reboot_import_dropbox.bat
├── reboot_twifo.bat
├── summarize_pdf.py
├── summary_render.py
├── smoke_test_pdf.py
├── twifo.py
├── verify_summary.py
├── test_*.py
├── PROJECT_MAP.md
├── SMOKE_TEST.md
├── SMOKE_RUN_CHECKLIST.md
├── CLEANUP_GIT_STEPS.md
├── DEPENDENCY_MAP.md
├── SAFE_CLEANUP_BASELINE.md
├── MOVE_PLAN.md
├── README.md
├── requirements.txt
├── .gitignore
└── QUICK_START_API_KEY.txt
```

---

## Section B: Code Diffs (File-by-File)

### B1. New: `summary/__init__.py`

```
# summary package
```

### B2. New: `summary/prompts/__init__.py`

```
# summary.prompts package
```

### B3. New: `twifo_prompts/prompts/article_prompts.py`

Exports: `PROMPT_VERSION`, `SYSTEM_PROMPT`, `USER_PROMPT`, `DOCUMENT_PLACEHOLDER`, `prompt_sha256()`, `prompt_source_file()`.

- `PROMPT_VERSION = "1.0"`
- Full system and user prompt strings (moved from summarize_pdf)
- `prompt_sha256()` — SHA256 hex of canonical prompt
- `prompt_source_file()` — resolved path to this module

### B4. Modified: `summarize_pdf.py`

**Imports added:** `subprocess` (already present)

**Removed:** `PROMPT_VERSION`, `_get_base_prompts_for_provenance()`, inline `system_prompt` and `user_prompt` strings, `hashlib` import (moved to article_prompts).

**Added:** `_get_prompt_provenance()` — builds `{prompt_version, prompt_source_file, prompt_sha256, code_git_commit}` from `summary.prompts.article_prompts`.

**llm_summarize_to_json:** Imports `article_prompts`, uses `SYSTEM_PROMPT`, builds `user_prompt` from `USER_PROMPT.replace(DOCUMENT_PLACEHOLDER, text)` and optional `extra_guidance`. Calls `_get_prompt_provenance()` and merges into `meta_out`.

**_failed_stub:** Adds `_get_prompt_provenance()` to `meta_out`.

### B5. New: `docs/CURRENT_PROMPT.md`

States it is the **only** authoritative prompt doc. Contains:
- What the prompt is for
- PROMPT_VERSION and live code path
- Critical rules (anti-hallucination, product ordering, volatility, machine-friendly bullets)
- Schema fields downstream depends on
- Provenance fields

### B6. New: `docs/README.md`

States CURRENT_PROMPT.md is the only authoritative prompt doc. Lists archive and live code path.

### B7. New: `PROJECT_MAP.md`

- What runs what (entrypoints + ports)
- Where summaries/rollups/prompts/docs live
- Deprecated (docs/archive)
- Archived items (root archive/)

### B8. New: `SMOKE_TEST.md`

Exact commands for article summarization, rollup pipeline, web apps. Path reference.

### B9. New: `SMOKE_RUN_CHECKLIST.md`

Validation for: provenance (meta.prompt_version, meta.prompt_sha256), summary rendering, rollup generation, UI score display (load_summary_score). Exact commands and artifacts to check.

### B10. Move: Old prompt docs → `docs/archive/`

- ANTI_HALLUCINATION_IMPLEMENTATION.md
- ARTICLE_FINAL_IMPLEMENTATION.md
- ARTICLE_PROMPT_UPGRADE.md
- BALANCED_PROMPT_UPDATE.md
- EXTRACTION_ONLY_PROMPT.md
- FINAL_PROMPT_CONFIGURATION.md

### B11. Move: Unused root files → `archive/`

**Python:** testing.py, summarize_pdf_new.py

**Implementation docs:** AUTH_CONSISTENCY_FIX, AUTH_PREFLIGHT_IMPLEMENTATION, AUTH_SINGLE_SOURCE_IMPLEMENTATION, EGYPT_FORMAT_COMPLETE, EGYPT_FORMAT_IMPLEMENTATION, EXACT_CODE_CHANGES, FIX_APPLIED, FIX_SUMMARY_20260110, IMPLEMENTATION_SUMMARY, INSPECTION_REPORT, OCR_FLOW_DIAGRAM, OCR_GUARDRAIL_README, OCR_INSTALL_GUIDE, OPTION_B_COMPLETE, OPTION_B_IMPLEMENTATION_PLAN, OPTION_B_QUICK_REF, PDF_RENDERER_README, PREFLIGHT_IMPLEMENTATION_SUMMARY, PREFLIGHT_QUICK_REF, PREFLIGHT_README, QUALITY_GATE_IMPLEMENTATION, QUALITY_RETRY_FIX, ROLLUP_UPDATE_SUMMARY, STYLE_B_IMPLEMENTATION, SUMMARY_STATUS

**Needs confirmation (not moved):** _tmp_json_list.txt, CLEANUP_GIT_STEPS.md, DEPENDENCY_MAP.md, SAFE_CLEANUP_BASELINE.md, QUICK_START_API_KEY.txt

---

## Section C: Git Command Sequence to Apply Safely

```bash
cd "c:\Coding Projects\TWIFO_Sharing"

# 1. Ensure known-good state
python -c "from twifo_prompts.prompts.article_prompts import PROMPT_VERSION, prompt_sha256; assert PROMPT_VERSION == '1.0'; print('OK')"
python -c "from summarize_pdf import _get_prompt_provenance; p = _get_prompt_provenance(); assert 'prompt_version' in p; print('OK')"

# 2. Commit, tag, branch (if not already done)
git add -A
git status
git commit -m "feat: prompt single source-of-truth, provenance, docs, archive clutter"
git tag -a v0-safe-cleanup -m "Safe cleanup baseline: prompts + provenance + docs"
git checkout -b chore/safe-cleanup

# 3. Root archive moves (if not already applied)
mkdir -p archive
git mv testing.py summarize_pdf_new.py archive/
git mv AUTH_CONSISTENCY_FIX.md AUTH_PREFLIGHT_IMPLEMENTATION.md AUTH_SINGLE_SOURCE_IMPLEMENTATION.md archive/
git mv EGYPT_FORMAT_COMPLETE.md EGYPT_FORMAT_IMPLEMENTATION.md EXACT_CODE_CHANGES.md archive/
git mv FIX_APPLIED.md FIX_SUMMARY_20260110.md IMPLEMENTATION_SUMMARY.md INSPECTION_REPORT.md archive/
git mv OCR_FLOW_DIAGRAM.md OCR_GUARDRAIL_README.md OCR_INSTALL_GUIDE.md archive/
git mv OPTION_B_COMPLETE.md OPTION_B_IMPLEMENTATION_PLAN.md OPTION_B_QUICK_REF.md archive/
git mv PDF_RENDERER_README.md PREFLIGHT_IMPLEMENTATION_SUMMARY.md PREFLIGHT_QUICK_REF.md PREFLIGHT_README.md archive/
git mv QUALITY_GATE_IMPLEMENTATION.md QUALITY_RETRY_FIX.md ROLLUP_UPDATE_SUMMARY.md STYLE_B_IMPLEMENTATION.md SUMMARY_STATUS.md archive/

# 4. Commit archive moves
git add archive/
git commit -m "chore: move unused/historical files to archive/"

# 5. Run verification (Section D)
```

**Note:** If prompt refactor and docs were already committed, skip steps that duplicate prior commits. Adapt to current git state.

---

## Section D: Verification Checklist

| # | Check | Command / Action |
|---|-------|------------------|
| 1 | Prompt module imports | `python -c "from twifo_prompts.prompts.article_prompts import PROMPT_VERSION, SYSTEM_PROMPT, USER_PROMPT, prompt_sha256, prompt_source_file; assert PROMPT_VERSION == '1.0'; print('OK')"` |
| 2 | Provenance helper | `python -c "from summarize_pdf import _get_prompt_provenance; p = _get_prompt_provenance(); assert p['prompt_version'] == '1.0' and len(p['prompt_sha256']) == 64; print('OK')"` |
| 3 | Summarization (if PDF) | `python smoke_test_pdf.py <path-to-pdf>` → check `*__sum.json` has `meta.prompt_version`, `meta.prompt_sha256` |
| 4 | Summary rendering | `python build_summaries.py <path-to-__sum.json>` → `*__sum.pdf` created |
| 5 | Rollup validation | `python rollup_validate.py --dir <rollups-daily-path>` → `[OK]` |
| 6 | UI score | `python twifo.py` → open http://127.0.0.1:8065 → confirm score pills on article rows |
| 7 | docs/CURRENT_PROMPT.md authoritative | Open file → first line states it is the only authoritative prompt doc |

See `SMOKE_RUN_CHECKLIST.md` for full validation steps.
