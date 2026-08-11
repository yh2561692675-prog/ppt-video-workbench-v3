# ADR-002：Provider adapter 信任边界

- Status: Accepted
- Date: 2026-08-11
- Supersedes: None

## Context

多供应商能力需要统一适配 LLM、TTS、ASR、OCR、数字人和渲染器。与此同时，模板工作台现有安全边界禁止执行第三方代码，不能借 Provider 插件机制绕过该限制。

## Decision

1. 第一阶段 adapter 是随应用发布、经过代码审查和签名的受信代码，不支持从模板、项目包或市场动态加载 Python/JavaScript/二进制代码。
2. Provider 配置只允许声明端点、模型、能力、限额和策略；声明文件不得包含可执行表达式、shell 或任意导入路径。
3. 外部进程 Provider 只能经 `PlatformServices.processes` 启动，使用参数数组、超时、资源限制、工作目录白名单和脱敏日志。
4. 凭证只能通过 `PlatformServices.credentials` 读取；adapter 不接触操作系统密钥库实现细节，不把密钥写入缓存、项目或诊断包。
5. 未知 provider、能力或 schema 版本必须拒绝，不能静默降级为任意执行。

## Consequences

新增 Provider 需要随版本发布，扩展速度低于开放插件，但审计、兼容和故障隔离边界清晰。第三方扩展机制如需开放，必须由新的沙箱 ADR 替代本决策。

## Compatibility

既有直连客户端可通过内置 adapter 包装；默认 provider 选择保持原值。

## Verification

- 对声明文件进行 schema、未知字段和路径穿越测试。
- 静态检查禁止 adapter 直接调用 shell、读取环境密钥或动态导入。
- 诊断包与结构化日志秘密扫描为零命中。
