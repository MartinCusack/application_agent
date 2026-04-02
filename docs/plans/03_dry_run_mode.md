# Plan: Dry Run Mode

## Overview

A `--dry-run` flag that renders and prints all agent prompts and their expected schema shapes without making any API calls. Useful for validating prompt templates, checking the skills table is loading correctly, and confirming environment setup before spending tokens.

---

## Feature Dependency Diagram

```
[No upstream dependencies]

  CLI apply command (cli.py)
      │  --dry-run flag
      ▼
  run_pipeline(dry_run=True) (pipeline.py)
      │
      ├── Loads CV, skills table, cover letter template — same as live
      ├── Renders all prompt f-strings — same as live
      │
      └── DryRunAgent (new) — prints rendered prompts, returns mock output
              │
              ▼
          Mock PipelineState (all agent fields populated with placeholder data)
              │
              ▼
          No vault writes, no API calls

[No downstream dependants]
```

---

## Technical Plan

### 1. CLI flag (`cli.py`)

```python
dry_run: bool = typer.Option(False, "--dry-run", help="Print rendered prompts without making API calls")
```

Pass to `run_pipeline(dry_run=dry_run)`.

### 2. `run_pipeline` signature (`pipeline.py`)

```python
def run_pipeline(
    company: str,
    role: str,
    job_description: str,
    threshold: int = config.MATCH_SCORE_THRESHOLD,
    force: bool = False,
    dry_run: bool = False,
) -> PipelineState:
```

When `dry_run=True`, replace every agent instantiation with `DryRunAgent(agent_class)`.

### 3. New `DryRunAgent` wrapper (`agents.py` or new `dry_run.py`)

```python
class DryRunAgent:
    """Wraps any agent class for dry-run mode. Prints the rendered prompt and returns a mock output."""

    def __init__(self, agent_class: type) -> None:
        self.agent_class = agent_class

    def run(self, *args, **kwargs) -> Any:
        # Instantiate the real agent to get access to its prompt-rendering logic
        # but override _call to print instead of invoking
        ...
```

Simpler alternative: pass `dry_run=True` into `BaseAgent._call`. When true, `_call` prints both the system and human prompts (via Rich `Syntax` with `json` or `markdown` highlighting), then returns a minimal mock of `output_model` constructed with `output_model.model_construct()` and placeholder field values.

#### Mock output construction

Use `output_model.model_fields` to discover fields and populate them with type-appropriate placeholders:
- `str` → `"[DRY RUN PLACEHOLDER]"`
- `int` → `0`
- `bool` → `True`
- `list` → `[]`
- `dict` → `{}`
- Nested `BaseModel` → recurse

This avoids needing hardcoded mock factories per agent.

### 4. Prompt printing format

```
╔══════════════════════════════════════════════════════╗
║  DRY RUN — Agent 1a (AnalystAgent)                   ║
║  System prompt: 847 chars | Human prompt: 3,241 chars ║
╚══════════════════════════════════════════════════════╝

── SYSTEM ─────────────────────────────────────────────
You are a senior technical recruiter with 15 years...

── HUMAN (first 500 chars) ────────────────────────────
Analyse this candidate's CV against the job description...

── OUTPUT SCHEMA ──────────────────────────────────────
AnalysisResult: aggregate_score (int), section_scores (list), ...
```

Use `Console().print(Panel(...))` and `Rule()` for structure. Truncate human prompts at 500 chars to keep dry-run output scannable — show `[... {n} chars truncated]` suffix.

### 5. Vault behaviour in dry run

Skip all vault writes. Print a summary at the end:

```
[DRY RUN] Would write to: ~/obsidian/Applications/Acme_Corp_Senior_DS_2025-01-15/
  - job_description.md
  - match_report.md
  - cover_letter.md
  - cv_tailored.md
  - cv_diff.md
  - rescore_report.md
  - status.md
```

### 6. Tests (`tests/test_dry_run.py`)

| Test | Approach |
|------|----------|
| No API calls made | Assert `BaseAgent.llm.invoke` never called when `dry_run=True` |
| All prompts printed | Capture stdout; assert agent name headings present |
| Returns complete PipelineState | Assert all agent fields on returned state are non-None |
| No vault files written | Assert vault folder not created |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Mock output triggers downstream assertion errors | Medium | `model_construct()` bypasses validation — fields are technically invalid. Pipeline logic must check `dry_run` before gates (Gate 1 and Gate 2 should be skipped in dry-run mode since `proceed_with_application=True` is a placeholder). |
| Human prompt truncation hides formatting errors | Low | Provide `--dry-run-full` flag that disables truncation; default truncated for readability. |
| f-string rendering itself throws (missing data file) | Medium | Data file loading still runs in dry-run mode by design — this is a feature, not a bug. The dry run validates loaders too. Errors here should surface with the same error messages as live runs. |
| Dry-run output too long to be useful | Medium | Truncate each prompt to 500 chars by default. Ensure the schema summary fits in < 5 lines. |
