# Job Agent

An AI-powered multi-agent pipeline that analyses job descriptions against your CV, rewrites your summary, and rescores the result — writing everything to your Obsidian vault.

**Stack:** Python 3.11+ · UV · LangChain · Claude (Anthropic) · Pydantic v2 · Obsidian

---

## Quickstart

```bash
# 1. Install UV if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install project dependencies
cd job_agent && uv sync

# 3. Configure
cp .env.example .env && $EDITOR .env

# 4. Verify setup
uv run job-agent check-config
```

### Required data files

| File | Description |
|------|-------------|
| `data/cv.md` | Master CV in markdown. Must have a `## Summary`, `## Profile`, or `## About` heading. Never modified by the pipeline. |
| `data/skills.xlsx` | One row per skill. Columns: Skill, Category, Proficiency, Projects, Roles, Years. Agent 2 cites specific rows to prevent hallucination. See `data/skills_template.csv` for format. |

### CLI usage

```bash
# Paste JD interactively
uv run job-agent apply --company "Acme Corp" --role "Senior Data Scientist"

# Load JD from file
uv run job-agent apply -c "Acme" -r "DS" --jd-file jd.txt

# Override score threshold for this run only
uv run job-agent apply -c "Acme" -r "DS" --threshold 70

# Skip Gate 1 and produce CV + cover letter regardless of analyst recommendation
uv run job-agent apply -c "Acme" -r "DS" --force

# Show all applications with scores and status
uv run job-agent list-applications

# Filter by outcome
uv run job-agent list-applications --status Interview

# Process all JD files in the TODO queue
uv run job-agent batch-apply

# Dry run — list what would be processed without running anything
uv run job-agent batch-apply --dry-run

# Batch with a threshold override
uv run job-agent batch-apply --threshold 60
```

---

## Folder Structure

No logic lives in `__init__.py`. Every file has a single responsibility.

```
job_agent/
├── job_agent/
│   ├── __init__.py              ← empty (package marker only)
│   ├── agents.py                ← all agent classes (AnalystAgent, WriterAgent …)
│   ├── batch.py                 ← batch orchestrator (processes all JDs in TODO queue)
│   ├── cli.py                   ← Typer CLI entry point (apply, batch-apply, list-applications, check-config)
│   ├── config.py                ← env-var config (API key, paths, threshold, batch settings)
│   ├── cv_utils.py              ← pure string helpers (extract_summary, substitute_summary)
│   ├── jd_parser.py             ← JD file parser (frontmatter + filename convention)
│   ├── loaders.py               ← file I/O (load_cv, load_skills_table → markdown)
│   ├── models.py                ← Pydantic schemas for every agent input/output
│   ├── pipeline.py              ← orchestrator (threads PipelineState through all agents)
│   ├── prompts.py               ← all LLM prompt strings (edit here to tune behaviour)
│   └── vault.py                 ← Obsidian I/O + markdown formatters
│
├── tests/
│   ├── conftest.py              ← shared fixtures (sample CV, model instances)
│   ├── test_agents.py           ← LLM mocked; tests JSON parsing + schema validation
│   ├── test_batch.py            ← batch orchestrator + JD parser tests (no API calls)
│   ├── test_cv_utils.py         ← pure unit tests; no mocking needed
│   ├── test_loaders.py          ← filesystem tests via tmp_path
│   ├── test_pipeline.py         ← all agents mocked; tests control flow + early exits
│   └── test_vault.py            ← formatter purity + file I/O via tmp_path
│
├── job_descriptions/
│   ├── TODO/                    ← drop .md files here for batch-apply to process
│   ├── applied/                 ← moved here after passing both gates
│   ├── gated_out/               ← moved here after failing Gate 2 (low rescore)
│   ├── skipped/                 ← moved here after failing Gate 1 (analyst said no)
│   └── failed/                  ← moved here on pipeline error (.error.txt sidecar written)
│
├── data/
│   ├── cv.md                    ← YOUR master CV (add this)
│   ├── skills.xlsx              ← YOUR skills table (add this)
│   └── skills_template.csv      ← column reference for skills.xlsx
│
├── .env.example                 ← copy to .env and fill in values
├── pyproject.toml               ← UV deps + pytest config
└── README.md
```

### Design principles

**Separation of concerns** — prompts are isolated in `prompts.py` so you can tune agent behaviour without touching logic. Pure string operations live in `cv_utils.py` where they can be unit-tested cheaply with no mocking. Vault I/O is confined to `vault.py` so the pipeline stays filesystem-agnostic.

**Structured outputs** — every agent returns a validated Pydantic model, never a free-form string. The `ScoringRubric` produced by Agent 1a is passed verbatim to Agent 3b to prevent criterion drift between the original analysis and the rescore. The `PipelineState` object accumulates all outputs and is returned to the caller for inspection after any run, including early exits. If Claude returns malformed JSON or a schema mismatch, `BaseAgent._call` retries up to 3 times with exponential backoff, appending the bad response and a correction prompt to the conversation each time.

---

## Batch Apply

Process multiple job descriptions in one run. Drop `.md` files into `job_descriptions/TODO/` and run:

```bash
uv run job-agent batch-apply
```

Files are processed sequentially and moved to outcome subdirectories automatically.

### JD file format

Files can be plain markdown (company and role are inferred from the filename) or include a YAML frontmatter block to override defaults:

```markdown
---
company: Deel
role: Data Scientist
threshold: 60      # optional — overrides MATCH_SCORE_THRESHOLD for this job
force: false       # optional — bypass Gate 1 for this job only
---

[Paste the full job description here]
```

Filename convention (no frontmatter): `Company_Role_Words.md` — the first underscore-separated token becomes the company; remaining tokens join as the role.

```
Deel_Data_Scientist.md  →  company=Deel, role=Data Scientist
```

### Batch outcome directories

| Directory | When moved there |
|-----------|-----------------|
| `applied/` | Both gates passed |
| `gated_out/` | Passed Gate 1, failed Gate 2 (rescored below threshold) |
| `skipped/` | Failed Gate 1 (analyst recommended not applying) |
| `failed/` | Pipeline raised an exception; a `.error.txt` sidecar is written |

A `batch_run_{id}.md` summary and `batch_run_{id}.json` are written to the vault root after each batch.

### Batch CLI options

```bash
uv run job-agent batch-apply --dir path/to/other/dir   # custom queue dir
uv run job-agent batch-apply --threshold 55            # global threshold override
uv run job-agent batch-apply --force                   # skip Gate 1 for all jobs
uv run job-agent batch-apply --delay 5.0               # seconds between jobs
uv run job-agent batch-apply --dry-run                 # list files, do nothing
```

---

## Pipeline Flow

Agents run sequentially. Two gates can stop the pipeline early, writing a partial `status.md` so partial results are never lost.

```
┌─────────────────────────────────────────────────────────┐
│  LOAD INPUTS                                            │
│  Read cv.md + skills.xlsx · Create vault folder         │
│  Write job_description.md · Init PipelineState          │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  AGENT 1a — DEEP ANALYST                                │
│                                                         │
│  · Aggregate score (0–100)                              │
│  · Section scores: summary / experience / skills        │
│  · HARD missing  — genuinely lacking                    │
│  · SOFT missing  — have it, wrong phrasing              │
│  · ScoringRubric — forwarded unchanged to Agent 3b      │
│                                                         │
│  → match_report.md                                      │
└───────────────────────────┬─────────────────────────────┘
                            │
              ┌─────────────▼──────────────┐
              │  GATE 1                    │
              │  proceed == False?         │
              │  → write status.md · STOP  │
              └─────────────┬──────────────┘
                            │ proceed == True
                            ▼
┌─────────────────────────────────────────────────────────┐
│  AGENT 1b — COVER LETTER WRITER                         │
│                                                         │
│  · Extracts JD signals (mission, product, challenges)   │
│  · Fills bracketed placeholders in template             │
│  · Writes tailoring notes citing each JD signal used    │
│                                                         │
│  → cover_letter.md                                      │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  AGENT 2 — WRITER                                       │
│                                                         │
│  · Rewrites summary using Google XYZ formula            │
│  · Soft gaps addressed via rephrasing only              │
│  · Hard gaps explicitly blocked — cannot be touched     │
│  · Leadership-focused variant                           │
│  · Cites skills table rows used (no hallucination)      │
│                                                         │
│  → cv_tailored.md                                       │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  AGENT 2b — DIFF                                        │
│                                                         │
│  · Before/after comparison of summary section           │
│  · Lists every change + which gap it addresses          │
│  · Keeps master CV clean and auditable                  │
│                                                         │
│  → cv_diff.md                                           │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  AGENT 3b — RESCORER                                    │
│                                                         │
│  · Uses exact ScoringRubric from Agent 1a               │
│  · Per-section score deltas vs original                 │
│  · Flags regressions (sections that got worse)          │
│  · Evaluates pass/fail gate                             │
│                                                         │
│  → rescore_report.md                                    │
└───────────────────────────┬─────────────────────────────┘
                            │
              ┌─────────────▼──────────────┐
              │  GATE 2                    │
              │  gate_passed == False?     │
              │  → write status.md · STOP  │
              └─────────────┬──────────────┘
                            │ gate_passed == True
                            ▼
                    Write status.md · DONE
```

---

## Vault Output

Each run creates a dated subfolder under your Obsidian `Applications/` directory.

```
~/obsidian/Applications/
└── Acme_Corp_Senior_Data_Scientist_2025-01-15/
    ├── job_description.md        ← raw JD text (written at pipeline start)
    ├── match_report.md           ← Agent 1a: scores, hard/soft gap split, rubric
    ├── cover_letter.md           ← Agent 1b: tailored cover letter + JD signals used
    ├── cv_tailored.md            ← Agent 2: full CV with rewritten summary
    ├── cv_diff.md                ← Agent 2b: before/after + change log
    ├── rescore_report.md         ← Agent 3b: new scores, deltas, regressions
    └── status.md                 ← update manually as application progresses
```

Files are written incrementally — partial output exists even on a Gate 1 or Gate 2 exit, so a rejected run still gives you the gap analysis.

Update `status.md` manually as the application moves through stages:

```
Applied → Interview → Offer
Applied → Interview → Rejected
Applied → Rejected
Closed - Did Not Apply   (role filled, withdrawn, or decided not to proceed)
Dead Link                (job posting no longer exists)
```

---

## Testing

No API key is needed to run the test suite — all LLM calls are mocked.

```bash
# Full suite with coverage report
uv run pytest

# Fast pure-unit tests only (no mocking, no fixtures)
uv run pytest tests/test_cv_utils.py tests/test_vault.py tests/test_loaders.py -v

# Single file
uv run pytest tests/test_pipeline.py -v
```

| Test file | What it covers |
|-----------|----------------|
| `test_cv_utils.py` | Pure string ops — extract and substitute summary sections |
| `test_loaders.py` | File I/O via `tmp_path` — CV and Excel loading |
| `test_vault.py` | Markdown formatters + file write operations |
| `test_agents.py` | LLM mocked — JSON parsing, markdown fence stripping, schema validation, exponential backoff retry |
| `test_pipeline.py` | Control flow — Gate 1/2 early exits, variant selection, threshold override |
| `test_batch.py` | JD file parsing (frontmatter + filename), queue discovery, dry run, error isolation, file movement, result counts |

---

## Configuration

All config lives in `.env`. Copy `.env.example` to get started.

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required. Your Anthropic API key. |
| `CV_PATH` | `data/cv.md` | Path to your master CV file. |
| `SKILLS_TABLE_PATH` | `data/skills.xlsx` | Path to your skills Excel table. |
| `OBSIDIAN_VAULT_PATH` | `~/obsidian/Applications` | Root folder where the pipeline writes new application folders. |
| `OBSIDIAN_LIST_PATH` | _(same as `OBSIDIAN_VAULT_PATH`)_ | Root folder scanned by `list-applications`. Set to a parent directory if your vault organises applications across subdirectories. |
| `MATCH_SCORE_THRESHOLD` | `65` | Minimum score to proceed past analysis. |
| `MODEL_NAME` | `claude-sonnet-4-6` | Model for all agents. Use `claude-opus-4-6` for higher quality. |
| `BATCH_TODO_DIR` | `job_descriptions/TODO` | Directory scanned by `batch-apply` for pending JD files. |
| `BATCH_DELAY_SECONDS` | `2.0` | Pause between pipeline runs in batch mode to avoid API rate limits. |

### Example `.env`

```dotenv
# Model
MODEL_PROVIDER=anthropic
MODEL_NAME=claude-sonnet-4-6
ANTHROPIC_API_KEY=sk-ant-...

# Paths
CV_PATH=data/cv.md
SKILLS_TABLE_PATH=data/skills.xlsx
COVER_LETTER_TEMPLATE_PATH=data/cover_letter.md
COVER_LETTER_RUBRIC_PATH=data/cover_letter_rubric.md

# Obsidian vault
# OBSIDIAN_VAULT_PATH: where new application folders are created
OBSIDIAN_VAULT_PATH=~/Documents/vault/Job_hunt/job_applications/companies/
# OBSIDIAN_LIST_PATH: where list-applications scans for status.md files
# Set to a parent dir if your vault organises applications across subdirectories
OBSIDIAN_LIST_PATH=~/Documents/vault/Job_hunt/job_applications/application_status/

# Scoring
MATCH_SCORE_THRESHOLD=60

# Batch
BATCH_TODO_DIR=job_descriptions/TODO
BATCH_DELAY_SECONDS=2.0
```

---

## Roadmap

### Shipped

**Cover letter writer (Agent 1b)** ✅ — Runs after Gate 1. Extracts JD signals (mission, product, challenges) then fills bracketed placeholders in your cover letter template. Every claim in the output cites the JD signal it was drawn from. Writes to `cover_letter.md`.

**Application tracker dashboard** ✅ — `uv run job-agent list-applications` scans the vault, reads every `status.md`, and renders a Rich table with initial score, final score, delta, and colour-coded status (Applied / Interview / Offer / Rejected / Closed - Did Not Apply / Dead Link). Supports `--status` filtering.

### High priority

**URL input for job descriptions** — accept a URL instead of pasted text. Scrape and clean the JD automatically using BeautifulSoup + readability. Removes the manual copy-paste step and ensures consistent formatting for the analyst.

### Medium priority

**Streaming terminal output** — LangChain supports streaming responses. Show token-by-token output for long agent runs rather than a blank wait.

**Dry run mode** — `--dry-run` flag that prints what each agent would receive and produce without making any API calls. Useful for validating prompt templates and confirming the skills table is loading correctly before spending tokens.

### Low priority

**Batch apply** ✅ — `uv run job-agent batch-apply` processes all `.md` files in `job_descriptions/TODO/`, runs the full pipeline for each, and moves files to `applied/`, `gated_out/`, `skipped/`, or `failed/` depending on outcome. Supports YAML frontmatter for per-job threshold/force overrides. Writes a `batch_run_{id}.md` and `.json` summary to the vault.

**LinkedIn / job board integration** — pull job descriptions directly from LinkedIn, Indeed, or Greenhouse.

**Salary benchmarking agent** — Agent 0 that searches Glassdoor/Levels.fyi for salary data before the main pipeline runs. Writes a benchmark note so you can negotiate from a position of knowledge.

**Company research agent** — pre-pipeline agent that searches recent news, financials, and Glassdoor reviews for the target company. Injects context into the Interviewer so model answers can reference the company's actual priorities.

**Skills gap learning plan** — post-pipeline agent that takes all hard gaps flagged across multiple failed runs and generates a prioritised upskilling plan with resource recommendations. Turns rejected applications into a structured development roadmap.

**DOCX / PDF export** — export the tailored CV from markdown to a DOCX or PDF with consistent formatting.