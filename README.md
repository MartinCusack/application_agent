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
```

---

## Folder Structure

No logic lives in `__init__.py`. Every file has a single responsibility.

```
job_agent/
├── job_agent/
│   ├── __init__.py              ← empty (package marker only)
│   ├── agents.py                ← all agent classes (AnalystAgent, WriterAgent …)
│   ├── cli.py                   ← Typer CLI entry point (apply, list-applications, check-config)
│   ├── config.py                ← env-var config (API key, paths, threshold)
│   ├── cv_utils.py              ← pure string helpers (extract_summary, substitute_summary)
│   ├── loaders.py               ← file I/O (load_cv, load_skills_table → markdown)
│   ├── models.py                ← Pydantic schemas for every agent input/output
│   ├── pipeline.py              ← orchestrator (threads PipelineState through all agents)
│   ├── prompts.py               ← all LLM prompt strings (edit here to tune behaviour)
│   └── vault.py                 ← Obsidian I/O + markdown formatters
│
├── tests/
│   ├── conftest.py              ← shared fixtures (sample CV, model instances)
│   ├── test_agents.py           ← LLM mocked; tests JSON parsing + schema validation
│   ├── test_cv_utils.py         ← pure unit tests; no mocking needed
│   ├── test_loaders.py          ← filesystem tests via tmp_path
│   ├── test_pipeline.py         ← all agents mocked; tests control flow + early exits
│   └── test_vault.py            ← formatter purity + file I/O via tmp_path
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

---

## Configuration

All config lives in `.env`. Copy `.env.example` to get started.

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required. Your Anthropic API key. |
| `CV_PATH` | `data/cv.md` | Path to your master CV file. |
| `SKILLS_TABLE_PATH` | `data/skills.xlsx` | Path to your skills Excel table. |
| `OBSIDIAN_VAULT_PATH` | `~/obsidian/Applications` | Root folder for vault output. |
| `MATCH_SCORE_THRESHOLD` | `65` | Minimum score to proceed past analysis. |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Model for all agents. Use `claude-opus-4-6` for higher quality. |

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

**LinkedIn / job board integration** — pull job descriptions directly from LinkedIn, Indeed, or Greenhouse. Feed them into a batch mode that queues multiple roles and runs the pipeline overnight.

**Salary benchmarking agent** — Agent 0 that searches Glassdoor/Levels.fyi for salary data before the main pipeline runs. Writes a benchmark note so you can negotiate from a position of knowledge.

**Company research agent** — pre-pipeline agent that searches recent news, financials, and Glassdoor reviews for the target company. Injects context into the Interviewer so model answers can reference the company's actual priorities.

**Skills gap learning plan** — post-pipeline agent that takes all hard gaps flagged across multiple failed runs and generates a prioritised upskilling plan with resource recommendations. Turns rejected applications into a structured development roadmap.

**DOCX / PDF export** — export the tailored CV from markdown to a DOCX or PDF with consistent formatting.