# PPT Video Workbench V1.0 非干扰式逐项实施计划

> 本计划按严格依赖顺序执行。默认连续推进，不在项目之间等待确认；涉及真实付费 Provider、正式签名证书、系统级安装/卸载、版本回滚或专用 Windows 验收窗口时，必须满足相应授权和 Gate。

**Goal:** 在不控制、不停止、不复用其他窗口程序和用户数据的前提下，先完成 clean source、逐层集成和唯一 RC，再在专用 Windows 窗口完成真实验收、签署和 V1.0 发布。

**Design:** `docs/superpowers/specs/2026-08-11-non-interference-v1-closure-design.md`

**Current baseline:** `recovery/root-snapshot-20260810@e81b455c4903889ac25697a4a030e523adb7650f`

## 1. 执行规则

- [ ] 开始任何任务前记录 branch、HEAD、dirty 状态和现有 worktree。
- [ ] recovery root 只作为受保护来源，不执行 reset、clean、批量 checkout 或覆盖式复制。
- [ ] 每项开发在指定独立 worktree 中进行。
- [ ] 每项测试使用独立 workspace、数据库、cache、端口、日志和输出。
- [ ] 不按进程名批量停止 Node、Python、Edge、Office、FFmpeg 或 Workbench。
- [ ] 只清理当前 run 明确记录的 PID、端口和临时目录。
- [ ] shared paths 只由 Foundation 或 Integration owner 修改。
- [ ] 每项任务先添加失败测试、非法 fixture 或 drift check，再实现。
- [ ] 源码、格式化、生成物和验收证据分开提交。
- [ ] 跳过、超时、重试后通过和后台仍运行不得记录为首轮全绿。
- [ ] 每个 Gate 生成 evidence manifest、stop point 和回退方法。
- [ ] 真实费用、正式签名和外部生产资源必须单独授权。

## 2. 隔离资源约定

| Line               | 建议 worktree                       |    端口范围 | 运行等级 |
| ------------------ | ----------------------------------- | ----------: | -------- |
| Foundation         | `.worktrees/v1-foundation-closure`  | 18100-18119 | N0-N2    |
| Core               | `.worktrees/v1-core-workbench`      | 18120-18139 | N0-N2    |
| Render             | `.worktrees/v1-render-release`      | 18140-18159 | N0-N2    |
| Platform           | `.worktrees/v1-platform-disabled`   | 18160-18179 | N0-N2    |
| Integration        | `.worktrees/v1-release-integration` | 18180-18199 | N0-N2    |
| Windows acceptance | 外部专用 evidence/workspace root    | 按 run 登记 | N3       |

每个任务的临时目录采用：

```text
<worktree>/.test-v1/<task-id>/<run-id>/
  workspace/
  cache/
  logs/
  output/
  browser-profile/
  evidence/
  process-context.json
```

# Phase 0：当前事实与受保护来源

## N00：刷新当前状态

**等级：** N0

- [ ] 记录 root branch、HEAD、tracked/untracked/unmerged 数量。
- [ ] 记录全部 worktree 的 path、branch、HEAD 和 dirty 状态。
- [ ] 验证 B01 `1bef208`、B02 `fc41bdf`、C00 `51cc325` 可解析。
- [ ] 验证 G0 stop point 和引用 hash。
- [ ] 记录现有 installer、release manifest、RC1 evidence 和 sign-off 状态。
- [ ] 标记所有与当前 HEAD/candidate 不一致的报告为 stale。
- [ ] 扫描当前监听端口和相关进程，仅登记、不关闭。

**产物：** `docs/acceptance/v1-non-interference/source/current-state-<run-id>.json`

## N01：冻结来源和所有权

**等级：** N0

- [ ] 按 source、contract、migration、test、doc、generated、cache、release、backup、user-data、unknown 分类。
- [ ] 为全部 tracked 修改登记来源与用途。
- [ ] 为全部 untracked 源码和测试登记 owner。
- [ ] unknown source 降为 0。
- [ ] 建立 shared path owner 表。
- [ ] 确认 recovery root、B01、B02、C00 都停止新增写入。
- [ ] 记录 safe resume 和禁止清理的路径。

**Gate S0 / PROTECTED_SOURCE_READY**

- [ ] 无 unmerged 文件。
- [ ] unknown source 为 0。
- [ ] 所有 active writer 和运行资源有 owner。
- [ ] 未停止或修改其他窗口进程。

# Phase 1：Clean Foundation Source

## N10：创建 Foundation 重建工作树

**等级：** N1

- [ ] 从已确认的恢复基线创建 `codex/v1-foundation-closure`。
- [ ] 核对绝对路径位于本仓库 `.worktrees` 下。
- [ ] 建立独立 test root 和端口登记。
- [ ] 不复制 root 的 `.venv`、`node_modules`、release、cache 或用户数据。
- [ ] 记录起始 HEAD 和 clean status。

## N11：重建 Domain 与错误契约

**等级：** N1

- [ ] 逐文件审查 domain models、enums 和 issues。
- [ ] 冻结 Job、Asset、RenderGraph、Subtitle、Quality、Provider 错误码。
- [ ] 禁止同义重复枚举。
- [ ] 添加 Python/TypeScript/Schema 枚举镜像测试。
- [ ] 提交单一 Domain commit。

## N12：冻结 Project Schema 与 OpenAPI

**等级：** N1

- [ ] 重新生成并审查 Project Schema diff。
- [ ] 重新生成并审查 OpenAPI diff。
- [ ] 建立 Python/TypeScript/JSON golden fixtures。
- [ ] 为 unknown field、旧版本和非法枚举定义兼容策略。
- [ ] 更新 generated client，禁止手写冲突类型。
- [ ] 建立 schema/OpenAPI/client drift gate。
- [ ] 提交单一 Contract commit。

## N13：集成 Migration 和 Legacy Reader

**等级：** N1

- [ ] 按版本审查 migration 单调性。
- [ ] 覆盖重复运行、中断、损坏行、部分 schema 和文件缺失。
- [ ] 旧项目只读扫描，来源零写入。
- [ ] 迁移仅操作隔离副本。
- [ ] V2 pointer 原子发布。
- [ ] rollback 恢复旧 reader 并保留诊断 bundle。
- [ ] 禁止数据库降级 SQL。
- [ ] 提交 Migration commit。

## N14：集成 Durable Job v3

**等级：** N1

- [ ] 接入 Job/Attempt/Checkpoint/Lease/Worker/Publication。
- [ ] expected revision 和 generation CAS。
- [ ] pause 只在 checkpoint 后完成。
- [ ] cancel 只清理本 operation 的临时文件。
- [ ] stale attempt 禁止发布。
- [ ] rename 前后崩溃均可恢复。
- [ ] 付费未知结果进入人工确认。
- [ ] API 和 Web job detail 使用统一状态。
- [ ] 为原 G1 stop point 补齐 foundation baseline HEAD。
- [ ] 提交 Durable Job commit。

## N15：集成 Asset、Probe 和 Derivative

**等级：** N1-N2

- [ ] 接入 AssetRef、对象存储和 project ownership。
- [ ] 接入 FFprobe 结构化媒体探测。
- [ ] 接入图片缩略图、裁剪和格式转换。
- [ ] 接入视频代理、转码和缩略图。
- [ ] 接入 PCM waveform 多分辨率输出。
- [ ] derivative job 使用确定性 identity 和原子 publication。
- [ ] 添加伪扩展名、损坏媒体和路径逃逸 fixture。
- [ ] 提交 Asset Foundation commit。

## N16：集成 Preview、Cache 和 GC

**等级：** N1-N2

- [ ] 接入 frozen preview plan 和 range projection。
- [ ] 接入 authoritative preview durable job。
- [ ] 接入 cache dependency graph 和反向索引。
- [ ] 选择性失效只标记 affected ranges。
- [ ] read lease 和 quarantine-before-delete。
- [ ] GC 保护源文件、正式输出、checkpoint 和上一成功成片。
- [ ] cache hit 不启动完整渲染。
- [ ] 并发 GC 不阻塞编辑和 publication。
- [ ] 提交 Preview/Cache commit。

## N17：Foundation 全量门禁

**等级：** N1

- [ ] Python 全量 pytest 首轮通过。
- [ ] Ruff check 和 format check 通过。
- [ ] strict mypy 通过。
- [ ] Web lint、typecheck、Vitest、build 通过。
- [ ] Remotion typecheck、Vitest、build 通过。
- [ ] contract、migration、security、release 子集通过。
- [ ] secret、大文件、绝对路径和用户数据扫描通过。
- [ ] 在新临时目录从 commit 和锁文件重建。
- [ ] 工作树 clean。
- [ ] 生成 source fingerprint 和 stop point。

**Gate G1 / FOUNDATION_READY**

- [ ] clean `foundation_source_commit` 可解析和重建。
- [ ] Schema/OpenAPI/migration/client drift 为 0。
- [ ] Job、Asset、Preview、Cache 和 Migration 使用统一事实。
- [ ] recovery root 和其他窗口进程未受影响。

# Phase 2：三线创建与基础集成

## N20：创建 Core、Render 和 Platform 工作树

**等级：** N1

- [ ] 从同一 `foundation_source_commit` 创建三线。
- [ ] 核对 branch、HEAD、git-dir 和 clean status。
- [ ] 为每条线建立独立 workspace、cache、port 和 evidence root。
- [ ] 生成资源登记清单。
- [ ] 禁止复制依赖或构建产物。

## N21：RenderGraph V2 选择性接入

**等级：** N1-N2

- [ ] 审查 B01 提交，不整分支合并。
- [ ] 接入 schema、timebase、snapshot、compiler 和 export pipeline。
- [ ] 接入 Remotion composition 和 FFmpeg final mux。
- [ ] 接入 release runtime 目录保持修复。
- [ ] Python/TypeScript 共用 24/25/30/60fps fixtures。
- [ ] 覆盖 16:9、9:16、1:1 和 720p/1080p/4K frame math。
- [ ] V2 feature flag 默认关闭。
- [ ] V1 fallback 在关闭 flag 时保持可用。

## N22：Effects 和 Presenter 扩展边界

**等级：** N1

- [ ] 审查 B02 reconstructed provenance 和冻结索引。
- [ ] 只移植源码、契约和测试，不移植 installer 或静态生成物。
- [ ] Effects/Presenter 使用统一 Timeline 和 RenderGraph adapter。
- [ ] 更新 production package provenance。
- [ ] 关闭 flag 时不写新状态、不改变旧输出。
- [ ] 原提交/原 ZIP 缺失保持显式 provenance，不伪造来源。

## N23：P2 默认关闭能力选择性接入

**等级：** N1

- [ ] 审查 C00 P2-specific commits/files。
- [ ] 只接入 Provider Kernel、PlatformServices 和 Cloud contract。
- [ ] shared wiring 按新 Foundation API 重写。
- [ ] provider/cloud/platform flags 默认关闭。
- [ ] 关闭时不创建客户端、不访问网络、不产生费用。
- [ ] generated TypeScript client drift 为 0。

## N24：短生命周期 Integration Gate

**等级：** N1-N2

- [ ] 从 Foundation 创建 `codex/v1-release-integration`。
- [ ] 按 Foundation→Render→Effects/Presenter→Platform 顺序集成。
- [ ] 每次只应用一个提交集合。
- [ ] 每次运行 contract、migration 和受影响回归。
- [ ] shared path 冲突逐行解决，不使用整文件 ours/theirs。
- [ ] 完成全量 Python/Web/Remotion。
- [ ] 工作树 clean 并记录可回退提交。

**Gate G2 / GRAPH_AND_INTEGRATION_READY**

- [ ] Preview、Export、Quality 和 Package 绑定 graph lineage。
- [ ] V1 fallback 可用。
- [ ] P2 默认关闭且离线。
- [ ] 集成提交 clean、可重建。

# Phase 3：Core Workbench 七项生产能力

## N30：Web 生产状态和 Task Center

**等级：** N1-N2

- [ ] 分离 server truth、selection、viewport、playhead、pending command 和 conflict。
- [ ] 使用 revision/CAS 提交命令。
- [ ] 冲突后保留可重放 payload。
- [ ] Task Center 展示 Job、attempt、checkpoint、lease 和 publication。
- [ ] 支持 pause/resume/cancel/retry。
- [ ] 付费未知任务禁止自动重提。
- [ ] 权威预览展示 stale/queued/running/ready/degraded/failed。
- [ ] 覆盖刷新恢复、双标签冲突、键盘和无障碍。

## N31：统一多轨时间线

**等级：** N1-N2

- [ ] 1000 clips 虚拟化轨道。
- [ ] 选择、拖动、裁剪、分割、ripple、多选和锁轨。
- [ ] 帧、边界、marker 和相邻 clip 吸附。
- [ ] 服务端 history、撤销重做和冲突重放。
- [ ] 波形、缩略图和代理视口预取。
- [ ] Presenter、字幕、Effects、音乐和 Overlay 共用时间轴。
- [ ] 平移缩放 p95 < 50 ms。
- [ ] 拖动主线程预算目标 16 ms。

## N32：素材库和材料组织

**等级：** N1-N2

- [ ] 批量导入、进度、去重、损坏媒体和失败恢复。
- [ ] 搜索、标签、类型、授权、来源、品牌包和字体治理。
- [ ] 代理、缩略图、波形和派生状态 UI。
- [ ] 无大纲、多文档、多课件和混合输入。
- [ ] 章节合并、拆分、排序、禁用和页面替换。
- [ ] 页面差异预览和人工锁定。
- [ ] MaterialCollection→Timeline 使用可撤销 sync command。

## N33：高级字幕工作台

**等级：** N1-N2

- [ ] cue/word 编辑、合并、拆分、平移和人工断句。
- [ ] 双语对齐、术语表、翻译 revision 和人工确认。
- [ ] 样式模板、逐词高亮、字体授权和安全区。
- [ ] burn-in/soft/both/none 单一真相。
- [ ] SRT/WebVTT/ASS 和 MP4 多语言 metadata。
- [ ] IME、键盘、无障碍和大量 cue 性能。

## N34：Continuity 和 Overlay

**等级：** N1-N2

- [ ] TransitionPlan 和视觉 overlap 时长语义。
- [ ] J/L Cut 和 waveform oracle。
- [ ] dissolve/wipe/slide/match。
- [ ] image/video/logo/text Overlay 属性。
- [ ] z-index、mask、opacity、enter/exit。
- [ ] 横屏、竖屏、方屏安全区。
- [ ] 与 Presenter/字幕共用 revision。

## N35：多规格导出

**等级：** N1-N2

- [ ] 720p/1080p/4K。
- [ ] 24/25/30/60fps。
- [ ] 16:9/9:16/1:1。
- [ ] H.264/H.265/VP9/AV1 capability gate。
- [ ] GIF、切片、章节、软字幕和制作包。
- [ ] 多 preset 共享中间产物但独立 publication。
- [ ] FFprobe 验证画布、fps、时长、音频和字幕。

## N36：批量生产与资源调度

**等级：** N1-N2

- [ ] BatchPlan/BatchItem DAG 入库。
- [ ] capability registry 和资源 lease。
- [ ] 公平优先级、项目并发和夜间队列。
- [ ] Worker heartbeat、续租、回收和稳定等待原因。
- [ ] 页面级重跑、缓存复用和 exactly-once publication。
- [ ] 重启恢复和 lease 回收。
- [ ] 20 项目模拟批次通过。

**Gate G3 / WORKBENCH_READY**

- [ ] 七项能力使用统一 Job、Asset、Timeline、Graph、Cache 和 Publication。
- [ ] 旧项目可只读打开、迁移和回滚。
- [ ] 性能、无障碍、冲突和恢复门禁通过。
- [ ] 每项成熟度和 feature flag 明确。

# Phase 4：质量、安全更新和 PPT 高保真

## N40：真实媒体自动验收平台

**等级：** N1-N2

- [ ] 定义 ProductionMediaFixture V1。
- [ ] 建立确定性 PPTX、PDF、扫描 PDF、图片、音频、视频和字幕 fixture。
- [ ] 建立 FFprobe、waveform、subtitle、frame 和 hash oracle。
- [ ] 生成损坏、黑帧、静音、爆音、越界和磁盘不足样本。
- [ ] 报告绑定 source、runtime、candidate、fixture 和 artifact hash。

## N41：质量检测生产门禁

**等级：** N1-N2

- [ ] strict/standard/fast 策略版本化。
- [ ] P0 规则不可关闭。
- [ ] P0/P1 坏样本召回目标 100%。
- [ ] 正常样本 P0/P1 误报为 0。
- [ ] QualityJob 绑定 graph、policy 和 candidate MP4 hash。
- [ ] 人工确认、豁免和安全重试可审计。

## N42：安全更新闭环

**等级：** N1；正式签名为 N3

- [ ] 正式 trust root 契约、threshold、expiry 和 anti-rollback。
- [ ] HTTPS metadata、断点下载、hash/size/disk budget。
- [ ] 安全解包、独立 helper 和参数约束。
- [ ] 激活健康检查、migration journal 和自动回滚。
- [ ] 密钥轮换、恶意包、路径逃逸和重放测试。
- [ ] 关闭在线更新时本地工作流无网络访问。

## N43：PPT 高保真闭环

**等级：** N1-N2；真实 Office 为 N3

- [ ] OOXML 安全扫描和恶意 PPTX corpus。
- [ ] SlideScene、MotionCueSet 和元素动画映射。
- [ ] Office/LibreOffice/F0 capability matrix。
- [ ] Fidelity Resolver 和明确降级诊断。
- [ ] 60 页 corpus 和 F0/F1/F2 差异阈值。
- [ ] 缓存、恢复和时间线接入。

**Gate G4 / CAPABILITIES_READY**

- [ ] Quality、Update、Fidelity 有自动化证据。
- [ ] 未完成的真实 Office/签名项保持 internal 或 pending N3。
- [ ] feature flag 关闭路径无回归。

# Phase 5：Effects、Presenter 和 P03-P12

## N50：Effects V2 集成与离线验收

**等级：** N1-N2

- [ ] 接入模板 draft/revision/autosave/conflict recovery。
- [ ] 模板 create/copy/validate/publish/deprecate/archive/rollback。
- [ ] `.pvtmpl` 安全导入导出和 quarantine。
- [ ] 验证 manifest、Ground Truth 和全资产 hash。
- [ ] 30 页静态/contract/视觉回归通过。
- [ ] flag 默认关闭，关闭后旧链完整。
- [ ] 原提交和原 ZIP 缺失保持显式 reconstructed provenance。

## N51：Presenter 离线生产准备

**等级：** N1-N2

- [ ] ASR、页面匹配、锚点修正和 revision lock 契约。
- [ ] PresenterTimeline 与 ProductionTimeline 对齐。
- [ ] 字幕/Effects/Overlay 碰撞规则。
- [ ] 单一主音轨和 fallback。
- [ ] 强杀恢复、缓存失效和长视频预算测试。
- [ ] 真实样本项标记 `pending_exclusive_windows`。

## N52：P03-P12 总接线

**等级：** N1-N2

- [ ] P03-P12 统一通过 Job v3 adapter。
- [ ] P03-P06 复用 MaterialCollection/AssetRef/Narration revision。
- [ ] P07 互斥、request ID、费用和未知状态。
- [ ] P08 复用 SubtitleDocument。
- [ ] P09 只使用已发布 EffectPlan/template revision。
- [ ] P10 汇总所有阻断。
- [ ] P11 frozen graph、分页重跑、FFmpeg 和制作包。
- [ ] P12 质量、artifact manifest、脱敏和双人签署。
- [ ] local/fake Provider 8 页链和失败恢复通过。

## N53：专项成熟度记录

**等级：** N0-N1

- [ ] Effects、Presenter、RenderGraph V2 Export、Update、Fidelity 分别声明成熟度。
- [ ] 记录默认开关、适用项目、观察指标和退出条件。
- [ ] 记录真实证据缺失项和 N3 blocker。
- [ ] 关闭 flag 的回归测试通过。
- [ ] 生成 feature-gate manifest 和 stop point。

**Gate G5 / FEATURE_GATES_READY**

- [ ] 自动化和离线媒体链通过。
- [ ] 无真实证据的能力保持关闭或明确 `pending_exclusive_windows`。
- [ ] 所有专项不再修改共享 Foundation 路径。

# Phase 6：完整 CI、Clean Integration 和唯一 RC

## N60：最终 Integration

**等级：** N1-N2

- [ ] 从当前 Foundation clean commit 重建 integration worktree。
- [ ] 按 Core→Render→Capabilities→Feature Gates→Platform Disabled 顺序接入。
- [ ] 每次只集成一个提交集合。
- [ ] 每次运行 contract、migration 和定向回归。
- [ ] 解决所有 shared path 冲突。
- [ ] 工作树 clean。

## N61：完整自动化矩阵

**等级：** N1-N2

- [ ] Python unit/integration/contract/security/release/acceptance 全量。
- [ ] Ruff check/format check 和 strict mypy。
- [ ] Web lint/typecheck/Vitest/build。
- [ ] Remotion typecheck/tests/build/visual snapshots。
- [ ] Playwright 项目生命周期、刷新恢复、冲突、暂停取消和 UI 播放。
- [ ] OpenAPI、schema、migration 和 generated client drift。
- [ ] installer/runtime/SBOM/license/secret scan。
- [ ] `.only` 禁止、`.skip` 审批和测试数量冻结。
- [ ] 所有命令首轮退出码为 0。
- [ ] 测试结束后无 owned 进程和端口残留。

## N62：版本和发布文档统一

**等级：** N0-N1

- [ ] Python、Web、installer 和 manifest 统一为 `1.0.0`。
- [ ] 重写根 README 为产品、开发、构建和验收入口。
- [ ] 更新用户指南、迁移、备份、卸载和回滚说明。
- [ ] 更新 feature flags 和已知限制。
- [ ] 更新 release notes、SBOM 和许可证状态。
- [ ] 建立 FR/NFR→测试→证据→缺陷→签署矩阵。

## N63：构建唯一 RC

**等级：** N2

- [ ] 从 clean integration HEAD 构建，不复用历史 staging。
- [ ] candidate manifest 记录 `dirty=false`。
- [ ] 记录 commit、lock、schema、runtime 和工具版本。
- [ ] 准备 Node、Chromium/Edge、Remotion、FFmpeg/FFprobe runtime。
- [ ] 运行完整 `scripts/build-release.ps1`。
- [ ] 生成 installer、launcher、runtime manifest、SBOM 和许可证。
- [ ] 生成并独立验证 release artifact manifest。
- [ ] 保存全部 SHA-256。
- [ ] 冻结 candidate；后续代码变化必须创建新 candidate。

## N64：RC 自动发布门禁

**等级：** N2

- [ ] launcher named mutex 和二次启动测试。
- [ ] stale state 和 API 恢复测试。
- [ ] active/previous release 和激活失败回滚。
- [ ] 安装/卸载/重装 contract 的离线验证。
- [ ] release tests 全量通过。
- [ ] freeze-release dry-run 对缺失 Windows 证据保持阻断。
- [ ] 生成不可变 G6 evidence manifest。

**Gate G6 / RC_READY_FOR_WINDOWS**

- [ ] clean integration commit 可重建。
- [ ] 完整自动化首轮全绿。
- [ ] 唯一 `dirty=false` RC 自校验通过。
- [ ] 后续验收只能消费该 candidate。

# Phase 7：专用 Windows 验收窗口

> 本阶段为 N3。开始前必须确认其他窗口没有依赖将被停止的程序，并使用单独 Windows 账户或明确隔离的安装、workspace 和 evidence root。

## N70：验收环境和数据保护

- [ ] 记录机器 ID、Windows build、系统时间、磁盘和 Office。
- [ ] 记录 runtime、GPU、encoder 和网络 capability。
- [ ] 验证 candidate artifact manifest。
- [ ] 旧项目来源设为只读并复制到隔离 workspace。
- [ ] 建立独立端口、日志、浏览器 profile 和 evidence root。
- [ ] 记录安装、卸载和回滚授权。
- [ ] 拍摄开始前进程/端口基线。

## N71：执行 A0-A3

- [ ] A0 验证 installer/payload/SBOM/license/launcher/candidate hash。
- [ ] A1 标准用户全新安装和数据分区。
- [ ] A2 首启、无黑窗、健康、二次点击和浏览器重开。
- [ ] A3 打开旧项目副本，核对页面、素材、音频、字幕和受保护 hash。

## N72：执行 A4-A7

- [ ] A4 checkpoint 后强杀 API，恢复且只发布一次最终结果。
- [ ] A5 fresh preflight 三轮，跨 API/launcher 重启指纹一致。
- [ ] A6 UI 从 0 播放到 ended，无 stall、console/page error 和资源 4xx/5xx。
- [ ] A7 UI 提交最终导出，验证 H.264/AAC、尺寸、fps、时长、MP4 和制作包。

## N73：执行 A8-A9

- [ ] A8 卸载、保留 workspace、重装同 RC 并重新发现项目。
- [ ] A9 baseline→candidate→baseline 回滚。
- [ ] 核对 active/previous pointer 和项目兼容。
- [ ] 进程、端口、文件锁和临时文件无残留。
- [ ] workspace retention marker 和媒体 hash 不变。

## N74：真实输入矩阵

- [ ] Word+PPTX+本地录音完整链。
- [ ] Word+可搜索 PDF。
- [ ] Word+扫描 PDF，OCR 低置信度定位和人工修正。
- [ ] 多图片自然排序和手工调整。
- [ ] 真实 MP3/WAV ASR、分页和字幕。
- [ ] 受控两页真实 HeyGen，记录费用、缓存和幂等。
- [ ] Presenter 5-8 分钟和 15-20 分钟样本。
- [ ] Effects V2 冻结 30 页动态预览、字幕/效果检查和最终导出。
- [ ] 9:16 和 1:1 安全区。
- [ ] 8/30/50/60 页和 20 项目批次适用门禁。

## N75：人工视听与异常矩阵

- [ ] 检查开头、中段、结尾。
- [ ] 检查错页、裁切、遮挡、旁白、字幕和转场。
- [ ] 检查黑帧、冻结、静音、爆音和音画漂移。
- [ ] 强杀 API、Worker、Remotion、FFmpeg、Office 和浏览器。
- [ ] 模拟磁盘满、数据库锁、文件锁、断网、429 和超时。
- [ ] 模拟睡眠唤醒。
- [ ] 失败和回滚后上一成功成片仍可用。
- [ ] 所有发现登记 severity、owner 和 candidate。

**Gate G7 / WINDOWS_ACCEPTED**

- [ ] A0-A9 在同一 run/candidate 连续通过。
- [ ] 真实 ASR、Effects、Presenter 和适用 Provider 证据完成。
- [ ] process cleanup、workspace retention 和 rollback 无 blocker。
- [ ] schema 2.0 Windows report 和 evidence manifest 完整。

# Phase 8：缺陷、签署、冻结和发布

## N80：缺陷清零

**等级：** N0-N2；修复产生新 RC

- [ ] 汇总自动化、Windows、媒体、人工和安全问题。
- [ ] P0 修复并在新唯一 candidate 上全量回归。
- [ ] P1 修复并在新唯一 candidate 上全量回归。
- [ ] P2/P3 记录 owner、影响、规避、计划版本和用户说明。
- [ ] 新 candidate 产生时废止旧 candidate 证据。
- [ ] P0=0、P1=0。

## N81：正式文档和追踪关闭

**等级：** N0

- [ ] FR/NFR→测试→证据→缺陷→签署无空缺。
- [ ] 用户指南、排障、迁移、备份、卸载和回滚完成。
- [ ] feature flags、默认值和已知限制完成。
- [ ] release notes、SBOM、许可证和签名状态完成。
- [ ] 所有文档引用同一 candidate/hash。

## N82：五类签署

**等级：** N3

- [ ] 产品签署核心场景和发布范围。
- [ ] 工程签署源码、构建、迁移和恢复。
- [ ] 安全签署输入、凭证、更新、安装包和证据脱敏。
- [ ] Windows 操作员签署 A0-A9。
- [ ] 视听复核签署成片、字幕、旁白和专项适用项。
- [ ] 所有签署绑定 candidate、artifact manifest 和 evidence manifest hash。

## N83：冻结和发布

**等级：** N3

- [ ] `freeze-release.ps1` 消费当前 schema 2.0 Windows 报告。
- [ ] 验证报告时效、机器批准、blocker 和引用 hash。
- [ ] freeze guard 首轮通过。
- [ ] 创建正式 `v1.0.0` tag。
- [ ] 发布 installer、校验文件、release notes、SBOM 和许可证。
- [ ] 保留上一稳定版本和回滚手册。
- [ ] 建立发布后观察窗口。
- [ ] 生成不可变 release record 和最终 stop point。

**Gate G8 / RELEASE_READY**

- [ ] P0=0、P1=0。
- [ ] clean source、RC、Windows 报告和签署指向同一 candidate。
- [ ] 所有默认启用能力有真实证据和回退路径。
- [ ] Cloud、插件、市场和跨平台未完成能力明确 disabled/beta。
- [ ] V1.0 可发布且可安全回滚。

# Phase 9：V1 后默认关闭项目

## N90：Provider 生产 Gate

- [ ] 每类至少一个真实 adapter 和一个 local/mock adapter。
- [ ] 预算、限流、熔断、failover 和未知状态证据。
- [ ] 凭证引用、轮换和撤销。
- [ ] Provider 失败不破坏本地项目且不重复计费。

## N91：云协作生产版本

- [ ] OIDC、组织、RBAC、设备和租户隔离。
- [ ] PostgreSQL、对象存储、PITR 和恢复演练。
- [ ] 离线编辑、冲突、评论、审核和版本历史。
- [ ] 远程执行、预算、region、lease 和 publication。
- [ ] SLO、监控、告警、审计和灾备。

## N92：插件与模板市场

- [ ] Plugin manifest、API version 和兼容矩阵。
- [ ] 文件、网络、进程、凭证和项目权限沙箱。
- [ ] 签名、来源、升级、卸载、撤销和崩溃隔离。
- [ ] 模板上传、审核、搜索、版本和恶意检测。
- [ ] 许可证、购买、退款、版权和下架。

## N93：macOS/Linux

- [ ] macOS Intel/Apple Silicon 和 Linux x64 支持矩阵。
- [ ] 路径、权限、大小写、进程和原子文件语义。
- [ ] Office 替代链、字体和编码器能力。
- [ ] macOS 签名/notarization 和 Linux 安装包。
- [ ] 安装、导入、预览、导出、恢复、回滚和卸载证据。

## 3. 每项任务固定交付物

每项任务完成时必须提供：

1. task ID、owner、branch/worktree、start HEAD 和 end HEAD。
2. N0/N1/N2/N3 隔离等级。
3. owned/shared paths 和明确非目标。
4. ports、workspace、cache、logs、output 和 PID 清单。
5. 失败测试或非法 fixture。
6. 实现提交和 contract/migration 影响。
7. 完整测试命令、版本、退出码、数量和日志 hash。
8. 真实媒体/Provider/Windows 需求及是否执行。
9. known failures、rollback 和 safe resume。
10. stop point JSON，`will_write_again=false`。

## 4. 标准验证命令

实际命令必须在对应 worktree 执行，并把缓存、workspace 和日志定向到任务私有目录。

```powershell
# Python
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check apps tests scripts
.venv\Scripts\python.exe -m ruff format --check apps tests scripts
.venv\Scripts\python.exe -m mypy apps/api/src

# Web / monorepo
pnpm.cmd lint
pnpm.cmd typecheck
pnpm.cmd test
pnpm.cmd build

# Playwright
pnpm.cmd e2e

# Release
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build-release.ps1
```

不得把超时、后台继续运行、只重跑失败项或缩小测试选择解释为全量通过。

## 5. 最终核对清单

- [ ] recovery root 未被 destructive cleanup。
- [ ] 所有开发成果来自 clean、可重建提交。
- [ ] 全量自动化首轮通过且测试数量未下降。
- [ ] 所有运行进程、端口和临时目录属于当前任务并已清理。
- [ ] Schema、OpenAPI、migration 和跨语言契约一致。
- [ ] Preview、Export、Quality 和 Package 绑定同一 graph/candidate。
- [ ] 七项工作台达到声明的成熟度和性能预算。
- [ ] Quality、Update、Fidelity 有证据或保持关闭。
- [ ] Effects、Presenter、P03-P12 有证据或保持阻断。
- [ ] 唯一 `dirty=false` RC 完成同一 run 的 A0-A9。
- [ ] 真实媒体、ASR、异常恢复和人工视听完成。
- [ ] P0=0、P1=0，五类签署完成。
- [ ] 卸载、升级、失败和回滚不破坏用户项目或上一成功成片。
- [ ] freeze guard 只接受当前 candidate 的完整报告。
- [ ] 未完成平台能力准确标为 disabled/beta。
- [ ] 正式 tag、发布记录和回滚手册完整。
