# 接口配置说明

工作台默认可以只使用本地录音和本地编辑，不配置任何外部接口。LLM 用于生成旁白候选稿，HeyGen 用于页面语音合成；二者是独立配置，不能把一个服务的密钥填到另一个服务。

## LLM

1. 打开“设置 → 模型接口设置”。
2. 填写配置名称、兼容 OpenAI Chat Completions 的 Base URL 和模型名称。
3. 在密钥输入框粘贴密钥并点击“安全保存配置”。保存成功后输入框会清空，页面只显示“密钥已由本机安全保护”。
4. 点击“测试连接”，确认模型可用后，再在第 3 步旁白编辑器中选择该配置。

工作台只记录 Base URL 摘要、模型和使用时间，不在项目清单、日志、诊断包或浏览器响应中回显密钥。连接失败时先检查 URL 是否包含正确的 API 版本路径、模型权限和本机网络策略。

## HeyGen

1. 打开“设置 → HeyGen 声音设置”。
2. 填写服务 Base URL 和密钥，保存后选择声音并使用试听功能验证。密钥只在本机当前 Windows 用户的 DPAPI 保护存储中使用；不要把密钥粘贴到聊天、工单、日志或报告。
3. 明确选择一个声音 ID，并在发送远程请求前确认本次 canary 的硬费用上限。没有声音批准或费用授权时，预检必须保持 `HEYGEN_WAIT_EXTERNAL`。
4. 在第 4 步为页面生成音频；生成前确认页面旁白 revision 与声音参数。

当前外部核查只读确认了 HeyGen 连接器可认证，并发现账户中的两个私有中文声音；这不等价于工作台本地配置已经通过，也没有提交任何计费请求。真实 canary 还必须绑定当前候选的本地凭据、非敏感两页样本、明确的声音 ID、硬费用上限和 Windows 候选签署记录。证据见 [HeyGen 本地就绪记录](acceptance/personal-use-closure/heygen-local-readiness-2026-08-14.json)。

已生成的音频会记录声音参数、revision、请求标识和缓存键。只有同一页面、同一 revision、同一声音参数才会复用；其他变化需要显式替换本页。若项目已经使用本地录音，跨路线替换会在发送远程请求前阻断，不会产生新的计费请求。

## 本地 API

安装后 API 只绑定 `127.0.0.1`。常用只读或动作接口如下：

| 用途       | 方法与路径                                 |
| ---------- | ------------------------------------------ |
| 健康检查   | `GET /api/health`                          |
| 环境报告   | `GET /api/environment`                     |
| 诊断包     | `POST /api/environment/diagnostic-package` |
| 检查更新   | `GET /api/updates/check`                   |
| 暂存更新   | `POST /api/updates/stage`                  |
| 应用更新   | `POST /api/updates/apply`                  |
| 回滚更新   | `POST /api/updates/rollback`               |
| 项目列表   | `GET /api/projects`                        |
| 运行预检   | `POST /api/projects/{id}/preflight`        |
| 导出制作包 | `POST /api/projects/{id}/render`           |

所有响应使用统一 envelope：成功数据在 `data`，失败信息在 `error`，其中包含 `code`、`message`、`action` 和 `blocking`。更新接口只接收工作区内的相对更新包路径，不把完整本地路径返回给前端。

## 诊断包

“环境诊断”只读取组件版本、路径摘要、磁盘、权限和中文目录读写结果。诊断 ZIP 包含 JSON、Markdown 和说明文件，不包含配置密钥、认证头、项目源文件正文或音频内容。发送诊断包前仍建议人工打开 ZIP 检查内容。

完整错误 code 和处理建议见 [排障手册](troubleshooting.md)。
