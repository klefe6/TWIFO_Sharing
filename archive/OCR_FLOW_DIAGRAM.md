# OCR Guardrail Extraction Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PDF SUMMARIZATION REQUEST                     │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  Should Skip?          │
                    │  (Chart Book check)    │
                    └───────┬────────────────┘
                            │
                 ┌──────────┴──────────┐
                 │                     │
                NO                    YES
                 │                     │
                 ▼                     ▼
    ┌────────────────────────┐   [SKIP - Return None]
    │  Preflight Check       │
    │  (Quality Analysis)    │
    └───────┬────────────────┘
            │
            ├─ Extract text from first N pages (PyPDF2)
            ├─ Compute metrics:
            │  • char_count
            │  • word_count
            │  • unique_word_ratio
            │  • alpha_ratio
            │  • pages_with_text
            │
            ▼
    ┌────────────────────────┐
    │  Quality Good Enough?  │
    └───────┬────────────────┘
            │
 ┌──────────┴──────────┐
 │                     │
YES                   NO
 │                     │
 │                     ▼
 │          ┌────────────────────────┐
 │          │  Check OCR Cache       │
 │          └───────┬────────────────┘
 │                  │
 │       ┌──────────┴──────────┐
 │       │                     │
 │     FOUND                NOT FOUND
 │       │                     │
 │       │                     ▼
 │       │          ┌────────────────────────┐
 │       │          │  Check OCR Tools       │
 │       │          │  Available?            │
 │       │          └───────┬────────────────┘
 │       │                  │
 │       │       ┌──────────┴──────────┐
 │       │       │                     │
 │       │      YES                   NO
 │       │       │                     │
 │       │       ▼                     ▼
 │       │  ┌────────────────┐   ┌────────────────┐
 │       │  │ Run OCR:       │   │ extraction_    │
 │       │  │ 1. ocrmypdf    │   │ status="failed"│
 │       │  │ 2. pytesseract │   │ reason="ocr_   │
 │       │  │                │   │  tool_missing" │
 │       │  └───────┬────────┘   └────────┬───────┘
 │       │          │                     │
 │       │          ▼                     │
 │       │  ┌────────────────┐           │
 │       │  │ OCR Succeeded? │           │
 │       │  └───────┬────────┘           │
 │       │          │                     │
 │       │    ┌─────┴─────┐              │
 │       │    │           │              │
 │       │   YES         NO              │
 │       │    │           │              │
 │       │    ▼           ▼              │
 │       │  [Cache]   [FAILED]           │
 │       │    │           │              │
 │       └────┴───────────┴──────────────┘
 │                      │
 │                      ▼
 │          ┌────────────────────────┐
 │          │  Re-analyze Quality    │
 │          └───────┬────────────────┘
 │                  │
 │       ┌──────────┴──────────┐
 │       │                     │
 │     GOOD                   BAD
 │       │                     │
 └───────┴─────────────────────┘
         │
         ▼
┌────────────────────────┐
│  Strip Boilerplate     │
└───────┬────────────────┘
        │
        ▼
┌────────────────────────┐         ┌────────────────────────┐
│  Send to OpenAI API    │         │  Create Failed Summary │
│  (Summarize)           │   OR    │  (score=0, failed flag)│
└───────┬────────────────┘         └────────┬───────────────┘
        │                                   │
        ▼                                   │
┌────────────────────────┐                 │
│  Parse AI Response     │                 │
└───────┬────────────────┘                 │
        │                                   │
        ▼                                   │
┌────────────────────────┐                 │
│  Add Extraction        │                 │
│  Metadata:             │                 │
│  • extraction_status   │                 │
│  • extraction_metrics  │                 │
└───────┬────────────────┘                 │
        │                                   │
        └───────────────┬───────────────────┘
                        │
                        ▼
               ┌────────────────────────┐
               │  Save __sum.json       │
               └───────┬────────────────┘
                       │
                       ▼
               ┌────────────────────────┐
               │  Generate __sum.pdf    │
               │  (with OCR indicator)  │
               └───────┬────────────────┘
                       │
                       ▼
               ┌────────────────────────┐
               │  Display in twifo.py   │
               │  (color by score)      │
               └────────────────────────┘


LEGEND:
━━━━━  Normal flow
- - -  Error/fallback path
[CAPS]  Terminal state
```

---

## Status Outcomes

| extraction_status | Meaning | UI Display |
|------------------|---------|------------|
| `"ok"` | Normal PyPDF2 extraction succeeded | Normal (colored by score) |
| `"ocr_used"` | OCR was needed and succeeded | Normal + orange "OCR used" notice |
| `"failed"` | Extraction failed (OCR unavailable or low quality) | Red (score=0) + red "extraction failed" notice |

---

## Threshold Decision Points

```
Preflight Triggers OCR if ANY:
├─ char_count < 1500
├─ word_count < 250
├─ pages_with_text / scanned_pages < 0.5
└─ alpha_ratio < 0.4

OCR Tool Priority:
1. ocrmypdf (best quality)
   └─ Requires: tesseract system binary
2. pytesseract + pdf2image (fallback)
   └─ Requires: tesseract + poppler system binaries
3. None available
   └─ Returns status="failed", reason="ocr_tool_missing"
```

---

## Cache Strategy

```
Cache Key = MD5(filepath + file_size + mtime)

On OCR Request:
├─ Compute cache key
├─ Check .ocr_cache/{key}.txt
│  ├─ Found? → Return cached text (instant)
│  └─ Not found? → Run OCR → Save to cache

Cache Invalidation:
├─ File modified (mtime changed)
├─ File size changed
└─ File moved (path changed)
→ New cache key computed → Re-run OCR
```

