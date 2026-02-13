# Summarization pipeline audit: LLM input proof

## Exact files and functions

| Role | File | Function |
|------|------|----------|
| **Payload construction** | `TWIFO_Sharing/summarize_pdf.py` | `llm_summarize_to_json(text, meta, ...)` (lines ~867–932) |
| **Prompt template** | `TWIFO_Sharing/twifo_prompts/prompts/article_prompts.py` | `USER_PROMPT`, `DOCUMENT_PLACEHOLDER` (`<<<PLACEHOLDER>>>`) |
| **User prompt build** | `summarize_pdf.py` | `user_prompt = article_prompts.USER_PROMPT.replace(article_prompts.DOCUMENT_PLACEHOLDER, text)` |
| **Entry (PDF)** | `summarize_pdf.py` | `summarize_pdf(pdf_path)` → `extract_text(pdf_path)` → `_summarize_with_quality_retry(text, meta, ...)` |
| **Entry (text)** | `summarize_pdf.py` | `summarize_text(text, ...)` → `_summarize_with_quality_retry(text, meta, ...)` |
| **LLM call** | `summarize_pdf.py` | `_summarize_with_quality_retry` → `llm_summarize_to_json(text, meta, ...)` (same `text` passed through) |
| **Extraction** | `summarize_pdf.py` | `extract_text(pdf_path)` (pypdf / pdfplumber / pymupdf); no cache in this path |

## DEV_LOGGING (guard: `DEV_LOGGING=1`)

When `DEV_LOGGING=1`, `llm_summarize_to_json` prints:

- `article_id` / filename (from `meta["title"]`)
- `input_text_len` (character count)
- `input_sha256` (sha256 of `text` passed to the LLM)
- `user_prompt_len` (final user message length)
- `input_text_first_200` (first 200 chars of `text`, single line)

## How to run the audit

```bash
cd TWIFO_Sharing
set DEV_LOGGING=1
python audit_summary_inputs.py "path\to\article1.pdf" "path\to\article2.pdf"
```

Or run two single-PDF runs and compare logs manually:

```bash
set DEV_LOGGING=1
python smoke_test_pdf.py article1.pdf
python smoke_test_pdf.py article2.pdf
```

## Note on "Products: ES, NQ, ZN, ZB, GC, SI, BTC, VIX, CL"

The pipeline **always** renders that product list: in `summarize_pdf.py` (lines 1012–1061) the code iterates over a fixed `product_order` and, for any product missing from the LLM response, **injects a default entry** (`"catalyst": "No direct trade idea from this article"`). So identical product lists across articles are expected; the question is whether the **bullets and ACTIONABLE content** differ. DEV_LOGGING proves whether the LLM receives different input text.

## How to interpret (root cause categories)

| Evidence | Conclusion |
|----------|------------|
| **input_sha256 identical** for two different articles | **B** (wrong variable / same string) or **C** (cached result). No caching in `summarize_pdf.py`; check callers (e.g. `db_filter_autorun`) for wrong or reused text. |
| **input_text_len** near zero or both 0 | **A**: input_text not passed or empty (extraction failed or wrong arg). |
| **input_sha256 differ**, **input_text_len** reasonable (>500) | Inputs are different and substantial. If generated PDFs/summaries still identical → **D**: post-processing or template injection (e.g. ACTIONABLE/products filled from template). |

## Evidence to report after running

After running on 2 very different articles, report:

1. Article 1: `article_id`, `input_text_len`, `input_sha256`, `user_prompt_len`, and whether first 200 chars look like real article text.
2. Article 2: same.
3. Do the two `input_sha256` values differ? Y/N.
4. Are both `input_text_len` values reasonable (e.g. >500)? Y/N.
5. Root cause category: **A** / **B** / **C** / **D** (per table above).
