# PPT Video Workbench V1.0 生产收口逐项实施计划

> 本计划按严格依赖顺序执行。任何任务未满足前置 Gate 时，不进入下一阶段；专项准备可以并行，但不得修改尚未冻结的共享契约。

**Goal:** 从当前恢复工作树形成一个干净、可重建、经过真实 Windows 全链路验收并完成签署的 V1.0 候选。

**Design:** `docs/superpowers/specs/2026-08-11-v1-production-closure-design.md`

**Audit baseline:** `recovery/root-snapshot-20260810@117fb60cbb0ca877c0920a26f5ceb31d8e42e901`

## 1. 总体顺序

| Phase | 内容                              | 前置       | Gate                   |
| ----- | --------------------------------- | ---------- | ---------------------- |
| 0     | 状态盘点、所有权和源码冻结        | 当前恢复根 | G0 SOURCE_READY        |
| 1     | 当前红灯、契约、迁移和 Job 底座   | G0         | G1 FOUNDATION_READY    |
| 2     | RenderGraph V2 真实执行闭环       | G1         | G2 GRAPH_READY         |
| 3     | P1 七项生产工作台                 | G2         | G3 WORKBENCH_READY     |
| 4     | 质量、更新和 PPT 高保真           | G3         | G4 CAPABILITIES_READY  |
| 5     | Effects、Presenter 和 P03-P12     | G4         | G5 FEATURE_GATES_READY |
| 6     | clean 集成、完整 CI 和冻结 RC     | G5         | G6 RC_READY            |
| 7     | Windows A0-A9、真实媒体和人工验收 | G6         | G7 WINDOWS_ACCEPTED    |
| 8     | 缺陷关闭、签署、冻结和发布        | G7         | G8 RELEASE_READY       |

## 2. 全局执行规则

- [ ] 不在共享 dirty root 直接开发新功能或构建正式 RC。
- [ ] 不执行 `git reset --hard`、`git clean`、历史重写或覆盖式目录复制。
- [ ] 不删除来源不明的 tracked/untracked 文件、恢复包或用户工件。
- [ ] 测试使用唯一临时 workspace、数据库、端口、缓存和输出目录。
- [ ] shared paths 只由当期 integration/foundation owner 修改。
- [ ] 每个任务先写失败测试或非法 fixture，再实现或修正文档。
- [ ] 每个提交只包含一个可审查目的；生成物和源码分开。
- [ ] 每个 Gate 生成 stop point、证据清单和明确回退方法。
- [ ] feature flag 默认关闭；关闭时旧流程和旧输出保持兼容。
- [ ] 跳过、重试、超时和外部依赖失败不得记录为通过。

## Phase 0：状态盘点、所有权和源码冻结

### T00：刷新当前事实

- [x] 记录根目录 branch、HEAD、tracked/untracked/unmerged 数量。
- [x] 记录全部 worktree 的路径、分支、HEAD、dirty 状态和 owner。
- [x] 记录 Python/Web/Remotion 当前首轮结果和精确失败测试。
- [x] 记录 M8、Effects、Presenter、S1、P2 和 Windows 报告状态。
- [x] 记录现有 installer、runtime、RC manifest 和 evidence manifest 的候选身份。
- [x] 标记所有旧于当前 HEAD 或候选不一致的报告为 stale。

**产物：** `docs/acceptance/v1-closure/current-state-<run-id>.json`。

### T01：分类工作树内容

- [x] 将文件分为 source、contract、migration、test、doc、generated、cache、release、backup、user-data 和 unknown。
- [x] 对全部 tracked 修改逐文件登记来源和意图。
- [x] 对全部 untracked 条目确认保留、忽略、归档或纳入候选；不直接删除。
- [x] 将 zip、日志、安装包、备份和临时目录标记为排除出源码提交。
- [x] 检查 `.gitignore` 是否覆盖新生成目录，同时不隐藏必需证据。
- [x] 执行 secret、大文件、绝对路径和用户数据扫描。

### T02：冻结所有权和停点

- [x] 为 domain、storage、jobs、main、OpenAPI、Web client、WorkflowShell、Remotion Root、installer 和 launcher 指定唯一 owner。
- [x] 收集每个活动 worktree 的 owned paths、shared paths、completed、remaining 和 safe resume。
- [x] 未知源码所有权降为 0。
- [x] 对重叠修改逐段审查，不按最后修改时间裁决。
- [x] 形成 foundation ownership map 和 stop point schema 校验。

### T03：建立可信 checkpoint

- [x] 按领域创建小型 checkpoint commits，不混入 release/cache/backup。
- [x] 在新的隔离目录重建 checkpoint。
- [x] 核对 tracked 文件清单、schema hash、lock hash 和 source fingerprint。
- [x] 运行最小 contract/import smoke，证明 checkpoint 可加载。
- [x] 创建 `FOUNDATION_SOURCE_READY` stop point。

**Gate G0 / SOURCE_READY**

- [x] 无 unmerged 文件。
- [x] 未知源码 owner 为 0。
- [x] checkpoint 可在隔离目录重建。
- [x] 用户数据、历史成片和其他 worktree 未被修改。

## Phase 1：当前红灯、契约、迁移和 Job 底座

### T10：关闭当前自动化红灯

- [x] 生成并审查 Project Schema 差异；确认代码还是提交快照为权威。
- [x] 同步 `packages/contracts/project.schema.json` 并保留兼容测试。
- [x] 生成并审查 OpenAPI 差异；拒绝无意外路由/字段漂移。
- [x] 修复 Job detail 的 attempt 创建时序或测试预期，定义 enqueue/claim 的正式语义。
- [x] 修复 packaged desktop CLI 的 uvicorn 入口契约。
- [x] 运行失败测试各 3 次独立进程，确认不是顺序污染。

### T11：冻结共享契约

- [x] Python、TypeScript、JSON Schema 和 OpenAPI 枚举/字段镜像。
- [x] RenderGraph、Asset、Job、Subtitle、Quality、Provider 引用使用版本字段。
- [x] 所有外部模型 `extra=forbid` 或明确兼容策略。
- [x] 生成 golden fixtures 并验证跨语言序列化一致。
- [x] 更新 API client，不手写与 OpenAPI 冲突的影子类型。

### T12：数据库和旧项目迁移

- [x] 覆盖 v1/v2/v3 数据库和项目 fixture。
- [x] 测试迁移重复运行、中断、损坏行、部分 schema 和文件缺失。
- [x] 数据库成功但文件缺失时标记 corrupted，不静默重建或复用。
- [x] migration 失败进入只读诊断；禁止自动重建正式数据库。
- [x] 旧项目来源零写入，迁移只作用于隔离副本。

### T13：Job v3 与 exactly-once publication

- [x] 状态变更使用 expected revision/attempt generation CAS。
- [x] 旧 attempt 不能完成、失败或发布新 attempt。
- [x] pause 只在 checkpoint 提交后完成。
- [x] cancel 只清理当前 operation 声明的临时文件。
- [x] reservation → verify → publish → complete 各阶段做崩溃注入。
- [x] rename 前后崩溃均可对账恢复。
- [x] publication 与磁盘不一致进入 quarantined/corrupted。
- [x] 付费任务未知结果进入人工确认，不自动重提。

### T14：资源租约、缓存和 GC

- [ ] Worker capability、heartbeat、lease acquire/renew/release/reclaim。
- [ ] CPU/GPU/内存/磁盘/Office/网络资源有稳定等待原因。
- [ ] 缓存键包含输入 hash、graph hash、参数、工具和平台能力。
- [ ] 反向依赖仅失效 affected ranges。
- [ ] GC 白名单保护源文件、正式输出、当前 checkpoint 和上一成功成片。
- [ ] GC 不阻塞编辑、预览或关键事务。

### T15：G1 全量门禁

- [ ] `.venv\Scripts\python.exe -m pytest` 首轮零失败。
- [ ] `uv run ruff check apps tests scripts` 通过。
- [ ] `uv run mypy apps/api/src` 通过。
- [ ] Web lint、typecheck、Vitest、build 通过。
- [ ] Remotion typecheck、Vitest、build 通过。
- [ ] contract、migration、security、release 子集单独通过。
- [ ] 保存命令、退出码、版本、测试数、日志和 hash。

**Gate G1 / FOUNDATION_READY**

- [ ] Schema/OpenAPI/migration 无漂移。
- [ ] Job/Attempt/Checkpoint/Lease/Publication 真相一致。
- [ ] 全量自动化首轮全绿。
- [ ] 形成 clean foundation commit 和 stop point。

## Phase 2：RenderGraph V2 真实执行闭环

### T20：统一 timebase 和 snapshot

- [ ] Python/TypeScript 共用 24/25/30/60fps golden fixtures。
- [ ] 覆盖 16:9、9:16、1:1 和 720p/1080p/4K frame math。
- [ ] 时间统一使用整数微秒，无双重舍入。
- [ ] snapshot 包含 project revision、graph hash、asset hashes 和 runtime fingerprint。

### T21：权威预览任务

- [ ] `render_preview` 冻结 graph/range/preset/runtime。
- [ ] 生成 video/audio/subtitle proxy 和 preview manifest。
- [ ] 支持 pause、cancel、restart、cache hit 和 stale graph。
- [ ] cache key 相同只发布一次。
- [ ] 前端显示 loading/empty/error/stale/blocked/degraded/retry。

### T22：LegacyProjectAdapter 和失效矩阵

- [ ] 旧项目只读投影 Timeline/RenderGraph。
- [ ] 无 V2 独占语义时允许显式安全 fallback。
- [ ] V2 项目关闭能力时明确失败，不静默改走 V1。
- [ ] 字幕、音频、overlay、transition、画幅修改分别验证 affected ranges。
- [ ] soft subtitle 和 J/L Cut 避免不必要的视频层重渲。

### T23：真实媒体和入队前预检

- [ ] 素材 project ownership、授权、hash、size 和媒体元数据校验。
- [ ] 检测素材/字体缺失、时长越界、非法重叠和字幕越界。
- [ ] transition、overlay、字幕和 J/L Cut 使用关键帧/波形 oracle。
- [ ] soft/burn-in/both/none 用 ffprobe 验证流。
- [ ] Windows packaged Node/Chromium/Remotion/FFmpeg smoke 通过。

### T24：V2 灰度

- [ ] contract-only 和 compile-only 无旧流程回归。
- [ ] preview-only 绑定 graph hash 并显示来源 revision。
- [ ] internal export 仅对白名单项目开放。
- [ ] 记录性能、失败率、fallback 和成片差异。
- [ ] 未通过真实证据前不切换新项目默认值。

**Gate G2 / GRAPH_READY**

- [ ] 第 6 步预览和第 7 步渲染绑定相同 graph hash。
- [ ] 真实媒体、ffprobe、缓存失效和 packaged runtime 通过。
- [ ] V1 兼容路径保持可用。

## Phase 3：P1 七项生产工作台

### T30：时间线编辑器

- [ ] 实现 clip 选择、拖动、裁剪、分割、吸附、ripple、链接和 marker。
- [ ] 撤销/重做、revision history、冲突重放和原子 batch command。
- [ ] Presenter、字幕、特效、音乐和 overlay 使用同一时间轴。
- [ ] 1000 clips/30 分钟项目虚拟化；拖动预算目标 16 ms。

### T31：素材库

- [ ] 批量导入安全检查、内容 hash 去重和对象存储。
- [ ] 真实缩略图、视频代理、波形、裁剪和转码派生任务。
- [ ] 授权、来源、字体、LUT、品牌包和项目隔离。
- [ ] H.264/H.265/VP9、PNG/SVG、长视频、WAV/MP3/AAC fixtures。
- [ ] AssetLibrary 正式接入七步工作流和时间线插入。

### T32：材料组织

- [ ] 多文档、多课件、角色、顺序、启用和解析状态。
- [ ] 无大纲、章节合并/拆分/重排/禁用。
- [ ] 页面替换、差异预览和人工锁定。
- [ ] P03/P04 复用 MaterialCollection/AssetRef。
- [ ] 同步时间线是可撤销的显式命令。

### T33：高级字幕

- [ ] 词级时间、分割/合并/微调、双语、术语表和译文确认。
- [ ] 样式模板、逐词高亮、软/烧录/both/none。
- [ ] Remotion 和 FFmpeg 读取同一 SubtitleDocument revision。
- [ ] 输入法、键盘、无障碍和大量 cue 虚拟化。

### T34：连续镜头和 Overlay

- [ ] TransitionPlan 和跨页重叠时长语义。
- [ ] J/L Cut 使用 20 ms waveform 验证。
- [ ] dissolve/wipe/slide/match 和章节 continuity。
- [ ] image/video/logo overlay 的 z-order、alpha、裁剪和安全区。
- [ ] 横屏、竖屏和方屏关键帧回归。

### T35：多规格导出

- [ ] 720p/1080p/4K、24/25/30/60fps、多画幅。
- [ ] H.264/H.265/VP9/AV1 按 runtime capability 开放。
- [ ] GIF、短视频切片、章节、软字幕和制作包。
- [ ] 每个 preset 独立进度、错误和产物。
- [ ] 每个结果写入 graph、policy、candidate 和 artifact hashes。

### T36：批量生产

- [ ] BatchPlan/Item DAG、优先级、失败策略和夜间窗口。
- [ ] 多 Worker 公平派发和资源 lease。
- [ ] 页面级失败重跑与缓存复用。
- [ ] 重启恢复、lease 回收和 exactly-once publication。
- [ ] 20 项目批次的资源、暂停、恢复和数据保留验收。

**Gate G3 / WORKBENCH_READY**

- [ ] 七项能力在 Web、API、RenderGraph 和真实媒体中闭环。
- [ ] 旧项目可只读打开并安全迁移。
- [ ] 每项成熟度和 feature flag 明确。

## Phase 4：质量、更新和 PPT 高保真

### T40：质量检测生产门禁

- [ ] 建立损坏、无流、黑帧、冻结、静音、字幕越界和音画漂移 corpus。
- [ ] strict/standard/fast 策略版本化；P0 不可关闭。
- [ ] P0/P1 召回率目标 100%，正常样本 P0/P1 误报为 0。
- [ ] QualityJob 绑定 graph、policy 和候选 MP4 hash。
- [ ] 安全重试、人工确认和豁免可审计。

### T41：安全更新生产闭环

- [ ] 配置正式 Ed25519 trust root、threshold、expiry 和 anti-rollback。
- [ ] HTTPS metadata、断点下载、hash/size/disk budget 和内容缓存。
- [ ] 安全解包、独立 helper、参数约束和 runtime manifest。
- [ ] 启动健康检查、migration journal、自动回滚和状态 marker。
- [ ] 密钥轮换、恶意包、路径逃逸、重放和中间人测试。
- [ ] 修复安装、升级、回滚和签名/SmartScreen 证据。

### T42：PPT 高保真生产闭环

- [ ] OOXML 能力扫描和恶意 PPTX corpus。
- [ ] SlideScene、MotionCueSet 和元素动画映射。
- [ ] Office/LibreOffice/F0 能力矩阵和明确降级。
- [ ] 原生 PowerPoint 捕获、页面 MP4/hash/environment。
- [ ] Fidelity Resolver、缓存、任务恢复和时间线接入。
- [ ] 60 页 corpus、人工视觉和性能门禁。

**Gate G4 / CAPABILITIES_READY**

- [ ] 三项能力都有真实证据、回滚路径和成熟度决策。
- [ ] 无正式密钥/Office/真实 corpus 时保持 internal 或 disabled。

## Phase 5：Effects、Presenter 和 P03-P12

### T50：Effects V2 和模板工作台

- [ ] 核对最后 branch/commit/stop point 和当前主线差异。
- [ ] 草稿、revision、自动保存、冲突恢复和不可变发布。
- [ ] 模板创建、复制、校验、发布、弃用、归档和回滚。
- [ ] `.pvtmpl` 安全导入/导出和 quarantine。
- [ ] 真实 30 页、Windows 安装版、重启、最终导出和人工视觉。
- [ ] 关闭 flag 后旧链完整回滚。

### T51：Presenter 正式验收

- [ ] 5–8 分钟和 15–20 分钟私有样本。
- [ ] 真实 ASR、页面匹配、锚点人工修正和 revision 锁。
- [ ] 字幕/特效碰撞、单一主音频和 fallback。
- [ ] 强杀恢复、长视频性能和缓存失效。
- [ ] Windows 人工音画同步和 P0/P1/P2 签署。

### T52：P03-P12 生产链

- [ ] S1 Job 通过 Job v3 adapter，不复制状态机。
- [ ] P03-P06 复用 MaterialCollection/AssetRef/Narration revision。
- [ ] P07 本地录音与 HeyGen 互斥；保存 request ID、费用和未知状态。
- [ ] P08 复用 SubtitleDocument。
- [ ] P09 只使用已发布 EffectPlan/template revision。
- [ ] P10 汇总 graph、素材、Presenter、效果、质量和交付阻断。
- [ ] P11 frozen graph、分页渲染、失败页重跑、FFmpeg 和制作包。
- [ ] P12 质量报告、artifact manifest、双人签署和脱敏归档。
- [ ] 8 页 local/fake-HeyGen/real-HeyGen 小额链和失败恢复。

### T53：专项成熟度决策

- [ ] 每项声明 disabled/internal/stable_optional。
- [ ] 记录默认开关、适用项目、回退条件和观察指标。
- [ ] 自动化不能替代的人工/外部证据明确列为 blocker。
- [ ] S1 acceptance record、Presenter report 和 Effects report 绑定当前 candidate。

**Gate G5 / FEATURE_GATES_READY**

- [ ] Effects、Presenter、S1 均有真实证据或保持关闭。
- [ ] 无真实 HeyGen/人工签署时交付链保持 BLOCK。
- [ ] 所有专项 stop point 可审查且不再写共享文件。

## Phase 6：clean 集成、完整 CI 和冻结 RC

### T60：创建 clean integration worktree

- [ ] 从 G1 clean foundation commit 创建 `codex/v1-release-integration`。
- [ ] 按 G2 → G3 → G4 → G5 顺序逐项目移植。
- [ ] 每次只集成一个提交集合并记录冲突语义。
- [ ] shared paths 由 integration owner 应用最小补丁。
- [ ] 每次集成后运行 contract/migration/受影响回归。

### T61：完整自动化矩阵

- [ ] Python unit/integration/contract/security/release/acceptance 全量。
- [ ] Ruff check/format check 和 strict mypy。
- [ ] Web lint/typecheck/Vitest/build。
- [ ] Remotion typecheck/tests/build/visual snapshots。
- [ ] Playwright 项目生命周期、刷新恢复、暂停取消、旧项目和真实 UI 播放。
- [ ] OpenAPI、migration、installer、runtime manifest、licenses 和 secret scan。
- [ ] CI 禁止 `.only`；新增 `.skip` 必须进入批准清单。
- [ ] 测试数量低于冻结基线时失败。

### T62：构建唯一 RC

- [ ] 记录 candidate ID、Git commit、dirty=false 和 lock hashes。
- [ ] 准备 Node、Chromium/Edge、Remotion、FFmpeg/ffprobe 和 schema runtime。
- [ ] 执行完整 `scripts/build-release.ps1`，不复用历史 staging。
- [ ] 生成并独立验证 `release-artifacts.json`。
- [ ] 生成 runtime manifest、SBOM、许可证、launcher 和 installer hashes。
- [ ] candidate/source/lock/runtime hashes 全部一致。

### T63：RC 自动发布门禁

- [ ] GUI launcher named mutex、二次启动、陈旧状态和 API 恢复测试。
- [ ] active/previous release、激活失败和自动回滚测试。
- [ ] 安装/卸载/重装 contract 与 workspace retention 测试。
- [ ] release tests 全量通过。
- [ ] 保存不可变 G6 evidence manifest。

**Gate G6 / RC_READY**

- [ ] clean integration commit 可重建。
- [ ] 全量自动化首轮全绿。
- [ ] 唯一 RC 及产物清单自校验通过。
- [ ] 后续验收只能消费该 candidate。

## Phase 7：Windows A0-A9、真实媒体和人工验收

### T70：验收环境和数据保护

- [ ] 专用 Windows 11 x64 实机，标准用户权限。
- [ ] 记录机器编号、OS build、系统时间、磁盘、Office 和 runtime capability。
- [ ] 准备候选/baseline artifact manifest。
- [ ] 旧项目来源设为只读并创建隔离副本。
- [ ] evidence root、workspace、端口和日志与正式用户数据隔离。
- [ ] 安装、卸载和回滚获得明确授权。

### T71：执行 A0-A3

- [ ] A0 校验 installer/payload/SBOM/launcher 和 candidate hash。
- [ ] A1 全新安装，验证版本目录、快捷方式、签名和数据分区。
- [ ] A2 首次启动无黑窗；关闭浏览器后快捷方式可重开；二次点击不重复启动 API。
- [ ] A3 打开旧项目副本；核对 ID、页、素材、音频、字幕和受保护 hash。

### T72：执行 A4-A7

- [ ] A4 首个分页 checkpoint 后结束 API；恢复后复用完成页且只发布一个最终结果。
- [ ] A5 fresh 完整预检三次；第二次前重启 API，第三次前重启 launcher。
- [ ] A6 真实 UI 从 0 播放至 ended；记录 stall、console/page error 和资源 4xx/5xx。
- [ ] A7 UI 提交最终导出；验证 H.264/AAC、尺寸、fps、时长、MP4 和制作包 hash。

### T73：执行 A8-A9

- [ ] A8 卸载，确认程序移除、workspace 保留；重装同 RC 并复开项目。
- [ ] A9 baseline → candidate → baseline 回滚；核对 active/previous 指针和项目兼容。
- [ ] 进程树、端口和临时文件无残留。
- [ ] workspace retention marker 和受保护媒体 hash 不变。

### T74：真实项目矩阵

- [ ] Word+PPTX+本地录音完整链。
- [ ] Word+扫描 PDF，OCR 低置信度定位和人工修正。
- [ ] 多图片自然排序和手工调整。
- [ ] 受控 2 页真实 HeyGen，记录费用、缓存和不重复计费。
- [ ] Presenter 5–8/15–20 分钟样本。
- [ ] Effects V2 30 页、9:16 和 1:1 安全区。
- [ ] 8 页标准、50/60 页压力和 20 项目批次。

### T75：人工视听和异常矩阵

- [ ] 检查开头/中段/结尾的画面、旁白、字幕和转场。
- [ ] 检查错页、裁切、遮挡、黑帧、冻结、静音、爆音和音画漂移。
- [ ] 强杀 API、Worker、Remotion、FFmpeg、Office 和浏览器。
- [ ] 模拟磁盘满、数据库锁、文件锁、断网、429、超时和睡眠唤醒。
- [ ] 验证上一成功成片在失败和回滚后仍可用。

**Gate G7 / WINDOWS_ACCEPTED**

- [ ] A0-A9 在同一 run/candidate 连续通过。
- [ ] 真实输入、外部服务和人工视听完成适用门禁。
- [ ] process cleanup、workspace retention 和 rollback 无 blocker。
- [ ] schema 2.0 Windows 报告及 evidence manifest 完整。

## Phase 8：缺陷关闭、签署、冻结和发布

### T80：缺陷清零

- [ ] 汇总自动化、Windows、媒体、人工和安全问题。
- [ ] P0/P1 修复并在同一候选或新唯一候选上完整回归。
- [ ] P2/P3 记录 owner、影响、规避、计划版本和用户可见说明。
- [ ] 新候选产生时废止旧候选证据，不混用 hash。

### T81：更新追踪与文档

- [ ] FR/NFR → 测试 → 证据 → 缺陷 → 签署无空缺。
- [ ] 更新用户指南、排障、迁移、备份、卸载和回滚说明。
- [ ] 更新 feature flags、默认值和已知限制。
- [ ] 更新 release notes、SBOM、许可证和签名状态。
- [ ] 重写根 README 为当前产品、开发、构建和验收入口。

### T82：正式签署

- [ ] 产品签署核心场景和范围。
- [ ] 工程签署源码、构建、迁移和恢复。
- [ ] 安全签署输入、凭证、更新、安装包和证据脱敏。
- [ ] Windows 操作员签署 A0-A9。
- [ ] 视听复核签署成片、字幕、旁白和 Presenter/Effects 适用项。
- [ ] 所有签署绑定 candidate、artifact manifest 和 evidence manifest hash。

### T83：冻结和发布

- [ ] `freeze-release.ps1` 强制消费当前 schema 2.0 Windows 报告。
- [ ] 验证报告未过期、机器批准、blockers 为空、引用 hash 正确。
- [ ] 创建正式 tag 和不可变发布记录。
- [ ] 发布安装包、校验文件、release notes、SBOM 和许可证。
- [ ] 保留上一稳定版本、回滚手册和发布后观察窗口。

**Gate G8 / RELEASE_READY**

- [ ] P0=0、P1=0。
- [ ] clean source、RC、Windows 报告和签署指向同一 candidate。
- [ ] 所有默认启用能力有真实证据和回退路径。
- [ ] P2/Cloud 等未完成能力明确 disabled/beta。
- [ ] V1.0 可发布且可安全回滚。

## 3. 每个任务的固定交付物

- [ ] 任务 ID、owner、branch/worktree 和起始 HEAD。
- [ ] owned paths、shared paths 和冲突说明。
- [ ] 设计偏差及原因。
- [ ] schema、migration、API、flags 和数据兼容清单。
- [ ] 失败测试、实现提交和定向回归。
- [ ] 完整命令、版本、测试数、退出码、日志和 hash。
- [ ] 真实媒体、性能、恢复或人工证据（如适用）。
- [ ] 已知失败、外部阻断和下一安全步骤。
- [ ] 回退方法和数据保护说明。
- [ ] stop point JSON，`will_write_again=false`。

## 4. 推荐证据目录

```text
docs/acceptance/v1-closure/<gate>/<run-id>/
├─ run.json
├─ environment.json
├─ source-manifest.json
├─ test-results.json
├─ evidence-manifest.json
├─ logs/
├─ reports/
├─ screenshots/
└─ media-probes/
```

Windows 大型视频可以外置，但 evidence manifest 必须保存批准位置、大小、SHA-256 和媒体类型。任何 token、Authorization、Cookie、API key、用户名、绝对工作区路径或项目正文进入通用证据时必须脱敏。

## 5. 最终验收清单

- [ ] 源码来源和所有权清楚，未知源码为 0。
- [ ] 全量自动化首轮通过，无未解释 skip。
- [ ] Schema、OpenAPI、migration 和跨语言合同一致。
- [ ] Job v3、缓存和原子发布通过故障注入。
- [ ] 预览、渲染、质量和制作包绑定同一 graph hash。
- [ ] 七项 P1 的声明成熟度与真实实现一致。
- [ ] Quality、Update、Fidelity 有生产证据或保持关闭。
- [ ] Effects、Presenter、P03-P12 有真实证据或保持阻断。
- [ ] 唯一 RC 从 clean commit 构建且产物清单可验证。
- [ ] Windows A0-A9、真实媒体、异常恢复和人工视听通过。
- [ ] 卸载、升级、失败和回滚不破坏项目或上一成功成片。
- [ ] P0/P1 为 0，产品/工程/安全/Windows/视听签署完成。
- [ ] 发布冻结仅接受当前 candidate 的完整报告。
