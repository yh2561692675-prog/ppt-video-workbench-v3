# P2 平台开发者指南

## 组合根与兼容原则

`P2Composition` 是 Provider、PlatformServices 和可选 SyncClient 的唯一组合根。新增代码必须满足：

- 三个 feature flag 可独立组合；全部关闭时旧路径、输出和网络行为不变；
- Provider 通过 PlatformServices 获取持久凭证；Provider 单独启用时只允许非持久内存凭证；
- SyncClient 只保存逻辑对象键、operation 和游标，不把 token、绝对路径或项目正文写入 outbox；
- 新持久化采用兼容迁移，不执行破坏性降级。

## 新增 Provider

1. 添加严格 `ProviderDescriptorV1` 和 capability；未知字段、重复 ID、未知 major 必须失败。
2. 实现 `probe`、`estimate`、`invoke`、`cancel` 和 `normalize_error` 协议。
3. 只允许内置签名或受控本地进程适配器；禁止远程 registry 动态下载代码到主进程。
4. 所有调用携带 operation/idempotency/attempt、deadline、预算和 logical resource ref。
5. cache identity 必须包含 Provider/model/adapter/参数/区域/input/output schema；返回值先进入 staging，验证后原子发布。
6. 添加超时、429、断网、无效响应、未知费用、预算竞争、failover 禁止矩阵和凭证脱敏测试。

真实供应商小额测试独立签署，不进入默认 CI，也不能用 fake 结果代替。

## 新增平台适配器

平台实现必须遵守 `PlatformServices` 协议，进程调用使用参数数组，禁止新增 shell 字符串拼接。路径服务返回逻辑/受控路径；工具探测记录版本/hash/来源；能力缺失返回明确状态，不抛出未经归一化的系统异常。

Windows 行为是当前兼容基线。macOS/Linux 适配器必须分别验证 Unicode 路径、取消、凭证后端、FFmpeg/字体和 Office 降级；只有真实 runner 的 MP4 与安装证据才能提升发布成熟度。

## Cloud API 与迁移规则

- OpenAPI 3.1 是外部契约；每个 runtime route 必须被文档覆盖，每个 mutation 必须有 Idempotency-Key。
- Project revision 不可变；operation 使用 base revision、operation ID、idempotency key 和 client sequence。
- 所有项目对象按 workspace/project ownership 查询；冲突 ID 也不能跨项目解决。
- 迁移文件一经应用不得修改；启动时校验版本和 SHA-256，兼容旧列的升级必须有回归测试。
- 修改 OpenAPI 后运行 `scripts/generate_cloud_client.py` 并提交生成快照。

## 必跑门禁

在隔离集成 worktree 中运行：

```powershell
$py = 'F:\ppt-video-workbench-v3\.venv\Scripts\python.exe'
$env:PYTHONPATH = 'apps/api/src'
$env:WORKBENCH_WORKSPACE = Join-Path $env:TEMP ('p2-gate-' + [guid]::NewGuid().ToString('N'))
& $py -m pytest tests/contract/test_p2_platform_contracts.py tests/contract/test_schema_alignment.py tests/unit/providers tests/unit/platform_foundation tests/unit/cache/test_p2_matrix.py tests/unit/diagnostics/test_p2_privacy.py tests/unit/sync tests/unit/test_p2_composition.py tests/integration/test_p2_opt_in.py tests/integration/test_narration_generation_api.py tests/cloud tests/platform tests/performance/test_p2_platform_budgets.py -q
& $py -m mypy --cache-dir .test-mypy-cache apps/api/src/workbench/p2.py apps/api/src/workbench/contracts/p2_platform.py apps/api/src/workbench/cache apps/api/src/workbench/diagnostics/p2_privacy.py apps/api/src/workbench/platform apps/api/src/workbench/providers apps/api/src/workbench/sync cloud_prototype scripts/generate_cloud_client.py
& $py -m ruff check --no-cache apps/api/src/workbench/p2.py apps/api/src/workbench/contracts/p2_platform.py apps/api/src/workbench/cache apps/api/src/workbench/diagnostics/p2_privacy.py apps/api/src/workbench/platform apps/api/src/workbench/providers apps/api/src/workbench/sync cloud_prototype tests/contract tests/unit/providers tests/unit/platform_foundation tests/unit/cache/test_p2_matrix.py tests/unit/diagnostics/test_p2_privacy.py tests/unit/sync tests/unit/test_p2_composition.py tests/integration/test_p2_opt_in.py tests/integration/test_narration_generation_api.py tests/cloud tests/platform tests/performance/test_p2_platform_budgets.py
& $py scripts/generate_cloud_client.py --check
```

全仓回归的既有失败必须单独记录；不得把已知非 P2 失败或外部证据缺失改写成通过。
