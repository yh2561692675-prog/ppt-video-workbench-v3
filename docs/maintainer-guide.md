# Maintainer guide

This guide defines the public maintenance process for PPT Video Workbench. It is a target for consistent behavior, not a promise of round-the-clock support by a single maintainer.

## Issue triage

Review new Issues approximately weekly when maintainer capacity allows.

1. Confirm that the report contains no credentials, private media, personal data, or vulnerability details. Remove public exposure and follow `SECURITY.md` if it does.
2. Search for duplicates and link the canonical Issue.
3. Reproduce bugs with synthetic data. Record the tested version, environment, minimal steps, and observed result.
4. Apply one type label, one status label, and a priority only after impact is understood.
5. Ask focused questions with `status:needs-info`. Close after 30 days without the requested information, noting that the Issue can be reopened with a reproducer.
6. Before closing a fixed Issue, link the merged PR and identify the first release expected to contain it.

Status labels:

- `status:needs-triage`: not yet assessed.
- `status:needs-info`: blocked on information from the reporter.
- `status:accepted`: scoped and ready for implementation.
- `status:in-progress`: an implementation PR is active.
- `status:blocked`: a documented external decision or dependency prevents progress.

Priority labels describe impact, not arrival order:

- `priority:p0`: active credential exposure, data loss, or a severe vulnerability; move security details to private reporting.
- `priority:p1`: core workflow unusable with no reasonable workaround.
- `priority:p2`: important defect or feature with a workaround.
- `priority:p3`: lower-impact improvement or cleanup.

## Pull request review

Every PR should have one clear outcome, a linked Issue for non-trivial work, exact validation results, and an honest release note. Review in this order:

1. **Safety:** credentials, private inputs, external requests, filesystem scope, destructive operations, dependency provenance, and logging.
2. **Correctness:** user-visible behavior, failure paths, retries, cancellation, cache invalidation, concurrency, and migrations.
3. **Compatibility:** Python/Node versions, Windows and Linux behavior, API/schema stability, project data, and rollback.
4. **Evidence:** focused regression tests plus required repository checks. Never treat a skipped manual gate as passed.
5. **Maintainability:** scope, naming, documentation, and whether a smaller change would be safer.

For a dependency PR, inspect the direct constraint and lockfile diff, read upstream security/breaking-change notes, rebase onto the current default branch, and require all checks to pass before merging. Major-version bumps should not be auto-merged.

The PR author cannot provide an independent approval. While the project has one maintainer, record a self-review as a comment, let required automation complete, and use squash merge. Add another approving reviewer when an active maintainer community exists.

## Release process

Releases follow semantic versioning. A GitHub prerelease may publish source readiness while a platform installer remains pending, but the title and notes must state that boundary explicitly.

1. Resolve or defer all Issues in the milestone and merge through reviewed PRs.
2. Update every checked-in package version and `CHANGELOG.md`.
3. Add `docs/releases/vX.Y.Z.md` with highlights, verification, known limitations, upgrade notes, and contributor credit.
4. Confirm the default branch has successful Ubuntu and Windows `quality` jobs.
5. Run the `Release` workflow with `X.Y.Z`. Keep `prerelease` enabled until all advertised platform acceptance is complete.
6. Verify the immutable tag, release notes, generated source archives, and linked PRs/Issues.
7. Only mark a release as latest/stable when every claim in its notes has corresponding evidence.

Never reuse or move a published tag. If release metadata is wrong, correct the notes; if code is wrong, publish a new patch version.
