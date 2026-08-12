# Maintenance workflow implementation plan

## Ordered checklist

- [x] Create a tracking Issue with scope, acceptance criteria, and release-claim boundaries.
- [x] Add structured bug and feature Issue forms plus private security routing.
- [x] Add a PR template and truthful CODEOWNERS ownership.
- [x] Define maintainer triage, review, dependency, and release procedures.
- [x] Add type/status/priority labels used by the documented workflow.
- [x] Add release-note categories and a guarded manual release workflow.
- [x] Add automated validation for package-version alignment and release notes.
- [x] Validate formatting, focused Python checks, and release guard behavior locally.
- [x] Remove duplicate branch/PR CI runs and align workflows with the actual default branch.
- [ ] Open a PR linked to the tracking Issue and record the review evidence.
- [ ] Wait for required CI, then squash-merge the PR.
- [ ] Publish and verify the first honest `0.1.x` source prerelease.
- [ ] Close the tracking Issue with links to the merged PR, CI run, and release.

## Verification commands

```powershell
python scripts/validate-release.py --version 0.1.0
python -m ruff check scripts/validate-release.py
python -m pytest tests/maintenance -q
pnpm exec prettier --check .github README.md docs/maintainer-guide.md
```

The release step remains blocked until the default branch has successful Ubuntu and Windows quality jobs. Windows installer acceptance remains a separate manual gate.
