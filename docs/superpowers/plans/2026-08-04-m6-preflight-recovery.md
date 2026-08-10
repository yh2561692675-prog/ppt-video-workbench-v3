# M6 Preflight and Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured preflight, auditable confirmations, deterministic cache invalidation, crash recovery, and safe cache cleanup on top of the M5 video workbench.

**Architecture:** Add a domain-level issue/report model persisted in `ProjectManifest`; a pure preflight engine computes stable fingerprints and writes immutable JSON snapshots, while a service/API layer enforces current-report render gates. Keep M5 video routes compatible, and add independent cache, checkpoint, and cleanup services whose plans are deterministic and atomically persisted.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, pytest, Ruff, strict mypy, React, TypeScript, Vitest, Playwright, `project.json`, SHA-256, pathlib, Remotion/FFmpeg integration already present in M5.

## Global Constraints

- Target platform remains Windows 10/11 64-bit; do not add cross-platform product scope.
- Default output remains 1920×1080, 16:9, MP4, H.264, AAC, embedded Chinese subtitles plus SRT.
- Only confirmed narration, processed audio differences, and a current preflight with no blocking/unconfirmed issues may enter formal render.
- Every issue has stable `code`, `issue_id`, location, action, level, fingerprint, and blocking semantics; no free-text-only flow decisions.
- `project.json` is authoritative and must be written through existing atomic `ManifestStore`; user files outside the M6 scope remain untouched.
- No API key, authentication header, remote response credential, or source正文 is written to logs, reports, checkpoints, or packages.
- Production code is written only after a focused test has failed for the intended missing behavior.
- Each task ends with focused tests, static checks, a clean diff check, and one independent commit.

---

### Task 27: Structured issue catalog and incremental preflight engine

**Files:**

- Create: `apps/api/src/workbench/domain/issues.py`
- Create: `apps/api/src/workbench/preflight/__init__.py`
- Create: `apps/api/src/workbench/preflight/engine.py`
- Create: `apps/api/src/workbench/preflight/checks/__init__.py`
- Create: `apps/api/src/workbench/preflight/checks/common.py`
- Create: `apps/api/src/workbench/preflight/checks/materials.py`
- Create: `apps/api/src/workbench/preflight/checks/content.py`
- Create: `apps/api/src/workbench/preflight/checks/audio.py`
- Create: `apps/api/src/workbench/preflight/checks/video.py`
- Create: `apps/api/src/workbench/preflight/checks/runtime.py`
- Modify: `apps/api/src/workbench/domain/models.py`
- Modify: `packages/contracts/project.schema.json`
- Create: `tests/unit/preflight/test_engine.py`
- Create: `tests/unit/preflight/test_checks.py`
- Create: `tests/contracts/test_m6_issue_schema.py`

**Interfaces:**

- Produces `IssueLevel`, `PreflightIssue`, `PreflightReport`, `IssueConfirmation`, `PreflightScope`.
- Produces `PreflightEngine.run_preflight(project, scope=None, previous=None) -> PreflightReport`.
- Each check returns `list[PreflightIssue]` plus a deterministic input fingerprint.
- `ProjectManifest` gains optional `preflight_report`, `preflight_history`, `issue_confirmations`, and `cleanup_plans` fields with defaults so M1–M5 JSON remains readable.

- [ ] **Step 1: Write failing model and behavior tests.** Cover all eight check domains, stable IDs, issue levels, actions, page/path locations, blocking calculation, report snapshots, unchanged-check reuse, changed-input re-run, and legacy manifest validation.
- [ ] **Step 2: Run the focused tests to confirm the expected RED state.** Run `uv run pytest tests/unit/preflight tests/contracts/test_m6_issue_schema.py -v`; expect import/model failures because the new domain and engine do not exist.
- [ ] **Step 3: Implement the domain models and manifest fields.** Use `ConfigDict(extra="forbid")`, UUID5 for stable issue IDs, explicit literals, and optional fields with empty defaults; do not increment `schema_version`.
- [ ] **Step 4: Implement pure check helpers.** Use safe project-relative paths, existing page/extraction/audio/subtitle fields, and redacted runtime probes. Return stable codes such as `source_missing`, `page_preview_missing`, `narration_unconfirmed`, `audio_difference_pending`, `subtitle_missing`, `ffmpeg_unavailable`, and `disk_space_low` with Chinese actionable messages.
- [ ] **Step 5: Implement incremental engine and atomic report snapshots.** Fingerprint only relevant inputs per check, reuse previous results when the fingerprint is unchanged, recompute changed or scoped checks, calculate `allowed`, and write `09_日志/预检/预检报告-<report_id>.json` through a temp file plus `os.replace`.
- [ ] **Step 6: Run focused tests, Ruff, and strict mypy.** Run `uv run pytest tests/unit/preflight tests/contracts/test_m6_issue_schema.py -v`, `uv run ruff check apps/api/src/workbench tests/unit/preflight tests/contracts/test_m6_issue_schema.py`, and `uv run mypy apps/api/src/workbench`.
- [ ] **Step 7: Export the contract snapshot and commit.** Run `uv run python scripts/export_contracts.py`; run `git diff --check`; commit `feat: add complete structured preflight engine`.

### Task 28: Preflight service, confirmation API, report export, and workspace

**Files:**

- Create: `apps/api/src/workbench/services/preflight_service.py`
- Create: `apps/api/src/workbench/api/preflight.py`
- Create: `apps/api/src/workbench/exports/preflight_report.py`
- Modify: `apps/api/src/workbench/main.py`
- Modify: `apps/api/src/workbench/video/package_service.py`
- Modify: `apps/api/src/workbench/api/projects.py`
- Create: `apps/web/src/features/preflight/PreflightWorkspace.tsx`
- Create: `apps/web/src/features/preflight/PreflightWorkspace.test.tsx`
- Modify: `apps/web/src/features/workflow/WorkflowShell.tsx`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/app/styles.css`
- Create: `tests/integration/test_preflight_routes.py`
- Create: `tests/e2e/preflight-gate.spec.ts`

**Interfaces:**

- `PreflightService.run(project_id, scope=None) -> PreflightReport`.
- `PreflightService.confirm(project_id, issue_id, actor, note) -> PreflightReport`.
- `PreflightService.render_gate(project_id) -> PreflightReport`.
- `POST/GET /api/projects/{id}/preflight`, `POST /api/projects/{id}/issues/{issue_id}/confirm`, and `GET /api/projects/{id}/preflight/report`.
- Compatibility routes `/api/projects/{id}/video/preflight` and `/video/render` must continue to pass existing M5 tests.

- [ ] **Step 1: Write failing API and UI tests.** Cover blocking issues returning 409 from render, confirmation-level issues allowing render only after confirmation, stale reports after a source/page mutation, direct HTTP render bypass rejection, JSON/Markdown report output, grouped UI levels, location labels, and confirmation audit text.
- [ ] **Step 2: Run the focused tests to confirm RED.** Run `uv run pytest tests/integration/test_preflight_routes.py -v` and `pnpm --filter web test -- PreflightWorkspace`; expect missing router/service/component failures.
- [ ] **Step 3: Implement the service and routes.** Re-load the manifest before every mutation, reject stale issue IDs, persist `IssueConfirmation` and `AuditEvent`, and return structured `ProblemDetails` with `blocking`, `page_id`, and `job_id`.
- [ ] **Step 4: Make formal render require the current M6 report.** The gate must run or validate a report whose project fingerprint still matches; it must call the existing M5 video preflight before export and reject any blocking/unconfirmed issue before FFmpeg or paid work begins.
- [ ] **Step 5: Implement report JSON/Markdown export.** Markdown must include check time, level, code, location, reason, action, confirmation actor/time, and final render decision; redact credentials and source正文.
- [ ] **Step 6: Implement the React workspace and connect Step 6.** Keep the existing Remotion preview, add grouped issue cards, confirmation controls only for non-blocking issues, report export actions, and page navigation callbacks; disable render until the latest report is allowed.
- [ ] **Step 7: Run API, Web, E2E, contract, and static checks.** Run focused tests first, then `uv run pytest tests/integration/test_m5_gate.py tests/integration/test_video_render_routes.py tests/integration/test_preflight_routes.py -v`, `pnpm --filter web test`, `pnpm --filter web typecheck`, and Playwright with the project Chromium cache.
- [ ] **Step 8: Commit.** Run `git diff --check`; commit `feat: enforce preflight review and reporting`.

### Task 29: Deterministic cache keys and exact dependency invalidation

**Files:**

- Create: `apps/api/src/workbench/cache/__init__.py`
- Create: `apps/api/src/workbench/cache/key.py`
- Create: `apps/api/src/workbench/cache/dependency_graph.py`
- Create: `tests/unit/cache/test_invalidation_matrix.py`
- Create: `tests/unit/cache/test_cache_key.py`
- Modify: `apps/api/src/workbench/domain/models.py`

**Interfaces:**

- `CacheKeyBuilder.build(node, inputs) -> str`.
- `InvalidationEvent(kind, page_id=None, affected_page_ids=(), payload={})`.
- `InvalidationPlan(preserve: list[str], rebuild: list[str], reason: str)`.
- `DependencyGraph.invalidate(project, event) -> InvalidationPlan`.

- [ ] **Step 1: Write the parameterized six-event matrix as failing tests.** Assert exact preserve/rebuild sets for single-page narration, timeline change, source/content change, template change, HeyGen voice change, and runtime upgrade; assert unrelated pages remain preserved.
- [ ] **Step 2: Run the matrix to confirm RED.** Run `uv run pytest tests/unit/cache/test_cache_key.py tests/unit/cache/test_invalidation_matrix.py -v`; expect missing module failures.
- [ ] **Step 3: Implement canonical cache key serialization.** Normalize dictionaries and lists, include required source/content/template fields, add narration/audio/timeline/subtitle versions where applicable, and hash canonical JSON with SHA-256.
- [ ] **Step 4: Implement the dependency graph.** Represent project-wide nodes and page-scoped nodes separately; propagate only downstream dependencies and mark `final` invalid whenever any segment changes.
- [ ] **Step 5: Run matrix, static checks, and commit.** Run the focused tests, Ruff, mypy, `git diff --check`; commit `feat: implement deterministic cache invalidation`.

### Task 30: Checkpoints, pause/cancel boundaries, and crash recovery

**Files:**

- Create: `apps/api/src/workbench/jobs/checkpoint.py`
- Modify: `apps/api/src/workbench/jobs/repository.py`
- Modify: `apps/api/src/workbench/jobs/runner.py`
- Create: `tests/integration/test_crash_recovery_matrix.py`
- Create: `tests/unit/jobs/test_checkpoint.py`
- Create: `scripts/kill-recovery-test.ps1`

**Interfaces:**

- `JobContext(job_id, project_dir, job_type, paid=False)`.
- `JobContext.checkpoint(progress, payload, artifacts=()) -> Checkpoint`.
- `JobContext.request_pause()`, `request_cancel()`, `should_pause`, `should_cancel`.
- `CheckpointStore.latest(job_id) -> Checkpoint | None` and `restore(job_id, verify=True) -> Checkpoint | None`.
- `recover_job(job_id, handler) -> JobRecord`.

- [ ] **Step 1: Write failing checkpoint and recovery tests.** Cover 30%/70% interruption for OCR, ASR, HeyGen polling, page rendering, and composition; assert completed pages and hashes remain unchanged, temporary files are cleaned, and paid remote IDs are queried before creation.
- [ ] **Step 2: Run the focused tests to confirm RED.** Run `uv run pytest tests/unit/jobs/test_checkpoint.py tests/integration/test_crash_recovery_matrix.py -v`; expect missing checkpoint/recovery behavior.
- [ ] **Step 3: Implement atomic checkpoint storage.** Store sanitized payload, progress, stage, cache keys, artifact hashes, temporary paths, and remote task IDs under `09_日志/检查点/`; use atomic replace and reject malformed checkpoints.
- [ ] **Step 4: Implement safe-boundary controls.** Pause only after a handler checkpoint; cancel removes only declared temporary artifacts; recovery validates hashes and cache keys before reusing an artifact.
- [ ] **Step 5: Integrate with job persistence and paid task idempotency.** Recover the latest job state at startup, preserve successful pages, and expose a remote-status lookup hook that must run before any new paid request.
- [ ] **Step 6: Run interruption matrix, static checks, and the PowerShell script where available.** Run `uv run pytest tests/unit/jobs tests/integration/test_crash_recovery_matrix.py -v`, Ruff, mypy, and `powershell -File scripts/kill-recovery-test.ps1` on Windows or the repository's non-Windows simulation path in this environment.
- [ ] **Step 7: Commit.** Run `git diff --check`; commit `feat: recover interrupted long-running jobs`.

### Task 31: Safe cache cleanup and M6 stage gate

**Files:**

- Create: `apps/api/src/workbench/cache/cleanup.py`
- Create: `apps/api/src/workbench/api/storage.py`
- Create: `apps/web/src/features/projects/storage/StoragePanel.tsx`
- Create: `apps/web/src/features/projects/storage/StoragePanel.test.tsx`
- Modify: `apps/web/src/features/projects/ProjectCenter.tsx`
- Modify: `apps/web/src/api/client.ts`
- Create: `tests/unit/cache/test_cleanup.py`
- Create: `tests/integration/test_cleanup_routes.py`
- Create: `M6-GATE.md`

**Interfaces:**

- `estimate_cleanup(project, selection=None) -> CleanupPlan`.
- `execute_cleanup(plan_id, confirmation_token) -> CleanupResult`.
- `POST /api/projects/{id}/storage/cleanup/estimate` and `POST /api/projects/{id}/storage/cleanup/execute`.

- [ ] **Step 1: Write failing protection and interruption tests.** Assert source files, confirmed narration/history, final packages, `project.json`, backup, index metadata, and current checkpoints are never selected; assert sizes and affected nodes are reported; assert interrupted cleanup leaves manifest unchanged.
- [ ] **Step 2: Run cleanup tests to confirm RED.** Run `uv run pytest tests/unit/cache/test_cleanup.py tests/integration/test_cleanup_routes.py -v`; expect missing module/route failures.
- [ ] **Step 3: Implement whitelist-based cleanup planning.** Enumerate only known rebuildable paths under `02_页面预览`, `03_文字识别`, `05_音频` derived intermediates, `06_字幕` derived files, `07_视频工程` caches/segments, and stale report/checkpoint files; reject path traversal and symlink escapes.
- [ ] **Step 4: Implement atomic execution and manifest update.** Require a fresh plan ID and second confirmation, delete only selected files, write a temp manifest that marks affected nodes missing, then replace it only after all deletions succeed; on failure restore the prior manifest and return a structured error.
- [ ] **Step 5: Implement storage API and Project Center panel.** Show freeable size, affected pages/nodes, protected items, second confirmation, progress/result, and a clear “下一次操作将按依赖重建” message.
- [ ] **Step 6: Run all M6-focused tests and the full project Gate.** Run Python full suite, Ruff, strict mypy, contract export, Web/Remotion tests, typecheck, lint/Prettier, production build, and Playwright preflight/recovery flows.
- [ ] **Step 7: Write and verify `M6-GATE.md`.** Record Task 27–31 commits, test counts, six-event invalidation matrix, five recovery scenarios, cleanup protection evidence, known environment limits, and exact reproduction commands.
- [ ] **Step 8: Commit and perform final verification.** Run `git diff --check`, commit `feat: add safe project cache cleanup`, then rerun all final checks on the latest commit before branch integration.
