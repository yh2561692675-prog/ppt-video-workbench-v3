# P02 Health Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a non-blocking one-click diagnostic center that classifies 13 health areas, exports a sanitized evidence bundle, and recognizes at least 95% of known injected faults.

**Architecture:** Extend the existing local environment route with a focused `workbench.diagnostics` package. The engine runs independent probes behind exception boundaries; the API and React UI consume strict report models, while the old environment endpoints remain compatible fallbacks.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLite, pytest, React 19, TypeScript, TanStack Query, Vitest.

## Global Constraints

- Preserve all P01 V11 and HeyGen R23 changes.
- Do not modify, delete, migrate, or clean `F:\Video` user data.
- Bind and probe only loopback addresses.
- Do not read or serialize secret plaintext; inspect references only.
- A diagnostic failure must never block `create_app()` or `/api/health`.
- Keep `/api/environment` and its response contract unchanged.
- Do not mix local-recording and HeyGen audio routes.

---

### Task 1: Diagnostic contracts and status aggregation

**Files:**

- Create: `apps/api/src/workbench/diagnostics/__init__.py`
- Create: `apps/api/src/workbench/diagnostics/models.py`
- Create: `tests/unit/diagnostics/test_models.py`

**Interfaces:**

- Produces: `DiagnosticStatus`, `DiagnosticCategory`, `DiagnosticCheck`, `DiagnosticReport`, `DiagnosticPackage`.

- [ ] **Step 1: Write failing model tests**

```python
def test_report_uses_worst_check_as_overall_status() -> None:
    report = DiagnosticReport.build([green_check(), red_check()])
    assert report.overall_status == DiagnosticStatus.RED
```

- [ ] **Step 2: Run the test and verify the models are missing**

Run: `python -m pytest tests/unit/diagnostics/test_models.py -v`  
Expected: FAIL because `workbench.diagnostics.models` does not exist.

- [ ] **Step 3: Implement strict models and deterministic aggregation**

```python
class DiagnosticReport(StrictModel):
    report_id: UUID
    checked_at: datetime
    overall_status: DiagnosticStatus
    checks: tuple[DiagnosticCheck, ...]

    @classmethod
    def build(cls, checks: Iterable[DiagnosticCheck]) -> "DiagnosticReport": ...
```

- [ ] **Step 4: Run the tests and verify green**

Run: `python -m pytest tests/unit/diagnostics/test_models.py -v`  
Expected: PASS.

### Task 2: Probe isolation and the 13 diagnostic areas

**Files:**

- Create: `apps/api/src/workbench/diagnostics/probes.py`
- Create: `apps/api/src/workbench/diagnostics/center.py`
- Create: `tests/unit/diagnostics/test_center.py`
- Create: `tests/integration/test_diagnostics_fault_injection.py`

**Interfaces:**

- Consumes: `RuntimeLayout`, workspace path, optional `HeyGenHealthProbe`.
- Produces: `DiagnosticCenter.run() -> DiagnosticReport` and `UnavailableDiagnosticCenter.run()`.

- [ ] **Step 1: Write failing tests for all check identifiers and exception isolation**

```python
def test_one_broken_probe_does_not_stop_remaining_checks(tmp_path: Path) -> None:
    center = DiagnosticCenter(tmp_path, probes=fixture_probes(crash="database_integrity"))
    report = center.run()
    assert len(report.checks) == 13
    assert next(c for c in report.checks if c.check_id == "database_integrity").category == "INTERNAL"
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/diagnostics/test_center.py -v`  
Expected: FAIL because the center is not implemented.

- [ ] **Step 3: Implement independent probes and classification**

```python
class DiagnosticCenter:
    def run(self) -> DiagnosticReport:
        return DiagnosticReport.build(self._safe_run(spec) for spec in self._specs)

    def _safe_run(self, spec: CheckSpec) -> DiagnosticCheck:
        try:
            return spec.probe()
        except Exception as error:
            return internal_failure(spec, type(error).__name__)
```

- [ ] **Step 4: Add 20 literal fault fixtures with expected categories**

Run: `python -m pytest tests/integration/test_diagnostics_fault_injection.py -v`  
Expected: PASS with `recognized / total >= 0.95`.

### Task 3: Recursive redaction and atomic diagnostic bundles

**Files:**

- Create: `apps/api/src/workbench/diagnostics/redaction.py`
- Create: `apps/api/src/workbench/diagnostics/package.py`
- Create: `tests/security/test_diagnostic_bundle_redaction.py`

**Interfaces:**

- Consumes: `DiagnosticReport`, allowed log paths, workspace root.
- Produces: `DiagnosticPackager.create(report) -> DiagnosticPackage`.

- [ ] **Step 1: Write a failing secret-leak test**

```python
def test_bundle_never_contains_injected_secrets(tmp_path: Path) -> None:
    injected = "sk-test-DO-NOT-LEAK"
    package = packager_with_log(tmp_path, f"Authorization: Bearer {injected}").create(report())
    assert injected.encode() not in Path(package.absolute_test_path).read_bytes()
```

- [ ] **Step 2: Verify RED, then implement recursive key/text/path redaction**

Run: `python -m pytest tests/security/test_diagnostic_bundle_redaction.py -v`  
Expected before implementation: FAIL; after implementation: PASS.

- [ ] **Step 3: Implement allowlisted, size-limited, atomic ZIP output with manifest hashes**

```python
def create(self, report: DiagnosticReport) -> DiagnosticPackage:
    temporary = target.with_suffix(".zip.tmp")
    write_allowlisted_entries(temporary, redact(report), tail_limit=256 * 1024)
    os.replace(temporary, target)
    return describe_package(target)
```

### Task 4: Non-blocking API integration and PowerShell entrypoint

**Files:**

- Create: `apps/api/src/workbench/api/diagnostics.py`
- Modify: `apps/api/src/workbench/main.py`
- Modify: `scripts/doctor.ps1`
- Create: `tests/integration/test_diagnostics_routes.py`
- Create: `tests/release/test_doctor_script.py`

**Interfaces:**

- Produces: `POST /api/diagnostics/run`, `GET /api/diagnostics/latest`, `POST /api/diagnostics/package`.

- [ ] **Step 1: Write failing route tests including constructor failure**

```python
def test_diagnostic_factory_failure_does_not_block_health(tmp_path: Path) -> None:
    app = create_app(tmp_path, diagnostic_center_factory=raising_factory)
    assert TestClient(app).get("/api/health").status_code == 200
```

- [ ] **Step 2: Verify RED and implement the router plus unavailable fallback**

Run: `python -m pytest tests/integration/test_diagnostics_routes.py -v`  
Expected after implementation: PASS.

- [ ] **Step 3: Make `doctor.ps1` prefer P02 and fall back to `/api/environment` on 404**

Run: `python -m pytest tests/release/test_doctor_script.py -v`  
Expected: PASS while the script rejects non-loopback URLs.

### Task 5: One-click React diagnostic center

**Files:**

- Create: `apps/web/src/features/diagnostics/DiagnosticCenter.tsx`
- Create: `apps/web/src/features/diagnostics/DiagnosticCenter.test.tsx`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/app/router.tsx`
- Modify: `apps/web/src/features/projects/ProjectCenter.tsx`
- Modify: `apps/web/src/app/styles.css`

**Interfaces:**

- Consumes: the three P02 endpoints.
- Produces: route `/diagnostics` and project-center navigation entry.

- [ ] **Step 1: Write failing UI tests for run, grouped status and package export**

```tsx
expect(screen.getByRole('button', { name: '开始一键检查' })).toBeInTheDocument();
await user.click(screen.getByRole('button', { name: '开始一键检查' }));
expect(await screen.findByText('需要处理')).toBeInTheDocument();
```

- [ ] **Step 2: Verify RED, then implement the smallest page matching existing styles**

Run: `pnpm --filter @workbench/web test -- DiagnosticCenter.test.tsx`  
Expected after implementation: PASS.

- [ ] **Step 3: Run TypeScript checks and web build**

Run: `pnpm --filter @workbench/web typecheck && pnpm --filter @workbench/web build`  
Expected: both commands exit 0.

### Task 6: Release gate, regression and Windows handoff

**Files:**

- Create: `tests/acceptance/test_p02_gate.py`
- Create: `Run-P02-Health-Diagnostics.ps1`
- Create: `README-P02-Health-Diagnostics.txt`
- Modify: `packages/contracts/openapi.json`

**Interfaces:**

- Produces: cumulative P02 overlay ZIP and Windows verification command.

- [ ] **Step 1: Add a gate that verifies 13 checks, recognition rate, secret scan and non-blocking startup**

Run: `python -m pytest tests/acceptance/test_p02_gate.py -v`  
Expected: PASS.

- [ ] **Step 2: Regenerate the OpenAPI snapshot from `create_app().openapi()`**

Run: `python -m pytest tests/contracts/test_project_schema.py::test_openapi_snapshot_matches_application_contract -v`  
Expected: PASS.

- [ ] **Step 3: Run all Python tests except the source-archive test that requires a real Git worktree**

Run: `python -m pytest -q --ignore-glob='*source_update*'` with the exact Git-only node deselected.  
Expected: no P02 failures.

- [ ] **Step 4: Run Ruff, Python compile, frontend tests/typecheck/build and ZIP re-extraction verification**

Expected: all commands exit 0; no secret fixture appears in the package.

- [ ] **Step 5: Perform Windows verification**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File .\Run-P02-Health-Diagnostics.ps1`  
Expected: `P02_WINDOWS_ACCEPTANCE=PASS`; `F:\Video` file count and hashes remain unchanged except new diagnostic outputs under `F:\Video\diagnostics`.
