# Single Source-of-Truth for OpenAI Auth - Implementation

**Purpose:** Prevent silent credential overrides with clear precedence hierarchy  
**Author:** Kevin Lefebvre  
**Date:** 2026-01-26  

---

## Problem

Multiple modules (`db_filter_autorun.py`, `summarize_pdf.py`, `summarize_pdf_new.py`) were independently reading `.env` files and environment variables, leading to:
- Silent overrides (unclear which source was used)
- Inconsistent behavior across modules
- Hard-to-debug authentication issues

---

## Solution: Centralized Auth Module

### New Module: `auth_env.py`

**Single source-of-truth** for loading OpenAI credentials with clear precedence.

#### Function 1: `get_openai_api_key() -> str`

**Priority (strict order):**
1. `.env` file in repo root (if present and contains non-empty `OPENAI_API_KEY`)
2. `os.environ['OPENAI_API_KEY']` (if set and non-empty)
3. Raise `SystemExit(1)` with clear error

**Returns:** API key string

**Raises:** `SystemExit(1)` if no valid key found

#### Function 2: `describe_key(key: str) -> str`

**Purpose:** Safe logging of API keys (first 12 chars + "…")

**Examples:**
- `sk-proj-1234567890AB` → `sk-proj-1234…`
- `sk-12` → `sk-1…`
- Empty → `<empty>`

#### Function 3: `assert_openai_auth_ok(model: str) -> None`

**Purpose:** Verify API key with OpenAI before processing

**Behavior:**
- Makes minimal API call: `responses.create(input="ping")`
- On 401 invalid_api_key: `SystemExit(1)` with message showing key prefix
- On other errors: `SystemExit(1)` with exception string
- On success: Returns normally

---

## Integration

### 1. `db_filter_autorun.py` (Lines 19-30, 711-738)

**At program start (before any processing):**

```python
# Step 1: Load API key (single source-of-truth)
api_key = get_openai_api_key()
source = ".env file" or "environment variable"  # detected
os.environ['OPENAI_API_KEY'] = api_key  # Set for child modules
print(f"[INFO] API key loaded from {source} (prefix={describe_key(api_key)})")

# Step 2: Verify authentication
base_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
assert_openai_auth_ok(base_model)
print("[INFO] OpenAI API authentication OK")
```

**Output example:**
```
[INFO] API key loaded from .env file (prefix=sk-proj-OKnM…)
[INFO] Verifying OpenAI API authentication...
[INFO] OpenAI API authentication OK
```

### 2. `summarize_pdf.py` (Lines 29-33)

**Simplified to read from `os.environ` only:**

```python
# Load API key from environment (set by db_filter_autorun.py)
# Note: Do NOT read .env directly here to avoid silent overrides
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
```

**Removed:**
- `load_api_key()` function (~40 lines)
- `load_dotenv()` calls
- Direct `.env` file reading
- `check_openai_auth()` function (replaced by `auth_env.assert_openai_auth_ok`)

### 3. `summarize_pdf_new.py` (Lines 25-28)

**Same simplification as `summarize_pdf.py`**

---

## Testing: `test_key_source_precedence.py`

### Test 1: .env File Precedence
```python
# Setup:
.env file:    OPENAI_API_KEY=sk-env-file-key-...
os.environ:   OPENAI_API_KEY=sk-process-env-key-...

# Result:
get_openai_api_key() returns sk-env-file-key-...  # .env wins
```

**✅ PASSED:** .env file takes precedence over environment

### Test 2: Process Environment Fallback
```python
# Setup:
.env file:    (absent)
os.environ:   OPENAI_API_KEY=sk-process-env-key-...

# Result:
get_openai_api_key() returns sk-process-env-key-...  # fallback works
```

**✅ PASSED:** Process environment used when .env absent

### Test 3: No Silent Override
```python
# Setup:
os.environ['OPENAI_API_KEY'] = "sk-set-by-main-..."
from summarize_pdf import OPENAI_API_KEY

# Result:
OPENAI_API_KEY == "sk-set-by-main-..."  # No override
```

**✅ PASSED:** summarize_pdf respects os.environ key

### Test 4: describe_key Safety
```python
describe_key("sk-proj-1234567890AB...") == "sk-proj-1234…"
describe_key("sk-12") == "sk-1…"
describe_key("") == "<empty>"
```

**✅ PASSED:** Safe truncation for logging

---

## Precedence Hierarchy (Visual)

```
┌─────────────────────────────────────┐
│ 1. .env file (if exists + non-empty) │  ◄── HIGHEST PRIORITY
├─────────────────────────────────────┤
│ 2. os.environ (if set + non-empty)   │
├─────────────────────────────────────┤
│ 3. SystemExit(1) with clear error    │  ◄── LOWEST PRIORITY
└─────────────────────────────────────┘

Flow:
db_filter_autorun.py (program start)
    ↓
get_openai_api_key()  ← Reads from .env or os.environ
    ↓
os.environ['OPENAI_API_KEY'] = key  ← Sets for all modules
    ↓
assert_openai_auth_ok(model)  ← Verifies with OpenAI
    ↓
summarize_pdf.py  ← Reads from os.environ only
summarize_pdf_new.py  ← Reads from os.environ only
```

---

## Benefits

### ✅ No Silent Overrides
- Only one place reads `.env` file: `auth_env.py`
- All other modules read from `os.environ` (set by `db_filter_autorun.py`)
- Clear logging shows which source was used

### ✅ Clear Precedence
- `.env` > `os.environ` > error
- Documented and tested
- No ambiguity

### ✅ Fail Fast
- Authentication verified before any PDF processing
- Clear error messages with key prefix
- No wasted time on invalid keys

### ✅ Simplified Modules
- Removed ~40 lines of duplicate code from each summarize module
- Single import: `from auth_env import ...`
- Consistent behavior across all modules

---

## Code Changes Summary

| File | Lines Changed | Purpose |
|------|---------------|---------|
| `auth_env.py` | +140 (new) | Single source-of-truth |
| `db_filter_autorun.py` | +30, -10 | Load key at start, set os.environ |
| `summarize_pdf.py` | -100 | Removed load_api_key(), load_dotenv() |
| `summarize_pdf_new.py` | -40 | Same simplification |
| `test_key_source_precedence.py` | +220 (new) | Precedence tests |

**Total:** ~250 lines net change (added auth module, simplified others)

---

## How to Use

### Option 1: Set in .env file (Recommended)
```bash
# In c:\Coding Projects\TWIFO_Sharing\.env
OPENAI_API_KEY=sk-proj-your_key_here
OPENAI_MODEL=gpt-4o-mini
```

### Option 2: Set in environment
```powershell
# PowerShell
$env:OPENAI_API_KEY="sk-proj-your_key_here"

# Or permanently
setx OPENAI_API_KEY "sk-proj-your_key_here"
```

### Run Pipeline
```powershell
cd "c:\Coding Projects\TWIFO_Sharing"
python db_filter_autorun.py
```

**Expected output:**
```
[INFO] Loading OpenAI API key...
[INFO] API key loaded from .env file (prefix=sk-proj-OKnM…)
[INFO] Verifying OpenAI API authentication...
[INFO] OpenAI API authentication OK
[OCR ENV CHECK]
...
```

---

## Troubleshooting

### Issue: "OPENAI_API_KEY not found"

**Fix:**
1. Create `.env` file in `c:\Coding Projects\TWIFO_Sharing\`
2. Add line: `OPENAI_API_KEY=sk-proj-your_key_here`
3. Or set environment variable

### Issue: "OPENAI_API_KEY is invalid/revoked"

**Output example:**
```
[ERROR] OPENAI_API_KEY is invalid/revoked.
        Current prefix=sk-proj-y0AU…
        Fix env var before running.
```

**Fix:**
1. Check the key prefix shown
2. Verify key in `.env` or environment matches
3. Generate new key at https://platform.openai.com/api-keys
4. Update `.env` or environment

### Issue: "Which source is being used?"

**Check the log:**
```
[INFO] API key loaded from .env file (prefix=sk-proj-OKnM…)
```

The log clearly shows whether `.env file` or `environment variable` was used.

---

## Security

✅ **Only first 12 characters** shown in logs (via `describe_key()`)  
✅ **Full key never logged**  
✅ **Single source-of-truth** prevents leaks via multiple code paths  

**Example:**
- Actual key: `sk-proj-OKnMCkuQHQ1Px1JxKT6z...` (full 107 chars)
- Logged as: `sk-proj-OKnM…`

---

## Summary

**Before:**
- 3 modules independently reading `.env` files
- Silent overrides
- Unclear precedence
- Duplicate code

**After:**
- 1 centralized `auth_env.py` module
- Clear precedence: `.env` > `os.environ` > error
- Explicit logging of source
- Simplified code

**Result:**
- No more silent credential overrides
- Clear error messages
- Single place to debug auth issues
- Consistent behavior across all modules
