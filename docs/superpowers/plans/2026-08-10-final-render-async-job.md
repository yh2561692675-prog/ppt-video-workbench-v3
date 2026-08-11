# Final Render Async Job Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将最终渲染与制作包导出改造成可持久查询、暂停、继续、取消、恢复和重试的本地异步任务，同时保留逐页缓存和原有导出结果契约。

**Architecture:** 扩展现有 `workspace.db/jobs` 为 schema v2，由 FastAPI lifespan 管理一个全局并发为 1 的后台 Worker。API 只做预检、幂等入队、查询和控制；Worker 通过持久化执行上下文驱动现有 `VideoExportService`，React 使用条件轮询展示权威任务状态。

**Tech Stack:** Python 3.12, FastAPI 0.116+, Pydantic 2.11+, SQLAlchemy 2, SQLite WAL, pytest 8.4+, React 19, TypeScript 5.8, TanStack Query 5, Vitest 3, Remotion 4.0.340, FFmpeg/FFprobe.

## Global Constraints

- 创建渲染后在 500 ms 内返回 `202 Accepted` 和稳定 `job_id`；HTTP 请求不等待渲染完成。
- 最终渲染 Worker 的全局并发固定为 `1`。
- 任务活动状态只允许 `queued`、`running`、`pause_requested`、`paused`、`cancel_requested`。
- 终态只允许 `succeeded`、`failed`、`cancelled`。
- 相同项目、相同输入指纹只允许一个活动 `EXPORT_PACKAGE` 任务。
- 进度只允许单调增加；活动任务轮询间隔为 `1` 秒，paused 为 `5` 秒，终态停止轮询。
- 外部进程控制检查间隔为 `250 ms`；取消先等待 `3` 秒，再强制结束。
- Worker 正常关停最多等待 `10` 秒到安全点。
- 已验证页面缓存、上一份成功 MP4 和上一份成功制作包不得因暂停、取消、失败或输入变化被删除或覆盖。
- 不引入 Redis、Celery、RabbitMQ、新的运行时依赖、SSE 或 WebSocket。
- 原 `POST /api/projects/{project_id}/video/render` 保留一个小版本周期并返回新任务提交契约。
- 所有命令继续使用参数数组，禁止 shell 插值；API 与任务错误不得暴露 stderr 全文、凭据或绝对项目路径。

---

## File Responsibility Map

| 文件                                               | 单一职责                                    |
| -------------------------------------------------- | ------------------------------------------- |
| `apps/api/src/workbench/domain/enums.py`           | 作业状态枚举与现有任务类型                  |
| `apps/api/src/workbench/domain/models.py`          | 持久化 `JobRecord` 契约                     |
| `apps/api/src/workbench/storage/workspace_db.py`   | 当前 schema 表定义与数据库初始化            |
| `apps/api/src/workbench/storage/migrations.py`     | schema v1 → v2 的事务迁移                   |
| `apps/api/src/workbench/jobs/repository.py`        | 幂等入队、原子领取、状态转换与结果事务      |
| `apps/api/src/workbench/jobs/worker.py`            | 单消费者线程生命周期，不包含视频业务        |
| `apps/api/src/workbench/jobs/execution.py`         | 持久化检查点、进度、暂停和取消上下文        |
| `apps/api/src/workbench/video/process_runner.py`   | 可取消的 Remotion/FFmpeg/FFprobe 子进程执行 |
| `apps/api/src/workbench/video/errors.py`           | 最终渲染稳定错误类型与错误码                |
| `apps/api/src/workbench/video/render_job.py`       | 输入快照、指纹、提交服务与渲染任务 Handler  |
| `apps/api/src/workbench/video/render_service.py`   | 可报告页级进度的 Remotion 分页渲染          |
| `apps/api/src/workbench/video/package_service.py`  | 阶段化导出、暂存、校验和原子发布            |
| `apps/api/src/workbench/api/video.py`              | 渲染任务创建、查询、控制和兼容路由          |
| `apps/api/src/workbench/main.py`                   | 服务组装及 Worker lifespan 启停             |
| `apps/web/src/api/client.ts`                       | Render Job DTO 与请求方法                   |
| `apps/web/src/features/video/RenderJobPanel.tsx`   | 第 7 步任务交互与状态展示                   |
| `apps/web/src/features/workflow/WorkflowShell.tsx` | 将第 6/7 步接到统一任务入口                 |

---

### Task 1: JobStatus Contract and Workspace Database v2 Migration

**Files:**

- Modify: `apps/api/src/workbench/domain/enums.py:4-20`
- Modify: `apps/api/src/workbench/domain/models.py:112-125`
- Modify: `apps/api/src/workbench/storage/workspace_db.py:21-71`
- Create: `apps/api/src/workbench/storage/migrations.py`
- Create: `tests/unit/storage/test_workspace_migrations.py`
- Modify: `tests/integration/test_job_recovery.py`

**Interfaces:**

- Produces: `JobStatus` with `queued`, `running`, `pause_requested`, `paused`, `cancel_requested`, `succeeded`, `failed`, `cancelled`.
- Produces: schema version `2` and additive job columns from the design document.
- Consumes: existing schema v1 databases and existing `JobType.EXPORT_PACKAGE`.

- [ ] **Step 1: Write a failing v1-to-v2 migration test**

Create a schema v1 database manually, insert one `not_started` and one `completed` job, call `WorkspaceDatabase.initialize()`, then assert version 2, preserved IDs, converted statuses, nullable new fields, and the active-job partial unique index. Add a second fixture with duplicate active `export_package` rows and assert the newest remains active while older rows become `failed` with `render_job_superseded_during_migration`. Load a legacy `project.json` containing `not_started`/`completed` job entries and assert model validation maps them to `queued`/`succeeded` without changing project schema version 1.

```python
def test_initialize_migrates_v1_jobs_without_losing_records(tmp_path: Path) -> None:
    path = tmp_path / "workspace.db"
    create_schema_v1_fixture(path, statuses=("not_started", "completed"))

    database = WorkspaceDatabase(path)
    database.initialize()

    assert schema_version(database) == 2
    rows = job_rows(database)
    assert [row["status"] for row in rows] == ["queued", "succeeded"]
    assert all(row["revision"] == 1 for row in rows)
    assert "uq_jobs_active_project_type" in sqlite_index_names(database)
```

- [ ] **Step 2: Run the focused test and confirm the current initializer leaves schema version 1**

Run: `uv run pytest tests/unit/storage/test_workspace_migrations.py -q`

Expected: FAIL because schema version 2, new columns, and the partial index do not exist.

- [ ] **Step 3: Add the job lifecycle contract**

```python
class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

Change only `JobRecord.status` from `NodeStatus` to `JobStatus` and add typed fields: `input_fingerprint`, `idempotency_key`, `parent_job_id`, `payload`, `result`, `stage`, `message`, `error_code`, `revision`, `heartbeat_at`, `started_at`, `finished_at`. Add a `model_validator(mode="before")` that maps only legacy job values `not_started` → `queued` and `completed` → `succeeded`. Keep `NodeStatus` unchanged for project/page workflow state.

- [ ] **Step 4: Implement an explicit additive migration**

Expose this exact entry point:

```python
CURRENT_SCHEMA_VERSION = 2


def migrate_workspace_database(connection: Connection, source_version: int) -> None:
    if source_version == 1:
        migrate_v1_to_v2(connection)
        return
    if source_version != CURRENT_SCHEMA_VERSION:
        raise WorkspaceMigrationError(f"unsupported workspace schema version: {source_version}")
```

Use `ALTER TABLE ... ADD COLUMN` for additive fields and convert legacy statuses in one transaction. Before creating the index, rank duplicate active `export_package` rows by `updated_at DESC, created_at DESC, id DESC`; keep rank 1 active and mark later ranks `failed` with `render_job_superseded_during_migration`. Create a partial unique index whose predicate includes `job_type = 'export_package'`, then update `schema_meta.version` last. Do not drop or recreate `jobs`; do not constrain multiple `render_page` rows for one project.

- [ ] **Step 5: Update existing recovery tests to use `JobStatus`**

Replace job-only assertions such as `NodeStatus.COMPLETED` with `JobStatus.SUCCEEDED`; retain `NodeStatus` for project manifest assertions.

- [ ] **Step 6: Run storage and recovery tests**

Run: `uv run pytest tests/unit/storage/test_workspace_migrations.py tests/integration/test_job_recovery.py -q`

Expected: PASS, including migration preservation and existing retry/recovery coverage.

- [ ] **Step 7: Commit the database contract**

```powershell
git add apps/api/src/workbench/domain/enums.py apps/api/src/workbench/domain/models.py apps/api/src/workbench/storage/workspace_db.py apps/api/src/workbench/storage/migrations.py tests/unit/storage/test_workspace_migrations.py tests/integration/test_job_recovery.py
git commit -m "feat: add durable render job schema"
```

### Task 2: Atomic Job Repository and State Transitions

**Files:**

- Modify: `apps/api/src/workbench/jobs/repository.py`
- Create: `tests/unit/jobs/test_repository.py`
- Modify: `tests/integration/test_job_recovery.py`

**Interfaces:**

- Produces: `enqueue_or_get`, `claim_next`, `request_pause`, `resume`, `request_cancel`, `update_progress`, `heartbeat`, `succeed`, and `fail`.
- Produces: `EnqueueResult(record: JobRecord, created: bool)`.
- Consumes: schema v2 `jobs` table and `JobSpec`.

- [ ] **Step 1: Write failing repository transition tests**

Cover: same idempotency key returns one active job; one active export per project; `claim_next()` claims oldest queued job once; progress cannot decrease; pause/cancel precedence; terminal result transaction; retry uses `parent_job_id` and a new job ID.

```python
def test_claim_next_is_single_winner(repository: JobRepository, project_id: UUID) -> None:
    submitted = repository.enqueue_or_get(export_spec(project_id, "fingerprint-a"))
    first = repository.claim_next(JobType.EXPORT_PACKAGE)
    second = repository.claim_next(JobType.EXPORT_PACKAGE)
    assert first is not None and first.id == submitted.record.id
    assert first.status is JobStatus.RUNNING
    assert second is None
```

- [ ] **Step 2: Run the focused tests and confirm missing repository methods**

Run: `uv run pytest tests/unit/jobs/test_repository.py -q`

Expected: FAIL at import or attribute lookup for the new API.

- [ ] **Step 3: Freeze repository method signatures**

```python
@dataclass(frozen=True)
class JobSpec:
    project_id: UUID
    job_type: JobType
    cache_key: str
    input_fingerprint: str
    idempotency_key: str
    payload: dict[str, object]
    page_id: UUID | None = None
    parent_job_id: UUID | None = None
    paid: bool = False
    max_attempts: int | None = None


@dataclass(frozen=True)
class EnqueueResult:
    record: JobRecord
    created: bool
```

- [ ] **Step 4: Implement idempotent enqueue and atomic claim**

Use a single transaction to query matching active/succeeded work and insert only when needed. Implement `claim_next()` as one conditional `UPDATE ... WHERE id=(SELECT ... LIMIT 1) AND status='queued' RETURNING ...`; set `started_at`, `heartbeat_at`, `stage='validating_input'`, and increment `revision`.

- [ ] **Step 5: Implement an explicit transition table**

```python
ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.PAUSED, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.PAUSE_REQUESTED,
            JobStatus.CANCEL_REQUESTED,
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
        }
    ),
    JobStatus.PAUSE_REQUESTED: frozenset({JobStatus.PAUSED, JobStatus.CANCEL_REQUESTED}),
    JobStatus.PAUSED: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
    JobStatus.CANCEL_REQUESTED: frozenset({JobStatus.CANCELLED, JobStatus.FAILED}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}
```

Every mutation must condition on the expected current status and increment `revision`; return `JobTransitionConflict` when another request won the race.

- [ ] **Step 6: Implement progress, heartbeat and terminal writes**

`update_progress()` rejects lower progress, truncates user-visible message to 500 characters, and updates heartbeat. `succeed()` writes `result_json`, progress `1.0`, stage `completed`, status `succeeded`, and `finished_at` in one transaction. `fail()` writes only stable error code and redacted summary.

- [ ] **Step 7: Run repository and recovery tests**

Run: `uv run pytest tests/unit/jobs/test_repository.py tests/integration/test_job_recovery.py -q`

Expected: PASS with no duplicate active job and no non-monotonic progress.

- [ ] **Step 8: Commit repository behavior**

```powershell
git add apps/api/src/workbench/jobs/repository.py tests/unit/jobs/test_repository.py tests/integration/test_job_recovery.py
git commit -m "feat: add atomic render job repository"
```

### Task 3: Single-Consumer Worker Lifecycle

**Files:**

- Create: `apps/api/src/workbench/jobs/worker.py`
- Create: `tests/unit/jobs/test_worker.py`

**Interfaces:**

- Produces: `RenderJobWorker.start()`, `wake()`, `stop(timeout=10.0)`, `is_alive`.
- Consumes: `JobRepository.claim_next(JobType.EXPORT_PACKAGE)` and `Callable[[JobRecord], None]`.

- [ ] **Step 1: Write failing worker tests**

Test wake-after-submit, FIFO execution, no concurrent handlers, handler exception isolation, disabled worker, and graceful shutdown requesting pause for the active job.

```python
def test_worker_never_runs_two_handlers_concurrently(repository: JobRepository) -> None:
    tracker = ConcurrencyTracker()
    worker = RenderJobWorker(repository, tracker.handle, poll_interval=0.01)
    enqueue_two_projects(repository)
    worker.start()
    worker.wake()
    tracker.wait_for_two()
    worker.stop()
    assert tracker.maximum == 1
```

- [ ] **Step 2: Run the test and confirm `worker.py` is missing**

Run: `uv run pytest tests/unit/jobs/test_worker.py -q`

Expected: FAIL on module import.

- [ ] **Step 3: Implement the worker shell**

```python
class RenderJobWorker:
    def __init__(
        self,
        repository: JobRepository,
        handler: Callable[[JobRecord], None],
        *,
        enabled: bool = True,
        poll_interval: float = 0.5,
    ) -> None: ...

    def start(self) -> None: ...
    def wake(self) -> None: ...
    def stop(self, timeout: float = 10.0) -> None: ...
```

Use one `Thread`, `_stop_event`, `_wake_event`, and `_active_job_id` guarded by a lock. Do not use `ThreadPoolExecutor`; the one-thread shape makes concurrency invariant explicit.

- [ ] **Step 4: Isolate task failures from the loop**

The Worker catches ordinary exceptions, calls `repository.fail(job_id, "video_export_rejected", safe_summary(error))` only if the handler did not already reach a terminal state, clears `_active_job_id`, and immediately attempts the next queued job.

- [ ] **Step 5: Implement shutdown semantics**

`stop()` stops new claims, requests pause for an active running job, wakes the loop, joins for the supplied timeout, and leaves interrupted state recoverable when the timeout expires.

- [ ] **Step 6: Run the worker tests**

Run: `uv run pytest tests/unit/jobs/test_worker.py -q`

Expected: PASS; maximum observed handler concurrency is exactly 1.

- [ ] **Step 7: Commit Worker lifecycle**

```powershell
git add apps/api/src/workbench/jobs/worker.py tests/unit/jobs/test_worker.py
git commit -m "feat: add single render job worker"
```

### Task 4: Cancellable External Process Runner

**Files:**

- Create: `apps/api/src/workbench/video/process_runner.py`
- Modify: `apps/api/src/workbench/video/render_service.py:60-120`
- Modify: `apps/api/src/workbench/video/package_service.py:290-339`
- Create: `tests/unit/video/test_process_runner.py`
- Modify: `tests/unit/video/test_render_service.py`
- Modify: `tests/unit/video/test_package_service.py`

**Interfaces:**

- Produces: `CancellableProcessRunner.run(command, cwd, control) -> ProcessResult`.
- Consumes: a `ProcessControl` with `cancel_requested` and `heartbeat()`.
- Replaces: direct `subprocess.run()` in Remotion, FFmpeg and FFprobe paths.

- [ ] **Step 1: Write failing process-control tests**

Use an injected fake `Popen` to cover success, non-zero exit, cancel → terminate, terminate timeout → kill, heartbeat every 5 seconds, and redacted error output.

```python
def test_cancel_terminates_then_kills_after_three_seconds() -> None:
    process = FakeProcess(terminate_never_exits=True)
    runner = CancellableProcessRunner(popen=lambda *args, **kwargs: process, clock=FakeClock())
    with pytest.raises(ProcessCancelled):
        runner.run(["ffmpeg", "-i", "input"], Path.cwd(), CancelImmediately())
    assert process.terminated is True
    assert process.killed is True
    assert process.wait_timeouts[-1] == 3.0
```

- [ ] **Step 2: Run focused tests and verify current `subprocess.run()` cannot cancel**

Run: `uv run pytest tests/unit/video/test_process_runner.py tests/unit/video/test_render_service.py tests/unit/video/test_package_service.py -q`

Expected: FAIL because `CancellableProcessRunner` is missing.

- [ ] **Step 3: Implement the shared process contract**

```python
class ProcessControl(Protocol):
    @property
    def cancel_requested(self) -> bool: ...
    def heartbeat(self) -> None: ...


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
```

Start with `stdin=DEVNULL`, `stdout=PIPE`, `stderr=PIPE`, `text=True`, `shell=False`. Poll with `communicate(timeout=0.25)`. On cancellation call `terminate()`, wait 3 seconds, then `kill()` and always reap the process.

- [ ] **Step 4: Route Remotion and FFmpeg through the runner**

Inject the runner into `RemotionPageRenderer` and `VideoExportService`. Preserve command argument arrays and existing user-facing error classes; map `ProcessCancelled` separately so it is never converted to `video_export_rejected`.

- [ ] **Step 5: Bound captured output and redact diagnostics**

Retain at most the final 64 KiB of stdout/stderr, pass diagnostic text through the existing redaction helper, and expose only exit code plus stable error code to the job record.

- [ ] **Step 6: Run video unit tests**

Run: `uv run pytest tests/unit/video/test_process_runner.py tests/unit/video/test_render_service.py tests/unit/video/test_package_service.py -q`

Expected: PASS with unchanged Remotion/FFmpeg argument assertions.

- [ ] **Step 7: Commit process control**

```powershell
git add apps/api/src/workbench/video/process_runner.py apps/api/src/workbench/video/render_service.py apps/api/src/workbench/video/package_service.py tests/unit/video/test_process_runner.py tests/unit/video/test_render_service.py tests/unit/video/test_package_service.py
git commit -m "feat: make render subprocesses cancellable"
```

### Task 5: Persistent Render Execution Context and Checkpoints

**Files:**

- Create: `apps/api/src/workbench/jobs/execution.py`
- Modify: `apps/api/src/workbench/jobs/checkpoint.py`
- Modify: `apps/api/src/workbench/video/render_service.py:123-217`
- Create: `tests/unit/jobs/test_execution.py`
- Modify: `tests/unit/jobs/test_checkpoint.py`
- Modify: `tests/unit/video/test_render_service.py`

**Interfaces:**

- Produces: `RenderExecutionContext`, `InlineRenderExecutionContext`, `PersistentRenderExecutionContext`.
- Produces: `RenderPauseRequested` and `RenderCancelled` control exceptions.
- Consumes: `JobRepository`, `CheckpointStore`, and page artifacts.

- [ ] **Step 1: Write failing execution-context tests**

Cover monotonic progress, checkpoint artifact hashing, pause at safe point, cancel precedence, heartbeat delegation, invalid checkpoint fallback, and page progress/cached-page counters.

```python
def test_pause_is_observed_only_at_safe_point(context: PersistentRenderExecutionContext) -> None:
    context.repository.request_pause(context.job_id)
    with pytest.raises(RenderPauseRequested):
        context.pause_if_requested()
    assert context.repository.get(context.job_id).status is JobStatus.PAUSED
```

- [ ] **Step 2: Run the focused tests and confirm the execution module is missing**

Run: `uv run pytest tests/unit/jobs/test_execution.py tests/unit/jobs/test_checkpoint.py -q`

Expected: FAIL on import.

- [ ] **Step 3: Define the context protocol**

```python
class RenderExecutionContext(Protocol):
    job_id: UUID | None
    input_fingerprint: str | None

    def checkpoint(
        self,
        *,
        stage: str,
        progress: float,
        message: str,
        artifacts: Iterable[Path] = (),
        payload: Mapping[str, object] | None = None,
    ) -> None: ...
    def raise_if_cancelled(self) -> None: ...
    def pause_if_requested(self) -> None: ...
    def heartbeat(self) -> None: ...
```

- [ ] **Step 4: Implement persistent control checks**

Read the current job status from SQLite on each safe-point check. `cancel_requested` raises `RenderCancelled`; `pause_requested` first writes a verified checkpoint, transitions to `paused`, then raises `RenderPauseRequested`. Never treat either as an execution failure.

- [ ] **Step 5: Add page-level callbacks to `render_pages()`**

Before each page call `raise_if_cancelled()`; after a cached or newly published page write a `rendering_pages` checkpoint and call `pause_if_requested()`. Progress formula is `0.05 + completed_pages / total_pages * 0.60`.

- [ ] **Step 6: Preserve synchronous compatibility**

When `VideoExportService.export()` or `VideoRenderService.render_pages()` receives no context, instantiate `InlineRenderExecutionContext`; it performs no persistence or control and keeps direct unit tests synchronous.

- [ ] **Step 7: Run execution, checkpoint and render tests**

Run: `uv run pytest tests/unit/jobs/test_execution.py tests/unit/jobs/test_checkpoint.py tests/unit/video/test_render_service.py -q`

Expected: PASS, including cache-hit progress and pause after the current page.

- [ ] **Step 8: Commit execution context**

```powershell
git add apps/api/src/workbench/jobs/execution.py apps/api/src/workbench/jobs/checkpoint.py apps/api/src/workbench/video/render_service.py tests/unit/jobs/test_execution.py tests/unit/jobs/test_checkpoint.py tests/unit/video/test_render_service.py
git commit -m "feat: checkpoint render job progress"
```

### Task 6: Stage the Export Pipeline and Publish Atomically

**Files:**

- Create: `apps/api/src/workbench/video/errors.py`
- Modify: `apps/api/src/workbench/video/package_service.py:68-347`
- Modify: `apps/api/src/workbench/video/render_service.py`
- Modify: `apps/api/src/workbench/cache/cleanup.py`
- Modify: `tests/unit/video/test_package_service.py`
- Modify: `tests/unit/cache/test_cleanup.py`
- Modify: `tests/integration/test_video_render_routes.py`

**Interfaces:**

- Produces: `VideoExportService.export(project_id, context=...) -> VideoExportResult`.
- Produces: job-scoped staging root `08_输出/.render-jobs/{job_id}` and atomically written `08_输出/latest.json`.
- Consumes: `RenderExecutionContext`, existing page cache, existing package manifest rules.

- [ ] **Step 1: Write failing staging and consistency tests**

Test stage progress, pause between segments, cancel cleanup, unchanged stable output on failure, input changed before publish, successful `latest.json` switch, and cleanup protection for active job paths.

```python
def test_failed_new_export_keeps_previous_successful_output(ready_export_service) -> None:
    previous = ready_export_service.export(PROJECT_ID)
    previous_bytes = stable_mp4().read_bytes()
    inject_failure_at("packaging")
    with pytest.raises(PackageError):
        ready_export_service.export(PROJECT_ID, context=persistent_context())
    assert stable_mp4().read_bytes() == previous_bytes
    assert previous.package_relative_path == read_latest_pointer()["package_relative_path"]
```

- [ ] **Step 2: Run focused tests and verify current code writes stable paths too early**

Run: `uv run pytest tests/unit/video/test_package_service.py tests/unit/cache/test_cleanup.py -q`

Expected: FAIL because job-scoped staging and latest pointer do not exist.

- [ ] **Step 3: Split `_export()` into explicit private stages**

Define stable `RenderJobFailure` subclasses in `video/errors.py`: `RenderInputStale`, `RenderInputChanged`, `RendererRuntimeUnavailable`, `RenderPageFailed`, `FfmpegMuxFailed`, `FfmpegConcatFailed`, `MediaValidationFailed`, `PackageValidationFailed`, and `RenderDiskFull`. Each subclass owns the exact code used in Task 7. Implement focused export methods with these return types:

```python
def _render_pages(...) -> list[RenderedPage]: ...
def _mux_pages(...) -> list[Path]: ...
def _concatenate(...) -> tuple[Path, dict[str, object]]: ...
def _build_package(...) -> tuple[Path, PackageManifest]: ...
def _publish(...) -> VideoExportResult: ...
```

Each loop checkpoint uses the ranges from the design: rendering `0.05–0.65`, muxing `0.65–0.85`, concatenating `0.85–0.91`, packaging `0.91–0.98`, publishing `0.98–0.99`.

- [ ] **Step 4: Implement job-scoped staging and stable publish**

Write all new output under `.render-jobs/{run_id}`, where `run_id = context.job_id or uuid4()` keeps direct synchronous calls compatible. Validate MP4 and every package manifest entry before `os.replace()` publishes stable files. Atomically replace `latest.json` last; do not delete the previous package until pointer replacement succeeds.

- [ ] **Step 5: Add start and pre-publish fingerprint checks**

Inject `Callable[[UUID], str]` into the export service. Compare with `context.input_fingerprint` before rendering and immediately before `_publish()`. Raise `RenderInputStale` or `RenderInputChanged` with stable codes; retain verified page cache but clean unverified staging output.

- [ ] **Step 6: Protect active job paths from cleanup**

Have `CleanupService` query active jobs and add snapshot, checkpoint, staging, page-cache, and previous stable output paths to `protected_paths`.

- [ ] **Step 7: Run package, cleanup and original route regression tests**

Run: `uv run pytest tests/unit/video/test_package_service.py tests/unit/cache/test_cleanup.py tests/integration/test_video_render_routes.py -q`

Expected: PASS; direct `export()` remains supported through inline context.

- [ ] **Step 8: Commit staged export**

```powershell
git add apps/api/src/workbench/video/errors.py apps/api/src/workbench/video/package_service.py apps/api/src/workbench/video/render_service.py apps/api/src/workbench/cache/cleanup.py tests/unit/video/test_package_service.py tests/unit/cache/test_cleanup.py tests/integration/test_video_render_routes.py
git commit -m "feat: stage and atomically publish video exports"
```

### Task 7: Render Job Submission Service and Handler

**Files:**

- Create: `apps/api/src/workbench/video/render_job.py`
- Create: `tests/unit/video/test_render_job.py`
- Create: `tests/integration/test_async_render_worker.py`

**Interfaces:**

- Produces: `RenderJobService.submit(project_id) -> RenderJobSubmission`.
- Produces: `RenderJobService.retry(project_id, failed_job_id) -> RenderJobSubmission`.
- Produces: `RenderJobService.act(project_id, job_id, action) -> RenderJobSubmission`.
- Produces: `RenderJobHandler.__call__(record: JobRecord) -> None`.
- Consumes: preview/preflight, `VideoExportService`, `JobRepository`, `PersistentRenderExecutionContext`.

- [ ] **Step 1: Write failing submission and handler tests**

Cover preflight rejection without a job, canonical fingerprint, input snapshot path safety, active dedupe, successful-result reuse only when artifacts validate, new run after failure, result persistence, classified failures, pause and cancellation.

```python
def test_submit_same_input_twice_returns_one_active_job(service: RenderJobService) -> None:
    first = service.submit(PROJECT_ID)
    second = service.submit(PROJECT_ID)
    assert first.created is True
    assert second.created is False
    assert second.job.id == first.job.id
```

- [ ] **Step 2: Run tests and confirm `render_job.py` is missing**

Run: `uv run pytest tests/unit/video/test_render_job.py tests/integration/test_async_render_worker.py -q`

Expected: FAIL on import.

- [ ] **Step 3: Define public DTOs**

```python
class RenderJobResultView(BaseModel):
    job: JobRecord
    created: bool


RenderJobSubmission = RenderJobResultView
```

Keep JSON names identical to the design API. `JobRecord.result` validates as `VideoExportResult` at the API boundary.

- [ ] **Step 4: Implement canonical input fingerprinting**

Serialize `ProjectVideoProps`, preflight `input_fingerprint`, and renderer runtime version with `sort_keys=True`, compact separators and UTF-8; hash using SHA-256. Store only project-relative paths. Atomically write `09_日志/render-jobs/{job_id}/input.json` before waking the Worker.

- [ ] **Step 5: Implement submit, retry and result reuse**

`submit()` runs the existing render gate and preview preflight, then calls `enqueue_or_get()`. If a matching succeeded job exists, verify MP4, package directory and package manifest hashes before reuse. `retry()` permits only `failed`/`cancelled`, sets `parent_job_id`, and always creates a new run. `act()` verifies project ownership, applies pause/resume/cancel/retry through the repository, writes the matching audit event, and wakes the Worker only for queued work.

- [ ] **Step 6: Implement the Handler outcome mapping**

Construct `PersistentRenderExecutionContext`, append the matching project audit event at each accepted control or terminal transition, call `export()`, then `repository.succeed()`. Map `RenderPauseRequested` to no terminal write, `RenderCancelled` to `cancelled`, known exceptions through the exact map below, and unknown exceptions to `video_export_rejected` after redaction.

```python
ERROR_CODE_BY_EXCEPTION = {
    RenderInputStale: "render_input_stale",
    RenderInputChanged: "render_input_changed",
    RendererRuntimeUnavailable: "renderer_runtime_unavailable",
    RenderPageFailed: "render_page_failed",
    FfmpegMuxFailed: "ffmpeg_mux_failed",
    FfmpegConcatFailed: "ffmpeg_concat_failed",
    MediaValidationFailed: "media_validation_failed",
    PackageValidationFailed: "package_validation_failed",
    RenderDiskFull: "render_disk_full",
}
```

Persist these exact audit action names: `video_render_job_created`, `video_render_job_started`, `video_render_job_pause_requested`, `video_render_job_paused`, `video_render_job_resumed`, `video_render_job_cancel_requested`, `video_render_job_cancelled`, `video_render_job_failed`, `video_render_job_succeeded`.

- [ ] **Step 7: Run unit and worker integration tests**

Run: `uv run pytest tests/unit/video/test_render_job.py tests/integration/test_async_render_worker.py -q`

Expected: PASS from queued through succeeded and for every control outcome.

- [ ] **Step 8: Commit render job orchestration**

```powershell
git add apps/api/src/workbench/video/render_job.py tests/unit/video/test_render_job.py tests/integration/test_async_render_worker.py
git commit -m "feat: orchestrate final render jobs"
```

### Task 8: FastAPI Job Endpoints and Lifespan Wiring

**Files:**

- Modify: `apps/api/src/workbench/api/video.py`
- Modify: `apps/api/src/workbench/main.py:94-250`
- Modify: `tests/integration/test_video_render_routes.py`
- Create: `tests/integration/test_video_render_job_routes.py`
- Modify: `packages/contracts/openapi.json`
- Modify: `tests/contracts/test_project_schema.py`

**Interfaces:**

- Produces: create/current/get/action endpoints from the design document.
- Produces: weak ETag `W/"job-{job_id}-{revision}"` and `304 Not Modified`.
- Consumes: `RenderJobService`, `RenderJobWorker`, existing envelope/error middleware.

- [ ] **Step 1: Write failing API contract tests**

Cover 202 new, 200 reused, 409 preflight block, current lookup, ownership 404, ETag 304, pause/resume/cancel/retry, illegal transition 409, and deprecated old route headers.

```python
def test_create_render_job_returns_before_handler_finishes(client, blocking_handler) -> None:
    response = client.post(f"/api/projects/{PROJECT_ID}/video/render-jobs")
    assert response.status_code == 202
    assert response.json()["data"]["job"]["status"] in {"queued", "running"}
    assert blocking_handler.finished is False
```

- [ ] **Step 2: Run route tests and confirm endpoints return 404**

Run: `uv run pytest tests/integration/test_video_render_job_routes.py -q`

Expected: FAIL because `/render-jobs` routes are absent.

- [ ] **Step 3: Add request and response models**

```python
class RenderJobActionRequest(BaseModel):
    action: Literal["pause", "resume", "cancel", "retry"]
```

Return the existing envelope shape. Map missing project/job to 404, preflight to 409, transition conflict to 409, unavailable worker to 503, and never expose internal exception strings.

- [ ] **Step 4: Implement the route set and ETag**

Add exact paths:

```text
POST /api/projects/{project_id}/video/render-jobs
GET  /api/projects/{project_id}/video/render-jobs/current
GET  /api/projects/{project_id}/video/render-jobs/{job_id}
POST /api/projects/{project_id}/video/render-jobs/{job_id}/actions
```

Set status code dynamically from `created`. For GET, compare `If-None-Match` and return 304 without a body when revision matches.

- [ ] **Step 5: Start and stop Worker in lifespan**

Build repository → export service → job handler → worker in `create_app()`. Store services on `app.state` for tests. In lifespan, `worker.start()` before `yield`; after `yield`, call `worker.stop(timeout=10.0)` before closing `ProjectService`.

- [ ] **Step 6: Add feature-flag behavior and old-route compatibility**

Read `WORKBENCH_ASYNC_RENDER_ENABLED`, default `true`. When false, Worker does not claim jobs. The old `/video/render` route calls `RenderJobService.submit()` and sets `Deprecation: true` plus a successor `Link` header.

- [ ] **Step 7: Export and validate OpenAPI**

Run: `uv run python scripts/export_contracts.py`

Expected: `packages/contracts/openapi.json` includes all four routes and the new DTO schemas.

- [ ] **Step 8: Run API, contract and original render regressions**

Run: `uv run pytest tests/integration/test_video_render_job_routes.py tests/integration/test_video_render_routes.py tests/contracts -q`

Expected: PASS; old route now returns job submission rather than blocking for `VideoExportResult`.

- [ ] **Step 9: Commit API wiring**

```powershell
git add apps/api/src/workbench/api/video.py apps/api/src/workbench/main.py tests/integration/test_video_render_job_routes.py tests/integration/test_video_render_routes.py packages/contracts/openapi.json tests/contracts/test_project_schema.py
git commit -m "feat: expose asynchronous render job API"
```

### Task 9: React Render Job Client and Panel

**Files:**

- Modify: `apps/web/src/api/client.ts:1-166,498-573`
- Modify: `apps/web/src/api/client.contract.test.ts`
- Create: `apps/web/src/features/video/RenderJobPanel.tsx`
- Create: `apps/web/src/features/video/RenderJobPanel.test.tsx`
- Modify: `apps/web/src/features/video/PreviewWorkspace.tsx:16-76`
- Modify: `apps/web/src/features/video/PreviewWorkspace.test.tsx`
- Modify: `apps/web/src/features/workflow/WorkflowShell.tsx:29-277`
- Modify: `apps/web/src/features/workflow/WorkflowShell.test.tsx`
- Modify: `apps/web/src/app/styles.css`

**Interfaces:**

- Produces: `RenderJob`, `RenderJobSubmission`, and `RenderJobAction` TypeScript types.
- Produces: `api.createRenderJob`, `getCurrentRenderJob`, `getRenderJob`, `actOnRenderJob`.
- Produces: `RenderJobPanel({projectId, enabled})`.

- [ ] **Step 1: Write failing API client tests**

Assert exact methods, paths, POST bodies, nullable current response, and preservation of structured `ApiRequestError` for 409 actions.

```typescript
it('sends a cancel action to the project-owned render job endpoint', async () => {
  mockJson({ data: cancelledJob, error: null, request_id: 'request-1' });
  await api.actOnRenderJob('project-1', 'job-1', 'cancel');
  expect(fetch).toHaveBeenCalledWith(
    '/api/projects/project-1/video/render-jobs/job-1/actions',
    expect.objectContaining({ method: 'POST', body: JSON.stringify({ action: 'cancel' }) }),
  );
});
```

- [ ] **Step 2: Define TypeScript contracts and client methods**

Use a literal union matching all eight backend statuses. `result` is `VideoExportResult | null`; all timestamps are `string | null`; progress is a number in `[0,1]`.

- [ ] **Step 3: Write failing panel state-matrix tests**

Cover no job, queued, running, pause requested, paused, cancel requested, failed, cancelled and succeeded. Assert button availability, stage copy, progress, cached page count, result paths, cancel confirmation, retry, and polling intervals.

- [ ] **Step 4: Implement query and mutation behavior**

```typescript
const jobQuery = useQuery({
  queryKey: ['render-job-current', projectId],
  queryFn: () => api.getCurrentRenderJob(projectId),
  enabled,
  refetchInterval: (query) => renderJobPollInterval(query.state.data),
  refetchOnWindowFocus: true,
});
```

Return `1000` for queued/running/pause_requested/cancel_requested, `5000` for paused, and `false` for null or terminal jobs. Mutations update query cache immediately and then invalidate.

- [ ] **Step 5: Implement accessible panel controls**

Use a native `<progress max={1} value={job.progress}>`; stage and message use `aria-live="polite"`. Cancel opens a confirmation block that states verified page cache is retained. Do not use browser alerts for ordinary errors.

- [ ] **Step 6: Replace the synchronous Workflow mutation**

Remove `videoRenderMutation`. The Step 7 area renders `RenderJobPanel`. Step 6 “开始渲染与导出” creates/reuses a job and navigates to Step 7; it does not remain pending for the job lifetime.

- [ ] **Step 7: Add focused styles without changing the visual system**

Reuse existing panel, status, muted, success, error, primary and secondary classes. Add only `.render-job-progress`, `.render-job-meta`, `.render-job-actions`, and `.render-job-confirmation` layout rules.

- [ ] **Step 8: Run Web tests and typecheck**

Run: `pnpm --filter @workbench/web test -- src/api/client.contract.test.ts src/features/video/RenderJobPanel.test.tsx src/features/video/PreviewWorkspace.test.tsx src/features/workflow/WorkflowShell.test.tsx`

Run: `pnpm --filter @workbench/web typecheck`

Expected: PASS; no component depends on a mutation staying pending during render.

- [ ] **Step 9: Commit the Web experience**

```powershell
git add apps/web/src/api/client.ts apps/web/src/api/client.contract.test.ts apps/web/src/features/video/RenderJobPanel.tsx apps/web/src/features/video/RenderJobPanel.test.tsx apps/web/src/features/video/PreviewWorkspace.tsx apps/web/src/features/video/PreviewWorkspace.test.tsx apps/web/src/features/workflow/WorkflowShell.tsx apps/web/src/features/workflow/WorkflowShell.test.tsx apps/web/src/app/styles.css
git commit -m "feat: add final render job panel"
```

### Task 10: Recovery, Diagnostics, Documentation, and End-to-End Acceptance

**Files:**

- Modify: `apps/api/src/workbench/services/project_service.py:44-60`
- Modify: `apps/api/src/workbench/diagnostics/probes.py`
- Modify: `apps/api/src/workbench/diagnostics/models.py`
- Modify: `tests/integration/test_job_recovery.py`
- Create: `tests/integration/test_async_render_recovery.py`
- Modify: `tests/integration/test_diagnostics_routes.py`
- Modify: `tests/e2e/project-lifecycle.spec.ts`
- Modify: `docs/user-guide.md`
- Modify: `docs/troubleshooting.md`
- Modify: `CHANGELOG.md`

**Interfaces:**

- Produces: restart conversion of interrupted active states to `paused` with `render_worker_interrupted`.
- Produces: diagnostics for worker alive, queue length, stale heartbeat and recent failure codes.
- Consumes: completed API and UI from Tasks 1–9.

- [ ] **Step 1: Write failing restart-recovery tests**

Seed `running`, `pause_requested` and `cancel_requested` jobs, then restart `ProjectService`. Assert `running` and `pause_requested` become `paused` and retain progress/checkpoints without auto-resume. Assert `cancel_requested` cleans its registered temporary paths and becomes `cancelled`; inject a cleanup failure and assert `failed/render_cancel_cleanup_failed`. Continue one paused task and assert already rendered pages are cache hits.

- [ ] **Step 2: Implement startup recovery without auto-run**

Replace the broad legacy recovery with `recover_interrupted_jobs(error_code="render_worker_interrupted")` for `running` and `pause_requested`. Preserve `progress`, `stage`, `attempts`, input fingerprint and payload; update message, heartbeat and revision. Process `cancel_requested` separately through verified temporary-path cleanup and never requeue it.

- [ ] **Step 3: Add Worker diagnostics tests and probes**

Expose only counts and stable codes:

```json
{
  "worker_alive": true,
  "queued_jobs": 2,
  "stale_running_jobs": 0,
  "recent_failure_codes": { "render_page_failed": 1 }
}
```

Do not read media files or return project names, job messages, absolute paths or stderr.

- [ ] **Step 4: Add an E2E async lifecycle scenario**

Mock a slow two-page renderer, start a task, assert the UI stays navigable, refresh, recover the same `job_id`, pause, resume, finish, and display both output paths. Add a separate cancel scenario that preserves the last successful output.

- [ ] **Step 5: Update user and troubleshooting documentation**

Document state meanings, safe pause/cancel semantics, resume after app restart, stale-input behavior, output preservation, error-code actions, the compatibility route, and `WORKBENCH_ASYNC_RENDER_ENABLED` emergency switch.

- [ ] **Step 6: Run focused recovery, diagnostics and E2E tests**

Run: `uv run pytest tests/integration/test_job_recovery.py tests/integration/test_async_render_recovery.py tests/integration/test_diagnostics_routes.py -q`

Run: `pnpm e2e -- tests/e2e/project-lifecycle.spec.ts`

Expected: PASS with the same `job_id` recovered after UI reload and paused state after backend restart.

- [ ] **Step 7: Run complete automated verification**

Run: `uv run pytest -q`

Run: `uv run ruff check .`

Run: `uv run mypy apps/api/src/workbench`

Run: `pnpm lint`

Run: `pnpm typecheck`

Run: `pnpm test`

Run: `pnpm build`

Expected: all commands exit 0. If this reconstructed workspace still lacks Git metadata, only Git-dependent release tests may be reported separately; no product test may be skipped.

- [ ] **Step 8: Perform Windows real-process acceptance**

Run an 8-page and a 50-page project with packaged Node, Chromium, Remotion, FFmpeg and FFprobe. Record create latency, 1-second progress visibility, memory/CPU peak, refresh recovery, pause/resume, cancel latency, app restart recovery, orphan-process check, H.264/AAC metadata, duration tolerance, package contents and SHA-256 verification.

- [ ] **Step 9: Verify rollback readiness**

Copy `workspace.db`, start once to migrate to v2, confirm the backup exists, set `WORKBENCH_ASYNC_RENDER_ENABLED=false`, verify Worker does not claim queued tasks and existing tasks remain queryable/cancellable. Do not run schema downgrade SQL.

- [ ] **Step 10: Commit acceptance and documentation**

```powershell
git add apps/api/src/workbench/services/project_service.py apps/api/src/workbench/diagnostics/probes.py apps/api/src/workbench/diagnostics/models.py tests/integration/test_job_recovery.py tests/integration/test_async_render_recovery.py tests/integration/test_diagnostics_routes.py tests/e2e/project-lifecycle.spec.ts docs/user-guide.md docs/troubleshooting.md CHANGELOG.md
git commit -m "docs: complete async render recovery acceptance"
```

---

## Final Acceptance Checklist

- [ ] `POST /video/render-jobs` returns before the render handler finishes and produces a stable `job_id`.
- [ ] Repeated submit with identical input returns one active job.
- [ ] Exactly one final-render handler runs globally.
- [ ] Query revision and ETag suppress unchanged payloads.
- [ ] Active status updates appear in the UI within 1 second.
- [ ] Pausing finishes the current atomic stage and starts no next stage.
- [ ] Cancelling terminates/forces cleanup of external processes without orphaning them.
- [ ] Restart converts interrupted work to paused and resume reuses verified page cache.
- [ ] Input change prevents stale output publication.
- [ ] Failure, cancellation and package validation errors preserve the previous successful output.
- [ ] Successful API result, project manifest, latest pointer and package checksums agree.
- [ ] No stderr, secrets or absolute project paths appear in the API response or job record.
- [ ] No new runtime dependency is present in `uv.lock` or `pnpm-lock.yaml`.
- [ ] Python, Web, contract, integration, E2E and Windows real-process checks pass.
