$ErrorActionPreference = 'Stop'
$python = 'F:\ppt-video-workbench-v3\.venv\Scripts\python.exe'
$remotionVitest = 'F:\ppt-video-workbench-v3\remotion\node_modules\.bin\vitest.CMD'
$tsc = 'F:\ppt-video-workbench-v3\node_modules\.bin\tsc.cmd'

& $python -m pytest tests/contract tests/unit/effects tests/unit/domain tests/unit/cache tests/unit/video -q
if ($LASTEXITCODE -ne 0) { throw 'Python unit/contract gates failed' }

& $python -m pytest tests/integration/test_project_api.py tests/integration/test_video_preview_routes.py tests/integration/test_video_render_routes.py -q
if ($LASTEXITCODE -ne 0) { throw 'Python integration gates failed' }

Push-Location remotion
& $remotionVitest run
if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'Remotion tests failed' }
Pop-Location

& $tsc -p remotion/tsconfig.json --noEmit
if ($LASTEXITCODE -ne 0) { throw 'Remotion typecheck failed' }
& $tsc -p apps/web/tsconfig.json --noEmit
if ($LASTEXITCODE -ne 0) { throw 'Web typecheck failed' }

Write-Output 'Effect Engine V2 quality gates passed.'
