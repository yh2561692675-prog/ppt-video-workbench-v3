# PPT Video Workbench v3 恢复总图

生成时间：2026-08-10  
项目：`F:\ppt-video-workbench-v3`

## 1. 恢复结论

项目主体代码没有整体丢失。当前根目录仍有约 177,671 个文件、9.12 GB 数据；真正导致 Codex 项目和旧窗口失效的关键原因，是根目录 `.git` 指向已经不存在的 Linux scratch worktree：

```text
gitdir: /workspace/scratch/ce46b7aa094c/work/ppt-video-workbench-v0.2.0-p0/.git/worktrees/runtime-packaging
```

已完成可逆修复：

- 原断裂 `.git` 文件已双份保留，没有删除。
- 根目录使用独立恢复元数据重新建立 Git 识别，不覆盖工作区源码。
- 恢复分支：`recovery/root-snapshot-20260810`。
- 基线提交：`2d7f8de9f1afd8fe70fb82f420a179783472daca`（`chore: import existing workbench baseline`）。
- 48 个基线后的现有修改全部保留；未执行 checkout、reset、clean、prune 或 gc。
- 两份确认缺失的脚手架文档已从基线恢复。
- 两个未引用提交已增加恢复引用，避免被 Git 回收。

根目录 Git 元数据：

```text
F:\Codex-Full-Recovery-2026-08-10\11_ppt-video-workbench-v3_repair\root-git-metadata-20260810-183914
```

断裂指针备份：

```text
F:\ppt-video-workbench-v3\.git.broken-pointer-20260810-183914.txt
F:\Codex-Full-Recovery-2026-08-10\11_ppt-video-workbench-v3_repair\original-git-pointer-20260810-183914.txt
```

## 2. 可用代码版本

### A. 根目录现存快照

路径：`F:\ppt-video-workbench-v3`

- 适合恢复主工作台、最终渲染、外围平台 P03-P12、Task26 和航空航天项目链路。
- 与导入基线比较：544 个基线文件中 494 个逐字节一致、48 个有修改、2 个原先缺失；这 2 个文档已恢复。
- 该目录包含大量构建产物、运行时、安装包、缓存和用户工作数据，后续禁止 `git clean`。

### B. 特效编辑器与模板管理工作台

路径：`F:\ppt-video-workbench-v3\.worktrees\effects-template-workbench`

- 分支：`feature/effects-template-workbench`
- HEAD：`727bec50ed544301c017fa759dd2fb3a7130618e`
- Git 跟踪文件：556
- 工作树：clean
- 最终记录：64 passed、2 skipped；Ruff、mypy、diff-check 通过。
- 这是特效编辑器/模板仓储任务的可信继续点，不应直接把它的文件盲目覆盖到根目录。

### C. 独立主仓库

路径：`F:\git仓库\ppt-video-workbench-v3`

- 仓库类型：main repository
- 主分支：`main`
- 主分支 HEAD：`a025baaf3bbb853f4fbbce7aaac3fc931da928fa`
- 主分支只有项目脚手架提交；完整代码主要在 `feature/effects-template-workbench` 和导入基线 `2d7f8de`。
- 已保存恢复引用：
  - `refs/recovery/unreachable-effect-drafts-4d349aa`
  - `refs/recovery/unreachable-template-repo-e067e20`

## 3. 离线恢复包

Git bundle：

```text
F:\Codex-Full-Recovery-2026-08-10\03_git_recovery\ppt-video-workbench-v3-e19b670b45\all-refs.bundle
SHA-256: A56F25AA36FB3E742D8544B8FDA527207D13C33E6CA5A38E4B50C8C6E7352275
```

代码 ZIP：

```text
F:\Codex-Full-Recovery-2026-08-10\04_project_code_archives\ppt-video-workbench-v3-930e15315c.zip
SHA-256: C09C80E0B3F596036971676063819BA2760C0C85C031BB71F6B9952875855659
```

- bundle 已通过 `git bundle verify`。
- ZIP 含 1,864 个条目，含根项目代码和特效 worktree 快照。

## 4. 截图中的原 Codex 窗口映射

| 原任务                                 | 原 Thread ID                           | 对话恢复文件                                                                                                             | 主要代码/文档继续点                                                  |
| -------------------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| PPT 自动生成视频特效节奏与表现形式引擎 | `019fe75f-3f52-7e42-be3c-1417c4d77864` | `F:\Codex-Full-Recovery-2026-08-10\05_threads_from_logs\readable_latest_context\019fe75f-3f52-7e42-be3c-1417c4d77864.md` | 根目录；`docs/reference-video-engine/`；V1.0 设计文档                |
| 直接接管当前项目 / Task26              | `019fe774-0e9f-7c30-bdc3-f7d22a703612` | `F:\Codex-Full-Recovery-2026-08-10\05_threads_from_logs\readable_latest_context\019fe774-0e9f-7c30-bdc3-f7d22a703612.md` | 根目录；Task26 补丁；Windows 验收；航空航天项目                      |
| 本地自动修复与验收代理                 | `019fe787-9623-74d2-9084-df719c9f3e2b` | `F:\Codex-Full-Recovery-2026-08-10\05_threads_from_logs\readable_latest_context\019fe787-9623-74d2-9084-df719c9f3e2b.md` | 根目录、`F:\app\app`、用户 workspace-data、`F:\Video`                |
| 最终渲染异步任务化                     | `019fe8e5-eb44-7060-bafe-3bdd1eea480e` | `F:\Codex-Full-Recovery-2026-08-10\05_threads_from_logs\readable_latest_context\019fe8e5-eb44-7060-bafe-3bdd1eea480e.md` | 两份设计文档；jobs、video、API、Web 面板；任务 1-10 已有实现记录     |
| 外围平台 S1/P03-P12                    | `019fe8e6-db49-7a20-be39-2a8529caa3ff` | `F:\Codex-Full-Recovery-2026-08-10\05_threads_from_logs\readable_latest_context\019fe8e6-db49-7a20-be39-2a8529caa3ff.md` | 两份设计文档；`peripheral-platform/`；business_modules；协调器持久化 |
| 特效编辑器与模板管理工作台             | `019fe8ea-3b97-7960-93af-2720739eb562` | `F:\Codex-Full-Recovery-2026-08-10\05_threads_from_logs\readable_latest_context\019fe8ea-3b97-7960-93af-2720739eb562.md` | 独立 worktree，HEAD `727bec5`                                        |
| 创建可识别 Git 仓库                    | `019fe8fb-2082-7160-b0b0-d61c4eb90c1b` | `F:\Codex-Full-Recovery-2026-08-10\05_threads_from_logs\readable_latest_context\019fe8fb-2082-7160-b0b0-d61c4eb90c1b.md` | `F:\git仓库\ppt-video-workbench-v3` 和本次根目录 Git 修复            |

这些父窗口的原 rollout 文件已经缺失，Codex 后台直接读取时返回 `thread not loaded`；但状态数据库、日志、结构化 transport、文件变更和子任务仍在恢复库中。特效任务的后续子任务可直接读取，能够验证提交 `727bec5` 和最终测试记录。

## 5. 已恢复的正式设计文件

```text
F:\ppt-video-workbench-v3\docs\superpowers\specs\2026-08-10-final-render-async-job-design.md
F:\ppt-video-workbench-v3\docs\superpowers\plans\2026-08-10-final-render-async-job.md
F:\ppt-video-workbench-v3\docs\superpowers\specs\2026-08-10-peripheral-s1-p03-p12-design.md
F:\ppt-video-workbench-v3\docs\superpowers\plans\2026-08-10-peripheral-s1-p03-p12.md
F:\ppt-video-workbench-v3\docs\superpowers\specs\2026-08-10-effects-editor-template-workbench-design.md
F:\ppt-video-workbench-v3\docs\superpowers\plans\2026-08-10-effects-editor-template-workbench.md
```

本地 Downloads 还保留：

```text
C:\Users\HanYu\Downloads\PPT自动生成视频_参考视频特效节奏与表现形式引擎_完整设计文档_V1.0.md
C:\Users\HanYu\Downloads\PPT自动生成视频_参考视频特效节奏与表现形式引擎_逐项实施计划_V1.0.md
C:\Users\HanYu\Downloads\PPT自动生成视频_真人讲解视频智能同步模式_完整设计文档_V1.0.md
C:\Users\HanYu\Downloads\PPT自动生成视频_真人讲解视频智能同步模式_逐项实施计划_V1.0.md
```

## 6. 本地补丁和压缩包

Downloads 中识别到 88 个与 PPT Video Workbench 直接相关的恢复文件，共 25,993,084 bytes：

- ZIP：83
- Markdown：4
- DOCX：1
- 时间跨度：2026-08-03 至 2026-08-10

其中包括 Task26、P01、P02、r12-r28、runtime packaging、Windows G5、HeyGen、F 盘路由和 M8 RC1 等多代补丁。它们是恢复证据，不应批量覆盖；必须先与当前根目录或 Git 提交逐文件比较。

## 7. ChatGPT 网页端和已连接网盘

ChatGPT 云端已找回 13 个强相关聊天，共 504 轮、430 个附件/生成内容引用：

| ChatGPT 对话         | ID                                     | 轮数 | 引用数 |
| -------------------- | -------------------------------------- | ---: | -----: |
| 自动生成视频工作流1  | `6a704ac5-5820-83ec-9da2-aae4ff4e5fa4` |   92 |     57 |
| 视频工作流进度       | `6a70beda-178c-83ec-afab-912e7ec1dc55` |   16 |      0 |
| 自动生成视频工作流2  | `6a717794-0978-83ec-840b-e957cb38c4a8` |  134 |    115 |
| 自动生成视频工作流3  | `6a730f5d-8ba0-83ec-8924-751de8383587` |  146 |    148 |
| 视频工作流拓展项目   | `6a76d592-1dbc-83ec-9997-871f14ffe8f1` |   57 |     68 |
| PPT 视频生成进度     | `6a776358-4604-83ec-8510-db8e272f11c0` |    4 |      1 |
| PPT 转视频进度查询   | `6a776a00-f9dc-83ec-919e-ba575bd5119a` |    8 |      0 |
| PPT 视频特效优化建议 | `6a7804ff-b8e4-83ec-a7f1-58ffb7d229fa` |   14 |      1 |
| PPT 转视频工作流设计 | `6a7847ef-6c6c-83ec-aff3-3c7fd32ffd96` |    4 |      9 |
| 视频单页特效设计     | `6a784dd1-53b8-83ec-a2d2-0126ba6c1dcf` |   10 |     24 |
| 文档生成 PPT 封存    | `6a787855-745c-83ec-8c47-037367fdafcb` |    3 |      2 |
| PPT 自动生成视频进度 | `6a788c1b-5da0-83ec-b8ce-7185a66a213f` |   12 |      5 |
| PPT 自动生成视频进度 | `6a78c030-35ac-83ec-93a9-8f1d20b41795` |    4 |      0 |

云端聊天正文目前可读取；连接器只返回附件引用标记，不能直接下载全部二进制附件。很多对应 ZIP/Markdown 已在 Downloads 找到。完整云端文本导出位于：

```text
F:\Codex-Full-Recovery-2026-08-10\07_chatgpt_cloud_export
```

已连接 Google Drive（账号 `yh2561692675@gmail.com`）已只读搜索以下关键词：`ppt-video-workbench-v3`、`PPT Video Workbench`、`P03 P12`、`特效编辑器`、`模板管理工作台`、`最终渲染`、`PPT 视频`，结果均为 0。因此当前连接的 Google Drive 不是该项目的备份来源。

ChatGPT 网页端项目不能直接读取 `F:` 本地目录；必须把恢复索引/文件上传为项目 Source，或在桌面 Codex 中使用本地项目。尚未向任何 ChatGPT 项目或 Google Drive 上传私有源码。

## 8. 后续安全规则

1. 根目录禁止 `git reset --hard`、`git clean`、`git checkout -- .`、`git gc` 和 `git prune`。
2. 特效 worktree 和根目录快照继续分开，合并前按提交和文件逐项审查。
3. Downloads 中的补丁禁止批量覆盖；先比较 SHA-256 和文件差异。
4. ChatGPT 云端只先接入本报告和必要设计文档；上传完整私有源码前需要明确选择目标 ChatGPT 项目。
5. Codex 项目缓存仍可能显示旧的 `isGitRepository=false`；新恢复窗口使用本地项目直接运行，并在窗口内用 `git rev-parse --show-toplevel` 验证实际 Git 已恢复。

## 9. 新恢复窗口的复核结论

已在原 `ppt-video-workbench-v3` 本地项目下重建 7 个只读恢复窗口，全部返回 `RECOVERY_RECOGNIZED`：

| 恢复窗口                       | 新 Thread ID                           | 复核结论                                                                                                 |
| ------------------------------ | -------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| PPT 视频特效节奏与表现形式引擎 | `019feb46-7f8b-7af3-82a8-280c691dc786` | 根 Git、V1.0 文档、E00-E12 记录和参考 MP4 均识别；正式 Windows 人工门禁与 HeyGen 外部服务验收未完成      |
| Task26 本地项目接管            | `019feb46-8950-7213-b4ca-422988a6b032` | RC `effects-v2-rc1-20260811-full-ffmpeg` 已冻结；Task26 隔离验收与完整回归通过；产品功能人工流程仍待执行 |
| 本地自动修复验收               | `019feb46-93fa-7752-b68c-61d4d6dc2dac` | 四个目录边界和航空航天项目 ID 已识别，安全继续点已恢复                                                   |
| 最终渲染异步任务化             | `019feb46-9d8c-75a2-b88a-950aa70c5a41` | Task 1-9 核心文件存在，但 Task 10 和完整发布门禁未闭环，不能把旧窗口的 completed 当作全部完成            |
| 外围平台 S1 P03-P12            | `019feb46-a8ea-7f43-b9ff-bc4fe9b31fea` | 十模块入口、契约和部分真实逻辑存在，但 P07/P11/P12 等仍是骨架，尚未达到完整 S1 发布门禁                  |
| 特效编辑器与模板管理工作台     | `019feb46-b286-72f0-903e-40807973392c` | Task 1-4 完成并通过最终复审；Task 5 只有 brief，后续应从 Task 5 Step 1 继续                              |
| Git 仓库与项目识别             | `019feb46-bb1c-7412-a5df-cfba9d4f253e` | 根快照、特效 worktree、独立保管库、bundle/ZIP、恢复引用和断链备份全部识别                                |

### 深度复核后的重要修正

- 最终渲染：旧线程曾把 Task 1-10 标为完成，但现存代码仍缺复用任务 200、最新终态查询、旧同步路由退役、输入指纹二次校验、成功产物哈希复核、原子发布完整性、若干专项测试及 Windows 8/50 页验收。
- P03-P12：十个模块都有 runner，但完整度不同。P03-P06、P09、P10 有部分真实领域逻辑；P07 主要校验元数据，P11 主要生成制作包清单，P12 主要做简单布尔决策，尚未实现设计中的真实 ASR/HeyGen、分页渲染/FFmpeg、质量归档和签署闭环。
- 特效工作台：当前精确停点是 Task 5，不能从 Task 1 重做，也不能将该分支整体覆盖根目录。
- Task26：Downloads 中三份标准补丁内容相同，AutoApply 为独立版本；当前根快照不包含补丁列出的 6 个正式文件，所以它们仅是恢复证据，尚未应用。
