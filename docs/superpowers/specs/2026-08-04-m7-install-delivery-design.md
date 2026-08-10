# M7 安装与交付设计规格

## 基线与范围

- 基线：`feature/m1-foundation`，M6 合并提交 `713f25c`。
- 范围：Task 32—36，覆盖运行环境诊断、可复现发布清单、Windows 安装启动、稳定版更新/回滚、用户手册与示范项目。
- 本阶段不改变 M1—M6 的项目数据、音频路线、字幕、预检、缓存和渲染契约；安装器只负责部署、启动和更新既有能力。
- 当前 Linux 容器无法执行 Windows VM/Inno Setup 实机验收，因此先把清单、脚本、哈希、健康检查和故障注入做成可自动验证的本地契约，并保留 Windows 脚本作为实机入口。

## 设计原则

1. 诊断只读：缺失、版本不兼容、权限和空间问题输出机器可读 code 与用户可执行 action，不自动修改系统环境。
2. 发布可复现：每个运行时文件必须有相对路径、大小、SHA-256、许可证和角色；开发密钥、`.env`、项目源文件不得进入发布包。
3. 安装可回归：launcher 只绑定 `127.0.0.1`，选择空闲端口，等待 `/api/health` 后打开默认浏览器；重复启动复用或拒绝已有实例。
4. 更新可回滚：只接受稳定版 manifest，下载后先校验哈希；更新前备份配置与项目索引，使用双目录切换，健康检查失败自动恢复旧版本。
5. 文档从 GUI 出发：用户手册不要求命令行；诊断包和示范项目不包含 API Key、认证头或真实源文件正文。

## Task 32：环境报告与诊断包

新增 `EnvironmentDetector` 和 `EnvironmentReport`。组件包括 Python、Node、Remotion、FFmpeg、FFprobe、LibreOffice、OCR、浏览器；系统检查包括项目目录写权限、输出目录写权限、可用磁盘和中文路径读写。

每个检查结果固定包含 `name`、`status`、`version`、`path`、`code`、`message`、`action`、`blocking`。状态只允许 `available`、`missing`、`incompatible`、`unusable`、`skipped`。诊断包为 ZIP，包含报告 JSON、Markdown 和脱敏环境摘要；递归过滤 `api_key`、`authorization`、`cookie`、`token`、源文件正文及项目文件内容。

API 提供 `GET /api/environment` 和 `POST /api/environment/diagnostic-package`，后者返回诊断包相对路径、SHA-256 和报告 ID。

## Task 33：生产构建与运行时清单

新增 `installer/runtime-manifest.json` 作为发布输入，记录发布版本、构建时间、组件版本、许可证列表和 artifacts。验证器拒绝缺文件、大小/哈希不符、许可证缺失、开发密钥残留和路径越界。

`scripts/build-release.ps1` 执行 Web/Remotion 构建、API 发布目录整理、清单生成、SBOM/许可证导出和最终哈希校验；`apps/api/workbench.spec` 固定 PyInstaller 收集入口。脚本支持 Windows 发布机，也保留 `--verify` 语义供 Linux 门禁验证清单。

## Task 34：安装、启动与卸载

`installer/workbench.iss` 固定安装目录、开始菜单/桌面快捷方式、仅本机防火墙绑定和卸载时保留用户项目/配置。`scripts/launcher.ps1` 选择空闲本机端口，启动 API，轮询 `/api/health`，再打开浏览器，并用进程/锁文件防止重复实例。

`tests/release/install-smoke.ps1` 覆盖静默安装、普通安装、中文用户名、无管理员权限、重复安装和卸载保留数据；Linux 侧用脚本结构和 launcher 命令契约测试替代 VM 执行。

## Task 35：稳定版更新与回滚

`UpdateService` 固定接口：`check_update(channel="stable")`、`stage_update(package)`、`apply_update()`、`rollback_update()`。只接受稳定版 manifest，展示版本、说明、大小和注意事项，用户确认后才下载/切换。

更新目录采用 `releases/current` 与 `releases/previous` 双目录；切换前备份 `settings/`、工作区索引和活动版本指针。新版本健康检查失败、迁移异常、哈希不符、磁盘不足或下载中断时，恢复旧目录、旧配置和旧指针；项目目录本身不移动、不覆盖。

前端在设置页显示当前版本、稳定版信息、更新说明、下载大小和“确认更新/回滚”状态；更新接口不返回任何密钥或完整本地路径。

## Task 36：手册与示范项目

新增 `docs/user-guide.md`、`docs/api-setup.md`、`docs/troubleshooting.md`，覆盖安装、七步流程、LLM/HeyGen、两条音频路线、预检、恢复、缓存、更新和错误 code。文档链接检查确保引用页面和接口路径存在。

新增无密钥 `examples/demo-project/`，提供 6—8 页结构化示范 manifest、页面文字、旁白、音频/字幕/预检说明和期望制作包清单；内容使用合成示例，不复制用户源文件。

## M7 Gate

- 环境检查覆盖组件缺失/版本不兼容/空间/权限/中文路径，并生成无敏感信息诊断包。
- 发布清单哈希、许可证、路径和开发密钥门禁通过。
- launcher 健康检查、端口选择、重复实例和卸载保留数据契约通过。
- 稳定版更新 N-1→N 成功；哈希失败、下载中断、磁盘不足、健康检查失败均自动回滚，项目内容不变。
- 文档链接、示范项目结构和无密钥检查通过。
- Windows 10/11 干净 VM 实机步骤与当前 Linux 可复现替代证据分别记录，不把脚本静态检查冒充 VM 通过。
