# Cloud production-readiness gate

The control plane is a local SQLite/WAL prototype. It is not a production
cloud service. Before a production launch, the implementation must move to
PostgreSQL with tenant-scoped row policies and object storage with short-lived
scoped URLs.

Required evidence before enabling production traffic:

- PostgreSQL point-in-time recovery and a recorded restore drill.
- Versioned object retention, deletion/export workflows, and legal-hold policy.
- OIDC issuer/audience/signature validation, device revocation, token rotation,
  and secret rotation evidence.
- SAST/DAST/dependency scanning, tenant-boundary penetration tests, and audit
  log redaction checks.
- Region/data-residency routing, SLOs, cost budgets, rate limits, and alerts.
- Executor crash recovery, result hash/schema/media/ownership verification,
  and no user-provided code execution.

Until those artifacts exist, `CLOUD_SYNC_ENABLED` remains a beta/local flag and
the desktop's local-first behavior is the supported default.
