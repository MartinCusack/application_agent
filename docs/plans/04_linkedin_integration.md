# Plan: LinkedIn / Job Board Integration

## Overview

Pull job descriptions directly from LinkedIn, Indeed, and Greenhouse without manual copy-paste. Extends Plan 01 (URL input) with board-specific parsers and adds a batch mode that queues multiple roles and runs the pipeline sequentially.

---

## Feature Dependency Diagram

```
[Depends on]
  └── 01_url_input.md — scraper.py base fetch logic

  scraper.py (extended)
      │
      ├── LinkedInScraper
      ├── IndeedScraper
      └── GreenhouseScraper  (public JSON API — no auth)
            │
            ▼
        Cleaned JD text
            │
            ▼
        run_pipeline() (unchanged)

  Batch mode (new CLI command: job-agent batch)
      │
      ├── Reads batch input file (JSON or CSV)
      ├── Queues runs sequentially
      └── Writes summary table to vault root
```

---

## Technical Plan

### 1. Board-specific scrapers (`job_agent/scraper.py` extension)

Each board has a dedicated parser class. All inherit from a `BaseJobScraper` protocol:

```python
class BaseJobScraper(Protocol):
    def fetch(self, url: str) -> str: ...
```

#### Greenhouse (`boards.greenhouse.io`)

Greenhouse has a public JSON API — no auth, no scraping needed:

```
GET https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}
```

Parse `job.content` (HTML) through BeautifulSoup `get_text()`. Extract from URL via regex.

#### Indeed

Indeed aggressively blocks scrapers. Approach: attempt `httpx.get` with a modern User-Agent; if response is a CAPTCHA page (detect by checking for `<title>` containing "Just a moment" or "Are you a robot"), raise `ScraperError` with message directing user to `--jd-file`.

#### LinkedIn

LinkedIn requires login for most JD pages. Approach: attempt public fetch; if redirect to login page detected (URL contains `linkedin.com/login`), raise `ScraperError` with clear message. LinkedIn integration is documented as best-effort; `--jd-url` with a public LinkedIn job URL sometimes works for unauthenticated pages.

#### Auto-detection

```python
def fetch_job_description(url: str) -> str:
    if "greenhouse.io" in url:
        return GreenhouseScraper().fetch(url)
    if "linkedin.com" in url:
        return LinkedInScraper().fetch(url)
    if "indeed.com" in url:
        return IndeedScraper().fetch(url)
    return GenericScraper().fetch(url)  # Plan 01 logic
```

### 2. Batch mode CLI command (`cli.py`)

```python
@app.command()
def batch(
    input_file: Path = typer.Argument(..., help="JSON or CSV file of roles to process"),
    threshold: Optional[int] = typer.Option(None, "--threshold"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Run the pipeline for multiple roles from a batch input file."""
```

#### Input file format (JSON)

```json
[
  {"company": "Acme Corp", "role": "Senior DS", "url": "https://..."},
  {"company": "Beta Ltd",  "role": "ML Engineer", "jd_file": "beta.txt"}
]
```

Each entry supports `url` or `jd_file` — same resolution logic as `apply`.

#### Execution

Runs are sequential, not concurrent — LLM API rate limits and cost make parallelism undesirable. After all runs, print the standard `list-applications` Rich table filtered to today's date.

### 3. Summary output

Batch run writes `batch_summary_{date}.md` to vault root with a table of company, role, initial score, outcome (proceed/stopped/gate2-fail).

### 4. Tests

| Test | Approach |
|------|----------|
| Greenhouse URL parse | Mock `httpx.get` returning fixture JSON; assert cleaned text |
| LinkedIn login redirect | Mock redirect; assert `ScraperError` with helpful message |
| Auto-detection routing | Assert correct scraper class called per URL pattern |
| Batch: sequential execution | Mock `run_pipeline`; assert called once per entry |
| Batch: mixed url/file inputs | Assert both resolution paths work in single batch |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| LinkedIn/Indeed block all scraping | High | Document clearly; these boards are best-effort. Greenhouse (public API) is the reliable path. |
| Greenhouse API changes schema | Low | Validate response shape with Pydantic before extracting; fail fast with clear error. |
| Batch run burns tokens on bad JDs | Medium | Apply Gate 1 — low-scoring JDs exit early. Add `--dry-run` support to batch for pre-flight checks. |
| Rate limiting from Anthropic API during long batches | Medium | Existing exponential backoff in `BaseAgent._call` handles transient 529s. Add a configurable `BATCH_INTER_RUN_DELAY` (default 5s) between runs. |
| Board-specific HTML structure changes over time | Medium | Tests use fixture HTML, not live pages. Scraper failures surface as `ScraperError` with a fallback hint. |
