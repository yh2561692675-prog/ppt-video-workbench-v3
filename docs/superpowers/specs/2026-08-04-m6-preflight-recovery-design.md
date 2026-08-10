# M6 预检与恢复系统设计规格

**日期：** 2026-08-04  
**基线：** `feature/m1-foundation` / M5 合并提交 `b34a77b`  
**范围：** Task 27—31

## 目标

在 M5 已具备的材料解析、旁白确认、音频门禁、字幕、Remotion 预览、分页渲染和制作包导出之上，建立一套可审计的预检、缓存失效、任务检查点和安全清理能力。目标是：阻断问题必须可定位且可执行修复；一般问题必须有人工确认记录；异常退出后从最近安全检查点恢复；只重做受影响页面；清理缓存不能破坏源文件、确认内容、最终包或项目索引。

## 不变边界

- 继续使用本地 Windows 工作台、Python/FastAPI、React/TypeScript、Remotion 和 SQLite/`project.json`。
- 不改变大纲与课件事实边界，不新增外部资料，不绕过旁白、音频和正式渲染人工门禁。
- 不改变 M5 的 `ProjectVideoProps`、字幕时间轴、音频路线和制作包格式；M6 只增加通用质量与恢复层。
- 预检不能只返回自由文本；每个问题必须包含稳定 `code`、稳定 `issue_id`、级别、对象定位、修复动作、输入指纹和阻断属性。
- 所有项目状态仍通过 `ManifestStore` 原子保存；预检报告、检查点和清理计划也必须采用临时文件加原子替换。

## 设计方案

### 1. 结构化问题模型

新增 `domain/issues.py`，定义：

- `IssueLevel`：`blocking`、`confirmation`、`required_warning`、`info`。
- `IssueLocation`：可选 `page_id`、`job_id`、节点名和相对路径。
- `PreflightIssue`：稳定 `issue_id`、稳定 `code`、级别、消息、修复动作、定位、`blocking`、检查指纹、确认状态和确认审计信息。
- `PreflightReport`：报告 ID、项目 ID、生成时间、范围、全局输入指纹、所有问题、每个检查的输入指纹、是否允许渲染、报告快照路径。
- `IssueConfirmation`：问题 ID、确认人、确认时间、确认说明和报告 ID。

稳定问题 ID 由项目 ID、检查 code、对象定位和输入指纹通过 UUID5 生成。同一输入下重复预检不会产生重复问题；输入变化后旧确认自动失效。

### 2. 预检引擎

新增 `preflight/checks/` 下按职责拆分的检查器，以及 `preflight/engine.py`。检查域覆盖：

1. 文件与页面：源文件存在、哈希、页数、顺序、预览文件和图片格式/尺寸。
2. 文字与 OCR：页面提取存在、低置信度定位、无法识别区域和人工校对状态。
3. 旁白：逐页覆盖、当前版本已确认、材料不足和预计时长异常。
4. 音频：路线、文件、逐页对应、差异处理、静音、分页时间轴和时长。
5. 字幕：字幕产物、页边界、时间轴覆盖、同步性和避让结果。
6. 接口：已配置的大模型/HeyGen 连接、模型/声音标识和最近错误；没有凭证时只返回脱敏问题。
7. 本地组件：Python、Node、Remotion、FFmpeg、OCR、浏览器的可用性与版本。
8. 资源：输出目录权限、磁盘空间和中文路径可访问性。

`run_preflight(project, scope)` 按检查输入指纹做增量运行：指纹未变化时复用上一次该检查的结果，变化或明确指定 scope 时重新执行。无论增量还是全量，都生成完整报告，并将 JSON 快照保存至 `09_日志/预检/`。

级别规则固定为：`blocking` 直接禁止渲染；`confirmation` 和 `required_warning` 必须有当前报告下的人工确认；`info` 不影响渲染。报告 `allowed` 只有在阻断问题为零、待确认问题均已确认且 M5 视频预览契约通过时为真。

### 3. 预检 API 与工作台

新增通用路由：

- `POST /api/projects/{project_id}/preflight`：运行完整或指定范围预检。
- `GET /api/projects/{project_id}/preflight`：读取当前报告。
- `POST /api/projects/{project_id}/issues/{issue_id}/confirm`：确认当前报告中的非阻断问题，写入审计日志。
- `GET /api/projects/{project_id}/preflight/report?format=json|markdown`：导出报告。
- `POST /api/projects/{project_id}/render`：与既有视频导出服务共享入口，但在调用导出前强制重新验证最新报告；旧报告、输入指纹变化或未确认问题均返回结构化 409。

保留 M5 的 `/video/preflight` 和 `/video/render` 兼容接口，并让它们共用 M6 门禁服务。前端新增 `features/preflight/PreflightWorkspace.tsx`，在第 6 步显示按级别分组的问题、页面/节点定位、修复动作、确认按钮、确认记录、报告导出和最后检查时间。阻断问题没有确认按钮；确认/警告问题确认后只刷新报告，不直接启动渲染。

### 4. 缓存键与依赖失效

新增 `cache/key.py` 和 `cache/dependency_graph.py`。节点链固定为：

`source → extraction → match → narration → audio → timeline → subtitle → segment → final`

缓存键使用规范化 JSON 计算 SHA-256，至少包含源文件哈希、内容版本、模板版本；音频/字幕/片段额外包含旁白版本、音频来源、声音标识、分页时间轴版本和字幕样式版本。

固定失效规则：

- 单页旁白变化：只重建该页 narration/audio/subtitle/segment，并使 final 失效；其他页面全部保留。
- 单页音频或分页点变化：只重建受影响页面的 timeline/subtitle/segment，并使 final 失效。
- 课件或大纲变化：重建 extraction/match，并按依赖传播到受影响页面；未受影响页面保留。
- 模板变化：只失效全部 segment/final，保留旁白、音频和字幕。
- HeyGen 声音变化：只失效用户明确选择重新配音的页面及其下游；不得自动重做成功页面。
- 运行时/软件升级：保留有效缓存；仅使明确不兼容节点失效。

### 5. 检查点与恢复

新增 `jobs/checkpoint.py`。`JobContext` 为长任务提供 `checkpoint(progress, payload)`、`request_pause()`、`request_cancel()` 和 `restore()`。检查点以 job ID 和阶段序号命名，写入 `09_日志/检查点/`，内容包含脱敏输入摘要、完成页、缓存键、临时产物和远端任务 ID。

所有 handler 只在安全边界写入检查点；重启后先加载最新有效检查点，再验证产物哈希和缓存键，验证失败则从该节点重新执行。OCR、ASR、HeyGen 轮询、分页渲染和合成均使用同一接口。付费任务恢复时优先查询已有远端任务 ID，确认不存在或失败后才允许创建新任务；成功结果永远优先复用。

暂停会在当前安全边界结束后将 job 置为 `paused`，取消会清理临时文件但保留已完成页和检查点，异常退出不会把已完成页降级。恢复操作具有幂等键，重复调用不会生成重复产物或重复付费请求。

### 6. 缓存空间管理与清理

新增 `cache/cleanup.py` 和项目中心存储面板。`estimate_cleanup(project, selection)` 只返回可删除的可重建缓存、大小、受影响节点和预计重建范围；`execute_cleanup(plan_id)` 在二次确认后执行。

禁止删除：`01_源文件`、已确认旁白及历史版本、`08_输出` 中的最终制作包、`project.json`、`project.json.bak`、必要的项目索引和当前有效检查点。清理采用逐文件白名单、路径约束和临时 manifest 更新；任何中断都不能产生半更新 manifest。清理完成后只将对应缓存节点标记为缺失，下一次操作按依赖图精确重建。

## 关键数据持久化

`ProjectManifest` 增加可选的 `preflight_report`、`preflight_history`、`issue_confirmations` 和 `cleanup_plans` 字段；旧项目缺少这些字段时按空值迁移，不升高现有 schema 版本。报告快照和检查点文件均位于项目目录内，项目恢复时以 `project.json` 为权威，文件清单只作为可验证产物。

## 测试与验收

- Task 27：每个检查域至少一个失败用例；稳定 code/定位/动作；级别门禁；无变化复用与变化重跑；报告快照存在。
- Task 28：阻断禁止渲染；确认/警告确认后允许；旧报告因输入变化失效；HTTP 直调不能绕过；前端按级别分组和定位。
- Task 29：六类变化事件完整矩阵；单页修改不影响其他页；模板/声音/软件变化符合失效边界；计划可序列化。
- Task 30：五类长任务在 30%/70% 强杀后恢复；检查点和产物哈希稳定；暂停/取消安全；付费任务不重复创建。
- Task 31：保护路径不可删除；空间估算准确；二次确认；清理中断不破坏 manifest；清理后只重建缺失节点。
- M6 Gate：Python、前端、Remotion、契约、生产构建、Playwright 和恢复矩阵全部通过；新增报告、失效计划、检查点和清理审计证据。

## 明确不做

本阶段不实现 Windows 安装器、运行时打包、稳定版更新、多人协作、云端任务、自动发布或 PPT 元素级动画；这些属于 M7/M8 或已明确暂缓范围。
