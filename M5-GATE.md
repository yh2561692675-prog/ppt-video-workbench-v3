# M5 Gate：视频预览与导出

日期：2026-08-04
分支：`feature/m5-video-system`

## 范围

本阶段完成 Task 22—26：

- Task 22：从 `PageAudio[]`、词级时间戳和已确认旁白生成无重叠 `SubtitleCue[]`，并落盘 SRT 与字幕时间轴。
- Task 23：冻结 Python/TypeScript 一致的 `ProjectVideoProps`，固定 1920×1080、16:9、30 FPS 与毫秒到帧的换算。
- Task 24：实现科技风 Remotion 整页模板，包括整页推拉、扫描线、中心雾化、前进网格、聚焦框、关键词发光、帧级字幕、避让底板、安全区和 reduced-motion。
- Task 25：实现基于 `@remotion/player` 的预览会话、字幕避让、预检报告及第 6/7 步的前后端门禁；预检和 reduced-motion 设置持久化到项目清单。
- Task 26：以 Remotion 分页 MP4 为生产渲染器，完成输入指纹缓存、失败页重试、FFmpeg H.264/AAC 合成、逐页/成片 ffprobe 时长校验和完整制作包导出。

## 完整制作包

`POST /api/projects/{project_id}/video/render` 在预检通过后生成：

- `最终视频.mp4`
- `字幕.srt`
- `旁白确认版.docx`
- `分页音频/page-*.wav`
- `Remotion工程/ProjectVideoProps.json`
- `预检报告.json`
- `日志清单.json`
- `制作包清单.json`

制作包清单为每个文件记录相对路径、字节数和 SHA-256；输出根目录校验不允许越界路径或缺失文件。渲染缓存按页面输入指纹复用，指纹包含页面预览图 SHA-256、页面时间、字幕、避让位置、模板版本与 reduced-motion；单页失败只重试该页，不重复成功页面。API 不会暴露 Remotion 或 FFmpeg 的原始错误输出；失败导出会写入安全错误码和审计事件。

## 阶段验收证据

| 检查项                   | 结果                          |
| ------------------------ | ----------------------------- |
| Python 测试              | 170 passed                    |
| Ruff                     | passed                        |
| 严格 mypy                | 87 个源文件无错误             |
| Web 测试                 | 21 passed，13 files           |
| Remotion 测试            | 5 passed，2 files             |
| TypeScript               | passed                        |
| ESLint + Prettier        | passed                        |
| 生产构建                 | passed                        |
| OpenAPI / Project Schema | passed                        |
| Playwright 生命周期回归  | 1 passed                      |
| 8 页受控导出链路         | 字幕→预检→分页渲染→制作包通过 |

8 页集成 fixture 使用真实 WAV 音频和页面图像，完成 2000 ms 视频导出，并验证 H.264/AAC、1920×1080、逐页音频、SRT、DOCX、Remotion 参数、预检报告、日志和制作包清单均存在。2 页制作包回归另外验证了页缓存命中、失败页单独重试、文件哈希/大小、越界路径阻断、字幕时间戳重叠阻断、真实时长容差和失败审计。浏览器预览使用同一份已持久化 Props，并通过受限资产接口读取项目内图像和音频。

统一复核命令：

```bash
bash scripts/check.sh
PLAYWRIGHT_BROWSERS_PATH=/tmp/ppt-video-workbench-playwright pnpm exec playwright test
```

## 实机补充项

真实 10 分钟普通话 WER/RTF、人工试听、Windows CUDA/DPAPI、真实 HeyGen 小额调用以及 Windows FFmpeg 编码器差异仍需在目标 Windows 环境补充验收；本 Gate 不以离线 fixture 冒充这些实机证据。另有一项必须在目标 Windows 环境执行：配置 `WORKBENCH_REMOTION_BROWSER_EXECUTABLE` 后运行真实 Remotion 分页渲染并检查制作包。本 Linux 容器的 Chromium 被沙箱限制在 `os.networkInterfaces` 初始化阶段，无法作为该实机证据；生产代码会返回受控失败，不会回退为静态 PNG 视频。
