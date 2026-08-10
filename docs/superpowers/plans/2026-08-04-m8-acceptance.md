# M8 实机验收实施计划

## 约束

- 分支：`feature/m8-acceptance`，从 M7 合并提交 `e488a95` 创建。
- 顺序：Task 37 → Task 38 → Task 39 → Task 40 → M8 Gate。
- 不暂存用户现有 `.gitignore`、`PROJECTS.md`、`docs/superpowers/plans/2026-08-03-integrate-volunteer-ai-mvp.md`、`projects/`。
- Windows VM、真实 HeyGen 和人工视听没有在当前容器中伪造执行结果。

## Task 37：验收数据集与需求追踪

**文件：**

- Create `tests/acceptance/fixtures-manifest.json`
- Create `tests/acceptance/acceptance-plan.md`
- Create `docs/traceability.xlsx`
- Create `tests/acceptance/test_traceability.py`
- Create `scripts/build-traceability.mjs`

**步骤：**

1. 先测试需求编号完整、验收 ID 无孤立、fixture 类型覆盖和 evidence 路径非空。
2. 建立合成/人工 fixture 清单，区分 Linux 可执行、Windows 待执行和真实凭证禁止自动执行的场景。
3. 使用表格工作流生成带 Summary、Traceability、Fixtures 三个工作表的可筛选矩阵，并渲染检查可读性。
4. 提交 `test: establish V1 acceptance and traceability baseline`。

## Task 38：自动化与非功能

**文件：**

- Create `tests/e2e/full-local-audio.spec.ts`
- Create `tests/e2e/full-heygen.spec.ts`
- Create `tests/performance/test_acceptance_budgets.py`
- Create `tests/security/test_m8_release_security.py`
- Create `tests/acceptance/test_automation_inventory.py`
- Modify `playwright.config.ts` only if needed for explicit M8 project labels

**步骤：**

1. 先写本地音频、fake HeyGen、缓存/失败页/安全/中文路径/磁盘约束测试。
2. 将已有 M4/M5/M6 集成证据映射进验收报告，不重复构造真实付费调用。
3. 运行 Python、Web、Remotion、Playwright；所有 Windows-only 用例输出清晰待执行原因。
4. 提交 `test: add RC automation and nonfunctional acceptance coverage`。

## Task 39：真实项目验收记录

**文件：**

- Create `tests/acceptance/results/RC1/README.md`
- Create `tests/acceptance/results/RC1/evidence-manifest.json`
- Create `docs/acceptance-report-RC1.md`

**步骤：**

1. 先测试报告状态、产物清单、P0/P1/P2 和签署字段不能缺失。
2. 写入真实 Word/PPTX、扫描 PDF、多图片、本地录音、2 页真实声音、暂停/恢复和人工视听的执行模板。
3. 在非 Windows 容器只登记 `pending_manual_windows`，不得写入通过结果。
4. 提交 `docs: prepare RC1 real-project acceptance record`。

## Task 40：RC 修复与 V1.0 冻结

**文件：**

- Create `CHANGELOG.md`
- Create `docs/release-notes-v1.0.md`
- Create `docs/acceptance-signoff-v1.0.md`
- Create `tests/release/test_release_freeze.py`
- Create `scripts/freeze-release.ps1`

**步骤：**

1. 测试冻结脚本会拒绝未签署 Windows 报告、P0/P1 缺陷和缺产物。
2. 生成 RC release notes 和当前已验证范围，不创建未满足条件的 v1.0 tag。
3. 运行 M8 Gate，记录自动化证据与实机阻塞，并提交 `release: freeze RC evidence for v1.0`。

## M8 Gate

运行全量 Python/Web/Remotion/契约/Playwright，检查 traceability、fixtures、报告、发布物和敏感信息；最终写 `M8-GATE.md`。若 Windows 实机证据仍缺失，Gate 结果为 `RC candidate — manual sign-off pending`，并保留下一步执行命令。
