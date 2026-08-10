# M7 Gate：安装与交付

## 结果

M7 Task 32—36 已完成。Linux 容器中的可复现门禁通过；Windows Inno Setup、PowerShell 和干净 VM 实机步骤已提供入口，但当前运行环境不是 Windows，未将脚本静态检查冒充 VM 通过。

当前功能分支：`feature/m7-install-delivery`

## Task 交付

| Task | 交付内容                                                                                              | 提交                 |
| ---- | ----------------------------------------------------------------------------------------------------- | -------------------- |
| 32   | 环境检测、组件版本/磁盘/权限/中文路径检查、脱敏诊断 ZIP、API 与 `doctor.ps1`                          | `bf95816`, `13c12be` |
| 33   | 运行时 artifact/license/SBOM 清单、大小与 SHA-256 校验、PyInstaller spec、发布脚本                    | `fc8ff3d`            |
| 34   | Inno Setup 安装器、当前用户安装、快捷方式、本机启动器、空闲端口、健康检查、重复实例锁、卸载留存       | `265df90`            |
| 35   | stable-only 更新、包哈希/大小/磁盘门禁、设置与索引备份、双目录切换、迁移/健康失败自动回滚、更新设置页 | `c744fe0`            |
| 36   | 中文用户手册、接口配置、排障 code 表、8 页无密钥合成示例项目                                          | `4989e99`            |

契约快照与最终格式修正：`2520ef1`。

## 自动化证据

- Python 全量：`218 passed`
- Ruff：`apps/api/src/workbench tests` 全部通过
- 严格 mypy：`114 source files` 全部通过
- OpenAPI/Schema 契约：快照测试 `9 passed`
- Web：`25 passed`
- Remotion：`5 passed`
- Web/Remotion TypeScript 与生产构建：通过
- `pnpm check`：lint、Prettier、typecheck、tests、build 全部通过
- Playwright：`1 passed`；使用 `PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-m7`
- Task 32—36 专项行为、路由、发布清单、安装器结构、更新回滚和文档测试：全部通过

## 关键安全/恢复检查

- 诊断包只含 `environment-report.json`、Markdown 和说明文件，路径脱敏，不含密钥、认证头或项目源文件正文。
- 发布清单拒绝缺失 artifact、大小/哈希不符、许可证缺失、路径越界和开发密钥残留。
- 启动器只绑定 `127.0.0.1`，使用临时 TCP listener 选择端口，轮询 `/api/health` 后才打开浏览器。
- 安装器使用 `PrivilegesRequired=lowest`；程序安装在 app 子目录，`workspace-data` 位于其外部，卸载不会删除项目与配置。
- 更新只接受 `stable` manifest；下载包校验哈希与大小后才暂存，应用前备份设置和工作区索引。
- 新版本迁移异常、健康检查失败、磁盘不足或哈希不符均阻断或自动回滚；项目目录不参与版本切换。
- 更新设置页的应用动作必须经过用户确认，前端不显示完整本地路径或任何密钥。
- 演示项目为 8 页合成 manifest，可由现有 `ProjectManifest` 校验，不包含真实素材或密钥。

## Windows 实机待执行步骤

在 Windows 10/11 干净 VM 中，使用发布目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/doctor.ps1 -BaseUrl http://127.0.0.1:8000
powershell -ExecutionPolicy Bypass -File tests/release/install-smoke.ps1 -InstallerPath .\release\ppt-video-workbench-setup.exe
powershell -ExecutionPolicy Bypass -File tests/release/update-rollback.ps1 -ApiBaseUrl http://127.0.0.1:8000 -WorkspaceRoot "$env:LOCALAPPDATA\PPTVideoWorkbench\workspace-data"
```

实机验收需覆盖：静默/普通安装、中文用户名、无管理员权限、重复启动、卸载留存数据、N-1→N 成功、哈希失败、下载中断、磁盘不足、健康检查失败自动回滚，以及示例项目打开和导出。

本 Gate 不宣称以上 Windows VM 项目已在当前 Linux 容器执行。
