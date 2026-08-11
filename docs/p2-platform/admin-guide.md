# P2 平台管理员指南

## 组织、角色与撤销

Workspace 资源按组织/工作区/项目校验 ownership。无权访问与不存在统一使用 ownership 404，避免 IDOR 泄露。Owner/Admin 可管理成员和 service account；Owner 不能被普通撤销操作移除。

撤销成员、设备或 executor 后应验证：

1. membership generation 或设备状态已更新；
2. 被撤销主体无法继续拉取 operation、解决冲突或读取项目；
3. 活跃 lease/attempt 已按策略释放或到期；
4. 审计记录只有 operation ID、结果、费用和安全详情，不含正文或凭证。

## Provider 策略、区域与预算

组织策略应固定允许的 Provider、能力、模型、数据区域、凭证 scope 和 failover 矩阵。远程 job 必须携带：

- immutable project revision；
- Provider policy SHA-256；
- Provider execution budget 和估算成本；
- runtime image SHA-256；
- capability labels、目标区域和完整 fingerprints。

控制面在排队时拒绝超预算任务；executor 领用前再次校验持久化预算、区域和能力，避免数据库漂移或绕过。结果只有通过 attempt token、hash、schema、media、ownership 和 fingerprint 校验后才发布。

## Executor 运维

Executor 只运行内置任务，不接受任务携带的脚本或插件代码。注册信息包含 OS、GPU、Office、区域、能力快照和 TTL。每次调度或重领生成新的 attempt、lease 和短期最小权限 token；数据库只保存 token hash。

监控至少包括队列延迟、lease 到期、重领次数、失败率、区域无可用 executor、结果拒绝原因和费用偏差。下线 executor 前等待或明确终止活跃 attempt，禁止复用旧 attempt 发布结果。

## Cloud beta 与生产硬门禁

当前 `cloud_prototype` 是 SQLite/WAL 单机原型，不是生产云服务。即使配置 issuer/audience，只要 C12 外部证据不完整，生产模式仍返回 `production_gate_incomplete`；即使证据标记齐全，OIDC 验证适配器未实现时仍返回 501，不能开放流量。

生产发布前必须由真实环境提供并签署：

- PostgreSQL PITR 与恢复演练；
- 对象版本、保留、导出/删除和 legal hold；
- OIDC 签名/issuer/audience、token 和密钥轮换；
- 依赖扫描、SAST、DAST、租户边界渗透与日志脱敏；
- 数据驻留/区域路由、SLO、容量、成本预算、限流和告警；
- executor 崩溃恢复与结果完整性证据。

缺少任一项时，Cloud Sync 只能作为显式 beta/local 功能，不能宣传为生产协作服务。

## 事件处置

发生同步或远程执行事故时，先冻结相关成员/设备/executor，再保存 operation、revision、attempt、lease、fingerprint 和审计 ID。不要复制用户正文、凭证或带签名 URL到工单。恢复后用双设备冲突矩阵、断点续传和结果校验门禁复验。
