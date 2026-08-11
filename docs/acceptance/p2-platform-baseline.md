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
& $py -m pytest tests/contract/test_p2_platform_contracts.py tests/contract/test_schema_alignment.py tests/unit/providers tests/unit/platform_foundation tests/unit/cache/test_p2_matrix.py tests/unit/diagnostics/test_p2_privacy.py tests/unit/sync tests/unit/test_p2_composition.py tests/integration/test_p2_opt_in.py tests/integration/test_narration_generation_api.py tests/cloud tests/platform -q
& $py -m mypy --cache-dir .test-mypy-cache apps/api/src/workbench/p2.py apps/api/src/workbench/contracts/p2_platform.py apps/api/src/workbench/cache apps/api/src/workbench/diagnostics/p2_privacy.py apps/api/src/workbench/platform apps/api/src/workbench/providers apps/api/src/workbench/sync cloud_prototype scripts/generate_cloud_client.py
& $py -m ruff check apps/api/src/workbench/p2.py apps/api/src/workbench/contracts/p2_platform.py apps/api/src/workbench/cache apps/api/src/workbench/diagnostics/p2_privacy.py apps/api/src/workbench/platform apps/api/src/workbench/providers apps/api/src/workbench/sync cloud_prototype tests/contract tests/unit/providers tests/unit/platform_foundation tests/unit/cache/test_p2_matrix.py tests/unit/diagnostics/test_p2_privacy.py tests/unit/sync tests/unit/test_p2_composition.py tests/integration/test_p2_opt_in.py tests/integration/test_narration_generation_api.py tests/cloud tests/platform
```

Current result: **108 focused P2 tests passed**, mypy reports no issues in 33 source files,
and Ruff reports no violations.

The generated Cloud TypeScript client covers all 37 OpenAPI operations; its drift check
passes and the P2 contract package passes a strict standalone TypeScript `--noEmit` run.

The independent `peripheral-platform` S0 host also passes **128 tests** on the
current Windows runner (2 symlink tests are skipped when Developer Mode is not
enabled); its 29 source files pass mypy and its source/tests pass Ruff.

The web workspace passes all 28 Vitest files (47 tests) with its bundled
dependency tree. A TypeScript `--noEmit` run was not repeated here because the
isolated worktree does not contain a TypeScript compiler binary; the earlier
baseline result is not reclassified as a current run.

## Explicitly unclaimed evidence

- Full recovery-snapshot acceptance remains a separate baseline with existing
  unrelated failures (10 legacy crash-recovery status expectations, the async
  M5 render status expectation, and one isolated-branch AI narration
  compatibility assertion); P04 legacy-result projection is covered by the
  current compatibility migration; it is not silently
  reclassified as a P2 pass. The S1 module smoke suite is 10/10 after linking
  the shared repository virtual environment into this worktree.
- macOS/Linux media export, native credential-store runner evidence, and signed
  installer/rollback artifacts require real runners and signing material.
- Production cloud release still requires OIDC token validation, PostgreSQL
  PITR/restore evidence, object-retention controls, dependency/SAST/DAST scans,
  and operational SLO evidence. The prototype fails closed until those gates
  exist.
- Provider migration is intentionally incremental: reviewed LLM/ASR/TTS/avatar/OCR/
  renderer bridge facades and opt-in create_app wiring are verified; real vendor
  and remote acceptance evidence still requires its upstream business windows.
- P2 cache invalidation now has an explicit matrix for provider, platform/runtime,
  cloud revision, price, review and comment changes; diagnostics expose only a
  pass/fail privacy summary with finding codes.
- Legacy projects have a deterministic local-first Provider policy helper that is
  additive and never writes policy fields implicitly.
- The cloud prototype has an HTTP-level two-device evidence test covering A's
  outbox, B's cursor pull/acknowledgement, and stale-base conflict handling.
- Remote jobs now persist provider-policy/platform/runtime/input fingerprints;
  result publication rejects a mismatched executor fingerprint set.
- Provider invocations now expose a bounded tenant/project-scoped audit stream
  containing operation status and billed cost only; request inputs and secrets
  are never persisted in the audit payload.
