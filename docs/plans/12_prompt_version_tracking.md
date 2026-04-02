# Plan: Prompt Version Tracking

## Overview

Embed a `PROMPT_VERSION` constant in `prompts.py` that is written into every vault run's `status.md`. Makes it possible to audit which prompt version produced a given output and compare score distributions across prompt revisions.

---

## Feature Dependency Diagram

```
[No upstream dependencies]

  prompts.py
      │  PROMPT_VERSION = "v1.3"
      ▼
  PipelineState (models.py)
      │  prompt_version: str field
      ▼
  pipeline.py
      │  state.prompt_version = prompts.PROMPT_VERSION
      ▼
  vault.py: format_status()
      │  writes "Prompt version: v1.3" to status.md
      ▼
  status.md

  vault.py: parse_status_file()
      │  reads prompt_version from status.md
      ▼
  list-applications table
      │  new "Prompt" column (optional, off by default)
      ▼
  CLI: list-applications --show-prompt-version
```

---

## Technical Plan

### 1. Version constant (`prompts.py`)

Add at the top of the file:

```python
# Bump this whenever any prompt string is modified.
# Format: vMAJOR.MINOR — bump MAJOR for structural changes (new fields, reordered output),
# MINOR for wording tweaks.
PROMPT_VERSION = "v1.0"
```

Single source of truth. All agents share one version — per-agent versioning adds complexity for minimal benefit given the project's solo use.

### 2. `PipelineState` field (`models.py`)

```python
class PipelineState(BaseModel):
    ...
    prompt_version: str = Field(default="unknown")
```

Default `"unknown"` ensures backward compatibility with any code that constructs `PipelineState` directly without the field (tests).

### 3. Pipeline write (`pipeline.py`)

```python
import job_agent.prompts as prompts

state = PipelineState(
    ...
    prompt_version=prompts.PROMPT_VERSION,
)
```

No other changes to pipeline logic.

### 4. `status.md` format (`vault.py`)

Extend `format_status` to include the prompt version line:

```markdown
# Application Status

Company: Acme Corp
Role: Senior Data Scientist
Date: 2025-01-15
Run ID: a1b2c3d4
Prompt version: v1.2          ← new line
Initial score: 74
Final score: 81
Score delta: +7
Variant: leadership
Status: Applied
```

### 5. `parse_status_file` update (`vault.py`)

Add prompt version parsing alongside the existing regex-based field extraction:

```python
prompt_version_match = re.search(r"Prompt version:\s*(\S+)", content)
data["prompt_version"] = prompt_version_match.group(1) if prompt_version_match else "unknown"
```

### 6. `list-applications` table update (`cli.py`)

Add an optional `--show-prompt-version` flag. When set, add a `Prompt` column to the Rich table. Hidden by default to keep the table compact.

### 7. Versioning convention (documented in `prompts.py` header)

| Change type | Version bump |
|-------------|-------------|
| New output field added to any prompt | MAJOR (e.g. v1.0 → v2.0) |
| Existing field renamed or removed | MAJOR |
| Wording/instruction change | MINOR (e.g. v1.0 → v1.1) |
| Typo fix, whitespace | No bump needed |

### 8. Tests

| Test | Approach |
|------|----------|
| `format_status` includes prompt version | Assert `"Prompt version:"` present in formatted output |
| `parse_status_file` reads version correctly | Fixture `status.md` with version line; assert `data["prompt_version"] == "v1.2"` |
| `parse_status_file` handles missing version | Fixture without version line; assert `data["prompt_version"] == "unknown"` |
| `PipelineState` picks up version from prompts module | Assert `state.prompt_version == prompts.PROMPT_VERSION` |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Developer forgets to bump version after prompt change | Medium | Add a note in `CLAUDE.md` under "Adding a new agent" and "Editing prompts". No automated enforcement without a linter rule. |
| Old status.md files don't have version line | Low | `parse_status_file` defaults to `"unknown"` — backward compatible. |
| Version string format diverges (e.g. "v1.0" vs "1.0" vs "1") | Low | Single regex `r"v\d+\.\d+"` normalises parsing. Constant declaration enforces format by example. |
| Per-prompt versioning needed for fine-grained analysis | Low | If needed later, extend to a dict: `PROMPT_VERSIONS = {"analyst": "v1.2", "writer": "v1.0"}`. Current single-version approach is the right starting point. |
