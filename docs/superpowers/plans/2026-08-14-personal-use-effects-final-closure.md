# PPT Video Workbench 本地个人可用与 Effects V2 最终收口逐项实施计划

> 日期：2026-08-14
>
> 状态：待实施
>
> 设计依据：[2026-08-14-personal-use-effects-final-closure-design.md](../specs/2026-08-14-personal-use-effects-final-closure-design.md)
>
> 执行规则：G00-G10 严格串行；一个 Gate 通过后直接进入下一项，不逐项等待确认；失败时只修复当前最早受影响阶段并按失效矩阵重跑

## 1. 总体执行规则

- [ ] 只在 `F:\ppt-video-workbench-v3\.worktrees\program-integration-v1` 开发和构建。
- [ ] 每个阶段开始前记录 branch、HEAD、dirty 状态、依赖锁和工具版本。
- [ ] 每个阶段使用新的 `run_id`，不覆盖失败或中断证据。
- [ ] 候选冻结后不原地修改；任何代码/依赖/策略变化都创建新 commit 和 candidate。
- [ ] 每个运行隔离 workspace、DB、cache、TEMP、output、logs、ports 和 process registry。
- [ ] 真实 PPT 只使用副本，并校验原件前后 SHA-256 不变。
- [ ] 只终止当前 run 登记且 PID 创建时间匹配的进程。
- [ ] 不执行 `git reset --hard`、`git clean`、目录覆盖或跨 worktree 批量修改。
- [ ] 不使用旧安装包、其他 worktree 产物、静态帧或中间循环替代当前 Gate。
- [ ] P0/P1 立即阻断；P2 必须有 owner、规避方案和具名接受记录。
- [ ] 阶段完成生成 JSON result、Markdown 摘要、evidence manifest 和 SHA-256。
- [ ] G10 后再次盘点全部未完成项；发现漏项时回到最早受影响 Gate，解决后继续向后重跑。

## 2. 阶段总览

| 顺序 | 阶段                   | Gate                                            |
| ---: | ---------------------- | ----------------------------------------------- |
|  G00 | 当前基线与边界         | `BASELINE_CONFIRMED=PASS`                       |
|  G01 | 必需集成与源码候选冻结 | `SOURCE_CANDIDATE_FROZEN=PASS`                  |
|  G02 | 本地全量与 CI          | `CI_GREEN=PASS`                                 |
|  G03 | 唯一 Windows 候选      | `FINAL_CANDIDATE_BUILT=PASS`                    |
|  G04 | DP45 长稳              | `DP45_READY=PASS`                               |
|  G05 | 安装与启动             | `INSTALLED_READY=PASS`                          |
|  G06 | 真实 PPT 本地全链      | `LOCAL_FLOW_READY=PASS`、`UI_EXPORT_READY=PASS` |
|  G07 | Effects V2 动态专项    | `EFFECTS_READY=PASS`                            |
|  G08 | 中断恢复、重装与回滚   | `RECOVERY_READY=PASS`                           |
|  G09 | 质量与人工视听         | `QUALITY_READY=PASS`                            |
|  G10 | 最终总审计             | `PERSONAL_USE_READY=PASS`                       |

## 3. G00：当前基线与边界

### G00.1 工作树确认

- [ ] 执行 `git status --short --branch`，确认目标分支和 clean 状态。
- [ ] 记录当前 40 位 HEAD、上游、ahead/behind 和最后 10 个提交。
- [ ] 执行 `git worktree list --porcelain`，只把 `program-integration-v1` 作为产品源。
- [ ] 记录根目录恢复快照和其他 worktree，仅作为来源/历史证据，不做构建。
- [ ] 检查 editable install、环境变量和 Node/Python 模块没有指向其他 worktree。

### G00.2 证据分级

- [ ] 将 `DEV_LOCAL_E2E_PASS` 标记为开发态能力证据。
- [ ] 将旧 `90a4fa31...` candidate 和其 DP45 证据标记为 stale/historical。
- [ ] 将 30 页/90 帧 Effects 结果标记为静态/合同证据。
- [ ] 将旧 Windows 安装包和 Task 26 结果标记为历史候选证据。
- [ ] 明确缺失项：当前候选、完整 DP45、安装版真实 PPT、动态 Effects、恢复、最终 MP4、人工视听。

### G00.3 输出

- [ ] 新增 `test-results/personal-use/<candidate-id>/baseline/baseline.json`。
- [ ] 写入 `BASELINE_CONFIRMED=PASS`。
- [ ] 若工作树脏或产品源不唯一，停止并先清晰收口来源。

## 4. G01：必需集成与源码候选冻结

### G01.1 只集成个人可用必需项

- [ ] 逐提交审查当前分支尚未推送的 43 个提交，确认没有缺失依赖和半完成提交。
- [ ] 核对 `program-core-workbench`、`program-render-release`、`rendergraph-v2-closure`、Effects、字体审计和文档分支的 stop point。
- [ ] 仅选择性集成会阻断本地转视频、Effects V2、Windows 安装、恢复或质量的提交。
- [ ] 不整分支合并恢复快照、云端或 P2 平台实验。
- [ ] 记录每个选择/排除项、来源 commit、理由、验证和回退点。

### G01.2 补齐最终聚合与功能策略

- [ ] 新增 `schemas/personal-use-closure-v1.schema.json`。
- [ ] 新增 `scripts/personal_use_closure.py`，只根据显式报告路径和 SHA-256 聚合，不扫描“最新”。
- [ ] 新增候选级 `feature-policy.json` 生成与验证逻辑。
- [ ] 在 runtime manifest 和 `release-artifacts.json` 中登记 feature policy hash。
- [ ] 为 `scripts/build-release.ps1` 增加 `-CandidateId`，并透传给 `scripts/release_artifacts.py --candidate-id`；缺失或不一致时失败关闭。
- [ ] API 暴露只读候选/策略端点，Web 明确显示 V1/V2、降级和回退状态。
- [ ] 非法 Effects V2 开关组合失败关闭。
- [ ] 旧项目默认 V1；新项目 V2 默认值只由已验收候选策略决定。
- [ ] V2 回退不删除 EffectPlan、人工锁或用户设置。

### G01.3 契约和数据安全

- [ ] 重新生成 OpenAPI、Project Schema 和 Web client。
- [ ] 验证 migration monotonicity、重复迁移和旧项目只读打开。
- [ ] 验证 Job/attempt/checkpoint/publication 不跨项目或跨 candidate 混用。
- [ ] 验证 cache GC 不删除源文件、活动任务、上一成功 MP4 或制作包。
- [ ] 验证日志和诊断包脱敏。

### G01.4 源码冻结

- [ ] 运行全部受影响定向测试。
- [ ] `git diff --check` 通过。
- [ ] 工作树 clean。
- [ ] 记录锁文件和关键契约 SHA-256。
- [ ] 生成候选 ID：`rc-personal-<short-commit>-<UTC>`；该格式满足当前个人预检的 `rc-` 前缀合同。
- [ ] 执行：

```powershell
.venv\Scripts\python.exe scripts\build_program_rc_manifest.py `
  --repository-root . `
  --candidate-id <candidate-id> `
  --output test-results\personal-use\<candidate-id>\candidate\candidate-manifest.json
```

- [ ] 独立重读 manifest，确认 commit、dirty=false 和所有输入 hash。
- [ ] 写入 `SOURCE_CANDIDATE_FROZEN=PASS`。

## 5. G02：本地全量与 CI

### G02.1 Python

- [ ] `.venv\Scripts\python.exe -m ruff check apps tests scripts`。
- [ ] `.venv\Scripts\python.exe -m mypy apps/api/src`。
- [ ] `.venv\Scripts\python.exe -m pytest -q`，保存 collection 数、passed/failed/skipped、耗时和日志 hash。
- [ ] 单独执行 migration、rendering、effects、jobs、recovery、release 和 security 测试集。
- [ ] 超时只记录为 timeout，不记 pass；定位阻塞测试后重新从干净进程执行。

### G02.2 Web、Remotion 与 E2E

- [ ] `pnpm lint`。
- [ ] `pnpm typecheck`。
- [ ] `pnpm test`。
- [ ] `pnpm build`。
- [ ] 执行 Web E2E 的本地音频、项目生命周期、播放、取消重试和恢复场景。
- [ ] 执行 Remotion typecheck、tests、bundle 和真实 render smoke。
- [ ] 不用 retry 掩盖首轮失败；flaky 场景修复后至少连续三次首轮通过。

### G02.3 契约与发布门禁

- [ ] OpenAPI、Project Schema 和 client 再生成后 diff 为零。
- [ ] `schemas/personal-use-closure-v1.schema.json` golden/tampered/missing/stale/wrong-candidate fixture 全过。
- [ ] `schemas/windows-release-acceptance-v2.schema.json` 合同测试通过。
- [ ] installer/release 脚本合同、runtime manifest、SBOM、许可证和绝对路径扫描通过。

### G02.4 CI

- [ ] 从同一 clean commit 触发项目配置的 CI。
- [ ] 保存 workflow/run ID、commit、环境、每个 job 结论和日志/产物哈希。
- [ ] 所有 required job 通过；取消、跳过或无法访问不等于通过。
- [ ] CI 无法使用时标记 `BLOCKED_EXTERNAL_CI`，不得写 `CI_GREEN`。
- [ ] 写入 `CI_GREEN=PASS`。

## 6. G03：唯一 Windows 候选

### G03.1 构建

- [ ] 在 G01 的 clean commit 上构建，不修改源码。
- [ ] 显式检查 Python、Node、pnpm、FFmpeg/FFprobe、PyInstaller 和 Inno Setup。
- [ ] 工具不存在或不可访问时失败关闭，不产生伪候选。
- [ ] 使用隔离输出目录：

```powershell
.\scripts\build-release.ps1 `
  -CandidateId <candidate-id> `
  -Output "test-results\personal-use\<candidate-id>\build\release" `
  -InstallerOutputDirectory "test-results\personal-use\<candidate-id>\candidate" `
  -Verify
```

- [ ] 构建前后源码完整性 hash 一致。

### G03.2 候选校验

- [ ] `release-artifacts.json` 从清单定位 installer，不猜固定路径。
- [ ] `release-artifacts.json` 的 candidate ID 与 G01 预先生成的 ID 完全一致。
- [ ] installer、payload、runtime manifest、launcher、Web build 和 feature policy hash 全部登记。
- [ ] 候选 source commit 与 G01 完全一致。
- [ ] 安装包可被独立 verifier 读取；缺文件、大小变化或 hash 不符立即失败。
- [ ] 运行：

```powershell
.venv\Scripts\python.exe scripts\verify_candidate_evidence.py `
  --candidate test-results\personal-use\<candidate-id>\candidate\candidate-manifest.json `
  --evidence test-results\personal-use\<candidate-id>\candidate\release-artifacts.json
```

- [ ] 使用一份明确的 PPT 验收副本和隔离输出目录运行：

```powershell
.venv\Scripts\python.exe scripts\personal_use_preflight.py `
  --repository-root . `
  --candidate-id <candidate-id> `
  --input <approved-ppt-copy> `
  --output-root test-results\personal-use\<candidate-id>\runs\preflight\output `
  --output test-results\personal-use\<candidate-id>\runs\preflight\personal-use-preflight.json
```

- [ ] source/build/runtime/project 四门禁全部通过。
- [ ] 写入 `FINAL_CANDIDATE_BUILT=PASS`，候选目录改为只读保留策略。

## 7. G04：DP45 长稳

### G04.1 配置

- [ ] 新建 `test-results/personal-use/<candidate-id>/config/dp45.json`。
- [ ] 绑定 G03 candidate manifest、FFmpeg/FFprobe、持续时间、最小周期、50 页、恢复/取消频率和日志段大小。
- [ ] TEMP/TMP、workspace、DB、cache、output 和 logs 全部位于 F 盘隔离目录。
- [ ] 创建 process registry、端口表和磁盘预算。

### G04.2 执行

```powershell
.\scripts\run_dp45_soak.ps1 `
  -Config test-results\personal-use\<candidate-id>\config\dp45.json `
  -TempRoot test-results\personal-use\<candidate-id>\runs\dp45\temp
```

- [ ] 持续时间与最小周期必须同时满足。
- [ ] 覆盖 normal、recovery、cancel_retry、缓存复用和 publication 保留。
- [ ] 采样 CPU、RSS、句柄、线程、磁盘、临时文件、端口和进程树。
- [ ] 保留 ledger、性能 JSONL、cycle events 和失败现场。

### G04.3 结束门禁

- [ ] 存在正式 completion marker 和汇总报告。
- [ ] 所有循环终态明确，failure=0 或缺陷已修复并新建候选重跑。
- [ ] 无孤儿受管进程、端口泄漏、临时文件失控和上一成功 publication 损坏。
- [ ] RSS/性能预算满足或有关闭的专项缺陷。
- [ ] completion、candidate、config、ledger 和 report hash 一致。
- [ ] 写入 `DP45_READY=PASS`。
- [ ] 从 G01 起无源码/依赖变化，写入 `FINAL_SOURCE_READY=PASS` 和 `FINAL_CANDIDATE_READY=PASS`。

## 8. G05：Windows 安装与启动

### G05.1 隔离准备

- [ ] 选择独立 `InstallRoot`、`WorkspaceRoot` 和 `ReportDirectory`。
- [ ] 确认不指向正式安装、正式 workspace DB 或用户项目根。
- [ ] 记录安装前进程、端口、快捷方式和相关目录状态。

### G05.2 运行 schema 2.0 验收

```powershell
.\tests\release\windows-acceptance.ps1 `
  -ArtifactManifest test-results\personal-use\<candidate-id>\candidate\release-artifacts.json `
  -InstallRoot F:\PPTVideoWorkbench-Acceptance\<candidate-id>\app `
  -WorkspaceRoot F:\PPTVideoWorkbench-Acceptance\<candidate-id>\workspace `
  -ReportDirectory F:\PPTVideoWorkbench-Acceptance\<candidate-id>\report
```

- [ ] `artifact_resolution`：candidate 和 installer hash 一致。
- [ ] `clean_install`：标准用户安装成功，布局和快捷方式正确。
- [ ] `first_launch`：无黑窗，API/UI 在预算内健康。
- [ ] 关闭浏览器后再次点击快捷方式，可重新打开同一健康实例。
- [ ] 启动器、API、Web build 均显示同一 candidate ID。
- [ ] workspace、state、logs 与安装目录分离。
- [ ] 写入 `INSTALLED_READY=PASS`。

## 9. G06：真实 PPT 本地全链

### G06.1 输入保护

- [ ] 用户选择小型、标准、复杂三类真实 PPT；如尚未提供，以明确标注的内部授权样本副本执行，不冒充用户成片验收。
- [ ] 记录原件路径标识、大小、SHA-256；复制到隔离 WorkspaceRoot。
- [ ] 每个副本使用新 project ID，不复用正式数据库记录。
- [ ] 执行字体审计、素材存在性和兼容性预检。

### G06.2 UI 完整流程

- [ ] 安装版 UI 新建项目并导入 PPT/材料。
- [ ] 核对页面数、标题、图片/图表、字体和源文件引用。
- [ ] 创建或导入旁白文本。
- [ ] 使用本地音频完成页面音频；无音频模式做补充 smoke。
- [ ] 生成/导入字幕并人工修正至少一处。
- [ ] 应用 Effects V2 推荐，调整强度，锁定一页，对同类页批量应用。
- [ ] 执行 fresh 完整预检，0 blocking issue。
- [ ] 从 0 播放到 ended，记录 stall、console error、资源失败和起中末截图。
- [ ] 通过 UI 选择导出规格并提交最终渲染。
- [ ] 观察 queued/running/verifying/publishing/succeeded 全状态。
- [ ] 刷新 UI 和重启启动器后仍可找到 job、project 和 publication。

### G06.3 媒体与制作包

- [ ] ffprobe 验证容器、视频/音频 codec、分辨率、fps、像素格式和时长。
- [ ] 完整 decode-to-null，无损坏帧或致命错误。
- [ ] 最终视频时长与时间轴/音频在预算内一致。
- [ ] 制作包 manifest 中路径、大小、SHA-256 与实际一致。
- [ ] UI 规格与实际文件一致。
- [ ] `latest` 指向 stable publication，不指向 staging/temp。
- [ ] 记录 source/project/snapshot/graph/spec/job/attempt/artifact 身份链。
- [ ] 验证原 PPT hash 未变化。
- [ ] 写入 `LOCAL_FLOW_READY=PASS` 和 `UI_EXPORT_READY=PASS`。

### G06.4 HeyGen 边界

- [ ] 本地音频链路不依赖 HeyGen。
- [ ] 没有显式凭证、声音、费用和 canary 授权时记录 `HEYGEN_WAIT_EXTERNAL`。
- [ ] 不因 HeyGen 未运行阻断本地个人使用 Gate。

## 10. G07：Effects V2 动态专项

### G07.1 验收工具补齐

- [ ] 扩展 Windows runner，新增 `effects_dynamic_preview`、`effects_final_export` 和 `effects_fallback` 阶段。
- [ ] 新增 `scripts/effects_dynamic_acceptance.py` 或等价模块，消费显式 candidate、project、manifest 和 output root。
- [ ] 每页记录 EffectPlan hash、RenderGraph hash、template version、runtime、关键时间点和输出片段 hash。
- [ ] 工具测试覆盖 missing/tampered/stale/wrong-candidate、预览/导出 hash 漂移和缺帧。

### G07.2 30 页动态矩阵

- [ ] 重新校验 30 份获准样本和 Ground Truth hash。
- [ ] 十类页面各 3 页全部生成动态预览和最终片段。
- [ ] 覆盖 L0/L1/L2/L3 和四档强度。
- [ ] 覆盖 `ProgressiveReveal`、`StatCounter`、镜头、转场、强调和确定性降级。
- [ ] 覆盖人工锁、重新推荐、同类页批量应用和恢复自动。
- [ ] 覆盖字幕安全区、长字幕、空字幕、Presenter/Overlay 避让。
- [ ] 覆盖从头播放、seek、中段、页边界和结束帧。
- [ ] preview/render plan/graph/template/runtime hash 完全一致。
- [ ] 不允许页面的 L3 误启用数为 0。

### G07.3 Windows 实机入口

```powershell
.\scripts\windows_effect_acceptance.ps1 `
  -Root . `
  -InstallRoot F:\PPTVideoWorkbench-Acceptance\<candidate-id>\app `
  -WorkspaceRoot F:\PPTVideoWorkbench-Acceptance\<candidate-id>\effects-workspace `
  -ProductionDatabasePath F:\Video\workspace.db `
  -RunTests
```

- [ ] 正式数据库阻断测试通过。
- [ ] 动态阶段必须从安装版候选执行；源码单元测试只能作为补充。
- [ ] 30/30 页面动态预览成功，30/30 最终片段成功。
- [ ] 关闭 V2 后同一项目副本通过 V1 预览与导出。

### G07.4 人工动态抽检与策略

- [ ] 每类至少抽检 1 页的开头、中段、结尾和页边界。
- [ ] 检查字幕遮挡、镜头晕动、信息裁切、转场、节奏和降级。
- [ ] P0/P1=0；P2 关闭或由用户具名接受；P3 全部登记。
- [ ] 验证 G03 已冻结的目标 `feature-policy.json`：旧项目 V1，新项目 V2，可一键回退；本阶段不修改候选策略。
- [ ] 若验收表明 feature policy 需要变化，必须创建新 commit 和新候选，从 G01/G03 及受影响 Gate 重跑，不能原地替换。
- [ ] 最终策略与 G03 已冻结策略一致且动态验收通过时，写入 `EFFECTS_READY=PASS`。

## 11. G08：中断恢复、重装与回滚

### G08.1 受控故障注入

- [ ] 在至少完成一页 checkpoint 后中断 owned API。
- [ ] 中断 owned Worker。
- [ ] 中断 owned Remotion/Node。
- [ ] 在分页渲染和最终合成阶段分别中断 owned FFmpeg。
- [ ] 注入输出锁、输出不可写、TEMP 不可写、低磁盘和端口冲突。
- [ ] 在 stable publish 前和 `latest` 切换前分别中断。
- [ ] 覆盖取消、重试、UI 刷新和启动器重启。

### G08.2 恢复断言

- [ ] 状态进入明确的 paused/recoverable/failed，不伪报 succeeded。
- [ ] resume 使用相同 frozen input、graph 和 export spec。
- [ ] 已完成页 cache hit，未完成页继续。
- [ ] attempt、checkpoint 和 publication 不串线。
- [ ] 上一成功 MP4、制作包和 `latest` 始终安全。
- [ ] 最终只产生一个有效 publication。
- [ ] process registry 外的进程不被终止。

### G08.3 卸载、重装和回滚

- [ ] 正常停止受管进程后卸载候选。
- [ ] 程序目录和快捷方式移除，WorkspaceRoot 和项目保留。
- [ ] 重装同一候选后发现原项目、任务记录和最终输出。
- [ ] 从基线版本升级候选并回滚到 previous。
- [ ] active/previous 指针、payload hash 和项目兼容性正确。
- [ ] 回滚关闭 V2 但不删除 V2 数据。
- [ ] 写入 `RECOVERY_READY=PASS`。

## 12. G09：质量与人工视听

### G09.1 自动媒体质量

- [ ] ffprobe 和完整 decode-to-null 通过。
- [ ] 黑帧、冻结帧、异常静音、爆音、响度、音画时长差和丢帧检查通过。
- [ ] 字幕时间、边界、安全区和烧录/软字幕策略正确。
- [ ] preview/render plan、graph、spec、runtime 和最终 artifact 绑定一致。
- [ ] 诊断包脱敏检查通过。

### G09.2 人工视听

- [ ] 用户或用户指定 reviewer 播放最终 MP4 全片。
- [ ] 检查开头、中段、结尾和每个页边界。
- [ ] 检查字幕、错字、断句、同步和可读性。
- [ ] 检查声音、静音、爆音和音画同步。
- [ ] 检查特效节奏、遮挡、镜头舒适度、转场和降级。
- [ ] 检查字体替换、画面裁切、图表/图片错误和明显卡顿。
- [ ] 记录 `reviewer`、`reviewed_at`、candidate、final MP4 SHA-256、decision 和 notes。
- [ ] 自动化不得代填用户的 `accepted_by`。
- [ ] 写入 `QUALITY_READY=PASS`。

## 13. G10：最终总审计与签署

### G10.1 聚合

- [ ] 显式列出 G00-G09 报告路径，不搜索“最新”。
- [ ] 运行 `scripts/personal_use_closure.py`。
- [ ] 校验所有报告 source commit、candidate、installer、runtime 和 feature policy 一致。
- [ ] 校验所有 evidence ref 存在且 SHA-256 匹配。
- [ ] 校验最终 MP4 hash 与人工视听记录一致。
- [ ] 校验无 not_run/running/blocked/failed/stale 阶段。

### G10.2 缺陷和失效审计

- [ ] P0/P1 为 0。
- [ ] P2 全部具备 owner、影响、规避、accepted_by 和 accepted_at。
- [ ] P3 进入已知限制和后续版本清单。
- [ ] 从 G01 起无未登记源码、依赖、安装包、runtime、模板、策略或输入变化。
- [ ] 当前工作树与最终 source commit 一致且 clean。

### G10.3 最终产物

- [ ] 生成 `final-evidence-manifest.json`。
- [ ] 生成 `personal-use-signoff.json`。
- [ ] 生成用户七步操作说明、Effects V2 使用/回退说明、恢复/重装说明和已知限制。
- [ ] 记录唯一 installer 路径与 SHA-256。
- [ ] 记录唯一最终 MP4 路径、大小与 SHA-256。
- [ ] 写入 `PERSONAL_USE_READY=PASS`。

## 14. 完成后的第二轮未完成项审计

- [ ] 再次搜索所有设计/计划中的 unchecked、TODO、blocked、not_run、stale 和 failed。
- [ ] 再次检查所有 worktree 是否有尚未选择的个人可用阻断变更。
- [ ] 再次核对 CI、DP45、Windows、真实 PPT、Effects、恢复、质量和人工签署报告。
- [ ] 再次验证 installer/runtime/feature-policy/final-MP4 hash 链。
- [ ] 发现漏项时回到最早受影响 Gate，完成后顺序重跑下游 Gate。
- [ ] 第二轮审计为零才保留 `PERSONAL_USE_READY=PASS`；否则立即标记 invalidated。

## 15. 最终检查清单

- [ ] `BASELINE_CONFIRMED=PASS`。
- [ ] `SOURCE_CANDIDATE_FROZEN=PASS`。
- [ ] `FINAL_SOURCE_READY=PASS`。
- [ ] `CI_GREEN=PASS`。
- [ ] `FINAL_CANDIDATE_BUILT=PASS`。
- [ ] `FINAL_CANDIDATE_READY=PASS`。
- [ ] `DP45_READY=PASS`。
- [ ] `INSTALLED_READY=PASS`。
- [ ] `LOCAL_FLOW_READY=PASS`。
- [ ] `UI_EXPORT_READY=PASS`。
- [ ] `EFFECTS_READY=PASS`。
- [ ] `RECOVERY_READY=PASS`。
- [ ] `QUALITY_READY=PASS`。
- [ ] `PERSONAL_USE_READY=PASS`。
- [ ] 第二轮未完成项审计为零。
