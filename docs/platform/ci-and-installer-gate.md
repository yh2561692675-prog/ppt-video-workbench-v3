# Three-platform CI and installer gate

`.github/workflows/platform-contracts.yml` runs the platform contract suite on
Windows, macOS and Linux. The tag-only installer job is intentionally a hard
gate: it cannot be satisfied by a Linux runner pretending to be macOS or by a
mock signature.

Each OS must attach evidence for first install, upgrade, rollback, uninstall,
data preservation, runtime fingerprint, and signed metadata. Until those
artifacts exist, the workflow proves only contract portability; it does not
claim cross-platform release parity.
