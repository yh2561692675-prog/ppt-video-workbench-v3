# ADR-003：operation、idempotency 与 attempt 身份

- Status: Accepted
- Date: 2026-08-11
- Supersedes: None

## Context

重试、失败切换、离线同步和远程任务都需要稳定身份。若追踪 ID、去重键和单次尝试 ID 混用，会导致重复计费、错误去重或无法定位具体失败。

## Decision

| 字段              | 生命周期                         | 用途                             |
| ----------------- | -------------------------------- | -------------------------------- |
| `operation_id`    | 一次用户意图从发起到最终结束     | 端到端追踪、审计和状态聚合       |
| `idempotency_key` | 同一副作用请求的语义内容与作用域 | 阻止重复写入、重复付费和重复创建 |
| `attempt_id`      | 每次实际执行或 Provider 调用     | 记录重试、切换、耗时和单次错误   |

规则如下：

1. 三者均使用 UUID 字符串；服务端验证格式但不从 UUID 推断时间或租户。
2. 重试复用 `operation_id` 和 `idempotency_key`，每次生成新的 `attempt_id`。
3. 改变语义输入、目标资源或副作用范围必须生成新的 `idempotency_key`。
4. 去重记录按租户、操作类型和幂等键联合限定，并保存请求摘要；同键不同摘要返回冲突。
5. 错误与日志必须携带 operation/attempt；用户可见输出不得暴露内部凭证或完整正文。

## Consequences

模型和日志字段增加，但 Provider、云同步与远程执行可以共享一致的重试语义。

## Compatibility

旧调用未提供字段时由边界适配器生成；核心层和新 API 不允许缺失。

## Verification

- 同键同摘要重复请求只产生一次副作用。
- 同键不同摘要返回 `409 idempotency_conflict`。
- 失败切换保留 operation，创建不同 attempt，审计链完整。
