# AI 与供应商平台基线来源清单

## 当前构建源

- 主集成 worktree：`F:/ppt-video-workbench-v3/.worktrees/program-integration-v1`
- 分支：`codex/program-integration-v1`
- 基线 HEAD：`72cb7bbee6fb2fa21485f77d627a8f1443d61eb8`
- 根恢复快照只作恢复参考，不作为构建源。
- 基线时已发现的未跟踪 Markdown 文件属于用户现有文件，保持原样，不纳入批量覆盖或清理。

## 能力库存

| 区域 | 当前来源 | 基线结论 | 本程序归属 |
| --- | --- | --- | --- |
| Provider Kernel | `apps/api/src/workbench/providers/{models,registry,broker,policy,billing,credentials,cache,probe,upstream}.py` | 已有 V1 registry/broker/policy/billing 基础，缺统一 V2 契约与持久治理 | AI02–AI03 |
| 本地 ASR | `apps/api/src/workbench/audio/{models,transcriber,transcription_service}.py`、`scripts/provision_asr_model.py` | 有 Faster-Whisper 与旧模型目录，缺 workspace 模型中心、不可变 revision 和 runtime lease | AI01 |
| 本地 TTS | `apps/api/src/workbench/audio/heygen_service.py` 中 `SpeechSynthesizer` 接口 | 已有合成桥接抽象，缺本地 TTS provider、统一 WAV 产物和模型绑定 | AI01–AI02 |
| HeyGen | `apps/api/src/workbench/integrations/heygen/client.py`、`apps/api/src/workbench/audio/heygen_service.py`、`heygen_chunks.py` | 已有 profile、分块、重试和缓存，缺跨重启 durable batch 状态与未知计费保护 | AI05 |
| 旁白/字幕 | `apps/api/src/workbench/audio`、`apps/api/src/workbench/subtitles`、对应 API routes | 已有 transcript/subtitle/revision 路径，缺 AI 候选修订、智能断句和翻译审阅边界 | AI06 |
| 应用总线 | `apps/api/src/workbench/main.py` | FastAPI composition 已集中接线；AI01 模型中心已挂载到 `/api/ai/models` | AI00–AI07 |

## Owned path map

- AI01：`apps/api/src/workbench/ai_models/`、`apps/api/src/workbench/api/ai_models.py`、`schemas/local-model-*.schema.json`、`tests/unit/ai_models/`、`tests/integration/test_ai_models_routes.py`
- AI02–AI03：`apps/api/src/workbench/providers/`、`schemas/provider-*.schema.json`、对应 contract/unit tests
- AI04：`apps/api/src/workbench/voices/`、voice authorization schemas/tests
- AI05：`apps/api/src/workbench/providers/batch/`、HeyGen batch schemas/tests
- AI06：`apps/api/src/workbench/content_assist/`、content-assist schemas/tests
- 共享接线：`apps/api/src/workbench/main.py`，仅串行修改并保留既有路由。

## 证据边界

- 当前验证使用本地 fixture，不下载或训练真实模型。
- 未提供真实供应商凭证，因此不声称真实远端服务 PASS；后续相关 Gate 需要 `WAIT_EXTERNAL` 边界。
- 本地链路必须在远端 provider 禁用、无凭证和无网络时继续可用。
