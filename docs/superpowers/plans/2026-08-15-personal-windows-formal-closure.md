# PPT Video Workbench 个人 Windows 可用正式收口逐项实施计划

> 日期：2026-08-15
>
> 状态：Ready
>
> 设计依据：[2026-08-15-personal-windows-formal-closure-design.md](../specs/2026-08-15-personal-windows-formal-closure-design.md)
>
> 工作树：`F:\ppt-video-workbench-v3\.worktrees\program-integration-v1`
>
> 执行规则：P01-P08 严格顺序；一个项目完成后直接进入下一个项目；发现缺陷返回最早受影响项目，修复后顺序重跑全部下游项目。

## 1. 总体执行规则

- [ ] 只在 `program-integration-v1` 产品工作树开发、测试和构建。
- [ ] 每个项目开始时记录 branch、HEAD、dirty、ahead/behind、lockfile hash 和工具版本。
- [ ] 保留 `rc-cc0f0c6-20260814T174100Z` 为 V1 历史基线，不原地修改。
- [ ] 最终 V2 候选只在 P02 所有源码和验收工具稳定后创建一次。
- [ ] 最终候选冻结后不得修改源码、依赖、schema、模板、runner、feature policy、runtime 或 installer。
- [ ] 如冻结后必须修改，立即将候选和下游证据标记 stale，返回 P02 创建新候选。
- [ ] 每个 run 使用独立 run ID、InstallRoot、WorkspaceRoot、StateRoot、LogRoot、TEMP、cache、output、DB 和端口范围。
- [ ] 不覆盖失败、中断或旧候选证据；不搜索“最新”产物。
- [ ] 只停止 process registry 中登记且创建时间、路径和命令行匹配的 PID。
- [ ] 自动化不得代填人工签署。
- [ ] push、PR、远端触发、模型下载和用户文件传输需要相应外部授权。
- [ ] 每个项目输出 JSON Gate、Markdown 摘要、evidence manifest 和 SHA-256。

## 2. 最终目录和运行变量

实施时统一设置：

```powershell
$candidateId = "rc-personal-<short-commit>-<UTC>"
$candidateEvidenceRoot = "test-results\personal-use\$candidateId"
$candidateStageRoot = "dist\release-$candidateId"
$candidateInstallerRoot = "release\$candidateId"
$candidateAcceptanceRoot = "F:\PPTVideoWorkbench-Acceptance\$candidateId"
```

最终候选创建前，`$candidateId` 只使用占位值；P02 冻结后所有 P03-P08 命令复用同一值。

## 3. P01：Effects V2 工程基线确认

### P01.1 只读基线

- [ ] 确认当前工作树 clean。
- [ ] 确认 Effects 动态聚合器、schema、测试和 30 页样本存在。
- [ ] 确认 V1 fallback、人工锁、批量应用和恢复合同仍在。
- [ ] 计算 `fixtures/effects/education-v2/manifest.json`、ground truth 和 30 个 PPTX 的 SHA-256。

### P01.2 专项门禁

```powershell
uv run --frozen pytest -q `
  tests/release/test_effects_dynamic_acceptance.py `
  tests/release/test_windows_effect_isolation_contract.py `
  tests/unit/effects `
  tests/integration/test_effect_engine_mainline.py `
  tests/integration/test_effect_batch_recovery.py

uv run --frozen ruff check `
  scripts/effects_dynamic_acceptance.py `
  tests/release/test_effects_dynamic_acceptance.py `
  tests/unit/effects `
  tests/integration/test_effect_engine_mainline.py `
  tests/integration/test_effect_batch_recovery.py

uv run --frozen mypy apps/api/src scripts/effects_dynamic_acceptance.py
pnpm --filter @workbench/web typecheck
pnpm --filter @workbench/remotion typecheck
git diff --check
```

### P01.3 输出与停止点

- [ ] 输出 `gates/p01-effects-engine-ready.json`。
- [ ] 记录 `EFFECTS_ENGINE_READY=PASS`。
- [ ] 若只出现源码回归，修复并形成 checkpoint commit；否则不重复开发 P01。
- [ ] 直接进入 P02。

## 4. P02：源码、CI 与最终 V2 候选

P02 必须先解决所有会导致冻结后改源码的验收工具缺口。

### P02.1 下游验收工具冻结前审计

- [ ] 搜索所有 required stage 中的 `blocked`、`not_run`、`TODO`、`phase_not_executed` 和硬编码占位。
- [ ] `tests/release/windows-acceptance.ps1` 不再将下列阶段硬编码为 blocked：
  - `legacy_project`
  - `interruption_recovery`
  - `full_preflight`
  - `play_from_start`
  - `final_export`
  - `version_rollback`
- [ ] 为 Windows runner 增加显式参数：小型/标准/复杂 PPT、previous candidate、真实音频、ASR model manifest 和人工步骤输出位置。
- [ ] Windows runner 从安装目录执行，源码服务只能用于辅助诊断。
- [ ] `scripts/windows_effect_acceptance.ps1` 能实际生成而非只消费动态 evidence。
- [ ] 实现安装版 30 页 preview/final/fallback runner，逐页记录 plan、graph、template、frame、duration 和 SHA-256。
- [ ] 由 `scripts/effects_dynamic_evidence.py` 从安装版实际输出组装 raw evidence；缺任一页 preview/final 或 `page.json` 时必须失败，禁止生成占位媒体。
- [ ] 实现 API、Worker、Node、FFmpeg 的精确 PID 故障注入 helper 和进程所有权测试。
- [ ] 实现 final MP4 单文件质量 CLI；它必须调用现有质量引擎并输出候选绑定 JSON。
- [ ] `scripts/run-video-quality-gates.ps1` 保留无参数全量测试模式，并新增 `-Input/-OutputRoot/-CandidateManifest/-TargetManifest/-FfmpegDir` 候选绑定模式。
- [ ] 扩展 `scripts/personal_use_closure.py`（或增加同级聚合器），显式区分 `PERSONAL_USE_FUNCTIONAL_READY` 与包含 G04 的 `PERSONAL_USE_READY`，不得让未提供 G04 证据的聚合结果误报完整 ready。
- [ ] 检查 `scripts/provision_asr_model.py`：正式验收必须记录模型 repository、revision、文件大小和 SHA-256；mutable `main` 不能作为唯一身份。
- [ ] 将 PyInstaller 加入 dev 依赖并更新 `uv.lock`，使 `workbench.spec` 合同测试可由 `uv sync --frozen` 恢复。
- [ ] 为所有新增/补齐 runner 添加 release contract tests、tampered/wrong-candidate tests 和 Windows 路径隔离测试。
- [ ] 所有验收工具完成后形成一个 clean checkpoint commit。

如果这一步发现产品代码缺陷，也在 P02 内修复并测试；不要先创建候选。

### P02.2 本地完整门禁

```powershell
uv sync --frozen
uv run --frozen ruff check apps tests scripts
uv run --frozen mypy apps/api/src
uv run --frozen pytest -q
pnpm install --frozen-lockfile
pnpm check
pnpm e2e
git diff --check
```

额外定向运行并单独保存日志：

- [ ] migrations 和 project schema。
- [ ] Effects V2、render graph、preview、final render。
- [ ] async jobs、checkpoint、cancel/retry 和 recovery。
- [ ] Windows launcher、release manifest、installer 和 rollback。
- [ ] quality、diagnostics、security 和 secret redaction。
- [ ] Remotion typecheck、tests、bundle 和真实短 render smoke。
- [ ] OpenAPI、generated client、project schema 和 contract drift 为零。

门禁规则：

- [ ] required 测试超时、取消、跳过或无摘要均不得记 pass。
- [ ] ruff 基线必须清零或由当前仓库的正式排除配置明确治理，不能在 Gate 报告中隐去。
- [ ] Playwright 使用隔离 workspace 和端口，不复用残留服务。

### P02.3 最终策略确认

- [ ] 使用 `schemas/feature-policy-effects-v2-acceptance.json` 的 V2 行为。
- [ ] 验证旧项目默认 V1、新项目默认 V2、三开关全开、允许 fallback。
- [ ] 验证非法部分开启组合失败关闭。
- [ ] 验证 V1 fallback 不删除 V2 数据。
- [ ] 保存 policy source hash，后续构建使用显式 `-FeaturePolicySource`。

### P02.4 clean commit 与候选身份

```powershell
git status --short
git rev-parse HEAD
git rev-list --left-right --count '@{upstream}...HEAD'
Get-FileHash uv.lock,pnpm-lock.yaml -Algorithm SHA256
```

- [ ] 工作树必须 clean。
- [ ] 生成 `candidate_id = rc-personal-<short-commit>-<UTC>`。
- [ ] 记录 branch、source commit、ahead/behind、最近 10 个 commit 和 lock hashes。
- [ ] 生成候选身份，状态必须为 `candidate_frozen`、`dirty=false`。

### P02.5 远端 CI

- [ ] 当前分支领先远端 62 个提交的事实写入 Gate。
- [ ] push 属于外部写操作；获得授权后才执行。
- [ ] required workflows 必须绑定最终 source commit。
- [ ] 保存 workflow ID、run ID、job conclusions、日志和产物 hashes。
- [ ] 所有 required jobs 通过后写 `CI_GREEN=PASS`。
- [ ] 未推送、无权限、网络失败、404、取消或超时时写 `BLOCKED_EXTERNAL_CI`。

### P02.6 构建唯一 V2 候选

```powershell
.\scripts\build-release.ps1 `
  -CandidateId $candidateId `
  -FeaturePolicySource "schemas\feature-policy-effects-v2-acceptance.json" `
  -Output $candidateStageRoot `
  -InstallerOutputDirectory $candidateInstallerRoot

.\scripts\build-release.ps1 `
  -Output $candidateStageRoot `
  -Verify
```

- [ ] 构建前后 HEAD、dirty、uv.lock 和 pnpm-lock.yaml 完全一致。
- [ ] installer、launcher、API、Web、Node、FFmpeg/FFprobe、Remotion、SBOM 和 licenses 完整。
- [ ] normalized feature policy 的 candidate ID、policy ID 和 hash 与 runtime manifest 一致。
- [ ] release-artifacts 的 installer/runtime hash 由独立 verifier 重算一致。
- [ ] 将 candidate identity、artifact manifest、runtime manifest 和 policy 复制到候选证据根，副本 hash 不变。

### P02.7 四门 preflight

```powershell
uv run --frozen python scripts/personal_use_preflight.py `
  --repository-root . `
  --candidate-id $candidateId `
  --input "<approved-small-ppt-copy>" `
  --output-root "$candidateEvidenceRoot\runs\preflight\output" `
  --output "$candidateEvidenceRoot\runs\preflight\personal-use-preflight.json"
```

- [ ] source/build/runtime/project 四门全部通过。
- [ ] 写入 `SOURCE_CANDIDATE_FROZEN=PASS`。
- [ ] 写入 `FINAL_CANDIDATE_BUILT=PASS`。
- [ ] 远端 CI 通过后写入 `CI_GREEN=PASS`。
- [ ] 输出 `gates/p02-source-candidate.json`。
- [ ] 冻结候选并直接进入 P03。

## 5. P03：Windows 普通用户安装与启动

### P03.1 准备隔离根

- [ ] `$candidateAcceptanceRoot` 必须为新目录。
- [ ] InstallRoot、WorkspaceRoot、StateRoot、LogRoot 互不包含。
- [ ] 与正式用户 workspace、生产 DB 和历史验收根无重叠。
- [ ] 记录 PowerShell、Windows、CPU、内存和磁盘基线。

### P03.2 执行物理验收

```powershell
.\tests\release\windows-acceptance.ps1 `
  -ArtifactManifest "$candidateInstallerRoot\release-artifacts.json" `
  -CandidateManifest "$candidateEvidenceRoot\candidate\candidate-identity.json" `
  -InstallRoot "$candidateAcceptanceRoot\app" `
  -WorkspaceRoot "$candidateAcceptanceRoot\workspace" `
  -ReportDirectory "$candidateAcceptanceRoot\windows-report" `
  -StartupTimeoutSeconds 60 `
  -InstallOnly
```

- [ ] 标准用户安装器退出码为 0，安装布局完整。
- [ ] candidate identity、installer、runtime 和 feature policy 一致。
- [ ] 首次启动健康，API 只绑定 `127.0.0.1`。
- [ ] 正常关闭后第二次启动健康，未启动重复 API。
- [ ] 快捷方式和 launcher 不依赖源码工作树。
- [ ] 日志不包含 secret 或用户未授权正文。
- [ ] 关闭后无本 run 孤儿进程和端口。
- [ ] 工作区保留 marker 和 hash 不变。

### P03.3 Gate

- [ ] 所有 required phase 为 passed。
- [ ] 输出 `gates/p03-installed-ready.json`。
- [ ] 写入 `INSTALLED_READY=PASS`。
- [ ] 若发现 runner 或产品缺陷，返回 P02 修复并创建新候选；否则直接进入 P04。

## 6. P04：小型、标准、复杂 PPT 完整转视频

### P04.1 样本与模型准备

- [ ] 准备三份授权 PPT 副本：2-5 页、8-15 页、30-50 页。
- [ ] 每份记录 owner、授权范围、原路径标识、页数、大小和 SHA-256。
- [ ] 准备真实本地 WAV/MP3，覆盖正常语音、跨页边界和短静音。
- [ ] 音频和 PPT 只复制到隔离 workspace，不修改原件。
- [ ] 使用受控 ASR 模型清单；记录 repository、revision、文件名、大小和 SHA-256。
- [ ] 如需下载模型，先取得外部网络和约 500 MB 本地写入授权，再运行：

```powershell
uv run --frozen python scripts/provision_asr_model.py `
  --workspace-root "$candidateAcceptanceRoot\workspace" `
  --model small `
  --revision "<pinned-model-commit>"
```

- [ ] 模型 provision 完成后重算文件 hashes，不把模型打入制作包或 Git。

### P04.2 每份 PPT 的安装版 UI 流程

对小型、标准、复杂样本逐份执行：

- [ ] 从 P03 安装版 launcher 启动并核对 candidate ID。
- [ ] 新建项目并导入 PPT、图片、图表和材料。
- [ ] 核对页数、标题、图片、图表、字体、裁切和引用。
- [ ] 导入或创建旁白，并完成批量确认。
- [ ] 导入真实本地音频，执行非 synthetic 本地转写和自动分页。
- [ ] 检查音频差异并修正至少一个分页边界。
- [ ] 生成字幕并人工修改至少一处文本或断句。
- [ ] 应用 V2 推荐，调整强度，人工锁一页并批量应用同类页。
- [ ] 执行 fresh 完整预检，blocking issue 为零。
- [ ] 从 0 播放到 ended，记录 stall、console error、资源失败和起中末帧。
- [ ] 通过 UI 提交最终导出，观察 queued/running/verifying/publishing/succeeded。
- [ ] 刷新 UI 和重启 launcher，项目、job、attempt、publication 和 latest 仍可发现。
- [ ] 导出最终 MP4、SRT、制作包和清单。

### P04.3 媒体与制作包快速校验

```powershell
ffprobe -v error -show_format -show_streams -of json "<final.mp4>"
ffmpeg -v error -i "<final.mp4>" -f null NUL
```

- [ ] video/audio stream、codec、分辨率、fps、像素格式和时长符合 export spec。
- [ ] 完整解码无 fatal error。
- [ ] 制作包清单路径、大小和 hash 与实际文件一致。
- [ ] `latest` 指向 stable publication，不指向 staging/temp。
- [ ] 原 PPT 和原音频 hash 未变化。

### P04.4 Gate

- [ ] 三档样本全部通过。
- [ ] 输出每份 `real-ppt-flow.json` 和汇总 `gates/p04-local-flow.json`。
- [ ] 写入 `LOCAL_FLOW_READY=PASS`。
- [ ] 写入 `UI_EXPORT_READY=PASS`。
- [ ] 若仅使用内部授权样本，登记 `USER_SAMPLE_REVIEW_PENDING`，不冒充用户成片。
- [ ] 直接进入 P05。

## 7. P05：Effects V2 30 页动态专项

### P05.1 样本矩阵静态核验

- [ ] 30 个 PPTX 全部存在且 hash 与 manifest 一致。
- [ ] 10 类页面各 3 页，授权和 ground truth 完整。
- [ ] 覆盖 L0-L3、四档强度、人工锁、重新推荐、批量应用和 fallback。
- [ ] 覆盖长字幕、空字幕、安全区、Presenter/Overlay 避让和 seek。

### P05.2 安装版动态运行

```powershell
.\scripts\windows_effect_acceptance.ps1 `
  -Root . `
  -CandidateManifest "$candidateEvidenceRoot\candidate\candidate-identity.json" `
  -ArtifactManifest "$candidateInstallerRoot\release-artifacts.json" `
  -SampleManifest "fixtures\effects\education-v2\manifest.json" `
  -FeaturePolicy "$candidateStageRoot\feature-policy.json" `
  -DynamicEvidence "$candidateAcceptanceRoot\effects-workspace\dynamic-evidence.json" `
  -DynamicOutputRoot "$candidateAcceptanceRoot\effects-workspace\dynamic-output" `
  -DynamicReport "$candidateAcceptanceRoot\effects-report\effects-dynamic-acceptance.json" `
  -InstallRoot "$candidateAcceptanceRoot\app" `
  -WorkspaceRoot "$candidateAcceptanceRoot\effects-workspace" `
  -RequireEffectsV2 `
  -RequireEffectsFallback
```

- [ ] 30/30 动态预览成功。
- [ ] 30/30 最终片段成功。
- [ ] preview/render plan、graph、template、runtime 和 policy hashes 一致。
- [ ] 无错误候选、缺帧、hash 漂移或超出阈值的时长漂移。
- [ ] 非法 L3 页为零。
- [ ] V1 fallback 预览和导出成功，V2 数据保留。

### P05.3 人工抽检

- [ ] 每类至少抽检 1 页的开头、中段、结尾和页边界。
- [ ] 检查字幕遮挡、画面裁切、镜头晃动、转场、节奏和降级原因。
- [ ] P0/P1 为零；P2 修复或具名接受；P3 登记。
- [ ] reviewer 记录绑定 candidate ID 和片段 SHA-256。

### P05.4 Gate

- [ ] 输出 `reviews/effects-manual-review.json`。
- [ ] 输出 `gates/p05-effects-ready.json`。
- [ ] 写入 `EFFECTS_READY=PASS`。
- [ ] 直接进入 P06。

## 8. P06：物理恢复、重装与上一版本回滚

### P06.1 自动恢复基线

```powershell
uv run --frozen pytest -q `
  tests/integration/test_async_render_recovery.py `
  tests/integration/test_crash_recovery_matrix.py `
  tests/integration/test_render_interruption_recovery.py `
  tests/integration/test_job_recovery.py `
  tests/unit/jobs/test_checkpoint_recovery.py `
  tests/unit/desktop/test_release_slots.py
```

### P06.2 物理故障注入

对最终候选独立项目副本执行：

- [ ] checkpoint 后终止 owned API。
- [ ] 分页或渲染中终止 owned Worker。
- [ ] 预览和最终渲染中终止 owned Node/Remotion。
- [ ] 分页和最终合成中分别终止 owned FFmpeg。
- [ ] 注入输出锁、输出不可写、TEMP 不可写、低磁盘和端口冲突。
- [ ] stable publish 前和 latest 切换前各中断一次。
- [ ] 覆盖取消、一次安全重试、UI 刷新和 launcher 重启。

每次恢复必须满足：

- [ ] 状态为 paused/recoverable/failed，不伪报 succeeded。
- [ ] resume 使用相同 frozen input、graph 和 export spec。
- [ ] 已完成页 cache hit，未完成页继续。
- [ ] attempt、checkpoint 和 publication 不串线。
- [ ] 上一成功 MP4、制作包和 latest 不损坏。
- [ ] 最终只有一个有效 publication。
- [ ] 未登记进程未被终止。

### P06.3 卸载重装和回滚

- [ ] 正常停止 owned processes 后卸载最终候选。
- [ ] 安装目录和快捷方式移除，WorkspaceRoot 保留。
- [ ] 重新安装同一候选，发现原项目、任务和最终输出。
- [ ] 使用显式 `rc-cc0f0c6-20260814T174100Z` 或经审核的 previous candidate 执行升级/回滚。
- [ ] active/previous 指针、payload hash 和项目兼容性正确。
- [ ] 回滚关闭 V2 执行但不删除 V2 数据。

### P06.4 Gate

- [ ] 输出逐故障 JSON 和 `gates/p06-recovery-ready.json`。
- [ ] 写入 `RECOVERY_READY=PASS`。
- [ ] 直接进入 P07。

## 9. P07：当前候选最终 MP4 质量与人工视听

### P07.1 自动媒体质量

P02 扩展 `run-video-quality-gates.ps1` 后，对 P04 三份最终 MP4 分别运行候选绑定质量 CLI：

```powershell
.\scripts\run-video-quality-gates.ps1 `
  -Input "<final.mp4>" `
  -OutputRoot "$candidateAcceptanceRoot\quality\<sample-id>" `
  -CandidateManifest "$candidateEvidenceRoot\candidate\candidate-identity.json" `
  -TargetManifest "$candidateAcceptanceRoot\<sample-id>\quality-target.json" `
  -FfmpegDir "$candidateStageRoot\runtime\ffmpeg"
```

- [ ] ffprobe 和完整 decode-to-null 通过。
- [ ] 黑帧、冻帧、静音、爆音、响度、true peak、同步和丢帧通过。
- [ ] 字幕时间、边界、安全区和遮挡通过。
- [ ] preview/render plan、graph、spec、runtime 与 final artifact 一致。
- [ ] 诊断包脱敏，无 secret、Cookie、私人正文和非白名单绝对路径。
- [ ] 每个报告绑定 final MP4 SHA-256。

### P07.2 人工视听

- [ ] 生成待审清单，列出 candidate、样本、MP4 路径、大小和 SHA-256。
- [ ] 用户或指定 reviewer 完整播放三份最终 MP4。
- [ ] 检查开头、中段、结尾和全部页边界。
- [ ] 检查字幕、错字、断句、同步和可读性。
- [ ] 检查声音、静音、爆音、响度和音画同步。
- [ ] 检查 Effects 节奏、遮挡、镜头舒适度、转场和降级。
- [ ] 检查字体替换、画面裁切、图片/图表错误和卡顿。
- [ ] 记录 reviewer、reviewed_at、decision、notes 和 MP4 hash。

### P07.3 Gate

- [ ] 自动质量 P0/P1 为零。
- [ ] 人工决定为 accepted。
- [ ] 输出 `reviews/final-av-review.json`。
- [ ] 输出 `gates/p07-quality-ready.json`。
- [ ] 写入 `QUALITY_READY=PASS`。
- [ ] 直接进入 P08。

## 10. P08：最终总审计、签署和交付

### P08.1 显式聚合

```powershell
uv run --frozen python scripts/personal_use_closure.py `
  --candidate "$candidateEvidenceRoot\candidate\candidate-identity.json" `
  --evidence "$candidateEvidenceRoot\gates\p01-effects-engine-ready.json" `
  --evidence "$candidateEvidenceRoot\gates\p02-source-candidate.json" `
  --evidence "$candidateEvidenceRoot\gates\p03-installed-ready.json" `
  --evidence "$candidateEvidenceRoot\gates\p04-local-flow.json" `
  --evidence "$candidateEvidenceRoot\gates\p05-effects-ready.json" `
  --evidence "$candidateEvidenceRoot\gates\p06-recovery-ready.json" `
  --evidence "$candidateEvidenceRoot\gates\p07-quality-ready.json" `
  --require-functional `
  --output "$candidateEvidenceRoot\p08-personal-use-closure.json"
```

- [ ] 所有报告 candidate ID 和 source commit 唯一一致。
- [ ] installer、runtime、policy、PPT、project、graph、spec、job、publication 和 MP4 hashes 一致。
- [ ] 所有相对 evidence refs 存在并位于候选根内。
- [ ] 无 required `blocked`、`failed`、`stale`、`not_run`、`cancelled` 或 `running`。
- [ ] 当前工作树 clean，HEAD 与最终 source commit 一致。

### P08.2 缺陷审计

- [ ] P0/P1 为零。
- [ ] P2 均有 owner、影响、规避、accepted_by 和 accepted_at。
- [ ] P3 进入已知限制。
- [ ] P02 后无未登记源码、依赖、策略、runtime 或 installer 变化。

### P08.3 用户交付物

- [ ] `final-evidence-manifest.json`。
- [ ] `personal-use-signoff.json`。
- [ ] `final-audit.json`。
- [ ] 七步使用说明。
- [ ] Effects V2 推荐、人工锁、降级和 V1 回退说明。
- [ ] 中断恢复、卸载重装和版本回滚说明。
- [ ] 本地 ASR 模型安装、校验、更新和移除说明。
- [ ] 已知限制、HeyGen `WAIT_EXTERNAL` 和 G04 状态说明。
- [ ] 唯一 installer 路径、大小和 SHA-256。
- [ ] 唯一最终 MP4/制作包清单及 SHA-256。

### P08.4 功能收口判定

- [ ] P01-P08 通过时写 `PERSONAL_USE_FUNCTIONAL_READY=PASS`。
- [ ] G04 未运行时写 `PERSONAL_USE_READY=BLOCKED_DEFERRED_G04`。
- [ ] 功能聚合必须使用 `--require-functional`，输出 `PERSONAL_USE_FUNCTIONAL_READY`；不带 G04 证据不得输出完整 `PERSONAL_USE_READY`。
- [ ] 不因 G04 延期抹掉已经完成的功能 Gate。

## 11. G04：最终候选 DP45 两小时资格检查与八小时正式长稳

### G04.1 两小时资格检查

- [ ] 使用最终 candidate/config 创建全新 F 盘隔离根。
- [ ] duration 7200 秒，覆盖 normal、recovery、cancel/retry、cache reuse 和 retention。
- [ ] completion marker、ledger、resource JSONL 和 report 全部存在且 hash 一致。
- [ ] 若失败，保留现场并修复最早受影响项目；源码修复返回 P02。

### G04.2 八小时正式运行

```powershell
.\scripts\run_dp45_soak.ps1 `
  -Candidate "$candidateEvidenceRoot\candidate\candidate-identity.json" `
  -Ffmpeg "$candidateStageRoot\runtime\ffmpeg\ffmpeg.exe" `
  -Ffprobe "$candidateStageRoot\runtime\ffmpeg\ffprobe.exe" `
  -Uv (Get-Command uv).Source `
  -DurationSeconds 28800 `
  -MinimumCycles 100 `
  -PageCount 50 `
  -TempRoot "F:\PPTVideoWorkbench-Soak\<candidate-id>\<run-id>\temp"
```

- [ ] runner 的完成 JSON 和 output log 从 `test-results\soak\long-runs` 复制进候选 evidence root，并记录原路径和 SHA-256。
- [ ] duration 28800 秒和 minimum cycles 同时满足。
- [ ] 使用 S50 或批量等价负载。
- [ ] recovery 和 cancel/retry 周期按配置完成。
- [ ] resource sampler 完整，无不可解释的持续资源增长。
- [ ] 无孤儿进程、端口泄漏、临时文件失控或 stable publication 损坏。
- [ ] completion、candidate、config、ledger、sampler 和 report hashes 一致。
- [ ] 写入 `DP45_READY=PASS`。

### G04.3 最终提升

- [ ] 将 G04 报告加入 `final-evidence-manifest.json`。
- [ ] 重跑 P08 聚合。
- [ ] 写入 `PERSONAL_USE_READY=PASS`。

## 12. 第二轮未完成项审计

完成 P08 后立即执行，不等待逐项确认：

- [ ] 搜索设计和计划中的 unchecked、TODO、blocked、not_run、stale、failed、cancelled 和 running。
- [ ] 搜索所有 worktree 是否存在尚未进入最终候选的个人使用修复。
- [ ] 复核远端 CI、Windows、真实 PPT、Effects、恢复、质量和人工签署。
- [ ] 重算 installer、runtime、policy、输入 PPT、MP4、制作包和 review hashes。
- [ ] 检查证据路径均为相对路径且没有跨候选引用。
- [ ] 发现遗漏时返回最早受影响项目，解决后顺序重跑下游项目。
- [ ] 除明确延期 G04 外，第二轮未完成项为零。

## 13. 最终检查清单

- [ ] `EFFECTS_ENGINE_READY=PASS`
- [ ] `SOURCE_CANDIDATE_FROZEN=PASS`
- [ ] `CI_GREEN=PASS`
- [ ] `FINAL_CANDIDATE_BUILT=PASS`
- [ ] `INSTALLED_READY=PASS`
- [ ] `LOCAL_FLOW_READY=PASS`
- [ ] `UI_EXPORT_READY=PASS`
- [ ] `EFFECTS_READY=PASS`
- [ ] `RECOVERY_READY=PASS`
- [ ] `QUALITY_READY=PASS`
- [ ] `PERSONAL_USE_FUNCTIONAL_READY=PASS`
- [ ] G04 延期时 `PERSONAL_USE_READY=BLOCKED_DEFERRED_G04`
- [ ] G04 通过后 `DP45_READY=PASS`
- [ ] G04 通过后 `PERSONAL_USE_READY=PASS`
- [ ] 第二轮未完成项除明确延期项外为零
