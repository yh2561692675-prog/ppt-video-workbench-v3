# Windows 发布稳定性基线

**建立日期：** 2026-08-11  
**基线类型：** 现状记录，不代表发布放行  
**后续入口：** `docs/superpowers/plans/2026-08-11-windows-release-stability-and-full-chain-acceptance.md`

## 当前观察

- 现有 `tests/release/windows-acceptance.ps1` 只覆盖 install、first launch、restart、uninstall 和 workspace retention。
- `apps/api/src/workbench/effects/rc_manifest.py` 曾直接拼接 `release/ppt-video-workbench-setup.exe`，无法表达自定义输出目录，这是 `installer_not_found` 需要从产物清单边界解决的原因。
- 默认安装快捷方式仍直接调用 PowerShell launcher；黑色窗口生命周期和 API 生命周期耦合。
- 2026-08-11 当前工作区复跑 `pnpm --filter @workbench/web test -- --reporter=verbose`：38 个测试文件、74 个测试项通过。该结果未绑定冻结候选和不可变证据包，不作为发布签署。

## 历史前端失败索引

来源：`web-vitest-error.log`，原始日志保留在工作区，以下只记录定位信息。

| 文件                                                    | 历史失败测试                                                                            |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `apps/web/src/features/workflow/WorkflowShell.test.tsx` | immediately disables HeyGen after local import even while project refetch remains stale |
| `apps/web/src/features/workflow/WorkflowShell.test.tsx` | disables local import when a HeyGen batch starts and keeps it disabled after success    |
| `apps/web/src/features/workflow/WorkflowShell.test.tsx` | restores the HeyGen route from completed page audio after a project reload              |

历史记录结论为 1 个测试文件、3 个测试项失败；当前复跑已通过，待冻结候选上按 T07 执行首轮与 3 次独立进程稳定性门禁后才能关闭。

## 候选身份规则

正式候选使用：

```text
candidate_id = rc-<short-git-commit>-<UTC-build-id>
```

候选必须同时记录：

- Git commit 和 dirty 状态；
- `uv.lock`、`pnpm-lock.yaml` 和 runtime manifest SHA-256；
- Windows 构建机、Node/pnpm、Python/uv、PyInstaller、Inno Setup 版本；
- `release-artifacts.json` 的 SHA-256；
- 每次验收的独立 `run_id`。

## 放行前置

本基线不改变现有发布状态。新候选必须完成 T01-T15，并由 schema 2.0 Windows 全链路报告消费；缺少实机 A0-A9 证据时保持 `pending_manual_windows`。
