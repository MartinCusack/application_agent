# Plan: Per-Agent Model Configuration

## Overview

Allow each agent to use a different model via `.env` configuration. The analyst and rescorer benefit from higher reasoning capacity (Opus); the diff agent is simple and can use Haiku to reduce cost.

---

## Feature Dependency Diagram

```
[No upstream dependencies]

  config.py
      │  reads per-agent model env vars
      ▼
  AgentModelConfig (new dataclass in config.py)
      │
      ├── ANALYST_MODEL   → AnalystAgent
      ├── COVER_LETTER_MODEL → CoverLetterAgent
      ├── WRITER_MODEL    → WriterAgent
      ├── DIFF_MODEL      → DiffAgent
      └── RESCORER_MODEL  → RescorerAgent

  BaseAgent.__init__(model=...)  — already accepts model param
      │
      ▼
  No changes to pipeline.py needed (agents instantiated with explicit model)
```

---

## Technical Plan

### 1. Config additions (`config.py`)

Extend `Config` with per-agent model fields, all defaulting to `MODEL_NAME`:

```python
class Config(BaseSettings):
    MODEL_NAME: str = "claude-sonnet-4-6"   # existing global default

    # Per-agent overrides — fall back to MODEL_NAME if not set
    ANALYST_MODEL: Optional[str] = None
    COVER_LETTER_MODEL: Optional[str] = None
    WRITER_MODEL: Optional[str] = None
    DIFF_MODEL: Optional[str] = None
    RESCORER_MODEL: Optional[str] = None

    @property
    def analyst_model(self) -> str:
        return self.ANALYST_MODEL or self.MODEL_NAME

    # ... one property per agent
```

Properties centralise the fallback logic so no conditional appears in pipeline code.

### 2. Pipeline instantiation (`pipeline.py`)

Replace:

```python
analysis = AnalystAgent().run(...)
```

With:

```python
analysis = AnalystAgent(model=config.analyst_model).run(...)
```

One change per agent instantiation — 5 lines total. `BaseAgent.__init__` already accepts `model: str`, so no agent-level changes needed.

### 3. `.env.example` additions

```bash
# Per-agent model overrides (optional — all default to MODEL_NAME)
# ANALYST_MODEL=claude-opus-4-6      # Recommended: higher reasoning for scoring
# RESCORER_MODEL=claude-opus-4-6     # Recommended: same model as analyst for rubric consistency
# DIFF_MODEL=claude-haiku-4-5-20251001  # Recommended: cheap, simple task
```

Add comments explaining the rationale for each recommendation.

### 4. `check-config` update (`cli.py`)

Print effective model per agent:

```
  Analyst model:      claude-opus-4-6   (override)
  Cover letter model: claude-sonnet-4-6 (default)
  Writer model:       claude-sonnet-4-6 (default)
  Diff model:         claude-haiku-4-5  (override)
  Rescorer model:     claude-opus-4-6   (override)
```

Helps the user verify configuration before spending tokens.

### 5. Streaming alignment note

If Plan 02 (streaming) is implemented, streaming behaviour is per-agent — higher model tier agents may stream visibly more slowly. No special handling needed.

### 6. Tests

| Test | Approach |
|------|----------|
| Config properties return correct models | Unit test: set env vars; assert each property returns expected value |
| Fallback to MODEL_NAME when override absent | Assert property returns `MODEL_NAME` when per-agent var is unset |
| Pipeline passes per-agent model to each agent | Mock `BaseAgent.__init__`; assert `model` kwarg matches config |
| `check-config` prints effective model per agent | Capture stdout; assert all 5 agent names present |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Analyst and rescorer using different model families produces criterion drift | Medium | Document in `.env.example` that `ANALYST_MODEL` and `RESCORER_MODEL` should use the same model. The `ScoringRubric` passthrough already guards against prompt drift — model difference is a secondary concern. |
| Haiku used for analyst produces lower-quality gap analysis | Low | Default is `MODEL_NAME` (Sonnet). User must explicitly configure Haiku for a specific agent. |
| Model IDs go stale as Anthropic releases new versions | Low | Config is user-controlled. `check-config` prints the resolved model ID, making stale IDs visible. |
| OpenAI provider path ignores per-agent overrides | Low | All agent model properties route through `_build_llm(model)` which already handles the provider switch. Per-agent config is provider-agnostic. |
