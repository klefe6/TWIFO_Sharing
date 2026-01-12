# Quick Reference: Option B Summaries

## Generate a Summary

```bash
cd "C:\Program Files\Coding Projects\TWIFO_Sharing"
python test_summarize_one.py
```

**What happens:**
1. Extracts text (with OCR fallback if needed)
2. Generates Option B JSON (meta + scan + deep_dive)
3. Creates __sum.pdf automatically
4. Shows extraction quality and scores

---

## JSON Structure Quick View

```json
{
  "meta": {...},           // Source, firm, date, extraction details
  "scan": {                // Quick view
    "tldr": [...],
    "top_actionables": [...],
    "score": {
      "summary_score_0_10": 7,
      "chart_score_0_3": 2,
      "why": "..."
    }
  },
  "deep_dive": {           // Detailed analysis
    "topic_map": [...],
    "cross_asset_impacts": [...],
    "scenarios": [...],
    "appendix_extra_insights": [...]
  }
}
```

---

## UI Features

### View Summaries
- Click "📄 View" to open PDF summary
- PDF auto-generates from JSON if missing
- Scores color-coded: 0-2=red, 3-4=orange, 5=yellow, 6-7=green, 8-10=dark green

### Indicators
- `[!] OCR was used` - Text extracted via OCR
- `[!] Text extraction failed` - PDF couldn't be read
- Score + "why" explanation shown in PDF

---

## Backward Compatibility

✅ **Old summaries still work:**
- Old JSON files display correctly
- Old PDFs open normally
- Scores read from either format
- No migration needed

---

## Troubleshooting

### Summary score shows 0
- Check `extraction.errors` in JSON
- Check `extraction_quality_0_100` score
- If < 50, text extraction was poor

### PDF won't generate
- Ensure `reportlab` installed
- Check JSON is valid
- Check console for errors

### OCR not working
- Install: `pip install ocrmypdf`
- Or: `pip install pytesseract pdf2image`
- System still works without OCR (fails gracefully)

---

## Key Files

- `__sum.json` - Source of truth (Option B schema)
- `__sum.pdf` - Professional PDF (auto-generated)
- `.ocr_cache/` - OCR results cache

---

## Tuneable Settings

**In summarize_pdf.py:**
- `MAX_INPUT_CHARS = 50000` - Text length limit
- `MAX_OUTPUT_TOKENS = 900` - AI output limit
- `MAX_PAGES_TO_SCAN = 12` - Pages to extract
- `OCR_MIN_CHAR_COUNT = 1500` - OCR trigger

Lower = more aggressive OCR, faster but may miss content  
Higher = less aggressive OCR, slower but more thorough

---

## Common Tasks

### Regenerate PDF from JSON
```python
from pathlib import Path
from summarize_pdf import ensure_summary_pdf
ensure_summary_pdf(Path("path/to/original.pdf"))
```

### Check extraction quality
```python
import json
with open("file__sum.json") as f:
    s = json.load(f)
    print(f"Quality: {s['meta']['extraction']['extraction_quality_0_100']}/100")
    print(f"Method: {s['meta']['extraction']['method']}")
    print(f"Errors: {s['meta']['extraction']['errors']}")
```

### Force OCR on specific file
```python
from pathlib import Path
from summarize_pdf import extract_text_with_fallback
text, status, metrics = extract_text_with_fallback(Path("file.pdf"))
print(f"Status: {status}, Chars: {metrics['char_count']}")
```

---

## Best Practices

1. **Let OCR decide:** Trust the preflight check
2. **Check scores:** Low scores (<3) may need review
3. **Review "why":** Score explanation shows what worked/didn't
4. **Monitor errors:** Check extraction.errors field
5. **Cache is your friend:** Don't delete .ocr_cache/ unless needed

---

## Performance Notes

- Text-based PDFs: ~2-5 seconds
- Image-based PDFs (first time): ~30-120 seconds
- Image-based PDFs (cached): ~1-2 seconds
- Smart truncation: Handles docs up to ~100k chars

---

**Last Updated:** 2026-01-10  
**Phase 4 (Daily/Weekly Rollups):** On hold

