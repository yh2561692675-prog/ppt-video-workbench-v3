# 云端契约失败用例矩阵

本矩阵在 F0 后转化为 Python/TypeScript/OpenAPI contract tests。所有样本使用合成 ID 和内容；禁止复制真实项目、路径或 token。

| ID     | 契约          | 变异                                     | 预期                                 |
| ------ | ------------- | ---------------------------------------- | ------------------------------------ |
| CF-001 | ObjectRef     | `C:\\Users\\name\\file.pptx`             | 拒绝绝对 Windows 路径                |
| CF-002 | ObjectRef     | `/home/name/file.pptx`                   | 拒绝绝对 POSIX 路径                  |
| CF-003 | ObjectRef     | `materials/../secret.txt`                | 拒绝路径穿越                         |
| CF-004 | ObjectRef     | 逻辑路径含反斜杠或 NUL                   | 拒绝非规范路径                       |
| CF-005 | ObjectRef     | 大写/短 SHA-256                          | 拒绝非法摘要                         |
| CF-006 | ObjectRef     | `schema_version: 2`                      | 拒绝未知未来版本                     |
| CF-007 | ObjectRef     | 增加 `local_absolute_path`               | 因未知字段拒绝                       |
| CF-008 | ObjectRef     | `size_bytes < 0` 或超过 1 TiB            | 拒绝越界大小                         |
| CF-009 | Revision      | 重复 parent ID 或超过两个 parent         | 拒绝非法 revision 图                 |
| CF-010 | Revision      | 非 UTC 时间或无 `Z`                      | 拒绝非规范时间                       |
| CF-011 | Revision      | object 引用含未知字段                    | 递归拒绝                             |
| CF-012 | Operation     | `operation_id == attempt_id`             | 语义验证拒绝身份混用                 |
| CF-013 | Operation     | 同幂等键、不同 payload 摘要              | 返回 `409 idempotency_conflict`      |
| CF-014 | Operation     | payload 含 NaN/Infinity                  | canonicalizer 拒绝                   |
| CF-015 | Operation     | 未知 kind                                | schema 拒绝                          |
| CF-016 | Operation     | base revision 不等于 head 且不可合并     | 返回结构化 conflict                  |
| CF-017 | API           | 写请求缺 `Idempotency-Key`               | OpenAPI/服务端返回 422               |
| CF-018 | API           | 跨租户 workspace/project 组合            | ownership 404                        |
| CF-019 | API           | cursor 来自其他租户/列表                 | 拒绝 scope 不匹配 cursor             |
| CF-020 | API           | 超过列表 limit、正文或批量上限           | 返回 413/422/429 的稳定错误          |
| CF-021 | Upload        | 声明摘要与实际字节不符                   | 不创建 ObjectRef，隔离临时对象       |
| CF-022 | Upload        | 过期 URL、换 key/method/size             | 对象存储拒绝                         |
| CF-023 | Download      | 无项目读取权限但已知 object hash         | ownership 404，不泄露存在性          |
| CF-024 | RBAC          | viewer/editor/reviewer 提升成员角色      | 拒绝并写审计                         |
| CF-025 | RBAC          | 成员移除后重放离线 operation             | 拒绝，不因创建时间放行               |
| CF-026 | Lease         | 过期续租、其他 client 续租、TTL 超限     | 拒绝或创建新租约，结果确定           |
| CF-027 | Job           | job 引用非本项目 revision/object         | ownership 404                        |
| CF-028 | Job           | executor 跨 job 读取/写入对象            | 工作负载授权拒绝                     |
| CF-029 | Privacy       | error/log/trace 含 token、正文、绝对路径 | 秘密扫描失败门禁                     |
| CF-030 | Compatibility | 当前 reader 收到未登记 major             | 明确 unsupported version，不静默忽略 |

## Golden fixture 规则

- JSON 源文件使用 UTF-8、LF、结尾换行；字段顺序不构成语义。
- canonicalizer 输出无空白、对象键按规则排序、Unicode NFC、时间 UTC `Z`。
- Python 和 TypeScript 对同一 fixture 的规范化字节与 `sha256:` 摘要完全相同。
- 规范化前先 schema 校验；规范化不负责“修复”未知字段、非法路径、NaN 或未来版本。
- operation payload 摘要只覆盖声明的语义 payload；租户、kind 和目标资源另纳入幂等作用域。
