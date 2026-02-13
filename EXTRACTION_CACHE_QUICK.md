# Extraction Caching - Quick Reference

**Version:** 1.0  
**Date:** 2026-02-12

---

## What It Does

Caches extracted text from PDFs using SHA256 hash as the key. Skips re-extraction if PDF hasn't changed.

---

## Files Created

```
artifacts/<basename>/
├── extracted.txt      # Cached extracted text
└── extraction.json    # Metadata + SHA256
```

---

## Quick Usage

```python
from summarize_pdf import extract_text
from path_manager import get_path_manager

pm = get_path_manager()
pdf_path = pm.original_pdf_path("BOA_Report.pdf")

# Automatically uses cache if available
text, meta = extract_text(pdf_path, path_manager=pm)
```

---

## Key Metadata

```json
{
  "pdf_sha256": "abc123...",
  "method_used": "pypdf",
  "status": "ok",
  "pages_total": 10,
  "pages_with_text": 10,
  "chars_total": 15234,
  "ocr_used": false,
  "errors": [],
  "created_at": "2026-02-12T10:30:00",
  "duration_ms": 245
}
```

---

## OCR Thresholds

```python
OCR_THRESHOLD_CHARS = 500          # < 500 chars → OCR
OCR_THRESHOLD_PAGES_RATIO = 0.3    # < 30% pages with text → OCR
```

---

## Check Cache Status

```python
from summarize_pdf import load_extraction_cache

cached = load_extraction_cache(pdf_path, pm)
if cached:
    print("✓ Cache hit")
else:
    print("✗ Cache miss")
```

---

## Force Re-extraction

```python
# Delete cache files
pm.artifact_path(basename, "extracted.txt").unlink(missing_ok=True)
pm.artifact_path(basename, "extraction.json").unlink(missing_ok=True)
```

Or:

```bash
rm -rf artifacts/BOA_Report_20260212_w/
```

---

## Performance

- **Cache hit:** ~5ms (vs 250ms extraction)
- **Cache hit rate:** 70-90% typical
- **Benefit:** ~10% faster re-processing

---

## Testing

```bash
python test_extraction_cache.py
```

---

## Common Issues

### Cache not working?

```python
# Always pass path_manager
text, meta = extract_text(pdf_path, path_manager=pm)
```

### OCR triggered too often?

```python
# Adjust thresholds in summarize_pdf.py
OCR_THRESHOLD_CHARS = 200  # Lower
```

---

*See `EXTRACTION_CACHE.md` for full documentation*
