# Dependency security remediation implementation plan

- [x] Separate zero secret-scanning alerts from dependency vulnerability alerts.
- [x] Record the open alert baseline by severity, package, scope, and patched version.
- [x] Prioritize the Remotion and Vitest critical advisories.
- [x] Diagnose the Remotion upgrade failure on Ubuntu and Windows.
- [x] Limit the Remotion compatibility change to the static unit-test asset boundary.
- [ ] Merge the synchronized Remotion upgrade after all protected checks pass.
- [ ] Upgrade Vitest and regenerate the root pnpm lockfile.
- [ ] Remediate direct high-severity JavaScript and Python dependencies.
- [ ] Recount alerts and link the final evidence from the tracking Issue.
- [ ] Prepare a later patch release without changing `v0.1.0`.
