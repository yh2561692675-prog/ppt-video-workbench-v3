# P2 平台基础 ADR 索引

本目录记录多供应商适配、跨平台基础层和云端协作控制面共同依赖的架构决策。状态为 `Accepted` 的 ADR 是实现约束；修改约束必须新增 ADR 并通过 `Supersedes` 关系替代，禁止直接改写既有结论。

| ADR                                                           | 主题                                 | 状态     |
| ------------------------------------------------------------- | ------------------------------------ | -------- |
| [ADR-001](ADR-001-local-first-cloud-optional.md)              | 本地优先、云端可选                   | Accepted |
| [ADR-002](ADR-002-provider-adapter-trust.md)                  | Provider adapter 信任边界            | Accepted |
| [ADR-003](ADR-003-operation-id-idempotency-attempt.md)        | operation、idempotency、attempt 身份 | Accepted |
| [ADR-004](ADR-004-canonical-json-versioning.md)               | 规范化 JSON、哈希与版本兼容          | Accepted |
| [ADR-005](ADR-005-content-addressed-objects-logical-paths.md) | 内容对象与逻辑路径                   | Accepted |
| [ADR-006](ADR-006-cloud-operation-log-immutable-revisions.md) | 操作日志与不可变修订                 | Accepted |
| [ADR-007](ADR-007-platform-services-composition-root.md)      | PlatformServices 组合根              | Accepted |

## 必填元数据

每份 ADR 必须包含 `Status`、`Date`、`Supersedes`、`Context`、`Decision`、`Consequences`、`Compatibility` 和 `Verification`。`Supersedes` 无前序决策时写 `None`。
