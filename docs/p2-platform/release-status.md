# P2 平台发布状态与边界

| 能力 | 当前状态 | 可声明范围 | 尚缺证据 |
| --- | --- | --- | --- |
| Provider Kernel | opt-in 实现完成 | 六类统一 descriptor、路由、预算、限流、failover、缓存、审计；已审查上游桥接 | 真实供应商远程/付费签署 |
| PlatformServices Windows | opt-in 兼容层完成 | 路径、进程、凭证、工具、媒体/Office、诊断和发行证据契约 | 正式发行窗口的签名安装/更新/回滚复验 |
| macOS/Linux | 契约与适配基础完成 | 能力矩阵、明确降级、CI 可移植性 | 两个平台真实 8 页 MP4、凭证后端、安装签名 |
| Cloud 合同与单机原型 | beta/local MVP | RBAC、revision、对象、operation、评论/审核/lease、双设备同步、远程 job/executor | PostgreSQL/OIDC/对象存储和 C12 全部生产证据 |
| 三项目集成 | opt-in 门禁 | 独立 flag、共享预算/区域/fingerprint、精确失效、安全诊断、本地资源预算 | 跨平台同项目 + 真实远程 executor 综合签署 |

## 当前发布规则

Provider 和 PlatformServices 仍保持 opt-in，Cloud Sync 保持独立 beta 放量。不得默认开启 Cloud Sync；不得把 SQLite 原型部署为生产控制面；不得把 `CloudProductionEvidence` 布尔值当成证据本身。

本地合成性能预算位于 `docs/acceptance/p2-platform-performance-budget.json`，只用于阻止明显回归。真实 Provider 延迟/费用、三平台媒体性能和生产云 SLO 必须由对应环境生成独立证据。

最新自动化结果记录在 `docs/acceptance/p2-platform-implementation-gate.md`。任何成熟度升级必须同时更新该文件、平台发行矩阵和 Cloud production-readiness gate。
