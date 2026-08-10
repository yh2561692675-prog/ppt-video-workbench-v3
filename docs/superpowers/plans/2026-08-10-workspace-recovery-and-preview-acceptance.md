# Workbench Workspace Recovery and Preview Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a normal Windows Workbench launch use the existing `%LOCALAPPDATA%\PPTVideoWorkbench\workspace-data` project store by default, then verify the original 航空航天 project through the real API without changing its authored media.

**Architecture:** Keep `F:\Video` as the configured cache/output location, while the user project workspace defaults to the launcher state root's `workspace-data` directory. Preserve `WORKBENCH_WORKSPACE` as an explicit override for isolated acceptance runs. The API continues to resolve project-relative preview paths against the selected workspace project directory; verification will exercise project recovery, full preflight, video props, asset serving, subtitles, restart, and render-task creation.

**Tech Stack:** PowerShell launcher, FastAPI/Pydantic API, pytest, pnpm/Vite, PyInstaller, Inno Setup 6, local HTTP API.

## Global Constraints

- Preserve the existing 航空航天 project ID `70fcfa18-c322-4312-9f48-ea25fe6dfccd` and all existing page, narration, audio, subtitle, and preview artifacts.
- Do not delete, recreate, or regenerate user-authored media; create a timestamped backup before any project/database write.
- Keep `F:\Video\Cache` and `F:\Video\Output` as cache/output roots.
- Keep `WORKBENCH_WORKSPACE` as the explicit override used by acceptance scripts.
- Do not read, print, copy, or write API keys or other credentials.
- Do not use destructive Git commands; the current `F:\ppt-video-workbench-v3\.git` pointer is invalid and must remain untouched.

---

### Task 1: Lock down the launcher default with a failing regression test

**Files:**

- Modify: `tests/release/test_launcher_contract.py`
- Test: `tests/release/test_launcher_contract.py::test_launcher_defaults_to_user_workspace_data`

**Interfaces:**

- Consumes: `scripts/launcher.ps1` source text.
- Produces: A contract test that fails while the default workspace is `F:\Video` and passes only when the launcher derives the default from `$stateRoot`.

- [ ] **Step 1: Write the failing test**

```python
def test_launcher_defaults_to_user_workspace_data() -> None:
    source = LAUNCHER.read_text(encoding="ascii")

    assert 'Join-Path $stateRoot "workspace-data"' in source
    assert '"F:\\Video"' not in source.split("$workspaceRoot =", 1)[1].split("$cacheRoot", 1)[0]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/release/test_launcher_contract.py::test_launcher_defaults_to_user_workspace_data -q`

Expected: FAIL because the current launcher uses the literal `F:\Video` as the default workspace.

### Task 2: Change only the launcher workspace default

**Files:**

- Modify: `scripts/launcher.ps1:22-27`
- Test: `tests/release/test_launcher_contract.py::test_launcher_defaults_to_user_workspace_data`

**Interfaces:**

- Consumes: `$stateRoot` and the existing `WORKBENCH_WORKSPACE` override.
- Produces: `$workspaceRoot` defaulting to `Join-Path $stateRoot "workspace-data"`; cache/output defaults remain unchanged.

- [ ] **Step 1: Implement the minimal change**

```powershell
$workspaceRoot = if ([string]::IsNullOrWhiteSpace($env:WORKBENCH_WORKSPACE)) {
    Join-Path $stateRoot "workspace-data"
}
else {
    $env:WORKBENCH_WORKSPACE
}
```

- [ ] **Step 2: Run the focused regression test**

Run: `uv run pytest tests/release/test_launcher_contract.py::test_launcher_defaults_to_user_workspace_data -q`

Expected: PASS.

- [ ] **Step 3: Run launcher contract tests**

Run: `uv run pytest tests/release/test_launcher_contract.py tests/release/test_video_storage_launcher.py -q`

Expected: PASS with no failures.

### Task 3: Run source checks and build the Windows payload

**Files:**

- Modify only files required by the failing checks; do not touch user project data.
- Verify: `scripts/build-release.ps1`, `dist/release`, `release/ppt-video-workbench-setup.exe`.

**Interfaces:**

- Consumes: the corrected launcher and existing runtime assets.
- Produces: a verified staged release and Windows installer.

- [ ] **Step 1: Run targeted Python and Web tests**

Run: `uv run pytest tests/unit/preflight tests/integration/test_preflight_routes.py tests/integration/test_video_preview_routes.py tests/unit/video -q`

Expected: PASS.

- [ ] **Step 2: Run static/type checks**

Run: `pnpm lint`; `pnpm typecheck`; `uv run ruff check .`; `uv run mypy`

Expected: exit code 0 for every command.

- [ ] **Step 3: Build and verify the release**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-release.ps1 -Output dist/release -InstallerOutputDirectory release -Verify`

Expected: staging verification passes and `release\ppt-video-workbench-setup.exe` exists.

### Task 4: Real-project acceptance and restart

**Files:**

- Modify: only derived runtime files created by the API under the backed-up project (`preflight_report`, audit/history, video-preflight record, render outputs).
- Verify: original project directory and ID mapping.

**Interfaces:**

- Consumes: installed `workbench.exe`, launcher, `%LOCALAPPDATA%\PPTVideoWorkbench\workspace-data`, and project ID.
- Produces: evidence for project recovery, 8/8 image asset HTTP responses, full preflight, Props, subtitles, audio timing, restart recovery, and render-task creation.

- [ ] **Step 1: Launch with the installed shortcut-equivalent command**

Use `scripts\launcher.ps1 -InstallRoot <install>\release` with no `WORKBENCH_WORKSPACE` override; assert the endpoint workspace is `%LOCALAPPDATA%\PPTVideoWorkbench\workspace-data`.

- [ ] **Step 2: Verify the real API**

GET `/api/health`, `/api/projects`, `/api/projects/{id}`, `/api/projects/{id}/subtitles`, and `/api/projects/{id}/video/preview`; POST `/api/projects/{id}/preflight` with `{}`; GET all eight `/api/projects/{id}/video/assets/{asset_path}` URLs.

Expected: project ID/`project_dir` match, 8 pages and 8 audio records are present, 224 subtitle cues and contiguous Props timing are present, full preflight has `allowed=true`, `issue_count=0`, `reused_checks=[]`, and all eight assets return `200 image/png`.

- [ ] **Step 3: Verify final render can start**

POST `/api/projects/{id}/video/render` and record the HTTP response/job or explicit runtime gate result; do not delete or overwrite authored inputs.

- [ ] **Step 4: Stop and relaunch the installed app**

After the first API process exits, relaunch with the same shortcut-equivalent command and repeat project recovery and health checks. Preserve the backup and record any remaining environment warnings separately from project correctness.
