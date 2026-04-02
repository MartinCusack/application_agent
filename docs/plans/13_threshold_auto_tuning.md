# Plan: Threshold Auto-Tuning Suggestion

## Overview

After each run, analyse the initial vs final score delta. If the delta is consistently small across recent runs (< 5 points), suggest raising the threshold. Turns tracker data into actionable config feedback without requiring a separate command.

---

## Feature Dependency Diagram

```
[Depends on]
  └── Application tracker: list-applications / parse_status_file (already shipped)
  └── vault/status.md files (already written)

  run_pipeline() completes
      │
      ▼
  ThresholdAdvisor (new: job_agent/advisor.py or inline in pipeline.py)
      │
      ├── Reads last N status.md files from vault
      ├── Computes median delta across completed runs
      │
      ├── delta consistently low → suggest raising threshold
      ├── many gate 2 failures → suggest lowering threshold
      └── insufficient data → no suggestion
      │
      ▼
  Console suggestion printed after pipeline completes
  (no file written — advisory only)

  Optional: job-agent threshold-advice (standalone command)
```

---

## Technical Plan

### 1. New module: `job_agent/advisor.py`

```python
def suggest_threshold_adjustment(
    vault_path: Path,
    current_threshold: int,
    lookback: int = 5,
) -> Optional[str]:
    """
    Analyse recent runs and return a suggestion string if warranted, else None.

    Returns a plain-English suggestion, e.g.:
      "Scores improved by an average of 3 points over the last 5 runs.
       Consider raising your threshold from 65 to 70."
    """
```

Implementation:

1. `vault_path.rglob("status.md")` — collect all files, sort by mtime, take last `lookback`
2. For each: `parse_status_file(path)` → extract `initial_score`, `final_score`
3. Filter to runs where both scores are non-None (i.e. completed runs, not gate-1 exits)
4. Compute `deltas = [final - initial for ...]`
5. Compute `median_delta = statistics.median(deltas)`
6. Decision logic:
   - `median_delta < 5` and `len(deltas) >= 3`: suggest `current_threshold + 5`
   - Many gate-2 failures (i.e. runs where `final_score < current_threshold` in many cases): suggest `current_threshold - 5`
   - Otherwise: `None`

### 2. Pipeline integration (`pipeline.py`)

After the final vault write at the end of `run_pipeline`:

```python
from job_agent.advisor import suggest_threshold_adjustment

suggestion = suggest_threshold_adjustment(
    vault_path=config.OBSIDIAN_VAULT_PATH.expanduser(),
    current_threshold=threshold,
)
if suggestion:
    console.print(f"\n[dim]💡 Threshold suggestion: {suggestion}[/dim]")
```

Printed in `dim` style — clearly advisory, not an error or warning.

### 3. Standalone command (optional)

```python
@app.command()
def threshold_advice(
    lookback: int = typer.Option(5, "--lookback", help="Number of recent runs to analyse"),
) -> None:
    """Analyse recent score deltas and suggest a threshold adjustment."""
```

Prints the same suggestion, plus a mini table showing the last `lookback` runs with their deltas.

### 4. Gate-2 failure counting

Gate-2 failures are runs where the pipeline stopped because `rescore_result.gate_passed == False`. These are detectable from `status.md` if the format includes a `Status: Ready to apply` vs a partial status. Currently `format_status` writes the status value — a gate-2 failure writes whatever the tracker status is at time of write.

A cleaner signal: the JSON sidecar from Plan 07 (`pipeline_state.json`) would expose `rescore_result.gate_passed` directly. If the sidecar isn't available, infer from: `final_score < threshold` in `status.md`.

### 5. Tests

| Test | Approach |
|------|----------|
| Low delta suggestion triggered | 3 fixture status files with delta = 3; assert suggestion mentions raising threshold |
| No suggestion when delta high | 3 fixture files with delta = 12; assert `None` returned |
| Insufficient data returns None | 1 fixture file; assert `None` |
| Negative delta (regression) handled gracefully | Fixture with delta = -2; assert no crash, no suggestion |
| Standalone command prints suggestion | Mock `suggest_threshold_adjustment`; assert output contains suggestion text |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Advice is based on too few runs and misleads the user | Medium | Minimum 3 runs required before any suggestion fires. Advisory is printed in `dim` style with clear "suggestion" framing — not a config change. |
| Pipeline applies different thresholds across runs making comparison invalid | Low | Advice notes the `current_threshold` it is referencing. Runs with `--threshold` overrides are included in the data — this is acceptable noise at 5-run lookback. |
| Score delta varies heavily by role type making averages meaningless | Low | Advice is printed only once per pipeline run, not enforced. User can ignore it. |
| Suggestion always fires for a specific user's CV style | Low | Threshold of `< 5 point` median delta is conservative. If user's writer agent consistently improves summaries by 3 points, the suggestion will be consistent — which is actually useful feedback. |
