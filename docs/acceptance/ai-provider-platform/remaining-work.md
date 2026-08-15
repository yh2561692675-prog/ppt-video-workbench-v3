# 未完成项与明确边界

本轮已经按 AI01→AI06 串行实现本地可验证基础，并完成一次受影响项目回归。以下项目仍不能标记为真实生产完成，原因是需要不同于本地代码提交的运行环境或人工授权：

1. AI01：模型中心已有离线导入、断点传输 primitive、manifest、probe、lease 和 legacy ASR 兼容；尚未在当前工作区下载真实大模型，也未声称 CUDA/DirectML 或真实 TTS 引擎通过。Web 模型中心界面未纳入本轮 API 基础实现。
2. AI02：V2 契约和 fake conformance 已完成；真实 LLM/ASR/TTS/renderer SDK 的供应商适配、价格/保留策略探测和设置页迁移需要 sandbox 凭证与供应商条款。
3. AI03：费用账本已接入 Provider Broker，未知计费会阻止远端自动切换，并提供人工 reconcile API；跨进程/跨机器的集中限流和账单对账仍需要部署级存储。
4. AI04：声音身份、本人/被授权主体、范围、撤销和本地导出红线已完成；真实声音克隆训练、样本保管和授权文件的人审流程不在无样本环境中伪造。
5. AI05：HeyGen 现有分段缓存/重试加上 durable batch 状态已完成；真实异步批量轮询、webhook、未知账单对账和付费回放必须在 sandbox 中验证。
6. AI06：本地润色/断句候选和人工 accept 已完成；无 provider 时翻译明确为 `needs_provider`，不生成伪译文。真实翻译质量评测和供应商成本策略待外部 sandbox。
7. AI07：本地独立链路和核心回归通过；完整 Windows 普通用户打包安装、断网硬件 smoke、真实外部服务和 Web UI 仍是发布前 Gate，不应把本地测试数替代为生产 PASS。

这些边界不会阻断本地导入音频、已有 transcript/subtitle 使用、项目打开、候选审阅或本地渲染；外部服务保持 opt-in。
