# EffectPlan V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a strict cross-language EffectPlan V2 contract with deterministic V1 migration.

**Architecture:** Python validates and migrates persisted plans; Remotion validates migrated JSON at its boundary. Both sides share field names, enum values, and fail-closed unknown-field behavior.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, TypeScript 5.8, Vitest.

## Global Constraints

- Preserve V1 effect timing and manual-lock behavior.
- Do not add runtime dependencies.
- Reject unknown fields and unsupported schema versions.

---

### Task 1: Python V2 contract and migration

**Files:**

- Create: `apps/api/src/effects/__init__.py`
- Create: `apps/api/src/effects/schema.py`
- Modify: `apps/api/pyproject.toml`
- Test: `tests/contract/test_effect_plan_v2.py`

- [x] **Step 1:** Run the new test and observe the missing-module failure.
- [x] **Step 2:** Add strict nested Pydantic models and deterministic V1 migration.
- [ ] **Step 3:** Run the focused Python contract test, Ruff, and Mypy.

### Task 2: Remotion V2 parser

**Files:**

- Create: `remotion/src/types.ts`
- Create: `remotion/src/effects/effectPlanSchema.ts`
- Test: `remotion/src/effects/effectPlanSchema.test.ts`

- [x] **Step 1:** Preserve the concurrently supplied TypeScript implementation.
- [x] **Step 2:** Run the focused Vitest suite.
- [ ] **Step 3:** Run Remotion typecheck and compare the Python/TypeScript contract fields.

### Task 3: Gate verification

- [ ] **Step 1:** Run both focused suites together.
- [ ] **Step 2:** Run full Python and Node gates and record remaining pre-existing failures separately.
