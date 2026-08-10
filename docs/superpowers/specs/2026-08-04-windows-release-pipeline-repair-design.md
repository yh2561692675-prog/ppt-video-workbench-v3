# Windows Release Pipeline Repair Design

## Problem

The RC1 source bundle cannot produce the installer required by M8. The existing
`scripts/build-release.ps1` builds frontend assets and a Python wheel only; it
does not create the API executable, stage the Web bundle, generate a complete
runtime manifest, or invoke Inno Setup. The existing installer sources a
nonexistent `release/` directory, while the launcher expects an executable and
web entry point that are not created by the script.

## Goal

Make one Windows command produce `release/ppt-video-workbench-setup.exe` from
a clean source checkout after the documented build dependencies are installed.
The installed shortcut must start a loopback-only API which serves the bundled
Web application.

## Scope and constraints

- Windows 10/11 build host; no administrator privilege is required for the
  application installer.
- Use the repository-pinned `pnpm@11.7.0`, Python 3.12 via `uv`, PyInstaller,
  and Inno Setup 6.
- Build staging lives in `dist/release`; final installer lives in `release/`.
- The release contains no real API key, authorization header, user project, or
  workspace data.
- The launcher binds only to `127.0.0.1`; it uses an ephemeral port and waits
  for `/api/health` before opening the browser.
- External runtime capabilities (FFmpeg, LibreOffice and OCR) remain reported
  by the existing doctor check. They are not silently bundled or claimed to be
  available.

## Design

1. Add a small `workbench.desktop` CLI module. `serve --host --port` starts the
   existing FastAPI application with Uvicorn and receives the staged Web root
   from `WORKBENCH_WEB_ROOT`.
2. Extend `create_app` to serve the staged Vite build only when that directory
   exists. API routes retain precedence; the Web root is mounted last so root
   and browser refreshes return the bundled `index.html`.
3. Make `build-release.ps1` synchronize locked dependencies, build Web and
   Remotion, produce a PyInstaller executable named `workbench.exe`, copy the
   Web distribution to `dist/release/web`, write a third-party notice and a
   hash-checked runtime manifest, then invoke `ISCC.exe`.
4. Make `installer/workbench.iss` read from `dist/release` and write the final
   installer to `release/ppt-video-workbench-setup.exe`. The installed layout
   remains `{app}/release/api/workbench.exe` and `{app}/release/web`.
5. Add focused tests for the desktop CLI, static Web fallback, script pipeline
   contracts, and installer staging/output paths. The Windows executable and
   installer are verified by the existing M8 smoke scripts on the user's PC.

## Success criteria

- A clean Windows machine with prerequisites runs `scripts/build-release.ps1`
  and receives `release/ppt-video-workbench-setup.exe`.
- The installer installs and uninstalls while preserving
  `%LOCALAPPDATA%/PPTVideoWorkbench/workspace-data`.
- The shortcut opens the packaged Web UI after `/api/health` is healthy.
- Linux repository tests validate all changed source and static build contracts;
  Windows-only executable behavior remains recorded as RC1 evidence.
