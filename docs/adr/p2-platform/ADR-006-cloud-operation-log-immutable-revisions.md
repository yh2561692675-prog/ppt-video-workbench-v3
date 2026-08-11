# ADR-006：云端操作日志与不可变修订

- Status: Accepted
- Date: 2026-08-11
- Supersedes: None

## Context

跨设备离线编辑、审核和回退需要可重放历史。直接同步可变数据库行会产生覆盖丢失、难以审计和版本回退不可靠的问题。

## Decision

1. 项目内容以不可变 `ProjectRevision` 表示；发布新内容只能创建新 revision，不修改旧 revision。
2. 客户端提交追加式 `SyncOperation`，包含 `base_revision_id`、operation 身份、规范化 payload 和客户端顺序。
3. 服务端验证权限、幂等和基线后，原子追加操作并生成新 revision；项目 head 通过比较交换推进。
4. 非重叠可交换操作可自动合并；同字段、页序、删除/修改等语义冲突必须产生显式 conflict，不使用最后写入获胜掩盖数据丢失。
5. 评论、审核和租约属于控制面资源，引用 revision 或对象，不写入其不可变内容。
6. 删除采用 tombstone 和保留期；审计日志追加且受访问控制，不能被普通项目删除覆盖。

## Consequences

需要 outbox/inbox、合并器、快照和压缩策略；获得离线重放、审计、回退和双设备一致性基础。

## Compatibility

首次同步把当前本地项目生成 genesis revision。旧客户端只能访问其声明支持的 schema 版本。

## Verification

- 操作乱序、重复、断线重放与并发 head 更新测试可重复。
- 已提交 revision 的内容哈希不可通过 API 改写。
- 冲突保留双方输入并可由新 operation 解决。
