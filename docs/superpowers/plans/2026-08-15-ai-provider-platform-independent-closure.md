# AI / Provider 平台独立收口线逐项实施计划

> 对应设计：`docs/superpowers/specs/2026-08-15-ai-provider-platform-independent-closure-design.md`  
> 工作树：`F:\ppt-video-workbench-v3\.worktrees\program-integration-v1`  
> 基础提交：`72cb7bbee6fb2fa21485f77d627a8f1443d61eb8`  
> 目标分支：`codex/program-ai-provider-platform`  
> 执行方式：AI00 → AI10 串行；每个 Gate 通过后直接进入下一项，不等待确认。

## 1. 全程执行规则

1. 当前工作树是 AI 收口线唯一写入位置和唯一写入者；开始前、每阶段后、提交前都核对绝对路径和分支。
2. 现有未提交修改与未跟踪文件是受保护成果；不得 clean、reset、覆盖式 checkout、自动 stash 或删除。
3. 不修改 `program-core-workbench`，不触碰 DP45 进程、运行根、计划任务和证据。
4. 不合并回 `codex/program-integration-v1`，不构建或替换最终个人使用候选。
5. AI/远端功能默认关闭；无凭证、无网络和 Provider 故障不得破坏本地音频生产链。
6. 无真实凭证不执行真实远端调用；无明确预算授权不执行可能付费的 canary。
7. 无真实授权样本不进行声音克隆、训练、导出或云端上传。
8. fake/fixture/mock 证据标记 `simulated=true`，不得写成真实供应商通过。
9. 公共入口发生冲突时只做最小接线并登记；不跨工作树解决核心线问题。
10. 暂存必须逐文件或经审计的精确路径清单执行，禁止 `git add .` 和 `git add -A`。
11. 每个阶段生成 receipt：输入身份、变更路径、测试、结果、外部边界、未完成项、下一阶段前置条件。
12. AI09 完成第一次审计后必须再做一次未完成项清扫；能解决的继续解决。

## 2. Gate 顺序

| 阶段 | 目标 Gate | 完成后动作 |
|---|---|---|
| AI00 | `AI_WORKTREE_ISOLATED` | 直接进入 AI01 |
| AI01 | `LOCAL_MODEL_CENTER_READY` | 直接进入 AI02 |
| AI02 | `PROVIDER_ADAPTERS_READY` | 直接进入 AI03 |
| AI03 | `PROVIDER_GOVERNANCE_READY` | 直接进入 AI04 |
| AI04 | `VOICE_IDENTITY_READY` | 直接进入 AI05 |
| AI05 | `REMOTE_BATCH_READY` | 直接进入 AI06 |
| AI06 | `AI_CONTENT_ASSIST_READY` | 直接进入 AI07 |
| AI07 | `AI_WEB_UI_READY` | 直接进入 AI08 |
| AI08 | `AI_PACKAGE_PREFLIGHT_READY` | 直接进入 AI09 |
| AI09 | `AI_PROVIDER_LOCAL_REGRESSION` | 直接进入 AI10 |
| AI10 | `AI_PROVIDER_INTEGRATION_HANDOFF_READY` | 停在交接，不合并 |

若阶段存在仅外部可完成的项目，不阻断可独立验证的本地 Gate，但必须用 `BLOCKED_EXTERNAL` 单列；若本地工程缺陷未解决，则该阶段不能进入 PASS。

## 3. AI00：保护现有成果并切换独立分支

### AI00.1 身份与禁区检查

- [ ] 确认 cwd 精确等于指定工作树。
- [ ] 确认 HEAD 精确等于 `72cb7bbee6fb2fa21485f77d627a8f1443d61eb8`。
- [ ] 确认当前分支为 `codex/program-integration-v1`。
- [ ] 记录 `git worktree list --porcelain`，确认核心线和 DP45 是其他工作树。
- [ ] 确认没有另一个写入者正在修改此工作树；若无法确认，停止为 `WAIT_WRITER_OWNERSHIP`。

### AI00.2 受保护清单

- [ ] 保存 `git status --porcelain=v1 -z` 原始输出。
- [ ] 对所有已修改与未跟踪文件记录路径、状态、字节数和 SHA-256。
- [ ] 生成 `owned-ai-paths.json`，标识 AI-owned、shared-entry、user-owned-excluded 三类。
- [ ] 将非 AI 的最终路线图、个人 Windows 收口文档列入排除清单，保留但不提交。
- [ ] 将清单写入新的 AI 验收根，不改写 DP45 或最终候选证据。

### AI00.3 目标分支检查与切换

- [ ] 检查本地是否存在 `codex/program-ai-provider-platform`。
- [ ] 在允许网络时只读检查远端同名分支；若存在，停止 `WAIT_BRANCH_CONFLICT`，不覆盖。
- [ ] 原地运行非覆盖式 `git switch -c codex/program-ai-provider-platform`。
- [ ] 不 stash、不提交到旧分支、不复制或删除未跟踪文件。
- [ ] 切换后确认 HEAD 未变化、分支正确。
- [ ] 重新生成状态和哈希清单，与切换前逐项比对。

### AI00.4 Gate

通过条件：路径、基础提交、目标分支、受保护路径集合和文件哈希全部一致；唯一写入者成立；禁区无写入。输出 `AI_WORKTREE_ISOLATED=PASS`。任一不一致立即停止，保留现场，不做自动恢复。

## 4. AI01：本地模型中心

### AI01.1 审计现有实现

- [ ] 逐文件检查 `ai_models/`、`audio/local_tts.py`、模型 API、schema 和测试。
- [ ] 对照已有验收资料，把“已实现”“仅 fixture”“真实硬件待验证”分开。
- [ ] 先运行现有 AI01 定向测试，记录初始失败，不因失败清理成果。

### AI01.2 契约与仓库

- [ ] 校验/补齐 descriptor、install、license、runtime probe schema。
- [ ] 补齐模型 registry、active version、原子写入和旧配置迁移。
- [ ] 模型目录只保存受控相对引用，阻止路径穿越和任意删除。
- [ ] 下载/导入记录来源、许可、哈希、体积和兼容 runtime。

### AI01.3 下载、离线导入与恢复

- [ ] 支持显式下载、断点恢复、临时文件、哈希校验和原子发布。
- [ ] 支持完全离线 fixture 导入，不依赖远端。
- [ ] 覆盖下载中断、空间不足、哈希错误、重复导入和崩溃恢复。
- [ ] 删除只允许未被租约引用的版本；active 版本删除需先切换。

### AI01.4 Runtime 接线

- [ ] 本地 ASR 通过 registry/runtime 选择模型，并保留 legacy fallback。
- [ ] 本地 TTS 通过稳定桥接接口工作；引擎缺失返回可操作错误。
- [ ] CPU 基础路径可运行；GPU/DirectML/CUDA 仅做 capability probe，不伪造通过。
- [ ] Provider 平台关闭时 ASR/TTS 和音频导入行为不变。

### AI01.5 API 与 Web

- [ ] 完成模型列表、详情、导入/下载、probe、激活、禁用/删除 API。
- [ ] 在统一 AI 设置区实现模型中心页面和所有状态。
- [ ] 显示来源、许可、体积、runtime、硬件状态和错误恢复动作。
- [ ] 默认不自动下载，不将绝对本地路径暴露给浏览器。

### AI01.6 验证与 Gate

- [ ] schema validation。
- [ ] repository/provisioner/runtime 单元测试。
- [ ] 模型 API 集成测试。
- [ ] 模型中心 Web 组件测试。
- [ ] local-only ASR/TTS 兼容测试。

本地条件全部通过后输出 `LOCAL_MODEL_CENTER_READY=PASS`；真实模型和硬件记录 `REAL_HARDWARE_MODEL=BLOCKED_EXTERNAL`。

## 5. AI02：Provider V2 适配层

### AI02.1 契约与 Registry

- [ ] 审计 `v2.py`、`conformance.py`、Provider API/Broker 与 schema。
- [ ] 统一 capability、operation、result、error、billing、idempotency、cancel 和 probe。
- [ ] Registry 使用延迟 factory；disabled Provider 不加载 SDK。
- [ ] 保留现有调用方兼容 shim，并标明废弃路径。

### AI02.2 能力族

- [ ] LLM：文本/结构化输出、token/费用元数据、可重试分类。
- [ ] ASR：音频输入、语言、时间戳、说话人能力声明。
- [ ] TTS：文本、voice binding、格式、采样率和时长元数据。
- [ ] Renderer：输入资产、模板、异步 job 和输出校验。
- [ ] 不支持的能力明确返回 `unsupported_capability`。

### AI02.3 Conformance

- [ ] fake adapter 覆盖成功、限流、超时、鉴权、取消、幂等和未知计费。
- [ ] 测试证明所有远端 operation 都经由统一接口和治理钩子。
- [ ] 响应记录 `provider_id`、环境、adapter/version 和 simulated 标志。
- [ ] 真实 Provider 状态默认 `unverified`，不得被 fake 测试提升。

### AI02.4 Web 与迁移

- [ ] Provider 页面展示能力、启用、环境、凭证引用和 conformance。
- [ ] 旧 LLM/HeyGen 配置迁移为新 policy 的兼容读取，不自动启用。
- [ ] 浏览器端不保存原始 token；只提交到受控 secret backend 或引用。

### AI02.5 Gate

契约、registry、兼容、fake conformance、API/UI 测试通过后输出 `PROVIDER_ADAPTERS_READY=PASS`。逐 Provider 真实验证保持 `REAL_PROVIDER_SANDBOX=BLOCKED_EXTERNAL`。

## 6. AI03：Provider 治理与费用控制

### AI03.1 费用账本

- [ ] 审计 governance、broker 接线、reservation schema 和 reconcile API。
- [ ] 持久化 estimated/reserved/committed/released/unknown/reconciled 状态。
- [ ] 支持全局、Provider、项目和单任务预算上限。
- [ ] 金额使用明确币种和定点/Decimal 语义，不用浮点累计。
- [ ] 账本重放和进程重启后余额一致。

### AI03.2 限流与并发

- [ ] 实现全局、Provider、能力、项目四级限流。
- [ ] 限流拒绝不产生费用预留泄漏。
- [ ] 标明单进程与集中部署的能力边界。
- [ ] UI 显示当前限制、等待/拒绝原因和重试建议。

### AI03.3 Retry / Failover

- [ ] 建立错误到重试/切换/停止的显式矩阵。
- [ ] 仅幂等、明确未计费、预算允许时自动切换。
- [ ] 未知计费进入 `reconcile_required` 并阻止后续远端调用。
- [ ] 输出发布采用幂等键和原子状态，避免重复制品。

### AI03.4 故障验证

- [ ] 429、超时、5xx、断网、响应丢失、崩溃恢复、重复回调。
- [ ] 预算耗尽、限流、费用估算缺失、汇率/币种不匹配。
- [ ] reconcile 后恢复和拒绝两条路径。
- [ ] Broker 回归证明本地操作不进入远端治理。

### AI03.5 Gate

账本、预算、限流、失败关闭、reconcile API/UI 和故障矩阵通过后输出 `PROVIDER_GOVERNANCE_READY=PASS`。跨进程集中限流若未部署，登记部署边界而非伪造完成。

## 7. AI04：声音身份和授权

### AI04.1 模型与授权

- [ ] 审计 voices 包、API、schema 和测试。
- [ ] 完成 identity、authorization、sample provenance、voice binding 和 audit event。
- [ ] 授权包含主体、用途、地域、有效期、训练/合成/上传权限。
- [ ] 默认 local-only；remote upload 必须独立授权。

### AI04.2 生命周期

- [ ] 创建、导入、绑定、使用、过期、撤销和删除状态机。
- [ ] 撤销立即阻止新任务；进行中远端任务进入人工判定。
- [ ] 样本和模型导出需权限校验并记录审计。
- [ ] 备份/恢复不得绕过撤销或用途范围。

### AI04.3 UI 与安全

- [ ] 声音中心清楚区分内置、本地本人授权、第三方授权和远端 binding。
- [ ] 显示授权范围、到期、撤销和上传状态。
- [ ] 无授权样本环境只用合成 fixture；不提供一键真实训练动作。
- [ ] 日志和错误不泄露样本路径、原始音频或身份敏感信息。

### AI04.4 Gate

本地身份、授权、撤销、API/UI 和自动化通过后输出 `VOICE_IDENTITY_READY=PASS`。真实声音克隆、训练、云上传与人工签署全部保持外部 Gate。

## 8. AI05：远端批处理

### AI05.1 状态机与仓库

- [ ] 审计 batch models/repository/service/API 和已有 HeyGen 路径。
- [ ] 补齐 batch/job/shard 状态、幂等键、费用预留和 provider job id。
- [ ] 所有状态持久化、可恢复、可审计。
- [ ] 部分成功不自动覆盖项目；发布步骤独立。

### AI05.2 协调器

- [ ] 提交、poll、webhook、取消、恢复和人工 reconcile。
- [ ] 重复 webhook/poll 去重，响应丢失不盲目重提。
- [ ] 输出下载到隔离区，校验媒体和哈希后再发布。
- [ ] Provider disabled/无凭证/无预算时只生成可操作的阻断状态。

### AI05.3 HeyGen 与通用 Provider

- [ ] 将已有 HeyGen 重试/缓存接入 V2 Broker 和统一 batch，不保留旁路。
- [ ] fake HeyGen adapter 覆盖长轮询、失败、取消、未知账单和恢复。
- [ ] 通用 Renderer/TTS batch 复用同一协调器。
- [ ] 真实 sandbox 和 production 状态在 UI、证据中明确区分。

### AI05.4 Gate

durable batch、恢复、取消、部分成功、未知计费、API/UI 和 fake 故障测试通过后输出 `REMOTE_BATCH_READY=PASS`。真实 HeyGen sandbox 标记待验证，付费 canary 标记待授权。

## 9. AI06：内容辅助

### AI06.1 候选契约

- [ ] 审计 content_assist package、API、schema 和测试。
- [ ] 候选绑定输入版本哈希、策略、模型/Provider、费用和质量警告。
- [ ] 支持 created/reviewed/accepted/rejected/expired。
- [ ] 原文变化后候选失效，accept 必须校验当前版本。

### AI06.2 三类能力

- [ ] 旁白润色：本地规则优先，保留语义和专名，显示 diff。
- [ ] 智能断句：按标点、最大长度、语速和字幕安全区生成候选。
- [ ] 字幕翻译：保持 timing/speaker/style，支持术语表和数字校验。
- [ ] 无 Provider 时翻译返回 `needs_provider`，不生成 fake 内容。

### AI06.3 Provider 与治理接线

- [ ] 远端增强必须显式启用并经过 Broker、预算和限流。
- [ ] 费用预估在确认前展示；未知计费不允许自动再试。
- [ ] 输入输出日志按隐私策略脱敏。
- [ ] accept 后才产生新活动版本，保留撤销点。

### AI06.4 Web

- [ ] 在现有旁白编辑器加入润色和断句候选 diff。
- [ ] 在现有字幕工作区加入翻译候选、术语和时间轴校验。
- [ ] 提供接受、拒绝、逐项选择、过期和错误状态。
- [ ] 默认关闭 AI 增强，不打断手工编辑。

### AI06.5 Gate

本地候选流、版本冲突、accept/reject、无 Provider 行为、API/UI 测试通过后输出 `AI_CONTENT_ASSIST_READY=PASS`。真实翻译质量保持 sandbox 和人工审核边界。

## 10. AI07：Web UI 和完整本地链路

### AI07.1 统一控制台

- [ ] 将模型、Provider、治理、声音、批次入口纳入统一“AI 与供应商”设置区。
- [ ] 复用现有 Provider/LLM/HeyGen 页面能力，迁移而非复制第二套配置。
- [ ] 全局开关和逐 Provider 开关默认 false。
- [ ] 每页实现 disabled/loading/empty/error/offline/permission-denied。
- [ ] 添加 API client 类型和契约漂移测试。

### AI07.2 安全与可用性

- [ ] 凭证只显示掩码和引用状态，不进入 URL、localStorage、DOM 快照或日志。
- [ ] 所有危险动作二次确认并说明费用/上传/授权影响。
- [ ] 键盘操作、焦点、标签、错误提示满足现有 UI 基线。
- [ ] Provider SDK 缺失时 UI 仍可打开，并显示 `unavailable`。

### AI07.3 本地独立 E2E

在无凭证、远端全部关闭、网络不可用条件下：

- [ ] 启动 API 与 Web。
- [ ] 创建和打开项目。
- [ ] 导入现有音频。
- [ ] 使用已有 transcript 或 fixture 本地 ASR。
- [ ] 本地 TTS 可用时生成；不可用时证明音频导入路径继续。
- [ ] 编辑旁白和字幕。
- [ ] 预览并导出测试制品。
- [ ] 捕获网络请求，证明没有远端 Provider 调用。
- [ ] 重新启动后项目、开关和候选状态恢复。

### AI07.4 Gate

Web 单测、typecheck、build、API 契约、本地独立 E2E 和远端零调用证明通过后输出 `AI_WEB_UI_READY=PASS`。

## 11. AI08：Windows 打包前置验收

### AI08.1 静态与构建前检查

- [ ] Web production build、Python import/compile、schema/OpenAPI 检查。
- [ ] 可选 Provider 依赖未安装时应用仍能启动。
- [ ] 检查 Windows 中文路径、空格路径、长路径和普通用户权限。
- [ ] 检查 runtime、FFmpeg、模型目录和应用数据目录发现逻辑。
- [ ] 检查 secret、绝对开发路径、测试 fixture 和超大模型未被误打包。
- [ ] 检查数据迁移与回滚脚本不会写入候选或 DP45 根。

### AI08.2 非候选 smoke 边界

- [ ] 优先使用现有 preflight/check 工具，不运行最终 release 构建。
- [ ] 如必须验证打包图，只能使用新建隔离 `preflight-only` 根。
- [ ] 任何输出显式标记 `candidate=false`、`publishable=false`。
- [ ] 不签名、不更新 release pointer、不复制到个人候选路径。
- [ ] 完成后保留可审计结果；不得删除用户既有证据。

### AI08.3 Gate

所有前置检查通过后输出 `AI_PACKAGE_PREFLIGHT_READY=PASS`，同时固定报告 `WINDOWS_FINAL_CANDIDATE_REVERIFY=BLOCKED_EXTERNAL`。若只有 Linux/开发环境结果，不得提升 Windows Gate。

## 12. AI09：全量回归和未完成项二次清扫

### AI09.1 第一轮全量回归

- [ ] `ruff`、`mypy` 与 AI 相关 Python 检查。
- [ ] AI01–AI06 单元、契约和集成测试。
- [ ] 受影响 audio/narration/subtitle/provider/render 回归。
- [ ] Web typecheck、Vitest、build。
- [ ] schema/OpenAPI/client generation drift。
- [ ] local-only E2E、应用重启恢复和远端零调用。
- [ ] Windows package preflight 重跑。

测试失败先归因：本分支缺陷、环境缺失、外部 Gate、共享入口冲突或既有非相关失败；不得用测试总数掩盖失败项。

### AI09.2 第一次未完成项审计

- [ ] 扫描 TODO/FIXME/XXX、skip/xfail、`WAIT_*`、`BLOCKED`、`NOT_RUN`、stale evidence。
- [ ] 对照 AI00 owned paths 和设计逐项检查遗漏。
- [ ] 对照 UI、API、schema、迁移、文档、测试和 CI 检查双向闭环。
- [ ] 每项标注类别、责任阶段、依赖、证据和完成条件。

### AI09.3 继续解决可完成项

- [ ] `ENGINEERING_DEFECT` 返回最早受影响阶段修复。
- [ ] 最小化解决 shared-entry 兼容；无法安全解决则登记 `WAIT_CONFLICT`。
- [ ] 修复后重跑该阶段及所有下游受影响测试。
- [ ] 不把真实硬件、sandbox、付费或人工签署改写成本地完成。

### AI09.4 第二次清扫

- [ ] 重复未完成项扫描与设计追踪。
- [ ] 确认可解决工程缺陷为零。
- [ ] 确认所有剩余项只属于外部证据、人工签署或集成冲突，并有完成条件。
- [ ] 更新 gates、remaining-work、source inventory 和阶段 receipts。

### AI09.5 Gate

全量本地回归通过、工程缺陷归零、剩余外部项分类完整后输出 `AI_PROVIDER_LOCAL_REGRESSION=PASS`。

## 13. AI10：提交、推送、CI 和集成交接

### AI10.1 提交前保护审计

- [ ] 确认分支仍为 `codex/program-ai-provider-platform`。
- [ ] 确认 merge-base/祖先包含基础提交 `72cb7bbe…`。
- [ ] 重新生成工作树状态、owned path 和排除清单。
- [ ] 运行 secret scan、绝对路径 scan、fake evidence 标签检查。
- [ ] 确认没有 DP45、候选、core-workbench 或非 AI 用户文件进入变更集。

### AI10.2 CI 触发修正

- [ ] 最小修改 `.github/workflows/ci.yml` 和需要的 contract workflow，使目标分支 push 可触发。
- [ ] 保留现有分支和 PR 触发，不弱化任何检查。
- [ ] 增加 AI local-only/contract 测试到合适 job，禁止 CI 调用真实远端或付费服务。
- [ ] workflow 变更本地语法检查通过。

### AI10.3 精确暂存与提交

推荐按以下逻辑提交；每次只对清单中的精确文件执行 `git add -- <file...>`：

1. `ai: preserve and complete local model and provider platform backend`
2. `web: add opt-in ai provider control center and content assist`
3. `test: add ai provider local-only regression and package preflight`
4. `docs: add ai provider closure evidence and integration handoff`

每次提交前：

- [ ] 检查 `git diff --cached --name-status`。
- [ ] 检查 staged diff 不含凭证、真实声音样本、候选制品和非 AI 文件。
- [ ] 运行与该提交范围匹配的测试。
- [ ] 记录 commit id 和 staged 文件清单。

### AI10.4 推送与 CI

- [ ] 推送 `codex/program-ai-provider-platform` 并设置 upstream。
- [ ] 记录 remote、push commit 和时间。
- [ ] 等待所有 GitHub Actions 到终态，不只看“已启动”。
- [ ] 下载/记录 run id、URL、job、平台、结论和 artifact 名称。
- [ ] CI 失败时只在本 AI 分支修复，逐文件提交、推送并重新等待。
- [ ] 无网络、无权限、workflow 未触发或取消时标记阻断，不声称 ready。

### AI10.5 集成交接包

在 `docs/acceptance/ai-provider-platform/integration-handoff/` 生成：

- [ ] `handoff.json`：符合 `AiProviderIntegrationHandoffV1`。
- [ ] `README.md`：范围、默认关闭策略、启动和验证方式。
- [ ] `source-identity.json`：base/head、分支、提交列表、remote。
- [ ] `owned-paths.json` 与 SHA-256 清单。
- [ ] `local-regression.json` 与命令/环境/结果。
- [ ] `ci-runs.json`：URL、run id、jobs、artifact、结论。
- [ ] `conflict-register.md`：公共入口最小修改和待集成冲突。
- [ ] `external-gates.md`：硬件、sandbox、付费、人工签署和 Windows 候选。
- [ ] `integration-order.md`：建议集成顺序、迁移、验证和回退点。

交接包只提供给集成人员；不运行 merge、rebase 到目标集成分支或最终发布。

### AI10.6 最终 Gate

只有目标分支已推送、CI 全部通过、交接包与最终 HEAD 绑定且没有未提交的 AI-owned 文件时，输出 `AI_PROVIDER_INTEGRATION_HANDOFF_READY=PASS`。非 AI 用户文件仍可按 AI00 排除清单保留未提交，不得为获得干净状态而删除或误提交。

## 14. 建议 owned paths

### 后端与 schema

- `apps/api/src/workbench/ai_models/**`
- `apps/api/src/workbench/audio/local_tts.py`
- `apps/api/src/workbench/providers/**` 中本线文件及精确共享修改
- `apps/api/src/workbench/voices/**`
- `apps/api/src/workbench/content_assist/**`
- `apps/api/src/workbench/api/ai_models.py`
- `apps/api/src/workbench/api/provider_governance.py`
- `apps/api/src/workbench/api/provider_batches.py`
- `apps/api/src/workbench/api/voices.py`
- `apps/api/src/workbench/api/content_assist.py`
- `apps/api/src/workbench/main.py`、`p2.py` 的精确 AI hunk
- `schemas/*local-model*`、`*provider*`、`*voice*`、`*content-assist*`、新增 closure/handoff schema

### Web

- `apps/web/src/features/ai/**`（推荐新统一入口）
- 现有 settings/provider/llm/heygen、narration、subtitles 的精确 AI 修改
- `apps/web/src/api/` 的 AI contract/client 文件
- router/navigation 的精确 AI hunk

### 测试、CI 与文档

- AI/Provider 对应 unit/contract/integration/Web/E2E 测试
- `.github/workflows/ci.yml`、`platform-contracts.yml` 的精确目标分支/AI job 修改
- `docs/acceptance/ai-provider-platform/**`
- 本设计与本实施计划、既有 AI/Provider program 设计/计划

AI00 必须把此建议转换为实际逐文件清单；建议列表不能直接当作宽泛暂存命令。

## 15. 最终报告模板

```text
AI_WORKTREE_ISOLATED=<PASS|FAIL|BLOCKED_EXTERNAL|NOT_RUN>
LOCAL_MODEL_CENTER_READY=<PASS|FAIL|BLOCKED_EXTERNAL|NOT_RUN>
PROVIDER_ADAPTERS_READY=<PASS|FAIL|BLOCKED_EXTERNAL|NOT_RUN>
PROVIDER_GOVERNANCE_READY=<PASS|FAIL|BLOCKED_EXTERNAL|NOT_RUN>
VOICE_IDENTITY_READY=<PASS|FAIL|BLOCKED_EXTERNAL|NOT_RUN>
REMOTE_BATCH_READY=<PASS|FAIL|BLOCKED_EXTERNAL|NOT_RUN>
AI_CONTENT_ASSIST_READY=<PASS|FAIL|BLOCKED_EXTERNAL|NOT_RUN>
AI_WEB_UI_READY=<PASS|FAIL|BLOCKED_EXTERNAL|NOT_RUN>
AI_PACKAGE_PREFLIGHT_READY=<PASS|FAIL|BLOCKED_EXTERNAL|NOT_RUN>
AI_PROVIDER_LOCAL_REGRESSION=<PASS|FAIL|BLOCKED_EXTERNAL|NOT_RUN>
AI_PROVIDER_INTEGRATION_HANDOFF_READY=<PASS|FAIL|BLOCKED_EXTERNAL|NOT_RUN>

本地自动化已通过：<与最终 HEAD、命令和证据绑定的列表>
Windows 最终候选待复验：<必须保持待复验，本线未构建候选>
真实硬件模型待验证：<模型/硬件/runtime/完成条件>
真实供应商 sandbox 待验证：<Provider/环境/凭证要求/canary 条件>
付费操作待明确授权：<操作/最大预算/授权人/当前状态>
人工声音授权和音画审核待签署：<主体/用途/证据/签署条件>
```

每个 PASS 后必须附证据路径、测试或 CI、源提交；`BLOCKED_EXTERNAL` 必须附依赖、责任人和完成条件。最终停点是交接包就绪，绝不自行合并。
