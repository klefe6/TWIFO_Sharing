# TWIFO File Layout - Quick Reference

**Version:** 1.0  
**Date:** 2026-02-12

---

## Directory Structure

```
FILES_DIR/
├── originals/              # ← Original PDFs (never modify)
├── artifacts/<basename>/   # ← Generated files
│   ├── extracted.txt
│   ├── extraction.json
│   ├── sum.json
│   ├── sum.txt
│   └── sum.pdf
└── rollups/                # ← Daily/weekly rollups
```

---

## Key Commands

### Migration

```bash
# Preview changes (safe)
python migrate_file_layout.py --dry-run

# Migrate (creates backup)
python migrate_file_layout.py

# Verify migration
python migrate_file_layout.py --verify-only
```

### Testing

```bash
# Run path manager tests
python test_path_manager.py
```

### Check Status

```python
from path_manager import get_path_manager

pm = get_path_manager()
print(f"Originals: {len(pm.list_originals())}")
print(f"Artifacts: {len(pm.list_artifacts_with_summaries())}")
```

---

## File Mapping

### Old Layout → New Layout

| Old Location | New Location |
|--------------|--------------|
| `FILES_DIR/BOA_Report.pdf` | `originals/BOA_Report.pdf` |
| `FILES_DIR/BOA_Report__sum.json` | `artifacts/BOA_Report/sum.json` |
| `FILES_DIR/BOA_Report__sum.txt` | `artifacts/BOA_Report/sum.txt` |
| `FILES_DIR/BOA_Report__sum.pdf` | `artifacts/BOA_Report/sum.pdf` |
| `FILES_DIR/BOA_Report__sum_debug_raw.txt` | `artifacts/BOA_Report/extracted.txt` |

---

## Code Examples

### Get Paths

```python
from path_manager import get_path_manager

pm = get_path_manager()

# Original PDF
orig = pm.original_pdf_path("BOA_Report_20260212_w.pdf")

# Summary artifacts
json_path = pm.artifact_path("BOA_Report_20260212_w", "sum.json")
pdf_path = pm.artifact_path("BOA_Report_20260212_w", "sum.pdf")
```

### Generate Summary (New)

```python
from summarize_pdf import summarize_pdf
from path_manager import get_path_manager

pm = get_path_manager()
pdf = pm.original_pdf_path("BOA_Report.pdf")

# Use path_manager for new layout
summary = summarize_pdf(pdf, path_manager=pm)
```

### Check Summary Exists

```python
from path_manager import get_path_manager

pm = get_path_manager()
has_pdf, has_json, has_txt = pm.has_summary("BOA_Report_20260212_w")

if has_pdf:
    print("Summary PDF exists")
if has_json:
    print("Summary JSON exists")
```

---

## Metadata in sum.json

All summaries now include:

```json
{
  "meta": {
    "original_pdf_path": "/path/to/originals/BOA_Report.pdf",
    "original_pdf_sha256": "abc123...",
    "extraction": {
      "status": "ok",
      "method_used": "pypdf",
      "extraction_quality_0_100": 95
    }
  }
}
```

---

## Backward Compatibility

✅ **System works with BOTH old and new layouts**

- Old `__sum.*` files still work
- No migration required (but recommended)
- Graceful fallback to legacy paths

---

## Common Issues

### "Original PDF not found"

```bash
# Run migration
python migrate_file_layout.py
```

### "Summary not showing"

```python
# Check if artifacts exist
from path_manager import get_path_manager
pm = get_path_manager()
print(pm.has_summary("BOA_Report_20260212_w"))
```

### "Old files still in root"

```bash
# Safe to re-run migration
python migrate_file_layout.py
```

---

## Documentation

- `FILE_LAYOUT.md` - Full documentation
- `IMPLEMENTATION_SUMMARY.md` - Implementation details
- `test_path_manager.py` - Test examples

---

## Status

✅ **Implemented and Tested**  
✅ **Backward Compatible**  
✅ **Production Ready**

---

*For detailed information, see `FILE_LAYOUT.md`*
