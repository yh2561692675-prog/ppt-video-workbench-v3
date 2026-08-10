# S0 G5 验收报告

- 验收日期：2026-08-08（Asia/Singapore）
- 源仓库目标：`F:\ppt-video-workbench-v3`
- 接入快照：`58e98ed6cc15446ac1387fec208612c1f727f2d0`
- 实施分支：`feature/s0-peripheral-platform`

## 门禁结果

| 门禁            | 证据                                                               | 当前结果 |
| --------------- | ------------------------------------------------------------------ | -------- |
| G0 仓库映射     | `docs/superpowers/reports/s0-g0-preflight.md`；基线 254 项通过     | PASS     |
| G1 协议与路径   | 5 份 JSON Schema；契约、路径、哈希与不可变发布测试                 | PASS     |
| G2 状态底座     | SQLite 迁移、事务状态机、事件顺序、`quick_check` 测试              | PASS     |
| G3 独立执行     | Echo 子进程、三次重试、取消、恢复和非法结果测试                    | PASS     |
| G4 主程序接入   | 五条薄路由；关闭/可用/主控停止三态测试                             | PASS     |
| G5 可移植测试   | Linux/Python 最终全仓 374 项通过；Ruff、严格 mypy、compileall 通过 | PASS     |
| G5 Windows 构建 | 当前环境没有 Windows PowerShell/PyInstaller 实机链路               | NOT RUN  |
| G5 Windows 冒烟 | 需在 `F:\ppt-video-workbench-v3` 执行 `verify-s0.ps1`              | NOT RUN  |

## 故障注入矩阵

| 故障              | 自动化证据                                     | 结果 |
| ----------------- | ---------------------------------------------- | ---- |
| 协议 2.0          | 422 `UNSUPPORTED_SCHEMA_VERSION`，数据库零写入 | PASS |
| 输入哈希不匹配    | 422 `ARTIFACT_HASH_MISMATCH`，attempt 零写入   | PASS |
| 路径穿越          | 422 `WORKSPACE_PATH_REJECTED`                  | PASS |
| Echo 永久失败     | 一次 attempt 后 `failed`，错误详情可读         | PASS |
| Echo 可恢复失败   | 5/30 秒退避，第三次后终止                      | PASS |
| 退出 0 但结果非法 | `failed`，制品零登记                           | PASS |
| 运行中取消        | `cancelling` 到 `cancelled`，无 `.tmp` 残留    | PASS |
| 主控运行中被杀    | 启动恢复到 `retry_wait`                        | PASS |
| SQLite 不可用     | 内部 API 503 且不泄露 SQL/路径                 | PASS |
| 外围端口不可达    | 主程序 `degraded`，`/api/health` 仍为 200      | PASS |
| Bearer 注入       | 日志只保留 `***`                               | PASS |

## 安全结果

- 仅允许 loopback 主控地址；适配器也拒绝非 loopback URL。
- 写接口仅接受 `application/json`，请求体最大 1 MiB，冲突 Content-Length 返回 400。
- 无任意来源 CORS；`/docs`、`/redoc`、`/openapi.json` 均关闭。
- 错误体不包含绝对路径、SQL、堆栈或模块 stderr。
- 日志对敏感键、Bearer、Windows 用户目录和 `parameters.text` 脱敏。

## Windows 完成命令

```powershell
Set-Location 'F:\ppt-video-workbench-v3'
git switch feature/s0-peripheral-platform
powershell -ExecutionPolicy Bypass -File '.\peripheral-platform\scripts\verify-s0.ps1'
```

期望末尾为：

```text
UNIT_TESTS=PASS
CONTRACT_TESTS=PASS
SECURITY_TESTS=PASS
INTEGRATION_TESTS=PASS
DATABASE_QUICK_CHECK=ok
DATABASE_FOREIGN_KEY_ERRORS=0
PACKAGE_MANIFEST=PASS
WINDOWS_SMOKE=PASS
S0_ACCEPTANCE=PASS
```

## 发布结论

当前结论：`BLOCKED_PENDING_WINDOWS_G5`。代码、跨平台测试和静态发布门禁已完成；在 Windows 构建、清单哈希、健康检查、Echo 冒烟和进程清理全部实际通过前，不进入 S1 发布。
