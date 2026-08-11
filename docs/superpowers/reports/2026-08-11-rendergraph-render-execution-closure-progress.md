# RenderGraph V2 渲染执行闭环进度

更新时间：2026-08-11

本进度文件用于与实施计划对照，避免重复开发。旧的 V1 渲染路径仍保留，RenderGraph V2 导出默认关闭，需显式开启 feature flag。

## 已完成

- RenderGraph V2 schema、Python/TypeScript 类型镜像、时间量化和 immutable snapshot store。
- Timeline/Continuity/Subtitle/Asset 输入编译为统一 graph；支持 transition、overlay、J/L Cut、字幕模式和 affected ranges。
- AssetResolver 的项目范围、legacy snapshot、proxy/final 选择、文件 hash/size 和媒体探测结果；GraphPreflight 会拦截授权、项目范围、素材缺失、hash/size/媒体元数据、时间越界和字幕越界。
- Remotion 全片 `RenderGraphV2` composition、transition/overlay/subtitle layers 和 Player 预览。
- FFmpeg 音频 filter graph、J/L Cut 时间改写、SRT/WebVTT/ASS 产物、soft/burn-in/both/none 字幕封装和 final mux。
- RenderJob V2 在入队时固定 graph hash/snapshot，Worker 只加载固定 snapshot；成功结果在复用前校验 graph hash、MP4、制作包和 artifact manifest。
- 导出流水线在 Remotion、master audio、final mux 三个阶段检查非空产物，并生成 `render-manifest.json` 和 `制作包清单.json`。
- V2 compile API 支持 expected revision 冲突返回 409；current/get/preflight/affected-ranges API 已提供。

## 当前开关

```text
WORKBENCH_RENDERGRAPH_V2_COMPILE=true
WORKBENCH_RENDERGRAPH_V2_PREVIEW=true
WORKBENCH_RENDERGRAPH_V2_EXPORT=true
WORKBENCH_RENDERGRAPH_V2_STRICT_ASSETS=true
WORKBENCH_RENDERER_GENERATION=v2
```

生产环境暂不应直接打开 export；先完成真实媒体、FFmpeg/ffprobe 和 Windows packaged runtime smoke test。

## 本轮验证

- 后端 RenderGraph/视频任务/路由/契约目标测试：38 passed。
- Remotion：31 passed，TypeScript build passed。
- Web：38 files / 74 tests passed，TypeScript stage passed。
- Ruff targeted checks passed。
- Web Vite 产物阶段仍受现有 `apps/web/dist/assets` Windows EPERM 文件锁/权限影响；不是 TypeScript 错误，也未删除该目录。

## 后续顺序

1. 从统一 fixture 文件驱动 Python/TypeScript 帧边界和 graph 解析测试。
2. 补齐真实媒体 fixture 的 ffprobe/waveform/字幕流验证，以及 24/25/30/60fps、16:9/9:16/1:1 矩阵。
3. 增加权威区间预览 Job、preview cache key 和 graph affected-ranges 失效。
4. 将 V2 graph 查询/编译开关接入 Web 工作流，在不改变 V1 默认行为的前提下显示 stale/diagnostics 状态。
5. 完成 Windows packaged runtime smoke、内部灰度导出后再切换新项目默认 V2。
