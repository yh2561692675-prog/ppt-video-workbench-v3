# PPT Video Workbench

> A local-first, auditable workbench for turning presentations and supporting documents into narrated videos.
>
> 一个本地优先、过程可审计的 PPT 讲解视频制作工作台。

PPT Video Workbench 将 PPTX、DOCX、PDF 和图片素材组织成一条完整的视频制作流水线：素材解析、页面匹配、旁白编辑、语音制作、字幕校准、效果预检、Remotion 渲染与制作包导出。项目数据默认保留在本机；只有用户主动配置并调用的外部服务会接收相应请求。

项目当前处于积极开发阶段（`0.1.x`）。核心流程、测试和 Windows 打包基础已经进入仓库，但正式 Windows 发布仍需完成仓库中标注的人工验收门禁。

## Why this project matters / 项目价值

制作高质量讲解视频通常需要在演示文稿、文案、配音、字幕和渲染工具之间反复搬运数据。本项目希望提供一个可复现、可恢复、可检查的开源工作流，让教育者、开发者和内容团队能够：

- 在一套本地工作台中管理从材料导入到视频导出的完整过程；
- 选择本地录音，或按需接入兼容 OpenAI 的 LLM 与 HeyGen；
- 保留 revision、输入指纹、预检报告和产物哈希，便于复核与恢复；
- 复用页面级缓存，并在长时间渲染任务中支持暂停、取消和失败重试；
- 在不配置任何 API Key 的情况下运行本地编辑与本地录音流程。

## Core capabilities / 核心能力

- **材料导入与解析**：支持 PPTX、DOCX、PDF 和图片，记录安全文件名、大小与 SHA-256。
- **旁白与音频**：支持本地编辑、本地录音、可选 LLM 辅助和可选 HeyGen 语音合成。
- **字幕工作台**：基于转写结果生成并校准词级时间轴与 SRT。
- **效果与渲染**：使用 Remotion、Node.js、FFmpeg/FFprobe 构建页面预览和最终视频。
- **可靠性与审计**：异步任务队列、检查点、原子产物切换、诊断包和发布门禁。
- **安全边界**：服务仅监听 `127.0.0.1`；密钥不写入项目清单、日志或诊断包。

## Repository layout / 仓库结构

| 路径                  | 内容                                       |
| --------------------- | ------------------------------------------ |
| `apps/api`            | FastAPI 后端、领域逻辑与本地任务执行       |
| `apps/web`            | React + Vite 工作台界面                    |
| `remotion`            | Remotion 视频组合与渲染逻辑                |
| `peripheral-platform` | 可选、可降级的本机外围任务底座             |
| `packages/contracts`  | OpenAPI、JSON Schema 与共享契约            |
| `tests`               | 单元、集成、契约、安全、性能和发布门禁测试 |
| `docs`                | 用户、接口、排障、架构决策和实施状态文档   |

## Quick start from source / 从源码启动

### Prerequisites / 环境要求

- Windows 10/11（当前主要支持和验收平台）
- Python `3.12`
- [uv](https://docs.astral.sh/uv/)
- Node.js 与 Corepack
- pnpm `11.7.0`（版本已在 `package.json` 固定）

### Install / 安装依赖

```powershell
git clone https://github.com/yh2561692675-prog/ppt-video-workbench-v3.git
cd ppt-video-workbench-v3

uv sync --frozen
corepack enable
pnpm install --frozen-lockfile
```

### Run in development / 开发模式运行

终端 1：启动后端。

```powershell
$env:WORKBENCH_WORKSPACE = "$PWD\workspace-data"
uv run uvicorn workbench.main:app `
  --app-dir apps/api/src `
  --host 127.0.0.1 `
  --port 8765 `
  --reload
```

终端 2：启动前端。

```powershell
pnpm --filter @workbench/web dev -- --port 5173
```

打开 <http://127.0.0.1:5173>。后端健康检查位于 <http://127.0.0.1:8765/api/health>。

本地编辑和本地录音流程不需要外部密钥。若要使用 LLM 或 HeyGen，请在工作台设置页安全保存凭据；不要把密钥写入源码、`.env.example`、Issue、日志或截图。

## Checks / 质量检查

Windows 上运行完整检查：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

该脚本会同步锁定依赖，并执行 Ruff、Mypy、Pytest、ESLint、Prettier、TypeScript 检查和前端测试。Linux/macOS 可使用 `bash scripts/check.sh`；当前发布打包与人工验收仍以 Windows 为准。

## Documentation / 文档

- [用户手册](docs/user-guide.md)
- [接口配置说明](docs/api-setup.md)
- [排障手册](docs/troubleshooting.md)
- [更新日志](CHANGELOG.md)
- [贡献指南](CONTRIBUTING.md)
- [安全政策](SECURITY.md)
- [维护者指南](docs/maintainer-guide.md)

## Contributing and license / 贡献与许可

欢迎提交可复现的 Issue 和范围清晰的 Pull Request。开始前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)；安全问题请按 [SECURITY.md](SECURITY.md) 私下报告，不要公开披露密钥或漏洞细节。

本项目采用 [MIT License](LICENSE)。
