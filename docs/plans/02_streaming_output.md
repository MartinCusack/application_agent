# Plan: Streaming Terminal Output

## Overview

Show token-by-token output for each agent run rather than a blank terminal wait. LangChain already supports streaming via `ChatAnthropic`'s `stream()` method. The challenge is reconciling streaming with the current JSON-validation-and-retry loop in `BaseAgent._call()`.

---

## Feature Dependency Diagram

```
[No upstream dependencies]

  BaseAgent._call() (agents.py)
      │
      ├── Currently: llm.invoke()  — blocks until full response
      └── New:       llm.stream()  — yields token chunks
            │
            ▼
        Accumulated raw string
            │
            ▼
        Existing JSON parse + Pydantic validation (unchanged)
            │
            ▼
        Retry loop (unchanged)

[No downstream dependants — purely internal to agents.py]
```

---

## Technical Plan

### 1. Config flag (`config.py`)

Add `STREAM_OUTPUT: bool = Field(default=True)` read from `STREAM_OUTPUT` env var. Allows streaming to be disabled for CI/testing or piped output.

### 2. `BaseAgent._call()` change (`agents.py`)

Replace the single `self.llm.invoke(messages)` call with a conditional:

```python
if config.STREAM_OUTPUT:
    raw = self._stream_to_console(messages)
else:
    response = self.llm.invoke(messages)
    raw = response.content
```

New private method `_stream_to_console`:

```python
def _stream_to_console(self, messages: list[BaseMessage]) -> str:
    chunks: list[str] = []
    for chunk in self.llm.stream(messages):
        text = chunk.content
        print(text, end="", flush=True)
        chunks.append(text)
    print()  # newline after stream ends
    return "".join(chunks)
```

The accumulated `raw` string is then fed into the identical JSON-parse and retry logic — no changes needed there.

### 3. Retry loop interaction

On a retry, streaming should be suppressed for the correction attempt to avoid confusing interleaved output. Pass an `_streaming` flag into `_call` that is `True` only on the first attempt:

```python
for attempt in range(_MAX_RETRIES):
    use_stream = config.STREAM_OUTPUT and attempt == 0
    raw = self._stream_to_console(messages) if use_stream else self.llm.invoke(messages).content
```

### 4. Rich console integration

Wrap streamed output inside a `Live` context or print a labelled header before each agent:

```
─── Agent 1a response ─────────────────────
{"aggregate_score": 74, "section_scores": ...
```

Use `Console().print(Rule(f"[dim]{agent_name} streaming[/dim]"))` before the stream starts, so the output is clearly attributed.

### 5. Tests

Existing `test_agents.py` mocks `BaseAgent.llm.invoke` — these remain unaffected because `STREAM_OUTPUT` defaults to `False` in the test environment (set via `monkeypatch.setenv("STREAM_OUTPUT", "false")`).

Add `test_streaming.py`:

| Test | Approach |
|------|----------|
| Chunks accumulate correctly | Mock `llm.stream` yielding 3 chunks; assert joined string equals expected |
| Valid JSON still parsed after stream | Full happy-path with mock stream |
| Retry uses invoke not stream | Assert `llm.invoke` called on attempt 2+ |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Streamed output interleaves with Rich panel output | Medium | Call `console.print(Rule(...))` before streaming; streaming uses raw `print()` on the same stdout, which Rich handles correctly when `Console(force_terminal=True)` is not set. Test manually. |
| `lm.stream()` not supported on all LangChain versions | Low | Already in `langchain-anthropic>=0.1`. Pin minimum version in `pyproject.toml`. |
| JSON streamed across chunk boundaries breaks naive parse | Not applicable | Full accumulation before parsing — no chunk-by-chunk JSON parsing attempted. |
| Streaming in non-TTY contexts (piped output, CI) | Medium | Check `sys.stdout.isatty()` and override `STREAM_OUTPUT` to `False` automatically when not a TTY. |
| Streaming adds noise to test output | Medium | `STREAM_OUTPUT=false` in test env config resolves this entirely. |
