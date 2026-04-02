# Plan: Interview Prep Agent

## Overview

A post-Gate-2 agent that uses the gap analysis, rescore result, and JD to generate likely interview questions with suggested answer frameworks citing the candidate's actual experience. Produces `interview_prep.md` in the vault.

---

## Feature Dependency Diagram

```
[Depends on]
  └── Agent 1a output: AnalysisResult (hard/soft gaps, transferable strengths)
  └── Agent 3b output: RescorerResult (soft_gaps_remaining, regressions)
  └── PipelineState: job_description, cv_text

  Gate 2 (gate_passed == True)
      │
      ▼
  Agent 4: InterviewPrepAgent (new)
      │
      ├── Input: JD + AnalysisResult + RescorerResult + cv_text
      ├── LLM: generates questions + answer frameworks
      │
      ▼
  InterviewPrepResult (new Pydantic model)
      │
      ▼
  vault: interview_prep.md

[Optional: also runs on --force pipelines or via standalone command]
```

**Updated pipeline flow:**

```
Gate 2 pass
    ↓
Agent 4: InterviewPrepAgent  ← NEW
    ↓
Write status.md · DONE
```

---

## Technical Plan

### 1. New Pydantic models (`models.py`)

```python
class InterviewQuestion(BaseModel):
    question: str
    question_type: str          # "behavioural" | "technical" | "gap-probe" | "culture"
    why_likely: str             # why this question is likely given the JD / gap analysis
    answer_framework: str       # STAR/CAR prompt or technical talking points
    evidence_to_cite: list[str] # specific CV items or skills rows to reference

class InterviewPrepResult(BaseModel):
    role: str
    company: str
    questions: list[InterviewQuestion]
    preparation_notes: list[str]   # general advice for this specific role/company
    gap_probe_warnings: list[str]  # likely probes on hard gaps — candidate should prepare
```

Add `interview_prep: Optional[InterviewPrepResult] = None` to `PipelineState`.

### 2. New prompts (`prompts.py`)

```
INTERVIEW_PREP_SYSTEM: You are a senior interview coach specialising in technical roles. You generate realistic interview questions based on the job description and the candidate's specific gap profile. You never invent CV content — answer frameworks cite only what exists in the candidate's materials.

INTERVIEW_PREP_HUMAN:
Role: {role}, Company: {company}

Job Description:
{job_description}

Candidate Profile:
{cv_text}

Gap Analysis:
Hard gaps: {hard_missing}
Soft gaps remaining: {soft_gaps_remaining}
Regressions: {regressions}
Transferable strengths: {transferable_strengths}

Generate 8-12 interview questions covering:
- 3-4 behavioural questions targeting the most important JD competencies
- 2-3 technical questions probing the role's core technical requirements
- 1-2 gap-probe questions likely to arise from hard or soft gaps
- 1-2 culture/motivation questions inferred from JD tone and company signals

For each question: explain why it is likely, provide an answer framework, and list specific evidence from the CV to cite.
```

### 3. New agent class (`agents.py`)

```python
class InterviewPrepAgent(BaseAgent):
    def run(
        self,
        cv_text: str,
        job_description: str,
        company: str,
        role: str,
        analysis: AnalysisResult,
        rescore: RescorerResult,
    ) -> InterviewPrepResult:
```

### 4. Pipeline integration (`pipeline.py`)

Insert after Gate 2 pass, before `write_to_vault("status.md", ...)`:

```python
# ── Agent 4: Interview Prep ────────────────────────────────────────
console.print(Panel("🎯 Agent 4: Interview Prep", style="bold cyan"))
interview_prep = InterviewPrepAgent().run(
    cv_text=cv_text,
    job_description=job_description,
    company=company,
    role=role,
    analysis=analysis,
    rescore=rescore,
)
state.interview_prep = interview_prep
write_to_vault(vault_folder, "interview_prep.md", format_interview_prep(interview_prep))
```

Add `--skip-interview-prep` flag to `apply` command for users who want to disable it.

### 5. Vault formatter (`vault.py`)

```python
def format_interview_prep(result: InterviewPrepResult) -> str:
```

Renders: section per question type → each question as H3 with why-likely, answer framework, and evidence bullets. Closes with preparation notes and gap-probe warnings.

### 6. Standalone command

```python
@app.command()
def prep(
    run_path: Path = typer.Argument(..., help="Path to vault run folder"),
) -> None:
    """Generate interview prep for an existing vault run."""
```

Loads `pipeline_state.json` (from Plan 07 sidecar, if implemented) or re-reads `match_report.md` and `rescore_report.md` from the vault folder.

### 7. Tests

| Test | Approach |
|------|----------|
| Agent returns validated result | Mock LLM; assert `InterviewPrepResult` with 8-12 questions |
| Gap-probe questions reference hard gaps | Assert at least one question with `question_type == "gap-probe"` when hard gaps present |
| Agent runs after Gate 2 pass in pipeline | Mock all agents; assert `interview_prep` non-None on `state` |
| `--skip-interview-prep` skips agent | Assert `InterviewPrepAgent` never instantiated |
| Vault file written | Assert `interview_prep.md` present |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Questions are generic and not role-specific | Medium | Prompt explicitly references gap analysis and JD signals. If `data_quality` is poor, questions will reflect sparse input — this is expected behaviour. |
| Answer frameworks reference non-existent CV items | Medium | Prompt instructs agent to cite only what exists in `cv_text`. `skills_rows_cited` pattern from WriterAgent enforced here too. |
| Adding Agent 4 to every successful run increases cost | Low | Agent is optional (`--skip-interview-prep`). Prompt is medium-length; cost is ~$0.01 per run at Sonnet pricing. |
| Only runs on Gate 2 pass — misses partial runs | Low | Standalone `prep` command covers this case. User can run prep on any vault folder regardless of gate outcome. |
| Interview questions may vary dramatically between runs | Low | Seed the question generation with the fixed `ScoringRubric` keywords to anchor the output. |
