# ADR-007：PlatformServices 组合根

- Status: Accepted
- Date: 2026-08-11
- Supersedes: None

## Context

当前平台判断、路径、凭证、工具发现和进程启动分散在模块与脚本中。若直接增加 macOS/Linux 分支，业务层会持续累积平台条件。

## Decision

1. 定义 `PlatformServices` 聚合协议，至少包含 paths、files、processes、credentials、tools、browser、media、office、updates 和 diagnostics。
2. 只有应用 composition root 根据探测到的平台构造具体实现；领域服务通过构造参数接收协议，禁止读取全局单例。
3. Windows adapter 第一阶段只包装现有行为，以基线输出等价为门禁；随后实现 macOS/Linux adapter。
4. `PlatformServices` 返回结构化能力和错误，不让业务层解析操作系统错误文本。
5. 每个子协议提供 fake 实现；测试不得依赖真实注册表、钥匙串、Office、浏览器或系统目录。
6. 新增 `sys.platform`、`os.name`、硬编码系统路径或 shell 拼接只允许出现在平台 adapter、composition root 或明确列入审计白名单的打包脚本。

## Consequences

迁移期会有旧调用和 adapter 并存，但平台分支可被收口并独立测试，业务服务可以跨平台复用。

## Compatibility

功能开关关闭时使用 legacy composition；开启 Windows adapter 时必须通过相同 fixtures 和端到端输出比较。

## Verification

- 静态检查阻止业务目录新增平台分支。
- fake services 覆盖成功、缺能力、超时、权限不足和取消。
- Windows 开关前后 8 页/50 页基线产物哈希或允许差异清单一致。
