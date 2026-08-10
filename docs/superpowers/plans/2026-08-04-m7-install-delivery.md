# M7 安装与交付实施计划

## 执行约束

- 分支：`feature/m7-install-delivery`，从 M6 合并基线 `713f25c` 创建。
- 顺序：Task 32 → 33 → 34 → 35 → 36 → M7 Gate。
- 每个 Task 先写红灯测试，再写最小实现；每次提交只包含对应任务和必要契约快照。
- 不暂存用户现有 `.gitignore`、`PROJECTS.md`、`docs/superpowers/plans/2026-08-03-integrate-volunteer-ai-mvp.md`、`projects/`。

## Task 32：环境检测与诊断包

**文件：**

- Create `apps/api/src/workbench/environment/detector.py`
- Create `apps/api/src/workbench/api/environment.py`
- Create `scripts/doctor.ps1`
- Create `tests/unit/environment/test_detector.py`
- Create `tests/integration/test_environment_routes.py`
- Modify `apps/api/src/workbench/main.py`

**步骤：**

1. 测试缺失组件、版本不兼容、权限/磁盘/中文路径失败、诊断包脱敏和 API 响应。
2. 实现探针注入、稳定 check code/action、报告 JSON/Markdown 和 ZIP 原子写入。
3. 接入 `/api/environment` 与 `/api/environment/diagnostic-package`，不自动安装或读取源文件正文。
4. 运行专项测试、Ruff、严格 mypy、契约导出并提交 `feat: detect and diagnose Windows runtime`。

## Task 33：发布运行时清单

**文件：**

- Create `apps/api/src/workbench/release/manifest.py`
- Create `installer/runtime-manifest.json`
- Create `apps/api/workbench.spec`
- Create `scripts/build-release.ps1`
- Create `tests/release/test_runtime_manifest.py`

**步骤：**

1. 写文件缺失、哈希不符、许可证缺失、路径越界和开发密钥残留红灯测试。
2. 实现 canonical manifest、artifact hash/size 校验、SBOM/许可证索引和发布目录验证。
3. 写 Windows 构建脚本和 PyInstaller spec；Linux 门禁执行 `--verify`。
4. 提交 `build: create reproducible Windows release bundle`。

## Task 34：安装与启动

**文件：**

- Create `installer/workbench.iss`
- Create `scripts/launcher.ps1`
- Create `tests/release/test_launcher_contract.py`
- Create `tests/release/install-smoke.ps1`

**步骤：**

1. 测试 launcher 的本机绑定、空闲端口、health 等待、重复实例和敏感参数过滤。
2. 实现 Inno Setup 安装/卸载策略、快捷方式和 launcher。
3. 在可用环境执行脚本结构门禁；记录 Windows VM 待执行命令，不虚报实机通过。
4. 提交 `build: add one-click Windows installer and launcher`。

## Task 35：更新、备份与回滚

**文件：**

- Create `apps/api/src/workbench/updates/service.py`
- Create `apps/api/src/workbench/api/updates.py`
- Create `apps/web/src/features/settings/update/UpdatePanel.tsx`
- Create `apps/web/src/features/settings/update/UpdatePanel.test.tsx`
- Create `tests/unit/updates/test_update_service.py`
- Create `tests/integration/test_update_routes.py`
- Create `tests/release/update-rollback.ps1`
- Modify `apps/api/src/workbench/main.py`, `apps/web/src/api/client.ts`, `apps/web/src/app/router.tsx`

**步骤：**

1. 写 stable-only、签名/哈希失败、下载中断、磁盘不足、健康失败、迁移失败和旧项目不变测试。
2. 实现 staged package 校验、配置/索引备份、双目录切换、health gate 和自动 rollback。
3. 接入 API 与设置页，用户确认后才 apply；测试不得触发真实外网下载。
4. 提交 `feat: add confirmed stable updates with rollback`。

## Task 36：手册与示范项目

**文件：**

- Create `docs/user-guide.md`
- Create `docs/api-setup.md`
- Create `docs/troubleshooting.md`
- Create `examples/demo-project/README.md`
- Create `examples/demo-project/project.json`
- Create `tests/docs/test_documentation_links.py`

**步骤：**

1. 写错误 code、GUI 路径、示范项目清单和敏感信息扫描红灯测试。
2. 编写安装、七步流程、接口、预检、恢复、缓存、更新和回滚文档。
3. 添加无密钥 6—8 页 demo manifest 与预期产物清单，不复制用户源文件。
4. 提交 `docs: deliver user guide and demonstration project`。

## 最终 Gate

运行：

- `UV_CACHE_DIR=/tmp/uv-cache-m7 uv run pytest -q`
- `UV_CACHE_DIR=/tmp/uv-cache-m7 uv run ruff check apps/api/src/workbench tests`
- `UV_CACHE_DIR=/tmp/uv-cache-m7 uv run mypy apps/api/src/workbench`
- `UV_CACHE_DIR=/tmp/uv-cache-m7 uv run python scripts/export_contracts.py`
- `pnpm check`
- `PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-m7 pnpm exec playwright test`
- Windows 可用时执行 `scripts/doctor.ps1`、`tests/release/install-smoke.ps1`、`tests/release/update-rollback.ps1`。

最终写 `M7-GATE.md`，记录五项任务提交、诊断脱敏、发布清单、安装/launcher 契约、N-1→N 回滚矩阵、文档/示范项目证据和 Windows VM 环境限制。
