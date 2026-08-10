# S0 外围能力平台

S0 为 PPT Video Workbench 提供独立、可降级的本机任务底座。它只实现统一任务、状态、事件、产物和模块进程协议，不承载后续 P01—P12 业务逻辑。

## 架构边界

- `peripheral_contracts`：冻结的 1.0 跨进程 JSON 契约。
- `peripheral_host`：仅绑定回环地址的 API、SQLite 状态库、调度器和模块运行器。
- `peripheral_modules.echo`：用于验收成功、失败、重试、取消和非法结果的标准模块。
- `workbench_peripheral_adapter`：主程序使用的冻结 DTO 与 HTTP 客户端；不导入主控、数据库或模块代码。
- 主程序通过功能开关接入。外围关闭或停止时，原有视频流程继续运行。

## 开发安装

要求 Python 3.12。

```powershell
uv sync --frozen --all-packages --all-extras --group dev
python -m pytest peripheral-platform/tests -q
```

## 环境变量

| 变量                         | 默认值      | 说明                              |
| ---------------------------- | ----------- | --------------------------------- |
| `PERIPHERAL_ENABLED`         | `false`     | 只有精确值 `true` 才启用外围主控  |
| `PERIPHERAL_HOST`            | `127.0.0.1` | 仅允许 `127.0.0.1` 或 `localhost` |
| `PERIPHERAL_PORT`            | `8765`      | 本机内部 API 端口                 |
| `PERIPHERAL_TIMEOUT_SECONDS` | `3.0`       | 主程序适配客户端超时              |
| `WORKBENCH_WORKSPACE`        | `F:\Video`  | 工作区；不得为盘符根目录          |
| `PERIPHERAL_MIGRATIONS_DIR`  | 随包目录    | 仅用于开发/诊断覆盖迁移目录       |

## 目录规则

初始化脚本创建 `workspace-data`、`projects`、`cache`、`logs`、`diagnostics`、`backups` 和 `quarantine`。数据库为 `workspace-data/peripheral.db`。输入路径必须是工作区内相对路径，拒绝盘符路径、UNC、`..`、保留设备名、ADS、符号链接和重解析点逃逸。产物经大小与 SHA-256 验证后原子发布，已发布版本不可覆盖。

## 接口

外围主控固定提供四类任务接口和一个健康接口：

```text
POST /internal/v1/jobs
GET  /internal/v1/jobs/{job_id}
GET  /internal/v1/jobs/{job_id}/artifacts
POST /internal/v1/jobs/{job_id}/actions
GET  /internal/v1/health
```

主程序在 `/api/peripheral` 下提供对应薄路由和 `/status`。状态为 `disabled`、`available` 或 `degraded`。请求只接受 JSON，请求体上限 1 MiB；发布配置不暴露 OpenAPI、Swagger 或 ReDoc。

## 模块契约

主控向独立模块写入 `JobEnvelope` 请求文件。模块只能在 attempt 目录暂存输出，通过 stdout 输出 `EventEnvelope` NDJSON，并原子写入 `JobResult`。进程退出码 0 不代表成功；主控必须验证结果契约、作业 ID、文件大小和 SHA-256。Echo 支持 `none`、`retryable`、`permanent` 和 `invalid_result` 四种模式。

## 测试与 Windows 构建

```powershell
python -m pytest peripheral-platform/tests/unit -v
python -m pytest peripheral-platform/tests/contract -v
python -m pytest peripheral-platform/tests/security -v
python -m pytest peripheral-platform/tests/integration -v
& '.\peripheral-platform\scripts\build-s0.ps1'
& '.\peripheral-platform\scripts\smoke-s0.ps1' -WorkspaceRoot "$env:TEMP\PPTVideoWorkbench-S0-Smoke"
& '.\peripheral-platform\scripts\verify-s0.ps1'
```

构建产物位于 `dist/release/peripheral`，包括 `peripheral-host.exe`、Schema、迁移、运行清单和 SHA-256 清单。

## 功能开关与降级

默认关闭外围能力。启用时，launcher 先初始化工作区，再启动自己持有的外围进程并最多等待健康检查 10 秒。失败会设置 `PERIPHERAL_DEGRADED=true` 并继续启动主程序。launcher 退出时只终止本次启动所持有的进程 ID，不按进程名清理系统进程。

## 数据库备份、恢复与回滚

每次迁移前自动生成 UTC 时间戳备份。启动时运行 `quick_check` 与外键检查；失败时停止外围写入，不覆盖或重建原数据库。回滚固定执行：

1. 设置 `PERIPHERAL_ENABLED=false`；
2. 停止本次 launcher 持有的外围进程；
3. 保留整个 `F:\Video`，尤其是 `projects`、`backups`、`quarantine` 和已验证产物；
4. 回退主程序与外围二进制和运行清单；
5. 不执行数据库降级 SQL，不向下回滚数据库结构；
6. 启动主程序，检查 `/api/health` 并运行原有标准样例。
