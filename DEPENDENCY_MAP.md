# TWIFO_Sharing - Dependency & Entrypoint Map

**Purpose:** Safe reorganization planning - do not move files until reviewing this map  
**Generated:** 2026-02-04  
**Author:** AI Analysis

---

## 1. Runtime Entrypoints (Executed Directly)

### Production Services

| File | Type | Launched By | Port | Description |
|------|------|-------------|------|-------------|
| `twifo.py` | Dash App | `reboot_twifo.bat` | 8050 | Main research directory web interface |
| `import_dropbox.py` | Streamlit App | `reboot_import_dropbox.bat` | 8001 | Dropbox management interface |
| `db_filter_autorun.py` | Script | `run_db_filter.bat` | - | Dropbox PDF import & summarization pipeline |
| `run_weekly_rollup.py` | Script | Windows Task Scheduler | - | Weekly rollup generation (Mondays 12:05am ET) |

### CLI Tools

| File | Purpose |
|------|---------|
| `generate_rollup_clean.py` | Manual daily/weekly rollup generation |
| `backfill_rollups.py` | Backfill rollups for date ranges |
| `rollup_validate.py` | Validate rollup JSON schema |
| `build_summaries.py` | Batch summary generation |
| `verify_summary.py` | Verify summary quality |

### Test Suite (17 files)

All files matching `test_*.py` pattern - these are direct execution entrypoints for testing:

- `test_auth_consistency.py` - Auth module consistency tests
- `test_auth_preflight.py` - Preflight auth validation tests
- `test_key_source_precedence.py` - API key precedence tests
- `test_quality_retry.py` - Quality gate retry logic tests
- `test_quality_gate.py` - Summary quality validation tests
- `test_quality_gate_integration.py` - End-to-end quality tests
- `test_article_quality_gate.py` - Article-specific quality tests
- `test_rollup_no_hallucination.py` - Rollup hallucination prevention tests
- `test_rollup_generation.py` - Rollup generation tests
- `test_summarize_one.py` - Single PDF summarization tests
- `test_ocr_guardrail.py` - OCR quality detection tests
- `test_full_summary.py` - Full summarization pipeline tests
- `test_new_extraction.py` - PDF text extraction tests
- `test_extraction_validation.py` - Extraction validation tests
- `test_format_one_file.py` - Format validation tests
- `test_api_key_setup.py` - API key setup tests
- `smoke_test_pdf.py` - Quick PDF summarization smoke test

---

## 2. Import Graph for `summarize_pdf.py`

### What `summarize_pdf.py` Imports

```
summarize_pdf.py
├── openai_client.py
│   └── auth_env.py
├── auth_env.py
├── format_validator.py (conditional, for validation/fixing)
└── Standard library: os, sys, json, pathlib, datetime, hashlib, tempfile, subprocess, re, typing
```

### Where `summarize_pdf.py` is Imported From

#### Production Code
- **`db_filter_autorun.py`** - Primary consumer
  - Imports: `summarize_pdf()`, `summarize_text()`
  - Uses: PDF/text summarization in Dropbox import pipeline
  
- **`twifo.py`** - Web interface
  - Imports: `ensure_summary_pdf()` (lazy import in route handler)
  - Uses: On-demand PDF generation for web views

#### Test Code (15 files)
- `test_auth_consistency.py` → `llm_summarize_to_json()`
- `test_auth_preflight.py` → `check_openai_auth()`
- `test_key_source_precedence.py` → `OPENAI_API_KEY`
- `test_quality_retry.py` → `is_low_quality_summary()`, `_failed_stub()`, `_extract_bullet_text()`, `_normalize_sections_in_place()`, `_write_debug_artifact()`, `_sum_debug_path()`
- `test_article_quality_gate.py` → `is_low_quality_summary()`
- `test_quality_gate_integration.py` → `summarize_text()`, `render_sum_txt()`
- `test_quality_gate.py` → `is_low_quality_summary()`
- `test_summarize_one.py` → `should_skip_summary()`, `summarize_pdf()`, `create_summary_file()`
- `test_ocr_guardrail.py` → Multiple OCR functions
- `test_full_summary.py` → `summarize_pdf()`
- `test_new_extraction.py` → `extract_text_best_effort()`, `MIN_CHARS_TO_ACCEPT`
- `test_extraction_validation.py` → `validate_extraction()`
- `test_format_one_file.py` → `render_sum_txt()`
- `smoke_test_pdf.py` → `summarize_pdf()`

### Critical Dependencies

**`summarize_pdf.py` is the CORE module** - changes to it affect:
- All 15+ test files
- Production Dropbox pipeline (`db_filter_autorun.py`)
- Web interface PDF generation (`twifo.py`)

---

## 3. Files with LLM Prompts (Prompt-Like Content)

### Code Files with Active Prompts

| File | Prompt Location | Description |
|------|----------------|-------------|
| **`summarize_pdf.py`** | Lines 789-941 | **PRIMARY PRODUCTION PROMPT** |
| | `system_prompt` (lines 789-839) | System instructions, anti-hallucination rules |
| | `user_prompt` (lines 846-941) | JSON schema, validation rules, quality requirements |
| `summarize_pdf_new.py` | Lines 418-436 | Alternative/experimental prompt (not in production) |
| `test_summarize_one.py` | Lines 181-234 | Test-specific prompt variant |
| `format_validator.py` | Lines 138, 199 | LLM-based format fixing prompts (compact) |

### Documentation Files with Prompt Content

| File | Content |
|------|---------|
| **`FINAL_PROMPT_CONFIGURATION.md`** | Current production prompt config (balanced + numeric ban) |
| **`ARTICLE_PROMPT_UPGRADE.md`** | Complete prompt with 15 critical rules (lines 519-565 reference) |
| **`ARTICLE_FINAL_IMPLEMENTATION.md`** | Volatility, product structure, machine-friendly rules |
| `BALANCED_PROMPT_UPDATE.md` | Balanced prompt version (allows directional ideas) |
| `EXTRACTION_ONLY_PROMPT.md` | Extraction-only prompt variant (strict version) |
| `ANTI_HALLUCINATION_IMPLEMENTATION.md` | Anti-hallucination prompt strategies |

### Prompt Evolution Tracking

**Active Prompt:** `summarize_pdf.py` lines 789-941  
**Documentation:** `FINAL_PROMPT_CONFIGURATION.md` + `ARTICLE_FINAL_IMPLEMENTATION.md`  
**History:** Other `*PROMPT*.md` files are historical/alternative versions

⚠️ **WARNING:** Prompt in `summarize_pdf.py` must stay in sync with documentation. Any prompt changes require updating both code and docs.

---

## 4. Batch Files & Task Scheduler Scripts

### Batch Files

| File | Executes | Python Path | Working Dir | Purpose |
|------|----------|-------------|-------------|---------|
| **`reboot_twifo.bat`** | `twifo.py` | `C:\Program Files\Coding Projects\HomePage\.venv13\Scripts\python.exe` | TWIFO_Sharing | Launch main Dash web app (port 8050) |
| **`reboot_import_dropbox.bat`** | `import_dropbox.py` | `C:\Program Files\Coding Projects\TWIFO_Sharing\.venv13\Scripts\streamlit.exe` | TWIFO_Sharing | Launch Streamlit Dropbox manager (port 8001) |
| **`run_db_filter.bat`** | `db_filter_autorun.py` | `.venv13\Scripts\python.exe` or `C:\Python313\python.exe` | TWIFO_Sharing | Run Dropbox PDF import pipeline |

### Batch File Details

#### `reboot_twifo.bat`
```batch
Python: C:\Program Files\Coding Projects\HomePage\.venv13\Scripts\python.exe
Script: twifo.py (in same dir as .bat)
Note: Uses HomePage's venv (not TWIFO_Sharing's)
```

#### `reboot_import_dropbox.bat`
```batch
Streamlit: C:\Program Files\Coding Projects\TWIFO_Sharing\.venv13\Scripts\streamlit.exe
Script: import_dropbox.py
Port: 8001 (fixed, no auto-increment)
Note: Uses TWIFO_Sharing's own venv
```

#### `run_db_filter.bat`
```batch
Python: .venv13\Scripts\python.exe (fallback: C:\Python313\python.exe)
Script: C:\Program Files\Coding Projects\TWIFO_Sharing\db_filter_autorun.py
Logs: %TEMP%\TWIFO_logs\db_filter_YYYYMMDD_HHmmss.log
```

### Windows Task Scheduler

| Task | Script | Schedule | Description |
|------|--------|----------|-------------|
| Weekly Rollup | `run_weekly_rollup.py` | Mondays 12:05am ET | Generate weekly rollups for previous Mon-Fri |

**Source:** `README.md` line 294

---

## 5. "Do Not Touch" List (Critical Files - Must Remain in Place)

### Core Runtime Files (Breaking Changes if Moved)

**Tier 1: Absolute Critical - Production Services Depend On These**

```
✋ REQUIRED AT ROOT - DO NOT MOVE OR RENAME

1. twifo.py                    - Main web app (launched by reboot_twifo.bat)
2. import_dropbox.py           - Streamlit app (launched by reboot_import_dropbox.bat)
3. db_filter_autorun.py        - Dropbox pipeline (launched by run_db_filter.bat)
4. run_weekly_rollup.py        - Task Scheduler (scheduled task points to this)

5. summarize_pdf.py            - Core summarization (imported by 15+ files)
6. summary_render.py           - PDF rendering (imported by production + tools)
7. rollups.py                  - Rollup builder (imported by generation scripts)

8. auth_env.py                 - Auth source-of-truth (imported by openai_client + summarize_pdf)
9. openai_client.py            - OpenAI client singleton (imported by summarize_pdf + auth_env)
10. format_validator.py        - Format validation (conditionally imported by summarize_pdf)

11. rollup_schema.py           - Rollup schema definitions
```

**Tier 2: Batch Files - Path Hardcoded**

```
✋ MUST REMAIN AT ROOT (batch files have hardcoded paths)

- reboot_twifo.bat
- reboot_import_dropbox.bat
- run_db_filter.bat
```

**Tier 3: CLI Tools - Can Move If Import Paths Updated**

```
⚠️ CAN MOVE BUT UPDATE IMPORTS

- generate_rollup_clean.py
- backfill_rollups.py
- rollup_validate.py
- build_summaries.py
- verify_summary.py
- testing.py (unused Streamlit prototype)
```

**Tier 4: Test Files - Safe to Reorganize**

```
✅ SAFE TO MOVE INTO /tests/ folder

All test_*.py files (17 files)
All smoke_test_*.py files
```

### Configuration Files

```
✋ DO NOT MOVE

- requirements.txt             - Pip dependencies
- .gitignore                   - Git ignore rules
- .env (if exists)             - API keys (not in repo, but expected at root)
```

### Documentation Files

```
✅ SAFE TO MOVE INTO /docs/ folder

All *.md files except README.md
- FINAL_PROMPT_CONFIGURATION.md
- ARTICLE_PROMPT_UPGRADE.md
- ARTICLE_FINAL_IMPLEMENTATION.md
- BALANCED_PROMPT_UPDATE.md
- EXTRACTION_ONLY_PROMPT.md
- ANTI_HALLUCINATION_IMPLEMENTATION.md
- etc. (all other .md files)

⚠️ Keep README.md at root (standard practice)
```

### Temp/Cache Files

```
🗑️ SAFE TO DELETE OR .gitignore

- _tmp_json_list.txt           - Temp file (already uncommitted)
- .pdf_cache/                  - PDF text cache (already in .gitignore)
- __pycache__/                 - Python bytecode (already in .gitignore)
```

---

## Reorganization Safe Zones

### ✅ Safe to Move (No Breaking Changes)

1. **Test Files** → `/tests/` subfolder
   - All `test_*.py` files
   - Update imports: `from summarize_pdf` → `from ..summarize_pdf`
   - Update pytest config if needed

2. **Documentation** → `/docs/` subfolder
   - All `*.md` files except `README.md`
   - No code dependencies

3. **CLI Tools** → `/scripts/` or `/tools/` subfolder
   - `generate_rollup_clean.py`
   - `backfill_rollups.py`
   - `rollup_validate.py`
   - `build_summaries.py`
   - `verify_summary.py`
   - Update imports as needed

4. **Unused/Experimental** → `/archive/` or delete
   - `testing.py` (unused Streamlit prototype)
   - `summarize_pdf_new.py` (experimental, not in production)

### ⚠️ Move Only After Updating References

1. **Batch Files** → Can't move without updating hardcoded paths in batch files themselves
2. **Core Modules** → Can move to `/src/` but requires updating ALL imports in:
   - Production code (twifo.py, db_filter_autorun.py, etc.)
   - Test files (15+ files)
   - Batch file Python paths

### ❌ Do Not Move Without Major Refactor

1. **Core Runtime Entrypoints**
   - `twifo.py`, `import_dropbox.py`, `db_filter_autorun.py`, `run_weekly_rollup.py`
   - Referenced by batch files, Task Scheduler, external launchers

2. **Core Dependency Chain**
   - `summarize_pdf.py` ← (imported by 15+ files)
   - `summary_render.py` ← (imported by production + tools)
   - `rollups.py` ← (imported by generation scripts)
   - `auth_env.py` + `openai_client.py` ← (imported by summarize_pdf + tests)

---

## Dependency Flow Diagram

```
Production Services (Entrypoints)
├── twifo.py (Dash Web App)
│   └── summarize_pdf.ensure_summary_pdf() [lazy]
│
├── import_dropbox.py (Streamlit)
│   └── (standalone, no internal deps)
│
└── db_filter_autorun.py (Dropbox Pipeline)
    ├── summarize_pdf.summarize_pdf()
    ├── summarize_pdf.summarize_text()
    ├── summary_render.render_summary_pdf()
    └── auth_env.assert_openai_auth_ok()

Core Module Chain
summarize_pdf.py
├── openai_client.get_client()
│   └── auth_env.get_openai_api_key()
├── auth_env.describe_key()
└── format_validator.validate_article_summary() [conditional]

Rollup Generation
generate_rollup_clean.py
├── rollups.build_daily_rollup()
├── rollups.build_weekly_rollup()
└── summary_render.render_rollup_pdf()

run_weekly_rollup.py
└── (calls generate_rollup_clean functions)

backfill_rollups.py
├── rollups.build_daily_rollup()
├── rollups.build_weekly_rollup()
└── summary_render.render_rollup_pdf()
```

---

## Recommended Reorganization (If Proceeding)

### Phase 1: Low-Risk Moves

```
/TWIFO_Sharing/
├── /docs/                           # NEW: Documentation
│   ├── FINAL_PROMPT_CONFIGURATION.md
│   ├── ARTICLE_PROMPT_UPGRADE.md
│   ├── ARTICLE_FINAL_IMPLEMENTATION.md
│   └── (all other .md files except README.md)
│
├── /tests/                          # NEW: Test suite
│   ├── test_*.py (17 files)
│   └── smoke_test_pdf.py
│
└── README.md (stays at root)
```

### Phase 2: Medium-Risk Moves (Update Imports)

```
/TWIFO_Sharing/
├── /scripts/                        # NEW: CLI tools
│   ├── generate_rollup_clean.py
│   ├── backfill_rollups.py
│   ├── rollup_validate.py
│   ├── build_summaries.py
│   └── verify_summary.py
│
└── (update imports in moved files)
```

### Phase 3: High-Risk Moves (Major Refactor Required)

**NOT RECOMMENDED** unless necessary - requires updating:
- All batch files (hardcoded paths)
- All import statements (15+ files)
- Windows Task Scheduler config
- External launchers (Manager, HomePage, etc.)

```
/TWIFO_Sharing/
├── /src/                            # Core modules
│   ├── summarize_pdf.py
│   ├── summary_render.py
│   ├── rollups.py
│   ├── auth_env.py
│   ├── openai_client.py
│   └── format_validator.py
│
└── (massive import refactor needed)
```

---

## Next Steps

1. **Review this map** - Identify files to reorganize
2. **Start with Phase 1** - Low-risk documentation + test moves
3. **Update imports** - If moving CLI tools (Phase 2)
4. **Avoid Phase 3** - Core module moves require major refactor

**Before moving ANY file:**
- Check "Do Not Touch" list
- Grep for imports: `rg "from FILENAME|import FILENAME"`
- Test after moving: Run test suite + manual smoke tests

---

## File Count Summary

| Category | Count |
|----------|-------|
| Production Entrypoints | 4 |
| CLI Tools | 5 |
| Test Files | 17 |
| Core Modules | 10 |
| Batch Files | 3 |
| Documentation | 25+ |
| Total Python Files | 35 |

**Critical Path:** `summarize_pdf.py` → imported by 15+ files  
**Highest Risk:** Moving core modules (breaks 15+ import statements)  
**Lowest Risk:** Moving docs + tests (no code dependencies)
