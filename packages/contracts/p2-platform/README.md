# P2 Platform Contract Package

This package freezes the versioned boundary shared by Provider, PlatformServices and Cloud.
The first implementation lives in `apps/api/src/workbench/contracts/p2_platform.py`; this
directory contains language-neutral schemas and snapshots that can be exported to Python,
TypeScript and OpenAPI after the foundation gate.

## Rules

- Every cross-boundary model has `schema_version: 1` and `additionalProperties: false`.
- UUIDs use lowercase RFC 4122 text; timestamps are UTC RFC 3339 with `Z`.
- Canonical JSON uses NFC Unicode, sorted object keys, no insignificant whitespace and no
  NaN/Infinity. Hashes are lowercase `sha256:` strings.
- Logical paths are POSIX-style safe relative paths. Credentials, local absolute paths and
  arbitrary executable extension dictionaries are forbidden.
- `operation_id`, `idempotency_key` and `attempt_id` have distinct lifetimes as defined by
  `docs/adr/p2-platform/ADR-003-operation-id-idempotency-attempt.md` in the design source.

