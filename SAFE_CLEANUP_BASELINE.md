# Safe Cleanup Baseline Controls

**Purpose:** Establish a known-good state before any file reorganization  
**Last Updated:** 2026-02-04

---

## Overview

Before modifying or moving files in TWIFO_Sharing:

1. **Validate** pipelines with smoke tests (no assumption that unit tests exist)
2. **Commit** current state
3. **Tag** baseline
4. **Branch** for cleanup work

---

## Documents

| Document | Purpose |
|----------|---------|
| [SMOKE_TEST.md](SMOKE_TEST.md) | Exact commands to validate article summarization and rollup pipelines |
| [CLEANUP_GIT_STEPS.md](CLEANUP_GIT_STEPS.md) | Git steps: commit, tag, new cleanup branch |
| [DEPENDENCY_MAP.md](DEPENDENCY_MAP.md) | Full dependency and entrypoint map (for reorganization planning) |

---

## Known-Good State

A known-good state means:

- `python smoke_test_pdf.py <pdf>` runs without import errors (or rollup validation passes)
- `python twifo.py` serves `http://127.0.0.1:8065`
- No uncommitted breaking changes

**Do not assume tests exist.** Use smoke commands in `SMOKE_TEST.md` to validate.

---

## Quick Start

```bash
# 1. Smoke validate (pick one or more)
python smoke_test_pdf.py <path-to-pdf>
python rollup_validate.py --dir <rollups-daily-path>
python twifo.py   # → open http://127.0.0.1:8065

# 2. Commit, tag, branch (see CLEANUP_GIT_STEPS.md)
git add .
git commit -m "chore: baseline before cleanup"
git tag -a v0-cleanup-baseline -m "Known-good state before reorganization"
git checkout -b chore/cleanup-reorg
```
