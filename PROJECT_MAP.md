# TWIFO_Sharing Project Map

**Last Updated:** 2026-02-04

---

## What Runs What

| Entrypoint | Launcher | Port | Purpose |
|------------|----------|------|---------|
| `twifo.py` | `reboot_twifo.bat` or `python twifo.py` | **8065** | Main Dash web app (research directory) |
| `import_dropbox.py` | `reboot_import_dropbox.bat` or `streamlit run import_dropbox.py` | **8001** | Dropbox management (Streamlit) |
| `db_filter_autorun.py` | `run_db_filter.bat` | — | PDF import + summarization pipeline |
| `run_weekly_rollup.py` | Windows Task Scheduler (Mondays 12:05am ET) | — | Weekly rollup generation |

---

## Where Summaries Live

Article summaries (`*__sum.json`, `*__sum.txt`, `*__sum.pdf`) are written alongside PDFs in:

```
<FILES_DIR>/
  *.pdf
  *_*__sum.json
  *_*__sum.txt
  *_*__sum.pdf
```

**FILES_DIR** (config in `twifo.py`, `db_filter_autorun.py`, `generate_rollup_clean.py`):

```
C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE
```

---

## Where Rollups Live

Daily and weekly rollups are under FILES_DIR:

```
<FILES_DIR>/rollups/
  daily/   → ROLLUP_DAILY_YYYYMMDD__sum.json
  weekly/  → ROLLUP_WEEKLY_YYYYMMDD__sum.json
```

---

## Where Prompts Live (Single Source of Truth)

| What | Path |
|------|------|
| **Live prompt code** | `twifo_prompts/prompts/article_prompts.py` |
| **Exports** | `PROMPT_VERSION`, `SYSTEM_PROMPT`, `USER_PROMPT`, `prompt_sha256()` |

Do not edit prompts elsewhere. See `docs/CURRENT_PROMPT.md` for authoritative prompt documentation.

---

## Where Docs Live

| Location | Purpose |
|----------|---------|
| `docs/CURRENT_PROMPT.md` | **Authoritative** prompt doc — version, rules, schema |
| `docs/README.md` | Points to CURRENT_PROMPT.md as sole prompt reference |
| `docs/archive/` | **Deprecated** — historical prompt docs (see below) |

---

## Deprecated

**`docs/archive/`** — Do not use for current behavior. Contains historical prompt docs:

- ANTI_HALLUCINATION_IMPLEMENTATION.md
- ARTICLE_FINAL_IMPLEMENTATION.md
- ARTICLE_PROMPT_UPGRADE.md
- BALANCED_PROMPT_UPDATE.md
- EXTRACTION_ONLY_PROMPT.md
- FINAL_PROMPT_CONFIGURATION.md

---

## Archived Items (Root `archive/`)

Unused or historical files moved from repo root. Not imported, not launched by batch/Task Scheduler.

**Python:** testing.py (Streamlit prototype), summarize_pdf_new.py (experimental, superseded by summarize_pdf)

**Implementation docs:** AUTH_CONSISTENCY_FIX, AUTH_PREFLIGHT_IMPLEMENTATION, AUTH_SINGLE_SOURCE_IMPLEMENTATION, EGYPT_FORMAT_COMPLETE, EGYPT_FORMAT_IMPLEMENTATION, EXACT_CODE_CHANGES, FIX_APPLIED, FIX_SUMMARY_20260110, IMPLEMENTATION_SUMMARY, INSPECTION_REPORT, OCR_FLOW_DIAGRAM, OCR_GUARDRAIL_README, OCR_INSTALL_GUIDE, OPTION_B_COMPLETE, OPTION_B_IMPLEMENTATION_PLAN, OPTION_B_QUICK_REF, PDF_RENDERER_README, PREFLIGHT_IMPLEMENTATION_SUMMARY, PREFLIGHT_QUICK_REF, PREFLIGHT_README, QUALITY_GATE_IMPLEMENTATION, QUALITY_RETRY_FIX, ROLLUP_UPDATE_SUMMARY, STYLE_B_IMPLEMENTATION, SUMMARY_STATUS
