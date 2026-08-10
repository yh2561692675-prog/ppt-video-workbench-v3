# HeyGen 批量配音重试与当前服务日志 r19

覆盖到 `F:\ppt-video-workbench-v3` 的同名路径，然后按原有流程重新构建并安装。

本包只包含三项变更：

- `apps/api/src/workbench/integrations/heygen/client.py`：对语音合成的超时、网络错误和服务端失败自动重试一次；认证、额度和限流错误不会自动重试。
- `apps/api/src/workbench/main.py`：当前运行的 API 服务会按本次服务进程写入独立请求日志。
- `tests/integration/test_heygen_retry.py`：覆盖自动重试、成功页不重复调用和日志脱敏的回归测试。

日志位置：

`%LOCALAPPDATA%\PPTVideoWorkbench\workspace-data\logs\heygen-requests-<服务进程号>.jsonl`

每行记录一次 `retry`、`success` 或 `failure`，包含服务进程号、尝试次数、耗时和错误代码；不会记录 API Key 或旁白文字。

成功页面会继续复用已有缓存；再次点击“生成全部页面配音”时，已完成页面不会重新生成或覆盖。
