$ErrorActionPreference = "Stop"
$env:UV_CACHE_DIR = Join-Path $env:TEMP "ppt-video-workbench-uv-cache"
$env:UV_LINK_MODE = "copy"

uv sync --frozen
uv run ruff check apps tests
uv run mypy apps/api/src
uv run pytest
pnpm install --frozen-lockfile
pnpm check
