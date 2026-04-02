# Job Agent — Developer Onboarding Guide

> **Purpose:** Get a new developer up to speed on the architecture, data flow, and known issues of the job_agent pipeline.

---

## Table of Contents

1. [What Does It Do?](#what-does-it-do)
2. [Quickstart](#quickstart)
3. [Architecture Overview](#architecture-overview)
4. [Data Flow — Step by Step](#data-flow--step-by-step)
5. [Each Agent In Depth](#each-agent-in-depth)
6. [Pipeline Gates](#pipeline-gates)
7. [Error Handling & Retry Logic](#error-handling--retry-logic)
8. [Vault Output](#vault-output)
9. [Where to Make Changes](#where-to-make-changes)
10. [Known Sticking Points & Bugs](#known-sticking-points--bugs)
11. [Testing](#testing)

---

## What Does It Do?

The job agent is an AI-powered multi-agent pipeline. Given a job description, it:

1. **Scores** the candidate's CV against the JD and classifies gaps
2. **Writes** a tailored cover letter by filling a pre-validated template
3. **Rewrites** the CV summary section to address soft skill gaps
4. **Re-scores** the edited CV to verify the score improved past a threshold
5. **Writes everything** to an Obsidian vault folder for review

The whole point: turn raw job posting + CV into an apply-ready, self-consistent application package with an auditable score trail.

---

## Quickstart

### Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) installed
- An Anthropic API key

### Setup

```bash
# From repo root
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and OBSIDIAN_VAULT_PATH in .env

uv sync                          # install deps
uv run job-agent check-config    # verify setup
```

### Required data files

| File | Notes |
|------|-------|
| `data/cv.md` | Full CV in markdown. Must have a `## Summary`, `## Profile`, or `## About` heading. |
| `data/skills.xlsx` | Excel table. Columns: Skill, Category, Proficiency, Projects, Roles, Years. |
| `data/cover_letter.md` | Template with `[BRACKETED PLACEHOLDERS]`. |
| `data/cover_letter_rubric.md` | Quality rubric injected into the cover letter agent. |

### Running the pipeline

```bash
# Interactive — paste JD when prompted
uv run job-agent apply --company "Acme Corp" --role "Senior Data Scientist"

# From a file
uv run job-agent apply -c "Acme" -r "DS" --jd-file job.txt

# Override the score threshold
uv run job-agent apply -c "Acme" -r "DS" --threshold 75
```

---

## Architecture Overview

```
job_agent/
├── cli.py         — Typer CLI entry point (apply + check-config commands)
├── pipeline.py    — Orchestrator: sequences agents, evaluates gates, calls vault
├── agents.py      — All agent classes + BaseAgent retry logic
├── models.py      — Pydantic schemas for every agent input/output + PipelineState
├── prompts.py     — Every LLM prompt string — edit here to tune agent behaviour
├── vault.py       — Obsidian folder creation + markdown formatters
├── cv_utils.py    — Pure string helpers (extract_summary, substitute_summary)
├── loaders.py     — File I/O (CV, skills table, templates)
└── config.py      — Env-var config with defaults
```

**Design principle:** Each module has one job. No logic lives in `__init__.py`. Prompt tuning happens entirely in `prompts.py` — you should rarely need to touch `agents.py` to change behaviour.

### Key config variables (`.env`)

| Variable | Default | Notes |
|----------|---------|-------|
| `ANTHROPIC_API_KEY` | — | Required |
| `MODEL_NAME` | `claude-sonnet-4-6` | Any Anthropic model ID |
| `MODEL_PROVIDER` | `anthropic` | `anthropic` or `openai` |
| `OBSIDIAN_VAULT_PATH` | `~/Documents/vault/.../companies/` | Where vault folders are created |
| `MATCH_SCORE_THRESHOLD` | `65` | Minimum score (0–100) to proceed past Gate 2 |
| `CV_PATH` | `data/cv.md` | Path to master CV |
| `SKILLS_TABLE_PATH` | `data/skills.xlsx` | Path to skills Excel |

---

## Data Flow — Step by Step

```
User: company, role, job_description
         │
         ▼
Load: cv.md, skills.xlsx, cover_letter.md, cover_letter_rubric.md
         │
         ▼
Create PipelineState (run_id, company, role, jd)
Create Obsidian vault folder → write job_description.md
         │
         ▼
Agent 1a AnalystAgent
  → scores CV against JD (0–100)
  → classifies gaps: hard / soft / recency
  → produces ScoringRubric (forwarded to rescorer verbatim)
  → sets proceed_with_application
  → writes match_report.md
         │
    [GATE 1]  proceed_with_application == False?
         │     └─ write status.md → return state (early exit)
         ▼
Agent 1b CoverLetterAgent
  → fills [BRACKETED PLACEHOLDERS] in template
  → grounds every claim in analysis.transferable_strengths
  → writes cover_letter.md
         │
         ▼
Agent 2 WriterAgent
  → rewrites CV summary (max 80 words, 4 sentences)
  → addresses soft_missing gaps only; ignores hard_missing
  → cites rows from skills.xlsx to prevent hallucination
  → writes cv_tailored.md
         │
         ▼
substitute_summary(cv_text, new_summary)   ← cv_utils.py
  → full CV ready for rescoring
         │
         ▼
Agent 2b DiffAgent
  → documents every change between original and new summary
  → writes cv_diff.md
         │
         ▼
Agent 3b RescorerAgent
  → re-scores using THE SAME ScoringRubric from Agent 1a
  → calculates deltas, flags regressions
  → sets gate_passed = (new_score >= threshold)
  → writes rescore_report.md
         │
    [GATE 2]  gate_passed == False?
         │     └─ write status.md → return state (early exit)
         ▼
Write status.md → return PipelineState (all fields populated)
```

**Critical design choice — ScoringRubric passthrough:** The rubric produced by Agent 1a (keywords, section weights, recency flags) is passed unchanged to Agent 3b. This is intentional: score deltas are only meaningful if both agents scored against identical criteria. Never let the rescorer invent its own rubric.

---

## Each Agent In Depth

### Agent 1a — AnalystAgent (`agents.py:142`)

**What it does:** Deep analysis of CV vs JD. This is the most important agent — its output drives every downstream decision.

**Inputs:** CV text, skills table (markdown), job description

**Output model:** `AnalysisResult` (`models.py:73`)

| Field | Type | Meaning |
|-------|------|---------|
| `aggregate_score` | `int` | 0–100 overall match |
| `section_scores` | `list[SectionScore]` | Per-section breakdown |
| `hard_missing` | `list[MissingKeyword]` | Skills genuinely absent — DO NOT fabricate |
| `soft_missing` | `list[MissingKeyword]` | Skills present but phrased differently — rephraseable |
| `recency_gaps` | `list[MissingKeyword]` | Fast-moving fields where 1–2 years = genuine seniority |
| `transferable_strengths` | `list[str]` | Domain expertise that commands a premium |
| `proceed_with_application` | `bool` | Gate 1 trigger |
| `rubric` | `ScoringRubric` | Forwarded verbatim to Rescorer |

**Prompt strategy (`prompts.py:13`):** Persona is "Senior technical recruiter, 15 years in regulated industries." Key instructions:
- Do not penalise candidates for limited tenure in fast-moving AI/ML fields
- Recognise transferable regulatory expertise (FDA, ISO 13485) as premium
- `section_weights` must sum to 1.0

---

### Agent 1b — CoverLetterAgent (`agents.py:174`)

**What it does:** Fills `[BRACKETED PLACEHOLDERS]` in the cover letter template. Never rewrites the body paragraph.

**Inputs:** Template, rubric, JD, company, role, `AnalysisResult`

**Output model:** `CoverLetterResult` (`models.py:~130`)

**Strict rules enforced by prompt (`prompts.py:88`):**
- No first-person pronouns — not once
- No en-dashes — use commas
- No deferential openers ("Eager to", "Looking to", "Hoping to")
- Every claim grounded in template or analysis
- The body paragraph is reproduced **verbatim** — not one word changed

---

### Agent 2 — WriterAgent (`agents.py:219`)

**What it does:** Rewrites the CV summary to better match the JD.

**Inputs:** Full CV, skills table, `AnalysisResult`

**Output model:** `WriterResult` → single `CVVariant` labelled `"leadership"`

**Summary rubric (from prompt, `prompts.py:156`):**
1. Seniority — role level, years, domain
2. Differentiator — what makes candidate rare (proved, never asserted)
3. Proof points — 1–2 specific, quantified achievements
4. Forward hook — targets role type, NOT specific employer

**Hard constraints:**
- Max 80 words, 4 sentences
- No first-person pronouns, no en-dashes
- Max 3 tool/technology names (rest belong in the skills table)
- Only cite rows that exist in skills.xlsx — do not fabricate
- Address soft gaps only; do NOT invent experience for hard gaps

---

### Agent 2b — DiffAgent (`agents.py:257`)

**What it does:** Produces an auditable change log between original and rewritten summary.

**Inputs:** Original summary, new summary, variant label

**Output model:** `DiffResult`

Straightforward agent. Prompt: "You produce clear, honest change logs. No spin."

---

### Agent 3b — RescorerAgent (`agents.py:285`)

**What it does:** Re-scores the edited CV using the exact same rubric produced by Agent 1a.

**Inputs:** Full CV (with substituted summary), JD, original `AnalysisResult`, variant label, threshold

**Output model:** `RescorerResult`

| Field | Meaning |
|-------|---------|
| `new_aggregate_score` | New 0–100 score |
| `score_deltas` | Dict of section → delta |
| `aggregate_delta` | New minus original |
| `soft_gaps_resolved` | Soft keywords now present |
| `regressions` | Sections that went down |
| `gate_passed` | `new_aggregate_score >= threshold` |

**The rubric is injected explicitly (`prompts.py:265`):** The same `keywords_identified` and `section_weights` from the analyst are passed in. The system prompt says: "Use ONLY the rubric provided — do not invent new criteria."

---

## Pipeline Gates

### Gate 1 — After AnalystAgent (`pipeline.py:113`)

```python
if not analysis.proceed_with_application:
    write_to_vault(vault_folder, "status.md", format_status(state))
    return state
```

**Triggers when:** Analyst judges the CV is too poor a match to bother applying (e.g., hard gaps dominate, score far below threshold).

**What's written:** `status.md` with initial score, "N/A" final score.
**What's preserved:** `state.analysis` is fully populated — inspect it to understand why.

---

### Gate 2 — After RescorerAgent (`pipeline.py:164`)

```python
if not rescore.gate_passed:
    write_to_vault(vault_folder, "status.md", format_status(state))
    return state
```

**Triggers when:** The rewritten CV still scores below `MATCH_SCORE_THRESHOLD`.

**What's written:** `status.md` with both initial and final scores.
**What's preserved:** All agent outputs are populated. The vault folder contains all intermediate files.

---

## Error Handling & Retry Logic

All LLM calls go through `BaseAgent._call()` (`agents.py:57`).

### What it does

1. Sends system + human messages to the LLM
2. Strips markdown fences from the response (```` ```json ... ``` ````)
3. Tries `json.loads()` → then `output_model.model_validate()`
4. On failure: appends the bad response + a correction prompt to the message history, then retries

### Retry schedule

| Attempt | Sleep before |
|---------|-------------|
| 1 | — |
| 2 | 1 second |
| 3 | 2 seconds |

Three attempts total. After the third failure:
- Invalid JSON → raises `ValueError` with the raw LLM response included
- Schema mismatch → raises `pydantic.ValidationError`

### Correction prompt strategy

On JSON failure:
> "Your previous response was not valid JSON. Respond ONLY with a valid JSON object matching the required schema. Do not include any explanation, markdown fences, or other text."

On schema failure:
> "Your previous response did not match the required schema. Error: [details]. Respond ONLY with a valid JSON object matching this exact schema: [full JSON schema]. …"

The full Pydantic schema is embedded in the correction, giving the model the best chance of self-correcting.

---

## Vault Output

Every run creates a dated folder under `OBSIDIAN_VAULT_PATH`:

```
Acme_Corp_Senior_Data_Scientist_2026-03-08/
├── job_description.md    — raw JD (always written)
├── match_report.md       — Agent 1a analysis + scores
├── cover_letter.md       — tailored cover letter + tailoring notes
├── cv_tailored.md        — full CV with rewritten summary
├── cv_diff.md            — before/after change log
├── rescore_report.md     — new scores, deltas, regressions
└── status.md             — one-page summary (written at gate exits or end)
```

On early exit (Gate 1 or Gate 2), only the files produced up to that point exist. `status.md` is always the last file written.

---

## Where to Make Changes

| Goal | File | What to change |
|------|------|----------------|
| Change agent behaviour / prompt | `prompts.py` | Edit the relevant `_SYSTEM` or `_HUMAN` constant |
| Add a new agent | `models.py`, `agents.py`, `prompts.py`, `vault.py`, `pipeline.py` | See "Adding a new agent" in CLAUDE.md |
| Change scoring thresholds / env vars | `.env` | Update `MATCH_SCORE_THRESHOLD` etc. |
| Change what's written to the vault | `vault.py` | Edit the `format_*` functions |
| Change gap classification logic | `models.py` | Edit `MissingKeyword` or `GapType` |
| Change CV parsing | `cv_utils.py` | Edit `extract_summary` / `substitute_summary` |

---

## Known Sticking Points & Bugs

### 1. CV must have a matching summary heading

`extract_summary()` (`cv_utils.py:16`) looks for `## Summary`, `## Profile`, or `## About` (case-insensitive). If none is found, it silently returns an empty string. The pipeline does not validate this early.

**Symptom:** DiffAgent produces an empty "original" in `cv_diff.md`.
**Fix/workaround:** Run `uv run job-agent check-config` before the first run, or ensure `data/cv.md` has one of the supported headings.

---

### 2. `substitute_summary()` skips `### subheadings`

`substitute_summary()` (`cv_utils.py:46`) stops "skipping" the old summary when it sees the next `## heading`. But `### subheadings` (triple hash) within the Summary section break this — the function keeps skipping until EOF, losing the rest of the CV.

**Symptom:** `cv_tailored.md` contains only the summary, nothing else.
**Fix:** Change line 71 in `cv_utils.py` from `line.startswith("## ")` to `line.startswith("#")` to stop at any heading level.

---

### 3. Markdown fence regex is too permissive

`BaseAgent._call()` (`agents.py:91`) strips markdown fences with:
```python
re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
```

If the LLM response contains multiple code blocks (e.g., an explanation followed by JSON), the first block — not the JSON — is extracted.

**Symptom:** JSON parse error on first attempt, usually self-corrects on retry.
**Fix:** After extraction, check that `json_str.strip().startswith("{")` before treating it as JSON.

---

### 4. ScoringRubric section weights are not validated before passing to Rescorer

The analyst produces `section_weights` (dict of section → float, must sum to 1.0). This is injected into the Rescorer prompt as a JSON string with no validation step.

**Symptom:** If the LLM returns weights that don't sum to 1.0 or are missing sections, the Rescorer silently uses broken weights, producing nonsensical score deltas.
**Fix:** Add a validation step in `RescorerAgent.run()`:
```python
total = sum(analysis.rubric.section_weights.values())
if abs(total - 1.0) > 0.05:
    raise ValueError(f"Rubric section_weights sum to {total:.2f}, expected 1.0")
```

---

### 5. No timeout on LLM calls

`ChatAnthropic` is initialised without an explicit timeout (`agents.py:44`). If the API hangs, the pipeline blocks indefinitely.

**Symptom:** Pipeline appears stuck with no output.
**Fix:** Pass `timeout=60` (or similar) when constructing `ChatAnthropic`.

---

### 6. API key config fails silently

`config.py:31` defaults `ANTHROPIC_API_KEY` to `""` rather than raising on startup. The failure only surfaces at the first LLM call.

**Symptom:** Confusing error deep inside LangChain rather than a clear "API key not set" message.
**Fix/workaround:** Always run `uv run job-agent check-config` before a real run.

---

### 7. WriterAgent hard gap constraint relies solely on prompt

The prompt tells WriterAgent not to address `hard_missing` gaps (`prompts.py:198`). There is no post-hoc validation that the new summary avoids injecting hard gap keywords.

**Symptom:** Occasional hallucination of experience the candidate doesn't have.
**Fix:** After `WriterAgent.run()` returns, scan `variant.summary_section` for any token in `analysis.hard_missing` and warn or fail.

---

## Testing

No API key needed — all LLM calls are mocked.

```bash
uv run pytest                                    # full suite with coverage
uv run pytest tests/test_cv_utils.py -v          # fast pure unit tests
uv run pytest tests/test_agents.py -v            # retry logic, schema validation
uv run pytest tests/test_pipeline.py -v          # gate control flow, vault writes
```

| Test file | What it covers |
|-----------|---------------|
| `test_cv_utils.py` | `extract_summary`, `substitute_summary` — pure string ops |
| `test_vault.py` | Markdown formatters, vault folder creation |
| `test_loaders.py` | CV and skills table loading |
| `test_agents.py` | JSON retry, schema retry, exponential backoff, correction prompt content |
| `test_pipeline.py` | Gate 1 / Gate 2 control flow, vault file writes, threshold override |

---

*Generated for job_agent — last updated 2026-03-08*
