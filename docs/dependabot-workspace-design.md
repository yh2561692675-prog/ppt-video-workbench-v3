# Dependabot workspace design

## Problem

The JavaScript packages are one pnpm workspace with a single root `pnpm-lock.yaml`.
Directory-scoped update PRs that edit only `remotion/package.json` are incomplete,
and independent Remotion updates can split packages that must remain on the same
version.

## Design

- Configure the npm ecosystem at `/`, the pnpm workspace root.
- Group `remotion` and `@remotion/*` so the renderer and CLI move together.
- Keep Python (`uv`) and GitHub Actions updates as separate weekly queues.
- Require the same protected cross-platform checks and human review as any other
  pull request; dependency PRs are never auto-merged.

## Safety properties

- Frozen installs continue to verify the committed root lockfile.
- A failed or incomplete dependency PR cannot enter the protected default branch.
- Runtime, test-tool, and workflow dependencies remain reviewable as separate
  maintenance concerns.
