# Source and production workflow

## Prepare the environment

Require Python 3.12, `uv`, Node.js, Corepack, pnpm 11.7.0, FFmpeg/FFprobe, and LibreOffice.
Run the bundled preflight first. From the repository root, install only from lockfiles:

```powershell
uv sync --frozen
corepack enable
pnpm install --frozen-lockfile
```

Do not refresh lockfiles unless dependency changes are explicitly in scope.

## Start the workbench

Start the local API:

```powershell
$env:WORKBENCH_WORKSPACE = "$PWD\workspace-data"
uv run uvicorn workbench.main:app --app-dir apps/api/src --host 127.0.0.1 --port 8765
```

Start the web app in a second terminal:

```powershell
pnpm --filter @workbench/web dev -- --port 5173
```

Verify `GET http://127.0.0.1:8765/api/health` before opening
`http://127.0.0.1:5173`.

## Follow the seven production stages

1. Create a project and import PPTX, DOCX, PDF, or images. Record safe names, sizes, and SHA-256.
2. Parse materials, confirm page order, and manually resolve low-confidence matches.
3. Create or edit narration. Treat every edit as a revision and confirm the selected revision.
4. Choose one audio route for the entire project: local recording or explicitly configured HeyGen.
5. Complete transcription, difference resolution, page boundaries, and subtitle timing.
6. Preview effects, run the full preflight, and resolve blockers or explicitly confirm warnings.
7. Submit the durable render job and verify MP4, SRT, narration, audio, configuration, preflight,
   logs, and SHA-256 manifest in the production package.

## Preserve auditability

- Reopen or refresh the same `job_id` instead of creating duplicate active jobs.
- Resume from a safe checkpoint after an application restart; do not edit queue state by hand.
- Reuse only caches whose input fingerprint and revision still match.
- Keep the last successful MP4 and production package when a retry fails.
- Verify final media and manifest hashes before reporting success.

## Validate source changes

Use the platform script when possible:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

On Linux or macOS, run `bash scripts/check.sh`. If a full gate is unavailable, run focused tests
and list both executed and unexecuted checks.
