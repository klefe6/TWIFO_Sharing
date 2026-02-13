# Git Steps for Safe Cleanup Baseline

**Purpose:** Establish a tagged known-good state before reorganization  
**Last Updated:** 2026-02-04

---

## Step List

### 1. Ensure known-good state

- Run smoke tests per `SMOKE_TEST.md` (or at minimum: rollup validation + web app loads)
- Fix any blocking issues before committing

### 2. Commit current changes

```bash
cd "c:\Coding Projects\TWIFO_Sharing"
git status
git add <files>
git commit -m "chore: baseline before cleanup (smoke tests passing)"
```

### 3. Create tag (optional but recommended)

```bash
git tag -a v0-cleanup-baseline -m "Known-good state before file reorganization"
```

### 4. Create cleanup branch

```bash
git checkout -b chore/cleanup-reorg
```

### 5. Verify branch

```bash
git branch
git log -1 --oneline
git tag -l
```

---

## Quick Copy-Paste Sequence

```bash
cd "c:\Coding Projects\TWIFO_Sharing"
git status
git add .
git commit -m "chore: baseline before cleanup (smoke tests passing)"
git tag -a v0-cleanup-baseline -m "Known-good state before file reorganization"
git checkout -b chore/cleanup-reorg
git branch
```

---

## Rollback (if needed)

```bash
# Discard uncommitted changes
git checkout -- .

# Reset to tagged baseline
git checkout v0-cleanup-baseline

# Delete cleanup branch and return to master
git checkout master
git branch -D chore/cleanup-reorg
```
