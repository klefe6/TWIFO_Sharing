# Quality Gate Filler Extension

**Purpose:** Extended quality gate to catch filler placeholders and repeated bullets  
**Author:** Kevin Lefebvre  
**Date:** 2026-02-12  

## Overview

Enhanced the quality gate in `summarize_pdf.py` with two new detection mechanisms:
1. **Banned filler phrases** (case-insensitive)
2. **Section-level repetition** (2+ identical bullets within same section)

Both trigger retry with stronger model, and return stub with `low_quality_output:filler` reason if both attempts fail.

## Changes Made

### 1. Enhanced `is_low_quality_summary()` Function

**Location:** `summarize_pdf.py` (lines 529-638)

#### New Check: Banned Filler Phrases (Check 3)

```python
# Check 3: Banned filler phrases (case-insensitive)
banned_phrases = [
    "market data pending analysis",
    "monitor key levels and data releases",
]

for bullet in all_bullets:
    for phrase in banned_phrases:
        if phrase in bullet:
            return True, f"filler:banned_phrase: '{phrase}' found in bullet"
```

**Behavior:**
- Case-insensitive matching (bullets are normalized to lowercase)
- Fails immediately if any bullet contains a banned phrase
- Returns reason: `filler:banned_phrase: '<phrase>' found in bullet`

#### New Check: Section-Level Repetition (Check 2b)

```python
# Check 2b: Section-level repetition (2+ identical bullets within same section)
for section_name, bullets in section_bullets.items():
    if len(bullets) >= 2:
        bullet_counts = {}
        for bullet in bullets:
            bullet_counts[bullet] = bullet_counts.get(bullet, 0) + 1
        for bullet, count in bullet_counts.items():
            if count >= 2:
                return True, f"filler:repeated_bullets_in_{section_name}: '{bullet[:50]}...' appears {count} times"
```

**Behavior:**
- Checks each section independently for identical bullets
- Fails if any section contains 2+ exact duplicates
- Returns reason: `filler:repeated_bullets_in_<section>: '<bullet>' appears <count> times`

### 2. Updated Test Suite

#### test_quality_gate.py

Added 5 new tests (now 12 total):

1. **test_banned_phrase_market_data_pending()** - Detects "market data pending analysis"
2. **test_banned_phrase_monitor_key_levels()** - Detects "monitor key levels and data releases"
3. **test_banned_phrase_case_insensitive()** - Verifies case-insensitive matching
4. **test_section_level_repetition()** - Detects 2+ identical bullets in same section
5. **test_section_level_repetition_multiple_sections()** - Detects repetition across sections

#### test_quality_retry.py

Added 3 new tests (now 8 total):

1. **test_banned_phrase_triggers_retry()** - Verifies banned phrases trigger quality gate failure
2. **test_section_repetition_triggers_retry()** - Verifies repetition triggers quality gate failure
3. **test_filler_failure_reason_format()** - Verifies stub generation with filler reasons

## Integration with Retry Mechanism

The quality gate runs in `_summarize_with_quality_retry()`:

1. **Attempt 1:** Base model (e.g., `gpt-4o-mini`)
   - If filler detected → write debug artifact, retry with stronger model
   
2. **Attempt 2:** Stronger model (e.g., `gpt-4o`)
   - If filler still present → return stub with `low_quality_output:filler` reason

**Debug Artifact:** On failure, writes `__sum_debug_raw.txt` containing:
- Model used
- Attempt number
- Quality reason (e.g., `filler:banned_phrase`)
- Bullet counts
- Raw LLM output

**Failure Stub:** If both attempts fail, returns deterministic stub:
```json
{
  "extraction": {
    "status": "failed",
    "reason": "low_quality_output:filler:banned_phrase",
    "attempt_count": 2,
    "quality_reason": "filler:banned_phrase: 'market data pending analysis' found in bullet"
  },
  "sections": {
    "tldr": [],
    "what_occurred": [],
    "forward_watch": [],
    "trade_ideas": [],
    ...
  }
}
```

## Reason Format

All filler-related failures use the `filler:` prefix for easy identification:

- `filler:banned_phrase: '<phrase>' found in bullet`
- `filler:repeated_bullets_in_<section>: '<bullet>' appears <count> times`

This allows downstream logic to distinguish filler failures from other quality issues:
- `too_few_unique_bullets`
- `excessive_duplication`
- `excessive_placeholders`
- `excessive_short_bullets`

## Test Results

### test_quality_gate.py
```
================================================================================
QUALITY GATE REGRESSION TESTS
================================================================================

[TEST 1] Too few unique bullets                                    [PASS]
[TEST 2] Excessive duplication                                     [PASS]
[TEST 3] Excessive placeholders                                    [PASS]
[TEST 4] Excessive short bullets                                   [PASS]
[TEST 5] Valid summary should pass                                 [PASS]
[TEST 6] Neutral products with 'no direct trade idea'              [PASS]
[TEST 7] Completely empty summary                                  [PASS]
[TEST 8] Banned phrase: 'market data pending analysis'             [PASS]
[TEST 9] Banned phrase: 'monitor key levels and data releases'     [PASS]
[TEST 10] Banned phrase detection (case-insensitive)               [PASS]
[TEST 11] Section-level repetition (2+ identical bullets)          [PASS]
[TEST 12] Section-level repetition in multiple sections            [PASS]

ALL TESTS PASSED
================================================================================
```

### test_quality_retry.py
```
================================================================================
QUALITY RETRY MECHANISM TESTS
================================================================================

[TEST 1] Retry structure validation                                [PASS]
[TEST 2] Model escalation metadata                                 [PASS]
[TEST 3] Double failure returns stub                               [PASS]
[TEST 4] Bullet normalization                                      [PASS]
[TEST 5] Debug artifact structure                                  [PASS]
[TEST 6] Banned phrase triggers retry                              [PASS]
[TEST 7] Section repetition triggers retry                         [PASS]
[TEST 8] Filler failure reason format                              [PASS]

ALL TESTS PASSED
================================================================================
```

### test_quality_gate_integration.py
```
================================================================================
QUALITY GATE INTEGRATION TESTS
================================================================================

[INTEGRATION TEST] Quality Gate with summarize_text()             [PASS]
[INTEGRATION TEST] Failed Extraction TXT Rendering                [PASS]

INTEGRATION TESTS COMPLETE
================================================================================
```

## Files Modified

1. **summarize_pdf.py** (~110 lines modified)
   - Enhanced `is_low_quality_summary()` with banned phrases and repetition checks
   - Added section-level bullet tracking
   - Added filler-specific reason format

2. **test_quality_gate.py** (~150 lines added)
   - Added 5 new test cases for banned phrases and repetition
   - Updated test runner

3. **test_quality_retry.py** (~80 lines added)
   - Added 3 new test cases for retry behavior with filler
   - Fixed bullet extraction test expectations

## Usage

### Adding New Banned Phrases

To add more banned phrases, update the list in `is_low_quality_summary()`:

```python
banned_phrases = [
    "market data pending analysis",
    "monitor key levels and data releases",
    "your new phrase here",  # Case-insensitive
]
```

### Monitoring Production

Watch for filler failures in logs:
```
[QUALITY GATE] Failed on attempt 1: filler:banned_phrase: 'market data pending analysis' found in bullet
[ATTEMPT 2/2] Using model: gpt-4o
[QUALITY GATE] Failed on attempt 2: filler:banned_phrase: 'market data pending analysis' found in bullet
[FAIL] All attempts exhausted. Returning failure stub.
```

Check debug artifacts at `__sum_debug_raw.txt` for full details.

## Backward Compatibility

✅ Fully backward compatible:
- Existing quality checks unchanged
- Same retry mechanism (2 attempts with model escalation)
- Same stub format for failures
- All existing tests pass

## Next Steps

Optional enhancements:
1. Add more banned phrases based on production patterns
2. Make repetition threshold configurable (currently 2)
3. Add telemetry to track filler failure rates
4. Consider phrase similarity detection (not just exact matches)
