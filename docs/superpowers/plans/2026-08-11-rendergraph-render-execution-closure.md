# RenderGraph 渲染执行闭环逐项实施计划

**设计依据：** `docs/superpowers/specs/2026-08-11-rendergraph-render-execution-closure-design.md`  
**目标：** 让转场、J/L Cut、媒体覆盖层和高级字幕进入真实预览与成片，并用 RenderGraph snapshot 统一所有执行路径。  
**预计工作量：** 10-14 工程师周  
**推荐日历工期：** 2-3 人并行 6-9 周，单人 12-16 周

## 0. 实施原则

- [ ] V2 代码只消费 immutable RenderGraph snapshot。
- [ ] 旧 `ProjectVideoProps` 路径在迁移期保留，但不再承载 V2 新语义。
- [ ] 先冻结契约和 golden fixtures，再实现执行器。
- [ ] 每个阶段都提供 feature flag 和回退路径。
- [ ] 不在 Render Worker 中读取“当前项目状态”或隐式重新编译。
- [ ] 所有失败门禁发生在任务入队前，Worker 只处理已通过 preflight 的 snapshot。
- [ ] 每个阶段完成后运行后端全量、前端全量、Remotion 测试和目标 Windows smoke test。

## Phase 0：基线、契约与开关

### Task 0.1：记录渲染基线（已完成 2026-08-11）

目标文件：

- `docs/acceptance/rendergraph-v2-baseline.md`
- `tests/fixtures/rendergraph-v2/`

工作项：

- [x] 记录当前旧渲染链路、feature flags、测试数量和已知环境门禁。
- [x] 固定至少 4 个代表性项目 fixture：AI 旁白、真人、竖屏、overlay/字幕。
- [x] 保存旧路径关键帧、音频波形、时长、编码和文件 hash 作为迁移对照。
- [x] 明确不允许修改或覆盖的现有 dirty worktree 文件范围。

验收：

- [x] fixture 可在测试中无网络加载。
- [x] 基线报告能定位旧 Props、Remotion、FFmpeg concat 和 preflight 入口。

### Task 0.2：建立 feature flags（已完成 2026-08-11）

目标文件：

- `apps/api/src/workbench/rendering/feature_flags.py`
- `apps/web/src/features/rendering/flags.ts`
- `tests/unit/rendering/test_feature_flags.py`

工作项：

- [x] 增加 compile、preview、export、strict-assets 四个开关。
- [x] 支持环境变量、项目级 renderer generation 和测试覆盖。
- [x] 默认全部关闭，内部 fixture 项目可显式开启。

验收：

- [x] 任一开关关闭时旧路径不受影响。
- [x] V2 独占语义项目禁止错误回退 V1。

### Task 0.3：冻结 RenderGraph V2 Schema（已完成 2026-08-11）

目标文件：

- `apps/api/src/workbench/rendering/models.py`
- `schemas/render-graph-v2.schema.json`
- `remotion/src/render-graph/types.ts`
- `packages/contracts/render-graph-v2.schema.json`
- `tests/contract/test_render_graph_v2.py`
- `remotion/src/render-graph/types.test.ts`

工作项：

- [x] 实现 canvas、source revisions、resolved assets、nodes、transitions、audio mix、subtitle plan、affected ranges。
- [x] 所有模型 `extra=forbid`，ID、revision、hash、时间和路径有严格约束。
- [ ] 定义稳定的 kind-specific payload discriminated union（Phase 1 编译器继续补齐）。
- [x] 导出 JSON Schema 和 TypeScript 镜像。
- [ ] 建立 Python/TypeScript 共享 fixture（当前为双端等价内嵌 fixture，待改为单一文件源）。

验收：

- [x] Python 生成的 fixture 可被 TypeScript 解析，反向 fixture 也通过 Python 校验。
- [x] 相同语义的序列化 hash 与字段顺序无关。

**Phase 0 Gate：** V2 schema、帧量化规则和 feature flags 冻结（已通过：后端全量 624 项、Remotion 31 项、Web 74 项；Ruff 与 mypy 通过）。

## Phase 1：权威 RenderGraph 编译器

### Task 1.1：建立 rendering 包与 snapshot store

目标文件：

- `apps/api/src/workbench/rendering/__init__.py`
- `apps/api/src/workbench/rendering/snapshot_store.py`
- `apps/api/src/workbench/rendering/hashing.py`
- `tests/unit/rendering/test_snapshot_store.py`

工作项：

- [x] graph snapshot 使用 graph ID 目录和 immutable `graph.json`。
- [x] 临时写入、flush/fsync、hash 校验、原子 replace。
- [x] current pointer 只保存 graph ID/hash，不复制 graph 内容。
- [x] snapshot 加载时重新校验 schema 和 hash。

验收：

- [x] 半写入、损坏 JSON、hash 不匹配快速失败。
- [x] 已存在相同 hash 的 snapshot 幂等返回。

### Task 1.2：统一时间与帧量化

目标文件：

- `apps/api/src/workbench/rendering/timebase.py`
- `remotion/src/render-graph/timebase.ts`
- `tests/fixtures/rendergraph-v2/timebase.json`
- `tests/unit/rendering/test_timebase.py`

工作项：

- [x] 实现微秒到 frame 的 floor-start/ceil-end。
- [ ] 覆盖 24/25/30/60fps、非整帧边界和长视频（当前 fixture/回归覆盖 30fps，扩展测试待补）。
- [x] 防止浮点参与 graph hash。

验收：

- [ ] Python/TypeScript 对每个 fixture 得到相同帧边界（当前已各自通过 30fps 等价测试，统一 fixture 读取待补）。
- [x] 时长误差不超过 1 帧。

### Task 1.3：AssetResolver

目标文件：

- `apps/api/src/workbench/rendering/asset_resolver.py`
- `tests/unit/rendering/test_asset_resolver.py`

工作项：

- [x] 将 timeline/continuity/subtitle source ref 解析为 AssetRecord revision。
- [x] 校验 project scope、路径 containment、文件存在、size/hash 和媒体元数据（媒体探针结果写入 resolved asset，并由 preflight 校验）。
- [x] 选择 interactive proxy、authoritative proxy 或 final asset。
- [x] 将字体、LUT、alpha 模式写入 resolved asset。
- [x] 兼容旧项目路径时建立显式 legacy asset snapshot，不允许直接透传任意路径。

验收：

- [x] 路径逃逸、软链接逃逸、文件替换、媒体元数据和 hash 错误被阻断。
- [x] 相同 asset revision 解析结果确定。

### Task 1.4：核心 GraphCompiler

目标文件：

- `apps/api/src/workbench/rendering/compiler.py`
- `apps/api/src/workbench/rendering/indexes.py`
- `tests/unit/rendering/test_compiler.py`

工作项：

- [ ] 按 expected revisions 加载 timeline、continuity、subtitle、effect 和 preset。
- [ ] 规范化 track order、z-index、source range 和节点依赖。
- [ ] 生成确定性 node ID、transition edge、cache key 和 graph hash。
- [ ] 返回 affected ranges。
- [ ] 检测未声明 overlap、孤立 transition、重复 node 和 duration 越界。

验收：

- [ ] 1,000 节点编译 p95 < 500ms，不含媒体探测。
- [ ] 相同输入重复编译得到相同 graph hash。

### Task 1.5：ContinuityPlan 编译

目标文件：

- `apps/api/src/workbench/rendering/continuity_compiler.py`
- `tests/unit/rendering/test_continuity_compiler.py`

工作项：

- [ ] 将 from/to page 映射为具体 visual node。
- [ ] 校验 dissolve/wipe/slide/match overlap。
- [ ] 将 overlay 转为 visual node 并解析 z-index、rect、mask、enter/exit。
- [ ] 将 chapter 写入 graph index，供 J/L Cut 门禁使用。

验收：

- [ ] 非 cut transition 的 edge range 与 visual overlap 完全一致。
- [ ] overlay source 和 license 均来自 AssetResolver。

### Task 1.6：SubtitlePlan 编译

目标文件：

- `apps/api/src/workbench/rendering/subtitle_compiler.py`
- `apps/api/src/workbench/rendering/layout_resolver.py`
- `tests/unit/rendering/test_subtitle_compiler.py`

工作项：

- [ ] 编译多语言 track、cue、word timing、style template 和 override。
- [ ] 解析 burn_in/soft/both/none。
- [ ] 统一处理人工换行和双语布局。
- [ ] 综合 presenter、overlay 和安全区输出 resolved rect。
- [ ] 字体只能引用注册 AssetRecord。

验收：

- [ ] cue/word 越界阻断。
- [ ] 同一画幅和输入得到确定布局。

### Task 1.7：AudioMixPlan 编译

目标文件：

- `apps/api/src/workbench/rendering/audio_compiler.py`
- `tests/unit/rendering/test_audio_compiler.py`

工作项：

- [ ] narration、presenter、music、sfx 映射到独立 bus。
- [ ] J/L Cut 改写 timeline audio range，不修改源文件。
- [ ] 生成 fade、gain、pan、crossfade、ducking automation。
- [ ] 校验 source duration、graph duration 和 chapter range。

验收：

- [ ] J/L Cut fixture 边界准确。
- [ ] 音频修改不影响无关视觉 cache key。

### Task 1.8：RenderGraph API

目标文件：

- `apps/api/src/workbench/api/render_graph.py`
- `apps/api/src/workbench/main.py`
- `tests/integration/test_render_graph_routes.py`

工作项：

- [x] compile/current/get/preflight/affected-ranges API。
- [ ] expected revision 冲突返回 409 和具体 code。
- [ ] `/timeline/compile` 在 flag 开启时转发 V2 compiler。

验收：

- [x] API 不暴露未校验路径。
- [x] graph snapshot 可按 ID/hash 重读。

**Phase 1 Gate：** timeline、continuity、subtitle、asset、audio 和 preset 全部进入唯一 V2 graph。

## Phase 2：导出前严格门禁

### Task 2.1：GraphPreflight

目标文件：

- `apps/api/src/workbench/rendering/preflight.py`
- `apps/api/src/workbench/preflight/checks/render_graph.py`
- `apps/api/src/workbench/preflight/engine.py`
- `tests/unit/preflight/test_render_graph_check.py`

工作项：

- [ ] 增加 render_graph、assets、continuity、subtitle_v2、audio_mix、output_contract scopes。
- [ ] issue fingerprint 包含 graph hash 和相关 source revisions。
- [ ] 阻断问题不可被旧 video preflight 结果覆盖。

### Task 2.2：素材授权门禁

目标文件：

- `apps/api/src/workbench/rendering/license_gate.py`
- `tests/unit/rendering/test_license_gate.py`

工作项：

- [ ] blocked、expired、项目范围不符直接阻断。
- [ ] unknown 在正式导出中默认阻断。
- [ ] 授权到期时间与预计交付时间比较。
- [ ] 项目级确认必须记录 actor、note、timestamp、asset revision 和 graph hash。
- [ ] 字体执行相同授权规则。

### Task 2.3：越界与输出门禁

- [ ] node、source、overlay、transition、J/L Cut、cue/word 全部边界检查。
- [ ] 检查主视觉未声明 overlap。
- [ ] 检查 preset width/height/fps/codec 和字幕轨要求。
- [ ] graph 或 preflight hash 不匹配时禁止入队。

**Phase 2 Gate：** 缺失、授权失效、hash 错误和所有时间越界均在 Job 入队前阻断。

## Phase 3：Remotion 全片视觉执行器

### Task 3.1：RenderGraphComposition

目标文件：

- `remotion/src/render-graph/RenderGraphComposition.tsx`
- `remotion/src/Root.tsx`
- `remotion/src/render-graph/GraphContext.tsx`
- `remotion/src/render-graph/RenderGraphComposition.test.tsx`

工作项：

- [ ] 只接受 graph、executionMode、assetBaseUrl。
- [ ] 按 graph canvas/fps/duration 注册 composition。
- [ ] 实现 background、visual、effect、presenter、overlay、subtitle 层级。
- [ ] 任意 seek 帧输出仅由 graph 和 frame 决定。

### Task 3.2：视觉节点解释器

目标文件：

- `remotion/src/render-graph/VisualNode.tsx`
- `remotion/src/render-graph/SlideNode.tsx`
- `remotion/src/render-graph/PresenterNode.tsx`
- `remotion/src/render-graph/EffectNode.tsx`

- [ ] slide 和 effect 复用现有 PageScene/EffectPlan 解释器。
- [ ] presenter 使用 graph 中已解析的 layout segment。
- [ ] 支持 proxy/final asset resolution。
- [ ] 移除 V2 路径对 `props.pages` 的依赖。

### Task 3.3：TransitionLayer

目标文件：

- `remotion/src/render-graph/TransitionLayer.tsx`
- `remotion/src/render-graph/transitions/`

- [ ] 实现 cut、dissolve、wipe、slide、match。
- [ ] easing 与 graph edge 一致。
- [ ] 缺少 match 参数时显示明确错误，不静默猜测。
- [ ] 起点/中点/终点视觉快照测试。

### Task 3.4：OverlayLayer

目标文件：

- `remotion/src/render-graph/OverlayLayer.tsx`
- `remotion/src/render-graph/OverlayNode.tsx`

- [ ] image/video/logo/sticker/text。
- [ ] contain/cover/fill、mask、opacity、enter/exit、z-index。
- [ ] alpha 图片和 alpha 视频。
- [ ] presenter/subtitle 安全区 visual test。

### Task 3.5：SubtitleLayer V2

目标文件：

- `remotion/src/render-graph/SubtitleLayerV2.tsx`
- `remotion/src/render-graph/WordHighlight.tsx`
- `remotion/src/render-graph/fonts.ts`

- [ ] 字体、字号、颜色、描边、背景、位置。
- [ ] 单语、双语、人工断句。
- [ ] word timing 驱动逐词高亮。
- [ ] soft/none 不渲染可见层。
- [ ] 竖屏、方屏、presenter 和 overlay 冲突回归。

### Task 3.6：Python Remotion runner 切换全片 composition

目标文件：

- `apps/api/src/workbench/rendering/remotion_runner.py`
- `apps/api/src/workbench/video/render_service.py`
- `tests/unit/rendering/test_remotion_runner.py`

- [ ] V2 一次渲染全片 video-only。
- [ ] 传入 graph snapshot，而不是动态 ProjectVideoProps。
- [ ] 保留 checkpoint、pause/cancel、timeout 和 runtime detection。
- [ ] 旧 PageRenderer 仅供 V1 fallback。

**Phase 3 Gate：** V2 全片视觉输出可执行真实 transition、overlay 和 burn-in 字幕，且没有分页 concat。

## Phase 4：FFmpeg 音频、字幕与最终封装

### Task 4.1：AudioFilterCompiler

目标文件：

- `apps/api/src/workbench/rendering/ffmpeg_audio.py`
- `tests/unit/rendering/test_ffmpeg_audio.py`
- `tests/fixtures/rendergraph-v2/audio-filter/`

- [ ] ordered inputs 和 deterministic filter_complex。
- [ ] atrim/asetpts/adelay/afade/volume/pan/amix。
- [ ] music ducking、crossfade、loudnorm、alimiter。
- [ ] Windows 路径和 FFmpeg filter escaping。
- [ ] filter snapshot 测试不得包含临时绝对路径。

### Task 4.2：真实 J/L Cut 验证

- [ ] 生成带可识别 tone/voice 边界的 fixture。
- [ ] J Cut 在下一画面前进入，L Cut 在下一画面后结束。
- [ ] 通过 waveform/ffprobe 自动验证边界误差 < 20ms。
- [ ] chapter 和 source duration 越界测试。

### Task 4.3：字幕产物与 soft track

目标文件：

- `apps/api/src/workbench/rendering/subtitle_packager.py`
- `tests/unit/rendering/test_subtitle_packager.py`

- [ ] 从 SubtitleRenderPlan 生成 SRT、WebVTT、ASS。
- [ ] soft/both 模式 mux MP4 subtitle track。
- [ ] 每个语言轨写 language/title metadata。
- [ ] burn-in/soft/both/none 产物矩阵测试。

### Task 4.4：FinalMuxService

目标文件：

- `apps/api/src/workbench/rendering/final_mux.py`
- `apps/api/src/workbench/video/package_service.py`
- `tests/unit/rendering/test_final_mux.py`

- [ ] 输入 video-only、master audio 和 soft subtitle tracks。
- [ ] 读取 ExportPreset 的画布、fps、codec、bitrate 和 pixel format。
- [ ] metadata 写入 graph hash、timeline revision 和 preset ID。
- [ ] ffprobe 校验时长、音轨、字幕轨和编码参数。

**Phase 4 Gate：** J/L Cut、混音、soft/both 字幕和最终 mux 在真实 FFmpeg 上通过。

## Phase 5：预览与正式渲染切换

### Task 5.1：RenderGraph Player

目标文件：

- `apps/web/src/features/rendering/RenderGraphPreview.tsx`
- `apps/web/src/features/video/PreviewWorkspace.tsx`
- `apps/web/src/api/client.ts`

- [ ] Player 使用 graph snapshot，不再使用旧 VideoPreflight props。
- [ ] 支持 proxy asset、affected ranges 和播放头预取。
- [ ] 展示 graph revision/hash 和 stale 状态。
- [ ] diagnostics overlay 显示缺失代理或预览降级。

### Task 5.2：权威区间预览 Job

- [ ] 提交 graph ID、range 和 preview preset。
- [ ] Remotion video proxy 和 FFmpeg audio proxy 使用同一 graph。
- [ ] 缓存键包含 graph hash、range 和 runtime version。
- [ ] 预览与最终成片边界对比测试。

### Task 5.3：RenderJobService 绑定 graph snapshot

目标文件：

- `apps/api/src/workbench/video/render_job.py`
- `apps/api/src/workbench/jobs/repository.py`
- `apps/api/src/workbench/jobs/execution.py`
- `tests/unit/video/test_render_job.py`

- [ ] submit 必须接受 graph ID/hash。
- [ ] payload 保存 snapshot path/hash，不保存动态 Props。
- [ ] Job fingerprint 来源为 graph hash + preset + runtime generation。
- [ ] Worker 开始前重新验证 snapshot hash，但不重新编译。
- [ ] 项目之后修改不会改变已提交 Job 输入。

### Task 5.4：制作包与质量报告

- [ ] 制作包包含 graph、audio plan、subtitle plan、preflight、runtime manifest。
- [ ] 导出结果记录全部 source revisions 和 encoder version。
- [ ] QualityJob 关联 graph ID/hash。
- [ ] 发布 exactly-once 和缓存结果校验继续有效。

### Task 5.5：旧 API 兼容投影

- [ ] `/video/preflight` 在 V2 返回 graph preflight 的兼容结构。
- [ ] `/video/render-jobs` V2 必须带 graph ID。
- [ ] V1 项目继续走旧 Props。
- [ ] 审计 legacy fallback。

**Phase 5 Gate：** 第 6 步预览和第 7 步正式渲染都绑定同一 graph hash。

## Phase 6：迁移、性能与发布

### Task 6.1：LegacyProjectAdapter

目标文件：

- `apps/api/src/workbench/rendering/legacy_adapter.py`
- `tests/unit/rendering/test_legacy_adapter.py`

- [ ] 从 ProjectManifest、旧 subtitle artifact 和 page timeline 建立 legacy ProductionTimeline。
- [ ] 将旧路径注册为内容寻址 asset snapshot。
- [ ] 无 V2 语义时允许安全回退。
- [ ] V2 独占语义项目明确禁止 V1 fallback。

### Task 6.2：缓存与增量失效

- [ ] 字幕、音频、overlay、transition、画幅变更分别验证失效范围。
- [ ] soft subtitle 修改不重渲 video-only。
- [ ] J/L Cut 修改不重渲视觉层。
- [ ] graph affected ranges 驱动预览缓存清理。

### Task 6.3：性能基准

- [ ] 1,000 节点全量编译 p95 < 500ms。
- [ ] 增量编译 p95 < 150ms。
- [ ] 交互预览首次播放 p95 < 3 秒。
- [ ] 10 秒权威预览缓存命中 p95 < 8 秒。
- [ ] 1080p30 graph 解释开销 < 10%。

### Task 6.4：完整测试矩阵

- [ ] 后端 unit/integration/contract 全量。
- [ ] 前端 Vitest/typecheck 全量。
- [ ] Remotion visual snapshots。
- [ ] FFmpeg audio waveform 和 probe。
- [ ] Playwright 项目生命周期。
- [ ] 16:9、9:16、1:1；24/25/30/60fps；1080p/4K。
- [ ] Windows packaged runtime smoke test。

### Task 6.5：灰度与切换

- [ ] compile-only。
- [ ] V2 preview。
- [ ] 内部 V2 export。
- [ ] 新项目默认 V2。
- [ ] 一个发布周期观察错误率、回退率和性能。
- [ ] 冻结 V1 新功能，另立项目删除旧路径。

**最终 Gate：** 设计文档第 17 节发布门禁全部通过。

## 验收矩阵

| 场景                      |       预览 |         正式渲染 | 自动验证                |
| ------------------------- | ---------: | ---------------: | ----------------------- |
| dissolve/wipe/slide/match |       必须 |             必须 | 关键帧截图              |
| J Cut/L Cut               |       必须 |             必须 | waveform + 20ms 边界    |
| image/video/logo overlay  |       必须 |             必须 | z-order/alpha 截图      |
| 单语/双语烧录字幕         |       必须 |             必须 | 截图 + cue timing       |
| soft/both subtitle        |     可选择 |             必须 | ffprobe subtitle stream |
| word highlight            |       必须 |             必须 | frame fixture           |
| 缺失素材/hash 错误        |       阻断 |             阻断 | preflight code          |
| expired/blocked license   | 提示或阻断 |             阻断 | preflight code          |
| source/overlay/cue 越界   |       阻断 |             阻断 | compiler/preflight      |
| graph stale after enqueue | 标记 stale | 按 snapshot 完成 | job input hash          |
| 旧 V1 项目                |     旧预览 |           旧渲染 | fallback test           |

## 推荐开展顺序

1. Phase 0：契约、fixtures、开关。
2. Phase 1：完整 RenderGraph V2 编译器。
3. Phase 2：严格 preflight，确保错误不进入执行器。
4. Phase 3：Remotion 全片视觉、转场、overlay、烧录字幕。
5. Phase 4：FFmpeg J/L Cut、混音、软字幕和 mux。
6. Phase 5：预览和正式 Job 切换到 graph snapshot。
7. Phase 6：迁移、性能、Windows 验收和灰度发布。

在 Phase 1 Gate 通过前不得开始正式执行器切换；在 Phase 2 Gate 通过前不得让 V2 Job 进入生产队列；在 Phase 4 Gate 通过前不得默认启用 V2 export。
