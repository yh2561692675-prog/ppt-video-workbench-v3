# PPT Video Workbench 八项目个人可用最终收口逐项实施计划

> 日期：2026-08-14
>
> 状态：待实施
>
> 目标工作树：`F:\ppt-video-workbench-v3\.worktrees\program-integration-v1`
>
> 设计依据：[2026-08-14-eight-project-personal-use-finalization-design.md](../specs/2026-08-14-eight-project-personal-use-finalization-design.md)
>
> 执行规则：P01-P08 严格串行；一个项目完成后直接进入下一项目，不逐项等待确认；G04 长稳按用户要求延期

## 1. 总体规则

- [ ] 只在 `program-integration-v1` 产品工作树读取、开发、测试和构建。
- [ ] 开始每个项目时记录 branch、40 位 HEAD、dirty、锁文件 hash 和工具版本。
- [ ] 当前 `rc-personal-69efe5a-20260814T1625Z` 只作为 V1 历史构建基线，不原地修改。
- [ ] P01 的任何源码或策略修改完成后，在 P02 创建新 commit 和新 candidate ID。
- [ ] 候选冻结后发生源码、依赖、schema、模板、runtime、installer 或策略变化，立即标记下游证据 stale。
- [ ] 每次验收使用新的 `run_id` 和独立 workspace、DB、TEMP、cache、output、logs、ports、process registry。
- [ ] 真实 PPT 使用副本，开始和结束验证原件 SHA-256 不变。
- [ ] 只终止当前 run 注册且 PID 创建时间匹配的进程。
- [ ] P0/P1 立即阻断；P2 必须有 owner、规避和具名接受；P3 登记限制。
- [ ] 每个项目生成机器可读 JSON、Markdown 摘要、evidence manifest 和 hash。
- [ ] 项目失败时只修复最早受影响项目，完成后按顺序重跑下游项目。
- [ ] 不执行 broad reset/clean/delete，不覆盖失败证据，不复用其他候选产物。

## 2. 项目顺序与 Gate

| 顺序 | 项目                    | 前置         | 输出 Gate                                                      |
| ---: | ----------------------- | ------------ | -------------------------------------------------------------- |
|  P01 | Effects V2 工程补齐     | 当前源码基线 | `EFFECTS_ENGINE_READY=PASS`                                    |
|  P02 | 重新冻结源码、CI 与候选 | P01          | `SOURCE_CANDIDATE_FROZEN`、`CI_GREEN`、`FINAL_CANDIDATE_BUILT` |
|  P03 | Windows 安装与启动闭环  | P02          | `INSTALLED_READY=PASS`                                         |
|  P04 | 真实 PPT 完整转视频     | P03          | `LOCAL_FLOW_READY=PASS`、`UI_EXPORT_READY=PASS`                |
|  P05 | Effects V2 动态专项     | P04          | `EFFECTS_READY=PASS`                                           |
|  P06 | 中断恢复、重装与回滚    | P05          | `RECOVERY_READY=PASS`                                          |
|  P07 | 媒体质量与人工视听      | P06          | `QUALITY_READY=PASS`                                           |
|  P08 | 最终总审计与交付        | P07          | `PERSONAL_USE_FUNCTIONAL_READY` 或 `PERSONAL_USE_READY`        |

## 3. P01：Effects V2 工程补齐

### P01.1 基线与 RED 测试

**目标文件：**

- 新增 `scripts/effects_dynamic_acceptance.py`。
- 新增 `schemas/effects-dynamic-acceptance-v1.schema.json`。
- 新增 `tests/release/test_effects_dynamic_acceptance.py`。
- 新增 `tests/fixtures/effects-dynamic-acceptance/`。
- 修改 `scripts/windows_effect_acceptance.ps1`。
- 必要时修改 `scripts/windows_effect_acceptance_lib.ps1`。
- 修改 feature policy schema、生成器、API/Web 显示和相关合同测试。

步骤：

- [ ] 记录 P01 开始时的 HEAD、dirty 和旧候选身份。
- [ ] 添加 missing candidate、tampered manifest、wrong candidate、stale policy、preview/render drift 和 missing frames 的 RED 测试。
- [ ] 添加非法 V2 开关组合 RED 测试：只开 preview、只开 render、只开 persistence 均失败。
- [ ] 添加 V1 fallback 保留 EffectPlan、人工锁和用户设置的 RED 测试。
- [ ] 添加 Windows runner 必须接收显式 candidate/artifact/sample/output 的合同测试。
- [ ] 运行 RED 测试并保存预期失败，不把环境错误当作 RED。

### P01.2 动态验收聚合器

- [ ] 实现显式输入解析，不搜索“最新”候选或输出。
- [ ] 验证 candidate、source commit、runtime manifest、feature policy 和 template hashes。
- [ ] 逐页记录 EffectPlan、RenderGraph、template、preview、final clip、帧数、时长和 SHA-256。
- [ ] 检测 preview/render 计划漂移、hash 漂移、缺帧、时长差和错误候选。
- [ ] 输出固定 schema 的 `effects-dynamic-acceptance.json`。
- [ ] 所有错误使用稳定 reason code，状态失败关闭。
- [ ] golden/tampered/missing/stale/wrong-candidate fixtures 全部通过。

### P01.3 Windows Effects runner

- [ ] 增加 `-CandidateManifest`、`-ArtifactManifest`、`-SampleManifest`、`-ReportRoot` 参数。
- [ ] 验证 InstallRoot、WorkspaceRoot、DB、ReportRoot 互不包含且不指向正式数据。
- [ ] 从安装目录启动 launcher/API，记录实际 candidate ID。
- [ ] 实现 `effects_dynamic_preview` 阶段。
- [ ] 实现 `effects_final_export` 阶段。
- [ ] 实现 `effects_fallback` 阶段，在项目副本上切回 V1 并导出。
- [ ] 每阶段写独立 JSON、日志、evidence refs 和 process registry。
- [ ] 源码测试只作为补充，不能代替安装版阶段。

### P01.4 最终 feature policy

- [ ] 目标策略设为旧项目默认 V1、新项目默认 V2、允许 V1/L0 回退。
- [ ] `persistence/preview/render` 三开关成组验证。
- [ ] UI 显示 generation、policy ID、降级原因和回退状态。
- [ ] 回退不删除 EffectPlan、人工锁、模板版本和用户设置。
- [ ] API/Web/OpenAPI/Project Schema 合同同步。

### P01.5 验证与停点

```powershell
uv run --frozen pytest tests/release/test_effects_dynamic_acceptance.py tests/release/test_windows_effect_isolation_contract.py tests/unit/effects tests/integration/test_effect_engine_mainline.py tests/integration/test_effect_batch_recovery.py -q
uv run --frozen ruff check scripts tests/release tests/unit/effects tests/integration
uv run --frozen mypy apps/api/src scripts/effects_dynamic_acceptance.py
pnpm --filter @workbench/web typecheck
pnpm --filter @workbench/web test -- --run
pnpm --filter @workbench/remotion typecheck
pnpm --filter @workbench/remotion test
git diff --check
```

- [ ] 所有定向验证通过。
- [ ] 生成 `test-results/personal-use/development/p01-effects-engine-ready.json`。
- [ ] 写入 `EFFECTS_ENGINE_READY=PASS`。
- [ ] 创建可回退的 P01 checkpoint commit。
- [ ] 直接进入 P02。

## 4. P02：重新冻结源码、CI 与 Windows 候选

### P02.1 clean source 与候选身份

- [ ] 确认 P01 已提交且工作树 clean。
- [ ] 记录 branch、HEAD、ahead/behind、最后 10 个提交。
- [ ] 计算 `uv.lock`、`pnpm-lock.yaml`、OpenAPI、Project Schema、Effects schema 和模板索引 hash。
- [ ] 生成 `candidate_id = rc-personal-<short-commit>-<UTC>`。
- [ ] 生成候选身份，确认 `dirty=false`、feature policy 为目标 V2 策略。
- [ ] 任何 source/lock/policy 不一致立即停止。

### P02.2 本地全量门禁

```powershell
uv sync --frozen
uv run --frozen ruff check apps tests scripts
uv run --frozen mypy apps/api/src
uv run --frozen pytest -q
pnpm install --frozen-lockfile
pnpm check
pnpm e2e
```

- [ ] 保存 Python collection、passed/failed/skipped、耗时和日志 hash。
- [ ] 单独执行 migration、rendering、effects、jobs、recovery、release、quality 和 security 测试。
- [ ] Web E2E 覆盖本地音频、项目生命周期、播放、取消重试和刷新恢复。
- [ ] Remotion 执行 typecheck、tests、bundle 和真实短 render smoke。
- [ ] OpenAPI、Project Schema 和生成 client diff 为零。
- [ ] installer/runtime/SBOM/license/absolute-path 合同通过。
- [ ] 超时、cancelled 或 skipped required test 不记 pass。

### P02.3 远端 CI

- [ ] 确认当前 commit 已存在于远端分支；若需要 push，等待相应外部授权后执行。
- [ ] 触发 `.github/workflows/ci.yml` 和 required workflows。
- [ ] 保存 workflow ID、run ID、commit、job 结论、日志和产物 hash。
- [ ] required jobs 全部通过才写 `CI_GREEN=PASS`。
- [ ] 未推送、无权限、404、取消或无法访问时写 `BLOCKED_EXTERNAL_CI`。

### P02.4 Windows 候选构建

```powershell
.\scripts\build-release.ps1 `
  -CandidateId <candidate-id> `
  -Output "dist\release\<candidate-id>" `
  -InstallerOutputDirectory "release\<candidate-id>"

.\scripts\build-release.ps1 `
  -Output "dist\release\<candidate-id>" `
  -Verify
```

- [ ] 使用隔离 uv cache 和项目 pnpm store。
- [ ] 构建前后 source HEAD、dirty 和 lock hash 完全一致。
- [ ] 安装包、launcher、API、Web、Node、FFmpeg/FFprobe、Remotion runtime、SBOM 和 license 完整。
- [ ] feature policy 已登记到 runtime manifest。
- [ ] `release-artifacts.json` candidate ID 与预生成 ID 一致。
- [ ] 独立 verifier 重算 installer 和 runtime manifest hash。

### P02.5 四门 preflight 与停点

```powershell
uv run --frozen python scripts/personal_use_preflight.py `
  --repository-root . `
  --candidate-id <candidate-id> `
  --input <approved-ppt-copy> `
  --output-root "test-results\personal-use\<candidate-id>\runs\preflight\output" `
  --output "test-results\personal-use\<candidate-id>\runs\preflight\personal-use-preflight.json"
```

- [ ] source/build/runtime/project 四门全部通过。
- [ ] 生成 `source-candidate.json`、`local-ci.json`、`remote-ci.json`、`final-candidate-built.json`。
- [ ] 写入 `SOURCE_CANDIDATE_FROZEN=PASS`。
- [ ] 写入 `FINAL_CANDIDATE_BUILT=PASS`。
- [ ] 远端 CI 通过时写 `CI_GREEN=PASS`；否则保留明确 blocker。
- [ ] 候选目录设置为不可原地修改的保留策略。
- [ ] 直接进入 P03。

## 5. P03：Windows 安装与启动闭环

### P03.1 补齐 runner 语义

**目标文件：**

- 修改 `tests/release/windows-acceptance.ps1`。
- 修改或复用 `scripts/windows_acceptance/runner.py`、`legacy_project.py`、`playback.py`、`render.py`、`processes.py`、`evidence.py`。
- 修改 `scripts/windows_acceptance_report.py` 和对应 schema/tests。

- [ ] `clean_install` 只在安装进程退出、launcher/runtime 文件完整后标 pass。
- [ ] `first_launch` 包含首次和第二次启动子场景。
- [ ] 第二次启动复用同一 workspace/state，端点健康且没有重复 API。
- [ ] launcher/API/Web/runtime candidate ID 一致。
- [ ] workspace、state、logs 与 InstallRoot 分离。
- [ ] 所有 evidence refs 位于 ReportRoot 内且使用相对路径。

### P03.2 隔离实机运行

```powershell
.\tests\release\windows-acceptance.ps1 `
  -ArtifactManifest "release\<candidate-id>\release-artifacts.json" `
  -InstallRoot "F:\PPTVideoWorkbench-Acceptance\<candidate-id>\app" `
  -WorkspaceRoot "F:\PPTVideoWorkbench-Acceptance\<candidate-id>\workspace" `
  -ReportDirectory "F:\PPTVideoWorkbench-Acceptance\<candidate-id>\report"
```

- [ ] 安装目标、workspace 和正式用户目录互不包含。
- [ ] 安装包 hash 与 artifact manifest 一致。
- [ ] 标准用户静默安装成功。
- [ ] 首次启动健康、无黑窗，端口仅 loopback。
- [ ] 关闭后第二次点击 launcher 重新健康启动。
- [ ] 受管进程正常关闭，无孤儿进程和残留端口。
- [ ] 工作区保留标记与 hash 不变。
- [ ] 生成 schema 2.0 报告。
- [ ] 写入 `INSTALLED_READY=PASS`。
- [ ] 直接进入 P04。

## 6. P04：真实 PPT 完整转视频

### P04.1 输入准备

- [ ] 准备小型 2-5 页、标准 8-15 页、复杂 30-50 页 PPT 副本。
- [ ] 优先使用用户明确指定样本；没有用户样本时使用明确标注的内部授权样本，只形成工程验收。
- [ ] 记录原件标识、大小和 SHA-256。
- [ ] 将副本复制到隔离 WorkspaceRoot，每份使用新 project ID。
- [ ] 执行字体、素材、PowerPoint 兼容性和源文件引用预检。

### P04.2 安装版 UI 全链

- [ ] 从 P03 安装版启动，确认 candidate ID。
- [ ] 新建项目并导入 PPT、图片、图表和材料。
- [ ] 核对页面数、标题、图片、图表、字体和源引用。
- [ ] 创建或导入旁白文本。
- [ ] 导入本地音频并完成分页；补充无音频 smoke。
- [ ] 生成或导入字幕，人工修正至少一处。
- [ ] 应用 Effects V2 推荐、调整强度、人工锁一页、批量应用同类页。
- [ ] 执行 fresh 完整预检，0 blocking issue。
- [ ] 从 0 播放到 ended，记录 stall、console error、资源失败和起中末证据。
- [ ] 通过 UI 提交最终导出，观察 queued/running/verifying/publishing/succeeded。
- [ ] 刷新 UI 和重启 launcher 后仍能找到 project、job、attempt 和 publication。

### P04.3 最终媒体与制作包

```powershell
ffprobe -v error -show_format -show_streams -of json <final.mp4>
ffmpeg -v error -i <final.mp4> -f null NUL
```

- [ ] 容器、video/audio codec、分辨率、fps、像素格式和时长与 UI 规格一致。
- [ ] 完整 decode-to-null 无致命错误。
- [ ] 最终时长与时间轴/音频在预算内一致。
- [ ] 制作包 manifest 的路径、大小和 SHA-256 与实际一致。
- [ ] `latest` 指向 stable publication，不指向 staging/temp。
- [ ] 记录 source/project/snapshot/graph/spec/job/attempt/artifact 身份链。
- [ ] 验证原 PPT hash 未变化。
- [ ] 写入 `LOCAL_FLOW_READY=PASS` 和 `UI_EXPORT_READY=PASS`。
- [ ] 若仅使用内部样本，另记 `USER_SAMPLE_REVIEW_PENDING`，不冒充用户最终成片。
- [ ] 直接进入 P05。

## 7. P05：Effects V2 动态专项验收

### P05.1 30 页输入矩阵

- [ ] 重算 `fixtures/effects/education-v2/sources` 下 30 个 PPTX 的 hash。
- [ ] 验证样本授权、类别和 Ground Truth manifest。
- [ ] 十类页面各 3 页，覆盖 L0/L1/L2/L3 和四档强度。
- [ ] 覆盖 ProgressiveReveal、StatCounter、镜头、转场、强调和确定性降级。
- [ ] 覆盖人工锁、重新推荐、批量应用和恢复自动。
- [ ] 覆盖长字幕、空字幕、安全区、Presenter/Overlay 避让。
- [ ] 覆盖从头、seek、中段、页边界和结束帧。

### P05.2 安装版动态运行

```powershell
.\scripts\windows_effect_acceptance.ps1 `
  -Root . `
  -CandidateManifest "test-results\personal-use\<candidate-id>\candidate\candidate-identity.json" `
  -ArtifactManifest "release\<candidate-id>\release-artifacts.json" `
  -SampleManifest "fixtures\effects\education-v2\manifest.json" `
  -FeaturePolicy "dist\release\<candidate-id>\feature-policy.json" `
  -DynamicEvidence "F:\PPTVideoWorkbench-Acceptance\<candidate-id>\effects-workspace\dynamic-evidence.json" `
  -DynamicOutputRoot "F:\PPTVideoWorkbench-Acceptance\<candidate-id>\effects-workspace\dynamic-output" `
  -DynamicReport "F:\PPTVideoWorkbench-Acceptance\<candidate-id>\effects-report\effects-dynamic-acceptance.json" `
  -InstallRoot "F:\PPTVideoWorkbench-Acceptance\<candidate-id>\app" `
  -WorkspaceRoot "F:\PPTVideoWorkbench-Acceptance\<candidate-id>\effects-workspace" `
  -RequireEffectsV2 `
  -RequireEffectsFallback
```

- [ ] 生产数据库路径阻断测试通过。
- [ ] 30/30 页面动态预览成功。
- [ ] 30/30 页面最终片段成功。
- [ ] preview/render 的 plan、graph、template、runtime hashes 一致。
- [ ] 0 个不允许页面误启用 L3。
- [ ] 关闭 V2 后同项目副本通过 V1 预览和导出。

### P05.3 人工动态抽检

- [ ] 每类至少抽检 1 页的开头、中段、结尾和页边界。
- [ ] 检查字幕遮挡、镜头晕动、信息裁切、转场、节奏和降级。
- [ ] P0/P1 为零；P2 修复、关闭或由用户具名接受；P3 登记。
- [ ] 人工记录绑定 candidate 和片段 SHA-256。
- [ ] 验证 feature policy 与 P02 冻结值一致。
- [ ] 写入 `EFFECTS_READY=PASS`。
- [ ] 直接进入 P06。

## 8. P06：中断恢复、重装与回滚

### P06.1 故障注入

- [ ] 在完成至少一页 checkpoint 后中断 owned API。
- [ ] 中断 owned Worker。
- [ ] 中断 owned Remotion/Node。
- [ ] 在分页渲染和最终合成阶段分别中断 owned FFmpeg。
- [ ] 注入输出锁、输出不可写、TEMP 不可写、低磁盘和端口冲突。
- [ ] 在 stable publish 前和 `latest` 切换前中断。
- [ ] 覆盖取消、重试、UI 刷新和 launcher 重启。
- [ ] 所有 PID 通过 process registry、创建时间和命令行确认所有权。

### P06.2 恢复断言

- [ ] 状态进入明确 paused/recoverable/failed，不伪报 succeeded。
- [ ] resume 使用相同 frozen input、graph 和 export spec。
- [ ] 已完成页 cache hit，未完成页继续。
- [ ] attempt、checkpoint 和 publication 不串线。
- [ ] 上一成功 MP4、制作包和 `latest` 始终安全。
- [ ] 最终只产生一个有效 publication。
- [ ] process registry 外的进程不被终止。

### P06.3 卸载、重装和回滚

- [ ] 正常停止受管进程后卸载候选。
- [ ] 程序目录和快捷方式移除，WorkspaceRoot 与项目保留。
- [ ] 实际重装同一候选。
- [ ] 重装后发现原项目、任务记录和最终输出。
- [ ] 使用显式 previous candidate 执行升级与回滚。
- [ ] active/previous 指针、payload hash 和项目兼容性正确。
- [ ] 回滚关闭 V2 但不删除 V2 数据。
- [ ] 写入 `RECOVERY_READY=PASS`。
- [ ] 直接进入 P07。

## 9. P07：媒体质量与人工视听

### P07.1 自动媒体质量

```powershell
.\scripts\run-video-quality-gates.ps1 -Input <final.mp4> -OutputRoot <quality-root>
```

- [ ] ffprobe 与完整 decode-to-null 通过。
- [ ] 黑帧、冻帧、异常静音、爆音、响度、音画时长差和丢帧检查通过。
- [ ] 字幕时间、边界、安全区和烧录/软字幕策略正确。
- [ ] preview/render plan、graph、spec、runtime 与 final artifact 绑定一致。
- [ ] 诊断包脱敏通过，不包含 secret、Cookie、私人正文和非白名单绝对路径。
- [ ] 自动报告绑定 final MP4 SHA-256。

### P07.2 人工视听

- [ ] 生成待审清单和最终 MP4 路径、大小、SHA-256。
- [ ] 用户或指定 reviewer 播放最终 MP4 全片。
- [ ] 检查开头、中段、结尾和每个页边界。
- [ ] 检查字幕、错字、断句、同步和可读性。
- [ ] 检查声音、静音、爆音、响度和音画同步。
- [ ] 检查特效节奏、遮挡、镜头舒适度、转场和降级。
- [ ] 检查字体替换、画面裁切、图表/图片错误和明显卡顿。
- [ ] 记录 reviewer、reviewed_at、candidate、final MP4 SHA-256、decision 和 notes。
- [ ] 自动化不代填 `accepted_by`。
- [ ] 人工未决定时写 `QUALITY_READY=BLOCKED_MANUAL_REVIEW`。
- [ ] 人工通过后写 `QUALITY_READY=PASS`。
- [ ] 直接进入 P08。

## 10. P08：最终总审计与交付

### P08.1 显式聚合

- [ ] 显式列出 P01-P07 报告路径，不搜索“最新”。
- [ ] 运行 `scripts/personal_use_closure.py`。
- [ ] 验证所有报告的 source commit、candidate、installer、runtime 和 feature policy 一致。
- [ ] 验证所有 evidence refs 存在且 SHA-256 匹配。
- [ ] 验证最终 MP4 hash 与人工视听记录一致。
- [ ] 验证无 not_run/running/blocked/failed/stale 必需阶段。

### P08.2 缺陷和失效审计

- [ ] P0/P1 为零。
- [ ] P2 全部有 owner、影响、规避、accepted_by 和 accepted_at。
- [ ] P3 进入已知限制与后续版本清单。
- [ ] P02 后无未登记源码、依赖、installer、runtime、template 或 policy 变化。
- [ ] 当前工作树与最终 source commit 一致且 clean。

### P08.3 交付产物

- [ ] 生成 `final-evidence-manifest.json`。
- [ ] 生成 `personal-use-signoff.json`。
- [ ] 生成用户七步操作说明。
- [ ] 生成 Effects V2 使用、降级和回退说明。
- [ ] 生成中断恢复、卸载重装和版本回滚说明。
- [ ] 生成已知限制和 HeyGen `WAIT_EXTERNAL` 说明。
- [ ] 记录唯一 installer 路径、大小和 SHA-256。
- [ ] 记录唯一 final MP4 路径、大小和 SHA-256。

### P08.4 G04 延期判定

- [ ] 若 G04 尚未执行，写入 `PERSONAL_USE_FUNCTIONAL_READY=PASS`。
- [ ] 同时写入 `PERSONAL_USE_READY=BLOCKED_DEFERRED_G04`，不得省略 blocker。
- [ ] 若同候选 G04 已通过且全部身份一致，写入 `PERSONAL_USE_READY=PASS`。

### P08.5 第二轮未完成项审计

- [ ] 搜索全部设计/计划中的 unchecked、TODO、blocked、not_run、stale 和 failed。
- [ ] 检查所有 worktree 是否存在尚未选择的个人使用阻断变更。
- [ ] 复核 CI、Windows、真实 PPT、Effects、恢复、质量和人工签署报告。
- [ ] 复核 installer/runtime/feature-policy/final-MP4 hash 链。
- [ ] 发现漏项时返回最早受影响项目，解决后顺序重跑下游项目。
- [ ] 第二轮除明确延期 G04 外为零。

## 11. Deferred G04：DP45 长时间稳定性

本项目不在当前连续开发顺序内，有可用窗口后执行：

- [ ] 使用 P02 最终候选创建独立 DP45 config、run ID 和 F 盘隔离根。
- [ ] 持续时间和最小周期同时满足。
- [ ] 覆盖 normal、recovery、cancel/retry、cache reuse 和 publication retention。
- [ ] 保留正式 completion marker、ledger、资源 JSONL 和失败现场。
- [ ] 无孤儿进程、端口泄漏、临时文件失控和上一成功 publication 损坏。
- [ ] completion、candidate、config、ledger 和 report hashes 一致。
- [ ] 写入 `DP45_READY=PASS`。
- [ ] 重新运行 P08 聚合，将功能就绪提升为 `PERSONAL_USE_READY=PASS`。

若执行 G04 前候选发生任何变化，先返回 P02 创建新候选，不复用旧功能验收。

## 12. 最终检查清单

- [ ] `EFFECTS_ENGINE_READY=PASS`。
- [ ] `SOURCE_CANDIDATE_FROZEN=PASS`。
- [ ] `CI_GREEN=PASS` 或明确 `BLOCKED_EXTERNAL_CI`。
- [ ] `FINAL_CANDIDATE_BUILT=PASS`。
- [ ] `INSTALLED_READY=PASS`。
- [ ] `LOCAL_FLOW_READY=PASS`。
- [ ] `UI_EXPORT_READY=PASS`。
- [ ] `EFFECTS_READY=PASS`。
- [ ] `RECOVERY_READY=PASS`。
- [ ] `QUALITY_READY=PASS`。
- [ ] `PERSONAL_USE_FUNCTIONAL_READY=PASS`。
- [ ] G04 延期时 `PERSONAL_USE_READY=BLOCKED_DEFERRED_G04`。
- [ ] G04 通过后 `DP45_READY=PASS` 和 `PERSONAL_USE_READY=PASS`。
- [ ] 第二轮未完成项审计除明确延期项外为零。
