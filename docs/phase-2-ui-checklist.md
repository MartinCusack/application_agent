# Phase 2 — Streamlit Web UI Checklist

Reference guide for self-implementation. Tick each sub-step as you go.

**Deviations from EXPANSION_PLAN.md:**
- Files are saved persistently to `data/` and `job_descriptions/TODO/` rather than a per-session temp dir
- Batch mode (`batch-apply`) is in scope
- Skills table accepts CSV in addition to `.xlsx`

---

## Step 2.1 — Audit pipeline I/O boundaries

Before writing any UI code, confirm the pipeline can accept an explicit output path rather than always reading from `config.OBSIDIAN_VAULT_PATH`.

- [ ] Check `run_pipeline()` signature in `pipeline.py` — does it accept `vault_path` as a parameter, or does it read from `config` directly?
- [ ] If config-only: add an optional `vault_path` parameter to `run_pipeline()` that overrides the config value at call time. Do not refactor the pipeline internals.
- [ ] Confirm `BaseAgent` instantiates the LLM client at call time (not import time) — this matters for the API key input in the UI

---

## Step 2.2 — Update `loaders.py` to support CSV

- [ ] Update `load_skills_table()` to detect `.csv` vs `.xlsx` by file extension and parse accordingly
- [ ] Add `pandas` CSV read path — same column expectations as xlsx (`Skill`, `Category`, `Proficiency`, `Projects`, `Roles`, `Years`)
- [ ] Validate columns on load — raise a clear error if expected columns are missing
- [ ] Update tests in `test_loaders.py` to cover the CSV path

---

## Step 2.3 — Add Streamlit dependency

- [ ] Run `uv add streamlit` — adds to `pyproject.toml` and updates `uv.lock`
- [ ] Confirm `uv run streamlit run streamlit_app.py` works locally before building the UI

---

## Step 2.4 — Create `streamlit_app.py`

Create at the repo root. Structure into four tabs:

**Tab 1 — Profile (CV + skills)**
- [ ] File uploader for CV (`.md`) — saves to `data/cv.md`
- [ ] File uploader for skills table (`.csv` or `.xlsx`) — saves to `data/skills.csv` or `data/skills.xlsx`
- [ ] Show current file status: does `data/cv.md` exist? Does a skills file exist?
- [ ] Warn before overwriting an existing file

**Tab 2 — Job Descriptions**
- [ ] File uploader for JD files (`.md`) — saves to `job_descriptions/TODO/`
- [ ] List current files in `job_descriptions/TODO/` with a delete button per file
- [ ] Show files currently in `job_descriptions/applied/` and `job_descriptions/failed/` as read-only history

**Tab 3 — Run**
- [ ] Company and role text inputs
- [ ] Dropdown to select a JD file from `job_descriptions/TODO/` (for single apply)
- [ ] Run button for `apply` — calls `run_pipeline()` with selected inputs
- [ ] Run button for `batch-apply` — calls `run_batch()` to process all files in TODO
- [ ] `st.spinner` during run — pipeline takes 30–60s, UI must not appear frozen
- [ ] Surface gate exit outcomes as `st.warning` banners with the rationale text
- [ ] Show match score and rescore result on completion

**Tab 4 — Output**
- [ ] List all folders in `output/` with company/role and timestamp
- [ ] Clicking a folder shows generated files
- [ ] Render markdown files as HTML (not raw text)
- [ ] Download button per file

**Sidebar (all tabs)**
- [ ] API key input (password field) — stored in `st.session_state`, passed to pipeline at call time
- [ ] Model selector
- [ ] Match score threshold slider

---

## Step 2.5 — Handle API key at call time

The sidebar API key input must reach the LLM client. Before implementing:

- [ ] Trace how `ANTHROPIC_API_KEY` flows from `config.py` → `BaseAgent` → `langchain-anthropic` client
- [ ] If the client is instantiated at import time: add an `api_key` parameter to `BaseAgent.__init__()` and pass it through
- [ ] If the client is instantiated at call time: overriding the config attribute is sufficient
- [ ] Add a fallback: if the sidebar key is empty, fall back to `config.ANTHROPIC_API_KEY` from `.env` — this means Docker users with a pre-filled `.env` don't need to re-enter their key

---

## Step 2.6 — Add Streamlit to Docker

- [ ] Add a second service `web` to `docker-compose.yml` that runs `streamlit run streamlit_app.py --server.address 0.0.0.0`
- [ ] Share the same `data/`, `output/`, and `job_descriptions/` volume mounts as the `job-agent` service
- [ ] Expose port `8501`
- [ ] Confirm the server is accessible at `http://localhost:8501` (not `localhost` only — `0.0.0.0` binding is required inside a container)

---

## Step 2.7 — Write `streamlit-setup.md`

- [ ] Local run: `uv run streamlit run streamlit_app.py`
- [ ] Docker run: `docker compose up web`
- [ ] Walk through each tab: what to upload, what to fill in
- [ ] Note that `.env` API key is used as a fallback — sidebar input takes precedence

---

## Step 2.8 — Tests

- [ ] `test_loaders.py` — CSV skills table load, missing columns error
- [ ] `test_streamlit.py` using `streamlit.testing.v1.AppTest`:
  - Missing CV shows an error state on the Run tab
  - Gate 1 early exit displays a warning banner
  - Successful single run updates the output tab
  - Batch run calls `run_batch()` with correct arguments
- [ ] Mock `run_pipeline` and `run_batch` as in `test_pipeline.py` — no API key needed

---

## Risks to keep in mind

| Risk | Mitigation |
|------|------------|
| Pipeline blocks UI thread for 30–60s | `st.spinner` handles this for Phase 2; async is a Phase 3 concern |
| Streamlit reruns script on every widget interaction | Store pipeline results in `st.session_state` keyed by run ID |
| Overwriting CV/skills on re-upload | Warn user before overwriting — confirm step in the UI |
| CSV column mismatch | Validate on upload, surface a clear error message |
| API key entered in sidebar lives in session state | Acceptable for local use — document that the app must not be deployed publicly |
| `0.0.0.0` binding required in Docker | Set `--server.address 0.0.0.0` in the Docker entrypoint |
| Cover letter template missing for new users | Bundle `data/cover_letter.md` defaults in the repo — already present |

---

## Done when

- `docker compose up web` starts the UI at `http://localhost:8501`
- A user can upload CV, skills table, and job descriptions entirely through the browser
- A user can trigger both `apply` and `batch-apply` from the UI and see results
- No terminal interaction required after initial Docker setup
