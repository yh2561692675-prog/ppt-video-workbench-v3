# 排障手册

先在“设置 → 环境与诊断”运行环境检查。每条检查都会给出状态、错误 code、是否阻断和下一步 action；不要为了绕过阻断直接删除项目清单或手动修改缓存。

## 安装与运行环境

| code                             | 含义                                                                   | 处理方式                                                                 |
| -------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `component_missing`              | Python、Node、Remotion、FFmpeg、FFprobe、LibreOffice、OCR 或浏览器缺失 | 重新运行安装器或安装对应运行时，再重新检查；不要把系统目录手动加入发布包 |
| `component_version_incompatible` | 组件版本低于工作台要求                                                 | 使用发布包内版本或升级组件；确认后重新启动                               |
| `disk_space_low`                 | 可用磁盘不足                                                           | 清理可重建缓存和旧诊断包，保留项目与最终制作包后重试                     |
| `workspace_not_writable`         | 工作区无法创建、替换或删除文件                                         | 选择有写权限的本地目录，避免只读同步盘                                   |
| `chinese_path_unsupported`       | 中文目录读写校验失败                                                   | 将工作区移动到支持 Unicode 的本地磁盘，再重新导入                        |

启动器只使用本机地址。如果浏览器没有自动打开，确认 `/api/health` 能在当前端口返回 `status: ok`；如果提示已有实例，先关闭旧窗口或等待旧 API 进程退出，再重试。

## Windows 安装验收（P01）

在源码根目录、已生成安装包后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\tests\release\windows-acceptance.ps1 `
  -InstallerPath .\release\ppt-video-workbench-setup.exe
```

验收报告默认写入 `%TEMP%\PPTVideoWorkbench-P01-Report`，包含 `acceptance-evidence.json`、`acceptance-report.json` 和 `acceptance-report.html`。脚本末尾显示 `P01_WINDOWS_ACCEPTANCE=PASS` 时，安装、两次启动、卸载和用户工作区保留均已获得实机证据；`P01_WINDOWS_ACCEPTANCE=BLOCK` 表示该次结果只能用于排障，不能作为发布放行依据。验收不会删除或迁移 `F:\Video`。

## 导入、匹配和旁白

- 导入失败：确认源文件仍可读取、项目目录有空间，并在项目中心重新选择文件。安全文件名和复制结果可以在项目日志中查看。
- 匹配需要确认：打开候选列表，检查页面顺序、标题和正文，再手动选择正确项；不要把低置信度结果直接送入旁白生成。
- 旁白无法进入音频：确认每页都有当前 revision，处理编辑器中的不足项，并在批量确认面板完成确认。
- LLM 连接失败：在模型设置中重新测试 Base URL 和模型权限；密钥输入框清空是正常的，不代表保存失败。

## 音频、字幕和预检

- `audio_route_mixed`：项目混用了本地录音和 HeyGen。统一整项目路线，或显式替换当前页并重新检查其他页面。
- `audio_revision_mismatch`：音频对应的旁白 revision 已变化。重新生成/导入当前 revision 后再进入字幕。
- `transcript_missing`：先完成转写；没有词级时间戳时不能生成可靠 SRT。
- `subtitle_timing_overlap`：检查词级时间戳和分页边界，保存边界后重新构建字幕。
- `video_preflight_blocked`：打开第 6 步查看具体页面 issue；解决阻断项或对允许确认的问题留下审计确认。

预检报告有输入指纹。页面文字、图片、音频、字幕或模板变化后，旧报告不会被当成最新通过结果；重新运行完整预检即可刷新。

## 更新与回滚

| code                      | 含义                           | 处理方式                                                 |
| ------------------------- | ------------------------------ | -------------------------------------------------------- |
| `stable_channel_required` | 不是受支持的稳定版清单         | 只选择 stable 通道，拒绝测试版或未知来源                 |
| `update_manifest_invalid` | 清单缺字段、版本或哈希格式错误 | 删除损坏清单，重新获取发布包                             |
| `package_hash_mismatch`   | 下载包与清单 SHA-256 不一致    | 不要应用该包，重新下载并检查磁盘/同步软件                |
| `package_size_mismatch`   | 包大小与清单不一致             | 重新下载完整包                                           |
| `disk_space_low`          | 暂存或切换更新前空间不足       | 清理可重建缓存后重试                                     |
| `health_check_failed`     | 新版本切换后健康检查失败       | 系统已自动恢复上一版本；保存诊断包后联系维护者           |
| `migration_failed`        | 更新迁移过程抛出异常           | 系统已自动恢复旧版本和设置，保留日志后重试               |
| `no_previous_release`     | 没有可回滚版本                 | 当前版本是首次安装或旧版本已被清理，重新检查 stable 更新 |

更新只替换 `releases/current`，项目目录不移动。若界面显示“已应用”但浏览器仍是旧页面，完全关闭启动器后再启动一次；若仍异常，先执行环境诊断再使用手动回滚。

## 缓存与长任务恢复

缓存清理前必须确认计划中的路径和受影响节点。若任务中断，重新打开项目后从任务中心重试失败节点；不要删除 `project.json`、设置目录或正在使用的项目源文件。最终制作包和诊断包可另行归档。

更多流程说明见 [用户手册](user-guide.md)，接口路径见 [接口配置说明](api-setup.md)。
