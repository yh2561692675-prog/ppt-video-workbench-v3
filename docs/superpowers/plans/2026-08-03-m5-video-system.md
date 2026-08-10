# M5 Video System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the M5 subtitle, preview, Remotion, rendering, and complete production-package loop on top of the M4 audio gate.

**Architecture:** Freeze a Python-owned subtitle/timeline and `ProjectVideoProps` contract first. Feed the same validated props into a Remotion composition for browser preview and page rendering, then use an API-owned export service to perform incremental page rendering, FFmpeg composition, artifact validation, and package manifest generation. Keep the workflow gate in both FastAPI and React Query UI.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, Pillow, FFmpeg/FFprobe, React 19, TypeScript 5.8, Vite, Vitest, Remotion 4.0.340, Playwright, pnpm, uv.

## Global Constraints

- Only implement M5 Task 22—26; do not pull M6 scope into this branch.
- Keep the M4 `PageAudio[]`/audio-gate contract as the only entry to subtitles, preview, and render.
- Freeze 1920×1080, 16:9, explicit FPS, millisecond-to-frame rounding, page order, and versioned cache keys.
- Preserve the whole-page visual texture; do not flatten all text into a new image or attempt PPT element decomposition.
- Every production function gets a behavior test written and observed failing before implementation.
- Never write API keys or other secrets into manifests, responses, export packages, or logs.
- Use fake transports/fixtures for automated external-service tests; record Windows/real-service checks separately.
- Do not claim M5 complete until the fresh full Gate, build, browser, and artifact checks pass on the latest commit.

---

### Task 22: Subtitle timeline and SRT

**Files:**

- Create: `apps/api/src/workbench/subtitles/models.py`
- Create: `apps/api/src/workbench/subtitles/service.py`
- Create: `apps/api/src/workbench/api/subtitles.py`
- Modify: `apps/api/src/workbench/domain/models.py` (manifest subtitle artifact metadata)
- Modify: `apps/api/src/workbench/main.py` (subtitle router/service wiring)
- Modify: `packages/contracts/project.schema.json` and `packages/contracts/openapi.json` through the existing export script
- Create: `tests/unit/subtitles/test_subtitle_service.py`
- Create: `tests/integration/test_subtitle_routes.py`

**Interfaces:**

- Consumes: `ProjectManifest`, confirmed `NarrationRecord`, M4 `AudioGateService`, `Transcript.words`, and `AudioTimeline`/page audio files.
- Produces: `SubtitleCue`, `SubtitleTimeline`, `format_srt()`, `POST /api/projects/{project_id}/subtitles/build`, and `GET /api/projects/{project_id}/subtitles`.

- [ ] **Step 1: Write failing unit tests** for ordered word grouping, page clipping, punctuation-safe cue text, no overlap, SRT timestamps, and rejection of missing/逆序/out-of-range word timestamps.
- [ ] **Step 2: Run the focused tests** with `UV_CACHE_DIR=/tmp/ppt-video-workbench-m5-uv uv run pytest tests/unit/subtitles/test_subtitle_service.py -q`; expect import/attribute failures because the subtitle module does not exist.
- [ ] **Step 3: Implement minimal subtitle models and service** with strict Pydantic models, deterministic cue IDs, page-relative/absolute time handling, and atomic writes to `06_字幕/字幕时间轴.json` and `06_字幕/字幕.srt`.
- [ ] **Step 4: Run the focused unit tests** and confirm all subtitle behavior passes with no warning output.
- [ ] **Step 5: Add route integration tests** for the audio gate, persistence, idempotent rebuild, and non-secret error responses.
- [ ] **Step 6: Wire the router, export contracts, and run integration/contract tests**; fix only the minimal contract drift.
- [ ] **Step 7: Commit** with `git add apps packages tests && git commit -m "feat: build subtitle timeline and srt"`.

### Task 23: Remotion props contract and base composition

**Files:**

- Create: `apps/api/src/workbench/video/models.py`
- Create: `apps/api/src/workbench/video/props_service.py`
- Create: `remotion/src/video/types.ts`
- Create: `remotion/src/video/ProjectVideo.tsx`
- Modify: `remotion/src/Root.tsx`
- Do not modify: `remotion/src/index.ts`; the existing root registration remains valid
- Create: `remotion/src/video/props.fixture.json`
- Create: `tests/unit/video/test_props_service.py`
- Create: `remotion/src/video/props.test.ts`
- Modify: `packages/contracts/project.schema.json` through the existing exporter

**Interfaces:**

- Consumes: `SubtitleTimeline`, confirmed pages, page preview paths, `PageAudio[]`, and project metadata.
- Produces: Python `ProjectVideoProps`, serialized fixture, TypeScript `ProjectVideoProps`, `msToFrames()`, and Remotion `ProjectVideo` composition with 1920×1080 defaults.

- [ ] **Step 1: Write failing Python and TypeScript fixture tests** for required fields, strict unknown-field rejection, dimensions, FPS, deterministic frame conversion, and page ordering.
- [ ] **Step 2: Run both focused suites** and confirm failure comes from missing props models/types rather than test setup.
- [ ] **Step 3: Implement the minimal cross-language props contract** and fixture; keep paths relative to the project package boundary and include template/revision/cache metadata.
- [ ] **Step 4: Implement the base Remotion composition** using props-driven page duration and a stable placeholder layout that preserves aspect ratio.
- [ ] **Step 5: Run Python, Remotion tests, and typecheck**; update only the generated contract snapshots needed for the new fields.
- [ ] **Step 6: Commit** with `git add apps remotion packages tests && git commit -m "feat: freeze video props contract"`.

### Task 24: Technology-board visual template

**Files:**

- Create: `remotion/src/video/TechBoardTemplate.tsx`
- Create: `remotion/src/video/animation.ts`
- Create: `remotion/src/video/TechBoardTemplate.test.tsx`
- Modify: `remotion/src/video/ProjectVideo.tsx`
- Modify: `remotion/src/video/types.ts`
- Modify: `remotion/src/video/props.fixture.json`

**Interfaces:**

- Consumes: `ProjectVideoProps`, page preview image, page title/keywords, subtitle cues, safety-zone settings, and reduced-motion flag.
- Produces: reusable `TechBoardTemplate` with deterministic frame rendering and `template_version` included in cache inputs.

- [ ] **Step 1: Write failing component tests** for 16:9 no-stretch rendering, 5% safe zone, bottom subtitle safe zone, page enter/exit, scanline/grid/fog layers, keyword highlight, and reduced-motion disabling transforms.
- [ ] **Step 2: Run the focused Remotion tests** and verify they fail because the template/effects are absent.
- [ ] **Step 3: Implement minimal CSS/Remotion layers**: whole-page push/zoom, restrained grid, scanline, center fog, focus frame, transition, and readable subtitle panel; do not add PPT element parsing.
- [ ] **Step 4: Run focused tests and Remotion typecheck/build**, then refactor only duplicated animation constants after green.
- [ ] **Step 5: Commit** with `git add remotion && git commit -m "feat: add technology board video template"`.

### Task 25: Preview workbench, subtitle avoidance, and preflight

**Files:**

- Create: `apps/api/src/workbench/video/avoidance.py`
- Create: `apps/api/src/workbench/video/preview_service.py`
- Create: `apps/api/src/workbench/api/video.py`
- Create: `apps/web/src/features/video/PreviewWorkspace.tsx`
- Create: `apps/web/src/features/video/PreviewWorkspace.test.tsx`
- Create: `apps/web/src/features/video/SubtitleStylePanel.tsx`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/features/workflow/WorkflowShell.tsx`
- Modify: `apps/web/src/app/styles.css`
- Create: `tests/unit/video/test_avoidance.py`
- Create: `tests/integration/test_video_preview_routes.py`

**Interfaces:**

- Consumes: audio gate, subtitle timeline, `ProjectVideoProps`, page text occupancy metadata, and template settings.
- Produces: `PreviewPreflight`, subtitle placement decision, `GET /preview`, `POST /preflight`, preview session payload, and a Step 6 React workspace.

- [ ] **Step 1: Write failing avoidance/preflight tests** for preferred positions, collision fallback to translucent panel, missing subtitles, stale props, and gate-blocked preview/render.
- [ ] **Step 2: Run focused Python and React tests** and verify they fail due to absent avoidance service, routes, and workspace.
- [ ] **Step 3: Implement deterministic avoidance** with explicit candidate rectangles, 5% canvas bounds, text occupancy, bottom safe zone, and auditable fallback reason.
- [ ] **Step 4: Implement preview/preflight service and API routes** using the same serialized props as Remotion; prevent step 6/7 bypass and keep errors secret-free.
- [ ] **Step 5: Implement React Query workspace** with page jump, play/pause preview controls, style/reduced-motion controls, per-page issues, and disabled Step 7 until preflight is allowed.
- [ ] **Step 6: Run focused/full Python and web suites**, including refresh synchronization after preflight/settings changes; fix static formatting and type errors.
- [ ] **Step 7: Commit** with `git add apps tests packages && git commit -m "feat: add video preview and preflight workspace"`.

### Task 26: Incremental rendering, FFmpeg composition, and production package

**Files:**

- Create: `apps/api/src/workbench/video/render_service.py`
- Create: `apps/api/src/workbench/video/package_service.py`
- Modify: `apps/api/src/workbench/api/video.py`
- Modify: `apps/api/src/workbench/domain/models.py` (persist `VideoPreflightRecord` and `VideoExportRecord`)
- Create: `tests/unit/video/test_render_service.py`
- Create: `tests/integration/test_video_render_routes.py`
- Create: `tests/integration/test_m5_gate.py`
- Create: `M5-GATE.md`
- Do not modify: `scripts/check.sh`; the existing full gate remains the M5 command

**Interfaces:**

- Consumes: allowed `PreviewPreflight`, `ProjectVideoProps`, Remotion renderer command, FFmpeg/FFprobe, subtitle SRT, narration DOCX exporter, and page audio files.
- Produces: page render cache, final MP4, SRT, complete production package, manifest with SHA-256 entries, render/preflight logs, and API job status.

- [ ] **Step 1: Write failing render/package tests** for cache hits, one-page retry, page duration validation, H.264/AAC composition, SRT/DOCX/audio/remotion/config/report/log completeness, path safety, and checksum manifest.
- [ ] **Step 2: Run focused tests** and verify failure is due to missing render/package services or endpoints.
- [ ] **Step 3: Implement page render orchestration** with deterministic cache keys, subprocess argument lists (no shell interpolation), atomic page outputs, and failure-page-only retry state.
- [ ] **Step 4: Implement FFmpeg composition and FFprobe validation** for 1920×1080 H.264/AAC, page/audio duration equality within the declared tolerance, and non-zero output checks.
- [ ] **Step 5: Implement package assembly** with fixed folders, copied/validated artifacts, `制作包清单.json`, SHA-256 entries, and redacted logs.
- [ ] **Step 6: Add render/export routes and Step 7 UI actions**, preserving the preflight gate and refreshing authoritative project state after completion/failure.
- [ ] **Step 7: Run the 8-page fixture M5 integration chain** from audio gate → subtitles → props → preflight → page render → FFmpeg → package; assert all listed artifacts and no extra paid/external calls.
- [ ] **Step 8: Commit** with `git add apps tests remotion packages M5-GATE.md scripts && git commit -m "feat: render video and export production package"`.

### Final M5 Gate and handoff

- [ ] Run fresh `uv run pytest` and record the exact count.
- [ ] Run fresh `uv run ruff check apps tests` and `uv run mypy apps/api/src`.
- [ ] Run fresh `pnpm check`, including web and Remotion test/type/build checks.
- [ ] Run contract export/snapshot checks and `pnpm exec playwright test`.
- [ ] Run the 8-page fixture render and inspect MP4 metadata, SRT, package manifest, checksums, and logs.
- [ ] Run `git diff --check`, inspect the complete branch diff, verify no secrets or generated junk are tracked, and confirm a clean worktree.
- [ ] Write the final M5 Gate record with automated evidence and Windows/real-service supplemental items.
- [ ] Use the finishing branch workflow to present merge/keep options; do not merge or push without the user’s selected option.
