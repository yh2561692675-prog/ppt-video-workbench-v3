# Dependency security remediation design

## Objective

Reduce open dependency vulnerability alerts without weakening compatibility,
cross-platform CI, or the immutable `v0.1.0` source prerelease.

## Evidence and priority

Secret scanning and dependency scanning are separate controls. Secret scanning
currently reports no leaked credentials. Dependency scanning reports duplicated
alerts across manifests and lockfiles, so remediation is prioritized by unique
package and patched version:

1. Remotion `>=4.0.410` and Vitest `>=3.2.6` for critical advisories.
2. React Router, Vite, Starlette, ws, nanoid, and Playwright for high advisories.
3. Remaining medium and low transitive advisories.

## Upgrade rules

- Keep `remotion`, `@remotion/player`, and `@remotion/cli` on one version.
- Update the owning root lockfile with every manifest change.
- Prefer one package family or compatibility boundary per reviewed pull request.
- Treat test failures as evidence: adapt only the boundary whose public contract
  changed, then run the complete protected matrix.
- Never rewrite the `v0.1.0` tag; remediations belong to a later release.

## Remotion compatibility boundary

Remotion 4.0.507 makes `<Img>` consult composition timing context. The
`TechBoardTemplate` unit tests render the template as static HTML to verify its
own subtitle, layout, safe-zone, and reduced-motion behavior. They do not test
Remotion's `<Img>` implementation. The test therefore replaces only `Img` and
`staticFile` with deterministic HTML-boundary substitutes. Production code and
real browser/render checks continue to use Remotion itself.

## Completion evidence

- Protected Ubuntu and Windows quality jobs.
- Linux, macOS, and Windows contract jobs.
- A before/after Dependabot alert count grouped by severity and package.
- Reviewed pull requests linked from the tracking Issue.
