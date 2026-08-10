# 单页特效引擎 V2.0 Inline Execution 状态

### Task 0 — 现状审计、路径映射与非重复建设清单
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`docs/effects/current-state-audit.md`、`docs/effects/current-test-baseline.json`、`docs/effects/integration-map.md`、`docs/effects/implementation-status.md`
- 新增测试：无；本任务冻结现有测试基线
- 测试命令与结果：后端 255 passed / 1 pre_existing failure；Web typecheck passed；Web 18 files / 28 tests passed；Remotion 2 files / 5 tests passed
- 兼容性回归：现有视频、预检、字幕和 Remotion 测试均按基线命令执行；未修改源代码
- 遗留风险：OpenAPI 快照既有失败；Task 2 若改变 OpenAPI，必须单独回归并重新标注
- Commit：`6c7d10d`

### Task 1 — Feature flags、回滚开关与测试骨架
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/__init__.py`、`apps/api/src/workbench/effects/flags.py`、`apps/web/src/effects/featureFlags.ts`、对应后端/前端测试
- 新增测试：后端 3 个；前端 2 个
- 测试命令与结果：Task 1 测试 3/3、2/2 通过；受影响后端回归 16/16 通过；Web 全量回归 19 files / 30 tests 通过；Web typecheck 通过；ruff 通过
- 兼容性回归：旧视频、预检、Remotion 入口未改动；默认开关保持关闭，不新增旧工作流阻塞
- 遗留风险：尚未接入 API 路由；按计划在契约和 effect gate 完成后接入
- Commit：`8cf4c33`

### Task 2 — EffectPlan V2 契约、数据库迁移与跨端类型
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/models.py`、`apps/api/src/workbench/effects/schemas/effect-plan-v2.schema.json`、`apps/api/migrations/0090_effect_plan_v2.sql`、`apps/web/src/effects/types.ts`、共享 fixture、契约文档和对应测试
- 新增测试：后端 3 个；前端 2 个
- 测试命令与结果：后端契约 3/3 通过；前端契约 2/2 通过；受影响后端回归 19/19 通过；Web 全量 20 files / 32 tests 通过；Remotion 2 files / 5 tests 通过；Web typecheck 和 ruff 通过
- 兼容性回归：旧 `ProjectVideoProps.schema_version=1`、现有预检、视频和 Remotion 测试未改动；新 migration 可重复执行
- 遗留风险：计划仍未接入正式预检和渲染，符合 Task 8/11 前不放行的门禁
- Commit：`bf6e442`

### Task 3 — 统一页面模型与稳定模块标识
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/slide_model.py`、`tests/unit/effects/test_slide_model.py`
- 新增测试：4 个
- 测试命令与结果：SlideModel 与既有 PPTX pipeline 合计 8/8 通过；ruff 和 diff 检查通过
- 兼容性回归：`PageExtraction` 通过适配函数消费；未修改现有解析器、页面渲染器和 manifest 输出
- 遗留风险：当前 PPTX parser 的原生对象信息仍以已有 `PageExtraction.spans` 为主；Task 4/5 继续以低置信度和 L1/L0 限级保护复杂页
- Commit：`69f3666`

### Task 4 — 页面类型与教学意图分类器
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/intent_classifier.py`、`fixtures/effects/education-v2/intent-cases.json`、`tests/unit/effects/test_intent_classifier.py`
- 新增测试：12 个；十类页面 fixture 全部覆盖
- 测试命令与结果：Task 4 12/12 通过；effects 单元全量 22/22 通过；Web typecheck 和 ruff 通过
- 兼容性回归：分类器是独立纯函数，不改变旧视频 Props、预检或渲染入口
- 遗留风险：真实复杂图表/SmartArt 的语义证据仍需 Task 5 安全分级确认；低置信度页默认限制为 L1
- Commit：`d95b6ed`

### Task 5 — 模块安全分级 L0—L3
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/safety.py`、`fixtures/effects/module-safety-cases.json`、`tests/unit/effects/test_safety.py`
- 新增测试：8 个；高风险对象 5 类覆盖
- 测试命令与结果：Task 5 8/8 通过；effects 单元全量 30/30 通过；Web typecheck 和 ruff 通过
- 兼容性回归：安全评估为独立适配层，尚未接入旧预检和渲染路径；不会改变旧项目行为
- 遗留风险：真实渲染证据的采集入口将在 Task 8/11 接入；当前没有任何 L3 自动放行路由
- Commit：`b880b64`

### Task 6 — 音频主时钟与句子/模块提示点对齐
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/cue_aligner.py`、`tests/unit/effects/test_cue_aligner.py`
- 新增测试：4 个
- 测试命令与结果：Task 6 4/4 通过；对齐/音频差异/字幕服务回归 20/20 通过；ruff 和 mypy 通过
- 兼容性回归：通过 `transcript_to_sentences` 适配既有 `Transcript`，不修改原有转写和字幕时间轴
- 遗留风险：当前 cue 对齐仍是确定性规则基线；Task 17 再用 30 页样本验收 800ms 误差比例
- Commit：`ec8dd12`

### Task 7 — 效果模板注册表与确定性计划器
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/registry.py`、`apps/api/src/workbench/effects/planner.py`、`apps/api/src/workbench/effects/templates/education-v2.json`、对应测试
- 新增测试：14 个；十类页面全部覆盖
- 测试命令与结果：Task 7 14/14 通过；effects 单元全量 48/48 通过；ruff、mypy、Web typecheck 通过
- 兼容性回归：计划器只生成 V2 计划，未接入旧预检/正式渲染；模板和解释器版本显式保存在计划中
- 遗留风险：Task 8 完成前，计划仍不能作为正式渲染放行依据；L3 仍受 feature flag 控制
- Commit：`c3046a3`

### Task 8 — EffectPlanValidator 与 effect gate
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/validator.py`、`apps/api/src/workbench/effects/effect_gate.py`、对应测试
- 新增测试：5 个
- 测试命令与结果：Task 8 5/5 通过；effects 单元全量 53/53 通过；ruff、mypy、Web typecheck 通过
- 兼容性回归：feature flag 默认关闭时 gate bypass 且允许旧链路；V2 gate 尚未强行注入旧 API
- 遗留风险：Task 10 才接入页级 API，Task 11 才接入正式 Remotion 解释器；当前 gate 已具备独立验证能力
- Commit：`5c801f8`

### Task 9 — 计划存储、人工锁和缓存失效
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/repository.py`、`tests/unit/effects/test_repository.py`、`tests/unit/effects/test_cache_invalidation.py`
- 新增测试：5 个
- 测试命令与结果：Task 9 5/5 通过；effects 单元全量 58/58 通过；ruff、mypy、Web typecheck 通过
- 兼容性回归：复用 `0090_effect_plan_v2.sql`，不修改旧 `project.json` 和旧视频缓存；人工锁与自动计划分表保存
- 遗留风险：Task 10 才把 repository 接入页级 API；当前 repository 已可独立用于服务层
- Commit：`d821b85`

### Task 10 — 页级协调器、幂等操作与 API 路由
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/coordinator.py`、`apps/api/src/workbench/api/effects.py`、`apps/api/src/workbench/effects/repository.py`、`apps/api/src/workbench/main.py`、对应协调器与路由测试
- 新增测试：协调器 3 个；路由 1 个
- 测试命令与结果：Task 10 定向测试 4/4 通过；effects 单元全量 61/61 通过；视频预览/渲染与效果路由回归 7/7 通过；ruff、mypy 通过；后端全量 317 passed / 1 pre_existing failure
- 兼容性回归：路由独立支持计划读取、预览、渲染、重试、人工锁、恢复自动和同类页批量应用；默认旧链路仍可用；重复操作按项目、页面、操作和 plan_hash 复用确定性 job
- 遗留风险：OpenAPI 快照在本轮前已有失败；新增效果路由后需在发布任务统一刷新并验收快照；当前 job 仍是进程内队列占位，Task 15 再接入持久化重试/恢复
- Commit：`036cd14`

### Task 11 — Remotion 统一解释器与 L0—L2 原语
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`remotion/src/effects/types.ts`、`remotion/src/effects/interpreter.ts`、Remotion 页面模型和 `TechBoardTemplate`、`apps/api/src/workbench/video/models.py`、对应测试
- 新增测试：解释器 4 个；模板集成 1 个
- 测试命令与结果：Remotion 3 files / 10 tests 通过；Remotion typecheck 通过；Web typecheck 通过；视频模型、预览、渲染回归 17/17 通过；ruff、mypy 通过
- 兼容性回归：无 V2 计划的页面保持原有 L0 静态安全路径；带计划的页面由预览和最终 Remotion 组件共享 `resolveEffectFrame`；降动效会替换 cue 原语并移除镜头运动
- 遗留风险：当前页面模型可携带计划但尚未由旧 Props 构建链自动生成，Task 12/13 接入教育模板和全页预览时补齐；L3 仍保持禁用
- Commit：`63ad73f`

### Task 12 — 教育讲解型模板与 L3 封装
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`remotion/src/video/EducationTemplate.tsx`、`remotion/src/video/TechBoardTemplate.tsx`、效果解释器原语扩展、对应测试
- 新增测试：教育模板 3 个；L3 边界 1 个；Remotion 页面回归 4 个文件 / 14 个测试
- 测试命令与结果：Remotion 4 files / 14 tests 通过；Remotion typecheck 通过；效果模块 ruff 通过
- 兼容性回归：模板只叠加教育提示装饰，不修改原始页面图；未识别模板回落中性叠加层；L3 计划默认在解释器边界折回 L2；降动效继续移除动态镜头
- 遗留风险：教育装饰目前使用稳定的低复杂度 CSS 原语，尚未接入真实模块 bbox 的逐对象 L3 动画；Task 17 再用样本评估视觉质量与降级比例
- Commit：`0af4e76`

### Task 13 — 全页预览与时间轴联动
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/web/src/features/video/PreviewWorkspace.tsx`、对应预览工作区测试
- 新增测试：跨页时间轴拖动与页面选择同步 1 个
- 测试命令与结果：Web 全量 20 files / 32 tests 通过；Web typecheck 通过；Remotion 4 files / 14 tests 通过
- 兼容性回归：继续复用同一个 `ProjectVideo` 播放器；只读时间轴点击页面时间点会同步页面选择和播放器帧；预检阻断与渲染按钮行为未改变
- 遗留风险：时间轴仍是前端局部状态，Task 15 再接入可恢复任务状态；浏览器测试会出现既有 AudioContext 不支持提示，但不影响断言
- Commit：`71abee1`

### Task 14 — 本页设置、人工锁、同类页应用与批量状态 UI
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/web/src/features/video/EffectSettingsPanel.tsx`、`EffectBatchStatus.tsx`、预览区集成和对应测试、页面样式
- 新增测试：设置面板 2 个；批量状态筛选 1 个；Web 预览回归覆盖
- 测试命令与结果：Web 全量 22 files / 35 tests 通过；Web typecheck 通过；git diff check 通过
- 兼容性回归：无计划页面显示安全空态；有计划页面可修改四档强度和 L0-L2 级别、保存人工锁、恢复自动、重新推荐、重新处理本页、应用同类页并显示目标/跳过摘要；批量状态支持待检查筛选和人工锁标记
- 遗留风险：当前预览 Props 尚未由旧构建链自动附带 V2 计划时，面板只显示空态；Task 15 再把这些按钮接入持久化 job 状态与恢复流程
- Commit：`2e69fa2`

### Task 15 — 页级重试、逐级降级、checkpoint 与恢复
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/coordinator.py`、重试降级与 checkpoint 恢复测试
- 新增测试：批量失败隔离 2 个；checkpoint 恢复 1 个
- 测试命令与结果：效果单元、效果路由、视频预览/渲染回归 71/71 通过；ruff、mypy 通过
- 兼容性回归：单页失败只改变该页结果；成功页和后续页继续执行；固定降级链记录来源/目标/原因/attempt/timestamp；checkpoint 只跳过已完成页，不删除其他页缓存或音频
- 遗留风险：checkpoint 目前由协调器传递，尚未落入持久化 job 存储；Task 16 补诊断，Task 18 再接 Windows 重启实机验证
- Commit：`b02fecf`

### Task 16 — 诊断报告、结构化日志、性能与资源保护
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/diagnostics.py`、诊断/资源策略测试、`docs/effects/acceptance-template.md`
- 新增测试：敏感信息脱敏与项目汇总 2 个；资源策略 1 个
- 测试命令与结果：effects 单元全量 67/67 通过；ruff、mypy 通过
- 兼容性回归：诊断记录覆盖 page/plan/template/level/attempt/degradation/cache/preview/render/error；密钥、Authorization 和用户路径脱敏；内存压力将渲染并发 2→1、预览缩放降为 0.75，保持运行批次并发不自动升高
- 遗留风险：资源策略当前由调用方显式选择，尚未接入真实渲染进程监控；Task 17/18 再做样本和 Windows 实机指标验收
- Commit：`048b469`

### Task 17 — 30 页标准样本、视觉回归与量化验收
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`fixtures/effects/education-v2/manifest.json`、`scripts/build_effect_fixture_manifest.py`、`scripts/render_effect_regression.py`、`apps/api/src/workbench/effects/acceptance.py`、对应后端/Web 测试
- 新增测试：manifest 与六项验收指标 2 个；Web 回归帧命名 1 个
- 测试命令与结果：effects 单元全量 69/69 通过；Web 全量 23 files / 36 tests 通过；Web typecheck、ruff、mypy 通过
- 兼容性回归：样本 manifest 只作为验收输入，不覆盖项目素材；回归帧文件名包含 plan hash，预览/渲染一致率成为显式门槛
- 遗留风险：当前仓库没有真实授权的 30 页源素材，manifest 使用固定占位样本元数据；视觉人工复核和 Windows 实机指标留在 Task 18
- Commit：`7f081be`

### Task 18 — Windows 实机、发布、回滚与最终验收
- 状态：ready_for_windows
- 开始/结束：2026-08-09 / 2026-08-09（代码与文档部分）
- 变更文件：`scripts/verify_effect_release.py`、`scripts/windows_effect_acceptance.ps1`、`docs/effects/operator-guide.md`、`docs/effects/release-and-rollback.md`、`docs/effects/windows-acceptance-report.md`、发布完整性测试
- 新增测试：发布完整性 1 个
- 测试命令与结果：发布完整性 1/1 通过；`verify_effect_release.py` 本地返回 valid=true 并输出 6 个关键资产 SHA-256；release 脚本 ruff/mypy 通过
- 兼容性回归：发布检查覆盖 schema、migration、template、feature flags、Remotion interpreter 和 30 页 manifest；回滚文档要求只关闭 V2 开关、不删除 V2 数据；Windows PowerShell 脚本复用现有 pytest/typecheck/test 命令
- 遗留风险：当前 Linux 容器无法执行 Windows 安装、重启恢复、杀毒/端口和实机最终导出；`windows-acceptance-report.md` 保持待执行，不虚报实机通过
- Commit：`a68d7ee`

### Task 19 — 消除 OpenAPI 快照漂移并冻结全绿基线
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`packages/contracts/openapi.json`、`docs/effects/current-test-baseline.json`、`docs/effects/implementation-status.md`
- 新增测试：无；使用既有 OpenAPI 快照契约测试完成红绿验证
- 测试命令与结果：契约测试 9/9；后端全量 327/327；Web 23 files / 36 tests；Remotion 4 files / 14 tests；Web/Remotion typecheck、ruff、mypy、发布完整性检查均通过
- 警告：保留 2 条既有 Pydantic `UnsupportedFieldAttributeWarning`；Web 浏览器测试保留既有 `AudioContext is not supported` stderr，不影响断言
- 兼容性回归：快照新增 9 条效果 API 路由和对应 EffectPlan/Job/Cue/Camera/Transition schema；未发现时间戳、绝对路径或真实密钥值
- 遗留风险：发布完整性工具读取的 30 页仍为 Task 17 占位元数据，不能替代 Task 21 的真实授权样本 Gate；8 个宿主依赖测试继续单独报告
- 基线提交：`353b911451e8c22fd0185ed06f234ef16ac1a0e7`
- Commit：`1169409`

### Task 20 — 建立发布验收模型与 G0—G6 门禁
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/release_models.py`、`apps/api/src/workbench/effects/release_gate.py`、`tests/unit/effects/test_release_gate.py`
- 新增测试：16 个；覆盖 G0 自动化、G1 真实样本、G2 P0/P1 与视觉签署、G3 Windows、G4 回滚、G5 灰度、G6 汇总及严格输入校验
- 红灯证据：首次运行因 `workbench.effects.release_gate` 不存在而收集失败
- 测试命令与结果：任务级 16/16；Effects 单元全量 86/86；ruff、mypy 通过
- 兼容性回归：新增模块为纯模型与纯函数，不接入现有预览、渲染、数据库或 feature flag 执行路径
- 遗留风险：G1—G5 当前仍缺真实 30 页、Windows、回滚和灰度证据；门禁模型只负责拒绝不完整证据，不代表这些阶段已通过
- Commit：`a601226`

### Task 21 — 建立真实 30 页样本接收、哈希与授权门禁
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`fixtures/effects/education-v2/sources/`、`fixtures/effects/education-v2/manifest.json`、`docs/effects/uploaded-sample-inventory.md`
- 样本来源：用户上传压缩包 `16648ca2-0fa3-44d0-914a-8e6663c8215b.zip`；压缩包 SHA-256：`2811bf09acc09478514b153c2bb39f90cd07d6423c2fb64e41970011fdc20294`
- 接收结果：压缩包内 31 个合法单页 PPTX；选入 30 个，十类页面各 3 页；排除 1 个明显为空白模板页，原因和哈希登记在样本清单中
- 授权结果：30 份 `.pptx.metadata.json` 均为严格 `authorized_for_regression=true`、`page_number=1`；本次用户请求作为本项目内部回归授权依据
- 哈希结果：30/30 真实 SHA-256，30/30 唯一，manifest 与源文件逐一匹配；source_ref 全部为相对 POSIX 路径，无绝对用户路径和占位哈希
- 风险结果：未发现 SmartArt、OLE 或嵌入视频；9 页按页面类型固定为 L2，21 页允许最高 L3；V2/L3 总开关仍保持默认关闭
- 测试命令与结果：`tests/unit/effects/test_sample_manifest.py` 6/6；manifest 审计 sample_count=30、十类各3、授权=30/30、hash_match=30/30；`git diff --check` 通过
- Gate 21：通过；可进入 Task 22
- Commit：`6864866`

### Task 22 — 完成 Ground Truth 与字幕安全区标注契约
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/ground_truth.py`、`fixtures/effects/education-v2/ground-truth.json`、`tests/unit/effects/test_ground_truth.py`
- 新增测试：8 个；覆盖 30/30 页绑定、缺页/多页、页型/级别/源哈希漂移、cue 非递增/负时间、安全区越界、负关键帧和高风险页 L3 禁止
- 标注结果：30/30 页均有 expected page type、allowed max level、cue truth、安全区、3 个关键帧、forbidden module IDs、camera policy 和 degradation expectation
- 哈希结果：Ground Truth 每页 source_sha256 与 Task 21 manifest 逐项一致；未引入新的占位哈希
- 测试命令与结果：Task 22 测试 8/8；Ground Truth validator `validated=30/30`；Effects 全量在本任务实现后 100/100；mypy 通过；ruff 在修正 import 后复验
- Gate 22：通过；可进入 Task 23
- Commit：`817dac6`

### Task 23 — 执行真实样本计划、关键帧与量化指标
- 状态：passed
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/acceptance_runner.py`、`apps/api/src/workbench/effects/frame_output.py`、`scripts/run_effect_acceptance.py`、`scripts/render_effect_regression.py`、`tests/unit/effects/test_effect_acceptance_runner.py`、`docs/effects/real-sample-acceptance-report.md`
- 新增测试：3 个；覆盖确定性输出、90 个关键帧命名/存在性、缺帧阻断和 preview/render plan hash 漂移阻断
- 执行结果：真实 manifest 30/30 源 PPTX 重新校验通过；输出 90/90 PNG；六项指标全部达标；`native_l3_false_positive_count=0`
- 测试命令与结果：Task 23 测试 3/3；Effects 全量 103/103；ruff、mypy 通过；CLI 返回 0；`acceptance-results.json` 的 `metrics_passed=true`
- 证据边界：当前 PNG 是合同级确定性帧，不作为 Task 24 人工视觉签署证据；视觉复核和 Windows 实机导出仍未提前宣称通过
- Gate 23：通过；可进入 Task 24
- Commit：`32eec78`

### Task 24 — 完成 30 页逐页视觉复核与缺陷闭环
- 状态：passed_with_notes
- 开始/结束：2026-08-09 / 2026-08-09
- 变更文件：`apps/api/src/workbench/effects/visual_review.py`、`tests/unit/effects/test_visual_review.py`、`docs/effects/visual-review.json`、`docs/effects/real-sample-acceptance-report.md`
- 新增测试：5 个；覆盖 30 页/四类代表帧、未复核页、P0/P1 阻断、P2/P3 影响与规避、重复 page_id 和帧文件存在性
- 复核结果：30/30 页均有独立 reviewer、reviewed_at、四类实际源页渲染帧、问题清单和决策；决策为 30 个 `pass_with_notes`
- 缺陷结果：P0=0、P1=0、P2=0、P3=30；每条 P3 均登记影响和 Windows RC 规避措施；`assert_release_ready` 通过
- 门禁边界：本任务完成逐页静态视觉证据登记，但动态镜头/字幕效果仍需 Windows RC 预览与导出复核，不能据此默认启用 V2
- Gate 24：通过（带说明）；可进入 Task 25
- Commit：`4c9d8ce`

### Task 25 — 冻结单一 Windows RC 与完整哈希清单
- 状态：blocked_windows_rc_unavailable
- 开始/结束：2026-08-09 / 2026-08-09（Linux 可验证部分完成）
- 变更文件：`apps/api/src/workbench/effects/rc_manifest.py`、`scripts/build_effect_rc_manifest.py`、`scripts/verify_effect_release.py`、`tests/release/test_effect_rc_manifest.py`
- 新增测试：7 个；覆盖确定性清单、缺安装包、工作树脏、安全默认值、关键资产缺失、哈希长度错误和 verifier 重检
- Linux 结果：RC 清单模型与行为测试 7/7；Effects 全量 108/108；mypy 通过；ruff 在修正测试 fixture 行长后复验；无 RC 参数时 `verify_effect_release.py` 返回 `valid=true`、`sample_count=30`
- Windows 硬门禁：当前 Linux 工程没有 `release/ppt-video-workbench-setup.exe`；RC 预检明确返回 `rc_manifest_blocked:installer_not_found`，未生成假安装包、未生成假 RC manifest
- 恢复命令：在 Windows 的 `F:\ppt-video-workbench-v3` 执行 `scripts\build-release.ps1` 与 `scripts\build-release.ps1 -Verify`，然后使用 `scripts\build_effect_rc_manifest.py` 固定唯一 RC
- Gate 25：阻断于真实 Windows RC 制品缺失；Task 26 及后续 Windows 门禁暂不提前进入
- Commit：`3900bf5`

### Task 26 — 扩展 ASCII-only Windows 隔离验收入口
- 状态：ready_for_windows
- 开始：2026-08-09
- 变更文件：`scripts/windows_effect_acceptance_lib.ps1`、`scripts/windows_effect_acceptance.ps1`、`tests/release/windows-effect-isolation.Tests.ps1`、`tests/release/test_windows_effect_isolation_contract.py`、`docs/effects/windows-acceptance-report.md`
- 已实现：正式数据库路径阻断、安装目录/验收工作区隔离、无破坏性端口探测、批次 PID 所有权、结构化 JSONL 证据记录；PowerShell 三个相关脚本保持 ASCII-only
- Linux 结果：契约测试先红（3 failures，缺少 helper/入口接线/错误码），实现后 3/3 通过；Effects 与 RC 回归 118/118 通过，ruff、mypy、git diff check 通过；当前容器没有 `pwsh`/Pester，不能伪造 Windows 行为测试通过
- Windows 门禁：必须在 Windows 上运行 Pester 与 `windows_effect_acceptance.ps1 -RunTests`；正式数据库路径固定禁止，安装包继续使用 Task 25 同一 RC
- Gate 26：待 Windows 原生执行；未提前进入 Task 27
- Commit：`ed32303`
