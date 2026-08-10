#!/usr/bin/env bash
set -euo pipefail

export UV_CACHE_DIR="${TMPDIR:-/tmp}/ppt-video-workbench-uv-cache"
export UV_LINK_MODE=copy
export npm_config_cache="${TMPDIR:-/tmp}/ppt-video-workbench-npm-cache"
export PNPM_HOME="${TMPDIR:-/tmp}/ppt-video-workbench-pnpm-home"

uv sync --frozen
uv run ruff check apps tests
uv run mypy apps/api/src
uv run pytest
pnpm install --frozen-lockfile --store-dir "${TMPDIR:-/tmp}/ppt-video-workbench-pnpm-store"
pnpm check
