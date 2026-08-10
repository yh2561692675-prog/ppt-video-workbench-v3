# RC1 真实项目验收报告

## 当前状态

`pending_manual_windows`

本报告模板已冻结，但当前没有 Windows 10/11 干净 VM、真实 Office 文件、真实用户声音、受控 HeyGen 小额凭证或人工视听记录。因此不能签署 RC1，也不能创建 `v1.0.0` tag。Linux 自动化结果见 [M8-GATE.md](../M8-GATE.md)；任务和需求映射见 [traceability.xlsx](traceability.xlsx) 与 [验收计划](../tests/acceptance/acceptance-plan.md)。

## 环境与前置条件

| 项目                                 | 结果                 | 证据                                                  |
| ------------------------------------ | -------------------- | ----------------------------------------------------- |
| Windows 10/11 干净 VM 或目标用户电脑 | 待执行               | `tests/acceptance/results/RC1/evidence-manifest.json` |
| RC 安装器、启动器和卸载              | 待执行               | `tests/release/install-smoke.ps1`                     |
| 真实 Word+PPTX                       | 待执行               | `results/RC1/RC-LOCAL/`                               |
| 真实 Word+扫描 PDF                   | 待执行               | `results/RC1/RC-SCAN/`                                |
| 真实 Word+多图片                     | 待执行               | `results/RC1/RC-IMAGES/`                              |
| 2 页真实声音                         | 待执行且需要受控额度 | `results/RC1/RC-HEYGEN/`                              |
| 人工视听检查                         | 待执行               | `results/RC1/RC-AUDIOVISUAL/`                         |

## 完整制作包

真实项目通过后，必须在 `RC-LOCAL/output/` 记录以下全部产物，并在 `evidence-manifest.json` 填入实际路径、SHA-256 和截图：

- MP4；
- SRT；
- 旁白 DOCX；
- 分页音频；
- Remotion 工程；
- 配置；
- 预检报告；
- 日志；
- SHA-256 清单。

## 场景结果

| 场景           | 期望                                             | 当前结果                 |
| -------------- | ------------------------------------------------ | ------------------------ |
| RC-LOCAL       | Word+PPTX、本地录音、无需命令行完成导出          | `pending_manual_windows` |
| RC-SCAN        | 扫描 PDF OCR 低置信度可定位、可人工修正          | `pending_manual_windows` |
| RC-IMAGES      | 多图片自然排序和人工调整生效                     | `pending_manual_windows` |
| RC-HEYGEN      | 2 页真实声音不重复计费，缓存和费用可追溯         | `pending_manual_windows` |
| RC-RECOVERY    | OCR/转写/声音/渲染暂停或关闭后可恢复             | `pending_manual_windows` |
| RC-AUDIOVISUAL | 音画、字幕、裁切、爆音、静音、错页和核心内容通过 | `pending_manual_windows` |

## 缺陷与签署

当前 P0、P1、P2、P3 均为 `not_assessed`。完成真实验收后，逐条记录严重度、复现步骤、修复提交和回归证据；只有 P0=0、P1=0、P2 有明确处置且所有核心场景通过，才可将 `signed` 改为 `true`。

## Windows 执行命令

```powershell
Set-Location "F:\ppt-video-workbench"

# 首次构建机准备：安装 uv、Node.js LTS（提供 Corepack）和 Inno Setup 6 后，
# 关闭并重新打开 PowerShell，再执行以下两行。
corepack enable
corepack prepare pnpm@11.7.0 --activate

powershell -ExecutionPolicy Bypass -File scripts/build-release.ps1
powershell -ExecutionPolicy Bypass -File tests/release/install-smoke.ps1 -InstallerPath .\release\ppt-video-workbench-setup.exe

# 冒烟脚本会卸载；随后手工安装一次，并从开始菜单启动 PPT Video Workbench。
Start-Process .\release\ppt-video-workbench-setup.exe -Wait

# 浏览器已由快捷方式打开且应用保持运行后，端点会被自动发现。
powershell -ExecutionPolicy Bypass -File scripts/doctor.ps1
```

更新/回滚验收需要一份受控的 N-1→N stable 更新包和对应
`stable-manifest.json`。该测试材料准备完毕后，在应用仍运行时执行：

```powershell
powershell -ExecutionPolicy Bypass -File tests/release/update-rollback.ps1 -WorkspaceRoot "$env:LOCALAPPDATA\PPTVideoWorkbench\workspace-data"
```

执行完成后，把截图、机器报告和导出包放入 RC1 证据目录，更新 manifest，再运行完整 M8 Gate。
