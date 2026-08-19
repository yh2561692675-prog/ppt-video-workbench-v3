# PPT 视频工作台 Skill 可安装性加固逐项实施计划 V1.0

本计划实施范围是 v0.1.2 Skill 可安装性加固；每项仅在 `codex/skill-v012-installability` worktree 执行。状态采用工程状态，不代表正式发布状态。

### T01：建立失败的能力契约测试

**状态：** COMPLETED

**依赖：** 无

**阻塞后续：** T02

**推荐方案：** 先为 render 与 office-import 缺失依赖、source 最小依赖和安装副本运行写行为测试，再实现生产代码。

**涉及文件：** `tests/skills/test_ppt_video_workbench_preflight.py`

**实施内容：** 增加能力需求和阻断清单断言；通过复制 Skill 到临时安装目录并运行其中的脚本，证明脚本不依赖仓库相对路径。

**完成标准：**

- [x] 新测试在旧实现上因缺少能力 API 或错误 READY 失败。
- [x] 测试不依赖网络、GitHub 令牌或真实 Office 渲染。

**验证命令：**

```powershell
python -m pytest tests/skills/test_ppt_video_workbench_preflight.py -q
```

**预期结果：** 初次执行非零，失败指向尚未实现的能力契约；实现后退出码为 0。

**工作目录：** `X:\Projects\01_Active\03_ppt-video-workbench-v3\01_Workspace\worktrees\skill-v012-installability`

**退出码：** 实现前非 0；实现后 0。

**关键输出：** pytest 用例名称、失败/通过数量。

**证据保存到：** `X:\Projects\01_Active\03_ppt-video-workbench-v3\06_AcceptanceEvidence\x-drive\skill-v012-installability\T01-pytest.txt`

**已知基线失败：** 现有实现没有 capability API，且 render/Office 工具缺失仍可 READY。

**失败处理：** 若测试环境缺少基础源码工具，构造受控探测器或临时假工具，不将机器缺依赖误判为实现失败。

**回滚方法：** 仅撤回本分支新增的测试提交；不修改其他 worktree。

### T02：实现能力感知预检

**状态：** COMPLETED

**依赖：** T01

**阻塞后续：** T03

**推荐方案：** 在现有 `preflight.py` 中以显式 capability 映射计算阻断工具，保留 JSON 输出并为不满足的所选能力返回非零。

**涉及文件：** `skills/ppt-video-workbench/scripts/preflight.py`、`tests/skills/test_ppt_video_workbench_preflight.py`

**实施内容：** 增加 `--capability source|office-import|render`；将工具状态与所选能力的阻断集合分离；输出 capability 和 blockers。

**完成标准：**

- [x] source 不要求 FFmpeg 或 LibreOffice。
- [x] render 缺 `ffmpeg` 或 `ffprobe` 时非零且 `ready=false`。
- [x] office-import 缺 `soffice` 时非零且 `ready=false`.

**验证命令：**

```powershell
python -m pytest tests/skills/test_ppt_video_workbench_preflight.py -q
```

**预期结果：** 退出码 0，所有预检行为用例通过。

**工作目录：** `X:\Projects\01_Active\03_ppt-video-workbench-v3\01_Workspace\worktrees\skill-v012-installability`

**退出码：** 0。

**关键输出：** capability、ready、blockers 字段与通过数量。

**证据保存到：** `X:\Projects\01_Active\03_ppt-video-workbench-v3\06_AcceptanceEvidence\x-drive\skill-v012-installability\T02-pytest.txt`

**已知基线失败：** 预检目前没有能力参数，工具缺失不会依据任务类型阻断。

**失败处理：** 保留现有输出字段兼容性；若原测试依赖旧默认，补充 source 默认行为后复测。

**回滚方法：** 回退本分支的预检实现提交。

### T03：修复安装入口与脚本自定位说明

**状态：** COMPLETED

**依赖：** T02

**阻塞后续：** T04

**推荐方案：** README 采用 repo/ref/path 的安装器指令；SKILL.md 用 `<skill-dir>` 表示已安装目录；工作流按 source、office-import、render 选择预检。

**涉及文件：** `README.md`、`skills/ppt-video-workbench/SKILL.md`、`skills/ppt-video-workbench/references/source-workflow.md`

**实施内容：** 移除歧义安装 URL，补充未发布 v0.1.2 前的来源分支边界和正式 Release 边界；要求先定位应用 repo 根与 Skill 安装目录。

**完成标准：**

- [x] 文档不再给出会把 `codex` 误解析为 ref 的 URL。
- [x] 全部预检命令从 `<skill-dir>/scripts/preflight.py` 执行。
- [x] 渲染和 Office 导入流程分别要求对应 capability。

**验证命令：**

```powershell
python -m pytest tests/skills/test_ppt_video_workbench_preflight.py -q
```

**预期结果：** 退出码 0，安装副本行为测试与能力测试均通过。

**工作目录：** `X:\Projects\01_Active\03_ppt-video-workbench-v3\01_Workspace\worktrees\skill-v012-installability`

**退出码：** 0。

**关键输出：** 安装副本脚本返回 JSON `ready=true`，且文档改动在 Git diff 中可审查。

**证据保存到：** `X:\Projects\01_Active\03_ppt-video-workbench-v3\06_AcceptanceEvidence\x-drive\skill-v012-installability\T03-docs-and-behavior.txt`

**已知基线失败：** README 安装 URL 在含 `/` 的分支名上不可稳定解析，SKILL 硬编码仓库相对脚本路径。

**失败处理：** 如安装器协议发生变化，以官方说明为准调整自然语言安装指令，不回退到歧义 URL。

**回滚方法：** 回退本分支的文档提交。

### T04：运行全量 Skill 验证并形成审查提交

**状态：** COMPLETED

**依赖：** T03

**阻塞后续：** 无

**推荐方案：** 运行目标测试、相关测试、`quick_validate.py`、X 盘合规、计划门禁和 Git 差异复核；通过后以显式文件列表创建本地提交。

**涉及文件：** 所有 T01-T03 文件与 `docs/future-development/` 文档。

**实施内容：** 保存验证证据、复核无关脏改动、提交本分支；不 push、不建 PR、不合并、不发 Release。

**完成标准：**

- [x] 目标测试和相关 Skill 测试均退出码 0。
- [x] Skill 验证器、项目合规和计划门禁均通过。
- [x] 本地提交只包含本计划列出的文件；版本控制的改动清洁，本地 X 盘项目契约文件除外。

**验证命令：**

```powershell
uv run python C:\Users\HanYu\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\ppt-video-workbench; uv run pytest tests/skills -q; .\Test-XProjectCompliance.ps1 -AsJson
```

**预期结果：** 退出码 0，验证器显示有效，pytest 全绿，合规 JSON 的 `passed=true`。

**工作目录：** `X:\Projects\01_Active\03_ppt-video-workbench-v3\01_Workspace\worktrees\skill-v012-installability`

**退出码：** 0。

**关键输出：** `Skill is valid!`、pytest 通过数、`PLAN_READY=PASS`、提交 SHA。

**证据保存到：** `X:\Projects\01_Active\03_ppt-video-workbench-v3\06_AcceptanceEvidence\x-drive\skill-v012-installability\T04-final-verification.txt`

**已知基线失败：** 无已知相关测试失败；正式 v0.1.2 发布未获授权。

**失败处理：** 先修复可复现的范围内失败并复测；外部发布、权限或人工验收阻塞记录为 BLOCKED_HUMAN，不绕过。

**回滚方法：** 使用本分支的提交 SHA 反向提交；不对主分支执行 reset。
