"""
Audit summarization pipeline: prove whether LLM receives real article text.
Purpose: Run 2 different articles with DEV_LOGGING=1 and compare input_text hashes/counts.
Usage: set DEV_LOGGING=1 then run:
   python audit_summary_inputs.py path/to/article1.pdf path/to/article2.pdf
Or:    python -c "import os; os.environ['DEV_LOGGING']='1'; exec(open('audit_summary_inputs.py').read())" -- pdf1 pdf2
Author: Kevin Lefebvre
Last Updated: 2026-02-05
"""

import os
import re
import sys
from pathlib import Path


def _run_one_and_capture_dev_logs(pdf_path: Path) -> dict:
    """Run summarize_pdf on one PDF with DEV_LOGGING=1; parse stdout for [DEV_LOGGING] lines."""
    import io
    from contextlib import redirect_stdout

    os.environ["DEV_LOGGING"] = "1"
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            from summarize_pdf import summarize_pdf

            result, json_path = summarize_pdf(Path(pdf_path), allow_ocr=False)
    except Exception as e:
        buf.write(f"[EXCEPTION] {e}\n")
    out = buf.getvalue()

    # Parse [DEV_LOGGING] lines (use first occurrence; retries use same input_text)
    article_id = ""
    input_len = None
    input_sha256 = ""
    user_prompt_len = None
    first_200 = ""

    m = re.search(
        r"\[DEV_LOGGING\] article_id=(.+?) \| input_text_len=(\d+) \| "
        r"input_sha256=([a-f0-9]+) \| user_prompt_len=(\d+)",
        out,
    )
    if m:
        article_id = m.group(1).strip("'\"")
        input_len = int(m.group(2))
        input_sha256 = m.group(3)
        user_prompt_len = int(m.group(4))

    m2 = re.search(r"\[DEV_LOGGING\] input_text_first_200=(.+)", out)
    if m2:
        first_200 = m2.group(1).strip().strip("'\"")[:200]

    return {
        "article_id": article_id,
        "input_text_len": input_len,
        "input_sha256": input_sha256,
        "user_prompt_len": user_prompt_len,
        "first_200": first_200,
        "raw_stdout": out,
    }


def main():
    if len(sys.argv) < 3:
        print(
            "Usage: set DEV_LOGGING=1 (optional, script sets it); then:\n"
            "  python audit_summary_inputs.py <article1.pdf> <article2.pdf>"
        )
        sys.exit(1)

    p1, p2 = Path(sys.argv[1]), Path(sys.argv[2])
    for p in (p1, p2):
        if not p.exists():
            print(f"[ERROR] Not found: {p}")
            sys.exit(2)

    os.environ["DEV_LOGGING"] = "1"

    print("Running article 1...")
    log1 = _run_one_and_capture_dev_logs(p1)
    print("Running article 2...")
    log2 = _run_one_and_capture_dev_logs(p2)

    # Comparison report
    print("\n" + "=" * 70)
    print("AUDIT REPORT: Input text passed to LLM")
    print("=" * 70)
    print(f"Article 1: {log1['article_id']!r}")
    print(f"  input_text_len={log1['input_text_len']}, input_sha256={log1['input_sha256']}, user_prompt_len={log1['user_prompt_len']}")
    print(f"  first_200: {log1['first_200'][:120]!r}...")
    print()
    print(f"Article 2: {log2['article_id']!r}")
    print(f"  input_text_len={log2['input_text_len']}, input_sha256={log2['input_sha256']}, user_prompt_len={log2['user_prompt_len']}")
    print(f"  first_200: {log2['first_200'][:120]!r}...")
    print()
    print("Comparison:")
    hashes_differ = log1["input_sha256"] != log2["input_sha256"]
    lens_ok = (log1["input_text_len"] or 0) > 500 and (log2["input_text_len"] or 0) > 500
    print(f"  input_sha256 differ? {hashes_differ}")
    print(f"  both input_text_len > 500? {lens_ok}")
    # Root cause category
    if not hashes_differ and (log1["input_text_len"] or 0) == 0 and (log2["input_text_len"] or 0) == 0:
        print("  >>> ROOT CAUSE A: input_text not passed / empty.")
    elif not hashes_differ:
        print("  >>> ROOT CAUSE B or C: same input (wrong variable or cached result).")
    elif not lens_ok:
        print("  >>> ROOT CAUSE A: input empty or near-zero (not passed or truncated).")
    else:
        print("  >>> Inputs differ and substantial; if PDFs still look identical, ROOT CAUSE D: post-processing/template.")


if __name__ == "__main__":
    main()
