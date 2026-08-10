# EffectPlan V2 Contract Design

## Goal

Add a strict, shared Python and TypeScript contract for page-level effect plans while preserving the visual timing of legacy V1 plans.

## Architecture

Python owns migration and canonical persistence. `migrate_effect_plan()` hashes the untouched V1 payload using sorted compact JSON, copies its page identity, duration, effects, and manual lock, then fills V2-only metadata with deterministic defaults. Pydantic models reject unknown fields at every nested boundary.

Remotion consumes the resulting V2 JSON through a dependency-free parser and matching TypeScript types. The parser rejects unknown top-level fields and validates the required page, timing, aspect-ratio, and timeline-array contract before rendering.

## Compatibility and Safety

- V1 effect `type`, `start_ms`, and `end_ms` values are copied unchanged.
- The migration records `migration_version=v1-to-v2` and a SHA-256 of the exact logical V1 payload.
- V2 defaults use a static camera, crossfade transition, steady rhythm, tech-blue background, and `SafeSlide` fallback.
- Unsupported schema versions and malformed or unknown fields fail closed.

## Verification

Python contract tests cover deterministic migration and strict unknown-field rejection. Remotion tests parse the migrated fixture and reject unknown top-level fields. Focused typecheck and both test suites are required before full project gates.
