# Dependabot workspace implementation plan

- [x] Record the invalid subdirectory updates and their review decisions.
- [x] Close PRs that omit the root lockfile or split synchronized packages.
- [x] Add a Dependabot v2 configuration at `.github/dependabot.yml`.
- [x] Point npm updates at the pnpm workspace root.
- [x] Group the Remotion package family.
- [x] Keep separate uv, npm, and GitHub Actions update queues.
- [x] Verify GitHub accepts the configuration on a protected pull request.
- [x] Close the tracking Issue after the protected checks pass and the PR merges.
- [x] Observe the first update run and record its initial PR volume.
- [x] Change routine scans to monthly and cap each ecosystem at three PRs.
- [x] Group routine minor/patch and GitHub Actions updates.
- [x] Close initialization PRs that are superseded by the queue policy.
