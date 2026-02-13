# TWIFO Extraction Quality Metrics & Degraded Gating

**Feature:** Deterministic extraction health scoring with degraded gating  
**Version:** 1.0  
**Date:** 2026-02-12

---

## Overview

The extraction quality system provides **deterministic, measurable health metrics** for PDF text extraction. It assigns quality scores (0-100) and status flags (`ok` | `degraded` | `failed`) based on objective signals.

---

## Quality Scoring (0-100)

### Scoring Components

Quality score is computed from four measurable factors:

| Component | Weight | Description |
|-----------|--------|-------------|
| **Page coverage** | 0-40 pts | `pages_with_text / pages_total` ratio |
| **Character count** | 0-40 pts | Total characters extracted |
| **OCR penalty** | -20 pts | Deduction for OCR usage (less reliable) |
| **Error penalty** | 0-20 pts | Deduction for extraction errors |

### Scoring Formula

```python
score = 0

# 1. Page coverage (0-40 points)
if pages_total > 0:
    page_ratio = pages_with_text / pages_total
    page_score = min(40, int(page_ratio * 40))
    score += page_score

# 2. Character count (0-40 points)
if chars >= 10,000:    score += 40      # Excellent
elif chars >= 5,000:   score += 30-40   # Good (interpolated)
elif chars >= 1,500:   score += 15-30   # Acceptable (interpolated)
elif chars >= 500:     score += 5-15    # Marginal (interpolated)
else:                  score += 0-5     # Poor

# 3. OCR penalty (-20 points)
if ocr_used:
    score -= 20

# 4. Error penalty (0-20 points)
error_penalty = min(20, len(errors) * 5)
score -= error_penalty

# 5. Clamp to 0-100
score = max(0, min(100, score))
```

---

## Extraction Status

### Status Values

| Status | Description | Publishing |
|--------|-------------|------------|
| **`ok`** | Good quality extraction | ✅ Published to main feed |
| **`degraded`** | Low quality but usable | ⚠️ Published with warning badge |
| **`failed`** | Complete failure | ❌ NOT published to main feed |
| **`unknown`** | Status could not be determined | ⚠️ Treated as degraded |

### Status Rules

**FAILED** when:
- `method_used == "failed"`
- `chars_total < 100`
- Critical errors (corrupt, unreadable, invalid)

**DEGRADED** when:
- `pages_with_text / pages_total < 0.4` (< 40% page coverage)
- `chars_total < 1500` (insufficient text)
- `quality_score < 40` (low overall quality)
- `len(errors) >= 2` (multiple errors)

**OK** when:
- None of the above conditions apply

---

## Degraded Gating Behavior

### What Happens for Degraded Extractions

1. **Summary generation proceeds** - Article is still summarized
2. **`meta.low_confidence = true`** - Flag added to JSON
3. **Warning badge in UI** - ⚠️ icon shown in summary link
4. **Warning banner in PDF** - Yellow alert box at top of summary
5. **Degradation reasons logged** - Stored in `meta.degradation_details`

### Example Degraded Summary

```json
{
  "schema_version": "twifo.sum.v1",
  "meta": {
    "low_confidence": true,
    "low_confidence_reason": "degraded_extraction",
    "degradation_details": [
      "low_page_coverage (0.3)",
      "low_char_count (1234)"
    ],
    "extraction": {
      "status": "degraded",
      "extraction_quality_0_100": 35,
      "pages_total": 10,
      "pages_with_text": 3,
      "chars_total": 1234,
      "ocr_used": false,
      "degradation_reasons": [
        "low_page_coverage (30.0%)",
        "low_char_count (1234)"
      ]
    }
  },
  "sections": { ... }
}
```

---

## UI Display

### Main Feed (twifo.py)

**OK extractions:**
```
| Summary |
|---------|
| 📄 View |
```

**Degraded extractions:**
```
| Summary |
|---------|
| ⚠️ View |
```

**Failed extractions:**
```
(Not shown in main feed)
```

### Summary PDF (summary_render.py)

Degraded extractions show a warning banner:

```
┌─────────────────────────────────────────────────────┐
│ ⚠️ LOW CONFIDENCE                                   │
│ This summary was generated from degraded text      │
│ extraction. Content may be incomplete or less      │
│ accurate than typical summaries.                   │
└─────────────────────────────────────────────────────┘
```

---

## Configuration

### Thresholds (in `summarize_pdf.py`)

```python
# Quality scoring
QUALITY_EXCELLENT_CHARS = 10000      # > 10k chars = excellent
QUALITY_GOOD_CHARS = 5000            # > 5k chars = good
QUALITY_DEGRADED_CHARS = 1500        # < 1.5k chars = degraded
QUALITY_DEGRADED_PAGE_RATIO = 0.4   # < 40% pages = degraded

# OCR penalty
OCR_QUALITY_PENALTY = 20             # -20 points for OCR

# OCR triggering (from previous feature)
OCR_THRESHOLD_CHARS = 500            # < 500 chars → try OCR
OCR_THRESHOLD_PAGES_RATIO = 0.3      # < 30% pages → try OCR
```

### Tuning Guidelines

Adjust thresholds based on your content:

**For dense research PDFs (current settings):**
```python
QUALITY_DEGRADED_CHARS = 1500
QUALITY_DEGRADED_PAGE_RATIO = 0.4
```

**For shorter briefings:**
```python
QUALITY_DEGRADED_CHARS = 800
QUALITY_DEGRADED_PAGE_RATIO = 0.3
```

**For infographics:**
```python
QUALITY_DEGRADED_CHARS = 500
QUALITY_DEGRADED_PAGE_RATIO = 0.2
```

---

## Examples

### Example 1: Excellent Quality

```python
extraction = {
    'pages_total': 12,
    'pages_with_text': 12,
    'chars_total': 18000,
    'ocr_used': False,
    'errors': []
}

score, status = compute_extraction_quality(extraction)
# score: 80, status: 'ok'
```

### Example 2: Degraded (Low Page Coverage)

```python
extraction = {
    'pages_total': 10,
    'pages_with_text': 3,  # Only 30%
    'chars_total': 5000,
    'ocr_used': False,
    'errors': []
}

score, status = compute_extraction_quality(extraction)
# score: ~52, status: 'degraded'
# Reason: low_page_coverage (30.0%)
```

### Example 3: Degraded (Insufficient Text)

```python
extraction = {
    'pages_total': 8,
    'pages_with_text': 8,
    'chars_total': 1200,  # < 1500
    'ocr_used': False,
    'errors': []
}

score, status = compute_extraction_quality(extraction)
# score: ~55, status: 'degraded'
# Reason: low_char_count (1200)
```

### Example 4: Failed

```python
extraction = {
    'pages_total': 10,
    'pages_with_text': 0,
    'chars_total': 0,
    'ocr_used': False,
    'errors': ['All methods failed'],
    'method_used': 'failed'
}

score, status = compute_extraction_quality(extraction)
# score: 0, status: 'failed'
```

---

## API Usage

### Compute Quality from Metadata

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
print(f"Quality: {score}/100, Status: {status}")
```

### Check Status in Summary JSON

```python
import json
from path_manager import get_path_manager

pm = get_path_manager()
json_path = pm.artifact_path("BOA_Report_20260212_w", "sum.json")

with open(json_path, 'r') as f:
    summary = json.load(f)

meta = summary['meta']
extraction = meta['extraction']

print(f"Status: {extraction['status']}")
print(f"Quality: {extraction['extraction_quality_0_100']}")
print(f"Low confidence: {meta.get('low_confidence', False)}")
```

---

## Testing

### Run Tests

```bash
python test_extraction_quality.py
```

### Test Coverage

✅ Excellent quality (high score)  
✅ Good quality (medium score)  
✅ Degraded: low character count  
✅ Degraded: low page coverage  
✅ Degraded: OCR penalty  
✅ Degraded: multiple errors  
✅ Failed: complete failure  
✅ Failed: insufficient chars  
✅ Failed: critical errors  
✅ Score clamping (0-100)  
✅ Edge cases (no pages, etc.)  

---

## Monitoring & Debugging

### Check Quality Distribution

```python
from path_manager import get_path_manager
import json

pm = get_path_manager()
artifacts = pm.list_artifacts_with_summaries()

quality_distribution = {'ok': 0, 'degraded': 0, 'failed': 0, 'unknown': 0}
scores = []

for art in artifacts:
    json_path = pm.artifact_path(art['basename'], 'sum.json')
    if json_path.exists():
        with open(json_path, 'r') as f:
            summary = json.load(f)
        
        status = summary.get('meta', {}).get('extraction', {}).get('status', 'unknown')
        quality = summary.get('meta', {}).get('extraction', {}).get('extraction_quality_0_100')
        
        quality_distribution[status] += 1
        if quality is not None:
            scores.append(quality)

print("Status distribution:", quality_distribution)
print(f"Average quality: {sum(scores) / len(scores):.1f}")
```

### Find Degraded Summaries

```python
degraded_summaries = []

for art in artifacts:
    json_path = pm.artifact_path(art['basename'], 'sum.json')
    if json_path.exists():
        with open(json_path, 'r') as f:
            summary = json.load(f)
        
        meta = summary.get('meta', {})
        if meta.get('low_confidence') or meta.get('extraction', {}).get('status') == 'degraded':
            degraded_summaries.append({
                'basename': art['basename'],
                'reasons': meta.get('degradation_details', []),
                'quality': meta.get('extraction', {}).get('extraction_quality_0_100')
            })

print(f"Found {len(degraded_summaries)} degraded summaries")
for item in degraded_summaries[:10]:
    print(f"  {item['basename']}: quality={item['quality']}, reasons={item['reasons']}")
```

---

## Troubleshooting

### Issue: Too many degraded summaries

**Cause:** Thresholds too strict for your content

**Fix:** Adjust thresholds in `summarize_pdf.py`:
```python
QUALITY_DEGRADED_CHARS = 1000  # Lower from 1500
QUALITY_DEGRADED_PAGE_RATIO = 0.3  # Lower from 0.4
```

### Issue: OCR penalty too harsh

**Cause:** OCR_QUALITY_PENALTY = 20 may be too high

**Fix:** Reduce penalty:
```python
OCR_QUALITY_PENALTY = 10  # Reduce from 20
```

### Issue: Failed summaries showing in feed

**Cause:** Filter logic not working

**Fix:** Check filter in `twifo.py`:
```python
if extraction_status == 'failed':
    continue  # Should skip failed summaries
```

---

## Benefits

### 1. **Transparency**
- Users know when extraction quality is low
- Clear warning badges prevent misinterpretation

### 2. **Quality Control**
- Failed extractions filtered from main feed
- Degraded extractions flagged for review

### 3. **Debugging**
- Quality score helps diagnose extraction issues
- Degradation reasons pinpoint problems

### 4. **Accountability**
- All quality metrics logged in metadata
- Deterministic scoring (no subjective judgment)

---

## Integration

### Pipeline Flow

```
1. Extract text (with caching)
   └─> Compute quality_score and status

2. Save to cache
   └─> Include quality_score in extraction.json

3. Generate summary
   └─> Add low_confidence flag if degraded

4. Render PDF
   └─> Show warning banner if degraded

5. Display in UI
   └─> Show ⚠️ icon if degraded
   └─> Hide if failed
```

---

## Metadata Structure

### In sum.json

```json
{
  "schema_version": "twifo.sum.v1",
  "meta": {
    "low_confidence": true,
    "low_confidence_reason": "degraded_extraction",
    "degradation_details": [
      "low_page_coverage (0.3)",
      "low_char_count (1234)"
    ],
    "extraction": {
      "status": "degraded",
      "extraction_quality_0_100": 35,
      "pages_total": 10,
      "pages_with_text": 3,
      "chars_total": 1234,
      "ocr_used": false,
      "method_used": "pypdf",
      "errors": [],
      "degradation_reasons": [
        "low_page_coverage (30.0%)",
        "low_char_count (1234)"
      ]
    }
  }
}
```

### In extraction.json (cache)

```json
{
  "pdf_sha256": "abc123...",
  "method_used": "pypdf",
  "status": "degraded",
  "extraction_quality_0_100": 35,
  "pages_total": 10,
  "pages_with_text": 3,
  "chars_total": 1234,
  "ocr_used": false,
  "errors": [],
  "created_at": "2026-02-12T10:30:00",
  "duration_ms": 245
}
```

---

## Status Determination Logic

### Detailed Rules

```python
def determine_extraction_status(extraction_meta, quality_score):
    # FAILED: Complete extraction failure
    if method_used == 'failed':
        return 'failed'
    
    if chars_total < 100:
        return 'failed'
    
    if has_critical_errors(errors):  # corrupt, unreadable, invalid
        return 'failed'
    
    # DEGRADED: Low quality but usable
    degraded_reasons = []
    
    # Rule 1: Low page coverage
    if pages_with_text / pages_total < 0.4:
        degraded_reasons.append(f"low_page_coverage ({ratio:.1%})")
    
    # Rule 2: Insufficient text
    if chars_total < 1500:
        degraded_reasons.append(f"low_char_count ({chars_total})")
    
    # Rule 3: Low quality score
    if quality_score < 40:
        degraded_reasons.append(f"low_quality_score ({quality_score})")
    
    # Rule 4: Multiple errors
    if len(errors) >= 2:
        degraded_reasons.append(f"multiple_errors ({len(errors)})")
    
    if degraded_reasons:
        extraction_meta['degradation_reasons'] = degraded_reasons
        return 'degraded'
    
    # OK: Good quality
    return 'ok'
```

---

## Quality Scenarios

### Scenario Matrix

| Pages with Text | Chars | OCR | Errors | Score | Status |
|-----------------|-------|-----|--------|-------|--------|
| 10/10 (100%) | 15,000 | No | 0 | **80** | ✅ ok |
| 8/10 (80%) | 7,000 | No | 0 | **67** | ✅ ok |
| 10/10 (100%) | 5,000 | Yes | 0 | **50** | ✅ ok |
| 3/10 (30%) | 5,000 | No | 0 | **52** | ⚠️ degraded |
| 10/10 (100%) | 1,200 | No | 0 | **53** | ⚠️ degraded |
| 5/5 (100%) | 3,000 | Yes | 2 | **30** | ⚠️ degraded |
| 0/10 (0%) | 0 | Yes | 3 | **0** | ❌ failed |

---

## Best Practices

### 1. **Monitor Quality Distribution**

Track how many summaries are degraded:
- **Target:** < 10% degraded
- **Alert:** > 20% degraded (investigate extraction setup)

### 2. **Review Degraded Summaries**

Periodically review degraded summaries to:
- Identify patterns (certain providers, date ranges)
- Adjust thresholds if needed
- Improve extraction methods

### 3. **Don't Over-Tune**

Resist temptation to lower thresholds just to reduce warnings:
- Degraded flag is valuable signal to users
- Better to improve extraction than hide quality issues

### 4. **Track OCR Usage**

Monitor `ocr_used` percentage:
- **Normal:** 5-10% of PDFs need OCR
- **High:** > 20% OCR usage may indicate extraction problems

---

## Testing

### Comprehensive Test Suite

```bash
python test_extraction_quality.py
```

**Test cases:**
- ✅ Excellent quality scoring
- ✅ Good quality scoring
- ✅ Degraded: low chars
- ✅ Degraded: low page coverage
- ✅ Degraded: OCR penalty
- ✅ Degraded: multiple errors
- ✅ Failed: complete failure
- ✅ Failed: insufficient chars
- ✅ Failed: critical errors
- ✅ Score clamping (0-100)
- ✅ Threshold edge cases
- ✅ Scoring components

---

## Related Features

This feature builds on:
- **File Layout** - Uses artifacts/ structure
- **Extraction Caching** - Quality metrics saved to cache
- **Path Manager** - Organizes quality metadata

---

## Documentation

- `EXTRACTION_QUALITY.md` - This file (full documentation)
- `test_extraction_quality.py` - Test examples
- `FILE_LAYOUT.md` - Directory structure
- `EXTRACTION_CACHE.md` - Caching system

---

## Success Metrics

✅ **Objective quality scoring** - Deterministic 0-100 scale  
✅ **Three-tier status** - ok, degraded, failed  
✅ **Failed summaries filtered** - Not published to main feed  
✅ **Degraded summaries flagged** - Warning badge in UI and PDF  
✅ **Rich metadata** - Full provenance in JSON  
✅ **Comprehensive tests** - 12+ test cases  
✅ **Full documentation** - Complete usage guide  

---

**Status:** ✅ Implemented and Tested  
**Production Ready:** ✅ Yes  
**Backward Compatible:** ✅ Yes
