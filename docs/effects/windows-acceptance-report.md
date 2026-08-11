# Windows 实机验收报告

状态：`Task 26 隔离门禁通过；完整产品功能流程仍待人工实机执行`

## Task 26 隔离门禁

- 入口脚本：`scripts/windows_effect_acceptance.ps1`
- ASCII helper：`scripts/windows_effect_acceptance_lib.ps1`
- 证据文件：隔离工作区内的 `acceptance-evidence.jsonl`
- 正式数据库：禁止接触；验收数据库必须位于 `WorkspaceRoot\workspace.db`
- 安装目录：必须位于独立的 `InstallRoot`，不得覆盖现有正式安装目录
- RC：继续使用 Task 25 冻结的同一安装包，不重新构建、不替换同名制品

Windows 执行命令：

```powershell
Set-Location 'F:\ppt-video-workbench-v3'
Invoke-Pester .\tests\release\windows-effect-isolation.Tests.ps1
.\scripts\windows_effect_acceptance.ps1 `
  -Root 'F:\ppt-video-workbench-v3' `
  -InstallRoot 'F:\PPTVideoWorkbench-Acceptance\app' `
  -WorkspaceRoot 'F:\Video\acceptance-effects-v2' `
  -ProductionDatabasePath 'F:\Video\workspace.db' `
  -RunTests
```

Task 26 已满足 Pester、ASCII、隔离路径、端口占用和 PID 所有权门禁；后续只剩安装后产品功能流程的人工验收。

本次实际证据：

- Pester 3.4：7/7 passed；验收脚本兼容 Pester 3.4/5 的断言语法。
- `windows_effect_acceptance.ps1 -RunTests`：后端 598 passed，Web 74 passed，Remotion 28 passed，类型检查通过。
- RC 完整性：`effects-v2-rc1-20260811-full-ffmpeg`，`verify_effect_release.py` 返回 `valid=true`、`reason_codes=[]`。
- 证据文件：`F:\Video\acceptance-effects-v2\acceptance-evidence.jsonl`。

## 环境

- Windows 版本：Windows PowerShell 5.1；CIM 查询受当前权限限制，未写入猜测值
- 安装包版本：`effects-v2-rc1-20260811-full-ffmpeg`
- 安装包 SHA-256：`6f6f84a06b76a0f4638d767496de388b12251c2539de543849a42453c5b04d6d`
- workbench.exe SHA-256：`734b9152a7cb534f61f952952c79fec9578d04b0e1e8ea829c84544dc14b5ffd`
- Python/runtime 版本：Python 3.12.13（uv `.venv`）；FFmpeg `9.0-full_build-www.gyan.dev`
- GPU/CPU/内存：未记录（CIM 权限限制）
- 执行时间：2026-08-11

## 固定流程

| 步骤                       | 结果   | 证据                          |
| -------------------------- | ------ | ----------------------------- |
| 安装与首次启动             | 待执行 | Task 26 仅完成隔离/完整性回归 |
| 打开既有项目               | 待执行 |                               |
| 单页音频、预览和完整预检   | 待执行 |                               |
| 批量处理与单页失败隔离     | 待执行 |                               |
| 关闭程序后重启恢复         | 待执行 |                               |
| 最终合成与导出             | 待执行 |                               |
| 关闭 V2 开关后的旧链路回滚 | 待执行 |                               |

## 发布完整性

- `verify_effect_release.py`：通过，`valid=true`、`reason_codes=[]`
- schema/template/migration/解释器/fixture SHA-256：已由 RC 清单登记并校验
- 诊断包脱敏检查：待执行

## 未通过项

| 错误码 | 页面/步骤 | 影响 | 处理 | 复测 |
| ------ | --------- | ---- | ---- | ---- |
|        |           |      |      |      |
