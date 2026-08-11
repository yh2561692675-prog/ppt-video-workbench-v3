# Three-platform CI and installer gate

`.github/workflows/platform-contracts.yml` runs the platform contract suite on
Windows, macOS and Linux. The tag-only installer job is intentionally a hard
gate: it cannot be satisfied by a Linux runner pretending to be macOS or by a
mock signature.

Each OS must attach evidence for first install, upgrade, rollback, uninstall,
data preservation, runtime fingerprint, and signed metadata under
`artifacts/platform/{windows,macos,linux}/`. The tag gate requires non-empty
`install.json`, `upgrade.json`, `rollback.json`, `uninstall.json`,
`runtime.json`, and `signature.json` for every real runner. The tag gate also
runs `scripts/verify_platform_evidence.py`, which rejects mismatched platform
identity, `real_runner=false`, missing media hashes, unverified signatures and
mock/test signing algorithms. Until those artifacts exist, the workflow proves
only contract portability; it does not claim cross-platform release parity.
