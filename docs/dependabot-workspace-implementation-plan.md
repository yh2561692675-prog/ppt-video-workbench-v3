# Dependabot workspace implementation plan

- [x] Record the invalid subdirectory updates and their review decisions.
- [x] Close PRs that omit the root lockfile or split synchronized packages.
- [x] Add a Dependabot v2 configuration at `.github/dependabot.yml`.
- [x] Point npm updates at the pnpm workspace root.
- [x] Group the Remotion package family.
- [x] Keep weekly uv and GitHub Actions update queues.
- [ ] Verify GitHub accepts the configuration on a protected pull request.
- [ ] Close the tracking Issue after the protected checks pass and the PR merges.
