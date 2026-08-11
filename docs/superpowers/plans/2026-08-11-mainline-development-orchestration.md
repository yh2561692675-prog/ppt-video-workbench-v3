# PPT Video Workbench 剩余主线开发逐项实施计划

> 本计划是剩余主线的总控计划。每个项目必须在独立 worktree 中逐项完成并通过 Gate；共享根目录只用于恢复确认和集成，不作为并行功能开发区。

**Goal:** 在不影响其他窗口、不覆盖恢复成果的前提下，依次完成共享底座、RenderGraph、七项 P1、三项重大能力生产收口、P03-P12、特效工作台、P2 和 Windows 发布闭环。

**Design:** `docs/superpowers/specs/2026-08-11-mainline-development-orchestration-design.md`

**Planning baseline:** `9bca5e97c3d11718a604eb3f2344d19a723de700`

## 1. 总体顺序

| Phase | 项目                                    | 前置              | Gate |
| ----- | --------------------------------------- | ----------------- | ---- |
| 0     | 保护边界、停点和 Foundation checkpoint  | 当前恢复根        | G0   |
| 1     | 生产级共享底座与 Job v3 收口            | G0                | G1   |
| 2     | RenderGraph V2 执行闭环                 | G1                | G2   |
| 3     | P1 时间线、素材和材料                   | G2                | G3   |
| 4     | P1 字幕、连续镜头、多规格导出和批量调度 | G3                | G4   |
| 5     | 质量、安全更新和 PPT 高保真生产收口     | G2/G4             | G5   |
| 6     | P03-P12 生产闭环                        | G1/G4             | G6   |
| 7     | 特效编辑器、模板管理和 Effects V2 集成  | G2                | G7   |
| 8     | P2 Provider、Platform 和 Cloud 生产化   | G1；现有 worktree | G8   |
| 9     | 主线集成、迁移和完整自动化              | G2-G8             | G9   |
| 10    | Windows、真实媒体、人工验收和灰度发布   | G9                | G10  |

项目按 Phase 顺序推进。一个项目完成后可以直接进入下一个项目，但必须先提交该项目 stop point 和 Gate 证据；未通过 Gate 不得提前修改下游共享文件。

## 2. 全局保护清单

- [ ] 不在 `F:\ppt-video-workbench-v3` 共享 dirty root 开始新功能代码。
- [ ] 不修改现有 `p2-platform-integration` 中其他 owner 的未提交文件。
- [ ] 不运行 `git reset --hard`、`git clean`、批量 checkout、历史重写或覆盖式目录复制。
- [ ] 不删除、移动或格式化来源不明的 tracked/untracked 文件。
- [ ] 不写正式 workspace、正式安装目录、既有 `F:\Video` 项目或成片。
- [ ] 每个测试使用唯一临时数据根、数据库、端口、缓存和输出目录。
- [ ] 每个新 worktree 从最新 `FOUNDATION_READY` clean commit 创建。
- [ ] 每个窗口先登记 owned paths，再开始写入。
- [ ] 数据库、Job 契约、OpenAPI、主 wiring、Remotion Root、launcher 和 installer 由单一 owner 串行修改。
- [ ] 所有 feature flag 默认关闭；关闭时旧工作流输出保持一致。
- [ ] 所有长任务冻结输入；所有工件验证后原子发布。
- [ ] 每个 Task 先写失败测试或非法 fixture，再实现生产代码。
- [ ] 每个 Phase 结束后形成 stop point，声明 `will_write_again=false` 才可集成。

## Phase 0：保护边界与可信 Foundation

### Task 0.1：刷新只读状态清单

**Execution:** 只读。

- [ ] 记录根目录 branch、HEAD、tracked/untracked/unmerged 状态。
- [ ] 记录所有 Git worktree、branch、HEAD 和 dirty 状态。
- [ ] 读取当前 ownership map 和所有 foundation stop point。
- [ ] 核对最终渲染、Presenter、Effects、P1、RenderGraph、S1 和 P2 的最后证据。
- [ ] 将旧恢复记录与较新 checkpoint 冲突标记为 stale，不用旧状态覆盖新实现。
- [ ] 运行两次只读清单并确认源码状态 hash 不变。

**Acceptance:** 得到一份时间戳化状态清单；无写入；未知活动窗口均标为阻断而不是猜测完成。

### Task 0.2：收集窗口 stop point

- [ ] Job v3/共享底座窗口提交 owned/shared paths 和剩余 G1 项。
- [ ] RenderGraph 窗口提交最后完成切片和 remaining。
- [ ] P1 窗口提交七项能力的逐项完成度，不只写“骨架存在”。
- [ ] P2 owner 提交当前 `cloud_prototype` 未提交范围和继续写入计划。
- [ ] 特效编辑器 owner 提交最后 branch/commit/Task 15 状态；若 worktree 缺失，先只读恢复引用。
- [ ] Windows/Presenter/Effects 验收窗口提交证据边界和人工待办。

**Acceptance:** 所有会继续写入的窗口都有 owner；不能确认的路径进入 quarantine ownership，不进入 checkpoint。

### Task 0.3：解决共享文件所有权

- [ ] 合并 stop point 与实际状态生成 ownership map。
- [ ] 对 `domain`、`storage`、`jobs`、`main.py`、OpenAPI、Web client、WorkflowShell、Remotion Root、installer 逐文件指定 owner。
- [ ] generated/cache/release/backup/user-data 与源码分开分类。
- [ ] 对同一文件的多来源修改逐段审查，禁止以最后修改时间裁决。
- [ ] 未知源码所有权降为 0。

**Gate G0-A:** 无 unmerged path；共享文件 owner 唯一；无活动窗口被覆盖。

### Task 0.4：创建可恢复 checkpoint

- [ ] 由 integration owner 选择要纳入的已审查文件。
- [ ] 在 checkpoint 前运行 secret、大文件、绝对路径和 workspace-data 扫描。
- [ ] 创建小型、可审查提交，不混入 cache、release、数据库或备份。
- [ ] 在新的隔离目录重建提交并核对文件清单/hash。
- [ ] 生成 foundation manifest、schema hash、dependency hash 和 source fingerprint。

### Task 0.5：Foundation 自动化基线

- [ ] Python 全量 pytest、Ruff、mypy。
- [ ] Web lint/typecheck/Vitest/build。
- [ ] Remotion typecheck/tests/build。
- [ ] OpenAPI/schema/migration/release contract。
- [ ] Playwright 关键本地流程。
- [ ] 记录环境失败、权限失败、文件锁和外部依赖，不把超时当作通过。

**Gate G0 / FOUNDATION_READY:** checkpoint 可重建；自动化基线结论完整；之后才创建下游 worktree。

## Phase 1：生产级共享底座与 Job v3

**Worktree:** `codex/foundation-g1-closure`

### Task 1.1：审查 Job v3 迁移

- [ ] 校验 v1/v2 → v3 的幂等迁移、旧 active export 唯一性和状态映射。
- [ ] 测试迁移中断、重复启动、损坏行和部分 schema。
- [ ] 确认新表：attempts、checkpoints、publications、resource leases、workers。
- [ ] 禁止执行 schema downgrade SQL。

### Task 1.2：Attempt generation 与 CAS

- [ ] 所有状态变更使用 revision/attempt generation CAS。
- [ ] 旧 Worker 不得完成、失败或发布新 attempt。
- [ ] terminal Job 拒绝重复覆盖。
- [ ] pause 仅在 checkpoint 成功提交后完成。
- [ ] cancel 对当前 attempt 幂等且不删除上一成功产物。

### Task 1.3：Exactly-once publication

- [ ] 写 reservation、verify、publish、complete 的故障注入测试。
- [ ] 工件校验 hash、size、schema、ffprobe 和 project ownership。
- [ ] 进程在 rename 前后崩溃均可对账恢复。
- [ ] publication 记录与磁盘不一致进入 quarantined/corrupted，不静默复用。

### Task 1.4：Resource lease 与 Worker 恢复

- [ ] Worker capability、heartbeat、lease acquire/renew/release/reclaim。
- [ ] 多 JobType 公平领取；默认仍保持安全的低并发。
- [ ] 启动扫描 stale running/pausing/cancelling。
- [ ] 付费/外部任务在未知结果时进入人工确认，不自动重试。

### Task 1.5：统一 Job API 与诊断

- [ ] 查询、分页、ETag、pause/resume/cancel/retry 契约统一。
- [ ] 诊断只返回计数、稳定错误码和脱敏 runtime identity。
- [ ] 旧最终渲染 API 通过 adapter 保持兼容。
- [ ] Web 现有 RenderJobPanel 回归不退化。

### Task 1.6：G1 故障矩阵

- [ ] API 创建后崩溃。
- [ ] Worker claim 后崩溃。
- [ ] checkpoint 写前/写后崩溃。
- [ ] 外部进程超时、拒绝退出和进程树残留。
- [ ] publisher rename 前/后崩溃。
- [ ] 数据库锁、磁盘满、工件损坏和重启恢复。

**Gate G1:** Job/Attempt/Checkpoint/Lease/Publication 真相一致；最终渲染兼容测试通过；形成 stop point 和 clean commit。

## Phase 2：RenderGraph V2 执行闭环

**Worktree:** `codex/rendergraph-v2-closure`

### Task 2.1：统一跨语言 timebase fixtures

- [ ] Python/TypeScript 共用 24/25/30/60fps golden fixture。
- [ ] 16:9、9:16、1:1 和 720p/1080p/4K frame math。
- [ ] 所有媒体时间使用整数微秒，帧边界无双重舍入。

### Task 2.2：权威预览 Job

- [ ] `render_preview` 冻结 graph snapshot/range/preset/runtime。
- [ ] 生成 video proxy、audio proxy、subtitle 和 preview manifest。
- [ ] 支持 pause/cancel/restart/cache hit。
- [ ] 同一缓存键只发布一次；stale graph 不覆盖新预览。

### Task 2.3：Web graph 状态接入

- [ ] 第 6 步显示 graph revision/hash、compile/preflight/preview 状态。
- [ ] loading/empty/error/stale/blocked/degraded 状态明确。
- [ ] 范围预览失败可重试，不影响已发布预览。
- [ ] feature flag 关闭时完全回到 V1。

### Task 2.4：LegacyProjectAdapter 与增量失效

- [ ] 旧项目只读投影 ProductionTimeline/RenderGraph。
- [ ] 无 V2 独占语义时允许安全 fallback。
- [ ] 字幕、音频、overlay、transition、画幅分别验证 affected ranges。
- [ ] soft subtitle 修改不重渲 video-only；J/L Cut 不重渲视觉层。

### Task 2.5：真实媒体与性能

- [ ] transition/overlay/subtitle/J-L Cut 关键帧和 waveform oracle。
- [ ] soft/both subtitle 通过 ffprobe 流验证。
- [ ] 1000 节点编译、增量编译、首次预览和缓存命中预算。
- [ ] Windows packaged runtime preview/export smoke。

**Gate G2:** 第 6 步预览和第 7 步渲染绑定同一 graph hash；V2 仍默认关闭；stop point 完整。

## Phase 3：P1 时间线、素材与材料

### Task 3.1：生产时间线内核

**Worktree:** `codex/p1-timeline`

- [ ] 审计现有 ProductionTimeline 和命令引擎，保留可用实现。
- [ ] 完成拖动、裁剪、分割、吸附、ripple、链接和 marker。
- [ ] 完成撤销/重做、revision history、冲突重放和原子 batch command。
- [ ] 1000 clip/30 分钟项目虚拟化和交互预算。
- [ ] Presenter、字幕、效果、音乐、overlay 共用同一时间轴。

### Task 3.2：素材库真实派生

**Worktree:** `codex/p1-assets-materials`

- [ ] 批量导入安全检查、hash 去重和对象存储。
- [ ] 真实缩略图、代理、波形、裁剪、转码和可重建派生任务。
- [ ] 授权、来源、品牌包、LUT、字体和项目隔离。
- [ ] H.264/H.265/VP9、透明 PNG、SVG、长视频、WAV/MP3/AAC fixtures。

### Task 3.3：材料组织完整工作台

- [ ] 多文档、多课件、角色、顺序、启用状态和解析状态。
- [ ] 无大纲、合并大纲、章节合并/拆分/重排/禁用。
- [ ] 页面替换、差异预览和人工锁定。
- [ ] P03/P04 共用 MaterialCollection，不建立第二套输入模型。
- [ ] 材料同步时间线为显式命令，并可撤销。

**Gate G3:** 时间线、素材和材料使用统一 AssetRef/Job/Cache/RenderGraph 契约；旧项目可只读打开。

## Phase 4：P1 字幕、连续镜头、导出与批量

### Task 4.1：高级字幕工作台

**Worktree:** `codex/p1-subtitles-continuity`

- [ ] SubtitleDocument V2、旧字幕适配和命令引擎。
- [ ] 词级时间、分割/合并/微调、双语、术语表和人工确认。
- [ ] 样式模板、逐词高亮、软/烧录/both/none。
- [ ] 大量 cue 虚拟化、输入法、键盘和无障碍。
- [ ] Remotion 与 FFmpeg 共享同一 cue truth。

### Task 4.2：连续镜头、转场和 overlay

- [ ] 跨页重叠时长语义和 TransitionPlan。
- [ ] J/L Cut 音频边界与 20ms waveform 验证。
- [ ] dissolve/wipe/slide/match 和章节 continuity。
- [ ] image/video/logo overlay 的 z-order、alpha、裁剪和安全区。
- [ ] 横屏、竖屏、方屏关键帧回归。

### Task 4.3：多规格导出

**Worktree:** `codex/p1-export-scheduler`

- [ ] 720p/1080p/4K、24/25/30/60fps、多画幅和能力探测。
- [ ] H.264/H.265/VP9/AV1 按真实 runtime 开放。
- [ ] GIF、短视频切片、章节视频、软字幕和制作包。
- [ ] 每个 preset 独立进度、错误和产物，不覆盖其他 preset。
- [ ] 质量报告和 graph hash 写入每个导出结果。

### Task 4.4：批量生产与调度

- [ ] BatchPlan/BatchItem DAG、优先级、失败策略和夜间窗口。
- [ ] CPU/GPU/内存/磁盘/Office/网络 ResourceLease。
- [ ] 多 Worker 公平派发和能力不足等待原因。
- [ ] 页面级失败重跑与缓存复用。
- [ ] 重启恢复、lease 回收和 exactly-once publication。
- [ ] 20 项目批次资源与恢复验收。

**Gate G4:** 七项 P1 功能在 Web、API、RenderGraph、真实媒体和恢复测试中闭环；默认仍由 flags 控制。

## Phase 5：三项重大能力生产收口

### Task 5.1：质量检测生产门禁

**Worktree:** `codex/quality-production`

- [ ] 建立损坏、无音视频、黑帧、冻结、静音、字幕越界和音画漂移 corpus。
- [ ] strict/standard/fast 版本化策略；P0 不可关闭。
- [ ] P0/P1 召回率 100%，正常样本 P0/P1 误报为 0。
- [ ] QualityJob 绑定 graph hash、policy hash 和候选 MP4 hash。
- [ ] 只允许一次安全重试；人工确认和豁免可审计。
- [ ] Windows 安装版真实分析和重启恢复。

### Task 5.2：在线安全更新闭环

**Worktree:** `codex/secure-update-production`

- [ ] 正式 Ed25519 trust root、threshold、expiry 和 anti-rollback。
- [ ] HTTPS metadata、断点下载、hash/size/disk budget 和内容缓存。
- [ ] 安全解包、runtime manifest、独立 update helper 和参数约束。
- [ ] 启动健康检查、迁移 journal、自动回滚和状态 marker。
- [ ] 安装器接入、密钥轮换、恶意包/路径/重放/中间人测试。
- [ ] 修复安装、升级、回滚、SmartScreen/签名状态证据。

### Task 5.3：PPT 高保真生产闭环

**Worktree:** `codex/fidelity-production`

- [ ] OOXML 能力扫描和恶意 PPTX corpus。
- [ ] SlideScene、MotionCueSet 和元素动画映射完整性。
- [ ] Office/LibreOffice/安全 F0 降级能力矩阵。
- [ ] 原生 PowerPoint 捕获适配器和页面级 MP4/hash/environment。
- [ ] Fidelity Resolver、缓存、任务恢复和时间线接入。
- [ ] 60 页 corpus、Windows/Office、人工视觉和性能门禁。

**Gate G5:** 三项能力各自形成真实证据、回滚路径和 stable-optional 决策；不重复实现统一时间线。

## Phase 6：P03-P12 生产闭环

**Worktree:** `codex/s1-p03-p12-closure`

### Task 6.1：统一 S0/S1 契约

- [ ] S1 Job 通过 Job v3 adapter 执行，不复制状态机。
- [ ] BusinessResult/Artifact/Event schema 与主程序 projector 对齐。
- [ ] artifact streaming 校验 job ownership、hash、size 和路径边界。
- [ ] host restart、inbox、quarantine 和幂等投影恢复。

### Task 6.2：P03-P06 输入与旁白

- [ ] 材料/提取复用 MaterialCollection/AssetRef。
- [ ] 页面匹配、旁白 revision、人工确认和依赖失效。
- [ ] LLM Provider 通过 P2 adapter seam；关闭 P2 时旧 provider 可用。

### Task 6.3：P07-P10 音频、字幕、效果和预检

- [ ] 本地录音与 HeyGen 严格互斥。
- [ ] ASR/TTS/HeyGen request id、费用、重试和未知状态恢复。
- [ ] P08 使用 SubtitleDocument V2 adapter。
- [ ] P09 使用已发布 EffectPlan/template revision。
- [ ] P10 汇总 graph、素材、Presenter、效果、质量和交付阻断。

### Task 6.4：P11-P12 渲染与交付

- [ ] P11 绑定 frozen graph，支持分页、失败页重跑、FFmpeg 和制作包。
- [ ] P12 校验质量报告、artifact manifest、签署和脱敏。
- [ ] 自动通过不能替代要求的人工确认。
- [ ] 8 页 local/fake-HeyGen/real-HeyGen 小额链路和失败恢复。

### Task 6.5：S1 Windows Gate

- [ ] S0/S1 runtime manifest、Office/OCR/ASR/FFmpeg/Remotion 能力。
- [ ] 中文路径、重启、端口恢复和 orphan process 检查。
- [ ] 真实 HeyGen、人工视听、rollback 和双人签署。

**Gate G6:** P03-P12 完整证据清单通过；无真实 HeyGen/人工签署时保持 BLOCK。

## Phase 7：特效编辑器、模板和 Effects V2

**Worktree:** `codex/effects-workbench-integration`

### Task 7.1：恢复并核对最后停点

- [ ] 找回特效工作台 branch/commit/patch/stop point。
- [ ] 确认 Task 1-15 实际完成范围和测试证据。
- [ ] 与当前 root 的 Effects V2/Remotion/OpenAPI 逐文件比较。
- [ ] 禁止将旧 worktree 整目录复制到根目录。

### Task 7.2：完成作者态与模板生命周期

- [ ] 草稿、revision、自动保存、冲突恢复和不可变发布。
- [ ] 模板创建、复制、校验、发布、弃用、归档和回滚。
- [ ] `.pvtmpl` 安全导入/导出、quarantine 和索引重建。
- [ ] renderer capability 和不支持模板的明确降级。

### Task 7.3：工作流与 E2E

- [ ] 编辑器页面轨道、检查器、预览、批量应用和发布。
- [ ] 已发布 revision 接入 RenderGraph；草稿无效状态不影响正式渲染。
- [ ] 浏览器刷新、断线、冲突、失败发布和回滚 E2E。
- [ ] OpenAPI、用户文档、诊断和迁移说明。

### Task 7.4：Effects V2 人工 Windows 验收

- [ ] 安装与首次启动、打开既有项目。
- [ ] 单页音频、预览、完整预检和批量失败隔离。
- [ ] 关闭程序后重启恢复、最终合成与导出。
- [ ] 关闭 V2 flag 后旧链回滚。
- [ ] 诊断包脱敏和人工视觉/动态字幕签署。

**Gate G7:** 工作台可审查集成；Effects V2 只有人工门禁完成后才可 stable optional。

## Phase 8：P2 平台生产化

**Worktree:** 继续使用 `codex/p2-platform-integration`；不得另建重复 P2 实现。

### Task 8.1：先收口当前未提交状态

- [ ] 由 P2 owner 审查 `cloud_prototype/app.py`。
- [ ] 审查 `tests/cloud/test_cloud_api.py` 和 `cloud_prototype/migrations/`。
- [ ] 形成小型提交和 stop point；其他窗口不触碰。
- [ ] 解决全量兼容失败，不修改 root 共享契约绕过问题。

### Task 8.2：Provider 真实迁移

- [ ] 六类 Provider 的 descriptor/probe/estimate/invoke/error/cache/audit。
- [ ] credential reference、预算、429、超时、幂等、区域和付费安全。
- [ ] LLM/ASR/TTS/avatar/OCR/renderer 逐类迁移。
- [ ] fake Provider 只用于自动化，真实供应商另行验收。

### Task 8.3：PlatformServices 与三平台

- [ ] Windows 路径、凭证、进程、工具、媒体、Office 行为封装且无回归。
- [ ] macOS/Linux capability snapshot 和安全降级。
- [ ] 两个平台真实 8 页软件编码 MP4。
- [ ] 三平台 installer/update/CI 和签名证据。

### Task 8.4：Cloud 生产门禁

- [ ] PostgreSQL tenant scope、PITR 和恢复演练。
- [ ] OIDC issuer/audience/signature、撤销和轮换。
- [ ] 对象存储短期 URL、保留、删除/导出和 legal hold。
- [ ] RBAC、IDOR、重放、恶意 executor 和租户边界测试。
- [ ] 双设备离线同步、冲突、评论、审核和撤销。
- [ ] remote executor lease、结果 hash/schema/media/ownership 校验。
- [ ] SAST/DAST/dependency scan、SLO、费用、区域和告警。

**Gate G8:** Provider/Platform 可按成熟度启用；Cloud 仍以独立 beta Gate 发布，未通过生产证据时 fail closed。

## Phase 9：主线集成与完整自动化

**Worktree:** `codex/mainline-release-integration`

### Task 9.1：创建 clean integration branch

- [ ] 从 FOUNDATION_READY 创建 clean worktree。
- [ ] 按 G1 → G2 → G3 → G4 → G5 → G6 → G7 → G8 顺序移植提交。
- [ ] 每次只集成一个项目；记录 commit、冲突文件和解决理由。
- [ ] 共享文件由 integration owner 应用最小补丁。

### Task 9.2：契约、迁移和失效矩阵

- [ ] Job/RenderGraph/Asset/Material/Subtitle/Quality/Provider/Cloud schema 对齐。
- [ ] OpenAPI 重新生成并验证无意外路由/字段漂移。
- [ ] v1/v2/v3 数据库和旧项目 fixtures 迁移。
- [ ] 建立跨项目 cache invalidation 和 feature flag 依赖图。

### Task 9.3：七步工作流集成

- [ ] 每一步 loading/empty/error/stale/blocked/degraded/retry 状态。
- [ ] 第 6 步使用 graph-aware preview；第 7 步使用 frozen graph render。
- [ ] 质量、Presenter、Effects、P03-P12 和多规格导出接入但可独立关闭。
- [ ] 所有 flags 关闭时旧七步流程完成且输出不变。

### Task 9.4：完整自动化矩阵

- [ ] Python unit/integration/contract/security/release 全量。
- [ ] Ruff check/format check 与 mypy 全量。
- [ ] Web lint/typecheck/Vitest/build。
- [ ] Remotion tests/typecheck/build/visual snapshots。
- [ ] Playwright 项目生命周期、刷新恢复、暂停取消和旧项目流程。
- [ ] migration、OpenAPI、installer、runtime manifest 和 secret scan。

**Gate G9 / INTEGRATION_READY:** clean integration commit 可重建；全量自动化无未知失败；生成唯一 RC source manifest。

## Phase 10：Windows、真实媒体与发布

### Task 10.1：构建唯一 RC

- [ ] 从 G9 clean commit 构建，不从共享开发根打包。
- [ ] 固定 installer、workbench.exe、runtime、Chromium、Node、FFmpeg/ffprobe 和 schema hash。
- [ ] 同一 RC 用于后续全部验收，不在过程中替换同名制品。

### Task 10.2：安装、修复、升级和回滚

- [ ] 隔离安装、首次启动、端口冲突和中文路径。
- [ ] 修复安装、旧版本升级、失败升级自动回滚。
- [ ] 卸载保留用户数据、同制品重装和恢复。
- [ ] antivirus/SmartScreen/签名状态记录。

### Task 10.3：真实项目矩阵

- [ ] 8 页标准项目：预览、渲染、制作包、质量报告和 hash。
- [ ] 50 页项目：峰值 CPU/内存/磁盘、暂停恢复和时长。
- [ ] Presenter 5-8 分钟与 15-20 分钟私有样本。
- [ ] 9:16 与 1:1 安全区、裁剪、字幕和 overlay。
- [ ] Effects V2 30 页动态预览/导出。
- [ ] P03-P12 local/fake/real Provider 代表链。
- [ ] 多规格、软字幕、章节、批量 20 项目。

### Task 10.4：异常与恢复矩阵

- [ ] 强制关闭 API、Worker、Remotion、FFmpeg、Office 和浏览器。
- [ ] 数据库锁、磁盘满、素材损坏、网络断开、429 和超时。
- [ ] 重启后 Job/Attempt/Checkpoint/Lease/Publication 对账。
- [ ] 进程树和端口无残留；上一成功成片保持可用。

### Task 10.5：灰度与签署

- [ ] compile-only → preview-only → internal export。
- [ ] stable optional 的质量、Presenter、Effects、P1 和 Provider 决策。
- [ ] Cloud Sync 保持独立 beta，除非生产云 Gate 单独通过。
- [ ] P0/P1 缺陷为 0；P2/P3 有 owner、影响和规避。
- [ ] 产品、工程、安全、Windows 操作员和视听复核签署。

**Gate G10 / RELEASE_READY:** 完整证据包签署；默认开关和回退条件明确；否则保持 RC/BLOCKED，不宣称发布完成。

## 3. 每个项目的固定交付物

每个 Phase/项目完成时必须提供：

- [ ] 独立 branch/worktree 和 clean HEAD。
- [ ] owned paths、shared paths 和冲突说明。
- [ ] 设计偏差及原因。
- [ ] 新增/修改 schema、migration、API 和 flags 清单。
- [ ] 定向测试、静态检查和真实媒体证据。
- [ ] 已知失败、环境阻断和未完成事项。
- [ ] 回退方法和数据兼容说明。
- [ ] stop point JSON 与 `will_write_again=false`。

## 4. 提交与集成规则

- [ ] 一个 Task 一个或多个小型提交，不混入其他项目。
- [ ] 不提交 cache、dist、成片、安装目录、临时数据库、模型缓存或恢复备份。
- [ ] schema/migration、后端、Web、Remotion、测试和文档可分提交，但必须在 Gate 前成套。
- [ ] 合并前运行 `git diff --check`、secret scan 和大文件审查。
- [ ] 冲突解决必须记录语义选择，不使用整文件 `ours/theirs` 覆盖未知成果。
- [ ] 失败的 integration candidate 可丢弃；不得回写或清理来源 worktree。

## 5. 推荐资源配置

在不共享写入路径的前提下，最多同时开启三条线：

1. Foundation/RenderGraph integration owner：唯一共享契约 owner。
2. 当前阶段的一个 P1/质量/S1/FX 功能 worktree。
3. 已隔离的 P2 worktree。

若只有一个开发窗口，严格按 Phase 0-10 顺序一个项目一个项目完成。若任一窗口仍在修改共享根目录，其他窗口只允许文档、fixture 和只读盘点。

## 6. 最终验收清单

- [ ] 共享根目录和所有 worktree 的成果来源清楚，未知源码所有权为 0。
- [ ] 最终渲染不被重写，现有异步兼容和 Windows 结果保持通过。
- [ ] Job v3 故障恢复与 exactly-once publication 通过。
- [ ] 预览、渲染、质量和制作包绑定相同 graph hash。
- [ ] 七项 P1 在真实媒体、Web 和 Windows 安装版中可用。
- [ ] 质量、安全更新和 PPT 高保真达到生产 Gate。
- [ ] P03-P12 完成真实 Provider、失败恢复、渲染和交付签署。
- [ ] 特效工作台安全集成，Effects V2 完成人工 Windows 流程。
- [ ] Presenter 私有样本和人工音画同步门禁完成。
- [ ] P2 准确声明 Provider、三平台和 Cloud 的成熟度，未完成能力 fail closed。
- [ ] 旧项目、旧成片、用户数据库和正式安装目录未被验收过程破坏。
- [ ] 完整自动化、真实媒体、安装升级回滚和人工签署使用同一 RC。

以上全部通过后，才可把总项目状态改为 `RELEASE_READY`。
