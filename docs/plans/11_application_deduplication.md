# Plan: Application Deduplication Check

## Overview

Before running the full pipeline, scan the vault for a previous run against the same company+role slug and warn (or block) to avoid spending tokens on a duplicate application. A `--force` flag (already used for Gate 1) bypasses the check.

---

## Feature Dependency Diagram

```
[Depends on]
  └── Vault structure: create_vault_folder (vault.py — already exists)
  └── OBSIDIAN_VAULT_PATH config (already exists)

  CLI apply command (cli.py)
      │
      ▼
  check_for_duplicate(vault_path, company, role) (new: vault.py)
      │
      ├── slug = slugify(company + role)
      ├── scan vault_path for folders matching slug pattern
      │
      ├── None found → proceed
      ├── Found + --force → warn and proceed
      └── Found + no --force → print warning table + prompt for confirmation
              │
              ▼
          run_pipeline() (unchanged)
```

---

## Technical Plan

### 1. Slug matching logic (`vault.py`)

The existing `create_vault_folder` already generates a slug:

```python
slug = f"{company}_{role}".replace(" ", "_")
folder_name = f"{slug}_{date}"
```

The duplicate check searches for any folder matching `{slug}_*`:

```python
def find_duplicate_runs(vault_path: Path, company: str, role: str) -> list[Path]:
    """Return vault folders from prior runs for the same company+role."""
    slug = f"{company}_{role}".replace(" ", "_")
    return sorted(vault_path.glob(f"{slug}_*"))
```

Case-insensitive matching via `slug.lower()` comparison against `folder.name.lower()`.

### 2. Duplicate check in CLI (`cli.py`)

Insert before calling `run_pipeline`:

```python
from job_agent.vault import find_duplicate_runs

duplicates = find_duplicate_runs(config.OBSIDIAN_VAULT_PATH.expanduser(), company, role)

if duplicates and not force:
    console.print("\n[yellow]⚠️  Duplicate application detected:[/yellow]")
    for d in duplicates:
        # Parse status from status.md if it exists
        status = _read_status_label(d / "status.md")
        console.print(f"  {d.name}  [{status}]")
    console.print("\nUse [bold]--force[/bold] to run anyway, or Ctrl+C to cancel.")
    typer.confirm("Continue with a new run?", abort=True)
```

`_read_status_label` is a small helper that reads the `Status:` line from an existing `status.md` — reuses the existing `parse_status_file` function from `vault.py`.

Note: `--force` already exists on the `apply` command (for Gate 1 bypass). It doubles as the deduplication bypass — same flag, consistent semantics.

### 3. Confidence in slug matching

Slugs normalise spaces to underscores but don't handle:
- Different capitalisation: "Acme Corp" vs "acme corp"
- Abbreviations: "DS" vs "Data Scientist"

This is intentional — the check is a heuristic warning, not a hard lock. False negatives (missed duplicates) are acceptable; the check only needs to catch the obvious case of re-running the same company+role string.

Implement case-insensitive slug matching only. Do not attempt fuzzy matching — it adds complexity for minimal benefit.

### 4. Non-interactive mode

If `--force` is set, skip the confirmation prompt entirely and print a one-line notice:

```
[yellow]⚠ Duplicate run detected (--force set, proceeding anyway)[/yellow]
```

### 5. Tests

| Test | Approach |
|------|----------|
| No duplicates → proceeds without prompt | Assert `typer.confirm` never called |
| Duplicate found, user confirms | Mock `typer.confirm` returning True; assert pipeline called |
| Duplicate found, user aborts | Mock `typer.confirm` raising `Abort`; assert pipeline not called |
| Duplicate found + `--force` → no prompt | Assert `typer.confirm` never called |
| `find_duplicate_runs` case insensitivity | Assert "Acme Corp" and "acme corp" both match same folder |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Slug matching misses duplicates with different spacing/abbreviations | Medium | Document limitation: check is best-effort, not exhaustive. JD deduplication by content hash (Plan 14) covers the complementary case. |
| User runs pipeline twice on same day — second run creates a new timestamped folder | Low | The check catches same-day duplicates (same slug prefix). Both folders will be listed in the warning. |
| `--force` semantics conflict (Gate 1 bypass vs dedup bypass) | Low | `--force` semantics are "override all safety gates" — combining both behaviours under one flag is consistent. Document clearly in `--help`. |
| Vault path not accessible | Low | `find_duplicate_runs` wraps in try/except and returns `[]` on any filesystem error, so the check degrades gracefully. |
