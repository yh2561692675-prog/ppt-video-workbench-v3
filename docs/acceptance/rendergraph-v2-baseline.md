# RenderGraph V2 迁移基线

日期：2026-08-11  
阶段：Phase 0 / Task 0.1（离线基线）

## 当前旧渲染链路

当前正式路径仍由 Python API 组装 `ProjectVideoProps`，Remotion 负责页面/效果视觉渲染，FFmpeg concat 与最终 mux 负责成片封装，导出前由既有 video preflight 和质量探针执行检查。现有时间线 RenderGraph 骨架位于 `apps/api/src/workbench/timeline/production.py`，只表达 V1 `RenderNode`，尚未成为 V2 执行权威。

主要入口：

- `apps/api/src/workbench/video/render_service.py`：运行时与 Remotion 渲染服务。
- `apps/api/src/workbench/rendering/exporter.py`：presenter 失败降级到 PPT/字幕/主音轨。
- `apps/api/src/workbench/timeline/production.py`：V1 ProductionTimeline/TimelineCompiler。
- `apps/api/src/workbench/preflight/`：导出前检查与 FFmpeg 能力探针。
- `remotion/src/`：现有页面、效果、presenter 和字幕组合。

## 开关与测试基线

RenderGraph V2 开关在本阶段默认关闭；`WORKBENCH_RENDERER_GENERATION=v1` 保持旧路径。已有 Effects V2 开关仍独立管理。最近一次完整验证结果为后端 624 个测试通过（2 个既有 Pydantic 警告）、Web 74 个测试通过、Remotion 31 个测试通过；Windows P01 隔离安装验收通过。真实 Office、真人、竖屏和 Playwright 成片证据仍是后续门禁，不在本离线基线中伪造。

## 离线迁移 fixtures

`tests/fixtures/rendergraph-v2/manifest.json` 固定四类代表项目：AI 旁白、真人 presenter、9:16 竖屏、overlay/字幕。fixture 只包含可审计的画布、时长、旧入口和输出占位元数据，`network_required=false`，测试不会加载网络或外部媒体。真实旧输出尚未在本阶段重新渲染，因此关键帧、波形和文件 hash 明确记录为空，而不是伪造 hash。

## Dirty worktree 保护范围

本阶段只新增本报告、`tests/fixtures/rendergraph-v2/`、RenderGraph flags、schema 与契约测试；不覆盖既有 dirty worktree 文件，不重建安装包，不修改 P1/P2 Provider/Cloud 实现，不执行 clean/reset/checkout/prune/gc。后续阶段必须继续保留当前 release、acceptance、cache 和用户未提交文件。
