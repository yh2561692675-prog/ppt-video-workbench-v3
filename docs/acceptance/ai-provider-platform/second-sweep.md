# AI Provider 未完成项二次清扫

## 清扫结论

第二轮扫描覆盖 AI/Provider 后端、统一 Web 控制中心、schema、测试、验收文档和实施计划。未发现可由当前 AI 分支直接解决而仍未处理的工程缺陷。

## 已解决的工程项

- OpenAPI 快照与新增 AI 路由同步。
- Windows 受限环境下的仓库 skill preflight 使用已存在 `.venv` 的安全 fallback。
- AI/Provider 新增模块 Mypy 类型错误全部归零。
- Web 控制面默认关闭，Provider API 只有显式开关开启后才读取。
- local-only 后端启动、模型、声音和内容辅助路由保持无凭证可用。

## 保留的外部/人工项

| 项目               | 状态             | 完成条件                                                                   |
| ------------------ | ---------------- | -------------------------------------------------------------------------- |
| Windows 最终候选   | BLOCKED_EXTERNAL | 普通用户安装、中文/长路径、真实运行时、播放/导出、回滚和重装证据绑定新候选 |
| 真实硬件模型       | BLOCKED_EXTERNAL | 指定 ASR/TTS 模型在目标 Windows 硬件完成 probe、音频质量和资源验收         |
| 真实供应商 sandbox | BLOCKED_EXTERNAL | 凭证、官方 sandbox、非生产数据、预算上限、异步恢复和费用对账完成           |
| 付费操作           | BLOCKED_EXTERNAL | 明确 Provider、最大预算、授权人和可回滚 canary                             |
| 声音授权与音画审核 | HUMAN_SIGNOFF    | 本人/被授权主体签署范围、有效期、样本哈希，并完成旁白/字幕/音画人工审核    |
| 跨进程集中限流     | DEPLOYMENT_TASK  | 部署级共享账本/限流存储和多进程恢复验收                                    |

这些项目不能用 fake adapter、fixture、测试数量或旧候选证据替代。
