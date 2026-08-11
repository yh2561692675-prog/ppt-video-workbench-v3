# P2 platform implementation gate

This file records evidence for the isolated integration branch
`codex/p2-platform-integration`.

| Gate | Evidence | Result |
| --- | --- | --- |
| Shared contracts | `tests/contract/test_p2_platform_contracts.py` | pass |
| Provider Kernel and controls | `tests/unit/providers` | pass |
| Provider usage and audit trail | `tests/unit/providers/test_provider_controls.py`, `GET /api/providers/audit` | pass (bounded, tenant/project scoped, no input refs or secrets) |
| Local-first policy migration | `tests/unit/providers/test_policy_migration.py` | pass (deterministic, additive, remote fail-closed) |
| P2 invalidation matrix | `tests/unit/cache/test_p2_matrix.py` | pass (price/review preservation; provider/platform/revision scope) |
| Upstream adapter seams | `tests/unit/providers/test_upstream_adapters.py`, `tests/integration/test_narration_generation_api.py` | pass for reviewed LLM/ASR/TTS/avatar/OCR/renderer bridge facades and opt-in create_app wiring; real vendor/remote acceptance remains pending upstream windows |
| Platform paths/process/capability states | `tests/unit/platform_foundation`, `tests/platform` | pass (tool version/hash probes, explicit unsupported/missing states) |
| Platform credentials/redaction | `test_platform_credentials.py` | pass |
| Cloud control plane/RBAC/revision/object/sync | `tests/cloud` | pass (logical object storage keys, bounded declarations, restricted upload rejection) |
| Remote executor fingerprints | `tests/cloud/test_cloud_api.py` | pass (capability snapshot portability and job/result fingerprint equality) |
| Production cloud fail-closed gate | `CloudProductionEvidence` and production-auth tests | pass (missing external evidence blocks traffic) |
| Desktop outbox/inbox/conflict | `tests/unit/sync` and stale-base cloud test | pass |
| Two-device HTTP sync prototype | `tests/cloud/test_two_device_sync.py` | pass (A outbox -> B cursor pull -> stale conflict) |
| Opt-in composition and diagnostics | `tests/unit/test_p2_composition.py`, `tests/integration/test_p2_opt_in.py` | pass |
| P2 privacy scan | `tests/unit/diagnostics/test_p2_privacy.py` and `/api/p2/diagnostics` | pass (codes only, no sensitive value echo) |
| P2 settings UI panels | three focused Vitest suites under `apps/web/src/features/{providers,settings/platform,cloud}` | pass |
| Full web UI regression | Vitest 28 files / 47 tests + TypeScript `--noEmit` | pass with bundled web dependencies |
| Static quality | Ruff + mypy on 32 P2 source files | pass |
| Focused P2 regression | 81 tests across contracts/providers/platform/cache/diagnostics/sync/cloud/integration | pass |
| Full recovery snapshot | `pytest --import-mode=importlib -q --maxfail=12` | pending: 10 crash-recovery status mismatches (`succeeded` vs legacy `completed`), M5 async render status mismatch (202 vs legacy 201), and P04 payload-contract mismatch |
| Real macOS/Linux media and signed installers | three-OS CI/tag evidence | pending runner artifacts |
| Production cloud | OIDC, PostgreSQL PITR, object retention, security scans | pending production environment |

Re-run the P2 gate with:

```powershell
$env:PYTHONPATH = "apps/api/src"
python -m pytest tests/contract/test_p2_platform_contracts.py tests/unit/providers tests/unit/platform_foundation tests/unit/sync tests/unit/test_p2_composition.py tests/integration/test_p2_opt_in.py tests/integration/test_narration_generation_api.py tests/cloud tests/platform -q
python -m mypy apps/api/src/workbench/p2.py apps/api/src/workbench/contracts/p2_platform.py apps/api/src/workbench/cache apps/api/src/workbench/diagnostics/p2_privacy.py apps/api/src/workbench/platform apps/api/src/workbench/providers apps/api/src/workbench/sync cloud_prototype
python -m ruff check apps/api/src/workbench/p2.py apps/api/src/workbench/contracts/p2_platform.py apps/api/src/workbench/cache apps/api/src/workbench/diagnostics/p2_privacy.py apps/api/src/workbench/platform apps/api/src/workbench/providers apps/api/src/workbench/sync cloud_prototype tests/contract/test_p2_platform_contracts.py tests/unit/providers tests/unit/platform_foundation tests/unit/cache/test_p2_matrix.py tests/unit/diagnostics/test_p2_privacy.py tests/unit/sync tests/unit/test_p2_composition.py tests/integration/test_p2_opt_in.py tests/integration/test_narration_generation_api.py tests/cloud tests/platform
```
