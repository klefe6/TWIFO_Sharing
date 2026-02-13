"""Quick verification of benign error fix."""
from summarize_pdf import compute_extraction_quality

print("=== BENIGN ERROR FIX VERIFICATION ===\n")

scenarios = [
    {
        "name": "Good extraction (30k chars, 96% pages) + benign error",
        "meta": {
            "pages_total": 50,
            "pages_with_text": 48,
            "chars_total": 30000,
            "ocr_used": False,
            "errors": ["invalid xref table"],
            "method_used": "pypdf",
        },
        "expected": "degraded",
    },
    {
        "name": "Poor extraction (300 chars, 10% pages) + benign error",
        "meta": {
            "pages_total": 10,
            "pages_with_text": 1,
            "chars_total": 300,
            "ocr_used": False,
            "errors": ["invalid stream"],
            "method_used": "pypdf",
        },
        "expected": "failed",
    },
    {
        "name": "Good extraction + fatal error (corrupt)",
        "meta": {
            "pages_total": 50,
            "pages_with_text": 50,
            "chars_total": 30000,
            "ocr_used": False,
            "errors": ["PDF is corrupt"],
            "method_used": "pypdf",
        },
        "expected": "failed",
    },
]

all_pass = True
for s in scenarios:
    score, status = compute_extraction_quality(s["meta"])
    passed = status == s["expected"]
    all_pass = all_pass and passed
    
    print(f"{s['name']}:")
    print(f"  chars={s['meta']['chars_total']}, errors={s['meta']['errors']}")
    print(f"  Result: status={status}, score={score}")
    print(f"  Expected: {s['expected']}")
    print(f"  {'[PASS]' if passed else '[FAIL]'}\n")

print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
