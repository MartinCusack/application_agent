# Plan: Soft Gap Coverage Report

## Overview

After Agent 3b completes, emit a structured CLI table showing which soft gaps were resolved vs still remaining. Surfaces the writer's effectiveness at a glance, without requiring the user to open `rescore_report.md`.

---

## Feature Dependency Diagram

```
[Depends on]
  └── Agent 1a output: AnalysisResult.soft_missing (list of MissingKeyword)
  └── Agent 3b output: RescorerResult.soft_gaps_resolved / soft_gaps_remaining

  Agent 3b completes (rescore_result available)
      │
      ▼
  print_soft_gap_coverage(analysis, rescore) (new: pipeline.py or vault.py)
      │
      ├── Builds coverage table: keyword | gap_type | resolved?
      ├── Counts resolved vs remaining
      │
      ▼
  Rich table printed to console (no vault write — ephemeral CLI output)

[No new files, no new agents, no new models]
```

---

## Technical Plan

### 1. New function (`pipeline.py` inline or extracted to `vault.py`)

```python
def print_soft_gap_coverage(
    analysis: AnalysisResult,
    rescore: RescorerResult,
    console: Console,
) -> None:
    """Print a Rich table summarising soft gap resolution."""
    from rich.table import Table

    table = Table(title="Soft Gap Coverage", show_lines=True)
    table.add_column("Keyword", style="bold")
    table.add_column("Resolved?", justify="center")
    table.add_column("Rationale", style="dim")

    resolved_set = {k.lower() for k in rescore.soft_gaps_resolved}

    for gap in analysis.soft_missing:
        is_resolved = gap.keyword.lower() in resolved_set
        resolved_str = "[green]✅ Yes[/green]" if is_resolved else "[red]❌ No[/red]"
        table.add_row(gap.keyword, resolved_str, gap.rationale)

    resolved_count = len(rescore.soft_gaps_resolved)
    total_count = len(analysis.soft_missing)
    console.print(table)
    console.print(
        f"  [bold]{resolved_count}/{total_count}[/bold] soft gaps resolved "
        f"({'100%' if total_count == 0 else f'{100*resolved_count//total_count}%'})"
    )
```

### 2. Pipeline integration (`pipeline.py`)

Insert immediately after the Agent 3b rescore block, before the Gate 2 check:

```python
print_soft_gap_coverage(analysis, rescore, console)
```

This is a 1-line addition to `pipeline.py` — the function does all the work.

### 3. Regression warning extension

If `rescore.regressions` is non-empty, print an additional warning after the coverage table:

```python
if rescore.regressions:
    console.print(
        f"  [red]⚠️  Regressions detected in: {', '.join(rescore.regressions)}[/red]"
    )
```

This is already inspectable in `rescore_report.md`, but surfacing it in the terminal prevents it from being missed.

### 4. `recency_gaps` coverage

`AnalysisResult.recency_gaps` are not soft gaps in the traditional sense (they are flagged as not addressable via rephrasing). Exclude them from the coverage table to avoid confusion. The `recency_gaps` field is already visible in `match_report.md`.

### 5. Tests

| Test | Approach |
|------|----------|
| All soft gaps resolved → 100% message | Fixture with all gaps in `soft_gaps_resolved` |
| No soft gaps resolved → 0% message | Fixture with empty `soft_gaps_resolved` |
| Partial resolution → correct count and table rows | Fixture with 2/3 resolved |
| Regression warning printed when regressions non-empty | Assert regression text in console output |
| No regression warning when regressions empty | Assert regression text absent |
| Empty soft_missing → table renders without crash | `analysis.soft_missing = []` |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Keyword matching is case-sensitive and misses resolved gaps | Low | Normalise to lowercase on both sides before comparison (already in implementation above). |
| `soft_gaps_resolved` from RescorerAgent uses different phrasing than `soft_missing` keywords | Medium | The rescorer prompt explicitly receives the original soft keyword list and is instructed to cite them verbatim when resolved. If phrasing drifts, the coverage count will be pessimistic (showing unresolved gaps that were actually addressed). Acceptable — better to over-flag than under-flag. |
| Table adds noise to terminal output for users who check the vault | Low | Function is purely additive output — it doesn't change any logic. Users who prefer vault-only inspection are unaffected. |
| Long keyword strings break table layout | Low | Rich auto-wraps table cells. No truncation needed. |
