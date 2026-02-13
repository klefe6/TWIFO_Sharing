# Root Clutter Reduction — Move Plan

**Date:** 2026-02-04

---

## Analysis Summary

**Entrypoints (DO NOT MOVE):** twifo.py, import_dropbox.py, db_filter_autorun.py, run_weekly_rollup.py, generate_rollup_clean.py, backfill_rollups.py, rollup_validate.py, build_summaries.py, verify_summary.py, smoke_test_pdf.py, test_*.py

**Imported modules (DO NOT MOVE):** auth_env.py, openai_client.py, summarize_pdf.py, summary_render.py, rollups.py, format_validator.py, rollup_schema.py

**Batch files (DO NOT MOVE):** reboot_twifo.bat, reboot_import_dropbox.bat, run_db_filter.bat — Manager/launch_all_services.py references these paths.

**Config (DO NOT MOVE):** requirements.txt, .gitignore, README.md, PROJECT_MAP.md

---

## Safe to Move (Clearly Unused)

| File | Reason |
|------|--------|
| `testing.py` | Streamlit prototype; import_dropbox.py is production. Not imported. |
| `summarize_pdf_new.py` | Experimental; summarize_pdf.py is production. Not imported. |
| `AUTH_CONSISTENCY_FIX.md` | Historical implementation doc |
| `AUTH_PREFLIGHT_IMPLEMENTATION.md` | Historical implementation doc |
| `AUTH_SINGLE_SOURCE_IMPLEMENTATION.md` | Historical implementation doc |
| `EGYPT_FORMAT_COMPLETE.md` | Historical implementation doc |
| `EGYPT_FORMAT_IMPLEMENTATION.md` | Historical implementation doc |
| `EXACT_CODE_CHANGES.md` | Historical implementation doc |
| `FIX_APPLIED.md` | Historical implementation doc |
| `FIX_SUMMARY_20260110.md` | Historical implementation doc |
| `IMPLEMENTATION_SUMMARY.md` | Historical implementation doc |
| `INSPECTION_REPORT.md` | Historical implementation doc |
| `OCR_FLOW_DIAGRAM.md` | Historical implementation doc |
| `OCR_GUARDRAIL_README.md` | Historical implementation doc |
| `OCR_INSTALL_GUIDE.md` | Historical implementation doc |
| `OPTION_B_COMPLETE.md` | Historical implementation doc |
| `OPTION_B_IMPLEMENTATION_PLAN.md` | Historical implementation doc |
| `OPTION_B_QUICK_REF.md` | Historical implementation doc |
| `PDF_RENDERER_README.md` | Historical implementation doc |
| `PREFLIGHT_IMPLEMENTATION_SUMMARY.md` | Historical implementation doc |
| `PREFLIGHT_QUICK_REF.md` | Historical implementation doc |
| `PREFLIGHT_README.md` | Historical implementation doc |
| `QUALITY_GATE_IMPLEMENTATION.md` | Historical implementation doc |
| `QUALITY_RETRY_FIX.md` | Historical implementation doc |
| `ROLLUP_UPDATE_SUMMARY.md` | Historical implementation doc |
| `STYLE_B_IMPLEMENTATION.md` | Historical implementation doc |
| `SUMMARY_STATUS.md` | Historical implementation doc |

---

## Needs Manual Confirmation

| File | Reason |
|------|--------|
| `_tmp_json_list.txt` | Temp file; may be regenerated. Consider .gitignore instead. |
| `CLEANUP_GIT_STEPS.md` | Git workflow reference; may stay at root. |
| `DEPENDENCY_MAP.md` | Reorganization planning; could archive. |
| `SAFE_CLEANUP_BASELINE.md` | References SMOKE_TEST.md; may stay at root. |
| `QUICK_START_API_KEY.txt` | Config/reference; may stay at root. |

---

## Batch / Task Script Impact

None. Batch files reference only: twifo.py, import_dropbox.py, db_filter_autorun.py. run_db_filter.bat uses hardcoded path to db_filter_autorun.py; no changes needed.

---

## Git MV Commands (Safe-to-Move Only)

Run from repo root (`TWIFO_Sharing`):

```bash
mkdir -p archive

git mv testing.py archive/
git mv summarize_pdf_new.py archive/

git mv AUTH_CONSISTENCY_FIX.md archive/
git mv AUTH_PREFLIGHT_IMPLEMENTATION.md archive/
git mv AUTH_SINGLE_SOURCE_IMPLEMENTATION.md archive/
git mv EGYPT_FORMAT_COMPLETE.md archive/
git mv EGYPT_FORMAT_IMPLEMENTATION.md archive/
git mv EXACT_CODE_CHANGES.md archive/
git mv FIX_APPLIED.md archive/
git mv FIX_SUMMARY_20260110.md archive/
git mv IMPLEMENTATION_SUMMARY.md archive/
git mv INSPECTION_REPORT.md archive/
git mv OCR_FLOW_DIAGRAM.md archive/
git mv OCR_GUARDRAIL_README.md archive/
git mv OCR_INSTALL_GUIDE.md archive/
git mv OPTION_B_COMPLETE.md archive/
git mv OPTION_B_IMPLEMENTATION_PLAN.md archive/
git mv OPTION_B_QUICK_REF.md archive/
git mv PDF_RENDERER_README.md archive/
git mv PREFLIGHT_IMPLEMENTATION_SUMMARY.md archive/
git mv PREFLIGHT_QUICK_REF.md archive/
git mv PREFLIGHT_README.md archive/
git mv QUALITY_GATE_IMPLEMENTATION.md archive/
git mv QUALITY_RETRY_FIX.md archive/
git mv ROLLUP_UPDATE_SUMMARY.md archive/
git mv STYLE_B_IMPLEMENTATION.md archive/
git mv SUMMARY_STATUS.md archive/
```

**PowerShell equivalent** (if git mv fails on Windows):

```powershell
New-Item -ItemType Directory -Force -Path archive
git mv testing.py archive/
git mv summarize_pdf_new.py archive/
# ... (repeat for each file)
```

---

## After Moving

Update PROJECT_MAP.md with an "Archived items" section (see PROJECT_MAP update below).
