# AI Provider 本地回归记录

## 第二轮结果

- 分支：`codex/program-ai-provider-platform`
- 基础提交：`72cb7bbee6fb2fa21485f77d627a8f1443d61eb8`
- Python 全量：`1085 passed, 1 warning`
- AI/Provider、契约、local-only、OpenAPI 和 skill preflight 定向集合：`72 passed, 1 warning`
- Web 全量：`47 test files, 88 tests passed`
- Web TypeScript：`tsc --noEmit PASS`
- Web production build：`PASS`（仅 bundle size warning）
- Ruff：`All checks passed`
- Mypy：`Success: no issues found in 380 source files`
- OpenAPI/project schema drift：`scripts/export_contracts.py --check PASS`
- `git diff --check`：`PASS`

## 首轮缺陷及处理

1. AI 路由接入后 OpenAPI 快照漂移：用仓库权威导出脚本更新 `packages/contracts/openapi.json`，契约测试恢复通过。
2. Windows 受限环境的 `uv.exe` PATH shim 返回拒绝访问：skill preflight 在已有 `.venv/pyvenv.cfg` 时报告安全 `fallback`，真实 release/build 脚本仍要求可执行 uv；预检测试恢复通过。
3. Mypy 暴露模型设备默认值、声音仓库迭代器、conformance 状态、Broker governance 可空收窄和 descriptor kind 类型问题：已在 AI/Provider 模块内修复并通过全量 Mypy。

## 外部边界

- 真实 CUDA/DirectML/Faster-Whisper/TTS 模型未下载或运行。
- 真实供应商 sandbox、HeyGen webhook/异步付费 canary 未调用。
- 无真实声音授权样本，未训练、克隆或云端上传。
- Windows 最终个人使用候选未构建、签名或替换。
