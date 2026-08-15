# 第四类：AI 与供应商平台程序完整设计

> 日期：2026-08-15  
> 状态：Proposed  
> 适用范围：PPT Video Workbench Windows 本地生产工作台  
> 优先级：低于本地 PPT 转视频、安装、恢复、质量和个人使用收口  
> 对应实施计划：docs/superpowers/plans/2026-08-15-ai-provider-platform-program.md

## 1. 设计结论

第四类程序不是另建一条 AI 制作流程，而是在现有本地七步生产流程之下补齐统一的 AI 模型与供应商控制面。

本期由六个严格有序的项目组成：

| 编号 | 项目 | 最终 Gate |
| --- | --- | --- |
| AI01 | 本地 ASR/TTS 模型管理中心 | LOCAL_MODEL_CENTER_READY |
| AI02 | 多 LLM、ASR、TTS、渲染供应商统一适配 | PROVIDER_ADAPTERS_READY |
| AI03 | 自动失败切换、费用预算和限流 | PROVIDER_GOVERNANCE_READY |
| AI04 | 本人声音克隆及模型授权管理 | VOICE_IDENTITY_READY |
| AI05 | HeyGen 等外部服务可靠批处理 | REMOTE_BATCH_READY |
| AI06 | AI 旁白润色、智能断句和字幕翻译 | AI_CONTENT_ASSIST_READY |

六个项目全部通过后，才允许写入 AI_PROVIDER_PLATFORM_READY=PASS。

最高级产品不变量是：

1. 本地音频导入、规范化、转写、分页、字幕编辑、预检、播放和最终导出不依赖任何远端供应商。
2. 外部服务默认关闭，必须由用户显式配置、显式选择并在任务级确认预算与数据边界。
3. 远端调用失败、无网络、欠费、限流、凭证失效或服务下线时，本地项目仍可打开、编辑、预览和导出已有本地资产。
4. 任何自动失败切换都不能扩大数据区域、费用上限、声音身份或授权范围。
5. 不允许把远端 AI 输出直接覆盖用户已确认的旁白、字幕、声音模型或上一成功音频。

## 2. 目标与非目标

### 2.1 产品目标

- 让用户在一个模型管理中心安装、校验、启用、停用和更新本地 ASR/TTS 模型。
- 让 LLM、ASR、TTS 和渲染器使用统一能力、调用、结果、错误、费用和审计契约。
- 在安全条件下自动重试和切换供应商，并在请求前阻止超预算、超速率或不允许的数据发送。
- 管理本人声音、参考录音、克隆模型、供应商 voice ID、授权证据、使用范围、期限、撤销和删除。
- 将 HeyGen 等长任务改造为可恢复、可核账、可取消、可逐页重试的持久批处理。
- 提供旁白润色、智能断句和字幕翻译，但保留原文、修订、差异和人工确认。

### 2.2 工程目标

- 复用现有 Provider Kernel、ProviderBroker、ProviderPolicyV1、凭证引用、预算账本、限流器、缓存、能力探测和审计事件。
- 复用现有 FasterWhisperBackend、Transcriber、provision_asr_model.py、HeyGenClient、HeyGenService、旁白 revision 和 SubtitleDocument V2。
- 所有长任务进入现有 JobRepository、检查点、取消、恢复和发布状态机。
- 所有本地模型和声音资产以 manifest、revision、SHA-256 和原子发布为权威，不依赖可变目录名。
- 所有供应商输出先进入隔离候选区，完成 schema、媒体、授权和内容检查后才发布到项目。

### 2.3 非目标

- 不在本项目内重新开发 PPT 导入、时间线、Effects、最终渲染或制作包主链。
- 不把云协作、多人租户、插件市场、支付结算或 macOS/Linux 正式发布纳入本期。
- 不在没有用户授权和费用上限时执行真实付费 canary。
- 不训练通用基础模型，不建立公共声音市场。
- 不允许第三方适配器执行未签名的任意本地代码。
- 不承诺供应商之间的音色、字幕、布局或渲染结果完全等价。

## 3. 当前事实基线

### 3.1 已有能力

- apps/api/src/workbench/providers 已包含 Provider 描述、注册、策略、Broker、缓存、预算、限流、凭证引用、探测、审计和上游桥接。
- schemas/provider-descriptor-v1.schema.json 与 schemas/provider-invocation-v1.schema.json 已冻结基础契约。
- Provider 类型已覆盖 LLM、TTS、ASR、OCR、数字人和 renderer；本期重点生产化 LLM、ASR、TTS、renderer。
- apps/api/src/workbench/audio/transcriber.py 已支持 faster-whisper、词级时间戳、暂停、checkpoint 和恢复。
- scripts/provision_asr_model.py 已支持固定 revision、完整性检查、原子切换和模型 manifest。
- HeyGen 已支持凭证隔离、长文本分段、指数退避、逐段缓存、失败段续跑和声音切换确认。
- 旁白已有 revision、生成服务、导入、确认和差异编辑；字幕已有 SubtitleDocument V2 和工作台服务。
- Windows 凭证、诊断脱敏和 Provider privacy scan 已有测试基础。

### 3.2 主要缺口

- 本地模型仍以脚本部署为主，没有统一目录、库存、磁盘预算、运行时探测、版本切换、回滚和 UI。
- 本地 TTS 与本人声音克隆没有进入同一模型生命周期和授权模型。
- Provider 生产适配仍以桥接和测试替身为主，真实供应商能力、价格、区域、请求幂等和核账证据不足。
- 预算和限流主要是内存态基础实现，缺持久账本、保留额度、实际核销、跨重启恢复和未知计费锁定。
- HeyGen 批处理仍以页面服务为中心，缺少完整批次状态机、远端状态对账、成本汇总和正式 canary Gate。
- AI 旁白、断句和翻译没有统一的内容候选、术语表、质量评分、差异确认和回退契约。
- 本地音频链与 Provider 控制面之间仍需明确的单向依赖边界和断网回归门禁。

## 4. 核心架构原则

### 4.1 本地生产面与供应商控制面分离

系统分成两个平面：

- Local Production Plane：项目、PPT、旁白、导入音频、本地 ASR/TTS、字幕、时间线、预检、预览、渲染和导出。
- AI Provider Control Plane：供应商注册、能力探测、路由、预算、限流、凭证、远端批次、费用和审计。

Local Production Plane 可以调用 Control Plane 获得可选增强结果；Control Plane 不得成为打开项目、编辑本地内容或导出已有本地资产的启动依赖。

应用启动时即使 Provider 数据库损坏、网络不可用或全部凭证失效，也必须进入 local_only 模式，而不是拒绝启动。

### 4.2 本地优先路由

每个新项目默认生成 local-only 的内存策略，不隐式修改项目清单：

- allow_remote_https=false
- allow_failover=false
- 本地 ASR/TTS 优先
- 已导入本地音频永远可以继续使用
- 远端能力必须在项目或任务级显式启用

当用户选择远端任务时，策略必须冻结到 operation_id，并进入输入 fingerprint。任务执行中不能因为设置变化而扩大路由范围。

### 4.3 候选发布而非原地覆盖

AI 生成内容一律先生成候选：

- 旁白生成 narration candidate revision。
- 断句生成 segmentation candidate。
- 翻译生成 subtitle translation candidate。
- TTS 生成 audio candidate。
- 声音克隆生成 voice model candidate。
- 远端渲染生成 render artifact candidate。

候选通过结构、内容、媒体、授权和人工确认后才能成为 active revision。失败或取消不改变上一成功结果。

### 4.4 费用与未知状态失败关闭

- 远端请求前必须有价格版本、最大费用、预算作用域和保留额度。
- 供应商返回成功后按实际 usage 核销；差额释放。
- 超时后无法确认供应商是否已处理时，状态进入 remote_unknown。
- remote_unknown 禁止自动重试、自动切换或再次计费，必须先对账或人工决定。
- 供应商不支持幂等键时，付费写操作默认不能跨供应商自动切换。

### 4.5 身份和授权先于声音质量

声音克隆是否可用由授权 Gate 决定，不由音质分数决定。缺少同意、所有权、用途、期限或撤销状态时，即使模型可推理也不能进入项目 TTS 选择器。

## 5. 总体组件

| 组件 | 职责 | 建议位置 |
| --- | --- | --- |
| LocalModelRegistry | 模型描述、revision、文件 manifest、兼容性和状态 | apps/api/src/workbench/ai_models |
| ModelProvisioner | 下载、断点续传、校验、原子安装、磁盘预算 | apps/api/src/workbench/ai_models |
| ModelRuntimeManager | 加载、卸载、设备选择、健康探测和资源租约 | apps/api/src/workbench/ai_models |
| ProviderRegistry | 统一供应商与能力库存 | 复用 providers/registry.py |
| ProviderBroker | 路由、幂等、缓存、预算、限流和切换 | 扩展 providers/broker.py |
| CostLedger | 预算保留、核销、释放和对账 | 扩展 providers/billing.py |
| VoiceIdentityRegistry | 声音身份、授权、参考录音和模型 revision | apps/api/src/workbench/voices |
| RemoteBatchCoordinator | 批次、页面、分段、尝试、远端状态和恢复 | apps/api/src/workbench/providers/batch |
| AIContentAssist | 润色、断句、翻译候选与差异 | apps/api/src/workbench/content_assist |
| AI Settings UI | 模型、供应商、预算、声音、任务和诊断 | apps/web/src/features/settings/ai |

## 6. 共享契约

### 6.1 LocalModelDescriptorV1

必须包含：

- model_id、display_name、kind：asr、tts、voice_clone、embedding。
- engine、engine_version、model_revision、source_ref。
- supported_languages、capabilities、license_ref。
- required_files 及每个文件的 size、SHA-256。
- minimum_ram、recommended_ram、minimum_vram、supported_devices。
- runtime_contract_version、compatible_app_versions。
- remote_download_required、redistribution_allowed。

模型 ID 和 revision 不包含绝对路径。运行目录由 PlatformServices 解析。

### 6.2 ModelInstallRecordV1

状态只允许：

- not_installed
- queued
- downloading
- verifying
- ready
- loading
- active
- degraded
- incompatible
- failed
- uninstall_pending

记录 attempt_id、bytes_total、bytes_completed、manifest_sha256、installed_at、last_probe、last_error_code 和 active_lease_count。

### 6.3 ProviderRoutePolicyV2

在 ProviderPolicyV1 上增量扩展：

- capability_id 级路由顺序。
- local_required 与 local_preferred。
- allowed_provider_ids 与 fixed_provider_id。
- allowed_regions、data classification 和 retention policy。
- max_cost_minor、daily/project budget scope。
- allow_retry、allow_failover、max_attempts。
- allow_voice_substitution，默认 false。
- require_cost_estimate、require_idempotency。
- unknown_remote_action，固定为 manual_reconcile。

旧项目没有 V2 策略时继续使用 local_first_policy，不自动写盘。

### 6.4 ProviderOperationV2

复用 ProviderInvocationV1，并补充：

- input_fingerprint、policy_fingerprint、price_book_version。
- credential_ref，只保存引用。
- idempotency_key。
- reserved_cost_minor。
- data_classification 与 consent_refs。
- output_candidate_ref。

### 6.5 VoiceIdentityV1

包含：

- voice_identity_id、display_name、owner_kind。
- reference_asset_refs，不存项目外绝对路径。
- consent_record_id、license_record_id。
- allowed_uses、allowed_projects、allowed_providers。
- valid_from、expires_at、revoked_at。
- local_only、remote_upload_allowed。
- active_model_revision 和外部 voice bindings。

### 6.6 VoiceConsentRecordV1

授权状态：

- draft
- pending_review
- active
- suspended
- revoked
- expired

必须记录主体、采集方式、用途、范围、期限、撤销方式、审核人和证据 hash。未 active 时不允许训练、上传或合成。

### 6.7 ContentAssistCandidateV1

适用于润色、断句和翻译：

- source_revision、source_hash。
- task_kind、model/provider/prompt revision。
- glossary_revision、style_profile_revision。
- candidate_text 或结构化 cue。
- changed_ranges、warnings、quality_checks。
- status：generated、reviewing、accepted、rejected、stale。

源 revision 变化后候选自动 stale，不能静默套用。

## 7. 项目 AI01：本地 ASR/TTS 模型管理中心

### 7.1 能力范围

- 管理 faster-whisper 等本地 ASR 模型。
- 管理普通本地 TTS 模型和后续声音克隆运行时。
- 展示模型大小、许可证、语言、设备、预计内存/显存和安装状态。
- 支持固定 revision 下载、断点续传、SHA-256 校验、临时目录和原子发布。
- 支持 CPU/GPU 设备探测、试运行、加载/卸载和资源租约。
- 支持选择默认 ASR/TTS，但项目已冻结任务仍使用任务绑定 revision。
- 支持更新候选、手动切换和一键回滚。
- 支持卸载前影响分析；有活跃租约或项目引用时拒绝物理删除。

### 7.2 目录建议

workspace-data/settings/ai-models 下保存：

- registry.json：非敏感模型库存。
- artifacts/model_id/revision：不可变模型文件。
- manifests/model_id/revision.json：文件 hash 和来源。
- downloads/attempt_id：可恢复临时下载。
- runtime：非权威运行状态和锁。

项目只保存 model_id、revision 和推理参数，不复制大模型。

### 7.3 本地链独立性

- 模型中心故障不影响导入已有音频、手工字幕和已有成片。
- ASR 模型缺失只阻断“新转写”，不能阻断打开项目和使用已有 transcript。
- TTS 模型缺失只阻断“新合成”，不能阻断使用导入音频。
- 模型下载必须由用户显式发起，应用启动不得偷偷联网。

## 8. 项目 AI02：多供应商统一适配

### 8.1 统一能力

本期生产化以下 capability：

- llm.completion 与 llm.structured_generation。
- asr.transcription 与 asr.word_timestamps。
- tts.speech_synthesize。
- renderer.page 与 renderer.video。

数字人和 OCR 保持兼容契约，但不作为本期正式 Gate。

### 8.2 Adapter 规则

每个适配器必须：

- 提供静态 descriptor。
- 支持不计费的 static probe。
- 明确 health/sample probe 是否计费。
- 在适配器边界完成输入、输出和错误归一化。
- 不返回密钥、完整本地路径或供应商原始敏感响应。
- 明确幂等、取消、流式、区域、保留、费用估算和最大输入。
- 输出稳定 provider_request_id、usage 和 billed state。

同一业务服务只依赖 ProviderBroker 或本地接口，不直接导入供应商 SDK。

### 8.3 迁移顺序

1. 现有 LLM CompletionClient。
2. 本地和远端 ASR。
3. 本地 TTS 与普通远端 TTS。
4. 页面/视频 renderer。
5. HeyGen 作为受管 TTS/数字人适配器接入。

迁移采用旁路比较：旧入口和新 Broker 对同一冻结输入生成候选，比较 schema、hash、时长、错误和缓存，不直接切换默认路径。

## 9. 项目 AI03：失败切换、费用预算和限流

### 9.1 路由决策顺序

1. 校验任务冻结策略和数据分类。
2. 过滤禁用、不兼容、区域不允许和凭证不可用的 Provider。
3. 保证 local_required 能力存在。
4. 检查价格版本与费用估算。
5. 保留预算。
6. 获取速率和并发令牌。
7. 执行首选 Provider。
8. 只有满足切换矩阵时才选择下一 Provider。
9. 发布结果并核销费用。

### 9.2 自动切换矩阵

允许自动切换：

- 连接失败且确认请求未被供应商接受。
- 供应商 5xx、明确可重试状态或健康探测降级。
- 未产生费用或供应商幂等键可证明不会重复计费。
- 目标 Provider 不扩大费用、区域、数据分类、保留范围和声音身份。

禁止自动切换：

- 400/401/403、schema 错误、凭证错误和人工锁定。
- 费用状态 unknown。
- 固定声音或固定供应商任务。
- 需要上传本人声音但新 Provider 未在授权范围内。
- 新 Provider 价格更高且任务预算未覆盖。
- 输出语义不可替代，例如数字人视频切换为普通 TTS。

### 9.3 预算层次

至少支持：

- 单次 operation 上限。
- 单项目日/月预算。
- Provider/credential 预算。
- 可选工作区月预算。

预算账本使用 reserve、commit、release、reconcile 四类不可变事件。金额使用最小货币单位和 ISO 4217 currency，不使用浮点数。

### 9.4 限流

- Provider、credential、capability 三维 token bucket。
- 支持 RPM、并发数、输入 token/字符/音频秒数。
- 限流状态必须跨进程重启恢复，不能只存在内存。
- 前台单页任务与后台批次分队列，批次不能耗尽全部额度。

## 10. 项目 AI04：本人声音克隆及模型授权管理

### 10.1 声音资产分类

- reference_recording：本人原始参考录音。
- cleaned_reference：降噪、裁剪后的派生资产。
- local_voice_model：本地克隆模型 revision。
- remote_voice_binding：供应商 voice ID 与授权映射。
- preview_audio：固定文本预览。

每项都必须有内容 hash、来源、派生关系、创建工具版本和授权引用。

### 10.2 创建流程

1. 创建声音身份。
2. 采集或导入参考录音。
3. 完成所有权、用途、范围和期限确认。
4. 运行音频质量与敏感内容检查。
5. 用户选择 local_only 或允许指定供应商上传。
6. 创建训练/克隆候选。
7. 生成固定文本预览。
8. 人工确认音色和发音。
9. 激活模型 revision。

### 10.3 安全和撤销

- 默认 local_only=true、remote_upload_allowed=false。
- 未经显式确认，参考录音不得发送到任何远端 Provider。
- 撤销授权后立即禁止新任务，运行中远端任务进入人工处置；已有项目引用保留审计但不允许再次生成。
- 删除先产生 tombstone 和引用报告，再删除本地模型、参考录音派生物和远端 voice binding；远端删除必须保留请求和完成证据。
- 诊断包不得包含参考录音、声纹、密钥或可回放样本。

### 10.4 防滥用边界

- 本期只允许本人声音或有明确书面授权的声音。
- 不提供绕过授权、冒充他人或批量抓取声音的入口。
- UI 持续显示当前声音身份、模型 revision、授权状态和适用范围。

## 11. 项目 AI05：外部服务可靠批处理

### 11.1 批次模型

RemoteBatchV1 由 batch、item、segment 和 attempt 四层组成：

- batch：项目、Provider、策略、预算和总状态。
- item：页面或目标产物。
- segment：长文本分段或媒体分片。
- attempt：一次具体供应商请求。

批次状态：

- draft
- awaiting_confirmation
- queued
- running
- partially_succeeded
- paused
- remote_unknown
- failed
- cancelled
- succeeded

### 11.2 可靠性规则

- 每个 segment 有稳定 idempotency_key、输入 hash 和 provider_request_id。
- 成功 segment 永不自动重复生成。
- 重启后从持久状态恢复，只重跑 failed 且允许重试的 segment。
- 取消只终止 owned 本地请求；供应商已接受的请求必须继续对账。
- 网络恢复后先 query/reconcile，再决定是否重试。
- 最终页面音频在所有 segment 校验通过后一次性原子发布。
- 批次可以部分成功，但项目正式音频发布仍需页面级完整。

### 11.3 HeyGen 专项

- 复用现有三次请求、指数退避、长文本分段和缓存逻辑。
- 增加批次持久化、费用保留、远端 request 查询、未知状态和人工恢复入口。
- 真实 canary 必须使用非敏感两页样本、明确 voice ID、候选身份和硬费用上限。
- HeyGen 不可用时，不得阻断本地导入音频或本地 TTS。
- 若切换到不同声音，必须要求用户确认，不能静默降级。

## 12. 项目 AI06：AI 内容辅助

### 12.1 旁白润色

- 输入为冻结的旁白 revision、风格配置、长度目标和页面上下文。
- 输出为候选 revision，不修改 confirmed revision。
- 提供逐段差异、长度变化、事实/数字保留检查和一键拒绝。
- 未提供材料证据时禁止新增具体事实、数字、引用或承诺。
- 支持本地规则模式：去口头重复、标点规范和长度提示，不需要 LLM。

### 12.2 智能断句

- 优先使用确定性标点、长度、停顿和页面边界算法。
- 可选 AI 只调整候选边界，不改原文字词。
- 输出每段字符数、预计时长、跨页风险和修改原因。
- 用户确认后生成新的 segmentation revision，并使受影响音频/字幕候选 stale。

### 12.3 字幕翻译

- 基于 SubtitleDocument V2，保留 cue ID、时间和源语言文本。
- 翻译只创建 target-language track，不覆盖源字幕。
- 支持术语表、禁译词、数字/单位保护和逐 cue 确认。
- 不允许 AI 自动移动已确认时间码；需要重排时生成独立候选。
- 导出前要求翻译 track 的 review 状态满足项目策略。

### 12.4 内容安全和质量

- 检查空输出、截断、语言错误、数字丢失、术语不一致和结构漂移。
- 模型拒答、超时或 schema 错误时保留原文并给出可执行提示。
- 用户可以完全关闭 AI 内容辅助，手工旁白和字幕工作流继续运行。

## 13. API 与界面

### 13.1 模型中心 API

- GET /api/ai/models
- GET /api/ai/models/{model_id}/revisions
- POST /api/ai/models/install
- POST /api/ai/models/{model_id}/probe
- POST /api/ai/models/{model_id}/activate
- POST /api/ai/models/{model_id}/rollback
- DELETE /api/ai/models/{model_id}/revisions/{revision}

安装、更新和删除是有副作用操作，必须有 CSRF/本地用户校验、明确确认和审计。

### 13.2 Provider API

复用现有 /api/providers，并增加：

- 路由策略预览。
- 预算保留和消费摘要。
- 限流状态。
- failover 决策解释。
- unknown remote operation 对账。

API 只返回 reason code、金额、非敏感元数据和引用，不返回 secret。

### 13.3 声音 API

- GET/POST /api/voices
- POST /api/voices/{id}/references
- POST /api/voices/{id}/consent
- POST /api/voices/{id}/clone
- POST /api/voices/{id}/preview
- POST /api/voices/{id}/activate
- POST /api/voices/{id}/revoke
- DELETE /api/voices/{id}

### 13.4 内容辅助 API

- POST /api/projects/{id}/narration/polish
- POST /api/projects/{id}/narration/segment
- POST /api/projects/{id}/subtitles/translate
- GET /api/projects/{id}/ai-candidates
- POST /api/projects/{id}/ai-candidates/{candidate_id}/accept
- POST /api/projects/{id}/ai-candidates/{candidate_id}/reject

所有 mutation 使用 expected_revision，冲突返回 409。

### 13.5 UI 信息架构

设置中心新增：

- 本地模型。
- AI 供应商。
- 费用与限流。
- 我的声音。
- 远端任务。
- 隐私与诊断。

项目工作流新增的是候选和状态面板，不新增第二套旁白、音频或字幕编辑器。

## 14. 数据、缓存与失效

### 14.1 权威数据

- 模型 manifest 是模型文件权威。
- Provider policy revision 是路由权威。
- Cost ledger 是费用权威。
- Voice consent record 是声音授权权威。
- 项目 narration/subtitle/audio active revision 是业务权威。
- Provider 原始响应不是项目权威。

### 14.2 缓存键

Provider 缓存至少绑定：

- tenant/workspace、project。
- provider、adapter version、capability、model revision。
- input fingerprint、parameters、prompt revision。
- policy fingerprint、data classification、region。
- voice identity/model revision。

费用价格变化不必使已生成资产失效，但新调用必须使用新 price book。

### 14.3 失效规则

- 源旁白变化：润色、断句、TTS 和翻译候选 stale。
- model revision 变化：新任务使用新 revision，旧成功资产仍可读取。
- 声音授权撤销：阻断新合成，不删除项目历史审计。
- Provider policy 收紧：阻断不符合的新任务，运行中任务按冻结策略和撤销级别处理。
- credential rotation：缓存内容不失效，未完成远端 attempt 必须重新认证或人工处置。

## 15. 安全、隐私与合规

- 密钥只存 Windows CurrentUser 凭证服务或等价受保护存储。
- 项目、日志、数据库业务表和诊断包只保存 credential_ref。
- 所有远端输入在调用前显示数据分类、目标 Provider、区域、保留策略和费用上限。
- 本人声音参考录音默认 restricted。
- 远端样本探测可能计费时必须二次确认。
- 输入和输出日志默认只保存 hash、长度、语言、状态和 request ID。
- 支持选择性导出非敏感诊断；禁止导出原始旁白、字幕、音频和声音样本。
- 适配器注册只允许 builtin_signed 或经过审计的 builtin_local_process。
- 所有路径通过 workspace ownership 校验；API 不接收任意绝对路径。

## 16. 可观测性

统一事件至少包括：

- model_install_started/progress/verified/activated/failed。
- model_runtime_loaded/unloaded/degraded。
- provider_route_considered/selected/rejected。
- provider_budget_reserved/committed/released/reconcile_required。
- provider_rate_limited。
- provider_failover_considered/applied/blocked。
- voice_consent_activated/revoked。
- remote_batch_item_started/succeeded/failed/unknown。
- content_candidate_generated/accepted/rejected/stale。

指标不得包含密钥、原始文本或音频。费用指标按 Provider、capability 和项目聚合，但对诊断导出进行最小化。

## 17. 测试策略

### 17.1 单元测试

- 模型状态机、manifest、hash、磁盘预算、租约和回滚。
- Provider 策略过滤、预算保留、限流、公平性和 failover 矩阵。
- 声音授权状态、过期、撤销、作用域和引用保护。
- 旁白/断句/翻译候选的 stale 和 revision guard。

### 17.2 契约测试

- JSON Schema 与 Python 模型一致。
- 所有 Provider Adapter 通过统一 adapter contract。
- 稳定 reason code、状态集合和金额表示。
- 旧 ProviderPolicyV1 和项目数据可确定性读取。

### 17.3 集成测试

- 无网络、无凭证、全部远端 Provider disabled 时，本地全链仍通过。
- ASR/TTS 模型安装中断后恢复，不留下半成品。
- 超时前后 billed state 不同的重试和切换结果。
- HeyGen 八页批次只重试失败页面/分段。
- 声音授权撤销后新任务被阻断。
- AI 内容候选接受、拒绝、冲突和 stale。

### 17.4 物理 Windows 验收

- 普通用户安装版中的模型安装、重启发现、CPU 推理和卸载保护。
- 断网启动与本地 PPT、音频、字幕、预检、播放、导出。
- 本人声音本地预览和授权撤销。
- 经过费用授权的两页 HeyGen canary。
- 当前候选上的凭证轮换、限流、超时、取消和恢复。

### 17.5 真实外部 Gate

自动化 fake、mock 和本地桥接不能替代：

- 真实供应商凭证。
- 真实价格/usage/charge。
- 真实 request ID 和对账。
- 真实声音授权。
- 当前候选 Windows 运行记录。

缺任一证据时对应 Provider 保持 WAIT_EXTERNAL，不影响 LOCAL_AUDIO_INDEPENDENT。

## 18. 验收 Gate

### Gate AI-G0：LOCAL_AUDIO_INDEPENDENT

- 禁用网络和全部远端 Provider。
- 使用已安装本地 ASR/TTS 或导入音频完成主链。
- 打开、编辑、预览、预检和导出不访问 Provider API。
- Provider 控制面损坏时应用进入 local_only 而不是启动失败。

### Gate AI-G1：LOCAL_MODEL_CENTER_READY

- ASR/TTS 模型安装、校验、探测、激活、回滚和引用保护通过。
- 安装中断和磁盘不足不会污染 active revision。
- UI 不隐藏许可证、大小、设备和联网需求。

### Gate AI-G2：PROVIDER_ADAPTERS_READY

- LLM、ASR、TTS、renderer 每类至少有一个本地/内置实现。
- 需要远端生产声明的能力至少有一个真实 Adapter 和 canary。
- 所有 Adapter 通过契约、错误、脱敏和取消测试。

### Gate AI-G3：PROVIDER_GOVERNANCE_READY

- 预算、限流、幂等、重试、切换和 unknown billing 全矩阵通过。
- 重启后账本、保留额度和限流状态恢复。
- 无任何超预算或重复计费案例。

### Gate AI-G4：VOICE_IDENTITY_READY

- 本地声音身份、授权、模型 revision、预览、激活、撤销和删除通过。
- 未授权或已撤销声音无法生成。
- 远端 voice binding 有独立授权和删除证据。

### Gate AI-G5：REMOTE_BATCH_READY

- 八页以上批次支持取消、重启、部分失败、逐段恢复和费用汇总。
- 成功页面不重复生成。
- remote_unknown 必须对账，不自动二次付费。

### Gate AI-G6：AI_CONTENT_ASSIST_READY

- 润色、断句和翻译均为候选 revision。
- 原文、数字、术语、时间码和人工确认受到保护。
- 关闭 AI 后手工工作流完整可用。

### Gate AI-G7：AI_PROVIDER_PLATFORM_READY

- AI-G0 至 AI-G6 全部 PASS。
- 当前候选身份、策略、模型 manifest、Provider Adapter、价格版本、测试与 Windows 证据绑定一致。
- 第二轮未完成项审计为零；真实外部可选 Provider 可以保持 WAIT_EXTERNAL，但不得冒充 PASS。

## 19. 发布和迁移

### 19.1 Feature flags

建议使用：

- ai_model_center_v1
- provider_routes_v2
- provider_governance_v1
- voice_identity_v1
- remote_batch_v1
- ai_content_assist_v1

默认顺序：内部只读 → 本地功能可写 → 远端 dry-run → 受控 canary → opt-in stable。任何阶段都可关闭远端 flag 并继续本地生产。

### 19.2 数据迁移

- 旧 ASR 目录读取为 legacy model record，不移动文件；用户激活新模型时才原子导入。
- 旧 HeyGen profile 转换为 Provider credential metadata 和 voice binding 引用，密钥不复制到项目。
- 旧页面 HeyGen 音频保留原 cache key、request ID 和 active revision。
- 旧项目无 AI policy 时使用内存 local-first 策略。
- 回滚必须继续读取已经发布的本地音频和字幕，不要求安装新模型。

## 20. 工作量与顺序

在不包含真实供应商商务协调的情况下，建议工程量：

| 项目 | 估算 |
| --- | --- |
| AI01 本地模型中心 | 8–12 个工程日 |
| AI02 统一适配生产化 | 8–12 个工程日 |
| AI03 预算、限流和切换 | 7–10 个工程日 |
| AI04 声音克隆与授权 | 10–15 个工程日 |
| AI05 远端可靠批处理 | 7–10 个工程日 |
| AI06 内容辅助 | 8–12 个工程日 |
| 集成、Windows 验收和二次收口 | 6–10 个工程日 |

推荐严格串行实施 AI01 → AI02 → AI03 → AI04 → AI05 → AI06。真实外部 canary 可在对应功能工程完成后等待授权，但不得阻塞后续本地工程开发。

## 21. 完成定义

本设计完成时：

- 用户不配置任何外部接口，也能使用本地音频链完成 PPT 转视频。
- 用户可以安全管理本地 ASR/TTS 和本人声音模型，清楚知道大小、来源、许可证、设备和授权状态。
- 所有远端 AI 调用都有显式 Provider、数据范围、预算、request ID、结果、费用和审计。
- 失败切换不会扩大费用、区域、数据或声音授权，也不会重复计费。
- HeyGen 等长任务可逐页/逐段恢复，成功结果不会被重复生成。
- 旁白润色、断句和字幕翻译都以可比较、可拒绝、可回滚的候选形式进入现有工作流。
- 关闭所有 AI 和远端 feature flags 后，项目仍能打开并使用已有本地资产完成预检和导出。
