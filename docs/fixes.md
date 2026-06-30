# Fixes / Known Issues

## `check-config` — vault path has no existence check

**File:** `job_agent/cli.py` line 190

**Problem:** `OBSIDIAN_VAULT_PATH` is printed without a ✅/❌ check, unlike all other paths. This is confusing — the user cannot tell from the output whether the vault directory actually exists.

**Fix:** Add an existence check consistent with the other paths:

```python
console.print(
    f"  Obsidian vault:  {config.OBSIDIAN_VAULT_PATH} "
    f"{'✅' if config.OBSIDIAN_VAULT_PATH.exists() else '❌ NOT FOUND'}"
)
```

**Priority:** Low — cosmetic, but causes confusion during Docker setup where the mount may silently fail.
