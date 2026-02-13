# Extraction Quality Quick Reference

**Purpose:** Deterministic health scoring for PDF text extraction  
**Date:** 2026-02-12

---

## Quality Score (0-100)

```python
score = page_coverage(0-40) + chars(0-40) - ocr_penalty(20) - errors(0-20)
```

### Score Ranges

| Range | Quality | Action |
|-------|---------|--------|
| 80-100 | Excellent | ✅ Publish normally |
| 60-79 | Good | ✅ Publish normally |
| 40-59 | Acceptable | ⚠️ Check if degraded |
| 20-39 | Poor | ⚠️ Likely degraded |
| 0-19 | Very Poor | ❌ Likely failed |

---

## Status Values

| Status | Publishing | UI Display |
|--------|------------|------------|
| **ok** | ✅ Published | 📄 View |
| **degraded** | ⚠️ With warning | ⚠️ View |
| **failed** | ❌ Hidden | Not shown |

---

## Degraded Rules

Marked as **degraded** when:

```python
pages_with_text / pages_total < 0.4  # < 40% coverage
OR chars_total < 1500                 # < 1500 chars
OR quality_score < 40                 # Low score
OR len(errors) >= 2                   # Multiple errors
```

---

## Failed Rules

Marked as **failed** when:

```python
method_used == "failed"               # Complete failure
OR chars_total < 100                  # No meaningful text
OR has_critical_errors()              # Corrupt, unreadable
```

---

## Usage

### Check Quality

```python
from summarize_pdf import compute_extraction_quality

extraction_meta = {
    'pages_total': 10,
    'pages_with_text': 8,
    'chars_total': 5000,
    'ocr_used': False,
    'errors': []
}

score, status = compute_extraction_quality(extraction_meta)
print(f"{status}: {score}/100")
```

### Find Degraded Summaries

```python
import json
from path_manager import get_path_manager

pm = get_path_manager()

for artifact in pm.list_artifacts_with_summaries():
    json_path = pm.artifact_path(artifact['basename'], 'sum.json')
    with open(json_path) as f:
        summary = json.load(f)
    
    if summary['meta'].get('low_confidence'):
        print(f"Degraded: {artifact['basename']}")
```

---

## Metadata Structure

### In sum.json

```json
{
  "meta": {
    "low_confidence": true,
    "extraction": {
      "status": "degraded",
      "extraction_quality_0_100": 35,
      "degradation_reasons": ["low_page_coverage (30.0%)"]
    }
  }
}
```

---

## Thresholds (Tunable)

```python
# In summarize_pdf.py
QUALITY_DEGRADED_CHARS = 1500       # < 1500 chars = degraded
QUALITY_DEGRADED_PAGE_RATIO = 0.4  # < 40% pages = degraded
OCR_QUALITY_PENALTY = 20            # -20 pts for OCR
```

---

## UI Behavior

### Main Feed (twifo.py)
- **ok**: 📄 View
- **degraded**: ⚠️ View
- **failed**: (hidden)

### Summary PDF (summary_render.py)
- **degraded**: Yellow warning banner at top
- **ok**: No banner

---

## Examples

### Excellent (80/100, ok)
```python
{'pages_total': 12, 'pages_with_text': 12, 'chars_total': 18000, 'ocr_used': False, 'errors': []}
```

### Degraded (35/100, degraded)
```python
{'pages_total': 10, 'pages_with_text': 3, 'chars_total': 1200, 'ocr_used': False, 'errors': []}
```

### Failed (0/100, failed)
```python
{'pages_total': 10, 'pages_with_text': 0, 'chars_total': 0, 'ocr_used': False, 'errors': ['All methods failed'], 'method_used': 'failed'}
```

---

## Testing

```bash
python test_extraction_quality.py
```

---

## Troubleshooting

### Too many degraded?
→ Lower `QUALITY_DEGRADED_CHARS` or `QUALITY_DEGRADED_PAGE_RATIO`

### OCR penalty too harsh?
→ Reduce `OCR_QUALITY_PENALTY` from 20 to 10

### Failed summaries showing?
→ Check filter in `twifo.py` line ~2012

---

**Full docs:** See `EXTRACTION_QUALITY.md`
