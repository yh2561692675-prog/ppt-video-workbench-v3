# Windows Release Pipeline Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the RC1 Windows build path so it produces an installer whose shortcut launches the bundled Web application.

**Architecture:** A small desktop CLI launches the existing FastAPI service. The service mounts a staged Vite bundle only in packaged mode. A deterministic PowerShell pipeline stages the API executable and Web assets under `dist/release`, writes release evidence, and calls Inno Setup to write the final installer under `release`.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, PyInstaller, React/Vite, pnpm 11.7.0, PowerShell, Inno Setup 6.

## Global Constraints

- Do not include secrets, user projects, or workspace data in a release.
- Bind only to `127.0.0.1` and wait for `/api/health` before browser launch.
- Keep `dist/release` as mutable staging and `release/` as the final installer destination.
- Do not claim Windows executable behavior passed until the user's RC1 evidence records it.

---

### Task 1: Packageable API and bundled Web fallback

**Files:**

- Create: `apps/api/src/workbench/desktop.py`
- Modify: `apps/api/src/workbench/main.py`
- Test: `tests/release/test_packaged_runtime.py`

**Interfaces:**

- Produces `main(argv: list[str] | None = None) -> None` accepting `serve`, `--host`, `--port`.
- Consumes `WORKBENCH_WEB_ROOT`; when it contains `index.html`, the app serves it after API routes.

- [ ] **Step 1: Write the failing test.** Assert that the CLI passes `serve`, host, and port to Uvicorn and that a staged `index.html` serves at `/` while `/api/health` remains available.
- [ ] **Step 2: Run `uv run pytest tests/release/test_packaged_runtime.py -q` and confirm it fails because the CLI and packaged fallback are absent.**
- [ ] **Step 3: Add the minimal CLI and conditional static mount.**
- [ ] **Step 4: Run `uv run pytest tests/release/test_packaged_runtime.py -q` and confirm it passes.**
- [ ] **Step 5: Commit with `git commit -m "fix: add packageable desktop runtime"`.**

### Task 2: Deterministic stage and installer build

**Files:**

- Modify: `pyproject.toml`, `uv.lock`, `apps/api/workbench.spec`, `scripts/build-release.ps1`, `installer/workbench.iss`
- Create: `scripts/build_runtime_manifest.py`
- Test: `tests/release/test_release_build_contract.py`

**Interfaces:**

- `build-release.ps1` creates `dist/release/api/workbench.exe`, `dist/release/web/index.html`, `dist/release/runtime-manifest.json`, then `release/ppt-video-workbench-setup.exe`.
- `workbench.iss` reads `..\\dist\\release\\*` and writes to `..\\release`.

- [ ] **Step 1: Write failing static contracts for required commands, paths, and installer staging/output.**
- [ ] **Step 2: Run `uv run pytest tests/release/test_release_build_contract.py -q` and confirm it fails against the old wheel-only script.**
- [ ] **Step 3: Pin PyInstaller, implement the manifest writer, stage the executable and Web assets, and invoke ISCC.**
- [ ] **Step 4: Run `uv run pytest tests/release/test_release_build_contract.py tests/release tests/security/test_m8_release_security.py -q`.**
- [ ] **Step 5: Commit with `git commit -m "fix: build staged Windows installer"`.**

### Task 3: Repository gate and refreshed Windows handoff

**Files:**

- Modify: `docs/acceptance-report-RC1.md`, `tests/acceptance/results/RC1/README.md`

- [ ] **Step 1: Add the prerequisite install and release-build commands before the install smoke command.**
- [ ] **Step 2: Run `scripts/check.sh`, release tests, `pnpm check`, and the build-script verification available on Linux.**
- [ ] **Step 3: Commit with `git commit -m "docs: correct Windows RC1 build handoff"` and package a refreshed source archive.**
