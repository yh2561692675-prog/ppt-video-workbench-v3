# P2 平台用户指南

## 默认行为

三个开关默认全部关闭：

- `PROVIDER_PLATFORM_ENABLED`：启用统一 Provider 列表、能力、预算和调用入口。
- `PLATFORM_SERVICES_ENABLED`：启用平台路径、进程、凭证、工具和能力探测。
- `CLOUD_SYNC_ENABLED`：启用独立 SQLite WAL outbox/inbox；不会自动上传已有项目。

开关可以独立组合。关闭全部开关时，不创建同步数据库、不发起网络请求，也不改变原项目输出。

## Provider、费用与隐私

Provider 页面展示能力、健康状态和费用估算。执行前确认以下信息：

1. 所需能力、语言、模型和数据区域均匹配；
2. 估算费用不超过本次、项目、每日和组织预算；
3. 需要自动切换时，候选 Provider 没有扩大区域、提升预算或越过人工锁定；
4. 凭证只以 `credential_ref` 引用，项目文件、日志、诊断包和同步内容中不含明文密钥。

费用未知、区域扩大、预算提升或人工锁定时，系统会阻止自动 failover。付费重试复用 operation/idempotency/attempt 语义，避免因断网或重启重复扣费。

## 平台能力与降级

平台能力报告区分 `supported`、`missing`、`misconfigured`、`temporarily_unavailable` 和 `unsupported`。能力缺失不会静默改写项目 revision：

- Windows 可使用受支持的 PowerPoint/FFmpeg 等链路；
- macOS/Linux 的 Office、硬件编码和安装签名仍需真实 PoC/发行证据；
- 缺少 PowerPoint 时应显示明确降级，不把 CI 探测当成等价渲染结果。

## 云端同步状态

- `local_only`：仅本地，尚未选择上传。
- `syncing`：outbox 中有待确认或可重试操作。
- `synced`：服务端已确认并推进游标。
- `conflict`：同一对象发生结构化冲突，需要人工处理。

断网、token 过期和服务端 5xx 不会删除未确认操作。不同对象的离线编辑可自动合并；同一 clip、资产、删除/修改或页面顺序竞争会生成冲突。人工解决可选择保留远端、应用本地或提交合并内容，并必须针对当前 head revision。

设备或成员被撤销后，后续拉取/提交会被拒绝。本地 outbox 仍保留，便于管理员确认后导出或处理，不会伪装为已同步。

## 安全诊断导出

`GET /api/p2/diagnostics/export` 只导出安全摘要。可重复传入 `sections` 选择 `flags`、`platform`、`platform_details`、`providers`、`sync`、`cloud` 或 `executor`。导出前再次扫描 API Key、token、Authorization、Cookie、正文、邮箱和绝对路径，只返回 finding code，不回显敏感值。

## 回退

关闭对应开关即可停止使用新路径。回退不会执行破坏性数据库降级，也不会删除 Provider 状态、平台派生记录或同步 outbox。确认不再需要数据后，再按管理员保留策略处理。
