# Windows 实机验收报告

状态：`Task 26 入口已实现；Windows 隔离门禁待实机执行`

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

Task 26 只有在 Pester、ASCII、隔离路径、端口占用和 PID 所有权全部通过后，才可进入 Task 27。

## 环境

- Windows 版本：
- 安装包版本：
- workbench.exe SHA-256：
- Python/runtime 版本：
- GPU/CPU/内存：
- 执行时间：

## 固定流程

| 步骤 | 结果 | 证据 |
| --- | --- | --- |
| 安装与首次启动 | 待执行 |  |
| 打开既有项目 | 待执行 |  |
| 单页音频、预览和完整预检 | 待执行 |  |
| 批量处理与单页失败隔离 | 待执行 |  |
| 关闭程序后重启恢复 | 待执行 |  |
| 最终合成与导出 | 待执行 |  |
| 关闭 V2 开关后的旧链路回滚 | 待执行 |  |

## 发布完整性

- `verify_effect_release.py`：待执行
- schema/template/migration/解释器/fixture SHA-256：待记录
- 诊断包脱敏检查：待执行

## 未通过项

| 错误码 | 页面/步骤 | 影响 | 处理 | 复测 |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |
