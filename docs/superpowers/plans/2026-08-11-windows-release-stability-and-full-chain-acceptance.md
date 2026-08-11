# Windows 安装包、启动器稳定性与全链路实机验收逐项实施计划

> 对应设计：`docs/superpowers/specs/2026-08-11-windows-release-stability-and-full-chain-acceptance-design.md`

**目标：** 根治安装包发现和桌面启动恢复问题，关闭历史前端失败记录，并在同一冻结候选上完成 Windows 全新安装、首次启动、旧项目兼容、中断恢复、完整预检、从头播放、最终导出、卸载重装和版本回滚的可审计闭环。

**完成标记：** `WINDOWS_FULL_CHAIN_ACCEPTANCE=PASS`

## 1. 工作规则

- 正式验收从冻结候选快照执行，不在持续写入的共享工作区形成发布证据。
- 不修改、迁移或删除真实用户项目；旧项目先生成来源清单，再使用隔离副本。
- 不删除 `F:\Video`、用户工作区根、仓库根或未知进程。
- 测试重跑不能覆盖第一次失败；每次执行生成新 `run_id`。
- 每个任务先补失败测试/contract，再实现，再运行受影响门禁。
- 文件名是建议落点；如实现时调整，必须同步更新设计和 traceability。

## 2. 依赖与里程碑

| 里程碑           | 任务    | 退出条件                             |
| ---------------- | ------- | ------------------------------------ |
| M0 基线冻结      | T00-T01 | 当前问题、候选身份和报告 schema 冻结 |
| M1 产物可发现    | T02-T03 | 构建产物清单成为唯一 installer 入口  |
| M2 启动/安装稳定 | T04-T06 | 无黑窗、可重入、可恢复、可卸载重装   |
| M3 质量/恢复     | T07-T09 | 前端、预检、中断恢复门禁完成         |
| M4 全链路验收器  | T10-T12 | A0-A9 自动/半自动采证可重复          |
| M5 实机放行      | T13-T15 | 同一 RC 实机通过并被冻结门禁消费     |

关键路径：`T00 → T01 → T02 → T03 → T04 → T05 → T06 → T10 → T11 → T12 → T13 → T14 → T15`。

## 3. 逐项任务

### T00：建立问题基线和候选身份

**依赖：** 无  
**预计：** 0.5 人日  
**产物：** 基线报告、候选命名规则、历史失败索引

**文件：**

- 新建：`docs/acceptance/windows-release-baseline.md`
- 新建：`tests/acceptance/windows/history/README.md`
- 修改：`.gitignore`（仅在排除大体积本机证据时）

**步骤：**

- [ ] 记录 `installer_not_found` 的触发位置、当时声明路径、实际输出路径和原始 RC manifest。
- [ ] 将 `web-vitest-error.log` 中 1 文件/3 测试失败的测试名、时间和命令提取为历史索引；原日志保持只读。
- [ ] 记录 2026-08-11 本地复跑的 38 文件/74 测试通过结果，并标明它不是冻结候选发布证据。
- [ ] 定义 `candidate_id = rc-<short-commit>-<UTC-build-id>`；记录 Git commit、dirty 状态、`uv.lock`、`pnpm-lock.yaml` 和 runtime manifest hash。
- [ ] 为所有后续 evidence 增加 `candidate_id` 和 `run_id`。

**验收：**

- [ ] 历史失败和当前观察不再相互覆盖。
- [ ] 任一证据都能追溯到唯一候选和执行批次。

---

### T01：升级 Windows 验收报告为 schema 2.0

**依赖：** T00  
**预计：** 1 人日  
**产物：** fail-closed 报告、证据清单、脱敏测试

**文件：**

- 修改：`scripts/windows_acceptance_report.py`
- 修改：`tests/release/test_windows_acceptance_report.py`
- 新建：`schemas/windows-release-acceptance-v2.schema.json`
- 新建：`tests/fixtures/windows-acceptance/`

**步骤：**

- [ ] 先写测试，要求缺少任一必需阶段时 `decision=block`。
- [ ] 必需阶段扩展为 `artifact_resolution`、`clean_install`、`first_launch`、`legacy_project`、`interruption_recovery`、`full_preflight`、`play_from_start`、`final_export`、`uninstall_reinstall`、`version_rollback`、`process_cleanup`、`workspace_retention`。
- [ ] 每阶段校验时间、结果、reason codes、evidence refs 和 metrics。
- [ ] 新增 `evidence-manifest.json` 生成/再校验；引用缺失或 hash 错时阻断。
- [ ] 扩展脱敏：token、Authorization、Cookie、API key、JWT、用户名、用户/工作区绝对路径和 URL 查询凭证。
- [ ] 保留 schema 1.0 迁移提示，但旧 schema 不满足新发布冻结。

**测试：**

```powershell
uv run pytest tests/release/test_windows_acceptance_report.py -v
uv run ruff check scripts/windows_acceptance_report.py tests/release/test_windows_acceptance_report.py
```

**验收：**

- [ ] 完整 fixture 为 pass；缺阶段、假引用、hash mismatch、敏感信息 fixture 均安全 block。

---

### T02：实现统一发布产物清单

**依赖：** T00  
**预计：** 1 人日  
**产物：** `release-artifacts.json`、独立 verifier、明确错误码

**文件：**

- 修改：`scripts/build-release.ps1`
- 新建：`scripts/release_artifacts.py`
- 新建：`tests/release/test_release_artifacts.py`
- 修改：`tests/release/test_build_release_script.py`
- 修改：`apps/api/src/workbench/effects/rc_manifest.py`
- 修改：相关 RC manifest model/tests

**步骤：**

- [ ] 写路径 containment、缺文件、hash 错和 `.partial` 不可见的失败测试。
- [ ] 构建结束计算 installer、payload manifest、SBOM、launcher 的大小和 SHA-256。
- [ ] 原子生成 `release/release-artifacts.json`，包含 candidate/source/lock hashes。
- [ ] verifier 独立重读并校验全部引用。
- [ ] `rc_manifest.py` 读取声明的 installer relative path，删除固定路径假设。
- [ ] 构建只在清单自校验通过后输出 `WINDOWS_RELEASE_BUILD=PASS`。

**测试：**

```powershell
uv run pytest tests/release/test_release_artifacts.py tests/release/test_build_release_script.py -v
uv run pytest tests/unit/effects -q
```

**验收：**

- [ ] 自定义 `-InstallerOutputDirectory` 仍能被准确发现。
- [ ] installer 被移动、截断或替换后，verifier 给出稳定错误码并阻断。

---

### T03：验收入口改为只消费产物清单

**依赖：** T01、T02  
**预计：** 0.5 人日  
**产物：** 不猜路径的 Windows runner

**文件：**

- 修改：`tests/release/windows-acceptance.ps1`
- 修改：`tests/release/test_launcher_contract.py`
- 修改：`docs/troubleshooting.md`

**步骤：**

- [ ] 参数改为必需 `-ArtifactManifest`，内部调用 verifier 获取规范化 installer 路径。
- [ ] 安装前写入 `artifact_resolution` 阶段。
- [ ] 清单缺失、路径越界、installer 缺失、hash 错都不调用安装器。
- [ ] 日志输出逻辑路径和 reason code；个人绝对路径只留在受控本机证据。
- [ ] 更新排障命令和成功/失败标记。

**验收：**

- [ ] 验收脚本不再拼接 installer 文件名。
- [ ] `installer_not_found` 被细化为构建边界错误并能直接定位。

---

### T04：实现版本槽与原子激活协议

**依赖：** T02  
**预计：** 1.5 人日  
**产物：** current/previous 槽、active pointer、激活/回滚 helper

**文件：**

- 新建：`apps/api/src/workbench/desktop/release_slots.py`
- 新建：`apps/api/src/workbench/desktop/activation.py`
- 新建：`tests/unit/desktop/test_release_slots.py`
- 修改：`apps/api/src/workbench/updates/service.py`
- 修改：`tests/unit/updates/test_update_service.py`

**步骤：**

- [ ] 定义 `active-release.json` 和 `previous-release.json` 严格 model。
- [ ] 校验版本目录 containment、payload manifest hash 和必需运行时。
- [ ] 用同卷临时文件加原子 replace 更新 active pointer。
- [ ] 将 update root 与 workspace root 分离，禁止程序目录进入用户项目目录。
- [ ] 实现 activate、rollback、failed-activation restore 和幂等重试。
- [ ] 加入磁盘满、指针半写、previous 损坏、迁移/健康失败测试。

**测试：**

```powershell
uv run pytest tests/unit/desktop tests/unit/updates -v
```

**验收：**

- [ ] 任意激活失败都保留原健康 active。
- [ ] 回滚不移动/删除项目媒体，状态文件始终可解析。

---

### T05：实现无控制台 GUI 启动器

**依赖：** T04  
**预计：** 2 人日  
**产物：** `workbench-launcher.exe`、可重入/恢复状态机、诊断命令

**文件：**

- 新建：`apps/api/src/workbench/desktop/launcher.py`
- 新建：`apps/api/workbench-launcher.spec`
- 新建：`tests/unit/desktop/test_launcher_state.py`
- 新建：`tests/release/test_gui_launcher_contract.py`
- 修改：`scripts/build-release.ps1`
- 保留并调整：`scripts/launcher.ps1`

**步骤：**

- [ ] 为 active 发现、named mutex、原子状态、PID 创建时间和二次启动写失败测试。
- [ ] 以 PyInstaller `windowed/noconsole` 构建 launcher。
- [ ] 实现 `start`、`status`、`open`、`restart`、`shutdown --wait`、`diagnostics`。
- [ ] 健康实例下第二次点击只打开当前 URL；不健康实例进入有预算恢复。
- [ ] API 异常退出最多自动恢复 2 次，写稳定 reason code 和结构化日志。
- [ ] active 不健康且 previous 有效时自动回退并留下审计。
- [ ] 用户可见失败使用 GUI 对话框/通知。
- [ ] PowerShell launcher 仅作为诊断路径，正式快捷方式不得引用。

**测试：**

```powershell
uv run pytest tests/unit/desktop tests/release/test_gui_launcher_contract.py tests/release/test_launcher_contract.py -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build-release.ps1 -Verify
```

**验收：**

- [ ] Windows 无可见 PowerShell/cmd 宿主窗口。
- [ ] 关闭浏览器后再次点击快捷方式恢复页面。
- [ ] 陈旧 state、API 崩溃和 launcher 重启均有确定恢复结果。

---

### T06：改造安装器生命周期

**依赖：** T04、T05  
**预计：** 1 人日  
**产物：** 版本化安装、真实首次启动验证、受控卸载

**文件：**

- 修改：`installer/workbench.iss`
- 修改：`tests/release/test_build_release_script.py`
- 新建：`tests/release/test_installer_contract.py`
- 修改：`tests/release/install-smoke.ps1`

**步骤：**

- [ ] payload 安装到 `app/releases/<version>`，launcher 安装到稳定 bootstrap 目录。
- [ ] 快捷方式和 `[Run]` 改指向 `workbench-launcher.exe`。
- [ ] 安装结束调用 activation helper，检查 launcher/API/UI 健康。
- [ ] `[UninstallRun]` 调用 `launcher --shutdown --wait`；只删除程序区和快捷方式。
- [ ] 明确排除 `workspace-data`、用户设置、update backups 和用户输出。
- [ ] 重装同版本保持幂等；半完成版本被隔离。

**测试：**

```powershell
uv run pytest tests/release/test_installer_contract.py tests/release/test_build_release_script.py -v
```

**验收：**

- [ ] contract 证明 installer 不再直接调用 PowerShell launcher。
- [ ] 卸载不会删除用户工作区或 `F:\Video`。

---

### T07：正式关闭前端 1 文件/3 测试历史问题

**依赖：** T00  
**预计：** 0.5-1 人日  
**产物：** 冻结候选首轮绿灯、稳定性复跑记录

**文件：**

- 视失败修改：`apps/web/src/features/workflow/WorkflowShell.tsx`
- 视失败修改：`apps/web/src/features/workflow/WorkflowShell.test.tsx`
- 修改：`.github/workflows/ci.yml`
- 新建：`scripts/run-web-release-gate.ps1`
- 新建：`tests/release/test_web_release_gate_contract.py`

**步骤：**

- [ ] 冻结候选先跑一次全量 Web 测试并保存首轮结果。
- [ ] 若仍失败，定位产品状态同步、异步测试或 fixture 污染；不得只增加任意 sleep。
- [ ] 修复后对历史三个场景分别以新 Vitest 进程连续运行 3 次。
- [ ] 再运行 `pnpm check`，保存测试数、退出码、版本和日志 hash。
- [ ] CI 上传机器可读报告；禁止 `.only`，新增 `.skip` 需要门禁/审批清单。
- [ ] 测试数量低于冻结基线时失败。

**命令：**

```powershell
pnpm --filter @workbench/web test -- --reporter=verbose
pnpm check
```

**验收：**

- [ ] 首轮零失败；三个历史场景 3/3 独立进程通过。
- [ ] 有正式证据后再将历史问题标记 closed，不删除历史日志。

---

### T08：让完整预检可重复、可解释、绑定输入

**依赖：** T07  
**预计：** 1.5 人日  
**产物：** fresh preflight、stale 判定、三轮一致性测试

**文件：**

- 修改：预检领域 service/models（按实际路由落点）
- 修改：`apps/web/src/features/preflight/PreflightWorkspace.tsx`
- 修改：`apps/web/src/features/video/PreviewWorkspace.tsx`
- 修改：`tests/integration/test_preflight_routes.py`
- 修改：`tests/integration/test_video_preview_routes.py`
- 新建：`tests/integration/test_preflight_determinism.py`

**步骤：**

- [ ] 定义项目、RenderGraph、Props、素材、配置和工具版本的 canonical fingerprint。
- [ ] 报告增加 `preflight_run_id`、fingerprint、fresh/cache 状态和稳定 issue code。
- [ ] 输入变化后旧报告 stale，render 入口拒绝 stale pass。
- [ ] 验收支持 `fresh=true`，跳过历史 `allowed=true` 缓存。
- [ ] 前端显示新鲜度、输入版本和可执行修复动作。
- [ ] 同输入三次结果相同；修改一个输入只失效相关检查。

**测试：**

```powershell
uv run pytest tests/unit/preflight tests/integration/test_preflight_routes.py tests/integration/test_video_preview_routes.py tests/integration/test_preflight_determinism.py -v
pnpm --filter @workbench/web test -- PreflightWorkspace PreviewWorkspace
```

**验收：**

- [ ] fresh 预检不会复用不匹配输入的旧结论。
- [ ] 同一项目副本跨 API/launcher 重启三轮稳定。

---

### T09：实现可控中断与渲染恢复验收钩子

**依赖：** T05、T08  
**预计：** 1 人日  
**产物：** 确定性故障注入、恢复审计、无重复发布

**文件：**

- 修改：`apps/api/src/workbench/video/render_job.py`
- 修改：`apps/api/src/workbench/video/render_service.py`
- 修改：`apps/api/src/workbench/video/process_runner.py`
- 修改：`tests/integration/test_video_render_job_routes.py`
- 新建：`tests/integration/test_render_interruption_recovery.py`

**步骤：**

- [ ] 在测试/验收模式提供“首个分页 checkpoint 完成”同步点，不在生产 API 暴露任意 kill。
- [ ] 中断前持久化 job ID、input fingerprint、completed pages、staging manifest。
- [ ] 启动恢复时将遗留 running/pause_requested 转为可解释状态。
- [ ] resume 校验 checkpoint hash，复用已完成页，仅继续缺失页。
- [ ] 最终发布使用 job-scoped staging 和原子 latest pointer。
- [ ] 审计记录 interrupted、recovered、resumed、cache_hit、succeeded。

**测试：**

```powershell
uv run pytest tests/integration/test_render_interruption_recovery.py tests/integration/test_video_render_job_routes.py tests/unit/video -v
```

**验收：**

- [ ] 受控 kill 后继续成功，已完成页不重复渲染。
- [ ] checkpoint 被篡改时安全失败。

---

### T10：重构 Windows 全链路验收编排器

**依赖：** T01、T03、T06、T09  
**预计：** 1.5 人日  
**产物：** A0-A9 编排、可续跑状态、统一 evidence writer

**文件：**

- 重构：`tests/release/windows-acceptance.ps1`
- 新建：`scripts/windows_acceptance/runner.py`
- 新建：`scripts/windows_acceptance/evidence.py`
- 新建：`scripts/windows_acceptance/processes.py`
- 新建：`tests/release/test_windows_full_chain_contract.py`

**步骤：**

- [ ] PowerShell 负责 Windows/installer 动作；Python 负责状态机、HTTP、schema、脱敏和证据清单。
- [ ] 增加 `-ArtifactManifest`、`-BaselineArtifactManifest`、`-LegacyProjectSource`、`-EvidenceRoot`、`-ResumeRunId`。
- [ ] 每阶段开始写 checkpoint，完成后原子写结果；中断只从安全阶段继续。
- [ ] 失败保留诊断状态；cleanup 只结束本 run 拥有的进程。
- [ ] 最终只输出一次 `WINDOWS_FULL_CHAIN_ACCEPTANCE=PASS|BLOCK`。
- [ ] dry-run/fixture 覆盖顺序、缺证据、恢复和脱敏，不执行真实安装。

**验收：**

- [ ] 自动测试覆盖 A0-A9 顺序和 fail-closed。
- [ ] `-ResumeRunId` 不跳过失败阶段，不复用其他 candidate 证据。

---

### T11：实现旧项目兼容与数据保留探针

**依赖：** T08、T10  
**预计：** 1 人日  
**产物：** 只读来源清单、隔离副本、迁移/兼容报告

**文件：**

- 新建：`scripts/windows_acceptance/legacy_project.py`
- 新建：`tests/fixtures/legacy-projects/manifest.json`
- 新建：`tests/integration/test_legacy_project_acceptance.py`

**步骤：**

- [ ] 只读扫描来源，记录 schema、项目 ID、页/音频/字幕数量和受保护文件 hash。
- [ ] 创建隔离副本和 copy manifest；迁移只针对副本。
- [ ] 候选打开后验证 ID、结构、素材可访问、字幕/音频/Props 连续性。
- [ ] 对迁移前后受保护媒体 hash 对比；新增派生文件单列。
- [ ] 卸载重装和回滚后重复打开并比较摘要。

**验收：**

- [ ] 来源项目零写入。
- [ ] 迁移、重装、回滚摘要一致，或差异有批准清单。

---

### T12：实现真实从头播放与最终导出采证

**依赖：** T08-T11  
**预计：** 1.5 人日  
**产物：** 浏览器播放探针、render 等待器、ffprobe/制作包校验

**文件：**

- 新建：`tests/e2e/windows-full-playback.spec.ts`
- 新建：`scripts/windows_acceptance/playback.py`
- 新建：`scripts/windows_acceptance/render.py`
- 修改：`playwright.config.ts`
- 复用/修改：`scripts/run-video-quality-gates.ps1`

**步骤：**

- [ ] Playwright 通过真实 UI 从 0 点击播放至 `ended`，不调用内部完成函数。
- [ ] 记录 currentTime、stall、console/page error、资源 4xx/5xx。
- [ ] 保存起始/中段/末尾截图；未知 console error 或素材 404 阻断。
- [ ] 通过 UI 提交最终导出，轮询同一 job 到终态。
- [ ] 用冻结 FFprobe 校验 H.264/AAC、尺寸、帧率、流/容器时长。
- [ ] 校验制作包 manifest 大小/hash，证明重启后 job/产物仍可查询。
- [ ] 生成开头/中段/结尾最小人工视听检查表。

**验收：**

- [ ] 播放到 ended，无未知致命浏览器/网络错误。
- [ ] 成片和制作包通过机器校验与最小人工确认。

---

### T13：执行冻结候选完整自动门禁与构建

**依赖：** T02-T12  
**预计：** 0.5-1 人日  
**产物：** 候选 installer、产物清单、G1-G3 证据

**步骤：**

- [ ] 从冻结快照记录 candidate 和源状态，确认无未登记写入。
- [ ] 执行 Python 全量、Ruff、mypy、`pnpm check`、Remotion 和 release tests。
- [ ] 执行前端历史失败场景 3 次独立进程稳定性门禁。
- [ ] 准备 runtime，执行完整 `build-release.ps1`，不能只验证旧 staging。
- [ ] 独立运行 release artifact verifier。
- [ ] 保存 stdout/stderr、统计、工具版本和 hash。

**建议命令：**

```powershell
uv run pytest
uv run ruff check .
uv run mypy apps/api/src
pnpm check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build-release.ps1
```

**验收：**

- [ ] G1-G3 首轮通过。
- [ ] `release-artifacts.json` candidate 与冻结快照一致。

---

### T14：在 Windows 实机执行 A0-A9

**依赖：** T13  
**预计：** 1 人日，渲染耗时另计  
**产物：** schema 2.0 报告和实机证据包

**前置：**

- [ ] 专用 Windows 11 x64 实体设备，标准用户权限。
- [ ] 验收机编号、OS build、系统时间和磁盘空间已记录。
- [ ] candidate/baseline manifest、旧项目只读来源和隔离 evidence root 已准备。
- [ ] 安装、卸载、重装和回滚已获得明确授权。

**执行：**

- [ ] A0：解析并校验 candidate/baseline 产物清单。
- [ ] A1：把批准的应用安装状态恢复到干净基线，执行全新安装。
- [ ] A2：观察安装后自动启动；确认无黑窗、API/UI 健康；关闭浏览器并从快捷方式恢复。
- [ ] A3：复制并打开旧项目；生成迁移和兼容摘要。
- [ ] A4：首个 render checkpoint 后中断 API，恢复并继续。
- [ ] A5：fresh 完整预检三次；第二次前重启 API，第三次前重启 launcher。
- [ ] A6：从 0 播放到结束，完成人工三点抽检。
- [ ] A7：从 UI 导出最终视频，执行 ffprobe、制作包和持久化验证。
- [ ] A8：卸载并验证程序移除/项目保留；重装同一 RC 并复开项目。
- [ ] A9：执行 baseline → candidate → baseline 回滚矩阵，验证项目和版本指针。
- [ ] 验证无本 run 残留进程，workspace retention marker hash 不变。

**验收：**

- [ ] 输出 `WINDOWS_FULL_CHAIN_ACCEPTANCE=PASS`。
- [ ] A0-A9、process cleanup、workspace retention 无缺失、无 blocker。

---

### T15：把完整 Windows 报告设为强制发布门禁

**依赖：** T14  
**预计：** 0.5 人日  
**产物：** 强制冻结门禁、签署记录、排障与复跑说明

**文件：**

- 修改：`scripts/freeze-release.ps1`
- 修改：`tests/release/test_release_freeze.py`
- 修改：`docs/troubleshooting.md`
- 修改：对应版本的 acceptance signoff 和 release notes

**步骤：**

- [ ] `-WindowsAcceptanceReport` 改为正式发布必需参数。
- [ ] 只接受 schema 2.0、decision pass、blockers 空、evidence manifest 完整的报告。
- [ ] 验证 candidate ID、installer/payload hash、Git commit 与冻结候选一致。
- [ ] 增加报告有效期和批准验收机检查；过期报告不能复用。
- [ ] 测试缺报告、旧 schema、错误 candidate、缺 evidence、阶段失败和过期。
- [ ] 更新排障文档：安全复跑、证据位置、数据保护、人工授权边界。

**测试：**

```powershell
uv run pytest tests/release/test_release_freeze.py tests/release/test_windows_acceptance_report.py -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/freeze-release.ps1 -WindowsAcceptanceReport <report>
```

**验收：**

- [ ] 无完整实机报告时发布冻结必然失败。
- [ ] 只有当前冻结候选的完整通过报告可冻结成功。

## 4. 最终追踪矩阵

| 关注项                | 实现任务     | 验收 | 证据                                    |
| --------------------- | ------------ | ---- | --------------------------------------- |
| `installer_not_found` | T02-T03      | A0   | 产物清单、verifier、installer hash      |
| 安装后不自动启动      | T05-T06      | A2   | installer 日志、GUI launcher、health/UI |
| 黑窗关闭后无法恢复    | T05          | A2   | 无控制台、关闭浏览器后二次快捷方式恢复  |
| 预检反复不通过        | T08          | A5   | 三轮 fresh 报告和一致 fingerprint       |
| 1 文件/3 前端测试失败 | T07、T13     | G1   | 首轮全量通过、历史场景 3 次通过         |
| 全新安装              | T06、T10     | A1   | 安装日志、布局、进程证据                |
| 首次启动              | T05-T06      | A2   | 首启计时、截图、health/UI               |
| 旧项目兼容            | T11          | A3   | 前后摘要、迁移报告、受保护 hash         |
| 中断后恢复            | T09          | A4   | 状态/审计、checkpoint/cache             |
| 完整预检              | T08          | A5   | 三份 fresh 报告                         |
| 从头播放              | T12          | A6   | currentTime/stall/console/network/截图  |
| 最终视频导出          | T09、T12     | A7   | job、ffprobe、制作包 manifest/hash      |
| 卸载和重装            | T06、T10-T11 | A8   | 日志、项目复开、保留标记                |
| 版本回滚              | T04、T11     | A9   | active/previous、健康和兼容报告         |

## 5. 风险与停点

| 风险                       | 触发停点                      | 处理                                                                  |
| -------------------------- | ----------------------------- | --------------------------------------------------------------------- |
| 旧项目迁移不可逆           | baseline 无法重新打开副本     | 停止声明可回滚，先设计兼容层或恢复格式                                |
| GUI launcher 体积/杀软误报 | installer/启动被系统拦截      | 保存签名/扫描证据，评估轻量 bootstrap；不退回可见 PowerShell 正式方案 |
| 实机 render 超时           | 超时但子进程仍存活            | 标记 blocked 并保存状态；明确新时限后新 run                           |
| 自动浏览器与默认浏览器不同 | Playwright 通过但人工首启失败 | 保留默认浏览器人工观察；自动化负责可重复数据                          |
| 卸载目标可能触及用户数据   | 目标不在批准隔离根            | 立即停止，不执行删除；重新解析并确认                                  |
| 仓库仍有未登记写入         | 冻结前后 hash 不一致          | 作废 candidate 和已有证据，重新冻结                                   |

## 6. 计划完成定义

- [ ] T00-T15 全部完成，代码、schema、测试和文档进入同一可重建候选。
- [ ] G1-G3 自动门禁通过并有不可变证据。
- [ ] Windows 实机 A0-A9 一次连续 run 全部通过。
- [ ] 前端历史 1 文件/3 测试失败由冻结候选证据正式关闭。
- [ ] installer 路径不再被发布/验收代码硬编码猜测。
- [ ] 最终用户快捷方式无黑窗且支持二次启动和故障恢复。
- [ ] 发布冻结强制消费 schema 2.0 完整 Windows 报告。
- [ ] 最终输出 `WINDOWS_FULL_CHAIN_ACCEPTANCE=PASS`，报告 candidate/hash 与发布候选一致。

## 7. 2026-08-11 实施结果

本节是本轮实际执行状态，优先于上文尚未机械回填的逐条复选框。详细证据见 `docs/acceptance/windows-full-flow-2026-08-11.md`。

- [x] 安装包产物清单、稳定发现、大小与 SHA-256 复核完成。
- [x] 前端历史残余失败关闭：正式发布构建中 Web 43 文件/84 测试、Remotion 12 文件/32 测试全部通过。
- [x] 全新安装、首次启动、PPT/提纲导入、4 页匹配、旁白确认、音频与字幕链完成。
- [x] 完整预检 0 blocker；单页渲染、4 页批量渲染和最终合成完成。
- [x] 渲染中断、重启识别、正式 retry 恢复和父子任务审计完成。
- [x] Edge 从 0 秒播放至 `ended`；最终 MP4 的 ffprobe 与完整解码通过。
- [x] 重启后项目、成功任务和最终视频恢复完成。
- [x] 故障版本槽自动回滚到 previous 健康版本完成。
- [x] Windows 原生 shutdown 修复；API、supervisor 和状态文件清理完成。
- [x] 最终安装包重建、重装、复开、最终卸载与外置工作区保留完成。
- [ ] 正式发布冻结签署：需要对最终 candidate_id 生成同一候选、单次连续、schema 2.0 证据；本轮不把跨候选修复回归伪报为冻结 PASS。
