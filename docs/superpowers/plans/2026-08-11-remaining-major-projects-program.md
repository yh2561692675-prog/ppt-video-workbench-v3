# PPT Video Workbench 剩余大型项目三线逐项实施计划

> 本计划固定使用三条隔离开发线。三线可以在同一 Wave 内并行，但共享契约、数据库迁移、主应用 wiring 和发布候选必须经过串行 integration Gate。

**Goal:** 完成剩余大型项目，先形成可发布 V1，再推进 Provider、云协作、插件市场和跨平台桌面版。

**Design:** `docs/superpowers/specs/2026-08-11-remaining-major-projects-program-design.md`

**Audit baseline:** `recovery/root-snapshot-20260810@117fb60cbb0ca877c0920a26f5ceb31d8e42e901`

## 1. 三条隔离开发线

| Line                    | Branch                             | Worktree                                | Owner scope                                                                              |
| ----------------------- | ---------------------------------- | --------------------------------------- | ---------------------------------------------------------------------------------------- |
| A：Core Workbench       | `codex/program-core-workbench`     | `.worktrees/program-core-workbench`     | foundation、数据库/API 权威、Web、时间线、素材、材料、字幕、continuity                   |
| B：Render & Release     | `codex/program-render-release`     | `.worktrees/program-render-release`     | RenderGraph、Remotion、FFmpeg、导出、调度执行、质量、高保真、Effects、Presenter、Windows |
| C：Platform & Ecosystem | `codex/program-platform-ecosystem` | `.worktrees/program-platform-ecosystem` | Provider、PlatformServices、云、插件、模板市场、macOS/Linux                              |

短生命周期 `codex/program-integration-v1` 只用于 Gate，不计为第四条开发线，不在其中开发新功能。

## 2. 全局执行规则

- [ ] 在 G0 通过前不创建三条长期 worktree，不从仍在运行的窗口抢占文件。
- [ ] 不对恢复根目录执行 reset、clean、覆盖式复制、批量 checkout 或历史重写。
- [ ] 三线从同一 `foundation_source_commit` 派生并记录 source fingerprint。
- [ ] 每条线使用独立 Python cache、Node 输出、端口、数据库、workspace、release 和 evidence 目录。
- [ ] 共享路径只由 A 线或 integration Gate 修改；B/C 以 contract proposal 提交需求。
- [ ] 每项任务先添加失败测试、非法 fixture 或漂移检查，再实现功能。
- [ ] 每个提交只完成一个目的，源码、格式化、生成物和证据分开提交。
- [ ] 每个任务提供 owned paths、测试命令、退出码、日志、回退和 safe resume。
- [ ] Gate 未通过时三线只修复当前 Wave，不越级进入下一 Wave。
- [ ] 付费 Provider、真实云资源、代码签名和市场计费需要单独授权；离线测试不得产生费用。

## 3. 共享路径责任

| 路径                                                   | Owner  | 其他线规则                                    |
| ------------------------------------------------------ | ------ | --------------------------------------------- |
| `apps/api/src/workbench/storage/`                      | A      | B/C 提交 migration proposal，不直接改历史迁移 |
| `apps/api/src/workbench/jobs/`                         | A      | B/C 注册 executor，不改核心状态机             |
| `apps/api/src/workbench/main.py`                       | A/Gate | B/C 提供独立 router 和 wiring patch           |
| `apps/web/src/api/client.ts`                           | A/Gate | B/C 先更新 OpenAPI/contract                   |
| `apps/web/src/features/workflow/WorkflowShell.tsx`     | A      | B/C 提供独立 Panel，不直接接线                |
| `packages/contracts/`、核心 `schemas/`                 | A/Gate | B/C 提交 versioned proposal 和 fixture        |
| `apps/api/src/workbench/rendering/`、`remotion/`       | B      | A 提供 timeline/asset/subtitle 输入契约       |
| `scripts/build-release.ps1`、`installer/`              | B      | A/C 不修改                                    |
| `providers/`、`platform/`、`sync/`、`cloud_prototype/` | C      | A/B 只实现 adapter boundary                   |
| `.github/workflows/`                                   | Gate   | 三线提交独立 job proposal                     |

## 4. Wave 总览

| Wave | A 线                                      | B 线                               | C 线                   | Gate                        |
| ---- | ----------------------------------------- | ---------------------------------- | ---------------------- | --------------------------- |
| W0   | 盘点 G1-G5 和 owner                       | 收口 Windows、RenderGraph、Effects | 复核 P2 基线           | G0 ACTIVE_LINES_CLOSED      |
| W1   | 干净 foundation、契约、迁移               | graph/export/runtime 接入          | P2 契约漂移关闭        | G1 INTEGRATION_READY        |
| W2   | Web、时间线、素材、材料、字幕、continuity | 导出、调度、质量、高保真           | Provider 生产适配      | G2-G4 V1_CAPABILITIES_READY |
| W3   | 七步工作流总接线                          | Presenter、外围、RC、Windows       | 云生产准备             | G5-G6 V1_RELEASED           |
| W4   | V1 维护                                   | 跨平台媒体执行                     | 云、插件、市场、跨平台 | G7-G9 PLATFORM_READY        |

# Wave 0：收口现有活跃任务并冻结来源

## A00：登记 G1-G5 共享底座

**Owner:** A 线准备负责人。  
**Writes:** 仅新增 Program evidence；不修改底座源码。

- [ ] 校验 G1-G5 stop point JSON schema、source HEAD、完成项和测试结果。
- [ ] 为每个 stop point 建立 source path、owned paths、contract versions 和 migration impact 清单。
- [ ] 标记尚未进入 commit 的文件，不把 stop point 误标为已归并。
- [ ] 记录 P6 Web 接入和 P7 资源调度的 safe resume。

**完成标准：** `g1-g5-source-inventory.json` 可定位每个成果的准确来源，unknown source 为 0。

## B00：完成 Windows 当前全链验收

**Owner:** B 线 Windows 子线。  
**上游专项:** `2026-08-11-windows-release-stability-and-full-chain-acceptance.md`。

- [ ] 完成当前修复候选的 Office/PPT 转换，不复用首个失败候选证据。
- [ ] 完成导入、配音、单页/批量渲染、故障恢复和最终合成。
- [ ] 完成重启恢复、升级、回滚、卸载和外部工作区保留。
- [ ] 修复实机发现的问题并为每个问题添加安装版回归测试。
- [ ] 生成绑定 candidate ID 的 A0-A9 报告和 release artifact manifest。
- [ ] 输出提交、dirty 状态、已完成、未完成和 safe resume。

**完成标准：** 当前窗口 idle/completed；成功候选与失败候选证据隔离；没有后台安装/Office/API 进程残留。

## B01：完成 RenderGraph V2/最终渲染收口

**Owner:** B 线渲染子线。  
**Worktree:** `.worktrees/rendergraph-v2-closure`。

- [ ] 完成隔离分支完整测试、构建和 release smoke。
- [ ] 固定 graph schema、timebase、Remotion composition、FFmpeg plan 和 final mux 契约。
- [ ] 完成真实转场、J/L Cut、字幕流、Overlay 和 graph-bound job 证据。
- [ ] 提交所有功能变更；格式化提交与功能提交分离。
- [ ] 输出 HEAD、owned paths、测试日志和 integration 顺序。

**完成标准：** worktree clean；分支可从 source commit 重建；没有依赖根目录未提交文件。

## B02：完成 Effects Task 18-25 恢复停点

**Owner:** B 线 Effects 子线。  
**Worktree:** `.worktrees/effects-task18-25-recovery`。

- [ ] 逐 Task 完成来源、源码、自动化、样本、视觉和 RC 六层门禁。
- [ ] 找不到的历史提交明确标记 `reconstructed`，保存搜索证据。
- [ ] 修复 manifest、Ground Truth 和安装包全资产 hash 校验。
- [ ] 恢复缺失测试和最小实现，不复制未知目录覆盖。
- [ ] 形成 Task 18-25 独立提交和最终冻结 stop point。

**完成标准：** 每个 Task 都有 source classification、commit、验证和回退；校验器不会对资产漂移返回 `valid=true`。

## C00：刷新 P2 平台基线

**Owner:** C 线准备负责人。  
**Source:** `codex/p2-platform-integration@51cc325`。

- [ ] 在隔离分支复跑 P2 聚焦测试、mypy、Ruff 和 TypeScript drift check。
- [ ] 记录 Provider、PlatformServices、Cloud OpenAPI、同步和远程任务的版本。
- [ ] 区分已完成 foundation、仍需真实 Provider 的项目和仅有 prototype 的云能力。
- [ ] 确认所有 P2 flags 默认关闭，离线测试不产生网络请求或费用。
- [ ] 输出与当前 V1 核心契约的漂移报告，不修改 V1 根目录。

**完成标准：** P2 source clean、测试可复现、契约漂移清单完整。

## Gate G0：ACTIVE_LINES_CLOSED

- [ ] Windows、RenderGraph、Effects 当前窗口均完成或形成可信停点。
- [ ] G1-G5 和 P2 来源可解析。
- [ ] 所有活动进程、端口、安装目录和 worktree 有 owner。
- [ ] 没有 unmerged 文件。
- [ ] 创建 `g0-active-lines-closed.json`。

# Wave 1：创建三线并完成干净集成基础

## A10：确定 foundation source commit

- [ ] 汇总 G0 来源，逐文件审查 shared paths。
- [ ] 排除 cache、release、backup、ZIP、日志、用户项目和临时构建。
- [ ] 运行 secret、大文件、绝对路径和用户数据扫描。
- [ ] 按 domain、contract、migration、test、docs 形成小提交。
- [ ] 在临时目录从提交和锁文件重建最小环境。

**完成标准：** `FOUNDATION_SOURCE_READY`；commit 可重建且工作树 clean。

## A11：创建三条隔离 worktree

仅在 A10 和 G0 通过后执行：

```powershell
git worktree add .worktrees/program-core-workbench -b codex/program-core-workbench <foundation_source_commit>
git worktree add .worktrees/program-render-release -b codex/program-render-release <foundation_source_commit>
git worktree add .worktrees/program-platform-ecosystem -b codex/program-platform-ecosystem <foundation_source_commit>
```

- [ ] 核对三个绝对路径位于预期仓库内。
- [ ] 记录 branch、HEAD、git-dir、lock hash 和 clean status。
- [ ] 建立独立 `.test-*`、workspace、port 和 evidence 配置。
- [ ] 不复制根目录 `node_modules`、`.venv`、release 或 cache；允许按锁文件安装/链接受控依赖。

## A12：归并 G1-G5

- [ ] 按 Job → assets → preview → cache → migration 顺序接入。
- [ ] 每接入一层运行其 stop point 定向测试。
- [ ] 解决 migration 单调递增、JobType、error code 和 API contract 冲突。
- [ ] 保留旧项目只读、V2 原子 pointer 和 rollback。
- [ ] 更新 Web client 和 fixtures，不手写影子类型。

**关键文件：** `storage/`、`jobs/`、`assets/`、`rendering/preview*`、`cache/`、`migrations/`、`api/migrations.py`。

## A13：冻结 V1 核心契约

- [ ] Project、Asset、Material、Timeline、Subtitle、Continuity、RenderGraph、Job、Export、Quality 全部带版本。
- [ ] Python、TypeScript、JSON Schema 和 OpenAPI 字段镜像一致。
- [ ] 生成单一 golden fixtures，禁止双端复制后各自漂移。
- [ ] unknown field、旧版本和非法枚举有明确兼容策略。
- [ ] 创建 contract fingerprint 和 drift test。

## B10：接入 RenderGraph 与发布运行时

- [ ] 从 B01 分支挑选已验证提交，不复制目录。
- [ ] 接入 graph snapshot、compiler、preflight、Remotion、audio filter 和 final mux。
- [ ] 注册 B 线 executor 到 A 线冻结 Job registry，不改 Job 状态机。
- [ ] 接入 Windows runtime manifest、launcher 和 release artifact manifest。
- [ ] 保持 feature flag 默认关闭并验证 V1 fallback。

## B11：接入 Effects/Presenter 扩展边界

- [ ] 只接入 provenance 完整的 Effects Task 18-25 提交。
- [ ] Effects、Presenter 和 P03-P12 通过独立模块/adapter 接入 RenderGraph。
- [ ] 失败不得修改基础 graph 或静默降级到错误成片。
- [ ] 更新制作包和质量报告 provenance。

## C10：迁移 P2 foundation

- [ ] 从 P2 集成分支挑选 contracts、Provider Kernel、PlatformServices、sync 和 cloud prototype 提交。
- [ ] 所有入口保持 flags 默认关闭。
- [ ] 不改变 V1 本地项目、凭证、路径和执行默认值。
- [ ] 解决与 A13 的 version envelope、Job、Asset 和 error code 漂移。
- [ ] 生成 standalone TypeScript client 并执行 drift check。

## Gate G1：INTEGRATION_READY

- [ ] 创建短生命周期 `codex/program-integration-v1`。
- [ ] 按 A12/A13 → B10/B11 → C10 顺序接入。
- [ ] Python 全量、Ruff、mypy 通过。
- [ ] Web 全量、typecheck、production build 通过。
- [ ] Remotion 全量、typecheck 通过。
- [ ] schema/OpenAPI/generated client/migration drift 为 0。
- [ ] 旧项目重复迁移、中断、回滚和损坏 V2 fallback 通过。
- [ ] 工作树 clean，生成 `g1-integration-ready.json`。

# Wave 2：V1 核心能力三线并行

## Line A：Core Workbench

### A20：Web 生产状态与统一 Task Center

- [ ] 分离 server truth、selection、viewport、playhead、pending command 和 conflict。
- [ ] 使用 revision/CAS 提交命令，失败保留可重放 payload。
- [ ] Task Center 展示 Job、attempt、checkpoint、资源等待、错误和 publication。
- [ ] 支持 pause/resume/cancel/retry，禁止重复提交付费未知任务。
- [ ] 接入 authoritative preview 的 stale/queued/running/ready/degraded/failed。

**测试：** reducer/store 性质测试、API contract、刷新恢复、双标签页冲突、键盘/无障碍。

### A21：统一多轨时间线编辑器

- [ ] 建立 1,000 clips 虚拟化轨道和稳定时间几何。
- [ ] 实现拖动、裁剪、分割、ripple、多选、框选和锁轨。
- [ ] 实现帧/边界/marker/相邻 clip 吸附。
- [ ] 接入波形、缩略图、代理和视口预取。
- [ ] 实现服务端历史、撤销重做、revision conflict 和命令重放。
- [ ] 播放头与 interactive/authoritative preview 双向同步。

**Gate A21:** 1,000 clips 平移/缩放 p95 < 50ms；无全量 DOM；冲突后不丢命令。

### A22：素材库与灵活材料组织

- [ ] 批量导入、进度、重复检测、损坏媒体和失败恢复。
- [ ] 搜索、标签、类型、授权、来源、品牌包和字体治理。
- [ ] 代理、缩略图、波形、透明通道和派生状态 UI。
- [ ] 支持无大纲、多文档、多套课件和混合输入。
- [ ] 章节合并、拆分、排序、禁用、页面替换和差异预览。
- [ ] 材料集合到时间线使用显式 sync command 和 revision。

### A23：高级字幕工作台

- [ ] cue/word 编辑、合并、拆分、平移和人工断句。
- [ ] 双语对齐、术语表、翻译版本和人工确认。
- [ ] 样式模板、逐词高亮、字体授权和安全区。
- [ ] burn-in/soft/both/none 统一真相。
- [ ] SRT/WebVTT/ASS 和 MP4 多语言轨 metadata。
- [ ] IME、键盘、无障碍和大量 cue 性能。

### A24：Continuity 与 Overlay 编辑

- [ ] TransitionPlan、视觉 overlap 和总时长语义。
- [ ] J/L Cut、chapter 和 crossfade 命令模型。
- [ ] image/video/logo/sticker/text Overlay 属性编辑。
- [ ] 安全区、z-index、mask、opacity、enter/exit。
- [ ] 与字幕、Presenter 和 timeline history 共用 revision。

## Line B：Render & Release

### B20：多规格导出系统

- [ ] 参数化 720p/1080p/4K、24/25/30/60fps、16:9/9:16/1:1。
- [ ] H.264/H.265/VP9/AV1 能力探测和安全降级。
- [ ] GIF、短视频切片、章节、多语言软字幕和制作包。
- [ ] 多 preset 共享中间产物但 publication 身份独立。
- [ ] ffprobe 校验画布、帧率、时长、音频、字幕和编码器。

### B21：批量生产与持久资源调度

- [ ] BatchPlan、BatchItem 和依赖图迁入数据库。
- [ ] capability registry 和 CPU/GPU/内存/磁盘/Office/网络 lease。
- [ ] 公平优先级、项目并发上限、夜间队列和恢复窗口。
- [ ] 多 Worker pool、心跳、续租、回收和稳定等待原因。
- [ ] 页面级重跑、缓存复用和 exactly-once publication。
- [ ] 资源监视器和预计耗时 API；UI wiring 由 A 线接入。

### B22：真实媒体自动验收平台

- [ ] 定义 ProductionMediaFixture V1 和确定性生成器。
- [ ] 覆盖 PPTX、PDF、扫描 PDF、图片、视频、音频、双语字幕和透明素材。
- [ ] 建立 ffprobe、waveform、subtitle、frame 和 hash oracle。
- [ ] 生成黑帧、静音、爆音、越界、损坏、磁盘满等坏样本。
- [ ] 报告绑定 source commit、runtime、candidate、fixture 和 artifact hash。

### B23：质量检测与 PPT 高保真

- [ ] 固化 P0/P1 质量规则版本、召回率、误报率和豁免审计。
- [ ] PowerPoint 原生捕获和 LibreOffice 降级。
- [ ] SmartArt、复杂图表、公式、媒体、字体和动画 corpus。
- [ ] F0/F1/F2 忠实度阈值和页面差异定位。
- [ ] 8/30/50/60 页、30 分钟、4K/60fps 资源预算。

## Line C：Platform & Ecosystem

### C20：真实 Provider 适配器框架

- [ ] 为 LLM/TTS/ASR/OCR/Avatar/Renderer 定义正式 adapter checklist。
- [ ] 能力发现、模型目录、region、健康和 runtime version。
- [ ] request fingerprint、idempotency key、unknown remote result。
- [ ] 本地/mock adapter 始终可用于无费用测试。

### C21：费用、预算、限流与 failover

- [ ] 提交前费用预估和项目/租户预算门禁。
- [ ] token/request/concurrency 限流和 Retry-After。
- [ ] 熔断、有限重试和显式 failover chain。
- [ ] 账单结果、缓存命中和审计流不保存输入或秘密。

### C22：凭证与隐私

- [ ] Windows Credential Manager/macOS Keychain/Linux Secret Service adapter。
- [ ] 项目只保存 credential reference。
- [ ] 日志、诊断、缓存和云同步执行 secret 扫描。
- [ ] 凭证撤销、轮换和不可用诊断。

## Gate G2：WEB_FOUNDATION_READY

- [ ] A20 和资源等待 UI 通过。
- [ ] Task Center 重启恢复和冲突控制通过。
- [ ] GC 保护源文件、正式输出、checkpoint 和上一成功成片。
- [ ] Web 全量、typecheck、build 和关键 Playwright 通过。

## Gate G3：EDITING_READY

- [ ] A21-A24 通过定向、性能、视觉和真实代理测试。
- [ ] 编辑后 affected ranges 精确，不做无关全量失效。
- [ ] 字幕、continuity、Overlay 和 Presenter 安全区一致。
- [ ] 旧项目可在不迁移时只读打开，迁移后可回滚。

## Gate G4：DELIVERY_READY

- [ ] B20-B23 通过多规格真实成片矩阵。
- [ ] 20 项目批次在进程重启后无丢失、无重复 publication。
- [ ] C20-C22 离线契约通过；真实付费验证单独记录。
- [ ] 三线接入 integration worktree 后全量门禁通过。

# Wave 3：V1 总接线、RC 与正式发布

## A30：七步工作流总接线

- [ ] 项目中心接入材料、时间线、素材、字幕、continuity、导出和 Task Center。
- [ ] 路由切换不丢 selection、playhead、pending command 和 job 状态。
- [ ] stale preflight/graph/preview 明确显示并阻止错误导出。
- [ ] 完成键盘、IME、屏幕阅读器、错误恢复和新手提示。
- [ ] 形成用户手册、迁移说明和诊断指南初稿。

## B30：Presenter 与 P03-P12 生产链

- [ ] 真实 ASR、真人音频、锚点修正和 5-20 分钟音画同步。
- [ ] Presenter、字幕、Overlay 和竖屏安全区验收。
- [ ] OCR/ASR/HeyGen/Remotion/FFmpeg 真实小样本和失败页续跑。
- [ ] 十个外围模块接入统一 Job、checkpoint、publication 和质量归档。
- [ ] 费用、缓存、未知远端状态和双人复核记录。

## C30：云协作生产准备

V1 发布前只完成默认关闭的生产准备：

- [ ] OIDC/JWKS 验证接口和 tenant/RBAC 契约。
- [ ] PostgreSQL migration、PITR 计划和对象保留策略。
- [ ] chunk upload、hash、revision、outbox 和 conflict UI 契约。
- [ ] remote executor capability/budget/region/lease/token 契约。
- [ ] 不把 prototype endpoint 暴露为默认生产服务。

## B31：构建唯一 Release Candidate

- [ ] 从 G4 integration clean commit 构建，不复用历史 staging。
- [ ] 记录 candidate ID、commit、dirty、lock、runtime 和工具版本。
- [ ] 生成 installer、launcher、runtime manifest、SBOM、许可证和全部 SHA-256。
- [ ] release artifact manifest 使用相对路径并自校验。
- [ ] 冻结后禁止修改候选；任何代码变更创建新 candidate。

## B32：Windows A0-A9 与真实项目矩阵

- [ ] A0 环境与数据保护。
- [ ] A1 全新安装、A2 首启、A3 旧项目兼容。
- [ ] A4 中断恢复、A5 fresh preflight、A6 从头播放、A7 最终导出。
- [ ] A8 卸载重装、A9 升级回滚。
- [ ] Windows 10/11、中文用户、中文/空格路径、Office/LibreOffice。
- [ ] Word/PPTX/PDF/扫描 PDF/图片/MP3/WAV/真人/竖屏矩阵。
- [ ] 进程、端口、文件锁、磁盘满、断网和睡眠唤醒。

## A31：人工视听、缺陷和签署

- [ ] 检查错页、裁切、黑帧、静音、爆音、音画/字幕同步、转场和遮挡。
- [ ] P0 缺陷为 0；P1 缺陷为 0 或有具名接受和修复版本。
- [ ] 产品、工程、安全、Windows 操作员和视听复核人签署。
- [ ] 文档、追踪矩阵和报告引用同一 candidate hash。

## Gate G5：RC_READY

- [ ] clean commit 和唯一候选可重建。
- [ ] 自动化、性能、安全和真实媒体全绿。
- [ ] release manifest、SBOM、许可证和签名材料齐全。
- [ ] 缺少真实证据时状态保持 `pending_manual_windows`。

## Gate G6：V1_RELEASED

- [ ] A0-A9 全部绑定唯一 candidate。
- [ ] 人工视听和签署完成。
- [ ] freeze guard 检查报告时效、机器批准、blockers 和 hash。
- [ ] 创建正式 tag、release notes 和恢复说明。
- [ ] 三线生成 V1 stop point；A/B 进入维护，C 获准进入 W4。

# Wave 4：V1 后平台与生态

## A40：V1 维护与兼容周期

- [ ] 一个发布周期观察错误率、回退率、迁移率和性能。
- [ ] 修复 V1 兼容缺陷，不再向 V1 fallback 添加新语义。
- [ ] 满足删除条件后另立项目移除旧渲染路径。

## C40：Provider 生产 Gate

- [ ] 每类至少一个真实适配器和一个 local/mock 适配器。
- [ ] 真实费用、限流、熔断、failover、未知状态和凭证轮换证据。
- [ ] Provider 失败不能破坏本地项目或重复计费。

## C41：云协作生产版本

- [ ] 正式 OIDC、组织、RBAC、设备和租户隔离。
- [ ] PostgreSQL、对象存储、PITR 和恢复演练。
- [ ] 两设备离线编辑、冲突、评论、审核、锁和版本历史。
- [ ] 远程执行、预算、region、lease 和结果 publication。
- [ ] SLO、监控、告警、审计、灾备和安全扫描。

## C42：插件运行时

- [ ] plugin manifest、API version、依赖和兼容矩阵。
- [ ] 文件、网络、进程、凭证和项目权限沙箱。
- [ ] 签名、来源、安装、升级、卸载、撤销和崩溃隔离。
- [ ] 第三方代码默认拒绝，模板声明与可执行插件分离。

## C43：模板市场与商业化

- [ ] 上传、审核、搜索、版本、更新和恶意检测。
- [ ] 许可证、购买、退款、离线授权和版权追踪。
- [ ] 商家后台、用户资产、审计和下架/撤销。
- [ ] 插件 Gate 未通过前市场只接受无代码声明式模板。

## B40/C44：macOS/Linux 桌面版

**B 线：** 媒体、Office 替代链、编码器和运行时。  
**C 线：** PlatformServices、凭证、安装、签名、更新和 CI。

- [ ] macOS Intel/Apple Silicon 和 Linux x64 支持矩阵。
- [ ] 路径、权限、大小写、进程和原子文件语义。
- [ ] LibreOffice/原生 Office 替代链和字体差异。
- [ ] VideoToolbox、Metal、VAAPI 和软件编码回退。
- [ ] macOS 签名/notarization、Linux 包和更新回滚。
- [ ] 真实安装、导入、预览、导出、恢复和卸载证据。

## Gate G7：PROVIDER_PRODUCTION_READY

- [ ] Provider 真实适配、预算、凭证、幂等和审计通过。

## Gate G8：CLOUD_AND_PLUGIN_READY

- [ ] 云身份、隔离、同步、PITR、远程执行和 SLO 通过。
- [ ] 插件沙箱、签名、权限、撤销和恶意样本通过。

## Gate G9：ECOSYSTEM_AND_CROSS_PLATFORM_READY

- [ ] 模板市场安全和许可证闭环通过。
- [ ] macOS/Linux 真实安装、运行、导出、签名和回滚通过。

## 5. 每个任务固定交付物

每个任务必须提供：

1. `task-id`、Line、Wave、owner、source commit 和 branch。
2. owned paths、shared paths 和明确非目标。
3. 失败测试或非法 fixture。
4. 实现提交和 migration/contract 影响。
5. 定向测试、静态检查、退出码和日志。
6. 真实媒体/Provider/平台需求及是否执行。
7. rollback、safe resume 和剩余项。
8. stop point JSON 及其 schema/hash。

建议目录：

```text
docs/acceptance/program/
  wave-0/
  wave-1/
  wave-2/
  wave-3/
  wave-4/
  gates/
  ownership/
  integration/
```

## 6. Integration Gate 固定流程

1. 创建或刷新短生命周期 integration worktree。
2. 核对 source commit 和 clean status。
3. 按 A → B → C 顺序接入已提交成果。
4. 每接入一线运行 contract、migration 和最小 smoke。
5. 三线接入后运行全量 Python/Web/Remotion/Playwright。
6. 运行真实媒体或平台专项门禁。
7. 生成 evidence manifest、stop point 和回退提交。
8. Gate 通过后将 integration commit 作为下一 Wave 三线共同 source。

Integration worktree 不长期保存未归属修复；失败返回来源线处理。

## 7. 标准验证命令

```powershell
# Python
F:\ppt-video-workbench-v3\.venv\Scripts\python.exe -m pytest -q
F:\ppt-video-workbench-v3\.venv\Scripts\python.exe -m ruff check --no-cache apps tests scripts
F:\ppt-video-workbench-v3\.venv\Scripts\python.exe -m mypy apps/api/src

# Web
pnpm.cmd --filter @workbench/web test
pnpm.cmd --filter @workbench/web typecheck
pnpm.cmd --filter @workbench/web build

# Remotion
pnpm.cmd --filter @workbench/remotion test
pnpm.cmd --filter @workbench/remotion typecheck

# Repository gate
pnpm.cmd lint
pnpm.cmd check
```

长命令必须保留完整退出码和日志；超时、后台仍运行和仅重跑失败项不能标记为全量通过。

## 8. 三线里程碑

| Milestone     | A 线                | B 线                       | C 线              | 预计日历 |
| ------------- | ------------------- | -------------------------- | ----------------- | -------: |
| M0 来源收口   | G1-G5 清单          | Windows/Graph/Effects 停点 | P2 基线           |   2-4 周 |
| M1 干净集成   | foundation/contract | graph/runtime 接入         | P2 默认关闭接入   |   3-5 周 |
| M2 核心工作台 | Web/P1 编辑器       | 导出/调度/质量             | Provider 适配     |  8-14 周 |
| M3 V1 RC      | workflow/签署       | RC/Windows/外围            | 云生产准备        |  6-10 周 |
| M4 平台生态   | V1 维护             | 跨平台媒体                 | 云/插件/市场/平台 |   多季度 |

日历估计假设三线均有稳定负责人、共享 Gate 每个 Wave 只需 1-2 轮修复。若 integration 反复失败，应减少并行范围，而不是增加第四条开发线。

## 9. Program 最终检查清单

### V1

- [ ] 三线均从共同 source 派生并可审计。
- [ ] G1-G5 正式进入 clean 主线。
- [ ] 时间线、素材、材料、字幕、continuity、导出和批量达到生产 Gate。
- [ ] RenderGraph、质量、高保真、Presenter 和外围形成真实证据。
- [ ] 唯一 Windows RC 完成 A0-A9、人工视听和签署。
- [ ] 安装、升级、回滚、卸载和数据保护通过。

### V1 后

- [ ] Provider 真实适配满足预算、幂等、failover 和审计。
- [ ] 云端满足身份、隔离、同步、PITR、远程执行和 SLO。
- [ ] 插件满足沙箱、权限、签名、撤销和恶意样本 Gate。
- [ ] 市场只分发通过安全和许可证审核的内容。
- [ ] macOS/Linux 有真实安装、运行、导出、签名和回滚证据。

任何未满足对应 Gate 的能力继续标记为 `internal`、`stable_optional` 或 `blocked`，不得仅因代码存在而宣布完成。
