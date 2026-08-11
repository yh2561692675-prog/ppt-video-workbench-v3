# Effects V2 Task 18—25 正确源码找回与验收基线冻结逐项实施计划

> 对应设计：`docs/superpowers/specs/2026-08-11-effects-task18-25-source-recovery-freeze-design.md`

**执行方式：** 严格按顺序推进；每项通过后直接进入下一项。  
**最终标记：** `TASK18_25_BASELINE_FROZEN=PASS`  
**默认分支：** `codex/effects-task18-25-recovery`

## 1. 执行规则

- 当前恢复根工作区只读；所有恢复写入在新的隔离 worktree 中完成。
- 不执行 `reset --hard`、`clean`、强制覆盖、历史改写或删除恢复材料。
- 每个任务先建立红灯/缺失证据，再找回或重建，再复验，再形成 stop-point。
- 每次命令执行绑定 `run_id`；失败日志保留，重跑生成新记录。
- 低优先级来源不能覆盖高优先级来源；来源冲突未裁决时不得继续冻结。
- Task 25 之前不得把安装包存在或 verifier 的单一 `valid=true` 当作完整 RC 通过。
- 任一硬门禁失败时，后续可以继续做只读调查，但不得生成更高层冻结标记。

## 2. 里程碑与关键路径

| 里程碑        | 任务    | 退出条件                                                       |
| ------------- | ------- | -------------------------------------------------------------- |
| M0 安全与来源 | T00—T03 | 当前状态、所有来源、声明提交和恢复材料完成只读登记             |
| M1 源码链     | T04—T08 | Task 18—20 恢复，Task 21—25 缺失文件定位完成，源码链可逐步构建 |
| M2 自动化基线 | T09—T11 | Task 19 全绿与 Task 20 G0—G6 从冻结候选首轮通过                |
| M3 样本合同   | T12—T14 | Task 21—22 的 30 页样本、授权、哈希和 GT 完全一致              |
| M4 效果验收   | T15—T17 | Task 23—24 的 90 帧、指标和逐页视觉复核完成                    |
| M5 Windows RC | T18—T21 | Task 25 全资产校验、单一 RC 和 Windows 实机链通过              |
| M6 总冻结     | T22—T24 | 双重复核、不可变索引、标签/回滚点和最终报告完成                |

关键路径：`T00 → T01 → T02 → T03 → T04 → T05 → T06 → T07 → T08 → T09 → T10 → T11 → T12 → T13 → T14 → T15 → T16 → T17 → T18 → T19 → T20 → T21 → T22 → T23 → T24`。

## 3. 逐项任务

### T00：建立只读安全边界和本次 run 身份

**依赖：** 无  
**产物：** `environment.json`、`workspace-state.txt`、运行目录  
**操作：**

- [ ] 生成唯一 `run_id=effects-recovery-<UTC>-<suffix>`，创建 `docs/acceptance/effects-task18-25-recovery/runs/<run_id>/`。
- [ ] 记录当前路径、分支、HEAD、Git common dir、所有 worktree、`git status --porcelain=v1` 和当前时间。
- [ ] 记录 Python、uv、Node、pnpm、Git、FFmpeg、PowerShell 和 Windows 版本。
- [ ] 对当前已修改和未跟踪文件生成路径清单；不读取或复制与 Effects 恢复无关的用户数据。
- [ ] 建立“当前根工作区禁止写入源码”的执行标记。

**验收：**

- [ ] 记录能够证明当前根为脏工作区，且后续恢复目录与其隔离。
- [ ] T00 全程未修改现有源码、Git refs 或发布制品。

---

### T01：刷新仓库来源和 Git 健康清单

**依赖：** T00  
**产物：** `source-inventory.json`、`git-fsck.log`、`refs.txt`  
**操作：**

- [ ] 运行 `git fsck --full`，保存完整结果和退出码。
- [ ] 导出本仓库所有 heads、remotes、tags、reflog 和 worktree 指针。
- [ ] 登记 `recovery-source/feature/effects-template-workbench`，明确其是独立 Effects authoring 演进线，不能自动视作 Task 18—25 发布链。
- [ ] 检查 `.worktrees/effects-template-workbench` 的断链指针，但不修复、不删除。
- [ ] 如需访问 `F:\git仓库`，先按仓库索引规则刷新 registry、读取 JSON，并按精确 path 选择主仓库或目标 worktree。
- [ ] 对找到的 Git bundle、裸库、仓库备份和恢复快照逐一计算 SHA-256。

**验收：**

- [ ] 所有候选仓库和 refs 有唯一 locator、哈希/HEAD、分支和脏状态。
- [ ] 没有根据目录邻近关系误选仓库。

---

### T02：解析 Task 18—25 声明提交

**依赖：** T01  
**产物：** `commit-resolution.json`、`commit-graph.md`  
**声明线索：**

| Task | 声明提交                                                           |
| ---- | ------------------------------------------------------------------ |
| 18   | `a68d7ee`                                                          |
| 19   | `1169409`；历史全绿基线 `353b911451e8c22fd0185ed06f234ef16ac1a0e7` |
| 20   | `a601226`                                                          |
| 21   | `6864866`                                                          |
| 22   | `817dac6`                                                          |
| 23   | `32eec78`                                                          |
| 24   | `4c9d8ce`                                                          |
| 25   | `3900bf5`                                                          |

**操作：**

- [ ] 在每个候选 Git object database 中对全部提交执行 `git cat-file -e <sha>^{commit}`。
- [ ] 对可解析提交记录完整 SHA、父提交、tree、author/committer 时间和 subject。
- [ ] 验证 Task 顺序的祖先关系；记录分叉、merge、缺口或短哈希歧义。
- [ ] 对不可解析项记录搜索过的来源，不把短哈希补零或猜测为其他提交。
- [ ] 当前对象库“全部不可解析、无 unreachable commit”的发现作为初始证据保存。

**验收：**

- [ ] 每条声明提交的状态为 `found_verified`、`found_conflict` 或 `not_found`，不存在 `unknown`。
- [ ] 所有 `found_verified` 提交可导出完整树且父链可解释。

---

### T03：定位并冻结非 Git 恢复材料

**依赖：** T01  
**产物：** `archive-inventory.json`、`artifact-inventory.json`  
**操作：**

- [ ] 定位 `PPTVideoWorkbench_Task26_RunAll_v3.zip`、`PPTVideoWorkbench_Task26_OneClick_Repair_v2.zip` 和原上传包 `16648ca2-0fa3-44d0-914a-8e6663c8215b.zip`。
- [ ] 定位旧安装包 `.tmp/pre-task25-root-installer-ba588d7675a767b.exe` 和所有同名/近名 RC 安装包。
- [ ] 定位 Windows evidence、Task 23 的 90 帧、acceptance-results 和 Task 24 的实际视觉复核帧。
- [ ] 对所有找到的材料记录绝对 locator、大小、SHA-256、mtime、来源说明和权限状态。
- [ ] 压缩包在唯一临时目录进行安全列表检查；拒绝绝对路径、`..` 穿越、重复路径和异常链接。
- [ ] 原件设为只读或仅复制到只读证据区，派生解压目录记录父 archive hash。

**验收：**

- [ ] 三个声明 ZIP 均被找到并验证，或形成明确 `not_found` 记录和已搜索位置。
- [ ] 安装包与外部证据不因后续重跑被覆盖。

---

### T04：建立候选文件台账和任务归属图

**依赖：** T02、T03  
**产物：** `candidate-ledger.json`、`path-ownership.json`  
**操作：**

- [ ] 从可验证提交、恢复包、worktree、快照和当前工作树提取 Task 18—25 候选文件。
- [ ] 逐文件计算 SHA-256，并记录来源优先级、任务、状态和依赖关系。
- [ ] 对同一路径的不同内容生成语义 diff 和冲突编号。
- [ ] 特别登记当前缺失的 Task 22—24 模块和原始测试。
- [ ] 区分 `recovered` 与 `reconstructed`；不得把根据文档重写的文件标成原始找回。

**验收：**

- [ ] 追踪矩阵中的每个必需路径至少有一个候选或明确缺失记录。
- [ ] 无未登记的同路径覆盖，无来源不明的最终候选。

---

### T05：创建隔离恢复分支和 worktree

**依赖：** T04  
**产物：** `codex/effects-task18-25-recovery`、隔离 worktree、父基线记录  
**操作：**

- [ ] 选择可信 Task 17 末端；验证其源码、测试和文档状态。
- [ ] 若 Task 17 不可信，生成前置 blocker，不继续写 Task 18。
- [ ] 从可信父提交创建恢复分支和独立 worktree。
- [ ] 在新 worktree 验证 `git status --porcelain=v1` 为空。
- [ ] 写入恢复运行 ID 和父提交到证据目录，不把证据运行目录混入任务源码提交。

**验收：**

- [ ] 新 worktree 干净，分支和父提交唯一。
- [ ] 当前根工作区的脏改动未被带入。

---

### T06：恢复 Task 18 发布、回滚和 Windows 验收入口

**依赖：** T05  
**产物：** Task 18 恢复提交、`stop-points/task-18.json`  
**操作：**

- [ ] 找回 `verify_effect_release.py`、Windows 验收脚本、operator guide、release/rollback 文档和发布完整性测试。
- [ ] 先复现缺安装包、错哈希和 Windows 证据缺失时的红灯。
- [ ] 验证回滚只关闭 V2/切换版本，不删除 V2 数据或用户项目。
- [ ] 若原提交缺失，按候选台账重建，并在提交说明中列出依据和差异。
- [ ] 运行 Task 18 测试、ruff、mypy 和本机可执行的发布检查。

**验收：**

- [ ] 非 Windows 环境不会伪报实机通过。
- [ ] Task 18 提交干净、可解析、父提交正确，stop-point 含测试日志哈希。

---

### T07：恢复 Task 19 OpenAPI 与历史全绿基线结构

**依赖：** T06  
**产物：** Task 19 恢复提交、初始 baseline schema、`stop-points/task-19-source.json`  
**操作：**

- [ ] 找回 `packages/contracts/openapi.json` 和缺失的 `docs/effects/current-test-baseline.json`。
- [ ] 验证 OpenAPI 包含当时 9 条 Effects API 路由及对应 schema，且无时间戳、绝对路径和秘密值。
- [ ] 将历史 `353b911...` 仅登记为声明基线，直到完整提交和测试日志被验证。
- [ ] 恢复 baseline 文件的数据模型：source commit、dirty=false、命令、首轮结果、计数、警告、日志哈希。
- [ ] 提交 Task 19 源码/契约恢复，但暂不把未重跑结果标为当前全绿。

**验收：**

- [ ] OpenAPI 生成结果与快照一致。
- [ ] 历史声明和当前复验状态在数据模型中分开。

---

### T08：恢复 Task 20—25 缺失源码和测试骨架

**依赖：** T07  
**产物：** Task 20—25 候选源码序列、每任务红灯记录  
**操作：**

- [ ] Task 20：找回/复核 `release_models.py`、`release_gate.py` 和 16 个 G0—G6 测试。
- [ ] Task 21：找回 sample manifest validator 和 6 个样本测试。
- [ ] Task 22：找回 `ground_truth.py` 和 8 个测试。
- [ ] Task 23：找回 `acceptance_runner.py`、`frame_output.py`、两个执行脚本和 3 个测试。
- [ ] Task 24：找回 `visual_review.py` 和 5 个测试。
- [ ] Task 25：找回 `rc_manifest.py`、build/verify 脚本和 7 个原始测试。
- [ ] 对无法找回的模块先写等价 contract 测试并确认红灯，再按文档、JSON schema 和下游调用重建。
- [ ] 每个任务单独提交，禁止将 Task 20—25 压成一个无法审计的恢复提交。

**验收：**

- [ ] Task 20—25 每个任务都有独立提交候选、原始或重建标识及红灯证据。
- [ ] 文件演化顺序与任务依赖一致。

---

### T09：执行 Task 19 冻结候选的全量自动化

**依赖：** T08  
**产物：** `test-results/task-19/`、当前全绿 baseline  
**操作：**

- [ ] 从 Task 19 恢复提交创建全新干净 worktree，按锁文件恢复依赖。
- [ ] 首轮运行契约测试、后端全量、Web、Remotion、typecheck、ruff、mypy 和 Task 18 发布完整性。
- [ ] 保存命令、stdout/stderr、退出码、开始/结束时间和日志 SHA-256。
- [ ] 记录测试数量和已知警告，但不以历史数量硬编码当前成功条件。
- [ ] 首轮失败时保留结果，修复进入新的提交和 run；不得覆盖失败记录。

**建议命令：**

```powershell
uv run pytest -q
uv run ruff check apps tests scripts
uv run mypy apps/api/src
pnpm --filter @workbench/web typecheck
pnpm --filter @workbench/web test
pnpm --filter @workbench/remotion typecheck
pnpm --filter @workbench/remotion test
```

**验收：**

- [ ] 所有必需命令在同一 source commit、dirty=false 的首轮运行通过。
- [ ] 更新后的 baseline 只引用本次可验证证据，并生成 `AUTOMATION_FROZEN` 候选。

---

### T10：复验 Task 20 G0—G6 fail-closed 门禁

**依赖：** T09  
**产物：** Task 20 最终恢复提交、`stop-points/task-20.json`  
**操作：**

- [ ] 验证 G0 自动化、G1 真实样本、G2 视觉缺陷/签署、G3 Windows、G4 回滚、G5 灰度、G6 汇总。
- [ ] 对每个 Gate 构造缺字段、错误类型、假引用、错哈希和跨候选输入。
- [ ] 确认 G1—G5 缺真实证据时拒绝，而不是因模型默认值通过。
- [ ] 确认模块是纯模型/纯函数，不改变预览、渲染、数据库和 feature flag 执行路径。

**验收：**

- [ ] 原 16 个测试及新增假绿防护测试通过。
- [ ] Task 20 stop-point 引用 Task 19 自动化基线。

---

### T11：冻结 L1 源码链和 L2 自动化基线

**依赖：** T10  
**产物：** `task18-25-source-manifest.json` 初版、`SOURCE_FROZEN`、`AUTOMATION_FROZEN`  
**操作：**

- [ ] 导出 Task 18—25 当前恢复提交、父链、tree hash 和每任务变更路径。
- [ ] 验证全链提交可解析、worktree 干净、无未解决 path ownership 冲突。
- [ ] 对源码、测试、schema、锁文件生成内容哈希树。
- [ ] 由另一独立脚本从零重算 source manifest 并比较。

**验收：**

- [ ] `SOURCE_FROZEN` 与 `AUTOMATION_FROZEN` 均可离线复核。
- [ ] 任一历史提交未找回时，manifest 明确标记相应恢复提交为 `reconstructed`。

---

### T12：复核 Task 21 原始样本来源与授权

**依赖：** T11  
**产物：** `sample-audit/source-archive.json`、30 页样本清单  
**操作：**

- [ ] 校验原上传 ZIP 的 SHA-256 是否为 `2811bf09acc09478514b153c2bb39f90cd07d6423c2fb64e41970011fdc20294`。
- [ ] 安全列出 31 个合法单页 PPTX，验证排除空白模板页的路径、哈希和理由。
- [ ] 对选入 30 页逐一重算 SHA-256，与 metadata 和 manifest 比较。
- [ ] 验证十类页面各 3 页、hash 唯一、`page_number=1`、`authorized_for_regression=true`。
- [ ] 验证 `source_ref` 全为仓库内相对 POSIX 路径，无占位 hash、绝对用户路径和秘密值。
- [ ] 如果原 ZIP 找不到，当前 30 页只能标为 `content_recovered_origin_unverified`，L3 和总冻结保持 BLOCKED。

**验收：**

- [ ] 30/30 内容、授权和分类通过，排除项有可验证来源。
- [ ] 原授权边界未被扩大。

---

### T13：恢复并复验 Task 22 Ground Truth

**依赖：** T12  
**产物：** Task 22 最终恢复提交、`sample-audit/ground-truth-audit.json`  
**操作：**

- [ ] 验证 Ground Truth 30/30 页绑定，不缺页、不重复。
- [ ] 逐页比较 page type、allowed max level 和 Task 21 source SHA-256。
- [ ] 验证 cue 单调且非负、安全区边界、三个关键帧、forbidden modules、camera policy 和 degradation expectation。
- [ ] 验证高风险页禁止原生 L3。
- [ ] 运行原始 8 个测试、全部 Effects 测试、ruff 和 mypy。

**验收：**

- [ ] Ground Truth 与 manifest/PPTX 三方哈希一致。
- [ ] 当前已观察到的 Ground Truth/RC 清单哈希漂移已被解释并修复，而不是更新清单掩盖问题。

---

### T14：冻结 L3 样本合同基线

**依赖：** T13  
**产物：** 完整样本 Merkle/哈希清单、`SAMPLE_FROZEN`  
**操作：**

- [ ] 冻结 30 个 PPTX、30 个 metadata、manifest、Ground Truth 和授权来源引用。
- [ ] 从只读副本重算全部哈希并与索引比较。
- [ ] 在 source manifest 中绑定 Task 21/22 提交、依赖锁和 schema 版本。

**验收：**

- [ ] 任意样本、metadata、manifest 或 Ground Truth 单字节变化都会使门禁失败。
- [ ] L3 不包含未授权素材或个人秘密信息。

---

### T15：执行 Task 23 真实样本计划、关键帧和指标

**依赖：** T14  
**产物：** Task 23 最终恢复提交、90 帧、`acceptance-results.json`  
**操作：**

- [ ] 在新 `run_id` 输出目录重跑 30 页 acceptance plan。
- [ ] 验证 preview plan 和 render plan hash 一致。
- [ ] 生成 90/90 PNG，检查命名、文件存在、尺寸、非空和内容 hash。
- [ ] 运行六项量化指标并确认 `metrics_passed=true`。
- [ ] 验证 `native_l3_false_positive_count=0`。
- [ ] 重跑一次并比较确定性输出；若 PNG 包含非确定元数据，规范化规则必须明确且有测试。

**验收：**

- [ ] 两次运行的语义输出和声明的确定性 hash 一致。
- [ ] 合同级帧未被误标为人工视觉或 Windows 动态证据。

---

### T16：执行 Task 24 逐页视觉复核与缺陷闭环

**依赖：** T15  
**产物：** Task 24 最终恢复提交、visual-review、缺陷台账  
**操作：**

- [ ] 逐页复核 Task 23 本次运行的四类代表帧，引用使用相对 evidence locator 和 hash。
- [ ] 每页记录 reviewer、reviewed_at、问题、严重度和决定。
- [ ] 验证 P0=0、P1=0；P2/P3 均有影响、规避、owner 和关闭条件。
- [ ] 对 30 个 `pass_with_notes` 的 P3 记录逐条复核，不接受批量复制的占位说明。
- [ ] 明确静态复核不能替代 Windows 动态镜头、字幕和最终导出。

**验收：**

- [ ] 30/30 页有独立、真实、可追溯记录。
- [ ] 任一帧丢失、hash 漂移、reviewer 缺失或 P0/P1 出现均阻断。

---

### T17：冻结 L4 效果验收基线

**依赖：** T16  
**产物：** `EFFECT_ACCEPTANCE_FROZEN`、Task 23/24 stop-points  
**操作：**

- [ ] 将 Task 23 结果、90 帧、Task 24 visual review 和缺陷清单绑定同一 source/sample baseline。
- [ ] 独立重算所有 evidence hash。
- [ ] 验证没有绝对临时路径、断裂引用和跨 run 混用。

**验收：**

- [ ] L4 索引离线可解析，所有引用存在且 hash 一致。

---

### T18：修复 Task 25 RC 全资产校验的假绿缺口

**依赖：** T17  
**产物：** Task 25 verifier 修复提交和防回归测试  
**已知红灯：** 当前 installer hash 匹配，但 education manifest 和 Ground Truth 实际 hash 与 RC 清单不一致；现有 verifier 仍返回 `valid=true`。

**操作：**

- [ ] 先新增测试，证明任一声明资产缺失或 hash 错误时 verifier 必须失败。
- [ ] 校验 `assets.education_manifest`、`assets.ground_truth`、`assets.visual_review` 的实际路径和 SHA-256。
- [ ] 增加声明路径 containment、普通文件、大小和 SHA-256 格式校验。
- [ ] 将 source commit、dirty=false、锁文件/schema hash 和 candidate id 加入 RC 身份。
- [ ] 验证 `v2_enabled=false`；任何默认开启都阻断。
- [ ] 增加跨候选 evidence、路径逃逸、缺引用和部分校验的测试。

**验收：**

- [ ] 当前不一致状态先稳定失败；修复正确资产后才通过。
- [ ] verifier 输出确定的 reason codes，不再只有 installer 校验。

---

### T19：重建单一 Task 25 Windows RC

**依赖：** T18  
**产物：** 新 RC manifest、installer、release artifacts、SBOM/依赖索引  
**操作：**

- [ ] 从 L1—L4 冻结 source commit 的干净快照构建，不从当前脏根目录打包。
- [ ] 生成唯一 `candidate_id=effects-v2-rc-<source_short_sha>-<build_id>`。
- [ ] 构建安装包并记录大小、SHA-256、构建工具和依赖版本。
- [ ] 生成包含所有必需资产的 RC manifest，再由独立 verifier 重算。
- [ ] 历史安装包 `6f6f84a0...` 保留为历史候选；只有其源码和全资产能证明同源时才可复用。
- [ ] 不覆盖旧安装包；新候选写入按 candidate id 隔离的不可变路径。

**验收：**

- [ ] RC manifest、release artifacts 和实际文件完全一致。
- [ ] 同一 candidate 不存在两个不同 installer 或 asset hash 集合。

---

### T20：审计并采用/拒绝现有 Windows 证据

**依赖：** T19  
**产物：** `windows/evidence-audit.json`  
**操作：**

- [ ] 计算 `F:\Video\acceptance-effects-v2\acceptance-evidence.jsonl` 的 SHA-256，逐行验证 schema 和追加写完整性。
- [ ] 检查每条记录的 candidate id、source commit、installer hash、asset hashes、run id、时间和退出码。
- [ ] 验证其是否覆盖安装、启动、隔离、测试、预览、导出、重启、回滚和数据保留。
- [ ] 与 T19 新 RC 身份逐项比较；任何缺字段或不一致都拒绝复用。
- [ ] 记录 `accepted`、`partial_context_only` 或 `rejected`，并给出 reason codes。

**验收：**

- [ ] 历史 Task 26/Pester 结果不再被自动等同于 Task 25 当前 RC 全链通过。

---

### T21：在同一 RC 上执行 Windows 实机验收

**依赖：** T20  
**产物：** Windows 证据包、`WINDOWS_RC_FROZEN`  
**操作：**

- [ ] 在专用 Windows 10/11 环境，以 T19 同一安装包完成全新安装和首次启动。
- [ ] 验证关闭/重开、进程所有权、端口隔离和异常恢复。
- [ ] 使用冻结的 30 页样本完成 preview、动态效果/字幕检查和最终导出。
- [ ] 验证重启恢复、回滚、卸载/重装和用户工作区保留。
- [ ] 验证 V2 默认关闭，只有显式灰度流程可开启。
- [ ] 保存机器信息、阶段日志、截图/视频、产物 hash、人工签署和 reason codes。
- [ ] 运行 RC verifier 并确保所有阶段绑定同一 candidate。

**验收：**

- [ ] 所有必需 Windows 阶段通过，无 P0/P1，证据无缺失/跨候选。
- [ ] 生成 `WINDOWS_RC_FROZEN`；否则保持 `BLOCKED`。

---

### T22：生成总冻结索引和双重复核

**依赖：** T21  
**产物：** `task18-25-freeze-index.json`、`task18-25-acceptance-baseline.json`  
**操作：**

- [ ] 汇总 L0—L5 标记、Task 18—25 提交、所有 evidence locator 和 hash。
- [ ] 验证 source commit、依赖锁、样本、GT、视觉复核、安装包和 Windows evidence 属于同一冻结链。
- [ ] 用第二个独立校验入口从磁盘重算全部 hash 和引用。
- [ ] 对 source manifest、RC manifest 和 freeze index 做交叉引用循环/断链检查。
- [ ] 记录已知警告、P3、豁免、签署人和基线失效条件。

**验收：**

- [ ] 两个校验入口结果一致。
- [ ] freeze index 中不存在 `unknown`、未解决 conflict 或未签署必需项。

---

### T23：创建不可变恢复点并演练回滚

**依赖：** T22  
**产物：** 源码/总基线 checkpoint、回滚演练记录  
**操作：**

- [ ] 创建源码冻结 checkpoint，绑定 L1/L2。
- [ ] 创建总基线 checkpoint，绑定 L0—L5 和 freeze index hash。
- [ ] 从 checkpoint 新建全新 worktree，重复运行轻量校验和关键 contract 测试。
- [ ] 演练回到 Task 18—24 任一 stop-point，不改写历史、不丢失证据。
- [ ] 演练产品回滚：关闭 V2/切换已验证版本，确认不删除 V2 数据和用户项目。

**验收：**

- [ ] checkpoint 可检出，freeze index hash 不变，回滚后关键测试通过。
- [ ] 旧失败、旧 RC 和恢复原件仍可追溯。

---

### T24：最终审计和状态发布

**依赖：** T23  
**产物：** 最终恢复报告、更新后的 implementation status、`TASK18_25_BASELINE_FROZEN`  
**操作：**

- [ ] 逐条核对设计文档的完成定义和本计划所有复选项。
- [ ] 为每个 Task 记录最终提交、来源类型、测试结果、stop-point 和残余风险。
- [ ] 明确区分历史声明、找回原件、合同重建和本次复验结果。
- [ ] 更新 Task 18—25 状态，不回写或篡改旧证据；更正项以追加说明呈现。
- [ ] 仅当 L0—L5 全部通过时发布 `TASK18_25_BASELINE_FROZEN=PASS`。
- [ ] 若原授权样本来源、全资产 RC 或 Windows 实机仍缺失，发布 `BLOCKED` 和精确 reason codes，不降级标准。

**验收：**

- [ ] 任何成员可仅凭仓库内索引和受控证据目录重现来源裁决与验收结论。
- [ ] 正确源码、验收基线、RC、回滚点和未解决风险均有唯一、可审计答案。

## 4. 预期最终文件

```text
docs/acceptance/effects-task18-25-recovery/
├── README.md
├── runs/<run_id>/...
├── stop-points/task-18.json ... task-25.json
├── task18-25-source-manifest.json
├── task18-25-acceptance-baseline.json
└── task18-25-freeze-index.json
```

源码恢复预计影响：

- `apps/api/src/workbench/effects/`
- `scripts/build_effect_rc_manifest.py`
- `scripts/verify_effect_release.py`
- `scripts/windows_effect_acceptance*.ps1`
- `scripts/run_effect_acceptance.py`
- `scripts/render_effect_regression.py`
- `tests/unit/effects/`
- `tests/release/`
- `fixtures/effects/education-v2/`
- `docs/effects/`
- `packages/contracts/openapi.json`

实际实施时只修改经 path ownership 台账批准的文件；与当前其他开发线重叠的文件先做三方比较，不直接覆盖。

## 5. 最终放行清单

- [ ] `PROVENANCE_FROZEN`
- [ ] `SOURCE_FROZEN`
- [ ] `AUTOMATION_FROZEN`
- [ ] `SAMPLE_FROZEN`
- [ ] `EFFECT_ACCEPTANCE_FROZEN`
- [ ] `WINDOWS_RC_FROZEN`
- [ ] `TASK18_25_BASELINE_FROZEN=PASS`

前六项必须全部有可复核 evidence hash；任何一项为 BLOCKED 时，最后一项不得勾选。
