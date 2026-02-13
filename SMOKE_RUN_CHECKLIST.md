# Smoke Run Checklist

**Purpose:** Validate key flows after prompt refactor and file moves  
**Last Updated:** 2026-02-04

Run from repo root: `c:\Coding Projects\TWIFO_Sharing`

---

## 1. Article Summary — Provenance (meta.prompt_version, meta.prompt_sha256)

### Command

```powershell
python smoke_test_pdf.py "<path-to-pdf>"
```

**Example:**

```powershell
python smoke_test_pdf.py "C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\BOA_some_report_20260108_w.pdf"
```

### Artifacts to Check

| Artifact | Location | What to verify |
|----------|----------|----------------|
| `*__sum.json` | Same folder as input PDF | `meta.prompt_version` == `"1.0"` |
| | | `meta.prompt_sha256` == 64-char hex string |
| | | `meta.prompt_source_file` ends with `article_prompts.py` |
| | | `meta.code_git_commit` present (or `"(not available)"`) |

### Quick JSON Check

```powershell
python -c "
import json
from pathlib import Path
j = Path(r'<FILES_DIR>\some_article_20260108_w__sum.json')
if j.exists():
    d = json.load(j.open())
    m = d.get('meta', {})
    pv = m.get('prompt_version')
    ps = m.get('prompt_sha256')
    ok = pv == '1.0' and ps and len(ps) == 64 and all(c in '0123456789abcdef' for c in ps)
    print('prompt_version:', pv, 'OK' if pv == '1.0' else 'FAIL')
    print('prompt_sha256:', ps[:16]+'...' if ps else 'MISSING', 'OK' if ok else 'FAIL')
else:
    print('File not found')
"
```

Replace `<FILES_DIR>` and `some_article_20260108_w` with an actual `*__sum.json` path.

---

## 2. Summary Rendering

### Command

```powershell
python build_summaries.py <path-to-__sum.json>
```

**Example:**

```powershell
python build_summaries.py "C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\BOA_some_report_20260108_w__sum.json"
```

### Artifacts to Check

| Artifact | Location | What to verify |
|----------|----------|----------------|
| `*__sum.pdf` | Same folder as input `*__sum.json` | PDF exists, non‑zero size, opens without error |

### Alternative (build all)

```powershell
python build_summaries.py --all
```

Expect `[OK] Generated: <path>` for each built PDF.

---

## 3. Rollup Generation

### Command

```powershell
python generate_rollup_clean.py daily YYYY-MM-DD
```

**Example:**

```powershell
python generate_rollup_clean.py daily 2026-01-11
```

### Artifacts to Check

| Artifact | Location | What to verify |
|----------|----------|----------------|
| `ROLLUP_DAILY_YYYYMMDD__sum.json` | `<FILES_DIR>\rollups\daily\` | File created |
| `ROLLUP_DAILY_YYYYMMDD__sum.txt` | Same | File created |

### Validate Rollup

```powershell
python rollup_validate.py "C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\rollups\daily\ROLLUP_DAILY_20260111__sum.json"
```

**Expected:** `[OK] <filename> is valid`

---

## 4. UI Score Display (load_summary_score)

### Command

```powershell
python twifo.py
```

Then open: `http://127.0.0.1:8065`

### What to Verify

- Article list shows colored score pills (e.g. `7/10`).
- `load_summary_score` reads `summary_score_0_10` and `chart_score_0_3` from `*__sum.json`.

### Programmatic Check

```powershell
python -c "
from twifo import load_summary_score
path = r'C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\BOA_some_report_20260108_w__sum.json'
s, c = load_summary_score(path)
print('summary_score:', s, 'chart_score:', c)
print('OK' if (s is not None or c is not None) else 'FAIL - no scores found')
"
```

Replace path with a real `*__sum.json`. Expect numeric scores or `OK` if at least one score is present.

---

## 5. Prompt 2 — Level Sanitization (No Inferred Price Levels)

### Unit Tests

```powershell
python -m pytest test_level_sanitization.py -v -p no:dash
```

**Expected:** 9 passed (explicit levels kept, inferred dropped, years/counts not misclassified).

### Manual Verification — Known Problematic Article

Use an article that previously produced inferred levels (e.g. vague “near resistance” with no number).

1. **Summarize a PDF** with vague price language (e.g. “gold near key resistance”):
   ```powershell
   python smoke_test_pdf.py "<path-to-pdf-with-vague-levels>"
   ```

2. **Check the output JSON** `*__sum.json`:
   - `sections.trade_ideas[].key_levels` must NOT contain invented numbers (e.g. “2050”) if the source has no explicit level.
   - If levels were dropped, `extraction.dropped_inferred_level_count` (and `dropped_inferred_level_details`) will be present when `DEV_LOGGING=1`.

3. **With dev logging**:
   ```powershell
   $env:DEV_LOGGING="1"
   python smoke_test_pdf.py "<path-to-pdf>"
   ```
   Expect `[SANITIZE] dropped_inferred_level_count=N` in stdout when inferred levels are dropped.

---

## Path Reference

| Purpose | Path |
|---------|------|
| Repo root | `c:\Coding Projects\TWIFO_Sharing` |
| Article export | `C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE` |
| Daily rollups | `...\FOLDERS_AVAILABLE_ONLINE\rollups\daily\` |

---

## Minimal Run (No API Key Required)

If no PDF is available for summarization:

1. **Provenance:** Pick any existing `*__sum.json` and run the JSON check (section 1).
2. **Rendering:** `python build_summaries.py <path-to-existing-__sum.json>`
3. **Rollup:** `python rollup_validate.py --dir <rollups-daily-path>`
4. **UI:** `python twifo.py` → open `http://127.0.0.1:8065` → confirm score pills appear on article rows.
