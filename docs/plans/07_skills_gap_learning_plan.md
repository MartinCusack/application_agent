# Plan: Skills Gap Learning Plan Agent

## Overview

A post-pipeline agent that aggregates hard gaps flagged across multiple failed or low-scoring pipeline runs and generates a prioritised upskilling plan with resource recommendations. Turns rejected applications into a structured development roadmap.

---

## Feature Dependency Diagram

```
[Depends on]
  └── Application tracker (list-applications — already shipped)
  └── Vault structure (status.md + match_report.md — already exist)

  vault/*.md (historical runs)
      │
  GapAggregator (new: gap_aggregator.py)
      │  reads match_report.md from N past runs
      │  aggregates hard/soft gaps by frequency
      ▼
  AggregatedGapReport (new Pydantic model)
      │
  LearningPlanAgent (new, runs on-demand — not part of apply pipeline)
      │
      ▼
  LearningPlanResult (new Pydantic model)
      │
      ▼
  vault root: skills_gap_learning_plan.md (updated on each invocation)

  CLI: job-agent learning-plan (new command)
```

---

## Technical Plan

### 1. New Pydantic models (`models.py`)

```python
class GapFrequency(BaseModel):
    keyword: str
    gap_type: str               # "hard" | "soft"
    frequency: int              # how many runs flagged this gap
    roles: list[str]            # which role titles flagged it
    addressable: bool           # OR of addressable_with_existing_skills across runs

class AggregatedGapReport(BaseModel):
    total_runs_analysed: int
    date_range: str             # "2024-11-01 to 2025-01-15"
    top_hard_gaps: list[GapFrequency]
    top_soft_gaps: list[GapFrequency]

class LearningResource(BaseModel):
    title: str
    url: Optional[str] = None
    type: str                   # "course", "book", "project", "certification"
    estimated_time: str         # e.g. "10 hours", "3 months"

class LearningPlanItem(BaseModel):
    skill: str
    priority: int               # 1 = highest
    rationale: str              # why this skill matters most given the gap data
    resources: list[LearningResource]
    quick_win: bool             # addressable in < 1 month

class LearningPlanResult(BaseModel):
    generated_at: str
    based_on_runs: int
    items: list[LearningPlanItem]
    executive_summary: str
```

### 2. Gap aggregator (`job_agent/gap_aggregator.py`)

```python
def aggregate_gaps(vault_path: Path, min_runs: int = 2) -> AggregatedGapReport:
    """Scan vault, parse match_report.md files, aggregate hard/soft gaps by frequency."""
```

Implementation:
1. `vault_path.rglob("match_report.md")` — find all reports
2. Parse each file: extract hard/soft gap tables using regex on the markdown output of `format_analysis_report`. This is brittle — see Risk 1.
3. Better approach: if `status.md` contains a `run_id`, use it to look up a JSON sidecar file (see below).

#### JSON sidecar approach (preferred)

After each pipeline run, write a `pipeline_state.json` sidecar to the vault folder containing a serialised subset of `PipelineState`:

```python
write_to_vault(
    vault_folder,
    "pipeline_state.json",
    state.model_dump_json(include={"analysis", "rescore_result", "company", "role", "created_at"})
)
```

`aggregate_gaps` then loads `pipeline_state.json` files — structured, no markdown parsing needed. This also enables `list-applications` to be more accurate (no regex parsing of `status.md`).

Note: the sidecar approach is a two-step change — first add the sidecar write to `pipeline.py`, then build the aggregator on top of it.

### 3. New agent class (`agents.py`)

```python
class LearningPlanAgent(BaseAgent):
    def run(self, gap_report: AggregatedGapReport, cv_text: str) -> LearningPlanResult:
```

Prompt instructs the LLM to:
- Prioritise hard gaps that appear in 2+ runs
- Prefer gaps flagged as `addressable_with_existing_skills = True` for quick wins
- Recommend specific, named resources (courses, books, projects)
- Group by timeline: immediate (< 1 month), short (1–3 months), long (3–6 months)

### 4. New CLI command (`cli.py`)

```python
@app.command()
def learning_plan(
    min_runs: int = typer.Option(2, "--min-runs", help="Minimum times a gap must appear to be included"),
    output: Optional[Path] = typer.Option(None, "--output", help="Output file path (default: vault root)"),
) -> None:
    """Generate a prioritised upskilling plan from historical gap analysis."""
```

### 5. Vault formatter (`vault.py`)

```python
def format_learning_plan(result: LearningPlanResult) -> str:
```

Renders: executive summary → prioritised table (skill, priority, timeline, quick win) → detailed items with resources.

### 6. Tests

| Test | Approach |
|------|----------|
| `aggregate_gaps` with 3 fixture JSONs | Assert gap frequencies counted correctly |
| `aggregate_gaps` with 0 runs | Assert graceful empty result with warning |
| `LearningPlanAgent` returns validated result | Mock LLM; assert `LearningPlanResult` |
| CLI command integration | Mock aggregator + agent; assert vault file written |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Markdown parsing of existing match_report.md files is fragile | High | Prefer the JSON sidecar approach. Adds a backward-compatibility gap for runs made before this feature — document that the learning plan only considers runs made after sidecar support is added. |
| LLM recommends non-existent or outdated resources | Medium | Prompt explicitly asks for named, verifiable resources. Mark `url` as Optional — user expected to verify. Consider using web search (Tavily) to ground resource recommendations. |
| Too few runs to generate a meaningful plan | Low | `min_runs` threshold (default 2) filters noise. If fewer than 2 runs exist, print a helpful message: "Run the pipeline on at least 2 roles first." |
| Pipeline sidecar write adds I/O to every run | Low | JSON write is negligible cost. Serialises only a subset of `PipelineState`. |
| Learning plan goes stale as skills are acquired | Low | Each invocation regenerates from latest vault data. Old plan is overwritten. |
