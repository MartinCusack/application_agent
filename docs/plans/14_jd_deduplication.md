# Plan: JD Deduplication via Content Hash

## Overview

Hash the raw JD text and store it in `status.md`. Warn before running the pipeline if the same JD content has been processed before, even under a different company/role slug. Complements Plan 11 (slug-based deduplication) by catching content-identical JDs submitted under different names.

---

## Feature Dependency Diagram

```
[No upstream dependencies]
[Complements 11_application_deduplication.md]

  CLI apply command (cli.py)
      │  job_description text available
      ▼
  compute_jd_hash(job_description) → str (SHA-256 hex, first 16 chars)
      │
      ▼
  find_runs_by_jd_hash(vault_path, hash) → list[Path]
      │  scans status.md files for matching JD hash
      │
      ├── None found → proceed
      └── Found → warn user + list matching runs
              │
              ▼
          user confirms or aborts (same pattern as Plan 11)
              │
              ▼
  run_pipeline() (unchanged)
      │
      ▼
  format_status() (vault.py)
      │  writes "JD hash: abc123def456" to status.md
      ▼
  status.md
```

---

## Technical Plan

### 1. Hash computation

Use Python's stdlib `hashlib` — no new dependency:

```python
import hashlib

def compute_jd_hash(job_description: str) -> str:
    """Return a short SHA-256 hash of the normalised JD text."""
    normalised = " ".join(job_description.split())  # collapse whitespace
    digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()
    return digest[:16]  # first 16 hex chars — sufficient for collision resistance at this scale
```

Normalising whitespace before hashing prevents trivial collisions from copy-paste formatting differences (extra spaces, different line endings).

### 2. Hash storage in `status.md` (`vault.py`)

Extend `format_status` to accept and write the JD hash:

```python
def format_status(state: PipelineState) -> str:
    ...
    # Add to status output:
    f"JD hash: {state.jd_hash}"
```

Add `jd_hash: Optional[str] = None` to `PipelineState`. Set in `pipeline.py` after the JD is loaded:

```python
from job_agent.vault import compute_jd_hash
state.jd_hash = compute_jd_hash(job_description)
```

### 3. Hash scanning (`vault.py`)

```python
def find_runs_by_jd_hash(vault_path: Path, jd_hash: str) -> list[Path]:
    """Return vault folders where status.md contains a matching JD hash."""
    matches = []
    for status_file in vault_path.rglob("status.md"):
        content = status_file.read_text(encoding="utf-8", errors="ignore")
        if f"JD hash: {jd_hash}" in content:
            matches.append(status_file.parent)
    return matches
```

### 4. CLI integration (`cli.py`)

Insert after the JD is loaded, before `run_pipeline`:

```python
from job_agent.vault import compute_jd_hash, find_runs_by_jd_hash

jd_hash = compute_jd_hash(job_description)
hash_matches = find_runs_by_jd_hash(config.OBSIDIAN_VAULT_PATH.expanduser(), jd_hash)

if hash_matches and not force:
    console.print(f"\n[yellow]⚠️  Identical JD content detected (hash: {jd_hash}):[/yellow]")
    for m in hash_matches:
        status = parse_status_file(m / "status.md")
        console.print(f"  {m.name}  [{status['status']}]")
    console.print("Use [bold]--force[/bold] to run again with the same JD.")
    typer.confirm("Continue anyway?", abort=True)
```

This check runs in addition to the slug check from Plan 11. Both can fire independently — a user might submit the same JD for two different company names (e.g. when a recruiter posts the same role through two agencies).

### 5. `parse_status_file` update (`vault.py`)

Add JD hash parsing:

```python
hash_match = re.search(r"JD hash:\s*([a-f0-9]+)", content)
data["jd_hash"] = hash_match.group(1) if hash_match else None
```

### 6. Tests

| Test | Approach |
|------|----------|
| `compute_jd_hash` is whitespace-invariant | Two strings differing only in whitespace produce same hash |
| `compute_jd_hash` different content → different hash | Assert two different JDs produce different hashes |
| `find_runs_by_jd_hash` finds match | Fixture status.md with known hash; assert folder returned |
| `find_runs_by_jd_hash` no match | Assert empty list returned |
| Hash written to status.md | Assert `"JD hash:"` present in `format_status` output |
| CLI warns on hash collision | Mock `find_runs_by_jd_hash`; assert warning printed |
| `--force` skips hash check | Assert no prompt when `force=True` |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Hash scan is slow on large vaults | Low | Linear scan of `status.md` files via `rglob` — at 200 applications this is negligible (< 100ms). |
| Whitespace normalisation misses structural differences | Low | Normalisation is intentional — two copies of the same JD with different spacing should be detected as duplicates. |
| Hash stored in status.md breaks existing `parse_status_file` logic | Low | Additive: new line in format, new regex in parser. Existing fields are unaffected. |
| User intentionally re-runs same JD (e.g. after prompt update) | Low | `--force` bypass is documented. This is the expected workflow after changing `PROMPT_VERSION`. |
| Old status.md files have no hash line | Low | `find_runs_by_jd_hash` only searches for the hash string; absent entries simply produce no match. |
