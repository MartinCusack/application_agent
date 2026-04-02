# Plan: Company Research Agent

## Overview

A pre-pipeline agent that searches recent news, financials, and culture signals for the target company before the main pipeline runs. The research context is injected into Agent 1a to enrich its analysis, and written to `company_research.md` in the vault.

---

## Feature Dependency Diagram

```
[No upstream dependencies — but benefits from 01_url_input.md's httpx dep]

  CLI apply command (cli.py)
      │  --skip-research flag (optional bypass)
      ▼
  Agent -1: CompanyResearchAgent (new)
      │
      ├── Web search: company name + recent news / funding / Glassdoor
      ├── LLM synthesis: extracts structured CompanyResearchResult
      │
      ▼
  CompanyResearchResult (new Pydantic model)
      │
      ├── vault: company_research.md (written before Agent 1a)
      │
      └── Injected as extra context into Agent 1a's human prompt
              │
              ▼
          Richer AnalysisResult (analyst references company priorities)
              │
              ▼
          Downstream agents unchanged
```

---

## Technical Plan

### 1. New Pydantic model (`models.py`)

```python
class CompanyResearchResult(BaseModel):
    company: str
    summary: str                       # 2-3 sentence company overview
    recent_news: list[str]             # last 3-6 months headlines
    growth_stage: str                  # e.g. "Series B", "public", "bootstrapped"
    glassdoor_signals: list[str]       # culture / management signals if findable
    tech_stack_signals: list[str]      # public signals from job ads / engineering blog
    key_priorities: list[str]          # inferred business priorities from news/JD
    data_quality: str                  # "high" | "medium" | "low"
    sources: list[str]                 # URLs or search result titles used
```

Add `company_research: Optional[CompanyResearchResult] = None` to `PipelineState`.

### 2. New agent class (`agents.py`)

```python
class CompanyResearchAgent(BaseAgent):
    def run(self, company: str, role: str, job_description: str) -> CompanyResearchResult:
```

Uses the same web search integration as Plan 05 (Tavily / DuckDuckGo fallback). Performs 3–4 searches:

```
"{company}" news 2024 2025
"{company}" glassdoor reviews culture
"{company}" funding series OR IPO OR acquisition
"{company}" engineering blog OR tech stack
```

Concatenates snippets and synthesises with LLM.

### 3. New prompts (`prompts.py`)

```
RESEARCH_SYSTEM: You are a business intelligence analyst. Extract factual, evidence-based signals about a company from search results. Do not speculate beyond what the sources say.

RESEARCH_HUMAN: Company: {company}, Role: {role}

Job Description signals:
{jd_excerpt}

Search results:
{search_results}

Extract: company overview, recent news, growth stage, culture signals, tech stack signals, and key business priorities. Cite each claim to a source.
```

### 4. Agent 1a prompt injection (`prompts.py` + `agents.py`)

Modify `ANALYST_HUMAN` to include an optional `{company_context}` section:

```
## Company Context (if available)
{company_context}
```

In `AnalystAgent.run()`, accept an optional `company_research: Optional[CompanyResearchResult]` parameter. If provided, serialise `key_priorities` + `tech_stack_signals` into the `company_context` slot. If not provided, slot is empty.

This is an additive change — `company_research=None` produces identical output to the current pipeline.

### 5. Pipeline integration (`pipeline.py`)

Insert before Agent 1a:

```python
company_research = None
if not skip_research:
    console.print(Panel("🔎 Agent -1: Company Research", style="bold blue"))
    company_research = CompanyResearchAgent().run(company, role, job_description)
    state.company_research = company_research
    write_to_vault(vault_folder, "company_research.md", format_company_research(company_research))

analysis = AnalystAgent().run(cv_text, skills_table, job_description, company_research=company_research)
```

### 6. Vault formatter (`vault.py`)

```python
def format_company_research(result: CompanyResearchResult) -> str:
```

Renders a structured markdown file: overview → news → growth stage → culture → tech stack → priorities → sources.

### 7. Tests

| Test | Approach |
|------|----------|
| Research agent with mocked search | Assert `CompanyResearchResult` returned with correct fields |
| Agent 1a with research context | Assert prompt contains company context string |
| Agent 1a without research context | Assert prompt slot is empty string — no regression |
| `--skip-research` bypasses agent | Assert `CompanyResearchAgent` never instantiated |
| Vault file written | Assert `company_research.md` present |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Search results for small/unknown companies are sparse | High | `data_quality = "low"` flag; vault file notes limitations. Agent 1a proceeds normally — company context is purely additive. |
| Injecting company context increases token cost for Agent 1a | Low | Research result is serialised selectively (only `key_priorities` + `tech_stack_signals`, not full result). Estimated < 300 tokens additional. |
| LLM hallucinates company details from training data | Medium | Prompt explicitly instructs "cite each claim to a source"; any uncited claim should be flagged `data_quality = "low"`. |
| Company name is ambiguous (e.g. "Atlas") | Medium | Include role and JD excerpt in search queries to disambiguate. If `data_quality = "low"`, warn user in console output. |
| Adds another optional agent that increases pipeline complexity | Low | Agent is opt-in via flag; no changes to existing control flow when skipped. |
