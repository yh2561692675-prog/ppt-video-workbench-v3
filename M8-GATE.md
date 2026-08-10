# M8 V1.0 Acceptance Gate

Status: **RC candidate — manual Windows sign-off pending**  
Branch: `feature/m8-acceptance`  
Release tag: **not created**  
Current evidence status: `pending_manual_windows`

## Scope

M8 Task 37–40 establishes the V1.0 acceptance baseline, traceability matrix,
RC automation, nonfunctional gates, RC1 evidence structure and release freeze
guard. It does not claim the unavailable Windows/Office/real-service/manual
audiovisual checks as passed.

## Commits

| Milestone                                      | Commit    | Result    |
| ---------------------------------------------- | --------- | --------- |
| M8 design and plan                             | `1f42f36` | committed |
| Task 37 acceptance baseline                    | `7785749` | committed |
| Task 38 RC automation and nonfunctional checks | `435657c` | committed |
| Task 39 RC1 evidence record                    | `c665f34` | committed |
| Task 40 release freeze guard                   | `ff188a2` | committed |
| M8 static gate corrections                     | `1b84c22` | committed |

## Automated evidence

| Gate                                             | Evidence                                             |
| ------------------------------------------------ | ---------------------------------------------------- |
| Python full suite                                | `229 passed, 1 warning`                              |
| Ruff                                             | passed                                               |
| Strict mypy                                      | passed on `apps/api/src`                             |
| Web unit tests                                   | `25 passed`                                          |
| Remotion tests                                   | `5 passed`                                           |
| ESLint and Prettier                              | passed                                               |
| TypeScript                                       | passed                                               |
| Production build                                 | passed                                               |
| Playwright                                       | `3 passed, 2 skipped`                                |
| M8 acceptance/performance/security/release tests | included in Python suite; passed                     |
| Release freeze behavior                          | current `pending_manual_windows` evidence is blocked |

The two Playwright skips are explicit real-service tests: real HeyGen and the
real local-audio full chain. They are skipped unless `M8_RUN_REAL_E2E` is set;
no paid request was made in this environment.

## Traceability and artifacts

- `docs/traceability.xlsx`: Summary, Traceability and Fixtures sheets.
- `tests/acceptance/fixtures-manifest.json`: 12 reproducible fixtures.
- `tests/acceptance/acceptance-plan.md`: AC-001 through AC-023 and FR/NFR mapping.
- `docs/acceptance-report-RC1.md`: RC1 report with explicit pending status.
- `tests/acceptance/results/RC1/evidence-manifest.json`: six scenarios and the
  nine-item production package manifest.
- `docs/acceptance-signoff-v1.0.md`: unsigned sign-off template.
- `scripts/freeze-release.ps1`: refuses freeze until signed evidence is complete.

## Manual Windows acceptance still required

The following remain `pending_manual_windows` and block the formal V1.0 tag:

- clean Windows 10/11 VM with real Office and Chinese-path smoke coverage;
- Word/PPTX/searchable PDF/scanned PDF/MP3/WAV import and full project flow;
- multi-image natural sort and manual correction;
- real local voice and HeyGen two-page routes with cost/cache evidence;
- recovery, retry, update, rollback, shortcut and browser-open checks;
- manual audiovisual review of MP4, SRT and narration alignment;
- P0/P1 defect assessment and final signer entry.

Until those items are completed, the correct state is an auditable RC candidate,
not a released V1.0.0.
