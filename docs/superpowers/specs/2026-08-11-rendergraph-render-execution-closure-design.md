# RenderGraph 渲染执行闭环设计

**日期：** 2026-08-11  
**状态：** Proposed  
**范围：** 转场、J/L Cut、媒体覆盖层、高级字幕、唯一 RenderGraph、导出前门禁  
**目标仓库：** `F:\ppt-video-workbench-v3`

## 1. 目标

本项目把已经存在但彼此分离的时间线、连续镜头、字幕工作台、素材注册表、Remotion 预览和 FFmpeg 导出收敛为一条可恢复、可复现的渲染执行链路。

完成后必须满足：

1. `ProductionTimeline` 是编辑时间的唯一权威。
2. `RenderGraph V2` 是预览、正式渲染、质量检测和制作包的唯一执行输入。
3. 转场、J/L Cut、overlay、字幕样式不再只是保存配置，而是实际改变预览和成片。
4. 预览和正式渲染可以使用不同质量的代理文件，但必须遵守完全相同的时间、层级、转场和音频语义。
5. 每个渲染任务绑定不可变的 graph revision、graph hash、素材 revision 和字幕 revision。
6. 素材缺失、授权失效、时间越界、非法重叠等问题必须在任务入队前阻断。

## 2. 当前实现与缺口

### 2.1 当前正式渲染链路

当前正式链路仍然是：

```text
ProjectManifest
  -> SubtitleTimeline V1
  -> VideoPropsService
  -> ProjectVideoProps V1/V2
  -> 按页调用 RemotionPageRenderer
  -> 每页视频与音频 mux
  -> FFmpeg concat -c copy
  -> 制作包
```

主要限制：

- `ProjectVideoProps` 只接受两种画布和固定 30fps。
- 页面按不重叠区间顺序渲染，无法执行真正跨页重叠转场。
- 音频按页 mux，J Cut、L Cut、跨页淡化和总线混音无法表达。
- Remotion 仍读取旧字幕 cue，只渲染固定字体、字号和单语文本。
- overlay、连续镜头和高级字幕文档没有进入 `ProjectVideoProps`。
- 渲染 Job 的 fingerprint 仍来自旧 preflight props，而不是新 RenderGraph。

### 2.2 当前 RenderGraph 骨架

`workbench.timeline.production` 已有微秒时间、track、clip、marker、revision、命令、内容 hash、确定性节点 ID 和基础依赖。

当前 `RenderGraph 1.0` 仍缺少：

- clip payload 的执行期规范化结果。
- transition 边和真实 overlap 区间。
- z-order、混合模式、布局、安全区和画幅解析结果。
- AssetRecord revision、content hash 和实际对象路径。
- SubtitleDocument revision、style template 和 cue/word timing。
- 音频 bus、gain envelope、crossfade、ducking 和 J/L Cut。
- continuity、effect catalog、export preset 等源 revision。
- 受影响区间和增量缓存失效信息。

### 2.3 已存在但尚未执行的能力

- `ContinuityPlan`：transition、audio mode、overlay、chapter。
- `SubtitleWorkbenchDocument`：多语言轨、样式模板、逐词 timing、render mode。
- `AssetRecord`：内容寻址文件、revision、授权、尺寸、时长和 alpha 信息。
- `ExportPlan`：输出画布、fps、码率、平台和分片计划。

## 3. 非目标

- 不重做时间线编辑器交互。
- 不新增抠图、智能裁剪或翻译供应商。
- 不重写现有 EffectPlan，只建立稳定的 graph 映射。
- 第一阶段不删除旧 `ProjectVideoProps` 路径。
- 不在本项目中实现分布式渲染集群。

## 4. 核心决策

### 4.1 一个执行权威

V2 项目中，任何执行器都不得重新读取多个“当前状态”再自行拼接语义。

```text
ProductionTimeline revision
ContinuityPlan revision
SubtitleDocument revision
AssetRecord revisions
EffectPlan revisions
ExportPreset revision
          |
          v
RenderGraphCompiler
          |
          v
Immutable RenderGraphSnapshot
          |
   +------+-------+----------------+
   |              |                |
Remotion Player  Remotion Render  FFmpeg Audio/Mux
```

编译完成后，预览和正式渲染只能读取 snapshot 内已经解析的引用、时间和参数。

### 4.2 全片视觉渲染，取消 V2 分页 concat

V2 正式渲染必须按完整 composition 渲染视频轨，不能继续使用“每页独立视频 + concat copy”作为主路径。

原因：

- 重叠转场需要同时看到前后两个视觉节点。
- 跨页 presenter、overlay 和 effect 需要连续帧上下文。
- 分页边界会破坏遮罩、运动模糊、连续动画和 transition easing。

旧分页缓存仍可作为 slide/effect 的中间代理，但不能成为最终剪辑边界。

### 4.3 Remotion 负责视觉，FFmpeg 负责音频与封装

| 执行器            | 职责                                                                          |
| ----------------- | ----------------------------------------------------------------------------- |
| Remotion          | slide、presenter、effect、视觉 transition、overlay、烧录字幕                  |
| FFmpeg            | narration、presenter audio、music、SFX、J/L Cut、crossfade、ducking、最终 mux |
| Subtitle packager | SRT/WebVTT/ASS/MP4 soft subtitle track 和字幕清单                             |

### 4.4 微秒是权威，帧边界集中量化

- 时间线和 graph 使用整数微秒。
- 编译器集中计算 `start_frame` 和 `end_frame_exclusive`。
- 开始帧使用 floor，结束帧使用 ceil，保证内容不会被提前截断。
- Python 和 TypeScript 使用共享 golden fixture 验证。
- 最终音画漂移不超过 1 帧；语音边界误差不超过 20ms。

### 4.5 渲染任务绑定不可变 snapshot

任务入队时保存 graph ID/revision/hash、snapshot 路径/hash、全部源 revision、编译器版本、Remotion bundle 版本和 FFmpeg 版本。项目之后发生编辑时，Worker 仍渲染原 snapshot，不得在执行中重新编译当前项目。

## 5. RenderGraph V2 契约

### 5.1 顶层结构

```yaml
schema_version: '2.0'
graph_id: uuid
project_id: uuid
timeline_revision: int
timeline_hash: sha256
compiler_version: string
canvas:
  width: int
  height: int
  fps_num: int
  fps_den: int
  duration_us: int
  background: string
source_revisions:
  continuity_revision: int
  continuity_hash: sha256
  subtitle_revision: int
  subtitle_hash: sha256
  effect_catalog_version: string
  export_preset_revision: int
assets: ResolvedAsset[]
nodes: RenderNodeV2[]
transitions: TransitionEdge[]
audio_mix: AudioMixPlan
subtitle_plan: SubtitleRenderPlan
affected_ranges: TimeRange[]
content_hash: sha256
```

`compiled_at` 可以记录，但不得参与 content hash。

### 5.2 ResolvedAsset

```yaml
asset_id: uuid
revision: int
kind: image | video | audio | logo | sticker | font | lut
content_hash: sha256
object_relative_path: string
proxy_relative_path: string | null
mime_type: string
duration_us: int | null
width: int | null
height: int | null
alpha_mode: none | straight | premultiplied
license_snapshot: LicenseRecord
```

所有 `source_ref` 必须在编译时解析为 `ResolvedAsset`。V2 graph 不允许留下未经校验的任意路径字符串。

### 5.3 RenderNodeV2

```yaml
id: uuid
clip_id: uuid
track_id: uuid
kind: slide | presenter | effect | overlay | narration | music | sfx | subtitle
start_us: int
end_us: int
start_frame: int
end_frame_exclusive: int
track_order: int
z_index: int
asset_id: uuid | null
source_in_us: int
source_out_us: int | null
depends_on: uuid[]
cache_key: sha256
payload: kind-specific object
```

kind-specific payload：

- slide：page ID、layout mode、effect plan revision。
- presenter：layout segment、crop、opacity、audio ownership。
- overlay：normalized rect、crop、mask、opacity、enter/exit、blend mode。
- subtitle：track ID、cue range、style template revision、layout rect。
- audio：bus、gain、pan、fade、ducking role。

### 5.4 TransitionEdge

```yaml
id: uuid
from_node_id: uuid
to_node_id: uuid
kind: cut | dissolve | wipe | slide | match
start_us: int
end_us: int
duration_us: int
easing: linear | ease_in | ease_out | ease_in_out
parameters: object
```

约束：

- cut 的 duration 必须为 0。
- 非 cut transition 的区间必须等于两个视觉节点的 overlap 区间。
- duration 默认不能超过任一相邻节点可用时长的 50%。
- transition 区间中两个节点同时存在，由 z-order 和 transition progress 决定可见度。
- chapter boundary 默认禁用 match transition，除非用户显式确认。

### 5.5 AudioMixPlan

```yaml
buses:
  - id: narration
    target_lufs: -16
  - id: presenter
    target_lufs: -16
  - id: music
    target_lufs: -24
  - id: sfx
    target_lufs: -20
clips:
  - node_id: uuid
    asset_id: uuid
    bus_id: string
    source_in_us: int
    source_out_us: int
    timeline_start_us: int
    timeline_end_us: int
    gain_db: float
    pan: float
    fade_in_us: int
    fade_out_us: int
automation:
  - bus_id: music
    kind: duck
    start_us: int
    end_us: int
    target_gain_db: -12
master:
  peak_limit_db: -1
  target_lufs: -16
```

J/L Cut 只改变 audio clip 的 timeline 边界：

- J Cut：下一叙事音频 `timeline_start_us < next_visual.start_us`。
- L Cut：上一叙事音频 `timeline_end_us > next_visual.start_us`。
- audio source range 仍必须位于源素材时长内。
- 语音不得越过所属 chapter 的允许边界。

### 5.6 SubtitleRenderPlan

```yaml
render_mode: burn_in | soft | both | none
document_revision: int
document_hash: sha256
tracks:
  - track_id: uuid
    language: string
    primary: bool
    visible: bool
    cues:
      - cue_id: uuid
        start_us: int
        end_us: int
        text: string
        translation: string | null
        line_breaks: int[]
        words: WordTiming[]
        style: ResolvedSubtitleStyle
        layout: ResolvedRect
```

规则：

- burn_in：Remotion 渲染可见字幕。
- soft：Remotion 不渲染字幕，packager 生成并 mux 可选字幕轨。
- both：同时烧录主轨并封装软字幕轨。
- none：不渲染、不封装，但制作包仍记录字幕 revision。
- 双语模式由两条可见 track 或主 cue 的 translation 决定。
- word_highlight 使用 word timing 计算当前 token，不能使用随机或 CSS 自运行动画。

## 6. 编译流程

编译请求携带 timeline、continuity、subtitle 和 preset 的 expected revisions，任一 revision 已变化时返回 409。

编译阶段：

1. 读取并验证 ProductionTimeline revision/hash。
2. 读取 ContinuityPlan 和 SubtitleDocument 指定 revision。
3. 规范化所有 track/clip，并建立 clip、page、chapter 索引。
4. 解析 AssetRecord revision，校验对象文件、hash、媒体元数据和授权。
5. 将 transition/overlay 绑定到具体 timeline node。
6. 根据 J/L Cut 生成 AudioMixPlan。
7. 根据画幅、安全区、presenter 和 overlay 生成字幕布局。
8. 量化微秒到帧。
9. 建立依赖、cache key、affected ranges 和 graph hash。
10. 原子写入 immutable graph snapshot。

相同输入 revision、编译器版本和 preset 必须生成相同的 node ID、graph hash、asset resolution、frame boundary、FFmpeg filter plan 和 Remotion props。

## 7. Remotion 执行设计

### 7.1 新 composition

新增 `RenderGraphComposition`，输入只包含：

```ts
type RenderGraphCompositionProps = {
  graph: RenderGraphV2;
  executionMode: 'interactive-preview' | 'authoritative-preview' | 'final';
  assetBaseUrl: string;
};
```

不得同时传入旧 `pages`、旧 `subtitles` 或当前项目状态。

### 7.2 视觉层级

推荐层级：

1. background。
2. slide/page visual。
3. effect layer。
4. presenter layer。
5. overlay layer，按 z-index 排序。
6. burn-in subtitle layer。
7. diagnostics layer，仅预览模式可见。

### 7.3 转场解释器

- cut：相邻 Sequence，无 overlap animation。
- dissolve：前节点 opacity 1→0，后节点 0→1。
- wipe：基于 clip-path/mask progress。
- slide：两个节点同步 transform。
- match：使用显式 anchor/crop 参数；缺参数时预检阻断或显式降级为 dissolve。

所有 progress 只由当前 frame 和 graph transition range 计算，保证 seek-safe。

### 7.4 OverlayLayer

支持 image、video、logo、sticker、text，支持 contain/cover/fill、none/circle/rounded mask、opacity、enter/exit、z-index、alpha 图片和带 alpha 视频。代理文件仅用于交互预览，正式渲染强制使用 final asset。

### 7.5 SubtitleLayer V2

- 读取 `SubtitleRenderPlan`，不再查找旧 page cue。
- 支持 font family、font size、color、outline、background、position。
- 支持双语上下两行、人工 line breaks 和逐词高亮。
- 字体通过 AssetRegistry 注册；缺失字体禁止不确定的系统回退。
- soft/none 模式不挂载可见字幕层。

## 8. FFmpeg 执行设计

### 8.1 视频输出

Remotion 一次渲染完整 video-only 文件。最终 width、height、fps、codec、pixel format、bitrate/CRF 和 color space 来自 ExportPreset。

### 8.2 音频过滤器编译

新增纯函数 `AudioFilterCompiler`：

```text
AudioMixPlan -> deterministic filter_complex + ordered input list
```

主要 filter：

- `atrim` / `asetpts`：源区间。
- `adelay`：timeline 起点。
- `afade`：fade in/out。
- `volume` / `pan`：片段参数。
- `sidechaincompress` 或显式 volume automation：music ducking。
- `amix`：bus 和 master 汇合。
- `loudnorm` / `alimiter`：最终响度和峰值。

J/L Cut 由 graph 中音频 clip 的时间位置自然实现，不在 Worker 中另写一套边界逻辑。

### 8.3 字幕封装

- SRT：基础软字幕交付。
- WebVTT：网页和播放器预览。
- ASS：保留高级样式和双语布局的制作包产物。
- MP4 soft track：默认 `mov_text`，每个可见语言轨独立 metadata language。
- both 模式中，烧录主轨与 soft track timing 必须来自同一 SubtitleRenderPlan。

### 8.4 最终 mux

最终输入为 Remotion video-only、AudioFilterCompiler 输出的 master audio、可选 soft subtitle tracks，以及 graph hash/timeline revision/preset ID metadata。V2 路径禁止再执行分页 concat。

## 9. 预览设计

### 9.1 交互预览

- Remotion Player 直接消费 RenderGraph snapshot。
- 视觉素材使用 proxy，时间和布局仍来自同一 graph。
- 修改时间线后只重新编译 affected ranges。
- 播放头附近预取 5-15 秒节点。

### 9.2 权威预览

- 生成短区间 Remotion video proxy。
- 使用正式渲染同一个 AudioFilterCompiler 生成音频代理。
- 作为最终导出前的音画一致性依据。

一致性指标：transition、subtitle 和 overlay 起止不超过 1 帧差异；J/L Cut 语音边界不超过 20ms 差异。

## 10. 导出前门禁

### 10.1 新检查范围

PreflightEngine 增加 `render_graph`、`assets`、`continuity`、`subtitle_v2`、`audio_mix` 和 `output_contract`。

### 10.2 素材门禁

| 条件                                    | 预览       | 正式导出                 |
| --------------------------------------- | ---------- | ------------------------ |
| 文件缺失                                | 阻断       | 阻断                     |
| hash 不一致                             | 阻断       | 阻断                     |
| license=blocked                         | 阻断       | 阻断                     |
| license=expired                         | 警告或阻断 | 阻断                     |
| license=unknown                         | 带提示预览 | 阻断，除非有审计确认策略 |
| confirmed 但 project_ids 不包含当前项目 | 阻断       | 阻断                     |
| 授权早于预计交付时间到期                | 警告       | 阻断                     |
| font 未注册或缺失                       | 阻断       | 阻断                     |

禁止通过文件名、扩展名或 source_ref 绕过 AssetRecord。

### 10.3 时间与边界门禁

阻断条件：

- node start < 0 或 end > graph duration。
- source range 超过 asset duration。
- overlay 超过 graph duration 或 normalized rect 越界。
- transition overlap 与相邻 visual node 不一致。
- J/L Cut 超过源音频、graph 或 chapter 边界。
- subtitle cue/word 超出 document 或 graph duration。
- 同一主视觉轨存在未声明的 overlap。
- graph 的 source revision 与 snapshot 不一致。

### 10.4 输出门禁

- width、height、fps、codec、audio codec 符合 preset。
- 最终时长误差不超过 max(1 frame, 50ms)。
- 有音频需求时必须存在 audio stream。
- soft/both 模式必须存在要求的 subtitle streams 和 language metadata。
- 输出报告必须包含 graph hash 和所有 source revisions。

## 11. API 设计

```text
POST /api/projects/{project_id}/render-graphs:compile
GET  /api/projects/{project_id}/render-graphs/current
GET  /api/projects/{project_id}/render-graphs/{graph_id}
GET  /api/projects/{project_id}/render-graphs/{graph_id}/preflight
POST /api/projects/{project_id}/render-graphs/{graph_id}/preview-jobs
POST /api/projects/{project_id}/render-graphs/{graph_id}/render-jobs
GET  /api/projects/{project_id}/render-graphs/{graph_id}/affected-ranges
```

编译响应返回 graph ID/hash、source revisions、affected ranges 和 blocking diagnostics。

旧接口兼容：

- `/timeline/compile` 在 V2 flag 开启后转发新 compiler。
- `/video/preflight` 返回新 graph preflight 的兼容投影。
- `/video/render-jobs` 可接受 graph ID；V2 项目禁止不带 graph ID 隐式读取当前状态。

## 12. 缓存与失效

节点 cache key 至少包含 clip payload、asset hash、effect/subtitle/style revision、canvas、fps、layout resolver version 和 compiler version。

失效原则：

- burn-in 字幕修改只失效字幕层和覆盖区间；soft 字幕只失效字幕产物和 mux。
- 音频 gain/J/L Cut 修改不失效 video-only 缓存。
- overlay 修改只失效覆盖区间。
- transition 修改失效两个相邻节点的 overlap 区间。
- 画幅、fps、字体或 layout resolver 变化失效所有布局相关节点。

## 13. 持久化与审计

建议目录：

```text
07_时间线/render-graphs/{graph_id}/graph.json
07_时间线/render-graphs/{graph_id}/preflight.json
07_时间线/render-graphs/{graph_id}/audio-filter.json
07_时间线/render-graphs/{graph_id}/subtitle-plan.json
09_日志/render-jobs/{job_id}/input.json
09_日志/render-jobs/{job_id}/runtime.json
```

采用临时文件、flush/fsync、hash 校验和原子 replace。

审计事件：render_graph_compiled、render_graph_preflight_blocked、render_job_bound_to_graph、render_job_started/succeeded/failed、legacy_render_fallback_used、asset_license_override_confirmed。

## 14. 兼容与迁移

Feature flags：

- `render_graph_v2_compile`。
- `render_graph_v2_preview`。
- `render_graph_v2_export`。
- `render_graph_v2_strict_assets`。

迁移阶段：

1. 新 compiler 只读生成 snapshot，不改变预览。
2. 新旧 graph/props 对照并记录差异。
3. 新 Remotion Player 使用 V2 graph，正式渲染仍走旧路径。
4. 内部项目启用 V2 正式渲染。
5. 新项目默认 V2；旧项目自动建立 legacy timeline 和 asset snapshot。
6. 一个发布周期后停止新增 V1 Props 功能。

只有未使用 V2 独占语义的 graph 才允许回退 V1。包含 overlap、J/L Cut、V2 overlay 或 soft/both subtitle 的项目禁止无损回退。

## 15. 性能目标

- 1,000 节点 graph 全量编译 p95 < 500ms，不含媒体探测。
- 单区间增量编译 p95 < 150ms。
- 缓存命中时 10 秒权威预览生成 p95 < 8 秒。
- 交互预览首次可播放 p95 < 3 秒。
- 1080p30 正式渲染不得因 graph 解释层增加超过 10% CPU 开销。
- snapshot 读取或验证失败时快速失败，不启动 Remotion/FFmpeg。

## 16. 测试策略

### 16.1 契约与编译器

- Python/TypeScript RenderGraph V2 fixture 双向校验。
- 微秒到帧 golden fixture。
- FFmpeg filter plan snapshot。
- graph hash 确定性。
- cut/dissolve/wipe/slide/match 和非法 overlap。
- J Cut、L Cut、chapter 边界和音频源越界。
- burn_in/soft/both/none、双语、人工断句和逐词高亮。
- 素材缺失、hash 错误、授权状态和项目范围。

### 16.2 Remotion 视觉回归

- 16:9、9:16、1:1；1080p 和 4K。
- transition 起点、中点、终点截图。
- overlay alpha、mask、z-order。
- 双语字幕、outline/background、word highlight。
- presenter + overlay + subtitle 安全区冲突。

### 16.3 音频与端到端

- 通过波形和静音区验证 J/L Cut。
- music ducking、crossfade、LUFS 和 peak。
- 24/25/30/60fps 音画边界。
- PPT + AI 旁白 + dissolve + 双语烧录字幕 + Logo。
- 真人视频 + J/L Cut + 跨页 overlay + music ducking。
- 竖屏 + word highlight + soft subtitle。
- 4K + alpha video overlay + both subtitle。
- 缺失或过期素材在入队前阻断。
- 入队后修改项目，旧 job 按 snapshot 可复现完成。

## 17. 发布门禁

- V2 预览和正式渲染只读取 RenderGraph snapshot。
- V2 正式路径不存在分页 concat。
- graph fingerprint 进入 JobRepository、输入快照和制作包。
- 转场、J/L Cut、overlay、字幕模式自动和视觉验收通过。
- 所有素材引用可追溯到 AssetRecord revision/hash。
- 缺失、授权失效和越界在入队前阻断。
- Feature flag 关闭时旧项目仍可渲染。
- Windows packaged runtime 的 Node、Chrome、Remotion、FFmpeg、FFprobe 全链路通过。

## 18. 工期与人员建议

预计工作量 10-14 工程师周。

推荐配置：1 名 Python/渲染后端、1 名 Remotion/React、0.5-1 名 FFmpeg 工程师；QA 从第 3 周开始维护视觉和音频 golden fixtures。

两至三人并行时推荐日历工期 6-9 周；单人顺序实施约 12-16 周。

关键路径：RenderGraph V2 契约 → 编译器 → Remotion 全片 composition → FFmpeg audio mix → subtitle packaging → preview/export cutover → Windows 验收。
