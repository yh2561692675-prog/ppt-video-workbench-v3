# PPT Video Workbench V3 Scaffold Design

## Goal

Create a recognizable, independently versioned Git repository for a Windows-first PPT and video workbench. The first delivery is a minimal runnable skeleton: a React web interface, a FastAPI backend, clear setup and development commands, and no product features beyond a health check.

## Scope

The scaffold includes:

- An independent Git repository on the `main` branch.
- A React, TypeScript, and Vite frontend.
- A Python and FastAPI backend.
- A frontend welcome screen that reports backend availability.
- A backend `GET /api/health` endpoint.
- Windows PowerShell setup and development scripts.
- Repository instructions for Codex and human contributors.
- Placeholder data directories whose generated contents stay out of Git.
- Basic backend tests and frontend build verification.

The scaffold does not include PPT parsing, video rendering, upload workflows, authentication, a database, Redis, Docker, deployment configuration, or background job infrastructure.

## Repository Structure

```text
ppt-video-workbench-v3/
|-- .codex/
|   `-- config.toml
|-- frontend/
|   |-- src/
|   |-- package.json
|   |-- tsconfig.json
|   `-- vite.config.ts
|-- backend/
|   |-- app/
|   |   |-- api/
|   |   `-- main.py
|   |-- tests/
|   `-- pyproject.toml
|-- scripts/
|   |-- setup.ps1
|   `-- dev.ps1
|-- data/
|   |-- input/
|   |-- output/
|   `-- temp/
|-- docs/
|-- AGENTS.md
|-- README.md
|-- .editorconfig
`-- .gitignore
```

## Architecture

The frontend and backend are separate applications with independent dependency manifests. The browser loads the Vite application, which requests `GET /api/health` from the local FastAPI server. Vite proxies `/api` during development so the frontend does not need environment-specific CORS logic for the default workflow. FastAPI still permits the local Vite development origin for direct API access during development.

The root scripts coordinate setup and startup without adding a monorepo orchestration framework. `scripts/setup.ps1` validates the required runtimes and installs both applications' dependencies. `scripts/dev.ps1` starts the backend and frontend in separate processes and reports their local URLs.

## Components

### Frontend

The frontend contains one small page with the project name, a concise description, and a backend status indicator. It performs a health request on page load and exposes a retry action when the backend is unavailable. No router, component library, state library, or design system is introduced in the scaffold.

### Backend

The backend exposes an application factory or a small importable application object and a versioned API package boundary. The health endpoint returns stable JSON containing a status value and application name. Keeping API routes separate from the application entry point leaves room for later PPT, asset, and render modules without prematurely implementing them.

### Repository Guidance

`AGENTS.md` documents the architecture, allowed data locations, setup commands, verification commands, and the rule that generated media must not be committed. `.codex/config.toml` contains only repository-local Codex settings that are supported and useful; it must not include secrets or machine-specific absolute paths.

### Data Directories

`data/input`, `data/output`, and `data/temp` are retained with placeholder files. Their contents are ignored because PPT sources, rendered videos, and temporary assets can be large or sensitive.

## Error Handling

- Setup stops with a clear message if Node.js, npm, Python, or a virtual environment prerequisite is unavailable.
- The frontend treats a failed health request as an unavailable backend and remains usable.
- The backend returns FastAPI's structured error responses and does not hide startup failures.
- Development scripts avoid silently terminating existing processes and do not delete generated data.

## Verification

The scaffold is accepted when all of the following are true:

1. The repository is discovered as an independent main repository after refreshing the repository registry.
2. Backend dependencies install and backend tests pass.
3. Frontend dependencies install and the production build succeeds.
4. The development servers start on documented local addresses.
5. The frontend reports a healthy backend while both servers are running.
6. `git status` shows only intentional scaffold files and no generated dependency or media directories.

## Future Extension Boundaries

Later work may add PPT ingestion, slide analysis, asset management, narration, FFmpeg or HyperFrames rendering, and task persistence. These capabilities should enter as focused backend modules and API routes rather than being embedded in the initial health-check skeleton.
