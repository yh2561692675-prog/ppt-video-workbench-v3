# Contributing / 贡献指南

感谢你帮助改进 PPT Video Workbench。项目包含 Python、TypeScript、React、Remotion 和 Windows 发布工具，请让每次变更保持范围清晰、结果可复现。

## Before you start / 开始前

1. 搜索现有 Issue 和 Pull Request，避免重复工作。
2. 对较大的功能或架构变化，先创建 Issue 说明目标、边界和验收方式。
3. 安全漏洞请遵循 [SECURITY.md](SECURITY.md)，不要公开披露。

## Development / 开发

环境准备与启动方式见 [README.md](README.md)。依赖由 `uv.lock` 和 `pnpm-lock.yaml` 固定；除非变更依赖，否则不要无关地刷新锁文件。

建议从默认分支创建短生命周期分支，并保持提交聚焦。新增行为应包含相应测试；涉及 API 或持久化格式时，还应更新契约、迁移和文档。

## Quality gates / 质量门禁

Windows 上提交前运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

若完整门禁受本机运行时限制，请至少运行与改动直接相关的测试，并在 Pull Request 中准确列出已运行和未运行的检查。不要把未执行的人工验收描述为已通过。

## Pull requests / 拉取请求

Pull Request 应说明：

- 问题与解决方案；
- 主要文件和兼容性影响；
- 测试命令与结果；
- 对密钥、隐私、本地文件和外部服务调用的影响；
- UI 变化对应的截图或短视频（不得包含真实项目数据或凭据）。

提交即表示你同意按本仓库的 [MIT License](LICENSE) 提供贡献。
