# M5 Rendering Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make M5 export and preview use the validated Remotion composition, with frame-correct subtitles, applied avoidance, measured media validation, stale-cache protection, and auditable failures.

**Architecture:** Python remains the owner of the persisted project/props contract and invokes a pinned local Remotion CLI through argument lists. Remotion renders each page segment from the same resolved props used by preview; FFmpeg only concatenates verified H.264/AAC segments. A versioned per-page render input includes the page, its cues, placement, template and reduced-motion settings.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, FFmpeg/FFprobe, Remotion 4.0.340, React 19, @remotion/player, TypeScript, Vitest, Playwright.

## Global Constraints

- Preserve the M4 audio gate and M5 fixed 1920×1080/30 FPS contract.
- Run real Remotion in the artifact integration path; a fake renderer is allowed only in focused cache unit tests.
- Validate every export duration with FFprobe; do not infer duration from props.
- Keep all subprocess calls argument-list based and redact internal tool output from API errors.
- Do not stage, modify, or ignore the user-owned `projects/`, `PROJECTS.md`, or root `.gitignore` changes.

---

### Task 1: Resolve render placements and frame-correct subtitle selection

**Files:**

- Modify: `apps/api/src/workbench/video/models.py`, `apps/api/src/workbench/video/preview_service.py`, `apps/api/src/workbench/video/props_service.py`
- Modify: `remotion/src/video/types.ts`, `remotion/src/video/TechBoardTemplate.tsx`, `remotion/src/video/ProjectVideo.tsx`, `remotion/src/Root.tsx`
- Test: `tests/unit/video/test_props_service.py`, `tests/integration/test_video_preview_routes.py`, `remotion/src/video/TechBoardTemplate.test.tsx`, `remotion/src/video/props.test.ts`

**Interfaces:** `ProjectVideoProps` gains `subtitle_placements`, one `SubtitlePlacement` per page with `page_id`; `TechBoardTemplate` chooses a cue when `cue.start_ms <= frame_ms < cue.end_ms` and uses the page's resolved placement.

- [ ] **Step 1: Write failing tests** proving a later cue is absent before its start and visible only in its frame range; prove preflight serializes a page placement into Props.
- [ ] **Step 2: Run focused tests** with `pnpm --filter @workbench/remotion test` and `uv run pytest tests/integration/test_video_preview_routes.py -q`; expect missing Props field/current page-wide cue behavior.
- [ ] **Step 3: Add the strict Python/TypeScript placement fields and resolve them before preflight persists Props.** Map `top`, `middle`, `bottom`, and `fallback-panel` to CSS geometry, with `panel` determining the opaque fallback.
- [ ] **Step 4: Set Composition `calculateMetadata` from `props.duration_ms` and render active cues from current frame time.**
- [ ] **Step 5: Run focused tests and typecheck**, then commit the self-contained contract/template correction.

### Task 2: Replace static export with Remotion page rendering and validated cache keys

**Files:**

- Modify: `apps/api/src/workbench/video/render_service.py`, `apps/api/src/workbench/video/package_service.py`, `apps/api/src/workbench/main.py`
- Test: `tests/unit/video/test_render_service.py`, `tests/integration/test_video_render_routes.py`, `tests/integration/test_m5_gate.py`

**Interfaces:** `RemotionPageRenderer.render(page, resolved_props, output)` writes a temporary H.264 page MP4 via `pnpm --filter @workbench/remotion exec remotion render remotion/src/index.ts PptVideoWorkbench <output> --props=<json> --frames=<start>-<end>`. `VideoRenderService` cache key hashes the complete resolved per-page props JSON plus source image SHA-256 and renderer version.

- [ ] **Step 1: Write failing integration tests** that inject a renderer recorder and assert that production export invokes the Remotion renderer, not Pillow, with cues/placements/reduced-motion in its JSON input; add a cache test changing a page cue or reduced-motion and expecting a cache miss.
- [ ] **Step 2: Run focused tests** and observe the static PNG path incorrectly satisfies old tests or the new Remotion assertion fails.
- [ ] **Step 3: Implement `RemotionPageRenderer` as the production default, retain `PillowPageRenderer` only as injected test helper, and cache page MP4 artifacts atomically.**
- [ ] **Step 4: Make FFmpeg consume rendered page MP4 segments with per-page audio, then concatenate them.**
- [ ] **Step 5: Run focused tests**, including one real short Remotion+FFmpeg fixture, and commit the renderer/cache correction.

### Task 3: Enforce media duration, subtitle monotonicity, and export failure audit

**Files:**

- Modify: `apps/api/src/workbench/subtitles/service.py`, `apps/api/src/workbench/video/package_service.py`, `apps/api/src/workbench/api/video.py`, `apps/api/src/workbench/domain/models.py`
- Test: `tests/unit/subtitles/test_subtitle_service.py`, `tests/unit/video/test_package_service.py`, `tests/integration/test_video_render_routes.py`

**Interfaces:** FFprobe returns width, height, codecs, and measured `duration_ms`; `VideoExportService` accepts a configurable `duration_tolerance_ms=100` and blocks a mismatched page or final file. `VideoExportRecord` stores completed or failed status plus safe error code; the audit log records render start, page failure/retry, and completion without command stderr.

- [ ] **Step 1: Write failing tests** for overlapping word intervals, an output duration outside tolerance, and a renderer/FFmpeg failure returning the existing redacted API envelope while persisting failure audit state.
- [ ] **Step 2: Run the focused tests** and confirm they fail because intervals/durations are currently accepted or failure state is absent.
- [ ] **Step 3: Reject overlap before subtitle cue construction and globally validate emitted cue monotonicity.**
- [ ] **Step 4: Extend FFprobe parsing and validate each page/final duration; record failure before re-raising a redacted `VideoExportError`.**
- [ ] **Step 5: Run focused tests and commit the media/audit correction.**

### Task 4: Make browser preview and Step 7 consume the persisted render contract

**Files:**

- Modify: `apps/web/package.json`, `pnpm-lock.yaml`, `apps/web/src/api/client.ts`, `apps/web/src/features/video/PreviewWorkspace.tsx`, `apps/web/src/features/workflow/WorkflowShell.tsx`, `apps/web/src/app/styles.css`
- Test: `apps/web/src/features/video/PreviewWorkspace.test.tsx`, `apps/web/src/features/workflow/WorkflowShell.test.tsx` if needed

**Interfaces:** The preview component receives `VideoPreflight.props`, embeds `@remotion/player` with the same props, updates `reduced_motion` through a preflight settings request, and the render action/status is available when current step is 7 and preflight is allowed.

- [ ] **Step 1: Write failing UI tests** showing that play/pause controls a real Player, reduced-motion updates the submitted render settings, and Step 7 exposes a gated render action/result.
- [ ] **Step 2: Run the focused web tests** and observe the current static image/toggle-only behavior fail.
- [ ] **Step 3: Add the direct Player dependency, a persisted settings/preflight route, and a Step 7 export panel using the same query state.**
- [ ] **Step 4: Run web tests, typecheck and production build**, then commit the preview/workflow correction.

### Final correction gate

- [ ] Run `bash scripts/check.sh` and `PLAYWRIGHT_BROWSERS_PATH=/tmp/ppt-video-workbench-playwright pnpm exec playwright test` on the final commit.
- [ ] Run the short real Remotion artifact chain, inspect ffprobe dimensions/codecs/duration and verify package SHA-256 entries independently.
- [ ] Refresh contract snapshots and `M5-GATE.md`, re-request independent review, then present branch integration options only after a green corrected gate.
