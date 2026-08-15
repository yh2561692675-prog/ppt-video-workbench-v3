# 集成顺序

1. 核对 `source-identity.json` 的 branch、base、head 和 `ci-runs.json` 的 URL。
2. 在目标集成分支建立干净 worktree；保留 AI 分支作为可回溯来源。
3. 按 `owned-paths.json` 逐文件选择性暂存，禁止 `git add .`，排除用户文档、core、DP45 和最终候选。
4. 重跑 OpenAPI export/check、Python AI/Provider targeted、Web typecheck/build 和 local-only chain。
5. 验证本地音频链在无凭证、断网条件下仍可独立运行。
6. 在外部授权齐备后，单独安排真实硬件模型、供应商 sandbox、费用控制和声音授权 Gate。
7. 最后由集成方决定是否合并；本交接包不代表已合并或已发布最终个人使用候选。
