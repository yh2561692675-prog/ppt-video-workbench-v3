# DP41 性能预算与启动基线

DP41 提供版本化、不可覆盖的性能预算契约；它将性能证据固定绑定到干净
candidate、输入 fixture、缓存模式和并发度。预算有两种状态：`proposed` 和
`approved`。只有具名工程负责人通过 `freeze` 子命令审核后才可转为
`approved`；本阶段生成的首份记录刻意保持 `proposed`。

## 契约与操作入口

- JSON Schema：[performance-budget-v1.schema.json](../../schemas/performance-budget-v1.schema.json)。
- Python 契约：`workbench.performance.budget.PerformanceBudgetV1`。
- 资源采样：`scripts/performance_sampler.py`（DP40）。
- 启动采样：`scripts/performance_startup_probe.py`。该命令只跟踪 API 根，
  不会把辅助进程冒充 Windows 产品启动器或计入产品组件聚合。
- 预算工具：`scripts/performance_budget.py propose|freeze`。它先校验
  candidate manifest 和当前 checkout，再接受采样摘要与 JSONL；任何哈希、
  session 边界、输出冲突或候选不一致都会失败。

固定指标集为 `startup_to_health`、`import`、`preflight`、`preview`、
`page_render`、`mux`、`package`。未执行的阶段明确写作 `not_observed`，
不会由历史恢复结果或零值代替。默认阈值为阶段回退不超过 20%、长稳 RSS
增长不超过 15%、禁止 OOM、最小可用磁盘 5 GiB、孤儿进程及未发布临时文件
均为 0。

## 干净候选基线规则

每次基线都必须先在没有已跟踪或未跟踪变更的 checkout 创建 candidate，再将
sampler JSONL、summary 和预算草案放入该 candidate 专属、被 Git 忽略且不可覆盖
的 `test-results/performance-candidates/<candidate-id>/performance/` 目录。验收停点
必须记录 candidate、fixture、主机 profile、实际测量值和三个证据文件的 SHA-256。

首个候选只生成 `proposed` 基线，不会声称已完成导入、预检、渲染、合成、S8
冷热缓存、S50 或长稳压力；这些工作分别属于 DP42-DP45。GPU 探针不受支持时，
GPU memory 必须为 `null` 并说明原因，绝不能填写猜测值。

## 审核冻结步骤

工程负责人应在同一干净 checkout 复核候选及证据哈希后执行：

```powershell
$env:PYTHONPATH = (Resolve-Path 'apps/api/src').Path
.\.venv\Scripts\python.exe scripts/performance_budget.py freeze `
  --candidate <candidate-manifest.json> --repo-root . `
  --input <performance-budget-v1-proposed.json> `
  --output <performance-budget-v1.json> --reviewer <engineering-owner>
```

该命令不覆盖已有输出；审批人的名字、时间和 candidate binding 均写入新文件。
