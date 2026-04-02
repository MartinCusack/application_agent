# Plan: Salary Benchmarking Agent (Agent 0)

## Overview

A pre-pipeline agent (Agent 0) that searches salary data sources for the target role and company before the main pipeline runs. Writes a `salary_benchmark.md` to the vault so the candidate can negotiate from a position of knowledge.

---

## Feature Dependency Diagram

```
[No upstream dependencies]

  CLI apply command (cli.py)
      │  --skip-salary flag (optional bypass)
      ▼
  Agent 0: SalaryBenchmarkAgent (new)
      │
      ├── Web search: Glassdoor, Levels.fyi, LinkedIn Salary, Payscale
      ├── LLM synthesis: extracts structured salary range from search results
      │
      ▼
  SalaryBenchmarkResult (new Pydantic model)
      │
      ▼
  vault: salary_benchmark.md  (written before Agent 1a runs)
      │
      ▼
  Existing pipeline continues unchanged (Agent 1a → ... → 3b)

[Optional: salary data injected into Agent 1a's context to inform proceed decision]
```

---

## Technical Plan

### 1. New Pydantic model (`models.py`)

```python
class SalaryRange(BaseModel):
    low: Optional[int] = None        # annual, GBP/USD
    mid: Optional[int] = None
    high: Optional[int] = None
    currency: str = "GBP"
    source: str                      # "Glassdoor", "Levels.fyi", etc.
    notes: str

class SalaryBenchmarkResult(BaseModel):
    role: str
    location: str
    ranges: list[SalaryRange]
    recommended_ask: Optional[int] = None
    negotiation_notes: list[str]
    data_quality: str                # "high" | "medium" | "low" — LLM self-assessment
```

Add `salary_benchmark: Optional[SalaryBenchmarkResult] = None` to `PipelineState`.

### 2. New agent class (`agents.py`)

```python
class SalaryBenchmarkAgent(BaseAgent):
    def run(self, role: str, company: str, location: str, job_description: str) -> SalaryBenchmarkResult:
```

#### Approach — tool use vs web search

Two options, ordered by preference:

**Option A (preferred): LangChain web search tool**

Use `langchain_community.tools.TavilySearchResults` (requires `TAVILY_API_KEY`) or `DuckDuckGoSearchRun` (no key required). Perform 2–3 targeted searches:

```
"{role}" salary {location} site:glassdoor.com
"{role}" salary {location} levels.fyi
"{role}" total compensation {company}
```

Concatenate result snippets, pass to LLM to extract structured `SalaryBenchmarkResult`.

**Option B (fallback):** Pass role + JD to LLM with a prompt asking it to reason about expected market rate from its training data. Clearly mark `data_quality = "low"` and note the data is from training cutoff, not live.

Implement both. If `TAVILY_API_KEY` is set, use Option A. Otherwise use Option B with a console warning.

### 3. New prompt (`prompts.py`)

```
SALARY_SYSTEM: You are a compensation analyst. Extract salary data from search results. Always express as annual gross. Convert to the candidate's preferred currency if possible.

SALARY_HUMAN: Role: {role}, Company: {company}, Location: {location}

Search results:
{search_results}

Extract salary ranges and negotiation notes. Be conservative — report what the data actually shows. Flag if data is sparse or unreliable.
```

### 4. Pipeline integration (`pipeline.py`)

Insert Agent 0 before Agent 1a:

```python
# ── Agent 0 (optional) ────────────────────────────────────────────
if not skip_salary:
    console.print(Panel("💰 Agent 0: Salary Benchmark", style="bold blue"))
    salary_result = SalaryBenchmarkAgent().run(role, company, location, job_description)
    state.salary_benchmark = salary_result
    write_to_vault(vault_folder, "salary_benchmark.md", format_salary_benchmark(salary_result))
```

`location` extracted from JD via a simple regex/LLM call, or accepted as a new `--location` CLI flag (optional, defaults to `"UK"`).

### 5. Vault formatter (`vault.py`)

```python
def format_salary_benchmark(result: SalaryBenchmarkResult) -> str:
```

Renders a markdown table of salary ranges by source, recommended ask, and negotiation notes.

### 6. Config additions (`.env.example`)

```
TAVILY_API_KEY=           # Optional. If set, enables live salary search (Option A).
SALARY_DEFAULT_LOCATION=UK
```

### 7. Tests

| Test | Approach |
|------|----------|
| Agent runs with Tavily mocked | Mock search tool + LLM; assert `SalaryBenchmarkResult` returned |
| Agent runs in fallback mode | Set `TAVILY_API_KEY=""` in env; assert `data_quality == "low"` |
| `--skip-salary` skips Agent 0 | Assert agent never instantiated |
| Vault file written | Assert `salary_benchmark.md` present in vault folder |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Salary data from search is noisy / irrelevant | High | LLM synthesises and flags `data_quality`; output includes source attribution per range. User can discard low-quality results. |
| Tavily API adds another paid dependency | Medium | DuckDuckGo fallback requires no key. Document both options clearly. |
| LLM fabricates salary figures from training data (Option B) | High | Mark Option B output with a prominent "estimated from model training data — verify independently" warning in the vault file. |
| Adding Agent 0 increases total pipeline cost | Low | Agent 0 is optional (`--skip-salary`). Search results are short; prompt is small. |
| Location extraction from JD is inaccurate | Medium | Prefer the explicit `--location` CLI flag. JD-based extraction is a best-effort fallback with a warning if no location found. |
