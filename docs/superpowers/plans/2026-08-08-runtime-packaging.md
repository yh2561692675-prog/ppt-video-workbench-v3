# 安装版独立渲染运行时 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package and verify the Windows video-rendering runtime so the installed API no longer needs the source repository or global pnpm.

**Architecture:** `RuntimeLayout` resolves and validates the bundled runtime. The renderer uses it to execute Node and the deployed Remotion CLI. A PowerShell preparation script creates the runtime input; the release script copies and records all required artifacts.

**Tech Stack:** Python 3.12, PyInstaller, PowerShell, pnpm/Remotion 4, FFmpeg, Inno Setup.

## Global Constraints

- The Windows payload must contain Node, Remotion, FFmpeg, FFprobe and Web/API assets.
- The installed renderer may not invoke `pnpm` or infer the source-repository root.
- System Microsoft Edge is allowed; its absence must be a blocking diagnostic.
- All release artifacts need size and SHA-256 entries in `runtime-manifest.json`.
- No API key, project content or developer `.env` may enter the release payload.

---

### Task 1: Runtime layout and renderer contract

**Files:** create `apps/api/src/workbench/runtime/layout.py`, `tests/unit/runtime/test_layout.py`; modify `apps/api/src/workbench/video/render_service.py`, `tests/unit/video/test_render_service.py`.

- [x] Write failing tests that resolve a temporary `runtime/node/node.exe` and `runtime/remotion/node_modules/@remotion/cli/remotion-cli.js`, and assert a rendered command starts with `node.exe` and contains no `pnpm`.
- [x] Run `UV_CACHE_DIR=/tmp/ppt-video-uv-cache uv run pytest tests/unit/runtime/test_layout.py tests/unit/video/test_render_service.py -q`; confirm red because the layout and renderer runtime argument do not exist.
- [x] Implement `RuntimeLayout.from_environment()` and direct Node/CLI invocation.
- [x] Re-run the focused tests; commit as `feat: resolve packaged rendering runtime`.

### Task 2: Prepare and stage the Windows runtime

**Files:** create `scripts/prepare-runtime.ps1`, `tests/release/test_runtime_layout_contract.py`; modify `scripts/build-release.ps1`, `scripts/build_runtime_manifest.py`, `tests/release/test_runtime_manifest.py`.

- [x] Write failing release tests asserting the manifest records `runtime/node/node.exe`, `runtime/ffmpeg/ffmpeg.exe`, `runtime/ffmpeg/ffprobe.exe`, the Remotion CLI and entry, and that a missing CLI is rejected.
- [x] Run `UV_CACHE_DIR=/tmp/ppt-video-uv-cache uv run pytest tests/release/test_runtime_manifest.py tests/release/test_runtime_layout_contract.py -q`; confirm red because runtime assets are not staged or inventoried.
- [x] Implement asset preparation, staging, required-file checks and recursive runtime artifact inventory.
- [x] Re-run the focused tests; commit as `build: stage independent rendering runtime`.

### Task 3: Diagnostics, launcher and final checks

**Files:** modify `apps/api/src/workbench/environment/detector.py`, `apps/api/src/workbench/preflight/checks/runtime.py`, `scripts/launcher.ps1`, `tests/unit/environment/test_detector.py`, `tests/unit/preflight/test_checks.py`, `tests/release/test_launcher_contract.py`.

- [x] Write failing tests that expect missing bundled components to instruct the user to restore the packaged runtime, not install global tools.
- [x] Run `UV_CACHE_DIR=/tmp/ppt-video-uv-cache uv run pytest tests/unit/environment/test_detector.py tests/unit/preflight/test_checks.py tests/release/test_launcher_contract.py -q`; confirm red.
- [x] Set `WORKBENCH_RUNTIME_ROOT=<InstallRoot>/runtime` in launcher and implement bundled-runtime actions.
- [x] Run `uv run pytest -q`, Ruff, mypy, and `pnpm check`.
- [ ] Run `scripts/prepare-runtime.ps1`, `scripts/build-release.ps1`, and an installed-copy two-page MP4 export on the Windows release machine.
