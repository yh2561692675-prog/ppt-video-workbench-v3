# PPT Video Workbench 剩余大型项目总体开发设计

## 1. 文档信息

- 设计日期：2026-08-11。
- 适用仓库：`F:\ppt-video-workbench-v3`。
- 审计分支：`recovery/root-snapshot-20260810`。
- 审计 HEAD：`117fb60cbb0ca877c0920a26f5ceb31d8e42e901`。
- 配套实施计划：`docs/superpowers/plans/2026-08-11-remaining-major-projects-program.md`。
- 目标：把当前仍分散在恢复根目录、隔离 worktree 和专项验收窗口中的成果，按依赖顺序收口为可发布 V1，再平滑推进 Provider、云协作、插件市场和跨平台桌面版。

本文是剩余大型项目的 Program 级总设计。它不替代各专项设计，而是规定它们之间的先后关系、权威边界、集成方式、发布门禁和资源安排。

## 2. 当前事实基线

### 2.1 已完成并作为输入复用的共享底座

以下能力已有可验证 stop point，后续不得重新建立第二套实现：

1. G1：持久 Job、attempt、checkpoint、资源租约基础、重启恢复和 exactly-once publication。
2. G2：图片/视频/音频派生、FFprobe、波形、内容寻址对象存储和缓存索引。
3. G3：权威区间预览任务、范围投影、音视频代理、缓存和 Web 播放面板。
4. G4：RenderGraph 依赖、affected ranges、选择性失效、持久缓存索引和并发安全 GC。
5. G5：LegacyProjectAdapter、迁移预览、journal、双读、回滚和兼容 API。
6. Web 当前全量测试为 43 个文件、84 项通过；历史 3 项 WorkflowShell 失败已独立重复关闭。
7. P2 隔离分支已建立 Provider、PlatformServices、云协作契约和本地原型基础；后续工作是生产化，不是重写平台骨架。

这些成果当前仍需进入干净集成提交才能成为正式产品基线。stop point 表示切片验证通过，不等于已经发布。

### 2.2 当前活跃收口线

| 工作线                  | 工作位置                                | 当前状态                                 | Program 约束                             |
| ----------------------- | --------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| Windows 安装版与 A0-A9  | 恢复根目录及隔离安装目录                | 候选已构建；正在真实 Office/PPT 全链验收 | 完成前禁止在根目录启动新的大范围写入任务 |
| RenderGraph V2/最终渲染 | `.worktrees/rendergraph-v2-closure`     | 正在执行完整质量门和发布构建             | 只从该分支接收可审查提交，不复制目录     |
| Effects Task 18-25 恢复 | `.worktrees/effects-task18-25-recovery` | 已进入 Task 19 自动化门禁                | 缺失来源不得以文档声明替代；按 Task 冻结 |

### 2.3 尚未形成正式候选的原因

- 恢复根目录仍有大量 tracked 和 untracked 内容，来源、生成物和用户工件混在同一工作树。
- G1-G5、RenderGraph、Windows、Effects 和 P2 位于不同提交或未提交切片中。
- 共享文件包括数据库迁移、`main.py`、OpenAPI、Web client、WorkflowShell、Remotion 入口、installer 和发布脚本，不能按目录覆盖合并。
- 真实 Windows、Office、长视频、复杂 PPT、真人媒体、签名和人工视听证据仍未全部绑定到同一候选。

## 3. Program 目标

### 3.1 V1 发布目标

V1 必须形成一个满足以下条件的单一候选：

- 可从干净 commit 和锁文件完全重建。
- 旧项目可只读打开、迁移、回滚，源文件和上一成功成片受保护。
- 编辑、预览和导出消费同一项目 revision、ProductionTimeline、RenderGraph 和素材 revision。
- 所有长任务进入统一 Job/attempt/checkpoint/publication 系统。
- Windows 安装、首启、导入、编辑、渲染、恢复、升级、回滚和卸载形成同一 candidate 的证据链。
- 自动化、性能、安全、真实媒体和人工视听门禁均有明确结果，不用 mock 或历史日志冒充实机通过。

### 3.2 V1 后平台化目标

V1 发布后按以下顺序扩展：

1. 将 P2 Provider 骨架接入真实供应商并形成费用、限流、回退和审计闭环。
2. 将云协作原型升级为正式身份、PostgreSQL、对象存储、同步和远程执行平台。
3. 建立第三方插件沙箱和模板签名体系。
4. 在插件安全边界稳定后建设模板市场和商业化。
5. 将 PlatformServices 扩展到 macOS/Linux 真实运行时、签名和安装验收。

### 3.3 三条隔离开发线

本 Program 固定使用三条长期开发线；除受控 integration Gate 外，不允许临时增加第四条共享源码开发线。

| 开发线                  | 建议分支/worktree                                                            | 长期职责                                                                                      | 当前专项接管                                      |
| ----------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| A：Core Workbench       | `codex/program-core-workbench` / `.worktrees/program-core-workbench`         | foundation 集成、数据库/API 权威、Web 生产工作流、时间线、素材、材料、字幕、连续镜头          | 接收 G1-G5 和 P1 工作台成果                       |
| B：Render & Release     | `codex/program-render-release` / `.worktrees/program-render-release`         | RenderGraph、Remotion、FFmpeg、导出、调度执行、质量、高保真、Effects、Presenter、Windows 发布 | 接收 RenderGraph、Windows、Effects 三条当前活跃线 |
| C：Platform & Ecosystem | `codex/program-platform-ecosystem` / `.worktrees/program-platform-ecosystem` | Provider、PlatformServices、云协作、插件、模板市场、macOS/Linux                               | 从 `codex/p2-platform-integration` 继续           |

三条线使用不同虚拟环境缓存、Node 输出目录、测试数据库、端口、证据目录和构建目录。任何一条线不得把另一条线的目录复制回自身。

`codex/program-integration-v1` 是短生命周期的 Gate 工作树，不计为第四条开发线：它不开发新功能，只按审查顺序接收三条线的已提交成果、解决共享 wiring、执行全量门禁并生成 stop point。

## 4. 非目标

- 不在当前恢复根目录直接开展新的云端或跨平台功能开发。
- 不为赶进度跳过 clean integration、真实候选身份或实机报告。
- 不建立第二套时间线、素材库、Job、RenderGraph、缓存、Provider 或同步协议。
- 不把 dry-run、mock、旧安装包或未签署报告标记为正式发布通过。
- 不在插件沙箱完成前允许第三方任意代码执行。
- 不在本 Program 中实现模板交易、税务、支付清算的具体商业规则；只定义技术边界和后续阶段。

## 5. 核心设计原则

### 5.1 六个单一权威

1. 项目权威：`ProjectManifest`、数据库 schema version 和项目 revision。
2. 编辑权威：`ProductionTimeline` 及其命令日志。
3. 素材权威：内容 hash、Asset revision、授权快照和派生关系。
4. 渲染权威：不可变 RenderGraph snapshot 及 graph hash。
5. 执行权威：持久 Job、attempt generation、checkpoint 和 publication。
6. 发布权威：candidate ID、release artifact manifest 和绑定该候选的验收报告。

任何 UI、缓存、兼容投影、云副本和市场条目只能是这些权威的投影或受控副本。

### 5.2 先收口再扩展

共享契约尚未进入干净主线时，不允许启动依赖它们的新平台项目。先完成当前三个活跃收口线，再创建唯一 integration worktree。

### 5.6 三线并行、共享点串行

- A 线是 V1 共享契约 owner；数据库 migration、OpenAPI、主应用 wiring 和 Web API client 由 A 线或 integration Gate 串行修改。
- B 线只通过已冻结的 RenderGraph、Job、Asset、Export 和 evidence 契约接入核心，不直接改写 A 线领域模型。
- C 线通过 versioned Provider/Platform/Cloud/Plugin 契约开发，V1 发布前默认关闭，不改变本地默认流程。
- 跨线接口先提交 contract proposal、fixture 和失败测试；A 线接受后，其他线才实现消费者。
- 每个 Wave 结束进入一次 integration Gate；Gate 未通过时三条线只能修复本 Wave，不进入下一 Wave。

### 5.3 写入可恢复

所有正式文件写入使用临时文件、校验、原子替换和 publication 对账。数据库事务成功但文件缺失必须进入 `corrupted` 或 `quarantined`，不得静默重建正式输出。

### 5.4 编辑与执行分离

前端只提交 revision-guarded 命令；Worker 只消费冻结输入，不读取“当前项目状态”重新编译。已入队任务的 graph、preset、runtime 和素材 revision 在 attempt 生命周期内不可变化。

### 5.5 能力成熟度显式化

所有大型能力使用统一成熟度：

`scaffold → internal → stable_optional → stable_default → deprecated`

升级成熟度必须绑定 Gate；代码存在、单测通过或 UI 可见都不能单独触发升级。

## 6. 总体架构

```text
Project/Material/Asset truth
          |
          v
ProductionTimeline + Subtitle + Continuity + ExportPreset
          |
          v
Immutable RenderGraph Snapshot
          |
          +-------------------+
          |                   |
          v                   v
Authoritative Preview     Final Export / Quality
          |                   |
          +---------+---------+
                    v
Durable Job + ResourceLease + Publication
                    |
                    v
Candidate Artifact + Evidence + Release Gate
```

V1 后增加的平台层只能包围该本地核心：

```text
Provider Kernel       Cloud Control Plane       Plugin Runtime
       \                     |                      /
        +---------- PlatformServices ------------+
                           |
                 Local-first Production Core
```

## 7. 阶段路线

### 7.0 三线 Wave 映射

| Wave | A：Core Workbench               | B：Render & Release                  | C：Platform & Ecosystem        | Integration Gate       |
| ---- | ------------------------------- | ------------------------------------ | ------------------------------ | ---------------------- |
| W0   | 盘点 G1-G5、冻结共享 owner      | 收口 Windows/RenderGraph/Effects     | 复核 P2 基线，只做离线契约     | G0 ACTIVE_LINES_CLOSED |
| W1   | 建立干净 foundation、契约、迁移 | 接入 graph/export/runtime 适配器     | Provider/Platform 合同漂移检查 | G1 INTEGRATION_READY   |
| W2   | Web、时间线、素材、材料         | 导出、调度执行、质量、高保真         | 真实 Provider 适配器           | G2/G3/G4               |
| W3   | 字幕、continuity、工作流总接线  | Presenter、P03-P12、唯一 RC、Windows | 云控制面生产准备               | G5/G6 V1_RELEASED      |
| W4   | V1 维护与兼容                   | 多平台媒体执行支持                   | 云、插件、市场、macOS/Linux    | G7-G9 PLATFORM_READY   |

同一 Wave 内允许三线并行；跨 Wave 不允许越级消费未冻结契约。

### 7.1 Phase 0：完成当前活跃收口线

目标是让 Windows、RenderGraph 和 Effects 三条线分别形成提交、验证结果、剩余项和安全接管点。

Gate `G0 ACTIVE_LINES_CLOSED` 要求：

- 三条线均不再向共享根目录持续写入。
- 每条线提供 HEAD、dirty 状态、owned paths、测试结果、候选/证据身份和未完成项。
- Windows 失败候选和成功候选证据分开保存。
- Effects 缺失来源明确标记为重建，不能伪装成找回。

### 7.2 Phase 1：干净主线与共享契约归并

从经过审计的 foundation source 创建唯一 integration worktree，按领域小提交归并 G1-G5、RenderGraph、Windows、Effects 和必要的 P2 契约。

关键设计：

- 共享迁移按版本单调递增，不重排历史 migration。
- OpenAPI、JSON Schema、Python、TypeScript 和 fixtures 一次冻结。
- generated、release、cache、backup 和 user data 不进入源码提交。
- P2 代码以默认关闭 feature flag 接入，不改变 V1 本地行为。

Gate `G1 INTEGRATION_READY` 要求 clean status、全量自动化通过、跨语言契约无漂移、旧项目重复迁移和回滚通过。

### 7.3 Phase 2：Web 生产工作流与资源治理

G1-G5 已解决后端执行和迁移基础，本阶段完成尚未冻结的 P6/P7：

- 前端 project session、selection、viewport、playhead、pending commands、server revision 和 conflict 状态分层。
- 统一 Task Center 展示 attempt、checkpoint、等待资源、重试和恢复。
- ResourceLease 补齐 capability、心跳、续租、回收、公平性和稳定等待原因。
- GC 保护源文件、正式输出、当前 checkpoint 和上一成功成片。
- 权威预览 stale/ready/degraded/failed 状态接入七步工作流。

Gate `G2 WEB_FOUNDATION_READY` 后，P1 工作台才能并行扩展。

### 7.4 Phase 3：核心编辑工作台

按依赖顺序完成：

1. 统一多轨时间线编辑器。
2. 素材库与灵活材料组织。
3. 高级字幕工作台。
4. 跨页转场、连续镜头和媒体 Overlay。

时间线先行，因为其他三项都需要 clip selection、区间、revision、history 和预览失效。素材和材料可在时间线几何冻结后并行；字幕与 continuity 共享安全区和 RenderGraph 语义，解释器阶段串行归并。

Gate `G3 EDITING_READY` 要求 1,000 clips 编辑预算、真实代理加载、冲突恢复、软/烧录字幕矩阵、J/L Cut 边界和 Overlay 视觉快照通过。

### 7.5 Phase 4：交付、批量与资源调度

完成多规格导出和多项目批量生产：

- ExportPreset 参数化画布、fps、codec、bitrate、字幕和制作包。
- 同一 graph 支持 720p/1080p/4K、24/25/30/60fps、横竖方屏。
- GIF、短视频切片、章节、多语言软字幕和平台预设。
- BatchPlan、依赖图、优先级、夜间队列、项目并发上限、多 Worker 和页级重跑。
- 同一候选的 encoder/runtime manifest 与 ffprobe 验证。

Gate `G4 DELIVERY_READY` 要求多 preset 真实成片、20 项目恢复批次、资源租约和 exactly-once 发布通过。

### 7.6 Phase 5：质量、高保真和外围生产链

统一建设真实媒体自动验收平台，并让以下消费者共用：

- 自动质量检测。
- PPT 高保真和元素级动画。
- Presenter。
- P03-P12 外围模块。
- Windows 和跨平台验收。

fixture 必须覆盖 PPTX、Word、PDF、扫描 PDF、图片、视频、MP3、WAV、多声道、双语字幕、透明素材和受控坏样本。自动 oracle 包括 ffprobe、波形、字幕流、关键帧、视觉差异和 hash。

Gate `G5 CAPABILITY_READY` 要求质量阈值、复杂 PPT corpus、Presenter 长样本和外围真实 Provider 小额调用形成可审计证据。

### 7.7 Phase 6：唯一 RC、Windows 验收与 V1 发布

从 clean integration commit 构建唯一 RC，执行：

- Windows 10/11、中文用户名和中文/空格路径。
- A0-A9：安装、首启、旧项目、恢复、预检、播放、导出、卸载重装、升级回滚。
- 真实 Office/LibreOffice、字体和硬件能力探测。
- 手工视听复核、P0/P1 缺陷清零和签署。
- SBOM、许可证、签名、SmartScreen/杀软记录和冻结门禁。

Gate `G6 V1_RELEASED` 只有在报告、产物、签署和 hash 全部绑定同一 candidate 时通过。

### 7.8 Phase 7：Provider 生产化

在 `codex/p2-platform-integration` 基础上逐供应商迁移 LLM、TTS、ASR、OCR、Avatar 和 Renderer：

- 能力发现、健康、地区和模型目录。
- 费用预估、预算、限流和账单对账。
- 幂等、熔断、受控 failover 和未知远端状态。
- 原生凭证存储、审计和隐私脱敏。
- 真实供应商契约和故障注入。

Gate `G7 PROVIDER_PRODUCTION_READY` 要求至少每类一个正式适配器和一个可替代 mock/local 适配器，并验证预算和重复请求保护。

### 7.9 Phase 8：云协作生产版本

将 cloud prototype 升级为正式控制面：

- OIDC、组织、成员、设备、RBAC 和租户隔离。
- PostgreSQL migration、PITR、恢复演练和对象保留。
- 分片对象上传、hash 校验、版本和删除策略。
- 离线 outbox、冲突 UI、评论、审核、锁和版本历史。
- 远程 executor、预算、region、capability 和短期 token。
- SLO、监控、告警、审计和灾备。

Gate `G8 CLOUD_PRODUCTION_READY` 要求两设备、断网、冲突、撤权、远程任务、PITR 和跨租户安全证据。

### 7.10 Phase 9：插件、市场与跨平台

严格顺序：

1. 插件沙箱、权限、签名、版本和依赖。
2. 模板上传、审核、许可证、更新和恶意检测。
3. 市场计费、购买、版权追踪和商家后台。
4. macOS/Linux runtime、安装、签名、Office 替代链和硬件编码。

插件运行时和跨平台可并行准备契约，但模板市场不得在沙箱和签名 Gate 前接收第三方可执行内容。

## 8. 工作树与所有权模型

### 8.1 分支模型

```text
foundation-source-ready
        |
        +-- codex/program-core-workbench       (Line A)
        +-- codex/program-render-release       (Line B)
        +-- codex/program-platform-ecosystem   (Line C)
        |
        +-- codex/program-integration-v1       (Gate only; no feature work)
```

### 8.2 共享路径

以下路径每个阶段只能有一个 owner：

- `apps/api/src/workbench/main.py`
- `apps/api/src/workbench/storage/`
- `apps/api/src/workbench/jobs/`
- `apps/web/src/api/client.ts`
- `apps/web/src/features/workflow/WorkflowShell.tsx`
- `packages/contracts/`
- `schemas/`
- `remotion/src/Root.tsx`
- `scripts/build-release.ps1`
- `installer/workbench.iss`
- `.github/workflows/`

专项分支通过新增模块和契约提案工作；共享 wiring 由 integration owner 串行接入。

### 8.3 三线文件责任

| 路径/领域                                      | A 线                      | B 线                               | C 线                       |
| ---------------------------------------------- | ------------------------- | ---------------------------------- | -------------------------- |
| `storage/`、`jobs/`、`main.py`                 | owner                     | 只消费；变更走 proposal            | 只消费；变更走 proposal    |
| timeline/assets/materials/subtitles/continuity | owner                     | RenderGraph 解释器消费者           | 不修改                     |
| Web client、WorkflowShell、编辑工作台          | owner                     | 仅交付独立 Panel                   | 仅交付独立设置/管理 Panel  |
| rendering、Remotion、FFmpeg、exports、quality  | 仅提供契约                | owner                              | 仅 Provider/remote adapter |
| installer、launcher、release scripts           | 不修改                    | owner                              | 提供平台抽象，不直接接线   |
| providers/platform/sync/cloud/plugin           | 只提供本地业务适配点      | 只提供 executor/runtime 适配点     | owner                      |
| schemas/contracts                              | V1 核心 schema owner      | 提交 render/export schema proposal | 提交 P2 schema proposal    |
| `.github/workflows/`                           | integration Gate 串行接入 | proposal                           | proposal                   |

### 8.4 合并节奏

1. 每条线只提交已通过定向门禁的小提交。
2. 每个提交附 owned paths、contract version、migration impact、测试和回退说明。
3. integration Gate 按 A → B → C 顺序接收提交；C 的默认关闭扩展最后接入。
4. 每接入一条线执行 contract、migration 和最小 smoke；三线全部接入后执行全量矩阵。
5. Gate 失败由来源线修复，integration worktree 不长期承载未归属功能补丁。

## 9. 数据与兼容设计

- migration 只能追加，不修改已发布 migration 内容。
- 每次迁移记录 source version、target version、plan hash、backup、journal 和 rollback 指令。
- legacy 文件只读；V2 bundle 在 staging 验证后原子发布 pointer。
- 云同步使用 object/revision/op 模型，不同步本地绝对路径。
- Provider、云和插件扩展字段使用 versioned envelope，未知字段按明确兼容策略处理。
- 正式成片、上一成功成片、用户源文件和迁移备份永不进入普通缓存 GC。

## 10. 测试与证据设计

### 10.1 自动化层次

1. 单元和性质测试：时间量化、状态机、调度、公平性、缓存失效、路径安全。
2. 契约测试：Python/TypeScript/JSON Schema/OpenAPI/SQL migration。
3. 集成测试：数据库、对象存储、Worker、Remotion、FFmpeg、Office、Provider。
4. E2E：七步工作流、失败恢复、批量生产、更新回滚、云同步。
5. 实机与人工：Windows/macOS/Linux、真实 Office、真实供应商、视听复核。

### 10.2 证据身份

每个 Gate 产物至少包含：

- source commit、dirty 状态和 lock hash。
- runtime/tool versions。
- candidate/run/attempt ID。
- 命令、开始/结束时间、退出码和日志路径。
- 输入 fixture hash、输出 artifact hash 和证据 manifest hash。
- 明确的 passed、failed、blocked 或 not_run。

## 11. 性能预算

| 领域                        | 目标                            |
| --------------------------- | ------------------------------- |
| 1,000 clips 时间线平移/缩放 | p95 < 50ms UI 响应              |
| 1,000 节点 graph 编译       | p95 < 500ms                     |
| 增量编译                    | p95 < 150ms                     |
| 10 秒权威预览缓存命中       | p95 < 8s                        |
| Job 控制 API                | p95 < 200ms，不含实际媒体执行   |
| 20 项目批次重启恢复         | 无重复 publication，无丢失 item |
| 云 outbox 1,000 ops 重放    | 无丢失、稳定幂等、可继续分页    |

预算未达标时能力不得升级为 `stable_default`。

## 12. 安全与隐私

- 所有路径经过 containment、软链接和 NUL 检查。
- FFmpeg、LibreOffice、Node 和脚本进程只使用参数数组，不拼接不可信命令行。
- 上传内容执行类型、大小、解压比例和媒体探测门禁。
- Provider 凭证只使用引用，不进入项目、日志、缓存键或云同步。
- 云端按 tenant/project/object 三层授权，撤权后 token 和 lease 失效。
- 插件默认无网络、无进程、无任意文件系统权限；能力按 manifest 授权。
- 支持包和验收证据在发布前执行 secret、PII、绝对路径和用户数据扫描。

## 13. 可观测性

统一事件字段：

- `correlation_id`
- `project_id`
- `job_id`
- `attempt_generation`
- `graph_hash`
- `candidate_id`
- `provider_id`
- `plugin_id`
- `platform`
- `error_code`
- `resource_wait_reason`

监控 CPU、GPU、内存、磁盘、Office 进程、队列长度、租约、缓存命中、Provider 成本、远程任务和同步延迟。诊断包默认脱敏。

## 14. 灰度与回退

### 14.1 V1 能力灰度

```text
contracts only
→ internal fixture
→ authoritative preview
→ internal export
→ stable_optional
→ new project default
```

### 14.2 平台灰度

```text
local only
→ explicit provider
→ provider policy
→ cloud read replica
→ cloud comments/review
→ remote execution
→ cross-device default
```

每一级都保留回退：关闭 feature flag 后，旧项目和已有成片仍可访问；不允许通过回退丢弃 V2 独占语义。

## 15. 人员与工作量

| 阶段                          | 剩余工作量估计 |
| ----------------------------- | -------------: |
| 当前三条活跃收口线            |      6-14 人周 |
| 干净集成与共享契约            |       4-8 人周 |
| Web/时间线/素材/字幕/连续镜头 |     19-32 人周 |
| 导出/调度/质量/高保真/外围    |     26-45 人周 |
| V1 RC、Windows、签署          |       4-8 人周 |
| Provider 生产化               |       5-9 人周 |
| 云协作生产化                  |     12-20 人周 |
| 插件、市场、跨平台            |     30-56 人周 |

工作量是人周，不是承诺日历。三条独立工程线需要一名 integration owner；共享路径冲突期间不能用增加窗口数量替代串行集成。

### 15.1 三线建议配置

- A 线：1 名前后端负责人 + 1 名前端/交互工程师。
- B 线：1 名媒体/渲染工程师 + 1 名 Windows/发布工程师。
- C 线：1 名平台/后端工程师；V1 前以契约和离线实现为主。
- integration steward 可由 A 线负责人轮值，但在 Gate 期间暂停 A 线新功能开发。

### 15.2 日历估计

在三线稳定并行、共享 Gate 不反复返工的前提下：

- V1 核心剩余工作：约 5-8 个月。
- Provider 生产化可在 V1 后段开始，额外约 1.5-2.5 个月。
- 云、插件市场和跨平台属于 V1 后多季度路线，不纳入 V1 发布承诺。

## 16. Program 完成定义

### 16.1 V1 完成

- clean commit 可重建唯一 RC。
- 自动化、真实媒体、Windows A0-A9 和人工视听均绑定该 RC。
- P0/P1 缺陷清零或有签署的接受记录。
- 安装、升级、回滚、卸载和数据保留通过。
- 文档、SBOM、许可证、签名和支持包齐全。

### 16.2 平台阶段完成

- Provider 真实适配器满足预算、幂等、审计和 failover Gate。
- 云端满足身份、隔离、同步、PITR、远程执行和 SLO Gate。
- 插件满足沙箱、权限、签名和撤销 Gate。
- 模板市场不允许未审查可执行内容。
- macOS/Linux 具有真实安装、运行、导出、签名和回滚证据。

只有满足对应 Gate 的能力才可以从计划清单移入“正式完成”。
