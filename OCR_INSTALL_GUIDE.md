# OCR Dependencies Installation Guide

**Purpose:** Install OCR tools to enable automatic text extraction from image-based PDFs  
**Optional:** The system works without OCR tools (will fail gracefully with clear error messages)

---

## Quick Install (Recommended)

### Option A: ocrmypdf (Best Quality)

**Step 1: Install Python package**
```bash
pip install ocrmypdf
```

**Step 2: Install Tesseract OCR engine**

#### Windows
1. Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
2. Run installer (default location: `C:\Program Files\Tesseract-OCR`)
3. Add to PATH:
   - Right-click "This PC" → Properties → Advanced system settings
   - Environment Variables → System Variables → Path → Edit → New
   - Add: `C:\Program Files\Tesseract-OCR`
4. Restart terminal/IDE

**Verify installation:**
```bash
tesseract --version
ocrmypdf --version
```

---

### Option B: pytesseract + pdf2image (Fallback)

**Step 1: Install Python packages**
```bash
pip install pytesseract pdf2image
```

**Step 2: Install Tesseract OCR engine**
- Same as Option A above

**Step 3: Install Poppler (for pdf2image)**

#### Windows
1. Download from: https://github.com/oschwartz10612/poppler-windows/releases/
2. Extract to `C:\Program Files\poppler` (or any location)
3. Add to PATH:
   - Add `C:\Program Files\poppler\Library\bin` to PATH
4. Restart terminal/IDE

**Verify installation:**
```bash
tesseract --version
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
python -c "import pdf2image; print('pdf2image OK')"
```

---

## Testing After Installation

```bash
cd "C:\Program Files\Coding Projects\TWIFO_Sharing"
python test_ocr_guardrail.py
```

Expected output:
```
============================================================
Testing OCR Tool Availability
============================================================
ocrmypdf:    [OK] Available
pytesseract: [OK] Available
pdf2image:   [OK] Available
```

---

## Troubleshooting

### Issue: "tesseract is not installed or not in PATH"

**Solution:**
1. Verify Tesseract is installed:
   ```bash
   tesseract --version
   ```
2. If command not found, add Tesseract to PATH (see above)
3. Restart terminal/PowerShell/Cursor

---

### Issue: "ocrmypdf: command not found"

**Solution:**
```bash
pip install ocrmypdf
# Then verify:
ocrmypdf --version
```

---

### Issue: "Unable to get page count (poppler not found)"

**Solution:**
- Install Poppler (see Option B, Step 3)
- Add `poppler/Library/bin` to PATH
- Restart terminal

---

### Issue: OCR is very slow (>2 minutes per PDF)

**Solutions:**
1. Reduce pages scanned (in `summarize_pdf.py`):
   ```python
   MAX_PAGES_TO_SCAN = 6  # Default is 12
   ```

2. Use faster OCR settings (modify `_ocr_with_ocrmypdf()` in `summarize_pdf.py`):
   ```python
   cmd = [
       "ocrmypdf",
       "--fast-web-view",  # Add this flag
       "--optimize", "1",
       ...
   ]
   ```

3. Accept that OCR is inherently slow (but results are cached!)

---

## Do I Need OCR Tools?

### You DON'T need OCR if:
- ✅ All your PDFs are text-based (created from Word/LaTeX/etc.)
- ✅ You're okay with failed extraction for image-based PDFs
- ✅ You want to test the system first before installing dependencies

### You DO need OCR if:
- ❌ Some PDFs are scanned documents or image-based
- ❌ You see "extraction_status: failed" in JSON summaries
- ❌ You want 100% coverage (even for scanned PDFs)

---

## Performance Expectations

### Without OCR Tools
- Text-based PDFs: ~2-5 seconds (normal)
- Image-based PDFs: Failed with clear error (instant)

### With OCR Tools
- Text-based PDFs: ~2-5 seconds (same, OCR skipped)
- Image-based PDFs (first time): ~30-120 seconds (OCR runs)
- Image-based PDFs (cached): ~1-2 seconds (cached)

---

## Alternative: Cloud OCR (Not Implemented)

If local OCR is too slow or doesn't work, consider cloud options:

### Google Cloud Vision API
- Pros: Fast, accurate, handles 200+ languages
- Cons: Requires Google Cloud account, costs ~$1.50 per 1000 pages
- Docs: https://cloud.google.com/vision/docs/ocr

### AWS Textract
- Pros: Fast, integrated with AWS
- Cons: Requires AWS account, costs ~$1.50 per 1000 pages
- Docs: https://aws.amazon.com/textract/

### Azure Computer Vision
- Pros: Fast, integrated with Azure
- Cons: Requires Azure account, costs ~$1.00 per 1000 pages
- Docs: https://azure.microsoft.com/en-us/services/cognitive-services/computer-vision/

**Note:** Cloud OCR is NOT implemented in current version but could be added.

---

## Summary

**Recommended Path:**
1. Try the system WITHOUT OCR tools first
2. Monitor `extraction_status` in generated JSON files
3. If you see many `"failed"` statuses, install OCR tools
4. Use Option A (ocrmypdf) for best quality

**Minimal Install:**
```bash
pip install ocrmypdf
# Then install Tesseract system binary for your OS
```

**Full Install:**
```bash
pip install ocrmypdf pytesseract pdf2image
# Then install Tesseract + Poppler system binaries
```

---

## Questions?

See `OCR_GUARDRAIL_README.md` for full documentation.

Contact: Kevin Lefebvre  
Date: 2026-01-10

