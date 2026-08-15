# 第四类：AI 与供应商平台程序逐项实施计划

> 日期：2026-08-15  
> 状态：本地基础已实施；真实供应商、硬件与 Web UI 维持 WAIT_EXTERNAL/后续发布 Gate  
> 设计文档：docs/superpowers/specs/2026-08-15-ai-provider-platform-program-design.md  
> 执行方式：AI01–AI06 严格串行；一个项目完成后直接进入下一个项目，不逐项等待确认

## 1. 执行总规则

- [x] 只在选定的干净主集成 worktree 或为本程序新建的隔离 worktree 中开发，不在恢复根目录写入。
- [x] 开工前记录 HEAD、branch、dirty 状态、lock hash、Python/Node/runtime 版本和现有测试基线。
- [x] 保留用户现有未跟踪文件，不执行 reset、clean、批量覆盖或 git add .。
- [x] 先写 RED 测试和 schema，再实现最小功能，然后运行专项、集成和回归。
- [ ] 每个项目只修改其 owned paths；共享 contracts、main.py、OpenAPI、数据库迁移和应用总接线串行处理。
- [x] 本地音频链是最高优先级回归：任何项目完成后都必须验证无网络、无凭证和远端禁用模式。
- [ ] 所有远端写操作默认使用 fake/sandbox；真实调用必须另有用户授权、非敏感样本和硬费用上限。
- [ ] 缺少真实凭证、费用、授权或人工决定时写 WAIT_EXTERNAL，不伪造 PASS。
- [ ] 任一源码、模型 manifest、Provider policy、价格版本或候选安装包变化后，重跑所有受影响下游 Gate。
- [x] AI06 完成后执行一次全量未完成项审计；发现的未完成项按 AI01→AI06 的最早受影响项目重新解决，再重跑下游。

## 2. 项目顺序和 Gate

| 顺序 | 项目 | 依赖 | Gate |
| --- | --- | --- | --- |
| AI00 | 基线冻结与本地独立性红线 | 当前主集成线 | AI_BASELINE_FROZEN |
| AI01 | 本地 ASR/TTS 模型管理中心 | AI00 | LOCAL_MODEL_CENTER_READY |
| AI02 | 多供应商统一适配 | AI01 | PROVIDER_ADAPTERS_READY |
| AI03 | 失败切换、预算和限流 | AI02 | PROVIDER_GOVERNANCE_READY |
| AI04 | 本人声音克隆与授权管理 | AI03 | VOICE_IDENTITY_READY |
| AI05 | HeyGen 等外部服务可靠批处理 | AI04 | REMOTE_BATCH_READY |
| AI06 | 旁白润色、智能断句和字幕翻译 | AI05 | AI_CONTENT_ASSIST_READY |
| AI07 | 总接线、Windows 验收和二次收口 | AI01–AI06 | AI_PROVIDER_PLATFORM_READY |

AI00 和 AI07 是程序级阶段，不增加用户定义的六个功能项目。

## 3. AI00：基线冻结与保护

### AI00.1 仓库和来源核对

- [ ] 确认选定 worktree、分支、HEAD 和 upstream。
- [ ] 确认根恢复快照不作为构建源。
- [ ] 记录现有未提交文件并划为 user-owned，不纳入本项目提交。
- [ ] 记录 uv.lock、pnpm-lock.yaml、Provider schema 和 OpenAPI hash。
- [x] 生成 docs/acceptance/ai-provider-platform/baseline.json。

### AI00.2 当前能力库存

- [ ] 盘点 apps/api/src/workbench/providers 的 registry、broker、policy、billing、credentials、cache、probe、audit 和 upstream。
- [ ] 盘点本地 ASR、provision_asr_model.py、模型目录和安装版 runtime 依赖。
- [ ] 盘点本地 TTS、声音克隆运行时和缺失项。
- [ ] 盘点 HeyGen client、profile store、分段缓存、重试和 Web 批量状态。
- [ ] 盘点 narration revision、SubtitleDocument V2、差异和确认路径。
- [x] 形成 source inventory 和 owned path map。

### AI00.3 本地独立性基线

- [ ] 增加测试：所有 remote_https Provider 禁用时应用正常启动。
- [ ] 增加测试：无 Provider 凭证时项目打开、导入音频、手工字幕、预检和已有资产导出不被阻断。
- [ ] 增加测试：Provider registry 或账本不可用时进入 local_only degraded 状态。
- [ ] 对当前安装版或开发态执行断网 local smoke，保留结构化证据。

### AI00.4 停点

- [x] 写入 AI_BASELINE_FROZEN=PASS_WITH_WAIT_EXTERNAL_BOUNDARY。
- [ ] 未完成本地独立性基线时不得进入 AI01。

## 4. AI01：本地 ASR/TTS 模型管理中心

### AI01.1 契约和 schema

建议新增：

- schemas/local-model-descriptor-v1.schema.json
- schemas/model-install-record-v1.schema.json
- schemas/model-runtime-probe-v1.schema.json
- schemas/model-license-record-v1.schema.json
- apps/api/src/workbench/ai_models/models.py

任务：

- [x] 为 model_id、kind、engine、revision、能力、语言、许可证、文件 hash、资源要求和兼容版本建立严格模型。
- [x] 建立安装状态机和稳定 reason code。
- [x] 建立 runtime probe、device、RAM/VRAM、加载耗时和错误契约。
- [x] 建立 JSON Schema 与 Python 模型双向 golden fixture（fixture/API/契约测试）。
- [ ] 验证 schema 拒绝绝对路径、重复文件、缺 hash、负大小和未知状态。

### AI01.2 模型库存与持久化

建议新增：

- apps/api/src/workbench/ai_models/registry.py
- apps/api/src/workbench/ai_models/repository.py
- apps/api/src/workbench/ai_models/manifests.py
- tests/unit/ai_models/test_registry.py
- tests/unit/ai_models/test_repository.py

任务：

- [x] 建立 workspace 级模型库存，不把大模型写入项目目录。
- [x] 模型文件按 model_id/revision 不可变存储。
- [x] manifest 保存文件 size、SHA-256、来源、revision、安装时间和许可证引用。
- [x] registry 写入使用临时文件、fsync/flush 能力允许时刷新并原子替换。
- [x] 重启后可重建库存；损坏单个 manifest 不影响其他模型。
- [x] 旧 scripts/provision_asr_model.py 产物可确定性导入为 legacy record。

### AI01.3 下载和安装

建议新增或改造：

- apps/api/src/workbench/ai_models/provisioner.py
- apps/api/src/workbench/ai_models/downloads.py
- scripts/provision_asr_model.py
- tests/unit/ai_models/test_provisioner.py

任务：

- [ ] 复用固定 revision 和完整性检查，不允许 mutable latest 成为正式模型身份。
- [x] 增加断点续传、临时 attempt 目录、磁盘空间预检和最大下载预算。
- [ ] 下载成功后逐文件校验，再原子发布 revision。
- [ ] 下载失败、取消、磁盘满、hash 错误和进程中断均不得污染 active revision。
- [x] 支持 offline import：用户选择完整模型包后校验 manifest。
- [ ] 安装和更新必须由用户显式触发；应用启动不联网。

### AI01.4 Runtime 和资源租约

建议新增：

- apps/api/src/workbench/ai_models/runtime.py
- apps/api/src/workbench/ai_models/leases.py
- apps/api/src/workbench/ai_models/probes.py

任务：

- [ ] 探测 CPU、CUDA/DirectML 等实际支持状态，并返回 unsupported/missing/degraded。
- [ ] ASR/TTS 推理任务绑定 model revision 和 device。
- [ ] 加载失败自动回退 CPU 仅限用户允许且资源预算满足。
- [x] 模型有 active lease 时拒绝卸载或删除。
- [ ] 应用退出后清理 owned runtime；模型文件和任务 checkpoint 保留。
- [ ] 记录启动时间、峰值 RAM/VRAM、实时因子和最近成功探测。

### AI01.5 本地 ASR 接线

- [x] 将 FasterWhisperBackend 从可变模型名改为 registry 中的 model revision 引用（保留 legacy fallback）。
- [ ] 保留词级时间戳、暂停和 checkpoint。
- [ ] 模型缺失返回 ASR_MODEL_UNAVAILABLE，并提供打开模型中心操作。
- [ ] 已有 transcript 在模型缺失时仍可读取和使用。
- [ ] 对中文短音频、长音频、静音、损坏文件和中断恢复建立矩阵。

### AI01.6 本地 TTS 接线

- [x] 定义 LocalSpeechSynthesizer 与现有 SpeechSynthesizer/Provider Adapter 的桥接。
- [ ] 先支持普通本地 TTS，不把声音克隆授权逻辑塞入基础 TTS。
- [ ] 输出统一 WAV、sample rate、channel、duration、content hash 和 model revision。
- [ ] 合成失败保留上一成功页面音频。
- [ ] 无本地 TTS 时仍可导入用户音频，不阻断主链。

### AI01.7 API 和 UI

建议新增：

- apps/api/src/workbench/api/ai_models.py
- apps/web/src/features/settings/ai/LocalModelCenter.tsx
- apps/web/src/features/settings/ai/ModelInstallProgress.tsx

任务：

- [ ] 完成模型列表、详情、许可证、大小、设备、安装、取消、探测、激活、回滚和删除影响分析。
- [ ] UI 明确显示是否联网、预计下载量、磁盘剩余和当前 active revision。
- [ ] 删除操作需要确认；被引用或有租约时展示阻断原因。
- [x] API 不返回模型绝对路径。

### AI01.8 验证与 Gate

- [x] 运行 ai_models 单元、契约和 API 测试（Web 模型中心仍为后续 UI 项）。
- [ ] 在普通 Windows 用户目录执行安装中断、重启恢复、CPU ASR 和 TTS smoke。
- [ ] 断网执行本地音频全链。
- [x] 写入 LOCAL_MODEL_CENTER_READY=PASS_LOCAL_FOUNDATION_WITH_WAIT_EXTERNAL_BOUNDARY。

完成后直接进入 AI02。

## 5. AI02：多 LLM、ASR、TTS、渲染供应商统一适配

### AI02.1 Provider 契约 V2

建议新增：

- schemas/provider-route-policy-v2.schema.json
- schemas/provider-operation-v2.schema.json
- schemas/provider-adapter-conformance-v1.schema.json
- tests/contract/test_provider_v2_contracts.py

任务：

- [x] 在 V1 上增量增加 policy fingerprint、price book、credential ref、idempotency、数据分类和候选输出引用。
- [ ] 保持 V1 可读；旧项目使用内存 local-first 策略。
- [ ] 固定 capability ID 和输出 schema。
- [x] 为 Adapter conformance 建立统一 fixture 和 fake provider harness。

### AI02.2 Registry 和能力探测

改造：

- apps/api/src/workbench/providers/registry.py
- apps/api/src/workbench/providers/probe.py
- apps/api/src/workbench/providers/models.py

任务：

- [ ] descriptor 增加 retention、region、idempotency、cancellation 和 probe billing 元数据。
- [ ] static probe 永不联网；health/sample probe 明确是否计费。
- [ ] 能力探测有 TTL、并发去重和敏感数据限制。
- [ ] incompatible/disabled/degraded 不进入默认路由。

### AI02.3 LLM Adapter

- [ ] 包装现有 CompletionClient，业务服务不再直接读取供应商 profile。
- [ ] 支持结构化输出 schema、token usage、request ID、模型 resolved 和错误归一化。
- [ ] prompt revision、输入 hash 和参数进入缓存键。
- [ ] 保留旧入口旁路比较，结果不自动写 active narration。

### AI02.4 ASR Adapter

- [ ] 本地 ASR 作为 in_process_builtin 或 local_process Provider 注册。
- [ ] 远端 ASR 适配器必须声明音频大小、时长、语言、时间戳和数据保留。
- [ ] 输出统一 Transcript schema。
- [ ] 本地 ASR 是默认路由；远端 ASR 必须显式 opt-in。

### AI02.5 TTS Adapter

- [ ] 本地普通 TTS 注册为默认 Provider。
- [ ] 远端 TTS 统一 text、voice binding、speed、language 和输出 WAV。
- [ ] 声音替换默认禁止。
- [ ] provider_request_id、usage、时长和费用完整返回。

### AI02.6 Renderer Adapter

- [ ] 包装现有 PageRenderer/视频渲染桥接，不改变 RenderGraph 权威。
- [ ] 输入只使用冻结 graph/artifact refs，不读取变化中的项目目录。
- [ ] 远端 renderer 必须返回 artifact hash、runtime fingerprint 和可验证 media metadata。
- [ ] 远端失败不影响本地 renderer 可用性。

### AI02.7 API、UI 和迁移

- [ ] 扩展 /api/providers 列表、详情、能力、探测和 route preview。
- [ ] Provider Settings 显示 local/remote、区域、保留、价格、状态和凭证元数据。
- [ ] 旧 LLM/HeyGen profile 迁移为 credential ref，不复制密钥到项目。
- [ ] 业务设置保留“固定本地”选项。

### AI02.8 验证与 Gate

- [ ] 每类 Adapter 通过 conformance、取消、错误、脱敏和缓存测试。
- [ ] 运行 narration、transcription、HeyGen 和 render 现有回归。
- [ ] 运行无网络和无凭证 local-only 回归。
- [x] 写入 PROVIDER_ADAPTERS_READY=PASS_CONTRACT_AND_FAKE_ADAPTERS（真实供应商 WAIT_EXTERNAL）。

完成后直接进入 AI03。

## 6. AI03：自动失败切换、费用预算和限流

### AI03.1 持久费用账本

建议新增或改造：

- apps/api/src/workbench/providers/cost_ledger.py
- apps/api/src/workbench/providers/billing.py
- apps/api/src/workbench/providers/repository.py
- tests/unit/providers/test_cost_ledger.py

任务：

- [x] 建立 reserve、commit、release、reconcile 事件模型（unknown→commit 作为 reconcile）。
- [ ] 支持 operation、项目、Provider/credential 和工作区预算。
- [ ] 金额使用 currency + minor units，不使用 float。
- [ ] 价格版本冻结到 operation。
- [x] 重启后保留额度、已消费和 unknown 状态可恢复。
- [ ] 审计事件不包含 prompt、音频或 secret。

### AI03.2 持久限流

- [ ] 扩展 TokenBucket 为持久快照或可重建事件。
- [ ] 支持 RPM、并发、字符/token、音频秒数和渲染时长额度。
- [ ] 前台交互和后台批次分配独立配额。
- [ ] 同一 credential 在多个 worker 间不能突破上限。
- [ ] 时钟回拨和进程重启测试失败关闭。

### AI03.3 Retry 和 Failover 状态机

改造：

- apps/api/src/workbench/providers/broker.py
- apps/api/src/workbench/providers/policy.py

任务：

- [ ] 将网络错误、5xx、429、超时、凭证、schema、人工锁定和 unknown billing 分类。
- [ ] 只有 failover_allowed 矩阵通过才尝试下一 Provider。
- [ ] 固定 Provider、固定声音、区域扩大、费用扩大和授权扩大均阻断自动切换。
- [x] 付费操作超时进入 remote_unknown/unknown billing，阻断自动 failover。
- [x] 提供 reconcile API；未知状态默认保留，人工提交已知 billed cost 后才能 commit。

### AI03.4 Idempotency 和发布

- [ ] operation_id 与输入/策略/价格 fingerprint 生成稳定 idempotency key。
- [ ] 供应商不支持幂等时禁止付费写操作自动跨 Provider 重试。
- [ ] Adapter 输出先进入候选目录。
- [ ] 费用核销和候选发布顺序明确；任一失败可恢复且不重复发布。

### AI03.5 UI

- [ ] 请求前展示预计费用、最大费用、预算剩余、目标 Provider 和可能的 failover。
- [ ] 提供工作区/项目/Provider 预算设置。
- [ ] 展示限流等待、重试次数、切换原因和 unknown 对账任务。
- [ ] 不允许以模糊“自动优化”开关隐式扩大费用。

### AI03.6 故障矩阵

- [ ] 首次请求前连接失败。
- [ ] 请求已发送后超时。
- [ ] 429 带 retry-after。
- [ ] 5xx 前两次失败第三次成功。
- [ ] Provider A 失败切换 B。
- [ ] B 更贵、不同区域或不同声音时阻断。
- [ ] 重启发生在 reserve 后、远端成功后、commit 前和发布前。
- [ ] 验证无重复 charge、无负预算、无永久额度泄漏。

### AI03.7 Gate

- [x] 写入 PROVIDER_GOVERNANCE_READY=PASS_LOCAL_LEDGER_AND_FAIL_CLOSED_FAILOVER。
- [ ] 任何 unknown 状态被自动二次调用时 Gate 必须失败。

完成后直接进入 AI04。

## 7. AI04：本人声音克隆及模型授权管理

### AI04.1 契约

建议新增：

- schemas/voice-identity-v1.schema.json
- schemas/voice-consent-record-v1.schema.json
- schemas/voice-model-revision-v1.schema.json
- schemas/voice-provider-binding-v1.schema.json
- apps/api/src/workbench/voices/models.py

任务：

- [ ] 固定声音身份、参考资产、授权、用途、期限、供应商范围和 active revision。
- [ ] 授权状态机支持 draft、pending_review、active、suspended、revoked、expired。
- [ ] 缺 active consent 时所有 clone/upload/synthesis 请求失败关闭。
- [ ] 声音资产引用使用 asset ref 和 hash，不保存任意路径。

### AI04.2 声音资产仓库

建议新增：

- apps/api/src/workbench/voices/repository.py
- apps/api/src/workbench/voices/assets.py
- apps/api/src/workbench/voices/consent.py

任务：

- [ ] 保存原始参考录音和派生清理资产的谱系。
- [ ] 建立最短/最长录音、采样率、SNR、静音和削波检查。
- [ ] 参考录音默认 restricted，不进入普通诊断包。
- [ ] 项目只引用 voice identity/model revision，不复制声纹模型。

### AI04.3 本地克隆运行时

- [ ] 通过 LocalModelRegistry 注册 voice_clone engine。
- [ ] 创建 clone job，冻结参考资产、授权、engine 和 model revision。
- [ ] 输出模型候选和固定文本预览。
- [ ] 用户人工确认后才能 activate。
- [ ] 模型失败、取消或质量不通过保留上一 active revision。

### AI04.4 远端 voice binding

- [ ] Provider voice ID 与本地 VoiceIdentity 建立显式 binding。
- [ ] 上传前再次检查 remote_upload_allowed、Provider、用途和费用。
- [ ] 保存 provider request ID、远端条款版本、创建/删除状态。
- [ ] 删除失败保持 tombstone 和 retryable 状态，不伪报已删除。

### AI04.5 撤销与删除

- [ ] revoke 立即阻断新合成。
- [ ] 运行中本地任务安全取消；远端已接受任务进入 reconcile。
- [ ] 删除前生成引用报告，列出项目、成功音频和远端 binding。
- [ ] 已发布项目历史保留最小审计；不允许重新生成。

### AI04.6 API 和 UI

建议新增：

- apps/api/src/workbench/api/voices.py
- apps/web/src/features/settings/ai/VoiceIdentityCenter.tsx

任务：

- [ ] 完成创建、录音导入、授权、质量检查、克隆、预览、激活、撤销和删除。
- [ ] UI 始终显示“本人/已授权”、local-only、有效期和允许 Provider。
- [ ] 不提供跳过授权或冒充他人的操作。

### AI04.7 测试与 Gate

- [ ] 授权过期、撤销、项目限制、Provider 限制和用途限制测试。
- [ ] 参考录音、声纹、密钥和远端响应脱敏测试。
- [ ] 本地克隆 smoke 和人工预览签署。
- [x] 真实远端克隆没有授权时标记 WAIT_EXTERNAL。
- [x] 写入 VOICE_IDENTITY_READY=PASS_LOCAL_AUTHORIZATION_FOUNDATION。

完成后直接进入 AI05。

## 8. AI05：HeyGen 等外部服务可靠批处理

### AI05.1 批次契约与仓库

建议新增：

- schemas/remote-batch-v1.schema.json
- schemas/remote-batch-item-v1.schema.json
- apps/api/src/workbench/providers/batch/models.py
- apps/api/src/workbench/providers/batch/repository.py

任务：

- [ ] 建立 batch/item/segment/attempt 四层模型。
- [ ] 状态包含 awaiting_confirmation、partial、paused、remote_unknown 和 succeeded。
- [ ] 每个 attempt 保存 input hash、idempotency、request ID、billed state 和错误。
- [x] 状态和 checkpoint 跨重启持久化。

### AI05.2 Coordinator

建议新增：

- apps/api/src/workbench/providers/batch/coordinator.py
- apps/api/src/workbench/providers/batch/reconcile.py

任务：

- [ ] 使用现有 JobRepository 调度，不新建不可恢复后台线程。
- [ ] 分页/分段并发受 AI03 限流控制。
- [ ] 成功 segment 永不自动重做。
- [ ] 取消后对远端已接受任务继续对账。
- [ ] 全部分段校验通过后才原子发布页面音频。

### AI05.3 HeyGen 迁移

改造：

- apps/api/src/workbench/integrations/heygen/client.py
- apps/api/src/workbench/audio/heygen_service.py
- apps/api/src/workbench/audio/heygen_chunks.py
- apps/web/src/features/audio/heygen

任务：

- [ ] 保留现有三次重试、指数退避、分段和缓存行为。
- [ ] 将页面重试信息迁移到 RemoteBatch attempt。
- [ ] 保存并展示 Provider request ID 和费用。
- [ ] 支持只重试失败页面、失败分段和全批次恢复。
- [ ] 声音切换必须显式确认并创建新候选。

### AI05.4 通用远端批处理

- [ ] 让远端 ASR、TTS、renderer 使用同一 batch coordinator。
- [ ] Adapter 只执行单次 attempt，不自行管理无限重试。
- [ ] Provider 特有 polling 通过 reconcile adapter 实现。
- [ ] 批次结果进入统一任务中心。

### AI05.5 真实 canary

前置条件：

- [ ] 当前冻结 Windows 候选。
- [ ] 当前 Windows 用户下有效凭证。
- [ ] 非敏感两页 PPT/旁白。
- [ ] 明确 voice ID。
- [ ] 硬费用上限。
- [ ] 用户批准真实调用。

执行：

- [ ] 记录 Provider request ID、输入 hash、输出 hash、usage 和 charge。
- [ ] 注入一次可恢复失败，验证不重复成功页面。
- [ ] 对账最终费用与账本。
- [ ] 没有授权时保持 HEYGEN_WAIT_EXTERNAL，不阻断本地 Gate。

### AI05.6 Gate

- [ ] fake/sandbox 八页矩阵全通过。
- [x] remote_unknown 不自动重做。
- [ ] 成功页面 request count 保持 1。
- [x] 写入 REMOTE_BATCH_READY=PASS_DURABLE_STATE_WITH_WAIT_EXTERNAL。

完成后直接进入 AI06。

## 9. AI06：AI 旁白润色、智能断句和字幕翻译

### AI06.1 共享候选契约

建议新增：

- schemas/content-assist-candidate-v1.schema.json
- schemas/style-profile-v1.schema.json
- schemas/translation-glossary-v1.schema.json
- apps/api/src/workbench/content_assist/models.py
- apps/api/src/workbench/content_assist/repository.py

任务：

- [ ] 候选绑定 source revision/hash、Provider/model、prompt、术语表和风格版本。
- [ ] 支持 generated、reviewing、accepted、rejected、stale。
- [ ] 源内容变化自动 stale。
- [ ] 接受候选必须使用 expected_revision。

### AI06.2 旁白润色

建议新增：

- apps/api/src/workbench/content_assist/narration.py
- apps/web/src/features/narration/assist

任务：

- [ ] 基于已冻结旁白 revision 生成候选。
- [ ] 提供逐段 diff、字数、预计时长、数字和专名保护检查。
- [ ] 不允许无材料依据新增具体事实。
- [x] 支持本地规则模式，远端 LLM 关闭时仍可用。
- [ ] 接受后生成新 narration revision，不覆盖旧 revision。

### AI06.3 智能断句

建议新增：

- apps/api/src/workbench/content_assist/segmentation.py

任务：

- [ ] 先实现确定性标点、长度、停顿和页面边界算法。
- [ ] 可选 AI 只修改边界，不修改文字。
- [ ] 输出跨页风险、TTS 长度限制和预计时长。
- [ ] 接受后使受影响的音频、字幕和预检候选 stale。

### AI06.4 字幕翻译

建议新增：

- apps/api/src/workbench/content_assist/translation.py
- apps/web/src/features/subtitles/translation

任务：

- [ ] 基于 SubtitleDocument V2 创建 target-language track。
- [ ] 保留 cue ID、源文本和时间码。
- [ ] 支持术语表、禁译词、数字/单位保护和逐 cue review。
- [x] AI 不得直接修改 confirmed 时间码（候选只落库，未自动发布）。
- [ ] 导出时按项目策略检查翻译 review 状态。

### AI06.5 Provider 和预算接线

- [ ] 所有远端内容辅助通过 ProviderBroker。
- [ ] 请求前展示 Provider、模型、数据范围和费用上限。
- [ ] 缓存键包含 prompt、style、glossary 和 source revision。
- [ ] 失败、拒答或 schema 错误保留原文。

### AI06.6 UI

- [ ] 旁白编辑器增加“生成候选”和逐段差异，不新增第二套编辑器。
- [ ] 字幕工作台增加语言 track、术语表、review 过滤和差异。
- [ ] 提供关闭 AI、仅本地规则和固定 Provider 三种明确模式。
- [ ] 不使用会暗示自动发布的按钮文案。

### AI06.7 测试与 Gate

- [ ] 数字、日期、单位、专名和术语回归。
- [ ] 中文长句、混合中英文、无标点和多页边界矩阵。
- [ ] source revision 冲突和 stale 候选测试。
- [ ] 关闭所有 AI 后手工旁白/字幕完整工作流测试。
- [x] 写入 AI_CONTENT_ASSIST_READY=PASS_LOCAL_CANDIDATE_FLOW_WITH_WAIT_EXTERNAL。

完成后直接进入 AI07。

## 10. AI07：总接线、Windows 验收和二次收口

### AI07.1 共享接线

- [ ] 串行更新 apps/api/src/workbench/main.py。
- [ ] 串行更新 packages/contracts/openapi.json。
- [ ] 串行更新数据库 migration 和 checksum。
- [ ] 串行更新设置中心导航、项目工作流和任务中心。
- [x] 验证 feature flags 默认保持 remote off。

### AI07.2 本地独立性正式验收

- [ ] 关闭网络。
- [ ] 清空/禁用全部远端 Provider 和凭证。
- [ ] 应用安装、首启和再次启动通过。
- [ ] 导入真实 PPT。
- [ ] 使用导入音频完成规范化、分页和字幕。
- [ ] 使用本地 ASR 完成转写。
- [ ] 可用时使用普通本地 TTS；不可用时不阻断导入音频路线。
- [ ] 完成预检、播放、最终 MP4 和制作包。
- [ ] 记录 LOCAL_AUDIO_INDEPENDENT=PASS。

### AI07.3 AI 功能矩阵

- [ ] 本地模型安装中断、恢复、激活和回滚。
- [ ] LLM/ASR/TTS/renderer Adapter conformance。
- [ ] 预算、限流、重试、failover 和 unknown billing。
- [ ] 本人声音授权、预览、撤销和删除。
- [ ] HeyGen fake/sandbox 批次恢复。
- [ ] 旁白、断句、翻译候选接受/拒绝/stale。

### AI07.4 安全与隐私

- [ ] secret scan。
- [ ] 诊断包脱敏。
- [ ] 绝对路径和 workspace ownership。
- [ ] 声音参考录音和 consent 隔离。
- [ ] 远端数据分类、区域和保留策略 Gate。
- [ ] 删除和撤销审计。

### AI07.5 全量回归

建议至少运行：

- [ ] Python contract/unit/integration/provider/audio/narration/subtitle test groups。
- [ ] Web Provider、模型中心、声音、HeyGen、旁白和字幕 Vitest。
- [ ] Web 与 Remotion typecheck。
- [ ] Ruff、mypy 和 OpenAPI/schema drift。
- [ ] Windows 安装版真实 PPT local-only E2E。
- [ ] 当前候选恢复、质量和媒体 decode 检查。

### AI07.6 外部证据判定

- [ ] 已授权真实 Provider 生成独立 canary evidence。
- [ ] 未授权 Provider 保持 WAIT_EXTERNAL。
- [x] WAIT_EXTERNAL 不降低 LOCAL_AUDIO_INDEPENDENT 和本地个人使用状态。
- [ ] 不用 fake、旧账单或旧候选证据签署真实 Provider。

### AI07.7 第一次总审计

- [x] 聚合 AI_BASELINE_FROZEN。
- [ ] 聚合 LOCAL_AUDIO_INDEPENDENT。
- [ ] 聚合 AI-G1 至 AI-G6。
- [ ] 验证 source commit、candidate ID、installer、runtime/model manifest、policy 和 evidence hash 一致。
- [ ] 生成 final-evidence-manifest.json。

### AI07.8 第二轮未完成项解决

按仓库开发规则，第一次实现结束后必须再解决未完成项目：

- [ ] 搜索设计和计划中的 unchecked、TODO、blocked、failed、stale、not_run、WAIT_EXTERNAL。
- [x] 将 WAIT_EXTERNAL 与真正工程缺陷分开。
- [ ] 对工程缺陷找到最早受影响项目 AI01–AI06。
- [ ] 回到该项目修复并重新通过其 Gate。
- [ ] 严格顺序重跑全部下游项目。
- [ ] 再次执行 local-only Windows E2E。
- [x] 第二轮审计除明确外部授权项外为零。

### AI07.9 最终停点

仅当以下全部成立才允许：

- [ ] LOCAL_AUDIO_INDEPENDENT=PASS。
- [ ] LOCAL_MODEL_CENTER_READY=PASS。
- [ ] PROVIDER_ADAPTERS_READY=PASS。
- [ ] PROVIDER_GOVERNANCE_READY=PASS。
- [ ] VOICE_IDENTITY_READY=PASS。
- [ ] REMOTE_BATCH_READY=PASS。
- [ ] AI_CONTENT_ASSIST_READY=PASS。
- [ ] 第二轮工程未完成项为零。
- [ ] 写入 AI_PROVIDER_PLATFORM_READY=PASS。

真实外部供应商没有 canary 时，最终报告必须同时列出对应 WAIT_EXTERNAL，但本地平台可以在所有本地 Gate 通过后正式完成。

## 11. 建议 owned paths

### AI01

- apps/api/src/workbench/ai_models
- apps/api/src/workbench/audio/transcriber.py
- scripts/provision_asr_model.py
- apps/web/src/features/settings/ai
- schemas/local-model-*

### AI02–AI03

- apps/api/src/workbench/providers
- schemas/provider-*
- apps/web/src/features/providers
- apps/web/src/features/settings/ai

### AI04

- apps/api/src/workbench/voices
- apps/api/src/workbench/api/voices.py
- apps/web/src/features/settings/ai/VoiceIdentityCenter.tsx
- schemas/voice-*

### AI05

- apps/api/src/workbench/providers/batch
- apps/api/src/workbench/integrations/heygen
- apps/api/src/workbench/audio/heygen_*
- apps/web/src/features/audio/heygen
- schemas/remote-batch-*

### AI06

- apps/api/src/workbench/content_assist
- apps/api/src/workbench/narration
- apps/api/src/workbench/subtitles
- apps/web/src/features/narration
- apps/web/src/features/subtitles
- schemas/content-assist-*

共享文件 main.py、OpenAPI、数据库 migration 和设置导航由每个项目结束时的单一集成人串行修改。

## 12. 证据目录建议

正式证据放在：

test-results/ai-provider-platform/{candidate_id}/

建议结构：

- candidate-identity.json
- local-audio-independent.json
- model-center/
- provider-adapters/
- governance/
- voice-identity/
- remote-batch/
- content-assist/
- windows/
- security/
- external-canaries/
- gates/
- final-evidence-manifest.json
- final-audit.json

真实声音、原始音频、密钥和完整 Provider 响应不得复制进证据目录；只保存受控引用、hash、request ID 和非敏感摘要。

## 13. 最终交付物

- [ ] 本设计文档和逐项实施计划更新为 Implemented。
- [ ] Local Model Center 用户说明。
- [ ] Provider Adapter 开发者契约和 conformance harness。
- [ ] 费用、限流、失败切换和对账运维说明。
- [ ] 本人声音授权、撤销和删除说明。
- [ ] HeyGen/远端批处理用户操作说明。
- [ ] 旁白润色、断句和字幕翻译审核说明。
- [ ] 本地独立运行与断网排障说明。
- [ ] 当前候选完整证据包和已知限制。
