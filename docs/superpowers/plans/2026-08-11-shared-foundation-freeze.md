# PPT Video Workbench 共享开发基线冻结与隔离集成逐项实施计划

> 本计划是 RenderGraph V2、P1 七项生产能力和 P2 平台能力正式集成前的共同前置项目。当前多个窗口共享恢复根目录；在窗口停点和文件责任完成前，只允许文档、只读盘点和隔离工具开发，不得在根目录运行格式化、全量构建、数据库迁移、安装或渲染验收。

**Goal:** 形成唯一、可恢复、可重建、通过分级门禁的 foundation commit 和冻结快照，同时让后续项目在独立 worktree 中继续开发，不影响其他窗口。

**Design:** `docs/superpowers/specs/2026-08-11-shared-foundation-freeze-design.md`

**Tech Stack:** PowerShell 7/Windows PowerShell 5.1、Python 3.12、Git、Pydantic 2、JSON Schema、SHA-256、uv、pnpm 11、Vitest、Playwright、Remotion、FFmpeg/FFprobe、现有 Windows 构建与验收脚本。

## 1. 执行等级

| 等级               | 允许内容                                             | 当前状态               |
| ------------------ | ---------------------------------------------------- | ---------------------- |
| `NOW-DOCS`         | 设计、计划、只读状态审计、契约草案                   | 允许                   |
| `AFTER-STOPPOINTS` | 隔离工具、ownership map、候选 checkpoint             | 等所有 writer 停点     |
| `AFTER-FOUNDATION` | 从 foundation commit 创建 P1/P2/RenderGraph worktree | G0-G4 后允许           |
| `AFTER-RENDER`     | 接入正式预览、成片、导出和调度主链                   | G5 后允许              |
| `AFTER-RELEASE`    | 隔离安装、升级/回滚和正式分发                        | G6-G7 且获得授权后允许 |

## 2. 全局保护规则

- [ ] 不执行 `git reset --hard`、`git clean`、批量 checkout、目录覆盖复制、worktree prune 或历史重写。
- [ ] 不用文件时间戳推断权威版本，不自动选择冲突一方。
- [ ] 不在活动根目录运行 `pnpm format`、全量构建、PyInstaller、Remotion render 或安装验收。
- [ ] 不修改 `F:\app\app`，除非已经达到 RELEASE_READY 且用户明确授权。
- [ ] 不修改真实 workspace-data 数据库；所有验收使用隔离复制。
- [ ] 不覆盖或清理 `F:\Video` 既有内容；输出只进入新的 Foundation ID 子目录。
- [ ] 不访问或收集密钥、浏览器登录态、凭证库和全量环境变量。
- [ ] 只终止当前 gate 自己启动并登记的进程，不停止来源不明的服务。
- [ ] 每次测试、构建和渲染都绑定 snapshot hash；hash 变化立即作废。
- [ ] 失败结果完整保留；修复后生成新候选和新 Foundation ID。

## 3. 计划产物和文件责任

### 3.1 新增契约与文档

- `schemas/foundation/window-stop-point-v1.schema.json`
- `schemas/foundation/ownership-map-v1.schema.json`
- `schemas/foundation/foundation-freeze-manifest-v1.schema.json`
- `schemas/foundation/gate-evidence-v1.schema.json`
- `docs/acceptance/foundation/README.md`
- `docs/acceptance/foundation/<foundation-id>/decision.md`
- `tests/contract/test_foundation_freeze_contracts.py`

### 3.2 新增工具

- `scripts/foundation/read-state.ps1`
- `scripts/foundation/collect-stop-point.ps1`
- `scripts/foundation/build-ownership-map.py`
- `scripts/foundation/create-checkpoint.ps1`
- `scripts/foundation/create-frozen-snapshot.ps1`
- `scripts/foundation/verify-frozen-snapshot.py`
- `scripts/foundation/run-gate.ps1`
- `scripts/foundation/build-evidence-index.py`
- `scripts/foundation/promote-foundation.ps1`

### 3.3 测试

- `tests/unit/foundation/test_ownership_map.py`
- `tests/unit/foundation/test_snapshot_manifest.py`
- `tests/unit/foundation/test_evidence_index.py`
- `tests/integration/test_foundation_checkpoint_rebuild.py`
- `tests/security/test_foundation_path_containment.py`
- `tests/security/test_foundation_log_redaction.py`

这些文件由 Foundation owner 独占。主业务源码、数据库迁移、Remotion 主 composition、launcher、installer 和现有 release 脚本在 Phase 7 前不修改。

## 4. 总体阶段和放行关系

| 阶段    | 内容                              | 前置         | 输出/Gate             |
| ------- | --------------------------------- | ------------ | --------------------- |
| Phase 0 | 契约、只读盘点和安全护栏          | 无           | G0                    |
| Phase 1 | 收集窗口停点                      | G0           | G1                    |
| Phase 2 | 文件责任和冲突决议                | G1           | G2                    |
| Phase 3 | 可恢复 checkpoint 与冻结 snapshot | G2           | G3                    |
| Phase 4 | Foundation 质量矩阵               | G3           | G4 / FOUNDATION_READY |
| Phase 5 | 真实渲染矩阵                      | G4           | G5 / RENDER_READY     |
| Phase 6 | Windows 发布和回滚                | G5           | G6-G7 / RELEASE_READY |
| Phase 7 | 推广 foundation 与创建 worktree   | 对应放行等级 | 下游安全继续点        |

## Phase 0：契约、盘点和安全护栏

### Task 0.1：冻结边界定义

**Execution:** NOW-DOCS，只读。

- [ ] 将主源码、安装目录、workspace-data 和 `F:\Video` 写入逻辑边界表。
- [ ] 使用规范化绝对路径验证四个边界互不嵌套。
- [ ] 标记每个边界的 authority、允许写入范围和禁止操作。
- [ ] 记录当前 branch、HEAD、status 数量和 unmerged 数量。
- [ ] 不扫描 workspace-data 文件正文，只记录目录存在性和必要元数据。

**Tests:** 路径规范化、盘符大小写、尾分隔符、`..`、junction/symlink 逃逸负例。

**Gate G0-A:** 四边界全部识别；任何目标无法解析或相互嵌套时停止。

### Task 0.2：定义四个版本化 Schema

- [ ] 先编写非法绝对路径、未知字段、错误 major、非法 hash、凭证字段和 NaN 的失败测试。
- [ ] 实现 `WindowStopPointV1`。
- [ ] 实现 `OwnershipMapV1`。
- [ ] 实现 `FoundationFreezeManifestV1`。
- [ ] 实现 `GateEvidenceV1`。
- [ ] 为每个 schema 增加最小有效、完整有效和非法 fixture。
- [ ] 验证规范化 JSON 跨 Python/Node 得到一致 hash。

**Tests:** `uv run pytest tests/contract/test_foundation_freeze_contracts.py`；Node/AJV schema 编译与 golden fixture。

**Gate G0-B:** 所有 schema 拒绝绝对路径、凭证、未知 major 和未知额外字段。

### Task 0.3：实现只读状态盘点器

- [ ] 使用 Git porcelain v2 `-z` 输出，正确处理空格、中文、rename 和冲突状态。
- [ ] 记录 branch、HEAD、git dir/common dir、所有 worktree 和 status manifest hash。
- [ ] 统计 tracked、untracked、ignored、unmerged，避免把备份/缓存当源码。
- [ ] 读取相关端口和进程摘要，但不停止进程。
- [ ] 记录 uv、Python、pnpm、Node、FFmpeg/FFprobe、Remotion 和 PowerShell 版本。
- [ ] 输出中去除用户正文、密钥和非必要命令行参数。
- [ ] 连续运行两次，验证只读盘点不改变 Git 状态。

**Tests:** dirty fixture repo、rename、中文路径、损坏 pointer、多个 worktree、进程信息脱敏。

**Gate G0:** 0.1-0.3 全部通过；盘点前后源码状态 hash 相同。

## Phase 1：收集窗口停点

### Task 1.1：建立活动窗口登记表

**Depends on:** G0。

- [ ] 登记恢复、最终渲染、特效、时间线、质量、P1、P2、Windows 发布等所有写入窗口。
- [ ] 标记 writer、read_only、idle 三种模式。
- [ ] 为每个 writer 分配唯一 `window_id` 和 stop point 文件。
- [ ] 记录其源码根、worktree、branch、HEAD、文件责任和共享文件触达范围。
- [ ] 未知窗口或未知进程只登记事实，不擅自停止。

**Acceptance:** 实际 worktree/进程与登记表双向可追溯；没有“在写但未登记”的窗口。

### Task 1.2：逐窗口生成 StopPoint

- [ ] 每个窗口记录已完成事项、门禁、证据引用、已知失败和剩余任务。
- [ ] 保存精确 status manifest hash，而不是只保存数量。
- [ ] 列出后续仍可能修改的路径和共享文件。
- [ ] 给出 `safe_resume`，说明新窗口如何从停点继续。
- [ ] writer 明确 `will_write_again=false` 后进入 idle；否则迁移到独立 worktree。
- [ ] 校验 stop point 与当前实际 HEAD/status 一致。

**Stop condition:** 任一 writer 无法形成一致 stop point，保持 `WAITING_FOR_STOPPOINTS`，不催促性合并、不创建 checkpoint。

### Task 1.3：确认根目录静默窗口

- [ ] 在约定的短静默期内重复读取 status manifest。
- [ ] 两次结果必须完全相同。
- [ ] 检查没有新增构建、格式化、测试或渲染进程写入根目录。
- [ ] 只读窗口可以继续存在，但不得写入主源码。

**Gate G1:** 所有 writer 已停点或迁移；连续盘点 hash 一致。

## Phase 2：文件责任和冲突决议

### Task 2.1：生成 Ownership Map

**Depends on:** G1。

- [ ] 合并所有 stop point 的 `owned_paths` 和实际状态清单。
- [ ] 将条目分类为 source、test、contract、doc、generated、cache、backup、evidence、user-data。
- [ ] 为正式源码和测试分配唯一 authoritative owner。
- [ ] 将主应用、公共模型、迁移、OpenAPI/client、Remotion Root 和 release 脚本标为 shared integration files。
- [ ] 输出未知来源、零 owner、多 owner 和跨边界条目。

**Tests:** 重叠 glob、rename、删除/新增同路径、大小写碰撞和 Windows 保留名。

### Task 2.2：清理“归属不明”，不清理文件

- [ ] 对每个未知来源条目选择：纳入、隔离、归档、生成物排除或等待确认。
- [ ] 任何删除候选只记录建议，不在本阶段删除。
- [ ] 对 `.tmp`、backup、release、cache、日志和压缩包制定显式排除/保留规则。
- [ ] 排除规则记录原因、owner 和是否需要恢复。
- [ ] 重新生成 ownership map，未知来源计数必须为 0。

### Task 2.3：逐文件解决语义冲突

- [ ] 对多 owner 文件生成 base/ours/theirs/候选四方摘要。
- [ ] 由对应窗口提供语义说明和必须保留的行为测试。
- [ ] 共享契约冲突先冻结契约，再适配实现。
- [ ] 主渲染/发布冲突使用最小差异合并，不做整目录复制。
- [ ] 每项决议记录输入 hash、选择理由、验证测试和 integration owner。
- [ ] 决议后的文件再次检查是否覆盖其他窗口未提交成果。

**Stop condition:** 无法证明语义兼容时保持冲突未决，不猜测合并。

### Task 2.4：建立候选来源清单

- [ ] 列出进入 checkpoint 的所有提交、未提交 diff 和未跟踪源文件。
- [ ] 列出排除项及理由。
- [ ] 验证 Git unmerged 为 0。
- [ ] 验证正式文件全部恰有一个 owner。
- [ ] 对候选执行密钥和绝对路径泄漏扫描，只报告位置，不读取秘密值。

**Gate G2:** 未知来源为 0、语义冲突为 0、unmerged 为 0。

## Phase 3：可恢复 checkpoint 和冻结 snapshot

### Task 3.1：创建候选 checkpoint

**Depends on:** G2。

- [ ] 为候选生成新的 Foundation ID。
- [ ] 保存 branch、HEAD、binary diff、未跟踪内容 manifest 和依赖锁 hash。
- [ ] 创建明确 Git ref/commit；提交范围只包含经 ownership map 接受的内容。
- [ ] 生成重建说明和恢复命令。
- [ ] 不 stage 或提交排除项、用户数据、缓存、构建和安装目录。
- [ ] 保留上一份恢复备份，不覆盖旧 checkpoint。

**Approval:** 如果创建提交会把其他窗口未确认内容纳入历史，停止并等待对应 owner 确认。

### Task 3.2：在新目录重建 checkpoint

- [ ] 从 Git ref/commit 和记录的补充内容在新目录重建。
- [ ] 不从活动根目录做覆盖式复制。
- [ ] 验证文件清单、大小、SHA-256、依赖锁和 schema hash。
- [ ] 验证重建目录 Git 状态符合 manifest。
- [ ] 故意遗漏一个未跟踪 fixture，确认验证器快速失败。

**Acceptance:** 两次独立重建得到相同 manifest hash。

### Task 3.3：创建不可变冻结 snapshot

- [ ] 从重建成功的 checkpoint 创建 snapshot，而不是直接从活动根目录创建。
- [ ] 生成 `FoundationFreezeManifestV1`。
- [ ] 设置只读约束或启动内容变更探针。
- [ ] 所有 gate 输出定向到 snapshot 外的 evidence 目录。
- [ ] 冻结前后双次 hash 必须相同。
- [ ] 记录 snapshot 与之前已验收冻结快照的差异摘要。

### Task 3.4：验证恢复和失败路径

- [ ] 损坏 manifest、篡改文件、替换软链接、hash 不匹配均被阻断。
- [ ] 中断 snapshot 创建不会留下可被误认的完整目录。
- [ ] 重复创建相同内容幂等返回同一内容 hash，但使用独立执行记录。
- [ ] 取消后保留 checkpoint，不改变活动根目录。

**Gate G3:** checkpoint 可重建；snapshot hash 稳定且不可变。

## Phase 4：Foundation 质量矩阵

### Task 4.1：运行 Python 门禁

**Execution root:** 冻结 snapshot。

- [ ] 锁定 Python/uv 版本和依赖锁 hash。
- [ ] `uv run ruff check .`。
- [ ] `uv run ruff format --check .`。
- [ ] `uv run mypy apps/api/src peripheral-platform/src`。
- [ ] `uv run pytest` 全量运行，记录 warnings、skips、耗时和退出码。
- [ ] 确认超时后无残留测试子进程。

**Gate:** 任一命令非零、超时或日志不完整均失败；禁止只重跑失败项后宣称全量通过。

### Task 4.2：运行 Web 和契约门禁

- [ ] 使用锁定 pnpm 和 lockfile，禁止隐式升级依赖。
- [ ] `pnpm lint`。
- [ ] `pnpm typecheck`。
- [ ] `pnpm test`。
- [ ] `pnpm build`。
- [ ] 校验 OpenAPI、JSON Schema、Python/TypeScript DTO 和 golden fixtures。
- [ ] 运行关键本地 Playwright E2E；保存 trace、截图和退出码。

### Task 4.3：运行 Remotion 与媒体基础门禁

- [ ] Remotion typecheck、unit、composition contract 和 seek-safe 测试。
- [ ] FFmpeg/FFprobe 版本、编码器、解码器和 filters 能力探针。
- [ ] 运行短媒体 smoke，不使用用户真实输出路径。
- [ ] 验证进程取消、stderr 持续消费、超时和子进程回收。
- [ ] 验证媒体 staging、hash、ffprobe 和原子发布。

### Task 4.4：运行安全与恢复门禁

- [ ] 路径 containment、symlink/junction 逃逸、命令参数注入测试。
- [ ] 日志脱敏扫描。
- [ ] checkpoint/snapshot 重建集成测试。
- [ ] 输入 fingerprint、任务幂等、取消和重启恢复测试。
- [ ] 安装目录、真实 workspace-data 和既有 `F:\Video` 内容保持不变。

### Task 4.5：生成 FOUNDATION_READY 决策

- [ ] 汇总 G0-G4 证据，验证全部绑定同一 snapshot hash。
- [ ] 记录通过数量、warnings、skips 和已知限制。
- [ ] 任何 warning 必须有 owner、风险等级和是否允许下游开发的决议。
- [ ] 创建 foundation commit/ref 的只读使用说明。
- [ ] 输出下游 worktree 建议，不立即创建或修改其他窗口。

**Gate G4 / FOUNDATION_READY:** G0-G4 全部有效。此时 P1/P2/RenderGraph 可在独立 worktree 开始，但真实渲染主链仍保持旧路径和默认关闭的 feature flags。

## Phase 5：真实渲染矩阵

### Task 5.1：准备隔离验收数据根

**Depends on:** FOUNDATION_READY。

- [ ] 从已获准样本创建只读源副本和新的隔离 workspace-data。
- [ ] 不复制密钥、账号 token 或无关用户项目。
- [ ] 每个样本记录项目 manifest、输入媒体 hash 和预期模式。
- [ ] `F:\Video` 仅使用新的 `<foundation-id>` 子目录。
- [ ] 验收 API 使用独立端口、PID ledger 和日志目录。

### Task 5.2：8 页标准项目完整验收

- [ ] 启动冻结 runtime，健康检查通过。
- [ ] general/video preflight `allowed=true` 且 blocking issue 为 0。
- [ ] 提交异步渲染，记录 job ID、输入 fingerprint 和状态流转。
- [ ] 完成后核对 MP4、制作包、artifact 数量、时长、1920x1080、H.264/AAC。
- [ ] 记录 MP4/制作包 SHA-256。
- [ ] 重启后终态、进度、产物和 hash 仍可查询。

### Task 5.3：50 页长项目与资源验收

- [ ] 记录总耗时、单页耗时、峰值内存、磁盘和进程数量。
- [ ] 验证缓存命中、失败重试、取消和重启恢复。
- [ ] 确认最终时长与页面/音频时间轴误差在契约内。
- [ ] 运行并发限制，确认不会压垮用户桌面或启动重复渲染。
- [ ] 超时或资源超预算产生结构化失败，不留下伪成功产物。

### Task 5.4：真人与竖屏样本

- [ ] 真人源视频探测、磁盘预算、页面锚点和时间线通过。
- [ ] 阻塞锚点必须人工校正，review 警告有明确确认记录。
- [ ] 验证音画同步、字幕、presenter layout 和安全降级。
- [ ] 9:16 项目验证裁剪、安全区、字幕/人物避让和输出元数据。
- [ ] 同时保留 16:9 回归，防止竖屏改动污染默认画幅。

### Task 5.5：质量检测样本

- [ ] 固定黑帧、冻结、静音、时长、字幕越界等正负 fixtures。
- [ ] 记录规则版本、问题 fingerprint、确认/豁免和报告 hash。
- [ ] 对真实成片运行质量 gate，严重问题必须阻断发布。
- [ ] 质量报告绑定同一 RenderGraph/输入 fingerprint 或旧链路等价标识。

### Task 5.6：生成 RENDER_READY 决策

- [ ] 所有样本证据绑定同一 snapshot。
- [ ] 记录实际未覆盖项，不以 mock 替代真人/竖屏/长项目证据。
- [ ] 旧 V1 转视频结果与新候选无不可解释回退。
- [ ] 明确哪些新能力仍在 feature flag 后。

**Gate G5 / RENDER_READY:** 8 页、50 页、真人、竖屏、质量和重启恢复全部通过。

## Phase 6：Windows 发布、升级和回滚

### Task 6.1：从冻结 snapshot 构建候选

**Depends on:** RENDER_READY。

- [ ] 使用 `scripts/build-release.ps1` 的独立 staging/work 目录。
- [ ] 构建脚本对依赖、复制、PyInstaller 和 installer 失败立即非零退出。
- [ ] 生成 runtime manifest、许可证清单和产物 SHA-256。
- [ ] 验证安装包内容来自 Foundation ID 对应 snapshot。
- [ ] 不从活动根目录拾取 `.tmp`、backup、cache 或其他窗口产物。

### Task 6.2：隔离安装和首次启动

- [ ] 使用新的隔离安装根和隔离 workspace-data。
- [ ] 首次启动健康、端口选择、运行时发现、FFmpeg/Remotion/Office 探针通过。
- [ ] 验证端口占用、缺少可选组件、路径含中文/空格和低磁盘场景。
- [ ] 验证优雅退出只停止自身进程。
- [ ] 未经授权不安装到 `F:\app\app`。

### Task 6.3：修复安装、升级和回滚

- [ ] 从上一已通过版本升级到候选，既有项目只读打开成功。
- [ ] 修复安装不删除项目和用户设置。
- [ ] 回滚到上一版本后项目、任务和产物仍可读取。
- [ ] 数据库迁移在复制数据根验证中断、幂等和回滚。
- [ ] 更新失败不会留下半发布 runtime 或破坏当前安装。

### Task 6.4：安装版真实渲染 smoke

- [ ] 安装版运行短项目 preflight/render/package。
- [ ] ffprobe、时长、编码和产物 hash 记录完整。
- [ ] 重启安装版并查询任务终态。
- [ ] 验证卸载只删除安装范围，不删除 workspace-data 和 `F:\Video` 用户产物。

### Task 6.5：恢复演练和最终决策

- [ ] 从 foundation checkpoint 重建源码和安装包。
- [ ] 验证证据 index 的所有引用和 hash。
- [ ] 演练候选失败时恢复上一安装版和上一 foundation ref。
- [ ] 更新限制、feature flags、升级说明和回滚说明。
- [ ] 获得明确批准后才把状态改为 RELEASE_READY。

**Gate G6-G7 / RELEASE_READY:** 构建、安装、首次启动、修复、升级、回滚、卸载边界和安装版渲染全部通过。

## Phase 7：推广 Foundation 与后续隔离开发

### Task 7.1：发布 foundation handoff

- [ ] 发布 foundation commit/ref、Foundation ID、snapshot hash 和证据索引。
- [ ] 记录根恢复目录仍保留的排除项，不误报 clean。
- [ ] 为每个下游项目给出允许起点、最低 gate 和禁止修改范围。
- [ ] 将旧冻结验收标为历史回归基准，不与新证据混记。
- [ ] 保留恢复地图和 checkpoint，不删除恢复资产。

### Task 7.2：创建下游 worktree

**Depends on:** FOUNDATION_READY；按用户安排逐个创建，不在本计划中自动执行。

- [ ] `codex/rendergraph-v2`：编译器、preflight、执行器。
- [ ] `codex/p1-assets-materials`：素材和材料，可按责任再拆分。
- [ ] `codex/p1-subtitles-continuity`：字幕、转场、连续镜头和覆盖层。
- [ ] `codex/p1-export-scheduler`：多规格导出和批量调度。
- [ ] `codex/p2-platform-foundation`：Provider/Platform/Cloud 公共契约。
- [ ] 每个 worktree 登记 owner、路径责任、共享文件禁区和合并顺序。

### Task 7.3：建立持续集成规则

- [ ] PR/合并请求必须声明 foundation commit 和受影响 gate。
- [ ] 共享文件修改必须由 integration owner 批准。
- [ ] feature flag 默认关闭，新主链只在相应放行等级后启用。
- [ ] 每次主线集成创建新 snapshot，不能继承旧 snapshot 的通过状态。
- [ ] 发布候选必须达到 RELEASE_READY，不允许从功能 worktree 直接打包。

## 5. 逐项验收矩阵

| ID  | 验收项              | 必须证据                            | 失败处理              |
| --- | ------------------- | ----------------------------------- | --------------------- |
| G0  | 四边界和只读盘点    | boundary manifest、前后 status hash | 停止，不写根目录      |
| G1  | 所有窗口停点        | stop points、静默期双 hash          | 等待或迁移 writer     |
| G2  | 文件归属和冲突      | ownership map、逐文件决议           | 不自动合并            |
| G3  | checkpoint/snapshot | 重建记录、manifest SHA-256          | 创建新候选            |
| G4  | Foundation 质量     | 全量命令、版本、退出码、日志        | 修复后重新冻结        |
| G5  | 真实渲染            | 8/50 页、真人、竖屏、质量、重启证据 | 保留 V1，禁止主链切换 |
| G6  | Windows 发布        | build/installer/runtime manifests   | 不触碰现有安装        |
| G7  | 升级回滚和恢复      | 安装版 smoke、回滚、重建记录        | 不推广候选            |

## 6. 建议提交序列

1. `docs: design shared foundation freeze`
2. `test: define foundation freeze contracts`
3. `feat: add read-only foundation inventory`
4. `feat: collect window stop points and ownership map`
5. `feat: create reproducible foundation checkpoints`
6. `feat: run content-addressed foundation gates`
7. `test: validate isolated render and release acceptance`
8. `chore: promote trusted foundation baseline`

每个提交只包含自己的责任文件。真实 checkpoint 提交必须等待所有活动窗口确认，不能仅因为计划写完就创建。

## 7. 完成定义

- [ ] G0-G7 全部通过并有同一候选链上的证据。
- [ ] 唯一 foundation commit/ref 和 Foundation ID 可重建。
- [ ] 四个边界未被越权修改。
- [ ] 根目录所有正式状态项来源明确，未知来源为 0。
- [ ] 已验收旧转视频链没有回退。
- [ ] 8 页、50 页、真人、竖屏和质量样本均有真实证据。
- [ ] Windows 构建、安装、修复、升级和回滚完成隔离验收。
- [ ] 后续 P1/P2/RenderGraph worktree 起点、责任和门禁明确。
- [ ] `F:\app\app` 是否更新仍由用户单独决定。

## 8. 当前安全继续点

在其他窗口仍可能开发的情况下，本项目当前只执行 Phase 0 的文档和只读盘点。下一次安全推进顺序为：

1. 获取所有 writer 的 stop point。
2. 确认短静默窗口。
3. 生成 ownership map，只处理归属，不清理文件。
4. 解决共享文件冲突并创建候选 checkpoint。
5. 在重建目录生成冻结 snapshot。
6. 所有门禁只在 snapshot 上运行。

如果任一步发现其他窗口仍在写入，退回 `WAITING_FOR_STOPPOINTS`，不影响其继续开发，也不把不完整结果当作前置项目完成。
