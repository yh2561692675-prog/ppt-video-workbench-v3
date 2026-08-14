# 个人可用闭环基线复核

**状态：** `BASELINE_RECOGNIZED`（不是 RC，不是发布通过）  
**复核日期：** 2026-08-14  
**目标工作树：** `F:\ppt-video-workbench-v3\.worktrees\program-integration-v1`  
**分支：** `codex/program-integration-v1`  
**复核时 HEAD：** `90a4fa311e90531e940ba436453d0e4f36a12457`

## 工作树边界

- `F:\ppt-video-workbench-v3` 是恢复快照且存在脏改动，不作为构建源。
- 本文档只认可上方工作树作为当前集成检查对象；执行后续项目前必须重新读取 HEAD 和 dirty 状态。
- 文档工作树 `personal-use-docs-parallel` 只保存设计/实施文档，不作为产品源。

## 当前证据分级

| 证据 | 当前判断 | 原因 |
|---|---|---|
| DP45 两小时 | `HISTORICAL_PARTIAL_PASS` | 绑定提交 `44705668...`，不是当前 HEAD；不能替代新候选稳定性 |
| DP45 八小时 | `INTERRUPTED` | 进程消失且无完成标记，不得写成通过 |
| Windows 全链路 | `BLOCKED` | runner 仍输出旧的简化 phase，未满足 schema 2.0 完整合同 |
| HeyGen 真实服务 | `WAIT_EXTERNAL` | 当前未绑定真实凭据、额度、voice 和 canary 证据 |
| 同候选安装态 PPT | `MISSING` | 尚无“源提交→安装包→安装态完整 PPT”闭环证据 |
| 人工音画 | `MISSING` | 尚无当前候选最终 MP4 的人工签署 |

## 集成选择规则

1. `program-core-workbench`、字体审计等其他工作树只按提交和语义逐项选择，不整分支盲合并。
2. 影响个人可用主链、RC 正确性、报告绑定、Windows 安装或数据安全的变更列为当前阻断项。
3. 只读字体审计若不影响主链稳定性，可在标准 PPT 暴露字体风险时纳入；否则作为本地可用后的增强项。
4. 任何代码、锁文件、运行时、模板、资源、打包脚本或功能开关变化都会使旧候选证据失效。

## 项目 00 出口

- 唯一认可的集成工作树已确定；
- 历史、部分通过、中断和缺失证据均已标注；
- 后续第一优先级为必要语义集成，然后统一 Windows runner/schema 2.0；
- 本项目不创建 RC，也不宣称稳定可用。

