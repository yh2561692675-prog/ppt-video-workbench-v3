# Maintenance workflow design

## Objective

Make public maintenance activity useful to contributors and auditable to reviewers: structured reports, explicit review evidence, deterministic release validation, and honest platform-readiness claims.

## Design decisions

- GitHub Issue Forms collect reproducible inputs and require a credential/privacy safety check.
- Blank Issues are disabled; suspected vulnerabilities route to private security reporting.
- A single PR template covers scope, tests, security/privacy, rollback, and release-note impact.
- CODEOWNERS reflects the real current maintainer and does not invent reviewers.
- Maintainer labels separate type, status, and priority so state can be queried consistently.
- Releases are manual, immutable, and validated against all four package version declarations, a versioned notes file, and successful default-branch Linux and Windows CI.
- `0.1.x` can be a source prerelease while Windows installer acceptance remains pending. Release notes must not imply otherwise.

## Trust boundaries

Issue and PR text is untrusted public input. Contributors are instructed not to attach secrets or private data. The release workflow runs only through `workflow_dispatch`, has read access to Actions and write access to repository contents, refuses existing tags, and publishes only the checked-out default-branch commit.

## Success criteria

- A new contributor can file a complete report without maintainer back-and-forth about basic environment and reproduction details.
- A reviewer can determine scope, risk, tests, and release impact from the PR body.
- An Issue has visible state and a linked resolution.
- A release cannot be published with version drift, missing notes, failed default-branch quality jobs, or a reused tag.
