# DP40 资源采样器

`workbench.performance.PerformanceSampler` 为性能、压力和长稳验收提供无外部依赖的资源证据。

## 使用方式

```powershell
$env:PYTHONPATH = "apps/api/src"
.\.venv\Scripts\python.exe scripts/performance_sampler.py `
  --output test-results/performance `
  --temporary-root tests/.e2e-workspace `
  --root launcher=1234 --root api=5678 --root worker=9012 `
  --interval 1 --duration 60 --stage render
```

输出目录必须是被忽略的验收结果目录。采样器以独占创建方式写入：一个 session 的 JSONL 或摘要已存在时立即失败，不覆盖旧证据。

## 证据契约

- JSONL 首行是 `session_started`；随后写入 `process_observed`、`stage`、`sample` 与 `session_finished` 事件。
- 每个 `sample` 记录命名根进程及其当前后代，包含 PID、父 PID、`instance_key`（PID 加启动 token）、角色、RSS、CPU、句柄、线程、读写字节和 GPU 内存。
- 不可用指标保持 `null`。当前不依赖供应商 GPU SDK，因此 `gpu_memory_bytes` 明确为 `null` 并附带降级说明，绝不估算。
- 根 PID 未出现时写入 `missing_roots`，汇总中的 `roots_not_observed` 会保留该事实；不会把缺失的 API/Worker/FFmpeg 伪装成零值。
- `temporary` 同时记录磁盘总/已用/可用空间及临时根目录的文件数、文件字节数。摘要给出峰值/最低可用空间。
- 阶段事件使用 `started`、`checkpoint` 与 `finished`，可将导入、预览、页面渲染、合成和制作包阶段关联到采样峰值。

Linux 从 `/proc` 读取指标；Windows 使用 Toolhelp、`GetProcessTimes`、`GetProcessMemoryInfo`、`GetProcessHandleCount` 和 `GetProcessIoCounters`。无法访问的受保护进程只产生空指标，不中止整次验收。

## 已验证边界

- 合成进程树测试验证 launcher → API → FFmpeg 关联、PID 复用拆分为不同 instance、阶段事件和峰值摘要。
- 真实 Windows 短探针验证 JSONL 可逐行解析、摘要可解析，以及 RSS/CPU/句柄/线程/I/O 在当前主机上可采集。
- 性能预算、S8/S50 冷热缓存、长稳和 GPU 运行时 profile 由后续 DP41–DP45 冻结与执行。
