# Plan: Expand Job Agent for Non-Technical Users

**Date:** 2026-06-15
**Status:** Draft — not started

---

## Objective

Make the job agent runnable by another person with no code interaction: first via Docker (CLI preserved, no local Python setup needed), then via a Streamlit web app (browser-based, no terminal at all).

---

## Phase 1 — Docker Container (CLI in a box)

The goal here is lowest-friction packaging: someone clones the repo, fills in a `.env`, runs `docker compose up`, and the CLI is available. Their CV and outputs live on their own machine via volume mounts.

### Steps

- [ ] **1.1 — Write `Dockerfile`**
  Use a `python:3.11-slim` base. Install `uv` via its official install script or `pip install uv`. Copy `pyproject.toml`, `uv.lock`, and source. Run `uv sync --no-dev`. Set entrypoint to `uv run job-agent`.

- [ ] **1.2 — Write `docker-compose.yml`**
  Mount two host volumes: one for `data/` (CV, skills table, templates) and one for the Obsidian output directory. Pass all `.env` vars as `environment:` entries. This avoids copying sensitive files into the image layer.

- [ ] **1.3 — Update `.env.example`**
  Add `DATA_DIR` and `OUTPUT_DIR` to document the expected mount points. These map to `CV_PATH`, `SKILLS_TABLE_PATH`, and `OBSIDIAN_VAULT_PATH` inside the container.

- [ ] **1.4 — Write a `docker-setup.md` guide**
  Step-by-step for a non-technical user: install Docker Desktop, clone repo, fill in `.env`, run a command. Include the exact `docker run` and `docker compose run` invocations for `apply`, `batch-apply`, and `check-config`.

- [ ] **1.5 — Verify `check-config` works inside the container**
  The check currently resolves `Path.expanduser()` which works differently inside a container. Confirm all paths resolve correctly through the mounts.

### Risks — Phase 1

- **UV in Docker is non-standard.** The official UV install script requires `curl` and writes to `/root/.cargo/bin` or similar — this adds image size and build complexity. *Mitigation:* use `pip install uv` in the Dockerfile, or switch to a `uv`-based Docker base image (`ghcr.io/astral-sh/uv`). Test the build before declaring it stable.

- **Obsidian vault path is deeply personal.** The `OBSIDIAN_VAULT_PATH` default points to `~/Documents/vault/...`. A different user won't have this path. The Docker guide must make it clear that this must be set to a real host path. *Mitigation:* default `OUTPUT_DIR` to `./output` in the `docker-compose.yml` so it works out of the box without Obsidian.

- **Windows path handling.** If the other user is on Windows, Docker Desktop volume mounts and path separators behave differently. `Path.expanduser()` inside a Linux container will not expand Windows-style paths passed as env vars. *Mitigation:* test explicitly on Windows or document it as unsupported for Phase 1.

- **Secrets in image layers.** If `.env` is `COPY`-d into the image rather than mounted at runtime, API keys end up in the image layer history. *Mitigation:* never `COPY .env` — pass all secrets as `--env-file` at run time.

- **`uv.lock` must be committed.** Docker builds need a lock file to be reproducible. If `uv.lock` is in `.gitignore`, the build will fail for a fresh clone. *Mitigation:* confirm `uv.lock` is tracked in git before writing the Dockerfile.

---

## Phase 2 — Streamlit Web App

The goal is a browser UI where a user uploads their CV and skills table, pastes a job description, and downloads a zip of the generated documents. No terminal, no vault, no local paths.

The core pipeline logic does not change. What changes is the input/output layer: files come in via upload widgets, outputs are zipped and served for download rather than written to an Obsidian folder.

### Architecture sketch

```
Browser
  └── Streamlit app (streamlit_app.py)
        ├── Accepts: CV upload, skills upload, JD text, company, role, API key
        ├── Writes uploads to a per-session temp dir
        ├── Calls run_pipeline() with paths pointing at that temp dir
        │     (pipeline writes vault files to the same temp dir)
        └── Zips temp dir → serves as st.download_button
```

The key insight: `run_pipeline()` and `vault.py` write markdown to a filesystem path. Point that path at a `tempfile.TemporaryDirectory` and the pipeline requires zero changes — only the caller changes.

### Steps

- [ ] **2.1 — Audit pipeline I/O boundaries**
  Confirm that `run_pipeline()` accepts `vault_path` as a parameter (or that `config.OBSIDIAN_VAULT_PATH` can be overridden at call time). If it reads `config` as a module-level singleton, a small change is needed to accept an explicit output path. Do not refactor the pipeline itself.

- [ ] **2.2 — Create `streamlit_app.py` at repo root**
  Sections:
  - Sidebar: API key input (password field), model selector, score threshold slider.
  - Main: file uploaders for CV (`.md`) and skills table (`.xlsx`), cover letter template (`.md`, optional).
  - JD entry: text area for paste or file upload.
  - Company and role text inputs.
  - Run button.
  - Results area: progress spinner during run, then rendered markdown previews + a single "Download results (zip)" button.

- [ ] **2.3 — Write session temp-dir handler**
  On each run, create a `tempfile.TemporaryDirectory`. Write uploaded files into it. Set config paths to point there. After the run, zip the output folder and return bytes for `st.download_button`. Clean up the temp dir.

- [ ] **2.4 — Add `streamlit` to `pyproject.toml` dependencies**
  Keep it in main dependencies (not dev) since it is a runtime requirement. Run `uv sync` to update the lock file.

- [ ] **2.5 — Handle pipeline gate outcomes in the UI**
  Gate 1 (analyst recommends not applying) and Gate 2 (rescore fails) currently print to console and write `status.md`. In Streamlit these need to surface as `st.warning` banners with the rationale, not silent exits. A `--force` equivalent toggle should be exposed in the sidebar.

- [ ] **2.6 — Add Streamlit to the Docker image**
  Update the `Dockerfile` to expose port 8501 and add a second `CMD` mode (or a second `docker-compose` service) that runs `streamlit run streamlit_app.py`. The CLI service and the web service can share the same image with different entrypoints.

- [ ] **2.7 — Write a `streamlit-setup.md` guide**
  For local run: `uv run streamlit run streamlit_app.py`. For Docker: `docker compose up web`. Document what each upload field expects (CV format requirements, skills table column names).

- [ ] **2.8 — Write basic Streamlit tests**
  Use `streamlit.testing.v1.AppTest` to cover: missing required field validation, gate 1 early exit displays warning, successful run produces a downloadable zip. Mock `run_pipeline` as in `test_pipeline.py`.

### Risks — Phase 2

- **Pipeline runtime is 30–60 seconds.** Streamlit runs Python synchronously in the main thread. A long pipeline call will freeze the UI with no feedback. *Mitigation:* wrap the `run_pipeline` call with `st.spinner("Running pipeline...")`. For a smoother experience later, consider `asyncio` or a background thread with `st.status` — but this adds complexity and should be a follow-up, not Phase 2 scope.

- **Session state and reruns.** Streamlit reruns the entire script on every widget interaction. If the pipeline result is not stored in `st.session_state` it will be lost on the next widget change (e.g. the user scrolls or changes a slider after the run). *Mitigation:* store `PipelineState` and the zip bytes in `st.session_state` keyed by a run ID, not as local variables.

- **Config is a module-level singleton.** `config.py` reads from env vars at import time. If the Streamlit app passes the API key via a text input, it cannot simply set `config.ANTHROPIC_API_KEY` after import because `langchain-anthropic` may have already instantiated the client. *Mitigation:* audit how `BaseAgent` instantiates the LLM client — if it uses the key at call time rather than init time, overriding the config attribute is sufficient. If not, the agent will need to accept an explicit `api_key` parameter.

- **API key in browser session.** The user's API key is entered into a Streamlit text input. It lives in `st.session_state` for the duration of the session. On a shared or public deployment this is a significant risk. *Mitigation:* for local Docker use this is acceptable. Document clearly that the app should NOT be deployed publicly without adding auth (e.g. Streamlit Cloud secrets or an nginx auth proxy). Do not build auth into Phase 2.

- **Uploaded file size limits.** Streamlit's default `maxUploadSize` is 200 MB. Skills tables and CVs are tiny, but worth knowing. No action needed unless a user has a very large skills table.

- **Temp dir cleanup on crash.** If the pipeline raises an unhandled exception, the `TemporaryDirectory` context manager will still clean up (it's in a `finally` block or uses `__del__`). However, the user loses any partial output. *Mitigation:* catch `ValueError`/`ValidationError` from the pipeline and display them as `st.error` with the partial state where possible.

- **Cover letter template and rubric paths.** These are currently hardcoded in config (`data/cover_letter.md`, `data/cover_letter_rubric.md`). For a new user these files do not exist. *Mitigation:* bundle defaults in the repo and copy them into the temp dir on startup, or make them optional uploads with sensible fallback text. Decide before starting 2.2.

- **Streamlit and UV entrypoint.** `uv run streamlit run streamlit_app.py` works locally. In Docker, the entrypoint needs to invoke streamlit correctly. Test that the Streamlit server starts and is accessible on `0.0.0.0:8501` (not `localhost` only) inside the container.

---

## Phase 3 — Windows Desktop App

The goal is a distributable Windows installer: the user downloads a `.exe`, runs it, and gets a desktop shortcut that opens the job agent in their browser. No Python, no Docker, no terminal.

**This phase builds directly on Phase 2.** The Streamlit app is the UI. Phase 3 bundles it into a self-contained Windows application using PyInstaller and packages it with Inno Setup.

### Architecture sketch

```
JobAgent.exe (launcher)
  ├── Bundled Python interpreter + all deps (via PyInstaller --onedir)
  ├── On launch:
  │     ├── Resolve user profile dir → %APPDATA%\JobAgent\
  │     ├── Start Streamlit server on localhost (random free port)
  │     ├── Wait for server ready, then open default browser
  │     └── Show system tray icon with "Quit" option
  └── On quit: shut down Streamlit server cleanly

Inno Setup installer wraps the PyInstaller output dir into a standard
Windows .exe installer that creates a desktop shortcut and Start Menu entry.
```

The key difference from Phase 2: user files (CV, skills table, cover letter template) are stored persistently in `%APPDATA%\JobAgent\` rather than uploaded every session. The Streamlit app detects whether a profile exists and shows a first-run setup screen if not.

### Steps

- [ ] **3.1 — Add profile persistence to the Streamlit app**
  Introduce a `profile.py` module that reads/writes user files to `%APPDATA%\JobAgent\` (Windows) or `~/.jobagent/` (cross-platform fallback). The Streamlit app checks on load: if no profile exists, show a "Set up your profile" screen (upload CV, skills table, enter API key). Once saved, subsequent runs skip setup and load from the profile dir. This is additive — Phase 2 upload-every-time still works as a fallback.

- [ ] **3.2 — Write `launcher.py`**
  This is the entry point PyInstaller will package. It:
  - Finds a free local port using `socket`.
  - Locates `streamlit_app.py` relative to `sys._MEIPASS` (PyInstaller's bundle path).
  - Starts the Streamlit server in-process via `streamlit.web.cli` (not as a subprocess — avoids process management complexity inside the bundle).
  - Opens `http://localhost:{port}` in the default browser after a brief ready-check loop.
  - Optionally adds a system tray icon via `pystray` so the user can quit cleanly without hunting for a terminal.

- [ ] **3.3 — Create `job_agent.spec` (PyInstaller spec file)**
  A `.spec` file gives explicit control over what gets bundled. Key entries needed:
  - `datas`: Streamlit's own static web assets (`streamlit/static`), the `data/` directory (bundled defaults for cover letter template and rubric), `streamlit_app.py`.
  - `hiddenimports`: `langchain_anthropic`, `langchain_openai`, `langchain_community`, `anthropic`, `openpyxl`, `pandas`, `pydantic` — these all use dynamic loading that PyInstaller's analyser misses.
  - `excludes`: test frameworks, dev tools, IPython — reduces bundle size.
  - Use `--onedir` not `--onefile` (onefile has severe cold-start penalties and more AV false positives).

- [ ] **3.4 — Test PyInstaller build on Windows**
  Build the bundle on a Windows machine (or a Windows GitHub Actions runner — see 3.7). Run it on the same machine first. Then test on a separate clean Windows VM with no Python installed. Verify: app launches, browser opens, file uploads work, pipeline runs, results download. This step will surface most hidden-import and data-file issues.

- [ ] **3.5 — Create Inno Setup script (`installer.iss`)**
  Wraps the PyInstaller `dist/JobAgent/` directory into a standard Windows installer. Configure:
  - Install to `%ProgramFiles%\JobAgent\`.
  - Create desktop shortcut and Start Menu entry pointing to `JobAgent.exe`.
  - Include an uninstaller.
  - Set minimum Windows version (Windows 10 64-bit is a reasonable target).

- [ ] **3.6 — Write a GitHub Actions workflow for the build**
  A `windows-build.yml` workflow that runs on a `windows-latest` runner, installs Python 3.11, runs `pip install pyinstaller` + `uv sync`, builds the PyInstaller bundle, then runs Inno Setup to produce the installer `.exe`. Uploads the installer as a workflow artifact. This means the Windows build does not require a Windows machine locally.

- [ ] **3.7 — Write `windows-app.md` user guide**
  Download link (or "run the GitHub Actions workflow"), installer walkthrough, first-run profile setup, how to update the API key, how to update the app (re-run installer). Include a note on the Windows Defender SmartScreen warning and why it appears.

### Risks — Phase 3

- **PyInstaller bundle size.** The dependency tree (langchain, pandas, anthropic SDK, openpyxl, Streamlit and its React frontend) will produce a `dist/` directory of roughly 400–700 MB. This is normal for ML-adjacent Python apps but surprises users used to small installers. *Mitigation:* use `excludes` in the `.spec` to trim unused packages. Accept the size rather than invest in complex tree-shaking. Document the expected installer size upfront.

- **Hidden imports in LangChain.** LangChain uses `importlib` and lazy provider loading heavily. PyInstaller's static analyser will miss these. *Mitigation:* use the `.spec` `hiddenimports` list and test with an actual LLM call inside the bundle — not just import checks. Expect to iterate on this list during step 3.4.

- **Streamlit's static assets inside the bundle.** Streamlit serves a React frontend from its own package directory. PyInstaller will not automatically include these. Without them, the browser gets a blank page. *Mitigation:* explicitly add `(streamlit_package_dir/static, 'streamlit/static')` to `datas` in the `.spec`. Verify this path after each `uv sync` since it changes between Streamlit versions.

- **Windows Defender SmartScreen.** Unsigned executables from unknown publishers trigger a "Windows protected your PC" warning. For personal use this is a minor inconvenience (click "More info → Run anyway"). For sharing with others it erodes trust. *Mitigation:* document the workaround in the user guide. Code signing certificates cost ~$300/year — note it as a future option if the app is shared more widely.

- **Antivirus false positives.** PyInstaller-bundled executables are frequently flagged by AV engines because malware uses the same packing technique. *Mitigation:* use `--onedir` (less suspicious than `--onefile`). If false positives are a consistent problem, consider submitting the binary to AV vendors for whitelisting — but this is a last resort.

- **Port conflicts.** The launcher picks a free port at startup. If `8501` (or whatever port is chosen) is already in use, the server fails silently. *Mitigation:* use `socket` to find a genuinely free port before passing it to Streamlit. Log the port visibly in the tray tooltip or a startup splash.

- **Cold start time.** Extracting and loading a 500 MB bundle, importing Streamlit, pandas, langchain, and then starting a web server takes 15–40 seconds on a cold start. *Mitigation:* show a visible splash screen or loading indicator from the launcher before the browser opens. Set user expectations in the guide: "first launch takes ~30 seconds."

- **Must build on Windows.** PyInstaller bundles the Python interpreter and `.dll`s of the host OS. A macOS build of `launcher.py` cannot produce a Windows `.exe`. *Mitigation:* use the GitHub Actions `windows-latest` runner (step 3.6) to avoid needing a local Windows machine.

- **Profile migration.** If the app is updated and `profile.py`'s schema changes, existing `%APPDATA%\JobAgent\` profiles may be incompatible. *Mitigation:* keep the profile format as plain files in a directory (one file per data item), not a serialised schema. Individual files can be added or removed without breaking existing profiles.

- **`pystray` is optional complexity.** A system tray icon requires `pystray` + `Pillow` (for the icon image), which adds more hidden imports and a `.ico` asset. If this proves fragile, a simpler approach is to just open the browser and let the user close it — the Streamlit server will keep running until they close the terminal window that launched it. *Mitigation:* treat `pystray` as a stretch goal within this phase; the app is usable without it.

---

## Future / out of scope

- **Authentication / multi-user support.** All phases are single-user local. Any public deployment needs auth.
- **Async pipeline with real-time progress.** Replace the spinner with a live log stream.
- **Cloud deployment.** Streamlit Cloud, Railway, or Fly.io. Requires secrets management and persistent storage decisions.
- **macOS `.app` bundle.** Same PyInstaller approach applies; separate phase given macOS notarisation requirements.
- **`list-applications` tab in the app.** Reads from the Obsidian vault — only meaningful for single-user local use.
- **Auto-update.** Would require a proper update server or GitHub Releases integration.

---

## Decision points to confirm before starting

1. **Output format for Docker users without Obsidian.** Should the Docker setup default to writing outputs to `./output/` on the host rather than requiring an Obsidian path? This is a usability call that affects the `docker-compose.yml` defaults and the setup guide.

2. **Cover letter template handling in Streamlit.** Bundle the repo's `data/cover_letter.md` as the default (good for your own use case, but opinionated for others) or make it a required upload with no default? The latter is more generic but adds friction.

3. **API key handling in Streamlit.** Enter it in the UI each session (simple, no storage) vs read from a `.env` file mounted into Docker (more like the CLI). Both are viable — decide before writing `streamlit_app.py`.

4. **Profile persistence scope (Phase 3).** The Windows app introduces `%APPDATA%` storage so files persist between sessions. Should the Phase 2 Streamlit app also adopt this pattern (for non-Windows users running locally), or stay upload-every-time? Unifying the behaviour makes `profile.py` simpler but changes Phase 2's design. Decide before starting step 3.1.

5. **System tray icon (Phase 3).** Include `pystray` for a clean quit experience, or ship without it (user just closes the browser tab, server keeps running until they kill the process)? The tray icon is more polished but adds fragile dependencies. Decide before writing `launcher.py`.

---

## Out of scope

- Changing any existing pipeline logic, agents, or prompts.
- Multi-user or cloud deployment.
- The `list-applications` CLI command (vault-dependent, single-user).
- Batch mode in the Streamlit UI (Phases 2 and 3 are single-job only).
