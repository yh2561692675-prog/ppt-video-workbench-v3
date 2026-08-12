# PPT Video Workbench V1 调试与生产验收逐项实施计划

> 本计划只负责调试基础设施、验证、缺陷闭环和发布证据。产品功能修复必须返回 A/B/C 来源线；当前 Windows、Effects 和 W0 活跃窗口未形成停点前，不启动本计划的长时执行任务。

**Goal:** 按“现有窗口停点 → 干净候选 → 全量自动化 → Playwright → 性能压力 → 视觉音画 → 故障恢复 → 并发迁移 → 真实服务 → 安全/UI → 唯一 RC 签署”的顺序，形成可重复、可审计、可发布的 V1 调试结论。

**Design:** `docs/superpowers/specs/2026-08-11-v1-debugging-and-production-acceptance-design.md`

**Upstream Program:** `docs/superpowers/plans/2026-08-11-remaining-major-projects-program.md`

## 1. 启动门禁

以下项目全部满足前，本计划保持 `PLANNED_NOT_STARTED`：

- [ ] 上游 G0 `ACTIVE_LINES_CLOSED` 已通过。
- [ ] Windows 当前全链窗口完成或形成可信 stop point。
- [ ] Effects Task 18-25 当前窗口完成或形成可信 stop point。
- [ ] RenderGraph/最终渲染 stop point 已验证可选择性接入。
- [ ] `foundation_source_commit` 已确定，未知来源文件为 0。
- [ ] 三条长期 worktree 从同一 foundation 派生且 clean。
- [ ] 没有后台安装、Office、LibreOffice、API、Worker、FFmpeg 或浏览器验收进程失去 owner。

若任一条件未满足，只能更新盘点和设计，不得在恢复根目录启动构建、格式化、测试写入或新功能修复。

## 2. 执行责任

| 责任体            | 任务范围                                                             |
| ----------------- | -------------------------------------------------------------------- |
| A 线              | 契约、CI、Playwright、项目/迁移 fixture、Web 竞态、可访问性、诊断 UI |
| B 线              | 媒体、性能、视觉/音画、故障注入、缓存/渲染并发、Windows 工件探针     |
| C 线              | Provider、凭证、预算、隐私、failover、真实服务和 deferred 平台证据   |
| Integration owner | 候选、场景编排、全量 Gate、缺陷路由、证据清单、签署和冻结            |
| Windows operator  | 物理安装、卸载、回滚、重启和实机采证                                 |
| AV reviewer       | 视觉、音频、字幕、Presenter、Effects 人工复核                        |
| Security reviewer | 安全、隐私、SBOM、许可证和供应链签署                                 |

Integration worktree 不长期开发功能。任何产品缺陷都回到 owner line 修复，再以提交进入下一 candidate。

## 3. 全局规则

- [ ] 不从共享 dirty root 构建候选。
- [ ] 不执行 reset、clean、整目录覆盖或最后写入者合并。
- [ ] 每次 run 使用唯一 workspace、数据库、端口、缓存、浏览器/Office profile 和 artifact root。
- [ ] 每个场景保存首轮结果；重跑追加写，不覆盖第一次失败。
- [ ] L3 以上验收只走公开 API、Web、安装器、launcher 和正式 Worker。
- [ ] 付费 Provider、真实云、签名、卸载、回滚和敏感 fixture 使用需要单独授权。
- [ ] 大型 MP4、安装器和运行时不提交 Git，只提交 manifest、hash 和小证据。
- [ ] 每个修复先复现，再提交最小回归测试；禁止用 skip、only、无条件 retry 或降低断言换绿灯。
- [ ] 超时、runner 取消、后台仍运行、退出码未知或日志不完整均为 `blocked`，不是 `passed`。
- [ ] P0/P1 不允许 waiver；P2 waiver 必须有 owner、规避、计划版本和签署。

## 4. 固定目录与命名

建议代码路径：

```text
schemas/debug-candidate-v1.schema.json
schemas/debug-scenario-v1.schema.json
schemas/debug-run-v1.schema.json
schemas/debug-defect-v1.schema.json
scripts/debug_program/
tests/debug_program/
tests/fixtures/debug-program/
docs/acceptance/debug-program/
```

建议非 Git artifact root：

```text
test-results/debug-program/<candidate-id>/<run-id>/
```

若现有恢复根目录 ACL 暂时禁止创建 `docs/acceptance/debug-program/`，不得修改 ACL 或绕过权限。先在已有可写 stop-point 目录记录 `evidence_storage_override`，待 clean integration worktree 建立后迁移为正式路径。

命名规则：

- Candidate：`v1-rc-<short-git>-<UTC timestamp>`。
- Run：`<candidate-id>-<matrix>-<UTC timestamp>-<sequence>`。
- Scenario：`DBG-<domain>-<number>`。
- Defect：`DEF-<candidate>-<sequence>`。

## 5. 固定任务交付物

每个任务必须提交：

1. task ID、owner、source commit、branch 和 owned paths。
2. 明确非目标与外部授权状态。
3. 首个失败测试、非法 fixture 或基线结果。
4. 实现提交及 contract/migration 影响。
5. 定向测试和完整退出码。
6. 证据文件、hash 和 artifact 位置。
7. rollback、safe resume 和是否仍会写入。
8. stop point JSON。

# Phase 0：等待现有窗口并冻结调试来源

## DP00：读取 G0 和三个专项停点

**Owner:** Integration owner。  
**Writes:** 仅调试 Program source inventory。

- [ ] 读取 Windows、Effects、RenderGraph 和 G1-G5 stop point。
- [ ] 校验每个 branch、HEAD、dirty status、owned paths 和 safe resume。
- [ ] 确认 Windows 中断恢复的失败与修复结论已落到同一候选证据。
- [ ] 确认 Effects RC 构建没有把 CRLF/LF 漂移或未知 snapshot 伪装为通过。
- [ ] 登记 P2 分支 57 个共享路径漂移，保持 whole-branch merge 禁止。

**完成标准：** `dp00-upstream-stop-points.json` 中所有 source 可解析，未知项为 0。

## DP01：冻结调试所有权和资源日历

- [ ] 将本计划任务映射到 A/B/C owner。
- [ ] 标记共享路径：CI、schema、OpenAPI、Job、migration、Web client、WorkflowShell、release scripts。
- [ ] 为 S50、长稳、安装器构建和 Windows 实机安排不重叠时间窗。
- [ ] 登记 CPU、GPU、内存、磁盘和受控 Provider 预算。
- [ ] 明确物理卸载、重启和回滚的操作员及授权方式。

**完成标准：** 没有两个活动任务同时写同一 shared path 或复用同一 workspace/runtime profile。

## DP02：确定调试 foundation 和 integration source

- [ ] 读取上游 `foundation_source_commit` 和 G1 integration commit。
- [ ] 验证 commit、锁文件和生成契约可在临时目录重建。
- [ ] 扫描 secret、大文件、绝对用户路径、生成物和用户数据。
- [ ] 记录必须选择性移植的 B/C 提交，不复制 worktree 目录。
- [ ] 创建短生命周期 `codex/program-integration-v1` 或复用上游 Gate worktree。

**完成标准：** source clean、可重建、没有未跟踪源码依赖。

## Gate DG0：DEBUG_SOURCE_READY

- [ ] DP00-DP02 全部通过。
- [ ] G0/G1 source 和本计划 evidence root 可用。
- [ ] 生成 `dg0-debug-source-ready.json`。
- [ ] 记录首次允许启动长时自动化的时间。

# Phase 1：候选、schema 和编排器基础

## DP10：定义 CandidateManifestV1

**Owner:** A/Gate。  
**Writes:** `schemas/`、`scripts/debug_program/`、`tests/debug_program/`。

- [ ] 定义 candidate ID、source commit、dirty、lock、contract、runtime、feature flags 和 installer。
- [ ] 所有文件引用使用受控根下相对路径、size 和 SHA-256。
- [ ] 校验 commit 为 40 位、hash 为 64 位、时间为 RFC3339。
- [ ] 对缺 installer、路径越界、坏 hash、dirty source 和 flag 漂移失败关闭。
- [ ] 增加 golden、非法、跨候选和篡改 fixture。

**测试：** schema 单元测试、路径安全、hash mismatch、候选不可变性。

## DP11：定义 Scenario、Run、Defect 和 Signoff schema

- [ ] 定义场景前置、fixture、步骤、机器断言、人工断言、资源和清理。
- [ ] 定义主机、工具版本、首次结果、重跑、artifact 和残留进程。
- [ ] 定义 defect 严重度、owner、复现、修复 commit、关闭 candidate。
- [ ] 定义产品/工程/安全/Windows/AV 签署身份和 hash 绑定。
- [ ] 保证 `not_applicable` 必须提供 feature flag 和依据。

**完成标准：** Python schema validator 和 TypeScript mirror 使用同一 golden fixtures。

## DP12：实现 append-only evidence writer

**Owner:** A/Gate。

- [ ] 使用 create-new 语义创建 run/scenario 结果。
- [ ] 重跑生成新 attempt，不覆盖第一次失败。
- [ ] 对日志、截图、probe、资源样本和人工复核计算 hash。
- [ ] 原子生成 evidence manifest 和 verdict。
- [ ] 进程中断后能够扫描未完成 run 并标记 `interrupted`。

**故障测试：** 写入中断、重复 run ID、磁盘不足、文件锁、manifest 部分写入。

## DP13：实现环境隔离器

- [ ] 为 run 分配 workspace、SQLite、cache、ports、browser profile 和 Office profile。
- [ ] 校验所有路径位于 candidate artifact root。
- [ ] 端口占用时选择新端口并记录，不杀未知进程。
- [ ] 清理前解析并验证 manifest 白名单。
- [ ] 运行结束检查子进程、句柄、端口和临时目录。

**完成标准：** 两个并行 smoke run 不共享状态，失败 run 不影响另一 run。

## DP14：实现场景注册表和 CLI

建议命令：

```powershell
python -m scripts.debug_program validate-candidate --candidate <path>
python -m scripts.debug_program list-scenarios --matrix pr-full
python -m scripts.debug_program run --candidate <path> --matrix local-e2e
python -m scripts.debug_program verdict --run <path>
```

- [ ] 支持按 matrix、risk、platform、feature flag 和 owner 过滤。
- [ ] 默认不执行 destructive、paid 或 manual 场景。
- [ ] destructive/paid 场景缺授权时返回 `blocked_external_authorization`。
- [ ] 输出机器可读 JSON 和简短终端摘要。

## Gate DG0.5：HARNESS_READY

- [ ] DP10-DP14 测试全绿。
- [ ] 证据写入中断可恢复且不会覆盖。
- [ ] 无授权的付费/卸载场景不会执行。
- [ ] 生成 `dg0-5-harness-ready.json`。

# Phase 2：干净候选与全量自动化

## DP20：从 clean integration commit 生成 Candidate 0

**Owner:** Integration/B release。

- [ ] 验证 source dirty=false。
- [ ] 记录 pnpm/uv lock hashes、schema/OpenAPI hashes 和 runtime fingerprint。
- [ ] 运行 API/Web/Remotion production build。
- [ ] 生成 release payload 和 installer；不复用历史 EXE。
- [ ] 生成 SBOM、许可证清单和 release artifact manifest。
- [ ] 对安装包、Node、FFmpeg、ffprobe、Remotion 和 launcher 做身份探针。

**完成标准：** Candidate 0 可由同 commit 和锁文件重新构建；两个构建的源码身份一致，非确定性字段有明确说明。

## DP21：Python 全量首轮门禁

- [ ] 在全新 run workspace 执行 `python -m pytest -q`。
- [ ] 执行 Ruff 和 mypy。
- [ ] 单独保存 contract、migration、job、recovery、release 和 security 分类摘要。
- [ ] 记录所有 skip/xfail 及其 feature/platform 依据。
- [ ] 首轮失败完整保留，不只重跑失败项。

**完成标准：** 首轮全绿；无未解释 skip/xfail；pytest cache warning 不影响结论但须记录。

## DP22：Web/Remotion 全量首轮门禁

- [ ] `pnpm lint`。
- [ ] `pnpm typecheck`。
- [ ] `pnpm test`。
- [ ] `pnpm build`。
- [ ] 核对 Web、Remotion、workspace package 的测试文件和测试数。
- [ ] 禁止遗留 `.only`、无理由 `.skip` 和 snapshot 自动更新。

## DP23：契约、生成文件和迁移漂移

- [ ] Project Schema 与模型一致。
- [ ] OpenAPI 与应用路由一致。
- [ ] Python/TypeScript/golden fixture 一致。
- [ ] v1-v4 migration 重复运行一致。
- [ ] 生成客户端在 clean checkout 中无 diff。
- [ ] feature flags 和 error code 枚举无影子定义。

## DP24：跨平台 CI 接线

**Owner:** Integration Gate。  
**Writes:** `.github/workflows/ci.yml` 和独立脚本。

- [ ] Windows 与 Ubuntu 执行 PR-full。
- [ ] CI 显式运行 `pnpm e2e`，不能只运行 `pnpm check`。
- [ ] Windows release gate 读取 Candidate，不搜索最新安装包。
- [ ] 保存完整日志、test report、trace 和构建摘要。
- [ ] timeout/cancel/continue-on-error 不进入 passed。

## DP25：重复构建和重复全量执行

- [ ] 从相同 clean commit 建立第二个隔离 run。
- [ ] 重复 DP20-DP24。
- [ ] 比较 contract、runtime、测试矩阵和工件清单。
- [ ] 将允许的时间戳/压缩非确定性与不可接受漂移分开。
- [ ] 若代码修复，创建 Candidate 1 并从 DP20 重启。

## Gate DG1：AUTOMATION_GREEN

- [ ] Python/Web/Remotion/contract/migration/build 两次首轮全绿。
- [ ] Windows/Ubuntu CI 通过。
- [ ] 无未解释 skip、only、重试或生成 diff。
- [ ] Candidate manifest 与工件 hash 可验证。
- [ ] 生成 `dg1-automation-green.json`。

# Phase 3：Playwright 本地真实 E2E

## DP30：整理 Playwright 场景清单

**Owner:** A。

- [x] 项目生命周期。
- [x] 本地音频完整链。
- [x] Presenter fake/local boundary。
- [x] HeyGen fake boundary 和真实场景的授权分离。
- [x] 刷新恢复、任务中心、预览、预检和最终导出。
- [x] 对现有三个 real E2E skip 建立明确去向，不留下无期限注释占位。

## DP31：建立 S1 与 S8 fixture

- [x] S1：2 页快速 smoke。
- [x] S8：8 页 PPTX+DOCX、本地 WAV、字幕、效果和制作包。
- [x] 固定来源、授权、页数、时长、hash 和预期输出。
- [x] 使用合成或已授权内容，不把私人材料提交仓库。
- [x] 建立 fixture validator。

## DP32：实现本地音频 E2E

- [x] Web 创建项目并上传材料。
- [x] 解析、匹配、旁白确认、本地 WAV、分页、字幕和预检。
- [x] authoritative preview 从 0 播放至 ended。
- [x] 创建异步渲染任务、刷新页面并恢复 job ID。
- [x] 验证 MP4、SRT、制作包和 manifest。

**注意：** 不复制当前 Windows 窗口的 4 页临时验收；等待其停点后使用正式 S8 候选重新执行。

## DP33：刷新、多标签页和重复操作

- [x] 渲染期间刷新和关闭重开。
- [x] 双标签页编辑冲突和 CAS 提示。
- [x] 连续点击创建任务只产生一个活动任务。
- [x] pause/resume/cancel/retry 的 UI 与服务状态一致。
- [ ] 网络短断和 API 重启后状态可恢复。

## DP34：Playwright 失败证据

- [x] 保存 trace、screenshot、video、console 和 network errors。
- [x] 失败页面标记 candidate/run/scenario。
- [x] 浏览器 profile 与其他 run 隔离。
- [x] 测试后无 Vite/API/browser 残留。
- [x] CI 与本地使用相同场景定义。

## Gate DG2：LOCAL_E2E_GREEN

- [x] S1/S8 项目生命周期和本地音频 E2E 首轮通过。
- [x] refresh/multi-tab/duplicate action 通过。
- [x] Playwright 纳入 CI，失败证据完整。
- [x] 无未解释 real-flow skip。
- [x] 生成 `dg2-local-e2e-green.json`。

# Phase 4：性能、压力和长稳

## DP40：建立资源采样器

**Owner:** B。

- [x] 采集 launcher/API/Worker/Node/FFmpeg/Office 进程树。
- [x] 每 1-5 秒记录 RSS、CPU、句柄、线程、GPU、磁盘读写和临时空间。
- [x] 记录阶段事件，能够把峰值映射到导入、预览、页面渲染和合成。
- [x] 进程 PID 重用或子进程变化时保持关联。
- [x] 输出 JSONL 和阶段摘要。

## DP41：冻结性能预算 schema

- [x] 定义主机 profile、fixture、冷/热缓存和并发度。
- [x] 定义启动、导入、预检、预览、渲染、合成和制作包指标。
- [x] 定义 OOM、磁盘、孤儿进程和回退阈值。
- [x] 首个 clean candidate 只生成 baseline，不用旧恢复结果代替。
- [ ] 工程负责人审核后冻结 `performance-budget-v1.json`。

## DP42：执行 S8 冷/热缓存

- [x] 清晰区分空缓存和热缓存，不手动删除未知目录。
- [x] 冷缓存完整执行一次。
- [x] 相同输入热缓存执行一次。
- [x] 修改一页、一个音频或一个 preset 后执行选择性失效。
- [x] 比较耗时、命中节点、graph hash 和工件一致性。

## DP43：执行 S50 大项目

- [ ] 50 页多媒体项目从导入到最终制作包。
- [ ] 记录峰值内存、磁盘、CPU/GPU 和总耗时。
- [ ] 检查日志、checkpoint、页缓存和临时文件数量。
- [ ] 中途暂停并恢复一次，确认峰值与重复工作。
- [ ] 验证最终 MP4、SRT、manifest 和制作包。

## DP44：执行画幅和导出压力

- [ ] 16:9、9:16、1:1。
- [ ] 已支持的 24/25/30/60fps 组合。
- [ ] 720p/1080p；4K 仅在 feature 和硬件能力允许时执行。
- [ ] 字幕软/烧录、Overlay、转场和音频混合。
- [ ] 不支持的组合必须在入队前明确阻断。

## DP45：2 小时与 8 小时长稳

- [ ] 2 小时标准 soak：反复预览、渲染、取消和重试。
- [ ] 8 小时夜间 soak：S50/批量或等价负载。
- [ ] 记录 RSS 稳定区增长、句柄、端口、临时文件和队列。
- [ ] 检查日志轮转和磁盘预算。
- [ ] 运行结束无孤儿进程和未发布临时结果。

## Gate DG3：PERFORMANCE_ACCEPTED

- [ ] S8/S50 有完整峰值和阶段指标。
- [ ] 冷/热缓存和选择性失效正确。
- [ ] 2 小时长稳通过；8 小时结果完成或有正式执行记录。
- [ ] 无 OOM、磁盘失控、孤儿进程和未解释 >20% 回退。
- [ ] 生成 `dg3-performance-accepted.json`。

# Phase 5：视觉、音频、字幕和质量引擎

## DP50：建立质量真值 corpus

**Owner:** B/AV reviewer。

- [ ] 正常成片集合。
- [ ] 黑帧、冻结、缺帧、坏编码和时长错误集合。
- [ ] 静音、削波、响度异常、截断和音画漂移集合。
- [ ] 字幕越界、遮挡、过密、字体缺失和时间错误集合。
- [ ] Presenter/Overlay/Effects 碰撞集合。
- [ ] 每个样本有授权、hash、ground truth 和严重度。

## DP51：升级自动视觉回归

- [ ] 从“manifest 数量检查”升级为实际帧比较。
- [ ] 支持像素 diff、感知 hash/SSIM 类指标和动态遮罩。
- [ ] 比较首帧、主帧、尾帧、字幕密集帧和章节边界。
- [ ] 固定 runtime/font/GPU profile，平台差异单独建立 baseline。
- [ ] threshold 变化需要版本和审核。

## DP52：实现音频与音画探针

- [ ] 流、采样率、声道、响度和削波。
- [ ] 首尾静音、语音截断和页面边界。
- [ ] 音画同步与漂移采样。
- [ ] VFR/CFR 输入的输出时间基一致。
- [ ] 失败给出页面、时间戳和稳定错误码。

## DP53：校准质量引擎

- [ ] 在坏样本上统计 P0/P1 召回。
- [ ] 在正常样本上统计误报。
- [ ] QualityJob 绑定 graph、policy 和 candidate MP4 hash。
- [ ] 自动处置最多一次，后续转人工。
- [ ] 误报豁免带 reviewer、原因、时间和 policy version。

## DP54：字幕与安全区矩阵

- [ ] 中文、英文、双语、长句、短句和术语。
- [ ] 16:9、9:16、1:1。
- [ ] 字体存在/缺失、描边、背景和逐词高亮。
- [ ] Presenter、Overlay、图表和底部 UI 安全区。
- [ ] 软字幕、烧录字幕和制作包输出一致。

## DP55：人工视听复核

- [ ] 片头、片尾、章节边界和随机正文页。
- [ ] 最密字幕、最复杂 PPT、最长转场和最高风险效果。
- [ ] 本地音频、Presenter 和 Effects 适用路线。
- [ ] 记录 reviewer、时间、candidate、artifact hash 和缺陷。
- [ ] 不使用“伪人工签署”或没有具名复核人的报告。

## Gate DG4：MEDIA_QUALITY_ACCEPTED

- [ ] 质量 corpus、自动视觉、音频和字幕矩阵通过。
- [ ] P0/P1 召回目标和正常样本误报目标满足批准预算。
- [ ] 人工复核 P0/P1 为 0。
- [ ] 所有报告绑定同一 candidate/graph/artifact。
- [ ] 生成 `dg4-media-quality-accepted.json`。

# Phase 6：故障注入、恢复和原子发布

## DP60：定义故障注入安全边界

**Owner:** A/B/Gate。

- [ ] 只终止 run manifest 中拥有的进程。
- [ ] 只锁定或限额 run root 中的文件系统。
- [ ] 不操作用户真实项目、系统盘根目录或未知服务。
- [ ] 每个 destructive fault 需要明确批准和回滚。
- [ ] 建立 dry-run，先打印目标和预期状态。

## DP61：launcher/API/Worker 中断矩阵

- [ ] 启动前、健康检查中、浏览器打开后终止 launcher。
- [ ] 导入、解析、预检和入队时终止 API。
- [ ] claim、页面渲染、合成和发布前终止 Worker。
- [ ] 重启后任务状态、checkpoint、attempt 和 UI 恢复正确。
- [ ] 不重复创建活动任务或覆盖成功结果。

## DP62：FFmpeg/Office 外部进程矩阵

- [ ] Remotion 页面渲染中断。
- [ ] FFmpeg 合成中断。
- [ ] Office/LibreOffice 转换超时、崩溃和 profile 锁。
- [ ] 子进程取消、超时和退出码映射正确。
- [ ] 临时文件清理只作用于声明路径。

## DP63：存储与权限故障

- [ ] 入队前磁盘不足。
- [ ] 页面渲染后、发布前磁盘不足。
- [ ] 输出文件被占用。
- [ ] 目录只读、临时目录缺失和长路径。
- [ ] cache、manifest、checkpoint 和 WAL 损坏。

## DP64：输入变化和 stale publication

- [ ] 排队期间修改项目 revision。
- [ ] 渲染期间替换素材或音频。
- [ ] 发布前修改 graph/preset/runtime fingerprint。
- [ ] 旧 attempt、旧 generation 和旧 publication reservation 被拒绝。
- [ ] 新任务可以复用仍有效页缓存，但不能发布旧输入结果。

## DP65：网络与远端未知状态

- [ ] DNS/连接失败、超时、429、5xx。
- [ ] 请求已发送但客户端未收到响应。
- [ ] 重启后先查询远端 request ID。
- [ ] 状态未知进入 `needs_confirmation`。
- [ ] 未确认前不得重试付费请求。

## Gate DG5：RECOVERY_ACCEPTED

- [ ] 所有故障产生稳定状态和错误码。
- [ ] 重启后可诊断、可继续或可安全重试。
- [ ] 上一成功项目、MP4 和制作包 hash 不变。
- [ ] 无重复计费、重复发布和越界清理。
- [ ] 生成 `dg5-recovery-accepted.json`。

# Phase 7：Job、缓存、并发、兼容和迁移

## DP70：Job 并发与 CAS

**Owner:** A/B。

- [ ] 同项目重复创建。
- [ ] 多标签页 stale revision。
- [ ] 多项目排队、优先级和取消。
- [ ] claim 竞争、lease 过期和 worker 重启。
- [ ] stale attempt/generation publication。
- [ ] exactly-once publication 和历史 attempt 可审计。

## DP71：缓存失效矩阵

- [ ] 页面文字、旁白、音频、字幕、效果和 preset 单独变化。
- [ ] runtime、font、FFmpeg、Remotion 和平台能力变化。
- [ ] 只失效依赖节点，不扩大为全项目无条件重算。
- [ ] 缓存命中同时验证输入 hash，不信任文件名/mtime。
- [ ] 损坏 entry 保守 miss 并重建。

## DP72：GC 与活动任务并发

- [ ] GC 与 preview 读取并发。
- [ ] GC 与页面渲染写入并发。
- [ ] lease/pin 保护活动节点。
- [ ] 取消任务释放可回收项但保留共享有效缓存。
- [ ] persistent repository 重启后索引一致。

## DP73：历史项目 corpus

**Owner:** A。

- [ ] 收集经授权的 v1-v4 项目副本。
- [ ] 包含中文路径、缺素材、旧 job 状态和旧制作包。
- [ ] 记录来源 hash 和敏感级别。
- [ ] 原项目只读，所有迁移在 run copy 执行。
- [ ] fixture manifest 不泄露私人内容。

## DP74：迁移与回滚矩阵

- [ ] v1→当前、v2→当前、v3→当前、当前重复迁移。
- [ ] migration 中断后重入。
- [ ] duplicate active job reconciliation。
- [ ] 损坏 media/manifest/DB 时阻断写入。
- [ ] feature flag 关闭和旧 reader fallback。
- [ ] baseline→candidate→baseline，不执行降级 SQL。

## DP75：Office 与素材兼容

- [ ] PowerPoint/LibreOffice 支持版本。
- [ ] 图表、SmartArt、嵌入字体、动画、音视频和透明对象。
- [ ] PDF、扫描 PDF、DOCX、图片、损坏和加密输入。
- [ ] 中文、空格、长路径、可移动磁盘和受控网络路径。
- [ ] 常见音视频 codec、采样率、VFR/CFR 和旋转元数据。

## Gate DG6：DATA_SAFETY_ACCEPTED

- [ ] Job/CAS/lease/publication 并发通过。
- [ ] cache 失效和 GC 不误删活动数据。
- [ ] 历史项目迁移、重入、回滚和损坏阻断通过。
- [ ] Office/素材支持矩阵和限制文档完成。
- [ ] 生成 `dg6-data-safety-accepted.json`。

# Phase 8：Presenter、HeyGen 与真实 Provider

## DP80：冻结外部授权和预算

**Owner:** C/Product。

- [ ] 列出需要的 Provider、账号、环境和数据范围。
- [ ] 每个真实场景设置调用次数和费用上限。
- [ ] 明确凭证由 secret store 注入，不进入日志或 fixture。
- [ ] 明确测试数据可发送范围。
- [ ] 未授权项目保持 disabled 并测试关闭路径。

## DP81：Presenter 短样本

- [ ] 5-8 分钟真实或经授权 Presenter 视频。
- [ ] probe、ASR、分页锚点、人工修正和锁定。
- [ ] 字幕、Overlay、Effects 碰撞和安全区。
- [ ] 刷新、重启、恢复和制作包。
- [ ] 音画同步与人工复核。

## DP82：Presenter 长样本与降级

- [ ] 15-20 分钟样本。
- [ ] 资源峰值、ASR 耗时和长稳。
- [ ] 低置信度、缺模型、坏视频和中断恢复。
- [ ] Presenter disabled 时 AI narration 路线无回归。
- [ ] 明确 stable_optional/internal/disabled 结论。

## DP83：HeyGen 两页受控实测

- [ ] 使用明确预算和两个页面。
- [ ] 保存远端 request ID 和幂等键。
- [ ] 成功页缓存，失败页独立重试。
- [ ] 429/5xx/超时/未知状态不重复计费。
- [ ] 制作包和审计日志不泄露凭证。

## DP84：LLM/ASR/TTS Provider 合同

- [ ] fake 与 real adapter 使用同一 request/result schema。
- [ ] invalid credential、rate limit、timeout 和 partial response。
- [ ] 预算、并发、failover 和 circuit breaker。
- [ ] Provider 关闭时不创建 client、不发送网络请求。
- [ ] 日志、诊断和 UI 错误明确。

## Gate DG7：OPTIONAL_FEATURES_DECIDED

- [ ] Presenter/HeyGen/Provider 每项为 passed、disabled 或 blocked_external_authorization。
- [ ] passed 项有真实 candidate 证据。
- [ ] disabled 项关闭路径通过且不产生网络/费用。
- [ ] 没有“代码存在即生产可用”的状态。
- [ ] 生成 `dg7-optional-features-decided.json`。

# Phase 9：安全、隐私、供应链、UI 与诊断

## DP90：文件与解析器安全

**Owner:** Security/A/B。

- [ ] 路径穿越、绝对路径、重解析点和目录逃逸。
- [ ] 恶意 OOXML、压缩炸弹、畸形 PDF/图片/媒体。
- [ ] 超大文件和解压/解析资源上限。
- [ ] 非受控路径不进入运行时或制作包。
- [ ] 解析失败不损坏项目。

## DP91：本地 API 与桌面边界

- [ ] 仅监听 loopback。
- [ ] CORS/来源和浏览器启动边界。
- [ ] 端口发现、已有实例、二次点击和 stale instance file。
- [ ] 非预期本地来源不能执行高风险操作。
- [ ] launcher/API 退出后不留公开监听端口。

## DP92：密钥与隐私

- [ ] secret store、凭证轮换和撤销。
- [ ] 日志、诊断包、截图、制作包和 Provider payload 脱敏。
- [ ] Git tracked 文件和 release payload secret scan。
- [ ] 用户项目、workspace-data 和私人 fixture 不进入源码包。
- [ ] 敏感证据访问和保留策略。

## DP93：供应链和更新

- [ ] 锁文件、SBOM、许可证和运行时来源。
- [ ] installer/runtime/artifact hashes。
- [ ] 坏签名、截断、重放、降级和过期 metadata。
- [ ] 更新失败、健康检查失败和自动回滚。
- [ ] baseline/candidate/previous 指针和项目数据安全。

**边界：** Windows 当前专项已覆盖的安装/回滚场景只消费其停点，不重复并行执行；本任务补安全攻击矩阵和最终同候选复核。

## DP94：UI 竞态和可访问性

**Owner:** A。

- [ ] refresh、多标签页、连续点击、前后台和断网。
- [ ] 100/125/150/200% DPI 与浏览器缩放。
- [ ] 键盘、焦点、状态播报和禁用原因。
- [ ] 大列表、长路径、中文、长错误和日志分页。
- [ ] 任务失败后的恢复入口可见且不会误导。

## DP95：诊断和错误码

- [ ] candidate/run/project/job/attempt/checkpoint/artifact 关联。
- [ ] 稳定错误码与用户行动建议。
- [ ] 一键诊断包包含必要日志、版本和探针。
- [ ] 诊断包通过 secret/path/user-data redaction。
- [ ] P0/P1 能由诊断包复现或定位到最小场景。

## Gate DG7.5：SECURITY_AND_UX_ACCEPTED

- [ ] 文件、API、密钥、供应链攻击矩阵通过。
- [ ] 更新/回滚安全证据绑定当前 candidate。
- [ ] UI 竞态、DPI、键盘和错误恢复通过。
- [ ] 诊断包脱敏和关联链通过。
- [ ] 生成 `dg7-5-security-ux-accepted.json`。

# Phase 10：唯一 RC、完整回归、缺陷关闭与签署

## DP100：汇总缺陷并决定新候选

- [ ] 汇总 DG1-DG7.5 的全部首次失败和重跑。
- [ ] P0/P1 全部退回来源线修复。
- [ ] P2/P3 分配 owner、规避和计划版本。
- [ ] 任一源码/锁/runtime/flag/installer 变化创建新 candidate。
- [ ] 生成 candidate lineage，不覆盖旧候选。

## DP101：构建唯一最终 RC

**Owner:** Integration/B release。

- [ ] 从 clean integration commit 构建。
- [ ] 生成 installer、release payload、runtime manifest、SBOM 和 licenses。
- [ ] 验证 Node、FFmpeg、ffprobe、Remotion、launcher 和 API。
- [ ] 生成 candidate/evidence manifests。
- [ ] 冻结后不再原地修改。

## DP102：完整自动化与样本回归

- [ ] DG1 全量自动化。
- [ ] DG2 Playwright S1/S8。
- [ ] DG3 S50 与性能关键预算。
- [ ] DG4 质量 corpus 和视觉音画。
- [ ] DG5 故障关键矩阵。
- [ ] DG6 并发、缓存、迁移和兼容。
- [ ] DG7 optional features 的最终启用/关闭矩阵。
- [ ] DG7.5 安全/UI/诊断。

所有结果必须来自最终 RC，不得混用 Candidate 0 的通过证据。

## DP103：消费 Windows A0-A9 并补最终同候选运行

- [ ] Windows 报告 candidate ID 与最终 RC 一致。
- [ ] 安装、启动、旧项目、中断恢复、预检、播放、导出、卸载重装、回滚完整。
- [ ] 修复后没有复用旧失败候选的截图或 hash。
- [ ] 进程、端口、安装目录和 workspace 清理/保留符合清单。
- [ ] 报告 schema、evidence manifest 和 artifact hash 全部验证。

## DP104：最终人工视听与产品验收

- [ ] S8、S50、竖屏/方屏适用样本。
- [ ] Presenter、Effects、HeyGen 仅检查最终启用项。
- [ ] 成片、字幕、旁白、音画和制作包复核。
- [ ] P0/P1=0；P2/P3 与已知限制一致。
- [ ] 具名 reviewer、时间和 candidate/hash。

## DP105：签署与冻结

- [ ] 产品签署范围和已知限制。
- [ ] 工程签署 clean source、自动化、性能和恢复。
- [ ] 安全签署隐私、供应链和攻击矩阵。
- [ ] Windows 操作员签署 A0-A9。
- [ ] AV reviewer 签署视听。
- [ ] `freeze-release.ps1` 拒绝旧、缺失、跨候选和被篡改报告。

## DP106：文档与发布准备

- [ ] 用户指南、排障、迁移、备份、卸载和回滚说明。
- [ ] 系统要求、支持的 Office/媒体矩阵和已知限制。
- [ ] feature flags 和 optional/disabled 状态。
- [ ] release notes、candidate ID、commit 和 artifact hashes。
- [ ] 维护者 safe resume、缺陷 backlog 和下个版本入口。

## Gate DG8：V1_DEBUG_ACCEPTED

- [ ] DG0-DG7.5 全部通过或按设计保持 disabled。
- [ ] 最终 RC 来自 clean commit，所有 hash 一致。
- [ ] 最终 RC 全量回归首轮通过，无未解释 skip。
- [ ] S8/S50、性能、视觉音画、恢复、并发、迁移和安全证据完整。
- [ ] Windows A0-A9 和人工视听绑定同一 candidate。
- [ ] P0=0、P1=0；P2/P3 已签署。
- [ ] 产品、工程、安全、Windows 和 AV 签署完成。
- [ ] 生成 `dg8-v1-debug-accepted.json` 和最终 `evidence-manifest.json`。

## 6. 标准验证命令

以下命令在对应 clean worktree 中执行；不得默认在恢复根目录运行：

```powershell
# Python
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check --no-cache apps tests scripts
.venv\Scripts\python.exe -m mypy apps/api/src

# Repository / Web / Remotion
pnpm.cmd lint
pnpm.cmd typecheck
pnpm.cmd test
pnpm.cmd build
pnpm.cmd e2e

# Candidate harness（实现 DP14 后）
.venv\Scripts\python.exe -m scripts.debug_program validate-candidate --candidate <candidate.json>
.venv\Scripts\python.exe -m scripts.debug_program run --candidate <candidate.json> --matrix pr-full
.venv\Scripts\python.exe -m scripts.debug_program verdict --run <run-dir>
```

每条长命令保存开始时间、结束时间、退出码、日志 hash 和残留进程检查。命令超时后先确认子进程是否仍在运行，不得重复启动同一构建或渲染造成并发污染。

## 7. 推荐实施节奏

| 阶段                     | 串行工程量 | 可并行部分                   | 预计日历 |
| ------------------------ | ---------: | ---------------------------- | -------: |
| Phase 0-1 来源与 harness |     2-3 周 | schema、fixture 草案         |   2-3 周 |
| Phase 2 自动化与 CI      |     2-4 周 | Python/Web/Remotion 分类修复 |   2-4 周 |
| Phase 3 Playwright       |     2-3 周 | fixture 与场景并行           |   2-3 周 |
| Phase 4 性能压力         |     2-4 周 | S8/S50/长稳分机器            |   2-4 周 |
| Phase 5 质量视听         |     3-5 周 | corpus、视觉、音频、字幕     |   3-5 周 |
| Phase 6-7 恢复与数据安全 |     3-5 周 | fault/cache/migration 矩阵   |   3-5 周 |
| Phase 8 真实服务         |     1-3 周 | Presenter 与 Provider        |   1-3 周 |
| Phase 9-10 安全与最终 RC |     3-5 周 | 安全、UI、文档               |   3-5 周 |

三线资源稳定且 Gate 修复不超过两轮时，整体约 10-16 周；单线串行或重大 P0/P1 较多时更长。时间估计不替代 Gate，不能因期限到达而降低门禁。

## 8. Stop point 模板

每个阶段结束生成：

```json
{
  "schema_version": "1.0",
  "task_id": "DPxx",
  "candidate_id": "...",
  "source_commit": "...",
  "branch": "...",
  "owned_paths": [],
  "shared_paths": [],
  "completed": [],
  "remaining": [],
  "verification": [],
  "evidence": [],
  "defects": [],
  "rollback": "...",
  "safe_resume": "...",
  "will_write_again": false
}
```

Stop point 必须能让下一窗口在不依赖聊天历史的情况下恢复任务。

## 9. 最终检查清单

- [ ] 现有 Windows、Effects、RenderGraph 和 W0 工作没有重复开发。
- [ ] 调试 Program 从 clean foundation 启动。
- [ ] Candidate/Scenario/Run/Defect/Signoff schema 已版本化。
- [ ] CI 显式运行 Playwright。
- [ ] S8/S50、竖屏/方屏和真实媒体证据固定。
- [ ] 性能测试记录峰值和长稳，不只检查 manifest。
- [ ] 视觉回归比较实际帧，不只检查样本数量。
- [ ] 故障注入证明恢复和上一成功结果安全。
- [ ] Job/cache/GC/迁移/回滚通过并发和损坏矩阵。
- [ ] Presenter/Provider 有真实证据或保持 disabled。
- [ ] 安全、隐私、SBOM、许可证和诊断脱敏通过。
- [ ] 最终唯一 RC 全量回归、Windows A0-A9 和人工视听一致。
- [ ] P0/P1 为 0，所有签署绑定同一 candidate。
- [ ] 发布冻结器能拒绝旧、缺失、跨候选和被篡改证据。
