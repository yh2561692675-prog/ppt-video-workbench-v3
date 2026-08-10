# HeyGen Resilient Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one HeyGen batch click continue past transient page failures and automatically retry only failed pages and chunks.

**Architecture:** Keep the existing single-page API and persistent chunk cache. Strengthen the remote request boundary with three bounded attempts and shorter chunks, then add a three-pass scheduler in the existing React panel that classifies structured API errors.

**Tech Stack:** Python 3.12, FastAPI, httpx, pytest, React 19, TypeScript, Vitest.

## Global Constraints

- Never regenerate a completed page whose cache key already matches.
- Never mix local audio and HeyGen page audio.
- Maximum remote attempts per chunk: 3.
- Maximum page-level batch passes: 3.
- Fatal authentication, quota, route, and regeneration errors stop immediately.
- No new runtime dependency.

---

### Task 1: Structured Web API Errors

**Files:**

- Modify: `apps/web/src/api/client.ts`
- Test: `apps/web/src/api/client.contract.test.ts`

**Interfaces:**

- Produces: `ApiRequestError` with `code`, `action`, and `status` fields.
- Consumes: Existing JSON envelope `{data,error,request_id}`.

- [ ] Add a failing contract test that returns a 422 envelope with `heygen_timeout` and asserts the thrown value retains the code and action.
- [ ] Run the focused Vitest test and confirm it fails because the current client throws a plain `Error`.
- [ ] Add `ApiRequestError` and throw it from `request()` without changing successful response behavior.
- [ ] Run the focused test and confirm it passes.

### Task 2: Batch Continues and Replays Failed Pages

**Files:**

- Create: `apps/web/src/features/audio/heygen/HeyGenAudioPanel.tsx`
- Create: `apps/web/src/features/audio/heygen/HeyGenAudioPanel.test.tsx`

**Interfaces:**

- Consumes: `api.synthesizeHeyGenAudio()` and `ApiRequestError`.
- Produces: A maximum-three-pass UI scheduler with one final failure summary.

- [ ] Add a failing component test with pages 1—3 where page 2 returns `heygen_timeout` twice; assert page 3 is attempted before page 2 succeeds on pass 3.
- [ ] Run the focused Vitest test and confirm the current fail-fast loop does not call page 3.
- [ ] Replace the fail-fast loop with a pending-page queue, success ID set, explicit retryable-code classification, and three-pass bound.
- [ ] Add a failing test for three exhausted pages and assert one aggregated alert is rendered.
- [ ] Implement the final aggregation and rerun both tests.

### Task 3: Bounded Backend Retries and Shorter Chunks

**Files:**

- Modify: `apps/api/src/workbench/integrations/heygen/client.py`
- Modify: `apps/api/src/workbench/audio/heygen_chunks.py`
- Modify: `tests/integration/test_heygen_retry.py`

**Interfaces:**

- Produces: `HeyGenClient(..., speech_max_attempts=3)` with exponential 2/4 second waits.
- Produces: `DEFAULT_SPEECH_CHUNK_MAX_CHARS = 60` used by `split_speech_text()`.

- [ ] Add a failing test where two `ReadTimeout` exceptions precede success; assert 3 calls and waits `[2, 4]`.
- [ ] Add a failing test that a 130-character clause is divided into parts no longer than 60 characters.
- [ ] Run the focused pytest tests and confirm failures against r21.
- [ ] Implement configurable bounded attempts, exponential backoff, and the 60-character default.
- [ ] Update the existing resume fixture so its first page call exhausts all three client attempts, then verify only the missing chunk is requested on the second call.
- [ ] Run the complete HeyGen integration test module.

### Task 4: Full Verification and Direct Overlay Package

**Files:**

- Update generated contract only if the contract test proves it changed.
- Create: `README-r23.md`
- Create: `ppt-video-workbench-heygen-resilient-batch-r23-direct.zip`

**Interfaces:**

- Produces: A root-relative archive that overlays `F:\ppt-video-workbench-v3`.

- [ ] Run Python focused tests, then full pytest excluding only tests that require a real Git worktree if this reconstructed source archive has no `.git` directory.
- [ ] Run Ruff and mypy.
- [ ] Run Web Vitest, TypeScript typecheck, ESLint, and Prettier checks.
- [ ] Verify archive paths, CRC integrity, and ensure no credentials, project data, audio, or build output are included.
- [ ] Save the validated ZIP as the r23 deliverable.
