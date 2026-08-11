# P2 platform baseline evidence

This baseline is intentionally scoped to the isolated integration worktree
`codex/p2-platform-integration`. It records what can be verified without
touching the active recovery window or claiming parity from a fake platform.

## Source and isolation

| Item | Evidence |
| --- | --- |
| Integration worktree | `F:/ppt-video-workbench-v3/.worktrees/p2-platform-integration` |
| Branch | `codex/p2-platform-integration` |
| Existing root window | preserved; no reset/clean/merge performed |
| Default behavior | all three P2 flags are disabled |
| Network behavior | provider and cloud clients are not created when their flags are disabled |

## Reproducible checks

Run from the integration worktree with the repository virtual environment:

```powershell
$py = 'F:\ppt-video-workbench-v3\.venv\Scripts\python.exe'
$env:PYTHONPATH = 'apps/api/src'
& $py -m pytest tests/contract/test_p2_platform_contracts.py tests/unit/providers tests/unit/platform_foundation tests/unit/sync tests/unit/test_p2_composition.py tests/integration/test_p2_opt_in.py tests/cloud tests/platform -q
& $py -m mypy apps/api/src/workbench/p2.py apps/api/src/workbench/platform apps/api/src/workbench/providers apps/api/src/workbench/sync cloud_prototype
& $py -m ruff check apps/api/src/workbench/p2.py apps/api/src/workbench/platform apps/api/src/workbench/providers apps/api/src/workbench/sync cloud_prototype tests/contract/test_p2_platform_contracts.py tests/unit/providers tests/unit/platform_foundation tests/unit/sync tests/unit/test_p2_composition.py tests/integration/test_p2_opt_in.py tests/cloud tests/platform
```

Current result: **64 tests passed**, mypy reports no issues in 24 source files,
and Ruff reports no violations.

The web workspace also passes TypeScript `--noEmit` and all 28 Vitest files
(47 tests) when its bundled dependency tree is mounted.

## Explicitly unclaimed evidence

- Full recovery-snapshot acceptance remains a separate baseline with existing
  unrelated failures (10 legacy crash-recovery status expectations, the async
  M5 render status expectation, and the P04 payload-contract expectation); it
  is not silently reclassified as a P2 pass.
- macOS/Linux media export, native credential-store evidence, and signed
  installer/rollback artifacts require real runners and signing material.
- Production cloud release still requires OIDC token validation, PostgreSQL
  PITR/restore evidence, object-retention controls, dependency/SAST/DAST scans,
  and operational SLO evidence. The prototype fails closed until those gates
  exist.
