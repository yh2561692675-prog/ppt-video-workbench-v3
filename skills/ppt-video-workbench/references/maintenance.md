# Repository maintenance workflow

## Triage an Issue

1. Check for credentials, private media, personal data, or vulnerability details. Move sensitive
   security reports to the private channel described in `SECURITY.md`.
2. Search for duplicates and reproduce with synthetic data.
3. Record version, platform, minimal steps, expected result, and observed result.
4. Apply one type label, one status label, and an impact-based priority.
5. Link the implementation PR and target release before closing a fixed Issue.

Use `status:needs-info` when reporter input is required, `status:accepted` when scoped,
`status:in-progress` while a PR is active, and `status:blocked` only for a documented dependency.

## Review a pull request

Review in this order:

1. **Safety:** secrets, private inputs, network calls, filesystem scope, destructive behavior,
   dependency provenance, and logging.
2. **Correctness:** success and failure paths, retries, cancellation, cache invalidation,
   concurrency, and migrations.
3. **Compatibility:** Python/Node constraints, Windows/Linux behavior, API contracts, project data,
   and rollback.
4. **Evidence:** focused regression tests and all required checks. A skipped gate is not a pass.
5. **Maintainability:** scope, naming, documentation, and whether a smaller patch is safer.

For dependency changes, inspect direct constraints and lockfile diffs, read upstream release and
security notes, rebase on the current default branch, and do not auto-merge major versions.

## Publish a source release

1. Resolve or explicitly defer milestone Issues.
2. Align every checked-in package and runtime version.
3. Update `CHANGELOG.md` and add `docs/releases/vX.Y.Z.md`.
4. Merge through a protected PR after required Ubuntu, Windows, and contract checks pass.
5. Confirm the default-branch quality run for the immutable target commit.
6. Dispatch the Release workflow with the exact semantic version and intended prerelease flag.
7. Verify the tag target, release notes, source archives, linked PRs, linked Issues, and artifact
   limitations.

Never reuse or move a published tag. Do not advertise a signed Windows installer unless signing
and manual Windows acceptance evidence both exist.

## Handle a single-maintainer approval exception

The author cannot provide an independent approval. Record a maintainer self-review as a comment,
wait for every required automated check, and request explicit authorization before using an admin
merge that bypasses only the independent-approval requirement. Never bypass CI, unresolved
conversations, or a failing release gate.
