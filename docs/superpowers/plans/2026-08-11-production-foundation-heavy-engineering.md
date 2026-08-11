# PPT Video Workbench 生产级共享底座逐项实施计划

> 本计划按依赖顺序实施生产级共享底座。每个 Phase 必须通过对应 Gate 并形成 stop point，才能进入下一阶段。七项 P1 产品功能可以消费本计划产物，但不得绕过这些共享契约各自建立任务、缓存、迁移或渲染真相。

**Goal:** 完成统一长任务、真实素材派生、权威预览、增量缓存、旧项目迁移、Web 生产接入、资源调度、真实媒体、Windows、安全与灰度发布闭环。

**Design:** `docs/superpowers/specs/2026-08-11-production-foundation-heavy-engineering-design.md`

**Planning baseline:** `9bca5e97c3d11718a604eb3f2344d19a723de700`

**Estimated effort:** 37–63 人周；建议 3 条独立开发线，日历工期约 4–6 个月。

## 1. 执行顺序

| Phase | 内容                          | 前置            | Gate |
| ----- | ----------------------------- | --------------- | ---- |
| 0     | Foundation 基线与共享契约冻结 | 当前 checkpoint | G0   |
| 1     | 统一持久长任务执行框架        | G0              | G1   |
| 2     | 素材派生与内容寻址缓存        | G1              | G2   |
| 3     | 权威区间预览执行器            | G2              | G3   |
| 4     | 增量依赖与缓存失效            | G3              | G4   |
| 5     | 旧项目适配、迁移与双读        | G4              | G5   |
| 6     | Web 生产工作流接入            | G5              | G6   |
| 7     | 资源调度与批量恢复            | G6              | G7   |
| 8     | 真实媒体自动验收平台          | G7              | G8   |
| 9     | Windows packaged runtime 闭环 | G8              | G9   |
| 10    | 安全、可观测性与灰度发布      | G9              | G10  |

## 2. 全局保护规则

- [ ] 每个 Phase 从上一 Gate 放行的 commit 创建独立 `codex/` worktree/branch。
- [ ] 开始编码前读取当前 Foundation decision、ownership map 和上一 stop point。
- [ ] 不在共享根目录同时修改数据库 schema、Job 契约、主 API wiring、Remotion Root、launcher 或 installer。
- [ ] 不执行 `git reset --hard`、`git clean`、批量 checkout、历史重写或覆盖式目录复制。
- [ ] 不修改用户真实 workspace-data、`F:\app\app` 或 `F:\Video` 既有内容。
- [ ] 测试只使用临时项目根、隔离数据库和新建输出目录。
- [ ] 先写失败测试和非法 fixture，再实现契约或状态迁移。
- [ ] 所有 schema 使用严格 major version、拒绝额外字段并提供 Python/TypeScript 镜像。
- [ ] 所有文件引用保存相对路径和 hash，不持久化任意绝对用户路径。
- [ ] 所有长任务输入在 enqueue 时冻结，Worker 不重新读取可变编辑状态。
- [ ] 所有工件通过临时文件、校验和原子发布，禁止直接写最终可见路径。
- [ ] 每个 Phase 结束时运行目标测试、全量静态检查、生成证据并形成 stop point。
- [ ] 未通过真实媒体和 Windows Gate 的能力默认关闭。

## 3. 文件责任与串行修改点

以下路径视为共享串行区：

- `apps/api/src/workbench/domain/enums.py`
- `apps/api/src/workbench/domain/models.py`
- `apps/api/src/workbench/storage/migrations.py`
- `apps/api/src/workbench/jobs/repository.py`
- `apps/api/src/workbench/main.py`
- `apps/api/src/workbench/api/video.py`
- `apps/api/src/workbench/api/timeline_production.py`
- `apps/web/src/api/client.ts`
- `apps/web/src/features/workflow/WorkflowShell.tsx`
- `remotion/src/Root.tsx`
- `packages/contracts/openapi.json`
- `installer/runtime-manifest.json`
- `scripts/launcher.ps1`

一个 Phase 修改共享串行区时，其他 worktree 只允许开发独占文件和测试 fixture。合并后重新创建下游 worktree。

## Phase 0：Foundation 基线与契约冻结

### Task 0.1：确认 checkpoint 与源码指纹

**Execution:** 只读。

- [ ] 确认 branch、HEAD 和 checkpoint commit 可解析。
- [ ] 确认工作树不存在 unmerged path。
- [ ] 读取 Foundation decision、ownership map 和所有有效 stop point。
- [ ] 记录 Python、Node、pnpm、Remotion、FFmpeg、FFprobe 和 PowerShell 版本。
- [ ] 记录 `uv.lock`、`pnpm-lock.yaml`、runtime manifest 和 schema hash。
- [ ] 记录 V1/V2 feature flag 默认值。
- [ ] 输出 `docs/acceptance/production-foundation/<foundation-id>/baseline.json`。

**Acceptance:** baseline 可由 schema 验证；源码、依赖和运行时指纹齐全。

### Task 0.2：建立基线测试结果

- [ ] 后端 unit/integration/contract 测试在隔离缓存目录运行。
- [ ] Web Vitest、typecheck 和 build 分开记录退出码。
- [ ] Remotion Vitest、typecheck 和现有 composition smoke 运行。
- [ ] 运行 release、launcher 和 Windows 只读诊断测试。
- [ ] 将当前已知失败分为源码、环境、权限、文件锁和外部依赖。
- [ ] 不把 `.pytest_cache` 或 `dist/assets` 权限警告声明为业务代码失败。

**Evidence:** `docs/acceptance/production-foundation/<foundation-id>/baseline-tests.json`。

### Task 0.3：冻结共享契约清单

- [ ] 建立 Job、Attempt、Checkpoint、Publication、Lease、Cache、Migration 和 RuntimeCapability 的 ownership 表。
- [ ] 确认 RenderGraph V2/timebase/preview-plan 当前契约版本。
- [ ] 定义 canonical JSON 和 SHA-256 规则。
- [ ] 定义时间字段统一使用 UTC ISO-8601；媒体时间统一使用整数微秒。
- [ ] 定义数据库 UUID、JSON 文件 UUID 和 API UUID 的序列化规则。
- [ ] 列出兼容期允许的 V1 fallback 和禁止 fallback 的 V2 独占语义。

### Task 0.4：准备实施 worktree

- [ ] 创建 `codex/foundation-jobs`。
- [ ] 为后续阶段预留 media、preview、migration、web、scheduler 和 release 分支名。
- [ ] 为每个 worktree 写 owned paths 和 shared paths。
- [ ] 禁止提前创建跨越未通过 Gate 的实现提交。

**Gate G0:** checkpoint 可信、基线可复现、共享契约与文件责任无冲突。

**Stop point:** 记录 HEAD、status manifest、基线证据、已知失败和 G1 安全入口。

## Phase 1：统一持久长任务执行框架

### Task 1.1：先冻结 Job Execution 契约

**Target files:**

- `apps/api/src/workbench/jobs/contracts.py`
- `schemas/job-execution-v1.schema.json`
- `packages/contracts/job-execution-v1.schema.json`
- `tests/contract/test_job_execution_contract.py`

- [ ] 为 JobInputSnapshot、JobAttempt、JobCheckpoint、ArtifactPublication、ResourceRequest 和 ResourceLease 写 Pydantic 模型。
- [ ] 拒绝未知字段、未知 major、非法 hash、负资源、绝对路径和空 fingerprint。
- [ ] canonical payload 排除 created_at、updated_at、临时路径和运行进度。
- [ ] Python 模型与 JSON Schema 使用同一 fixture。
- [ ] 为旧 JobRecord 提供显式兼容适配器，不在模型中无限放宽字段。

**Tests:** 最小有效、完整有效、额外字段、非法状态、非法路径、跨语言 hash golden。

### Task 1.2：扩展 JobType 与 executor registry

**Target files:**

- `apps/api/src/workbench/domain/enums.py`
- `apps/api/src/workbench/jobs/executor_registry.py`
- `apps/api/src/workbench/jobs/execution.py`
- `tests/unit/jobs/test_executor_registry.py`

- [ ] 增加 `render_preview`、`derive_asset`、`build_proxy`、`build_waveform`、`translate_subtitles`、`quality_scan` 和 `render_export`。
- [ ] 保留 `export_package` 兼容 executor。
- [ ] 每种 Job 注册输入模型、executor、checkpoint policy、resource estimator 和 publication policy。
- [ ] 未注册 JobType 在启动检查阶段失败，不进入 Worker 死循环。
- [ ] executor 不允许直接持有 FastAPI request 或前端 DTO。

### Task 1.3：数据库增量迁移

**Target files:**

- `apps/api/src/workbench/storage/migrations.py`
- `apps/api/src/workbench/storage/models.py`
- `tests/unit/storage/test_workspace_migrations.py`
- `tests/integration/test_job_schema_migration.py`

- [ ] 新增 `job_attempts`。
- [ ] 新增 `job_checkpoints`。
- [ ] 新增 `artifact_publications`。
- [ ] 新增 `resource_leases`。
- [ ] 新增 `workers`。
- [ ] 为 job fingerprint、status/priority、lease expiry 和 publication key 建索引。
- [ ] migration 只新增，不删除旧表列。
- [ ] migration 中断回滚；重复运行幂等。
- [ ] 旧 active export job 在迁移后保持唯一性和可恢复状态。

### Task 1.4：实现 revision CAS 与 attempt generation

**Target files:**

- `apps/api/src/workbench/jobs/repository.py`
- `tests/unit/jobs/test_repository_state_machine.py`

- [ ] 所有状态变更使用 `WHERE id=? AND revision=?`。
- [ ] claim 创建新 attempt 和 generation。
- [ ] heartbeat 必须匹配 attempt/generation。
- [ ] 旧 attempt 不得完成、失败或发布新 attempt 的 Job。
- [ ] pause/cancel 请求幂等。
- [ ] terminal Job 不接受恢复或重复状态覆盖。

### Task 1.5：实现安全 checkpoint

**Target files:**

- `apps/api/src/workbench/jobs/checkpoint.py`
- `apps/api/src/workbench/jobs/recovery.py`
- `tests/unit/jobs/test_checkpoint_recovery.py`

- [ ] checkpoint 写入临时文件并计算 hash。
- [ ] 数据库只登记已存在、可验证的 checkpoint。
- [ ] sequence 单调增加。
- [ ] pause 只有在 checkpoint 提交后才完成。
- [ ] resume 创建新 attempt，从最后有效 checkpoint 开始。
- [ ] 损坏 checkpoint 回退到上一有效点或明确失败。

### Task 1.6：实现 ResourceLease 基础服务

**Target files:**

- `apps/api/src/workbench/jobs/leases.py`
- `tests/unit/jobs/test_resource_leases.py`

- [ ] 原子申请 CPU、内存、GPU 和临时磁盘。
- [ ] lease 绑定 job/attempt/worker/generation。
- [ ] heartbeat 续租使用 UTC。
- [ ] 过期租约可回收，旧 Worker 不能续租。
- [ ] 释放操作幂等。
- [ ] 资源超额返回结构化等待原因。

### Task 1.7：实现 exactly-once Publisher

**Target files:**

- `apps/api/src/workbench/jobs/publisher.py`
- `apps/api/src/workbench/jobs/artifacts.py`
- `tests/unit/jobs/test_artifact_publication.py`

- [ ] publication key 由 project、job type、fingerprint 和 output slot 生成。
- [ ] 临时工件完成 hash、size 和媒体探测后才能发布。
- [ ] 同卷原子 rename。
- [ ] 已发布有效 manifest 直接复用。
- [ ] 数据库成功但文件缺失标记 corrupted。
- [ ] 文件存在但数据库未提交可安全对账。
- [ ] 旧 attempt publication 请求被 generation 拒绝。

### Task 1.8：统一 Worker 与启动恢复

**Target files:**

- `apps/api/src/workbench/jobs/worker.py`
- `apps/api/src/workbench/jobs/worker_pool.py`
- `apps/api/src/workbench/main.py`
- `tests/integration/test_worker_recovery_matrix.py`

- [ ] Worker 按 registry 领取多种 JobType。
- [ ] 启动时扫描过期 running/pausing/cancelling 状态。
- [ ] 使用 wake event 和有限轮询，不 busy loop。
- [ ] stop 时请求安全 checkpoint 并限制等待时间。
- [ ] 子进程树由 executor/process runner 负责终止。
- [ ] 单消费者 Worker 保留为兼容模式。

### Task 1.9：统一 Job API

**Target files:**

- `apps/api/src/workbench/api/jobs.py`
- `apps/web/src/api/client.ts`
- `tests/integration/test_job_control_routes.py`

- [ ] GET Job 和 attempt/checkpoint 摘要。
- [ ] POST pause/resume/cancel，使用 expected revision。
- [ ] 返回结构化 conflict、not-pausable、lease-lost 和 corrupted-artifact。
- [ ] 列表分页，不返回密钥、绝对路径或完整命令行。
- [ ] 旧 render-job API 通过兼容 service 调用统一仓库。

### Task 1.10：故障注入 Gate

- [ ] enqueue 后 API 崩溃。
- [ ] claim 后 Worker 崩溃。
- [ ] checkpoint 写一半。
- [ ] heartbeat 中断和 lease 过期。
- [ ] 旧 Worker 恢复并尝试发布。
- [ ] 文件发布与数据库提交之间崩溃。
- [ ] pause/cancel/重启竞态。
- [ ] 并发提交相同 idempotency key。

**Gate G1:** 状态机、checkpoint、lease、恢复和 publication 全部通过；成功产物不重复发布。

## Phase 2：素材派生与内容寻址缓存

### Task 2.1：冻结派生请求和产物契约

**Target files:**

- `apps/api/src/workbench/assets/derivative_models.py`
- `schemas/asset-derivative-v1.schema.json`
- `tests/contract/test_asset_derivative_contract.py`

- [ ] 定义 parent asset/revision/hash、operation、parameters、output contract 和 tool fingerprint。
- [ ] 定义 derivative manifest、probe、license snapshot 和 lineage。
- [ ] operation 参数严格白名单和版本化。
- [ ] 相同父对象、参数和工具版本得到相同 fingerprint。

### Task 2.2：实现内容寻址对象存储

**Target files:**

- `apps/api/src/workbench/assets/object_store.py`
- `tests/unit/assets/test_object_store.py`

- [ ] 流式 SHA-256 和大小统计。
- [ ] 对象写入 `.part` 后原子发布。
- [ ] 同 hash 并发写入只有一个可见对象。
- [ ] 相对路径 containment 和 symlink/junction 防逃逸。
- [ ] read/open/verify API 不信任索引元数据。

### Task 2.3：统一 FFprobe 媒体探测

**Target files:**

- `apps/api/src/workbench/media/probe.py`
- `apps/api/src/workbench/video/process_runner.py`
- `tests/unit/media/test_probe.py`

- [ ] 使用参数数组执行 FFprobe。
- [ ] 解析容器、codec、duration、fps rational、像素格式、alpha、音频布局和字幕流。
- [ ] 超时、损坏 JSON、缺失流和零时长返回结构化错误。
- [ ] 记录 tool version，不保存绝对命令行。
- [ ] 中文、空格和长路径通过。

### Task 2.4：图片与视频派生 executor

**Target files:**

- `apps/api/src/workbench/assets/executors/image.py`
- `apps/api/src/workbench/assets/executors/video.py`
- `tests/integration/test_image_derivatives.py`
- `tests/integration/test_video_derivatives.py`

- [ ] 图片裁剪、缩放、格式转换和 alpha 规范化。
- [ ] 视频裁剪、缩放、代理转码、缩略图和关键帧。
- [ ] 保持 SAR/DAR 和旋转元数据语义。
- [ ] 输出不满足 contract 时阻止发布。
- [ ] 原始对象永不被覆盖。

### Task 2.5：音频波形与瞬态索引

**Target files:**

- `apps/api/src/workbench/assets/executors/audio.py`
- `apps/api/src/workbench/media/waveform.py`
- `tests/integration/test_waveform_derivative.py`

- [ ] 生成多分辨率峰值/RMS 波形。
- [ ] 时间位置使用整数微秒或固定 sample index。
- [ ] 波形 manifest 记录源 hash、采样率和算法版本。
- [ ] 长音频支持分块 checkpoint。
- [ ] Web 可按 viewport 请求需要的层级。

### Task 2.6：背景移除与外部处理适配器

- [ ] 定义 provider-neutral adapter。
- [ ] provider 密钥只从 secret store 读取，不进入 Job payload。
- [ ] 本地/远程输出都必须进入相同 object store 和 probe 流程。
- [ ] 网络中断可恢复，不重复计费请求必须有 operation id。
- [ ] provider 不可用时源素材保持不变。

### Task 2.7：缓存索引、配额与 GC

**Target files:**

- `apps/api/src/workbench/cache/models.py`
- `apps/api/src/workbench/cache/repository.py`
- `apps/api/src/workbench/cache/gc.py`
- `tests/unit/cache/test_gc_policy.py`

- [ ] 保存 cache key、artifact manifest、大小、最后访问和依赖。
- [ ] 配置总容量、项目配额和高低水位。
- [ ] 使用中的对象拥有引用 lease。
- [ ] GC 只删无 lease、可重建缓存。
- [ ] 临时文件按 owner attempt 和年龄清理。
- [ ] 权威源对象、旧项目正文和制作包不可被普通 GC 删除。

### Task 2.8：派生 API 和 Web 状态

- [ ] POST derivative 创建 `derive_asset` Job。
- [ ] GET derivative 返回 queued/running/ready/failed/stale。
- [ ] 素材库展示代理、缩略图、波形和失败诊断。
- [ ] 只有 Publisher 成功后 AssetRegistry 才登记新的独立对象。
- [ ] 删除/归档前检查当前项目和历史 revision 引用。

### Task 2.9：真实媒体 Gate

- [ ] PNG/JPEG/WebP/SVG 安全样本。
- [ ] H.264/H.265/VP9/带旋转视频。
- [ ] 透明视频或明确不支持诊断。
- [ ] WAV/MP3/AAC、多采样率和单/双声道。
- [ ] 损坏、伪 MIME、超大尺寸和路径攻击。

**Gate G2:** 派生对象真实存在、probe 与 contract 一致、缓存复用正确、GC 不删除权威对象。

## Phase 3：权威区间预览执行器

### Task 3.1：保留并扩展现有 preview-plan 契约

**Existing files:**

- `apps/api/src/workbench/rendering/preview.py`
- `apps/api/src/workbench/api/timeline_production.py`
- `tests/unit/rendering/test_preview.py`

- [ ] 保留已经通过的 range 校验、affected range 筛选和确定性 cache key。
- [ ] 新增 graph snapshot ref/hash，不重新实现已有算法。
- [ ] 新增 resource request、priority 和 client request id。
- [ ] 增加 PreviewArtifactManifestV1 schema。

### Task 3.2：提交 `render_preview` Job

**Target files:**

- `apps/api/src/workbench/rendering/preview_service.py`
- `apps/api/src/workbench/api/timeline_production.py`
- `tests/integration/test_preview_job_routes.py`

- [ ] POST preview-jobs 加载指定 graph snapshot。
- [ ] graph ID/hash 不匹配立即拒绝。
- [ ] 相同 cache key 返回有效缓存或同一 active Job。
- [ ] payload 固定 snapshot path/hash、range 和 preset。
- [ ] 请求范围超界、授权阻断和素材缺失返回结构化诊断。

### Task 3.3：构造 range-specific graph view

**Target files:**

- `apps/api/src/workbench/rendering/range_projection.py`
- `tests/unit/rendering/test_range_projection.py`

- [ ] 保留跨边界 transition 所需的前后 handle。
- [ ] 正确投影 source_in、J/L Cut 和字幕 cue。
- [ ] 输出时间从零开始，但 manifest 保留原 timeline range。
- [ ] 不截断仍影响区间的 overlay、音频 fade 和 transition。
- [ ] 24/25/30/60fps 使用统一 timebase fixture。

### Task 3.4：Remotion 视频代理 executor

**Target files:**

- `apps/api/src/workbench/rendering/preview_executor.py`
- `apps/api/src/workbench/rendering/remotion_runner.py`
- `remotion/src/render-graph/RenderGraphComposition.tsx`
- `tests/integration/test_preview_video_proxy.py`

- [ ] 使用 range-specific graph snapshot。
- [ ] preview preset 只改变分辨率、码率、代理资产选择。
- [ ] composition 语义与 final export 相同。
- [ ] 支持安全取消和进程树关闭。
- [ ] video-only 产物非空并通过 probe。

### Task 3.5：FFmpeg 音频代理与字幕

- [ ] 音频使用同一 range projection。
- [ ] J/L Cut、gain、ducking、fade 和 source-in 边界正确。
- [ ] interactive/authoritative 字幕模式在 manifest 中明确。
- [ ] soft subtitle 可作为独立流或预览 sidecar。
- [ ] 音频 duration 与视频允许误差不超过一帧。

### Task 3.6：Preview mux 与发布

- [ ] mux 产物写临时目录。
- [ ] probe 验证 codec、duration、fps、画幅和音频流。
- [ ] manifest 保存 graph/range/runtime/source revisions。
- [ ] Publisher 原子发布到 preview cache。
- [ ] 缓存损坏自动 miss，不返回空文件。

### Task 3.7：Web authoritative preview 面板

**Target files:**

- `apps/web/src/features/video/RenderGraphPreview.tsx`
- `apps/web/src/features/video/AuthoritativePreviewPanel.tsx`
- `apps/web/src/api/client.ts`

- [ ] 提交播放头附近区间。
- [ ] 显示 queued/running/cache hit/failed/stale。
- [ ] 显示 graph revision/hash 和 range。
- [ ] 明确区分 Player 即时预览与权威预览文件。
- [ ] graph 改变时旧预览仍可查看但标为 stale。

### Task 3.8：边界一致性 Gate

- [ ] cut、dissolve、wipe、slide 和 match 边界。
- [ ] J Cut、L Cut 和连续旁白。
- [ ] overlay 入场/出场和 source crop。
- [ ] 双语、逐词高亮、soft/burn-in。
- [ ] 预览区间与完整 final export 对应帧/波形比较。
- [ ] pause、cancel、重启和缓存复用。

**Gate G3:** authoritative preview 与最终成片的剪辑、音频和字幕边界一致；实际 Worker 可恢复。

## Phase 4：增量依赖与缓存失效

### Task 4.1：冻结 CacheDependency 契约

- [ ] 定义 cache domain、node key、upstream hash、time range 和 artifact refs。
- [ ] 定义 stale reason 和 invalidation event。
- [ ] 同一依赖集合规范化排序。
- [ ] Python/TypeScript/schema fixture 一致。

### Task 4.2：扩展 RenderGraph compiler 依赖输出

**Target files:**

- `apps/api/src/workbench/rendering/compiler.py`
- `apps/api/src/workbench/rendering/models.py`
- `schemas/render-graph-v2.schema.json`

- [ ] 节点输出视觉、字幕、音频、transition、overlay 和 asset 依赖。
- [ ] affected ranges 合并相交区间但保留 reasons。
- [ ] soft subtitle、J/L Cut 和画幅变更具有正确域。
- [ ] compiler version 参与下游 cache key。

### Task 4.3：实现持久 Cache Index

- [ ] 新增 cache_entries/cache_dependencies 表。
- [ ] 保存 artifact manifest hash，不信任目录扫描结果。
- [ ] 反向依赖查询能从 source revision 找到受影响缓存。
- [ ] lookup 验证文件、hash、runtime compatibility 和 license。
- [ ] 读操作更新访问时间不阻塞关键事务。

### Task 4.4：实现选择性失效

- [ ] soft subtitle 不失效 video-only。
- [ ] burn-in 字幕只失效相关区间视觉。
- [ ] J/L Cut 不失效 visual node。
- [ ] overlay/transition 只失效交叉区间。
- [ ] 画幅/fps 失效全部布局相关缓存。
- [ ] asset revision 只失效实际引用节点。

### Task 4.5：缓存 GC 与并发安全

- [ ] stale 仅改变索引状态，不在编辑事务内删除大文件。
- [ ] GC 不删除 active lease 和 active Player 引用。
- [ ] 并发 lookup/GC 不返回已删路径。
- [ ] cache manifest/file 不一致进入 corrupted 隔离状态。
- [ ] 提供 dry-run 和诊断统计。

### Task 4.6：属性与性能测试

- [ ] 随机 graph 变更验证“不漏失效”。
- [ ] 验证失效范围不扩大到无关域。
- [ ] 1,000 节点反向依赖查询基准。
- [ ] 缓存命中、损坏和 runtime 升级矩阵。

**Gate G4:** 所有变更类别均有精确失效证据；缓存损坏不会污染预览或导出。

## Phase 5：旧项目适配、迁移与双读

### Task 5.1：建立旧项目 golden fixtures

- [ ] 收集匿名化的 V1 manifest、subtitle artifact、page timeline 和 Props 组合。
- [ ] 覆盖缺失字段、旧绝对路径、重复页面和部分产物丢失。
- [ ] 保存迁移前 source/media/final hash。
- [ ] fixtures 不包含用户正文、密钥和真实个人路径。

### Task 5.2：实现 LegacyProjectAdapter

**Target files:**

- `apps/api/src/workbench/rendering/legacy_adapter.py`
- `tests/unit/rendering/test_legacy_adapter.py`

- [ ] 只读构造 ProductionTimeline 兼容视图。
- [ ] 旧素材注册为内容寻址 legacy snapshot。
- [ ] 旧字幕投影为 SubtitleRenderPlan。
- [ ] 旧 page timeline 转为稳定 page/clip ID。
- [ ] adapter 调用不写项目目录。
- [ ] V2 独占语义明确禁止 V1 fallback。

### Task 5.3：迁移预览

- [ ] 计算将新增的 revision、asset snapshots 和文件。
- [ ] 估算所需磁盘空间。
- [ ] 标出无法迁移、会 stale 或需人工确认的内容。
- [ ] 返回备份和回滚说明。
- [ ] 相同旧项目输入得到相同迁移计划 hash。

### Task 5.4：迁移 journal 与执行器

**Target files:**

- `apps/api/src/workbench/migrations/project_v2.py`
- `apps/api/src/workbench/migrations/journal.py`
- `tests/integration/test_project_v2_migration.py`

- [ ] prepare、snapshot、write、validate、commit 分阶段。
- [ ] 每阶段可重入并有 checkpoint。
- [ ] commit 前失败清理临时内容。
- [ ] commit 后回滚旧入口但保留诊断 revision。
- [ ] 不覆盖旧 manifest、字幕、素材和成片。

### Task 5.5：双读与兼容 API

- [ ] 项目打开优先有效 V2，否则只读 adapter。
- [ ] `/video/preflight` 对 V2 返回 graph preflight 兼容结构。
- [ ] V2 render job 强制 graph ID/hash。
- [ ] legacy fallback 记录审计事件和原因。
- [ ] 关闭 migration flag 时旧项目仍可打开和导出。

### Task 5.6：迁移故障与回归 Gate

- [ ] 迁移中断、重复执行和应用重启。
- [ ] 磁盘不足和素材丢失。
- [ ] 降级打开和回滚。
- [ ] 迁移前后源素材和旧成片 hash 不变。
- [ ] 旧项目只读打开不产生 Git/项目目录写入。

**Gate G5:** golden 旧项目可只读、迁移、回滚和继续 V1 导出；V2 独占项目不会静默降级。

## Phase 6：Web 生产工作流接入

### Task 6.1：冻结前端编辑状态模型

- [ ] 区分 server revision、pending intent、UI viewport 和 preview state。
- [ ] 所有业务编辑通过 command API。
- [ ] command 返回 revision 更新本地缓存。
- [ ] 409 冲突保留本地意图，不静默丢弃。
- [ ] graph revision/hash 和 stale reasons 进入统一 store。

### Task 6.2：时间线几何与交互内核

**Target files:**

- `apps/web/src/features/timeline/timelineEditor.ts`
- `apps/web/src/features/timeline/TimelineWorkspace.tsx`
- `apps/web/src/features/timeline/useTimelineInteraction.ts`

- [ ] 统一微秒到像素转换和 zoom anchor。
- [ ] 拖动、裁剪、分割、多选、框选和键盘移动。
- [ ] frame、clip、marker 和 playhead 吸附。
- [ ] ripple、链接片段和锁定轨道规则。
- [ ] pointer capture、自动滚动和取消交互。
- [ ] 500 clips/20 tracks 使用虚拟化。

### Task 6.3：波形、缩略图与代理加载

- [ ] 根据 viewport 选择波形层级。
- [ ] 缩略图和代理异步加载，失败不阻塞编辑。
- [ ] 旧 revision 请求完成时不得覆盖新 revision 状态。
- [ ] 素材派生 Job 状态在 clip 上可见。
- [ ] 缓存降级显示原因。

### Task 6.4：历史、撤销重做与冲突重放

- [ ] undo/redo 调用服务端 revision 命令。
- [ ] 重启后历史面板可重建。
- [ ] 冲突时刷新最新 revision 并尝试重放意图。
- [ ] 无法重放时展示原意图、当前状态和可选操作。
- [ ] 不维护第二套完整可变业务副本。

### Task 6.5：双模式预览与诊断

- [ ] interactive Player 使用当前 graph snapshot。
- [ ] authoritative preview 使用 Job 产物。
- [ ] 显示 graph hash、range、cache hit 和 stale。
- [ ] diagnostics overlay 显示缺失代理、授权、runtime 和降级。
- [ ] preview 与 export 的差异有明确解释。

### Task 6.6：七步工作流 wiring

- [ ] MaterialCollection 进入匹配和旁白步骤。
- [ ] 音频、字幕、presenter 和素材进入统一时间线。
- [ ] 第 6 步包含时间线、字幕、转场、overlay 和预览。
- [ ] 第 7 步绑定 graph 的 preset、质量和制作包。
- [ ] 全局导航接入素材库、批量中心和资源监视器。
- [ ] 各 feature flag 关闭时旧流程可完成。

### Task 6.7：可访问性和性能 Gate

- [ ] 键盘完成选择、移动、裁剪、分割和撤销。
- [ ] focus、ARIA 和 screen reader 标签。
- [ ] 500 clips/20 tracks 常规交互 50fps 目标。
- [ ] 长波形和缩略图不造成主线程长任务。
- [ ] Playwright 覆盖刷新、冲突和任务恢复。

**Gate G6:** 编辑、历史、冲突、stale、双预览和七步工作流闭环通过。

## Phase 7：资源调度与批量恢复

### Task 7.1：批次权威迁入数据库

- [ ] 新增 batches 和 batch_items 表。
- [ ] JSON 批次文件降为导出快照，不再是唯一权威。
- [ ] BatchItem 保存 page、preset、fingerprint、priority、dependencies 和 resource request。
- [ ] migration 导入现有 JSON 批次并可重复运行。

### Task 7.2：Worker capability registry

- [ ] Worker 注册 runtime、job types、codec 和资源容量。
- [ ] heartbeat 更新能力和健康状态。
- [ ] 过期 Worker 不参与调度。
- [ ] 能力变化不会中途迁移正在运行的 attempt。

### Task 7.3：ResourceLease Manager

- [ ] 全局与项目级 CPU/内存/GPU/磁盘配额。
- [ ] 原子申请和释放。
- [ ] generation 防止旧 Worker 续租。
- [ ] 前台预览保留资源。
- [ ] 资源不足提供可解释等待原因。

### Task 7.4：公平 Dispatcher

- [ ] 优先级队列。
- [ ] 同优先级项目轮转。
- [ ] 等待老化不突破安全上限。
- [ ] 依赖成功后才可派发。
- [ ] 项目并发上限。
- [ ] GPU 等待/CPU 降级遵循显式策略。

### Task 7.5：多 Worker Pool

- [ ] 按 capability 分组领取任务。
- [ ] Worker 数量和 concurrency 可配置。
- [ ] Remotion/FFmpeg 子进程并发受 lease 限制。
- [ ] 单消费者 Worker 保留兼容 executor。
- [ ] 关闭新 scheduler 可回到旧路径。

### Task 7.6：夜间队列

- [ ] 明确 timezone 和跨午夜窗口。
- [ ] 睡眠/唤醒后重新计算。
- [ ] 时钟回拨不重复派发。
- [ ] 窗口结束时 checkpoint 后暂停。
- [ ] 前台任务可按策略抢占等待资源，不强杀后台任务。

### Task 7.7：页面级重跑和缓存复用

- [ ] 只选择 failed/cancelled item。
- [ ] 新 attempt 保留历史错误。
- [ ] 成功页和有效缓存不重复执行。
- [ ] 依赖变更后只重跑受影响 item。
- [ ] 批次最终发布检查所有必需产物。

### Task 7.8：重启恢复和 exactly-once

- [ ] 启动扫描 batch/job/attempt/lease/publication。
- [ ] 过期 running item 回到可恢复状态。
- [ ] 成功 publication 不重复。
- [ ] 崩溃中间态有确定恢复决策。
- [ ] 20 项目模拟器验证公平性和资源上限。

### Task 7.9：资源监视器 UI

- [ ] 展示 Worker、CPU、内存、GPU、磁盘和 lease。
- [ ] 展示队列等待原因和预计顺序，不承诺不可靠完成时间。
- [ ] 支持 batch 暂停、恢复、取消和失败页重跑。
- [ ] 越权操作和 revision 冲突有明确提示。

**Gate G7:** 资源上限、公平性、依赖、夜间队列、重启和 exactly-once 全部通过。

## Phase 8：真实媒体自动验收平台

### Task 8.1：定义 ProductionMediaFixtureV1

- [ ] manifest schema 记录 source、license、expected probe、关键时间点和允许误差。
- [ ] fixture 使用相对路径和 hash。
- [ ] 大媒体通过确定性生成器生成。
- [ ] 禁止提交用户媒体、密钥和受限素材。

### Task 8.2：建立确定性媒体生成器

- [ ] 生成测试色块、运动图形、透明素材和固定帧标记。
- [ ] 生成带脉冲/频率标记的音频。
- [ ] 生成 24/25/30/60fps 和多画幅样本。
- [ ] 生成 SRT/WebVTT/ASS 双语和逐词 cue。
- [ ] 输出生成器版本和 hash。

### Task 8.3：FFprobe 与 waveform oracle

- [ ] 保存期望容器/流元数据。
- [ ] 检测 duration、fps rational、音频布局和字幕流。
- [ ] 波形比较使用时间容差和幅度容差。
- [ ] J/L Cut 脉冲位置自动验证。

### Task 8.4：视觉 snapshot 与成片差异

- [ ] 关键帧截图绑定 graph/range/frame。
- [ ] 感知差异阈值和人工复核流程。
- [ ] 转场中点、overlay 边界、字幕高亮和画幅安全区。
- [ ] preview 与 final 对应帧比较。

### Task 8.5：完整矩阵

- [ ] 720p/1080p/4K。
- [ ] 16:9/9:16/1:1。
- [ ] 24/25/30/60fps。
- [ ] 图片、视频、真人、Logo、透明素材和多音频 bus。
- [ ] soft/burn-in/both/none 字幕。
- [ ] 缺失、损坏、越界和授权过期负例。

### Task 8.6：E2E 场景

- [ ] 无大纲 + 多套 PPT + 双语字幕 + 横竖屏导出。
- [ ] 真人视频 + J/L Cut + overlay + 音乐 + 4K。
- [ ] 多文档 + 替换页面 + 差异失效 + 失败页重跑。
- [ ] 20 项目夜间批次 + 重启恢复 + 制作包。

**Gate G8:** 真实媒体矩阵全部自动验证；没有以 mock 替代关键执行器。

## Phase 9：Windows packaged runtime 闭环

### Task 9.1：RuntimeCapabilityManifest

- [ ] Node/Chrome/Remotion/FFmpeg/FFprobe 路径和版本。
- [ ] encoder/decoder/pixel format/hardware acceleration。
- [ ] 字体目录和字符覆盖。
- [ ] Office/LibreOffice/无 Office 能力。
- [ ] VC Runtime、临时目录、长路径和磁盘能力。
- [ ] manifest 不包含不必要绝对用户路径。

### Task 9.2：统一 Windows ProcessRunner

- [ ] 参数数组执行，不拼接 shell。
- [ ] 中文、空格、`&`、括号和长路径。
- [ ] timeout、cancel 和进程树关闭。
- [ ] stdout/stderr 限量、分阶段和脱敏。
- [ ] filter script 使用安全临时文件。
- [ ] 退出码、signal 和 stderr 分类。

### Task 9.3：打包运行时

- [ ] installer/runtime manifest 包含所需二进制和 hash。
- [ ] 安装后自检确认文件存在和版本匹配。
- [ ] Remotion browser/runtime 可在无开发依赖环境启动。
- [ ] FFmpeg/FFprobe 从安装路径调用。
- [ ] 字体 fallback 可解释。

### Task 9.4：路径、权限和文件锁

- [ ] 非 ASCII 用户名、项目名和输出名。
- [ ] 无管理员权限。
- [ ] dist/cache/output 被占用。
- [ ] 临时目录不可写和磁盘满。
- [ ] 杀毒软件延迟/锁定场景。
- [ ] 重试有上限，不删除未知占用文件。

### Task 9.5：安装、升级和回滚

- [ ] 全新安装启动和关闭。
- [ ] 升级后打开 V1/V2 项目。
- [ ] 数据库 migration 失败进入只读诊断。
- [ ] 回滚旧版本不破坏项目正文。
- [ ] 卸载不删除 workspace-data。

### Task 9.6：异常恢复矩阵

- [ ] 端口占用、断网、睡眠、唤醒和时钟回拨。
- [ ] GPU 不可用、encoder 缺失和浏览器启动失败。
- [ ] Office/LibreOffice 存在和不存在。
- [ ] 渲染中强杀应用并重启。
- [ ] 任务、lease、checkpoint 和 publication 恢复正确。

**Gate G9:** 隔离 Windows 安装版完成安装、升级、真实渲染和异常恢复，不依赖开发机全局工具。

## Phase 10：安全、可观测性与灰度发布

### Task 10.1：安全测试矩阵

- [ ] 路径穿越、junction/symlink、跨项目 asset。
- [ ] 伪 MIME、恶意媒体、压缩炸弹和超大输入。
- [ ] FFmpeg/filter/文件名模板注入。
- [ ] 恶意 Office、字体、LUT 和字幕附件。
- [ ] lease generation、越权暂停/取消和 publication 重放。
- [ ] API、数据库、日志和制作包密钥/路径泄露检查。

### Task 10.2：结构化诊断事件

- [ ] 定义 diagnostic code、severity、scope、cause 和 remediation。
- [ ] graph、project、batch、job、attempt 和 publication 可关联。
- [ ] 缓存 miss、失效、降级和 preflight 阻断可解释。
- [ ] 用户可见信息不暴露内部绝对路径和命令行。

### Task 10.3：资源与性能指标

- [ ] queue wait、stage duration、retry/recovery。
- [ ] CPU、峰值内存、GPU、磁盘和临时空间。
- [ ] cache hit/miss、失效原因和复用字节。
- [ ] 子进程版本、退出码和错误分类。
- [ ] 指标写入有容量上限和保留策略。

### Task 10.4：性能总门禁

- [ ] 1,000 节点全量编译 p95 < 500ms。
- [ ] 增量编译 p95 < 150ms。
- [ ] interactive preview 首帧 p95 < 3 秒。
- [ ] 10 秒 authoritative preview 缓存命中 p95 < 8 秒。
- [ ] 1080p30 graph 解释开销 < 10%。
- [ ] 500 clips/20 tracks 编辑器交互达标。
- [ ] 20 项目批次不突破资源上限。

### Task 10.5：Feature flag 依赖图

- [ ] Durable Jobs 是 preview、derived media 和 scheduler 的前置。
- [ ] V2 preview 依赖 graph compile、derived media 和 preview Worker。
- [ ] V2 export 依赖 strict assets、runtime capability 和 G8/G9。
- [ ] migration flag 与 V1 fallback 独立。
- [ ] 非法开关组合在启动时诊断并保持安全旧路径。

### Task 10.6：灰度顺序与回退条件

- [ ] compile-only。
- [ ] interactive preview 只读。
- [ ] authoritative preview 内部启用。
- [ ] V2 export 内部启用。
- [ ] 新项目默认 V2。
- [ ] 每阶段定义错误率、恢复率、性能和回退阈值。
- [ ] 回退不删除新 revision、Job 证据和缓存 manifest。

### Task 10.7：最终文档与证据包

- [ ] 用户手册：时间线、素材、字幕、预览、导出和批量。
- [ ] 管理员手册：资源、缓存、迁移、恢复和 runtime。
- [ ] 排障手册：诊断 code 和恢复动作。
- [ ] 安全报告。
- [ ] 性能报告。
- [ ] Windows 安装验收报告。
- [ ] 迁移与回滚报告。
- [ ] 灰度发布报告。

### Task 10.8：最终发布 Gate

- [ ] G0-G9 证据绑定同一候选源码或可追溯后继提交。
- [ ] 后端、Web、Remotion、契约、E2E 和 release 全量通过。
- [ ] 真实媒体和 Windows 报告不是旧源码证据。
- [ ] 安全高风险问题为零。
- [ ] 默认开关、升级和回退已演练。
- [ ] 形成 RELEASE_READY decision。

**Gate G10:** 安全、性能、诊断、真实媒体、Windows、迁移和灰度条件全部满足，才允许新项目默认启用 V2。

## 4. 每阶段统一测试命令模板

命令必须在对应 worktree 和隔离临时目录执行，并保存版本、退出码和日志路径。

```powershell
uv run pytest -q tests/unit
uv run pytest -q tests/contract
uv run pytest -q tests/integration
uv run ruff check apps/api/src tests
uv run mypy apps/api/src
pnpm --filter @workbench/web test
pnpm --filter @workbench/web typecheck
pnpm --filter @workbench/remotion test
pnpm --filter @workbench/remotion build
```

如果 `uv` 受当前 Windows 权限限制，可以使用已安装项目虚拟环境执行等价命令，但证据中必须记录实际 Python 路径。构建产物目录存在文件锁时，先记录 owner 和错误；不得直接删除未知进程占用目录。

## 5. 单阶段交付模板

每个 Phase 完成时必须交付：

- [ ] 设计/ADR 变更摘要。
- [ ] 新增或升级的 schema 和 golden fixtures。
- [ ] 数据库 migration 与 rollback/兼容说明。
- [ ] 单元、契约、集成、故障注入和必要真实媒体测试。
- [ ] feature flag 默认值和依赖。
- [ ] 性能与资源基线。
- [ ] 安全检查结果。
- [ ] 用户可见诊断和文档。
- [ ] stop point：branch、HEAD、status manifest、owned paths、shared paths、completed、remaining、safe resume。

## 6. Stop/Resume 规则

- 任一共享契约发生未决冲突：停止写入，形成 stop point，交由主集成线决议。
- migration 出现不可逆写入风险：停止，不推断用户选择。
- 测试需要修改真实 workspace-data 或安装目录：停止并申请明确授权。
- Windows 文件锁目标不明：只读定位 owner，不删除目录或终止未知进程。
- Gate 失败但仍可修复：留在当前 Phase，不开始下一 Phase。
- 同一阻塞在连续三次恢复中仍无法推进：标记 blocked 并列出所需外部条件。

## 7. 最终验收清单

### 7.1 任务与恢复

- [ ] 所有长任务拥有持久 job/attempt/checkpoint/lease/publication。
- [ ] 暂停、取消、重启和旧 Worker 回归不破坏状态。
- [ ] 成功工件 exactly-once 发布。

### 7.2 素材与缓存

- [ ] 派生素材是真实独立对象并通过 probe。
- [ ] 内容寻址缓存可验证、可复用、可安全 GC。
- [ ] affected ranges 选择性失效正确。

### 7.3 预览与渲染

- [ ] interactive、authoritative 和 final 使用同一 graph 语义。
- [ ] transition、J/L Cut、overlay、字幕和音频边界一致。
- [ ] 预览缓存损坏不会返回空文件或旧内容。

### 7.4 迁移与 Web

- [ ] 旧项目只读打开不写盘。
- [ ] 显式迁移可中断、恢复和回滚。
- [ ] Web revision、history、冲突、stale 和 diagnostics 完整。

### 7.5 调度与发布

- [ ] 多项目批次遵守资源上限和公平性。
- [ ] 夜间队列在睡眠、重启和时钟回拨后正确恢复。
- [ ] 真实媒体、Windows、安全、性能和灰度报告齐全。
- [ ] 默认启用 V2 前存在已演练回退路径。

完成以上所有项目且 G10 通过后，本共享底座项目才可声明完成。
