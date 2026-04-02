# Plan: Configurable Agent Pipeline

## Overview

Allow individual agents to be skipped via CLI flags or a config key. Useful when iterating on the CV summary alone without regenerating the cover letter each run, or when a fast feedback loop is needed. The full pipeline remains the default.

---

## Feature Dependency Diagram

```
[No upstream dependencies]
[Interacts with all agents — purely orchestration logic in pipeline.py + cli.py]

  CLI flags (cli.py)
      │
      ├── --skip-cover-letter  → skip Agent 1b
      └── --skip-diff          → skip Agent 2b

  config.py (optional .env overrides)
      │
      ├── SKIP_COVER_LETTER=true  → always skip Agent 1b
      └── SKIP_DIFF=true          → always skip Agent 2b

  run_pipeline(skip_cover_letter=..., skip_diff=...) (pipeline.py)
      │
      ├── Agent 1a — always runs (scoring is non-optional)
      ├── Gate 1
      ├── Agent 1b — conditional
      ├── Agent 2  — always runs (core feature)
      ├── Agent 2b — conditional
      ├── Agent 3b — always runs (gate 2 requires it)
      └── Gate 2

[Downstream: Plans 05, 06, 10 — their skip flags follow the same pattern]
```

**Constraint:** Agents 1a, 2, and 3b are non-optional — they are required for the scoring gates. Only Agents 1b (cover letter) and 2b (diff) are skippable without breaking pipeline logic.

---

## Technical Plan

### 1. Config additions (`config.py`)

```python
SKIP_COVER_LETTER: bool = False   # read from SKIP_COVER_LETTER env var
SKIP_DIFF: bool = False           # read from SKIP_DIFF env var
```

These provide persistent defaults. CLI flags override on a per-run basis.

### 2. `run_pipeline` signature (`pipeline.py`)

```python
def run_pipeline(
    company: str,
    role: str,
    job_description: str,
    threshold: int = config.MATCH_SCORE_THRESHOLD,
    force: bool = False,
    skip_cover_letter: bool = False,
    skip_diff: bool = False,
) -> PipelineState:
```

Effective skip = `config.SKIP_COVER_LETTER or skip_cover_letter` (CLI overrides config).

### 3. Conditional agent blocks (`pipeline.py`)

**Agent 1b:**

```python
if not (skip_cover_letter or config.SKIP_COVER_LETTER):
    console.print(Panel("✉️  Agent 1b: Cover Letter", style="bold magenta"))
    cover_letter_result = CoverLetterAgent().run(...)
    state.cover_letter_result = cover_letter_result
    write_to_vault(vault_folder, "cover_letter.md", format_cover_letter(cover_letter_result))
else:
    console.print("[dim]Agent 1b skipped (--skip-cover-letter)[/dim]")
```

**Agent 2b:**

```python
if not (skip_diff or config.SKIP_DIFF):
    console.print(Panel("📊 Agent 2b: Change Log", style="bold cyan"))
    diff_result = DiffAgent().run(...)
    state.diff_result = diff_result
    write_to_vault(vault_folder, "cv_diff.md", format_diff_report(diff_result))
else:
    console.print("[dim]Agent 2b skipped (--skip-diff)[/dim]")
```

### 4. CLI flag additions (`cli.py`)

```python
skip_cover_letter: bool = typer.Option(False, "--skip-cover-letter", help="Skip cover letter generation (Agent 1b)")
skip_diff: bool = typer.Option(False, "--skip-diff", help="Skip change log generation (Agent 2b)")
```

### 5. `check-config` extension

Print skip states:

```
  Skip cover letter: false
  Skip diff:         false
```

### 6. Vault completeness

Skipped agents produce no vault file. The `status.md` should note which agents were skipped:

```markdown
Agents skipped: cover_letter, diff
```

Add `skipped_agents: list[str] = Field(default_factory=list)` to `PipelineState`. Populate in `pipeline.py` when an agent is skipped. Include in `format_status`.

### 7. Tests

| Test | Approach |
|------|----------|
| `--skip-cover-letter` skips Agent 1b | Assert `CoverLetterAgent` never instantiated; `cover_letter.md` not written |
| `--skip-diff` skips Agent 2b | Assert `DiffAgent` never instantiated; `cv_diff.md` not written |
| Config env var skip overrides default | Set `SKIP_COVER_LETTER=true` in env; assert agent skipped without CLI flag |
| CLI flag overrides config | `SKIP_COVER_LETTER=false` in env + `--skip-cover-letter` → skip fires |
| Skipped agents recorded in `status.md` | Assert `"Agents skipped:"` in format_status output |
| Core agents (1a, 2, 3b) cannot be skipped | No skip flags provided for these — enforced by absence of flags |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Skipping Agent 2b means no diff in vault — user forgets they skipped it | Low | `status.md` records which agents were skipped. `list-applications` could mark these runs with a `[partial]` indicator. |
| Future agents added without skip flag support | Low | The skip pattern is simple and well-documented. Any new optional agent should follow the same `--skip-{agent}` convention. |
| SKIP_COVER_LETTER=true persisted in .env inadvertently disables cover letters | Low | `check-config` prints skip states prominently. Document in `.env.example` with a warning comment. |
| Test mocking of skipped agents is incomplete | Low | Test must assert `CoverLetterAgent` was never instantiated — use `mocker.patch` and assert `call_count == 0`. |
