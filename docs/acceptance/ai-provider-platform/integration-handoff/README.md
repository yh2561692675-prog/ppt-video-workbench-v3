# AI / Provider 平台集成交接包

## 结论

`AI_PROVIDER_INTEGRATION_HANDOFF_READY=PASS`。

本包交付独立分支 `codex/program-ai-provider-platform` 的源码身份、精确范围、本地回归、GitHub Actions 结果和外部边界。它不是最终个人使用候选，也不执行合并。

## 源码身份

- 工作树：`F:/ppt-video-workbench-v3/.worktrees/program-integration-v1`
- 基础提交：`72cb7bbee6fb2fa21485f77d627a8f1443d61eb8`
- 最终交接提交：`30d24a4721b22415585363b7a35cfb0749f6ba16`
- 分支：`codex/program-ai-provider-platform`
- 推送状态：已推送到 origin

详见 `source-identity.json`、`owned-paths.json` 和 `handoff.json`。

## 已验证

- Python 全量：`1085 passed, 1 warning`
- 受影响 AI/Provider 集合：`72 passed, 1 warning`
- Web：`47 test files, 88 tests passed`
- Ruff、Mypy、OpenAPI drift、Web typecheck/build：通过
- CI Ubuntu/Windows quality：通过
- platform-contracts Ubuntu/Windows/macOS：通过

详见 `local-regression.json`、`ci-runs.json`。

## 集成顺序

1. 集成方核对本包的 branch、base、head 和 CI URL。
2. 先在目标集成分支复验本地核心链路，再审阅 AI 功能的 opt-in 默认值。
3. 仅按 `owned-paths.json` 选择性迁移；不要带入四份被排除的用户文档。
4. 完成目标分支回归和 Windows 最终候选复验后，再由集成方决定是否合并。

详见 `integration-order.md` 和 `conflict-register.md`。

## 明确未完成

Windows 最终候选、真实硬件模型、真实供应商 sandbox、付费操作、人工声音授权以及音画审核均未被本地自动化替代。详见 `external-gates.md`。
