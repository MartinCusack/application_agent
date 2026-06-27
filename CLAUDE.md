# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands run from the repo root (`~/repos/application_agent/`) where `pyproject.toml` lives. Package manager is **UV** — always use `uv run` prefix.

```bash
uv sync                                                  # install / sync deps
uv run job-agent check-config                            # verify env setup
uv run job-agent apply --company "Acme" --role "DS"      # run pipeline (paste JD interactively)
uv run job-agent apply -c "Acme" -r "DS" --jd-file j.txt # load JD from file
uv run job-agent batch-apply                             # process all .md files in job_descriptions/TODO/
uv run job-agent batch-apply --dry-run                   # list files without running

uv run pytest                                            # full suite with coverage
uv run pytest tests/test_cv_utils.py tests/test_vault.py tests/test_loaders.py -v  # pure unit tests (fast, no mocking)
uv run pytest tests/test_pipeline.py -v                  # single file
uv run pytest tests/test_batch.py -v                     # batch + parser tests
```

## Architecture

### Single-responsibility modules

| File | Owns |
|------|------|
| `job_agent/prompts.py` | All LLM prompt strings — **edit here to change agent behaviour** |
| `job_agent/models.py` | Pydantic schemas for every agent input/output, `PipelineState`, and batch models |
| `job_agent/agents.py` | Agent classes — thin wrappers that wire prompts to `BaseAgent._call()` |
| `job_agent/pipeline.py` | Single-job orchestrator — sequences agents, evaluates gates, writes vault files |
| `job_agent/batch.py` | Batch orchestrator — discovers JD queue, runs `run_pipeline` per job, moves files |
| `job_agent/jd_parser.py` | Parses JD `.md` files — YAML frontmatter + filename convention fallback |
| `job_agent/vault.py` | Obsidian I/O and markdown formatters (including `format_batch_summary`) |
| `job_agent/cv_utils.py` | Pure string helpers (`extract_summary`, `substitute_summary`) |
| `job_agent/loaders.py` | File I/O (`load_cv`, `load_skills_table`, `load_text`) |
| `job_agent/config.py` | Env-var config with defaults |

No logic lives in `__init__.py`. Pure string operations that need cheap testing go in `cv_utils.py`, not `agents.py`.

### PipelineState data flow

`PipelineState` is created once and passed through every stage. Each agent adds its output field; all other fields are read-only. The state is always returned to the caller — including on early exit — so partial results are inspectable.

```
Init PipelineState
  ↓
Agent 1a → state.analysis (AnalysisResult + ScoringRubric)
  ↓ Gate 1: analysis.proceed_with_application
Agent 1b → state.cover_letter_result    → cover_letter.md
  ↓
Agent 2  → state.writer_result          → cv_tailored.md
  ↓
Agent 2b → state.diff_result            → cv_diff.md
  ↓
Agent 3b → state.rescore_result         → rescore_report.md
  ↓ Gate 2: rescore_result.gate_passed
Write status.md → done
```

Gates write `status.md` before returning, so partial vault output is always present.

### BaseAgent retry loop

`BaseAgent._call(system, human, output_model)` handles all LLM calls:
- Strips markdown fences from responses
- Validates JSON against the Pydantic schema
- On failure: appends bad response + correction prompt to history, retries up to 3× with exponential backoff (1s, 2s, 4s)
- Raises `ValueError` (bad JSON) or `ValidationError` (schema mismatch) after exhausting retries

### ScoringRubric passthrough

`AnalystAgent` (1a) produces a `ScoringRubric` embedded in `AnalysisResult`. This exact object is forwarded to `RescorerAgent` (3b) unchanged. This prevents criterion drift — score deltas are only meaningful if both agents scored against the same criteria.

### Adding a new agent

1. Add output model to `models.py`
2. Add field to `PipelineState` (Optional, defaults to None)
3. Add system + human prompt constants to `prompts.py`
4. Add agent class to `agents.py` (inherit `BaseAgent`, implement `run()`)
5. Add vault formatter to `vault.py`
6. Wire into `pipeline.py` — call agent, set state field, call `write_to_vault`

## Required data files

| File | Notes |
|------|-------|
| `data/cv.md` | Must have a `## Summary`, `## Profile`, or `## About` heading for `cv_utils` extraction |
| `data/skills.xlsx` | Columns: Skill, Category, Proficiency, Projects, Roles, Years. Agent 2 cites rows to prevent hallucination |
| `data/cover_letter.md` | Template with `[BRACKETED PLACEHOLDERS]` — Agent 1b fills these from the JD |
| `data/cover_letter_rubric.md` | Quality rubric injected into Agent 1b's prompt |

## Testing strategy

No API key needed — LLM calls are mocked in `test_agents.py` and `test_pipeline.py`.

| Test file | Approach |
|-----------|----------|
| `test_cv_utils.py`, `test_vault.py`, `test_loaders.py` | Pure unit tests; no mocking |
| `test_agents.py` | `mocker.patch` on `BaseAgent.llm.invoke`; tests JSON parsing, retry logic, schema validation |
| `test_pipeline.py` | All agents mocked; tests Gate 1/2 control flow, vault writes, threshold override |
| `test_batch.py` | `patch` on `run_pipeline`; tests JD parsing, file movement, error isolation, result counts |

## Key config variables

All in `.env` (copy from `.env.example`):

| Variable | Default |
|----------|---------|
| `ANTHROPIC_API_KEY` | — required |
| `MATCH_SCORE_THRESHOLD` | `65` |
| `MODEL_NAME` | `claude-sonnet-4-6` |
| `OBSIDIAN_VAULT_PATH` | `~/Documents/vault/.../companies/` |
| `COVER_LETTER_TEMPLATE_PATH` | `data/cover_letter.md` |
| `COVER_LETTER_RUBRIC_PATH` | `data/cover_letter_rubric.md` |
| `BATCH_TODO_DIR` | `job_descriptions/TODO` |
| `BATCH_DELAY_SECONDS` | `2.0` |
