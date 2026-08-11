# PPT Video Workbench V3 Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal runnable Windows-first PPT and video workbench skeleton with a React status page, a FastAPI health endpoint, repository guidance, and repeatable setup and verification commands.

**Architecture:** Keep `frontend/` and `backend/` as independent applications coordinated by root PowerShell scripts. Vite proxies `/api` to FastAPI during development, while the repository root provides Codex instructions, data boundaries, and verification documentation.

**Tech Stack:** React 19.2.8, TypeScript 7.0.2, Vite 8.2.1, Vitest 4.1.10, Python 3.11+, FastAPI 0.141.1, Uvicorn 0.52.1, pytest 9.1.1, HTTPX 0.28.1, PowerShell, Git.

## Global Constraints

- Support Windows development with Node.js 22 or newer and Python 3.11 or newer.
- Keep the first delivery limited to a welcome page and `GET /api/health`.
- Do not add PPT parsing, video rendering, uploads, authentication, databases, Redis, Docker, deployment configuration, or background job infrastructure.
- Do not store secrets, user-specific absolute paths, dependency directories, or generated media in Git.
- Preserve `data/input`, `data/output`, and `data/temp` with tracked `.gitkeep` files while ignoring their other contents.
- Use repository-root `AGENTS.md` for Codex guidance and a project-scoped `.codex/config.toml` containing only supported, non-sensitive settings.

---

## File Map

- `backend/pyproject.toml`: Python metadata, runtime dependencies, development dependencies, and pytest configuration.
- `backend/app/main.py`: FastAPI application construction and router registration.
- `backend/app/api/health.py`: Health response model and route.
- `backend/tests/test_health.py`: Health endpoint contract test.
- `frontend/package.json`: Frontend scripts and pinned npm dependencies.
- `frontend/tsconfig.json`: Browser TypeScript compiler settings.
- `frontend/vite.config.ts`: React plugin and `/api` development proxy.
- `frontend/index.html`: Vite browser entry document.
- `frontend/src/api.ts`: Typed health request boundary.
- `frontend/src/api.test.ts`: Health request success and failure tests.
- `frontend/src/App.tsx`: Welcome screen and backend status state.
- `frontend/src/main.tsx`: React DOM mount point.
- `frontend/src/styles.css`: Small responsive visual system for the welcome screen.
- `scripts/setup.ps1`: Runtime validation and dependency installation.
- `scripts/dev.ps1`: Coordinated local server startup and cleanup.
- `AGENTS.md`: Repository-specific instructions and verification commands.
- `.codex/config.toml`: Project-scoped Codex schema and instruction-size setting.
- `.gitignore`: Dependency, environment, cache, build, and generated-media exclusions.
- `.editorconfig`: Cross-language whitespace and newline defaults.
- `README.md`: Setup, startup, URLs, tests, and repository layout.
- `data/*/.gitkeep`: Tracked placeholders for ignored runtime data directories.

---

### Task 1: FastAPI Health Service

**Files:**

- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/health.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_health.py`

**Interfaces:**

- Consumes: HTTP `GET /api/health` requests.
- Produces: JSON `{ "status": "ok", "app": "ppt-video-workbench-v3" }` and importable `app.main:app`.

- [ ] **Step 1: Add Python metadata and the failing health contract test**

Create `backend/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=80"]
build-backend = "setuptools.build_meta"

[project]
name = "ppt-video-workbench-backend"
version = "0.1.0"
description = "Backend API for PPT Video Workbench V3"
requires-python = ">=3.11"
dependencies = [
  "fastapi==0.141.1",
  "uvicorn[standard]==0.52.1",
]

[project.optional-dependencies]
dev = [
  "httpx==0.28.1",
  "pytest==9.1.1",
]

[tool.pytest.ini_options]
addopts = "-q"
pythonpath = ["."]
testpaths = ["tests"]
```

Create `backend/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_stable_contract() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "ppt-video-workbench-v3",
    }
```

- [ ] **Step 2: Install the backend development environment**

Run from the repository root:

```powershell
python -m venv backend/.venv
& backend/.venv/Scripts/python.exe -m pip install --upgrade pip
& backend/.venv/Scripts/python.exe -m pip install -e "backend[dev]"
```

Expected: editable package installation succeeds.

- [ ] **Step 3: Run the test and verify the missing application fails**

Run:

```powershell
& backend/.venv/Scripts/python.exe -m pytest backend/tests/test_health.py -q
```

Expected: collection fails because `app.main` does not exist.

- [ ] **Step 4: Add the minimal application and health route**

Create empty `backend/app/__init__.py` and `backend/app/api/__init__.py` files.

Create `backend/app/api/health.py`:

```python
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str


@router.get("/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    return HealthResponse(status="ok", app="ppt-video-workbench-v3")
```

Create `backend/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router


def create_app() -> FastAPI:
    application = FastAPI(title="PPT Video Workbench V3", version="0.1.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    application.include_router(health_router, prefix="/api")
    return application


app = create_app()
```

- [ ] **Step 5: Run the backend test and verify it passes**

Run:

```powershell
Push-Location backend
& .venv/Scripts/python.exe -m pytest
Pop-Location
```

Expected: `1 passed`.

- [ ] **Step 6: Commit the backend service**

```powershell
git add backend/pyproject.toml backend/app backend/tests
git commit -m "feat: add backend health service"
```

---

### Task 2: React Backend Status Page

**Files:**

- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/api.test.ts`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/styles.css`

**Interfaces:**

- Consumes: `GET /api/health` returning `HealthStatus`.
- Produces: `fetchHealth(fetcher?: typeof fetch): Promise<HealthStatus>` and a browser page that displays checking, healthy, or unavailable state.

- [ ] **Step 1: Add the frontend manifest, compiler, Vite configuration, and failing API test**

Create `frontend/package.json`:

```json
{
  "name": "ppt-video-workbench-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "19.2.8",
    "react-dom": "19.2.8"
  },
  "devDependencies": {
    "@types/react": "19.2.18",
    "@types/react-dom": "19.2.4",
    "@vitejs/plugin-react": "6.0.5",
    "typescript": "7.0.2",
    "vite": "8.2.1",
    "vitest": "4.1.10"
  }
}
```

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src", "vite.config.ts"]
}
```

Create `frontend/vite.config.ts`:

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
});
```

Create `frontend/src/api.test.ts`:

```typescript
import { describe, expect, it, vi } from 'vitest';

import { fetchHealth } from './api';

describe('fetchHealth', () => {
  it('returns the typed health payload', async () => {
    const fetcher = vi.fn(
      async () =>
        new Response(JSON.stringify({ status: 'ok', app: 'ppt-video-workbench-v3' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    );

    await expect(fetchHealth(fetcher)).resolves.toEqual({
      status: 'ok',
      app: 'ppt-video-workbench-v3',
    });
    expect(fetcher).toHaveBeenCalledWith('/api/health');
  });

  it('rejects an unhealthy HTTP response', async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 503 }));

    await expect(fetchHealth(fetcher)).rejects.toThrow('Health request failed: 503');
  });
});
```

- [ ] **Step 2: Install frontend dependencies and verify the test fails**

Run:

```powershell
Push-Location frontend
npm install
npm test
Pop-Location
```

Expected: test collection fails because `src/api.ts` does not exist.

- [ ] **Step 3: Add the typed API client**

Create `frontend/src/api.ts`:

```typescript
export type HealthStatus = {
  status: 'ok';
  app: string;
};

export async function fetchHealth(fetcher: typeof fetch = fetch): Promise<HealthStatus> {
  const response = await fetcher('/api/health');
  if (!response.ok) {
    throw new Error(`Health request failed: ${response.status}`);
  }
  return (await response.json()) as HealthStatus;
}
```

- [ ] **Step 4: Run the API tests and verify they pass**

Run:

```powershell
Push-Location frontend
npm test
Pop-Location
```

Expected: `2 passed`.

- [ ] **Step 5: Add the welcome page**

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#07111f" />
    <title>PPT Video Workbench V3</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `frontend/src/App.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react';

import { fetchHealth } from './api';

type ConnectionState = 'checking' | 'healthy' | 'unavailable';

export function App() {
  const [connection, setConnection] = useState<ConnectionState>('checking');

  const checkBackend = useCallback(async () => {
    setConnection('checking');
    try {
      await fetchHealth();
      setConnection('healthy');
    } catch {
      setConnection('unavailable');
    }
  }, []);

  useEffect(() => {
    void checkBackend();
  }, [checkBackend]);

  const statusText = {
    checking: '正在连接后端…',
    healthy: '后端服务正常',
    unavailable: '后端暂不可用',
  }[connection];

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">PPT · VIDEO · WORKFLOW</p>
        <h1>
          PPT Video Workbench <span>V3</span>
        </h1>
        <p className="intro">
          面向演示文稿与视频生产的本地工作台。项目骨架已经就绪，可以继续接入 PPT
          解析、素材管理和渲染流水线。
        </p>
        <div className={`status status--${connection}`} role="status">
          <span className="status__dot" aria-hidden="true" />
          <span>{statusText}</span>
        </div>
        {connection === 'unavailable' && (
          <button type="button" onClick={() => void checkBackend()}>
            重新连接
          </button>
        )}
      </section>
    </main>
  );
}
```

Create `frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import './styles.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

Create `frontend/src/styles.css` with a focused responsive layout:

```css
:root {
  color: #eef6ff;
  background: #07111f;
  font-family: Inter, 'Segoe UI', sans-serif;
  font-synthesis: none;
}

* {
  box-sizing: border-box;
}
body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
}
button {
  font: inherit;
}

.shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px;
  background:
    radial-gradient(circle at 15% 20%, rgba(42, 196, 255, 0.18), transparent 32%),
    radial-gradient(circle at 85% 80%, rgba(136, 87, 255, 0.18), transparent 30%), #07111f;
}

.hero {
  width: min(760px, 100%);
  padding: clamp(32px, 7vw, 72px);
  border: 1px solid rgba(158, 207, 255, 0.2);
  border-radius: 28px;
  background: rgba(11, 25, 43, 0.76);
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(18px);
}

.eyebrow {
  color: #66d9ff;
  letter-spacing: 0.2em;
  font-size: 0.78rem;
  font-weight: 700;
}
h1 {
  margin: 18px 0;
  font-size: clamp(2.6rem, 8vw, 5.6rem);
  line-height: 0.98;
  letter-spacing: -0.05em;
}
h1 span {
  color: #8f7cff;
}
.intro {
  max-width: 58ch;
  color: #a9bfd6;
  line-height: 1.8;
}
.status {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-top: 26px;
  color: #c5d5e5;
}
.status__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #f7b84b;
  box-shadow: 0 0 18px currentColor;
}
.status--healthy .status__dot {
  background: #48e09b;
}
.status--unavailable .status__dot {
  background: #ff6b7b;
}
button {
  margin-top: 20px;
  padding: 10px 18px;
  border: 0;
  border-radius: 999px;
  color: #07111f;
  background: #66d9ff;
  cursor: pointer;
}
button:hover {
  background: #94e6ff;
}
```

- [ ] **Step 6: Verify the production build**

Run:

```powershell
Push-Location frontend
npm run build
Pop-Location
```

Expected: TypeScript succeeds and Vite writes `frontend/dist/`.

- [ ] **Step 7: Commit the frontend**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html frontend/src
git commit -m "feat: add frontend backend-status page"
```

---

### Task 3: Windows Tooling and Repository Guidance

**Files:**

- Create: `.gitignore`
- Create: `.editorconfig`
- Create: `.codex/config.toml`
- Create: `AGENTS.md`
- Create: `scripts/setup.ps1`
- Create: `scripts/dev.ps1`
- Create: `README.md`
- Create: `data/input/.gitkeep`
- Create: `data/output/.gitkeep`
- Create: `data/temp/.gitkeep`

**Interfaces:**

- Consumes: Node.js 22+, npm, Python 3.11+, `frontend/package.json`, and `backend/pyproject.toml`.
- Produces: `./scripts/setup.ps1` for setup and `./scripts/dev.ps1` for a coordinated local session on ports 5173 and 8000.

- [ ] **Step 1: Add repository exclusions and validate ignored runtime paths**

Create `.gitignore`:

```gitignore
# Python
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
backend/*.egg-info/

# Node and Vite
node_modules/
dist/
*.tsbuildinfo

# Environment and editor files
.env
.env.*
!.env.example
.vscode/
.idea/

# Runtime data; preserve directory markers
data/input/*
!data/input/.gitkeep
data/output/*
!data/output/.gitkeep
data/temp/*
!data/temp/.gitkeep

# Local logs
*.log
```

Create the three empty `.gitkeep` files, then verify:

```powershell
New-Item -ItemType File -Path data/input/sample.pptx -Force | Out-Null
New-Item -ItemType File -Path data/output/sample.mp4 -Force | Out-Null
New-Item -ItemType File -Path data/temp/sample.log -Force | Out-Null
git check-ignore data/input/sample.pptx data/output/sample.mp4 data/temp/sample.log
Remove-Item -LiteralPath data/input/sample.pptx,data/output/sample.mp4,data/temp/sample.log
```

Expected: all three sample paths are printed by `git check-ignore`.

- [ ] **Step 2: Add editor and Codex project configuration**

Create `.editorconfig`:

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
indent_style = space
indent_size = 2

[*.py]
indent_size = 4

[*.ps1]
end_of_line = crlf
indent_size = 4
```

Create `.codex/config.toml`:

```toml
#:schema https://developers.openai.com/codex/config-schema.json
project_doc_max_bytes = 65536
```

- [ ] **Step 3: Add the setup script**

Create `scripts/setup.ps1`:

```powershell
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Require-Command([string]$Name, [string]$InstallHint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required. $InstallHint"
    }
}

Require-Command "node" "Install Node.js 22 or newer."
Require-Command "npm" "Install npm with Node.js."
Require-Command "python" "Install Python 3.11 or newer."

$nodeMajor = [int]((node --version).TrimStart("v").Split(".")[0])
if ($nodeMajor -lt 22) { throw "Node.js 22 or newer is required." }

$pythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$pythonVersion -lt [version]"3.11") { throw "Python 3.11 or newer is required." }

$backendPath = Join-Path $repoRoot "backend"
$venvPath = Join-Path $backendPath ".venv"
if (-not (Test-Path -LiteralPath $venvPath)) {
    python -m venv $venvPath
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e "$backendPath[dev]"

Push-Location (Join-Path $repoRoot "frontend")
try { npm install } finally { Pop-Location }

Write-Host "Setup complete. Run .\scripts\dev.ps1"
```

- [ ] **Step 4: Add the coordinated development script**

Create `scripts/dev.ps1`:

```powershell
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $repoRoot "backend"
$frontendPath = Join-Path $repoRoot "frontend"
$venvPython = Join-Path $backendPath ".venv\Scripts\python.exe"
$npmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Backend environment not found. Run .\scripts\setup.ps1 first."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendPath "node_modules"))) {
    throw "Frontend dependencies not found. Run .\scripts\setup.ps1 first."
}

$backend = Start-Process -FilePath $venvPython `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $backendPath -WindowStyle Hidden -PassThru
$frontend = Start-Process -FilePath $npmCommand `
    -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "5173") `
    -WorkingDirectory $frontendPath -WindowStyle Hidden -PassThru

Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "Backend:  http://127.0.0.1:8000/docs"
Write-Host "Press Ctrl+C to stop both services."

try {
    while (-not $backend.HasExited -and -not $frontend.HasExited) {
        Start-Sleep -Seconds 1
        $backend.Refresh()
        $frontend.Refresh()
    }
} finally {
    foreach ($process in @($backend, $frontend)) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id }
    }
}
```

- [ ] **Step 5: Add contributor and user documentation**

Create `AGENTS.md` with these exact operational rules:

```markdown
# Repository Instructions

## Architecture

- `frontend/` is the React and Vite application.
- `backend/` is the FastAPI application.
- `scripts/` contains Windows setup and development commands.
- `data/` is runtime storage; do not commit its generated contents.

## Setup and Development

- Initial setup: `./scripts/setup.ps1`
- Start both services: `./scripts/dev.ps1`
- Backend tests: `backend/.venv/Scripts/python.exe -m pytest backend/tests`
- Frontend tests: run `npm test` from `frontend/`
- Frontend build: run `npm run build` from `frontend/`

## Change Rules

- Keep API routes under `/api` and separate route modules by responsibility.
- Add a focused test before changing backend or frontend behavior.
- Do not commit virtual environments, `node_modules`, build output, secrets, PPT inputs, rendered videos, or temporary media.
- Keep PowerShell scripts Windows-compatible and fail with actionable messages.
```

Create `README.md` with:

````markdown
# PPT Video Workbench V3

A Windows-first local workbench skeleton for future PPT processing and video production workflows.

## Requirements

- Node.js 22 or newer
- Python 3.11 or newer
- PowerShell 5.1 or newer

## Start

```powershell
./scripts/setup.ps1
./scripts/dev.ps1
```

Open `http://127.0.0.1:5173`. FastAPI documentation is available at `http://127.0.0.1:8000/docs`.

## Verify

```powershell
& backend/.venv/Scripts/python.exe -m pytest backend/tests
Push-Location frontend
npm test
npm run build
Pop-Location
```

## Layout

- `frontend/`: React user interface
- `backend/`: FastAPI service
- `scripts/`: setup and development entry points
- `data/input/`: local PPT and source inputs
- `data/output/`: generated presentations and videos
- `data/temp/`: disposable intermediate files
- `docs/`: design and implementation records
````

- [ ] **Step 6: Run documentation and script smoke checks**

Run:

```powershell
$null = [scriptblock]::Create((Get-Content scripts/setup.ps1 -Raw))
$null = [scriptblock]::Create((Get-Content scripts/dev.ps1 -Raw))
Test-Path AGENTS.md
Test-Path .codex/config.toml
git status --short
```

Expected: both scripts parse, both files exist, and only intentional scaffold files are shown.

- [ ] **Step 7: Commit tooling and guidance**

```powershell
git add .gitignore .editorconfig .codex AGENTS.md README.md scripts data
git commit -m "chore: add project tooling and repository guidance"
```

---

### Task 4: Full Verification and Repository Discovery

**Files:**

- Modify only if verification exposes a concrete defect in a file created by Tasks 1-3.

**Interfaces:**

- Consumes: setup script, development script, backend API, frontend page, and repository indexer.
- Produces: passing verification evidence and a clean independently discovered repository.

- [ ] **Step 1: Re-run setup from the documented entry point**

Run:

```powershell
./scripts/setup.ps1
```

Expected: setup completes without changing tracked dependency definitions.

- [ ] **Step 2: Run the complete automated verification suite**

Run:

```powershell
& backend/.venv/Scripts/python.exe -m pytest backend/tests
Push-Location frontend
npm test
npm run build
Pop-Location
```

Expected: backend test passes, both frontend tests pass, and the production build succeeds.

- [ ] **Step 3: Verify the live API and page**

Start `./scripts/dev.ps1`, then verify:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-WebRequest http://127.0.0.1:5173 -UseBasicParsing | Select-Object StatusCode
```

Expected: the API returns `status=ok` and `app=ppt-video-workbench-v3`; the page returns HTTP 200. Inspect the page in a browser and confirm it displays `后端服务正常`, then stop the development script with Ctrl+C.

- [ ] **Step 4: Refresh repository discovery and verify the exact record**

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "F:\git仓库\_repo_indexer\update_repo_registry.ps1"
$registry = Get-Content "F:\git仓库\_repo_indexer\repo_registry.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$registry.repositories | Where-Object { $_.path -eq "F:\git仓库\ppt-video-workbench-v3" } | Format-List repository_type,current_branch,has_uncommitted_changes
```

Expected: `repository_type=main_repository`, `current_branch=main`, and `has_uncommitted_changes=False` after all intended changes are committed.

- [ ] **Step 5: Record final Git evidence**

Run:

```powershell
git status --short --branch
git log --oneline -5
```

Expected: branch `main`, a clean working tree, and separate commits for backend, frontend, tooling, design, and implementation plan.
