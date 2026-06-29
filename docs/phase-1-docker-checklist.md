# Phase 1 — Docker Implementation Checklist

Reference guide for self-implementation. Tick each sub-step as you go.

---

## Step 1.1 — `Dockerfile`

- [x] Use `ghcr.io/astral-sh/uv:python3.11-bookworm-slim` as base image (uv pre-installed, no extra setup)
- [x] Set `WORKDIR /app`
- [x] Copy `pyproject.toml` and `uv.lock` first (before source — this keeps the dep install layer cached)
- [x] Run `uv sync --frozen --no-dev` to install deps from the lock file
- [x] Copy the rest of the source (`job_agent/`)
- [x] Set the default `CMD` to `["uv", "run", "job-agent"]` — note: changed to `ENTRYPOINT` so subcommands (apply, check-config) are appended correctly
- [x] Do **not** `COPY .env`, `COPY data/`, or `COPY job_descriptions/` — these come in via mounts

**Key flags:**
- `--frozen` — fails the build if `uv.lock` is out of date, keeping builds reproducible
- `--no-dev` — excludes pytest and other dev tools from the image

---

## Step 1.2 — `docker-compose.yml`

- [x] Define a single service: `job-agent`
- [x] Set `build: .` (builds from the local `Dockerfile`)
- [x] Set `stdin_open: true` and `tty: true` — the CLI reads from stdin for the JD paste prompt
- [x] Mount the host `data/` dir into `/app/data` (CV, skills table, templates)
- [x] Mount a host output dir (e.g. `./output`) into `/app/output` for generated files
- [x] Pass all required env vars via `environment:` using `${VAR}` substitution from the host `.env`
- [x] Do **not** use `env_file:` — secrets should be passed explicitly, never baked in

**Env vars to pass through:**
```
ANTHROPIC_API_KEY
MODEL_NAME
MATCH_SCORE_THRESHOLD
OBSIDIAN_VAULT_PATH       # set to /app/output inside the container
COVER_LETTER_TEMPLATE_PATH
COVER_LETTER_RUBRIC_PATH
BATCH_TODO_DIR
BATCH_DELAY_SECONDS
```

---

## Step 1.3 — Update `.env.example`

- [x] Add `DATA_DIR=./data` — documents the expected host path for the data volume mount
- [x] Add `OUTPUT_DIR=./output` — the default host output path (no Obsidian required)
- [x] Add a comment explaining that `OBSIDIAN_VAULT_PATH` inside the container should be set to `/app/output`
- [x] Keep all existing vars — don't remove anything

---

## Step 1.4 — `docker-setup.md` guide

Write a plain-English guide aimed at someone with no Python knowledge. Cover:

- [x] Prerequisites: install Docker Desktop (link the download page)
- [x] Clone the repo: removed — guide lives in the repo, reader already has it
- [x] Copy and fill in `.env`: `cp .env.example .env` — explain each required field
- [x] Put their CV (`cv.md`) and skills table (`skills.xlsx`) in `data/`
- [x] Build and run:
  ```
  docker compose run job-agent apply --company "Acme" --role "Data Scientist"
  docker compose run job-agent batch-apply
  docker compose run job-agent check-config
  ```
- [x] Where to find the output: the `output/` folder in the repo root
- [x] Note: `OUTPUT_DIR=./output` in `.env` means no Obsidian needed

---

## Step 1.5 — Verify `check-config` inside the container

- [x] Build the image: `docker compose build`
- [x] Run `check-config` inside the container: `docker compose run job-agent check-config`
- [x] Confirm all paths resolve correctly:
  - `CV_PATH` → `data/cv.md` ✅ (resolves to `/app/data/cv.md` via volume mount)
  - `SKILLS_TABLE_PATH` → `data/skills.xlsx` ✅
  - `OBSIDIAN_VAULT_PATH` → `/app/output` (no existence check in cli.py — logged in `docs/fixes.md`)
- [x] Watch for `Path.expanduser()` calls — `~` expands to `/root` inside the container, not your home dir. If `check-config` resolves a `~`-prefixed path, it will point somewhere that doesn't exist.
- [x] Fix any path issues in `config.py` before declaring Phase 1 done — paths confirmed correct
- [x] End-to-end test: `docker compose run job-agent apply -c "Test" -r "Test" --jd-file AI_and_machine_Learning_engineer.md` ran successfully and wrote output to `./output/`

---

## Risks to keep in mind

| Risk | Mitigation |
|------|-----------|
| `uv.lock` not committed | Check `git ls-files uv.lock` — if missing, the Docker build will fail on a fresh clone |
| `~` in env vars | Use absolute paths or `/app/...` paths in `.env` for container use |
| Windows host | Volume mounts behave differently on Windows — document as unsupported for now |
| Secrets in image layers | Never `COPY .env` — always pass secrets at runtime via `environment:` |
| stdin for JD paste | Without `stdin_open: true` + `tty: true`, the interactive JD prompt will hang |

---

## Done when

- `docker compose run job-agent check-config` exits cleanly with all green
- `docker compose run job-agent apply -c "Test" -r "Test" --jd-file some.txt` runs the pipeline and writes output to `./output/`
- No Python installed on the host is required
