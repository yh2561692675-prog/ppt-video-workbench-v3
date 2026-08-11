# M6 Gate：预检、缓存失效与恢复

## 交付范围

| 任务    | 交付                                               | 提交      |
| ------- | -------------------------------------------------- | --------- |
| Task 27 | 结构化问题目录、六域预检、增量检查、JSON 快照      | `1942307` |
| Task 28 | 预检工作区、确认审计、Markdown 报告、HTTP 渲染门禁 | `83d2b7b` |
| Task 29 | 规范化 SHA-256 缓存键、确定性依赖失效计划          | `a0c248f` |
| Task 30 | 原子检查点、暂停/取消边界、哈希校验、付费任务恢复  | `94285c5` |
| Task 31 | 白名单缓存清理、二次确认、事务回滚、存储面板       | 当前提交  |

## 六类失效矩阵

依赖链固定为：`source → extraction → match → narration → audio → timeline → subtitle → segment → final`。

- 单页旁白变化：该页 `narration/audio/subtitle/segment` 与 `final` 重建；该页 `timeline` 和其他页面保留。
- 单页音频或分页点变化：该页 `timeline/subtitle/segment` 与 `final` 重建；其他页面保留。
- 课件/大纲变化：`extraction/match` 和指定受影响页面的全部下游重建；未受影响页面保留。
- 模板变化：全部页面 `segment` 与 `final` 重建；旁白、音频、时间轴和字幕保留。
- HeyGen 声音变化：仅用户指定页面的 `audio/timeline/subtitle/segment` 与 `final` 重建。
- 运行时升级：仅 `incompatible_nodes` 指定节点及其下游重建；没有显式不兼容节点时不清空有效缓存。

## 恢复与安全证据

- OCR、ASR、HeyGen 轮询、页面渲染、制作包合成均通过同一 `JobContext` 检查点接口覆盖 30%/70% 中断。
- 检查点写入 `09_日志/检查点/`，使用临时文件和原子替换；恢复前验证产物 SHA-256 与项目路径。
- 暂停只在 handler 完成检查点后生效；取消只删除检查点声明的临时文件，已完成产物保留。
- 付费恢复先查询已保存的远端任务 ID；成功远端结果复用，不创建重复请求。
- 清理只允许白名单缓存目录；源文件、确认旁白、最终包、`project.json`、备份、索引和当前检查点受保护。
- 清理先移动到事务目录，所有文件成功后才原子更新 manifest；中断会恢复已移动文件并保持 manifest 不变。

## 验收命令与结果

```text
UV_CACHE_DIR=/tmp/uv-cache-m6 uv run pytest -q
199 passed

UV_CACHE_DIR=/tmp/uv-cache-m6 uv run ruff check apps/api/src/workbench tests
All checks passed

UV_CACHE_DIR=/tmp/uv-cache-m6 uv run mypy apps/api/src/workbench
Success: no issues found in 106 source files

UV_CACHE_DIR=/tmp/uv-cache-m6 uv run pytest tests/contracts -q
10 passed

pnpm check
ESLint/Prettier、TypeScript、Web 24/24、Remotion 5/5、生产构建通过

PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-m6 pnpm exec playwright test
1 passed
```

Task 27—31 的专项回归、契约快照、全量 Python、前端/Remotion、生产构建与 Playwright 均已通过。当前容器没有 PowerShell，因此 `scripts/kill-recovery-test.ps1` 仅在 Windows 验证；Linux 等价恢复矩阵已通过。

## 2026-08-11 恢复窗口复核

以下结果是在恢复分支 `recovery/root-snapshot-20260810` 的当前工作树上重新执行，覆盖 Task 27—31 的专项实现；它们不替换上面的历史记录，也不表示已经创建新的 Git 提交：

```text
Python focused M6 suites: 61 passed, 1 existing pytest cache warning
Ruff (preflight/cache/jobs and focused tests): All checks passed
mypy (preflight/cache/jobs): Success: no issues found in 22 source files
Web PreflightWorkspace: 2 passed
```

当前恢复分支的 HEAD 为 `956929e`；Task 27—31 的变更仍属于恢复工作树中的未提交内容，历史表中的提交号只作来源记录。后续若要合入主线，必须先按文件审查并单独提交，不能把恢复快照直接视为已合入。
