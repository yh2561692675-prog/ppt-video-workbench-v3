# P2 平台基础能力可信基线

- Status: `BLOCKED_PENDING_ACTIVE_WINDOWS`
- Snapshot: 2026-08-11 Asia/Shanghai
- Purpose: Phase 0 / Task 0.1 evidence and handoff record
- Rule: 本文件记录事实，不把仍在运行或未提交的结果标记为通过

## 1. 当前结论

F0 尚未通过，因此不得创建或启用 Provider Kernel、PlatformServices、云端控制面代码，也不得修改 LLM/TTS/ASR/OCR/HeyGen/渲染/更新主链。

阻断原因：同一恢复根目录仍有多个活动任务写入；当前快照显示根目录有 123 个 tracked 状态项和 187 个 untracked 状态项；特效模板 worktree 仍有未提交状态项；真实 8/50 页、真人、竖屏和 Playwright 证据仍未冻结。Windows RC/安装验收、Task 26 隔离门禁和 FFmpeg 滤镜能力已完成，但这些结果仍属于未提交恢复工作树，不能直接当作 foundation 基线。

NOW-DOCS 产物独立且已校验，可保留；它们不代表 F0 已通过。

## 2. 仓库身份

| 角色              | 路径                                                                                                   | 类型/分支                                             | HEAD                                       | 状态                               | 用途                                                                             |
| ----------------- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------- | ------------------------------------------ | ---------------------------------- | -------------------------------------------------------------------------------- |
| 恢复开发根        | `F:\ppt-video-workbench-v3`                                                                            | recovery snapshot / `recovery/root-snapshot-20260810` | `956929e7b75f80df8d17891420ccc812574a682e` | dirty：120 tracked + 159 untracked | 多个恢复任务当前共享写入点，不可直接作为 foundation 基线                         |
| 恢复 Git 元数据   | `F:\Codex-Full-Recovery-2026-08-10\11_ppt-video-workbench-v3_repair\root-git-metadata-20260810-183914` | recovery metadata                                     | 同上                                       | Git 识别修复                       | 根目录 `.git` 的实际 git-dir/common-dir                                          |
| 正式主仓库        | `F:\git仓库\ppt-video-workbench-v3`                                                                    | main repository / `main`                              | `a025baaf3bbb853f4fbbce7aaac3fc931da928fa` | clean                              | 注册表确认的正式主仓库，但尚未包含恢复根最新实现                                 |
| 特效模板 worktree | `F:\ppt-video-workbench-v3\.worktrees\effects-template-workbench`                                      | worktree / `feature/effects-template-workbench`       | `c23e1b3`                                  | clean                              | 已形成可审查停点；前序实现 `3636d3d`、`fe1f1e7` 已在提交历史，禁止目录覆盖式合并 |

正式主仓库信息来自按仓库 `AGENTS.md` 刷新的 `F:\git仓库\_repo_indexer\repo_registry.json`：`repository_type=main_repository`、`main_repository_path=F:\git仓库\ppt-video-workbench-v3`、`current_branch=main`、`has_uncommitted_changes=false`。

## 3. 活动变更来源表

| 任务                   | Task ID                                | 当前工作/权威范围                            | F0 要求的停点                                      |
| ---------------------- | -------------------------------------- | -------------------------------------------- | -------------------------------------------------- |
| P1 项目逐项实施        | `019fec23-1884-72d1-a362-7298042ed8e0` | 根目录；素材库已完成，正在灵活材料组织       | 提交或逐文件状态清单，说明后续仍会修改的范围       |
| 特效节奏与表现引擎     | `019feb46-7f8b-7af3-82a8-280c691dc786` | 根目录 runtime/release/FFmpeg 与特效质量链   | 完整 FFmpeg 来源、摘要、许可证、filters 验收和提交 |
| 最终渲染异步任务       | `019feb46-9d8c-75a2-b88a-950aa70c5a41` | 根目录最终渲染、长视频时长与测试             | 全量 pytest 最终结论、真进程时长证据和提交         |
| Windows 自动修复验收   | `019feb46-93fa-7752-b68c-61d4d6dc2dac` | 根目录/安装隔离快照/发布验证                 | 可复现的完整快照、Windows release 结果和明确停点   |
| 特效编辑器与模板工作台 | `019feb46-b286-72f0-903e-40807973392c` | 独立 effects worktree；Task 15 验收/E2E/文档 | worktree 12 项变更审查并提交，给出 HEAD            |

可能重叠的权威范围：根目录 `runtime-assets`/`release`/FFmpeg、最终渲染与质量验收、公共文档和测试基础设施。F0 前必须由各任务明确提交和所有权，不能仅凭最后修改时间推断来源。

## 4. 已完成的 NOW-DOCS 证据

| 产物                                                 | 结果                                                                                   |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `docs/adr/p2-platform/`                              | 7 份 Accepted ADR；必填元数据/章节和索引链接检查通过                                   |
| `docs/platform/platform-dependency-audit.md`         | Windows/路径/凭证/进程/Office/媒体绑定点与 B1-B11 迁移门禁已登记                       |
| `docs/adr/cloud/cloud-collaboration-threat-model.md` | 数据分类、RBAC、24 类威胁、对象/同步/executor/生命周期门禁已登记                       |
| `schemas/cloud/*.schema.json`                        | 3 份 Draft 2020-12 schema 由 AJV 8 strict 编译通过                                     |
| `schemas/cloud/examples/*.valid.json`                | ObjectRef、ProjectRevision、SyncOperation 合成 fixtures 均通过 schema                  |
| `schemas/cloud/cloud-collaboration-v1.openapi.yaml`  | YAML 可解析；23 个 operationId 唯一；281 个内部/外部引用存在；所有 mutation 声明幂等键 |
| 路径负例                                             | Windows/POSIX 绝对路径、`..`、反斜杠、NUL 均被 ObjectRef schema 拒绝                   |

## 5. F0 待执行基线矩阵

| 门禁             | 命令/证据                                             | 当前状态                                        |
| ---------------- | ----------------------------------------------------- | ----------------------------------------------- |
| Python 单元/集成 | 项目锁定 Python 环境下全量 pytest，保存失败清单和时长 | `598 passed, 2 warnings`（2026-08-11）          |
| Ruff             | 锁定版本的 check/format check                         | 受影响范围全绿；全量最终停点待复核              |
| mypy             | 项目配置下全量类型检查                                | 受影响范围全绿；全量最终停点待复核              |
| Web              | pnpm 锁定安装；typecheck、lint、unit                  | typecheck 通过；74 tests passed                 |
| Remotion         | composition/contract/render smoke                     | typecheck 通过；28 tests passed                 |
| Playwright       | 关键本地流程 E2E                                      | 等待模板/P1 UI 收口                             |
| Windows release  | build、安装、启动、修复、升级/卸载                    | P01 isolated acceptance passed；升级/回滚待执行 |
| 8 页样本         | manifest、MP4、时长、质量问题报告和 hash              | 待固定                                          |
| 50 页样本        | 同上，另记录峰值内存和耗时                            | 待固定                                          |
| 真人样本         | 音画同步、字幕、数字人/真人素材和降级                 | 待固定                                          |
| 竖屏样本         | 画幅、裁剪、安全区和导出元数据                        | 待固定                                          |
| 质量检测样本     | 规则版本、问题列表、误报豁免和报告 hash               | 待固定                                          |

测试只接受完整退出码和保留日志；shell 超时、后台仍运行、仅重跑失败项或沿用旧窗口口述均不能算通过。真实 Provider 付费调用不是 F0 必需，不得为基线产生费用。

## 6. 放行步骤

1. 等待上表活动任务全部变为 idle/completed，并读取其最终停点、HEAD 和未提交清单。
2. 重新刷新正式仓库注册表，重新统计恢复根、正式主仓库和所有 worktree。
3. 为每个根目录变更登记来源；对同一文件的多任务改动逐项审查，不做目录覆盖合并。
4. 选择包含已验收实现的单一 foundation commit；若正式主仓库未包含恢复实现，先制定显式提交/移植序列。
5. 在资源稳定时执行完整基线矩阵，写入命令、版本、退出码、日志路径和样本摘要。
6. 仅在所有硬门禁通过后创建 `codex/p2-platform-foundation` worktree；记录创建源提交和 clean status。
7. 将本文件状态改为 `PASSED`，更新精确 HEAD/测试证据后，才可开始 Task 0.3。

## 7. 禁止事项

- 禁止 `git reset --hard`、`git clean`、批量 checkout、目录复制覆盖和破坏性历史整理。
- 禁止从正式主仓库的 clean 状态推断其实现比恢复根更新。
- 禁止把特效 worktree 的整棵目录复制回根目录。
- 禁止在活动窗口未收口时创建“看似 clean”的不完整 foundation 分支。
- 禁止用 mock、旧日志或超时命令替代真实基线结果。
