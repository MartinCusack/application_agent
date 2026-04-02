# Plan: URL Input for Job Descriptions

## Overview

Accept a `--jd-url` CLI flag that scrapes, cleans, and normalises a job description from a URL instead of requiring manual copy-paste. Removes the friction of the current interactive stdin flow and ensures consistent input formatting across all pipeline runs.

---

## Feature Dependency Diagram

```
[No upstream dependencies]

  CLI (cli.py)
      │
      ▼
  JD Scraper (new: scraper.py)
  ├── requests / httpx  — HTTP fetch
  ├── BeautifulSoup     — HTML parse
  └── readability-lxml  — main-content extraction
      │
      ▼
  Cleaned JD text
      │
      ▼
  run_pipeline() — existing, unchanged

[Downstream dependant features]
  └── 04_linkedin_integration.md  (reuses scraper.py)
  └── 06_company_research_agent.md (reuses HTTP fetch logic)
```

---

## Technical Plan

### 1. New dependency additions (`pyproject.toml`)

```toml
httpx = ">=0.27"
beautifulsoup4 = ">=4.12"
readability-lxml = ">=0.8"
lxml = ">=5.0"
```

`httpx` is preferred over `requests` for async readiness; sync usage here, async later for batch mode.

### 2. New module: `job_agent/scraper.py`

Single public function:

```python
def fetch_job_description(url: str) -> str:
    """Fetch a URL, extract the main article content, return cleaned plain text."""
```

Implementation steps inside `fetch_job_description`:

1. `httpx.get(url, follow_redirects=True, timeout=15, headers={"User-Agent": "..."})` — polite UA string to avoid trivial bot blocks
2. Raise `ScraperError` (custom exception) if status >= 400
3. Pass `response.text` to `readability.Document` — extracts main content, strips nav/footer/ads
4. Parse the summary HTML with `BeautifulSoup(doc.summary(), "lxml")`
5. Call `soup.get_text(separator="\n")` — plain text with line breaks preserved
6. Strip consecutive blank lines (regex `\n{3,}` → `\n\n`)
7. Return cleaned string

Custom exception class in `scraper.py`:

```python
class ScraperError(RuntimeError):
    """Raised when a URL cannot be fetched or yields no extractable content."""
```

### 3. CLI change (`cli.py`)

Add `--jd-url` option to the `apply` command:

```python
jd_url: Optional[str] = typer.Option(None, "--jd-url", "-u", help="URL to scrape JD from")
```

Input resolution order (first wins):

1. `--jd-file` — existing file flag
2. `--jd-url` — new URL flag (calls `fetch_job_description`)
3. Interactive stdin — existing fallback

Add a `[green]Scraped JD from {url} ({len} chars)[/green]` Rich console print after successful fetch.

### 4. `check-config` update

Add a connectivity check: attempt `httpx.head("https://example.com", timeout=5)` and print `✅ Network reachable` or `❌ Network unreachable`.

### 5. Tests (`tests/test_scraper.py`)

| Test | Approach |
|------|----------|
| Happy path | `respx` mock returning fixture HTML; assert keywords present in output |
| 404 response | Assert `ScraperError` raised |
| Timeout | Mock `httpx.TimeoutException`; assert `ScraperError` raised |
| Content extraction | Use real static HTML fixture; assert nav text absent from output |
| Blank content | Mock returning empty body; assert `ScraperError` raised |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Anti-scraping blocks (Cloudflare, JS-rendered pages) | High for LinkedIn/Greenhouse | Document clearly; these require the `--jd-file` fallback. Plan 04 covers board-specific APIs. |
| `readability-lxml` removes too much content | Medium | Log raw char count before/after extraction. If < 200 chars, raise `ScraperError` with a hint to use `--jd-file`. |
| `lxml` C extension fails to install on some platforms | Low | Fallback to `html.parser` in BeautifulSoup if lxml import fails. |
| JD text truncated by paywall | Medium | No mitigation at scraper level; pipeline analyst will surface a low score with vague gaps — user will notice. |
| URL contains PII in query string (tracking params) | Low | Strip query params before logging the URL to vault. |
