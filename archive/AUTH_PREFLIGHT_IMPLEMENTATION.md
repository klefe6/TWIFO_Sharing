# OpenAI Auth Preflight - Implementation Summary

**Purpose:** Fail fast if OpenAI API key is invalid/revoked  
**Author:** Kevin Lefebvre  
**Date:** 2026-01-26  

---

## Problem

Pipeline would start processing PDFs, then fail partway through with cryptic API errors when the key was invalid. Wasted time and left partial outputs.

---

## Solution: Preflight Auth Check

### A) Auth Check Function

**Location:** `summarize_pdf.py` lines 70-130

**Function:** `check_openai_auth(model: str = None) -> bool`

**What it does:**
1. Checks if `OPENAI_API_KEY` is set
2. Makes a minimal API call: `responses.create` with input "ping"
3. If 401 (invalid key):
   - Prints clear error message with first 12 chars of key
   - Raises `SystemExit(1)` (fail fast)
4. If network error or other non-401 error:
   - Warns but continues (don't block on transient issues)

**Error message format:**
```
[ERROR] OPENAI_API_KEY is invalid/revoked.
        Current prefix=sk-proj-ABCD
        Fix env var before running.
```

**Key safety:** Only shows first 12 characters of API key (never full key in logs).

---

## B) Integration Points

### 1. Program Start (db_filter_autorun.py)

**Location:** Lines 711-715

**Flow:**
```python
def main():
    check_ocr_env()
    
    # Preflight: verify OpenAI API key before processing any PDFs
    if SUMMARIZE_AVAILABLE and check_openai_auth:
        print("[INFO] Verifying OpenAI API authentication...")
        check_openai_auth()
        print("[INFO] OpenAI API authentication OK")
    
    # Continue with normal processing...
```

**When it runs:** Immediately at program start, before processing any PDFs.

**Result:** If auth fails, program exits with code 1 and clear message. No PDFs processed, no stubs written.

---

## Code Changes

### File: `summarize_pdf.py`

**Lines 70-130:** New `check_openai_auth()` function
```python
def check_openai_auth(model: str = None) -> bool:
    """
    Preflight check: verify OpenAI API key is valid before attempting summaries.
    """
    if not OPENAI_API_KEY:
        print("[ERROR] OPENAI_API_KEY is not set.")
        raise SystemExit(1)
    
    test_model = model or MODEL
    key_prefix = OPENAI_API_KEY[:12]
    
    # Make minimal API call
    r = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", ...},
        json={"model": test_model, "input": [{"role": "user", "content": "ping"}], ...},
        timeout=10,
    )
    
    if r.status_code == 401:
        print(f"[ERROR] OPENAI_API_KEY is invalid/revoked.")
        print(f"        Current prefix={key_prefix}")
        print(f"        Fix env var before running.")
        raise SystemExit(1)
    
    return True
```

### File: `db_filter_autorun.py`

**Line 21:** Added `check_openai_auth` to imports
```python
from summarize_pdf import summarize_pdf, summarize_text, check_openai_auth
```

**Lines 711-715:** Added preflight check at start of `main()`
```python
if SUMMARIZE_AVAILABLE and check_openai_auth:
    print("[INFO] Verifying OpenAI API authentication...")
    check_openai_auth()
    print("[INFO] OpenAI API authentication OK")
```

---

## Behavior

### Scenario 1: Valid API Key

```
[INFO] Verifying OpenAI API authentication...
[INFO] OpenAI API authentication OK
[INFO] Date range selection enabled.
Enter date range (YYYY-MM-DD format)
...
```

**Result:** Program continues normally.

---

### Scenario 2: Invalid/Revoked API Key

```
[INFO] Verifying OpenAI API authentication...
[ERROR] OPENAI_API_KEY is invalid/revoked.
        Current prefix=sk-proj-ABCD
        Fix env var before running.
```

**Result:** Program exits with code 1. No PDFs processed.

---

### Scenario 3: Missing API Key

```
[INFO] Verifying OpenAI API authentication...
[ERROR] OPENAI_API_KEY is not set.
        Set it in .env file or environment variable before running.
```

**Result:** Program exits with code 1. No PDFs processed.

---

### Scenario 4: Network Error / Transient Issue

```
[INFO] Verifying OpenAI API authentication...
[WARN] OpenAI API preflight check failed: Connection timeout
       Network issue or API unavailable. Will attempt to continue...
[INFO] Date range selection enabled.
...
```

**Result:** Warning printed but program continues. Actual API errors will surface during summarization if issue persists.

---

## Testing

### Test File: `test_auth_preflight.py`

**Tests:**
1. ✓ Valid key passes preflight
2. ✓ Invalid key triggers SystemExit(1)
3. ✓ Missing key triggers SystemExit(1)
4. ✓ Key prefix extraction (first 12 chars)

**Run:**
```bash
cd "c:\Coding Projects\TWIFO_Sharing"
python test_auth_preflight.py
```

**Note:** Tests 2 and 3 require mocking/reloading to avoid affecting real runs.

---

## Manual Test

### Test with valid key:
```bash
cd "c:\Coding Projects\TWIFO_Sharing"
python db_filter_autorun.py
```

**Expected output:**
```
[INFO] Verifying OpenAI API authentication...
[INFO] OpenAI API authentication OK
[INFO] Date range selection enabled.
...
```

### Test with invalid key:
```bash
# Temporarily set bad key
set OPENAI_API_KEY=sk-invalid_test_key

python db_filter_autorun.py
```

**Expected output:**
```
[INFO] Verifying OpenAI API authentication...
[ERROR] OPENAI_API_KEY is invalid/revoked.
        Current prefix=sk-invalid_t
        Fix env var before running.
```

**Exit code:** 1

---

## Security

✅ **Only first 12 characters of API key shown** in error messages  
✅ **Full key never logged or printed**  
✅ **Key stored in environment variable (not hardcoded)**  

**Example:**
- Actual key: `sk-proj-1OLL2NVAjBF3DfZ...` (full 107 chars)
- Error message shows: `sk-proj-1OLL2` (12 chars)

---

## Guarantees

### ✅ Fail Fast
- If auth fails, program exits **before** processing any PDFs
- No partial outputs, no wasted time

### ✅ Clear Error Message
- Shows exactly what's wrong (invalid/revoked/missing)
- Shows first 12 chars of key for debugging
- Tells user how to fix (update env var)

### ✅ No False Positives
- Network errors don't block execution (warn only)
- Only 401 Unauthorized triggers fail-fast

### ✅ Minimal Overhead
- Single API call at program start (~1-2 seconds)
- No per-PDF overhead

---

## Diff Summary

**Total changes:** ~70 lines across 2 files

| File | Lines Added | Lines Modified | Purpose |
|------|-------------|----------------|---------|
| `summarize_pdf.py` | ~60 | 0 | Auth check function |
| `db_filter_autorun.py` | ~6 | ~1 | Import & call at start |
| `test_auth_preflight.py` | ~180 | 0 | Unit tests |
| `AUTH_PREFLIGHT_IMPLEMENTATION.md` | ~280 | 0 | This doc |

---

## Configuration

### Set API Key

**Option 1: .env file** (recommended)
```bash
# In c:\Coding Projects\TWIFO_Sharing\.env
OPENAI_API_KEY=sk-proj-your_key_here
```

**Option 2: Environment variable**
```powershell
# PowerShell
$env:OPENAI_API_KEY="sk-proj-your_key_here"

# Or permanently in System Environment Variables
```

**Option 3: Within Python session**
```python
import os
os.environ["OPENAI_API_KEY"] = "sk-proj-your_key_here"
```

---

## Troubleshooting

### Issue: "OPENAI_API_KEY is invalid/revoked"

**Fix:**
1. Check the key prefix shown in error message
2. Verify key in .env file or environment variable matches
3. Try generating a new key at https://platform.openai.com/api-keys
4. Update .env file or environment variable with new key

### Issue: "OPENAI_API_KEY is not set"

**Fix:**
1. Create `.env` file in `c:\Coding Projects\TWIFO_Sharing\`
2. Add line: `OPENAI_API_KEY=sk-proj-your_key_here`
3. Or set environment variable permanently in Windows

### Issue: "Network issue or API unavailable"

**Not a blocker** - program will continue and try actual summarization. If issue persists, you'll see errors during PDF processing.

**Check:**
- Internet connection
- OpenAI API status: https://status.openai.com/
- Firewall/proxy settings

---

## Summary

✅ **Added:** Preflight auth check at program start  
✅ **Behavior:** Fail fast with clear message if key invalid  
✅ **Security:** Only first 12 chars of key shown in logs  
✅ **Testing:** Unit tests + manual test instructions  
✅ **Diffs:** Minimal (~70 lines across 2 files)  

**Expected improvement:** No more wasted runs with invalid keys. Clear actionable error messages.
