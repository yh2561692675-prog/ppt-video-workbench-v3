# 七项 P1 视频生产能力逐项实施计划

> 本计划必须按依赖顺序执行。当前恢复根目录存在大量未提交改动，Phase 0 基线没有形成前，不得在根目录同时启动七条编码线。每个实施线使用独立 worktree；共享契约、迁移和主渲染入口串行修改。

**Goal:** 按“统一时间线 → 素材与材料 → 高级字幕 → 跨页转场与覆盖层 → 多规格导出 → 批量调度”的顺序，形成一个时间权威、一个素材权威、一个 RenderGraph 和一个任务系统。  
**Design:** `docs/superpowers/specs/2026-08-11-seven-p1-production-capabilities-design.md`  
**Tech Stack:** Python 3.12、FastAPI、Pydantic 2、SQLite WAL、React 19、TypeScript、TanStack Query、Vitest/Playwright、Remotion、FFmpeg/FFprobe、PowerPoint/LibreOffice 可选适配器。

## 1. 全局实施约束

- [ ] 先形成当前恢复分支的可信 checkpoint，记录 branch、HEAD、已跟踪改动、未跟踪条目和其他 worktree。
- [ ] 禁止 `reset --hard`、`clean`、批量覆盖根目录或跨 worktree 复制整个目录。
- [ ] 同一正式文件在同一时间只能由一个实施线负责。
- [ ] 所有权威时间使用整数微秒；帧号只在预览与渲染边界计算。
- [ ] 所有 mutation 使用 `expected_revision`、`command_id` 或等价幂等键。
- [ ] 所有持久写入使用项目相对路径、临时文件、校验和和原子替换。
- [ ] 所有长任务拥有持久 job_id、输入 fingerprint、检查点、取消和重启恢复。
- [ ] 预览、渲染、质量检测和导出只消费同一 RenderGraph revision。
- [ ] 素材正文、密钥、绝对路径和完整远程 URL 不进入普通日志、API 错误或诊断包。
- [ ] Office、浏览器、FFmpeg 和 Remotion 进程必须由可取消进程执行器管理。
- [ ] 每个任务先写失败测试，再实现，再跑相邻回归，最后形成独立可审查提交。
- [ ] 未通过真实 Windows、真实媒体和安装版门禁的能力只能放在 feature flag 后。

## 2. 分支与文件责任建议

| 实施线      | 建议分支                          | 主要目录                                           |
| ----------- | --------------------------------- | -------------------------------------------------- |
| Foundation  | `codex/p1-production-foundation`  | contracts、schemas、domain、migrations、docs       |
| Timeline    | `codex/timeline-editor-v2`        | timeline、render graph、Web timeline               |
| Assets      | `codex/asset-registry`            | assets、brand packs、asset UI                      |
| Materials   | `codex/flexible-materials`        | materials、import、matching adapter、material UI   |
| Subtitles   | `codex/subtitle-workbench-v2`     | subtitles、templates、translation、subtitle UI     |
| Continuity  | `codex/continuous-transitions`    | transitions、overlay、audio mix、Remotion          |
| Export      | `codex/multi-export`              | export presets、render、FFmpeg、package、export UI |
| Scheduler   | `codex/batch-scheduler`           | jobs、scheduler、batch API/UI                      |
| Integration | `codex/p1-production-integration` | main、workflow、OpenAPI、E2E、release              |

共享文件如 `main.py`、`domain/models.py`、`storage/migrations.py`、`packages/contracts/openapi.json`、`apps/web/src/api/client.ts` 和主 Remotion composition 只在阶段集成提交中修改。

## 3. 阶段总览

| 阶段     | 项目                       | 前置门禁                    | 可并行关系   |
| -------- | -------------------------- | --------------------------- | ------------ |
| Phase 0  | 基线与共享契约             | 无                          | 串行         |
| Phase 1  | 统一多轨时间线             | Phase 0                     | 串行主线     |
| Phase 2A | 素材库基础层               | Phase 1 契约冻结            | 可与 2B 并行 |
| Phase 2B | 灵活材料组织               | Phase 1 契约冻结            | 可与 2A 并行 |
| Phase 3  | 高级字幕工作台             | Phase 1、2A/2B 共享引用冻结 | 单线         |
| Phase 4  | 跨页转场、连续镜头、覆盖层 | Phase 3                     | 单线         |
| Phase 5  | 多规格导出                 | Phase 4                     | 单线         |
| Phase 6  | 批量生产与资源调度         | Phase 5，全部长任务可恢复   | 单线         |
| Phase 7  | 主线集成与发布             | Phase 1-6                   | 串行         |

---

## Phase 0：可信基线与共享契约

### Task 0.1：冻结恢复根目录基线

**Files:** 新增基线报告；不修改业务代码。

- [ ] 记录当前 branch、HEAD、Git worktree、恢复引用和根目录 status 数量。
- [ ] 将现存改动按当前窗口、恢复窗口、特效、渲染、P03-P12、真人模式和本计划分类。
- [ ] 确认同目录活动窗口是只读、已提交或拥有独立 worktree。
- [ ] 为现有未提交成果形成可恢复 checkpoint；保存恢复命令和风险说明。
- [ ] 跑当前 Python、Web、Remotion、release 和 Windows smoke 基线。
- [ ] 把失败分成“现有基线失败”和“本计划新增失败”，禁止混记。
- [ ] 新增 `docs/acceptance/p1-production-baseline.md`。

**Gate:** 来源不明的正式文件、损坏 Git 指针或未登记的大量改动存在时停止编码。

### Task 0.2：冻结七项共享命名与版本

**Create:**

- `schemas/asset-manifest-v1.schema.json`
- `schemas/material-collection-v1.schema.json`
- `schemas/production-timeline-v2.schema.json`
- `schemas/subtitle-document-v2.schema.json`
- `schemas/transition-plan-v1.schema.json`
- `schemas/export-preset-v1.schema.json`
- `schemas/batch-plan-v1.schema.json`
- `schemas/render-graph-v2.schema.json`

**Checklist:**

- [ ] 为八个契约先写失败的 Schema 测试。
- [ ] 固定 UUID、revision、整数微秒、relative path、fingerprint 和 content_hash 规则。
- [ ] 禁止绝对路径、NaN/Infinity、浮点时间和未知额外字段。
- [ ] 明确 V1 → V2 adapter，禁止原地修改旧 Schema 含义。
- [ ] 建立规范化 JSON 的 Python/TypeScript golden fixtures。
- [ ] 生成或维护 TypeScript DTO 快照和 OpenAPI 契约快照。
- [ ] 记录每个契约的 owner 和允许扩展方式。

**Verify:** contract tests、Schema snapshot、Web typecheck。

### Task 0.3：增量数据库与项目清单迁移

**Modify:** `domain/models.py`、`storage/migrations.py`、project schema、migration tests。

- [ ] 新增 asset、material collection、timeline revision、subtitle revision、preset、batch、lease 表或引用表。
- [ ] ProjectManifest 只增加可空摘要和 current pointer，不嵌入大型正文。
- [ ] 迁移只新增表、列和索引，不删除旧 jobs/projects 数据。
- [ ] 迁移中断必须回滚；重复执行必须幂等。
- [ ] 旧项目加载和保存不得自动生成 V2 文件。
- [ ] 迁移前后原项目媒体、settings 和成片 hash 保持不变。
- [ ] 更新数据库健康探针和 schema version 诊断。

### Task 0.4：共享错误码、工件和 Job 类型

- [ ] 增加资产导入/派生、材料同步、字幕翻译、时间线编译、代理预览、导出、批次和资源等待 JobType。
- [ ] 为每类任务定义输入工件、输出工件、MIME、大小上限和 manifest schema。
- [ ] 定义稳定错误码与 HTTP 映射；用户错误、资源等待、可重试故障和永久故障分离。
- [ ] 路径逃逸、非法工件、错误 MIME、坏 hash 和敏感信息脱敏测试通过。
- [ ] Feature flags 默认关闭，诊断中心只显示 capability summary。

### Task 0.5：统一失效与依赖矩阵

- [ ] 列出 source → asset → material → timeline → subtitle/effect/transition → graph → export → quality 依赖。
- [ ] 为每种编辑动作定义受影响区间和缓存节点。
- [ ] 对“字幕文字修改不重渲无关视觉”“画幅修改使所有布局失效”等关键规则写测试。
- [ ] 旧 dependency graph adapter 与新节点并存一个兼容周期。

### Task 0.6：Foundation Gate

- [ ] Python contract/migration/security tests 全部通过。
- [ ] Web DTO typecheck 和 OpenAPI snapshot 通过。
- [ ] 旧项目 smoke、旧成片导出和现有安装构建无回归。
- [ ] Foundation 形成独立提交；后续 worktree 均从该提交创建。

---

## Phase 1：统一多轨时间线编辑器

### Task 1.1：审计并升级现有时间线核心

**Existing:** `workbench/timeline/production.py`、`api/timeline_production.py`、`TimelineWorkspace.tsx`。

- [ ] 为现有 V1 模型、命令、持久化和编译器补齐行为快照测试。
- [ ] 明确哪些 V1 字段直接保留，哪些通过 V2 adapter 转换。
- [ ] 增加轨道组、visible/solo、audio bus、proxy policy 和 transition edge。
- [ ] 增加 clip transform、crop、opacity、blend、gain、pan、fade 和 playback rate。
- [ ] 验证相同输入得到 byte-stable graph、node ID 和 cache key。
- [ ] 旧 V1 timeline 可只读编译，V2 编辑器只写 V2 revision。

### Task 1.2：不可变仓库与原子 batch command

- [ ] 将 timeline current、revision、command audit 和 graph pointer 持久化到正式 repository。
- [ ] 实现 command_id 跨重启幂等，而不只在内存中幂等。
- [ ] 实现 `TimelineCommandBatchV1` 全成或全败。
- [ ] command result 返回 affected ranges、warnings 和 current revision。
- [ ] 写入失败、磁盘满、进程崩溃和 revision 冲突不能破坏 current。
- [ ] 实现 create/get/list/restore/undo/redo 的一致仓库语义。

### Task 1.3：时间坐标与吸附引擎

**Create:** `apps/web/src/features/timeline/model/timeScale.ts`、`snapEngine.ts` 及测试。

- [ ] 实现 px ↔ integer microseconds 的稳定转换。
- [ ] 支持 page、clip edge、marker、subtitle cue、playhead 和 audio transient snap points。
- [ ] 按缩放级别计算吸附阈值，避免时间单位固定阈值造成手感变化。
- [ ] Alt/修饰键临时关闭吸附，方向键支持帧级/毫秒级微调。
- [ ] 相同输入的 snap 选择确定性一致。

### Task 1.4：虚拟化编辑器骨架

- [ ] 拆分 TimelineEditorShell、Viewport、TrackHeader、TrackLane、Ruler、Playhead。
- [ ] 实现水平时间窗口和垂直轨道虚拟化。
- [ ] 实现缩放、滚动、适合全部、适合选择和跟随播放头。
- [ ] 50 页、500 clips、20 tracks 的测试数据保持可交互。
- [ ] 空项目、加载、404、revision 冲突和只读模式都有明确界面。

### Task 1.5：拖动、裁剪、分割与 ripple edit

- [ ] pointer drag 使用本地 preview command，pointer up 才提交服务端命令。
- [ ] 支持跨轨移动并校验 track kind。
- [ ] 支持左右边缘裁剪、source range 和最短时长。
- [ ] 支持播放头/鼠标位置分割、多选删除和复制。
- [ ] 支持关闭或开启 ripple 的移动、删除和插入。
- [ ] 服务端拒绝 locked、source 越界、非法重叠和 revision 冲突。

### Task 1.6：选择、快捷键与属性检查器

- [ ] 单选、多选、范围选择、框选和全选。
- [ ] Delete、Split、Nudge、Copy/Paste、Undo/Redo 快捷键。
- [ ] 输入框聚焦时不触发时间线破坏性快捷键。
- [ ] TimelineInspector 根据 clip kind 显示允许属性。
- [ ] 批量修改使用 batch command，任一非法则全部回滚。
- [ ] 键盘和屏幕阅读器可完成核心操作。

### Task 1.7：撤销、重做与冲突恢复

- [ ] undo/redo 基于命令结果和 revision，不维护无界完整副本。
- [ ] 远端/其他窗口 revision 变化时停止自动重放并显示差异摘要。
- [ ] 拖动期间发生冲突时保留用户意图，可刷新后安全重试。
- [ ] restore 生成新 revision，不把 current pointer 指回旧可变对象。
- [ ] 重启后 history panel 和可恢复点可重建。

### Task 1.8：音频轨、波形与混音基础

- [ ] 生成可缓存的分层波形和音频瞬态索引。
- [ ] 支持 narration、presenter、music、sfx 轨的 gain、pan、mute、solo、fade。
- [ ] 定义 dialogue/music/sfx bus 和默认 ducking contract。
- [ ] 预览与正式 FFmpeg 混音共享同一 AudioMixGraph。
- [ ] 音频 clip 修改只使音频及相关字幕/同步检查失效。

### Task 1.9：增量 RenderGraph 与实时预览

- [ ] 编译器输出视觉、音频、字幕、特效、素材和缓存节点依赖。
- [ ] graph 编译返回 affected ranges 和 reusable nodes。
- [ ] Remotion Player 使用 graph adapter，不再自己拼接页面时间。
- [ ] 播放头附近代理素材预取，缺失代理时显示降级状态。
- [ ] graph 编译失败保留上一份成功 graph。
- [ ] 预览、正式渲染和质量检测记录同一 graph hash。

### Task 1.10：时间线 API、工作流和发布门禁

- [ ] 补齐 initialize/get/commands/batch/compile/revisions/restore/render-graph API。
- [ ] ETag/304、ownership 404、revision 409 和错误 envelope 契约通过。
- [ ] 接入 WorkflowShell 的专业时间线入口，不覆盖现有基础流程。
- [ ] 8 页、50 页、横屏、竖屏、AI 旁白、真人模式 E2E 通过。
- [ ] 500 clips 性能、崩溃恢复、键盘操作和视觉回归通过。
- [ ] `timeline_editor_v2` 先以 opt-in 发布。

**Timeline Gate:** Task 1.1-1.10 全部通过后，冻结 ProductionTimeline V2、Command、RenderGraph V2 和 AssetRef 接口。

---

## Phase 2A：素材库基础层与媒体资产

### Task 2.1：AssetRegistry 领域模型与对象存储

- [ ] 实现 AssetManifest、LicenseRecord、DerivedAssetRef、BrandPack strict 模型。
- [ ] 工作区对象存储按 SHA-256 分层，项目只保存逻辑引用。
- [ ] 相同内容去重，但不同授权记录和逻辑名称可独立存在。
- [ ] 原始对象不可变；归档只影响引用，不立即删除共享正文。
- [ ] 原子 current pointer、引用计数和垃圾回收候选清单测试通过。

### Task 2.2：安全批量导入

- [ ] 支持图片、视频、音频、Logo、贴纸、图标、字体、LUT、文档和课件类型。
- [ ] 校验扩展名、MIME、magic bytes、大小、像素、时长、压缩比和路径。
- [ ] 拒绝路径穿越、设备文件、链接、宏、ActiveX、OLE 自动执行和超限压缩包。
- [ ] 导入先写 staging、计算 hash、探测媒体，再原子发布对象。
- [ ] 批量中单项失败不破坏成功项；用户可选择全成或部分成功模式。
- [ ] 远程 URL 导入默认关闭，并有独立安全测试。

### Task 2.3：代理、缩略图、波形和派生资产

- [ ] 图片生成缩略图和编辑代理；保留 alpha 信息。
- [ ] 视频生成首帧、联系表、低码率代理和媒体探测摘要。
- [ ] 音频生成多级波形、响度和瞬态索引。
- [ ] 抠图、裁剪、转码、压缩、chroma key 预处理生成派生资产。
- [ ] 派生资产记录父 hash、参数 hash、工具版本和可重建状态。
- [ ] 代理任务可暂停、取消、恢复和缓存复用。

### Task 2.4：授权与品牌治理

- [ ] 实现许可类型、来源、作者、适用项目、到期时间和人工确认。
- [ ] 未知/过期/项目范围不匹配授权产生稳定 preflight issue。
- [ ] 日志和 API 不返回完整授权 URL token 或本地绝对路径。
- [ ] BrandPack 支持 Logo、字体、颜色、片头片尾和 overlay 模板引用。
- [ ] 品牌锁限制 Logo 最小尺寸、边距和允许修改项。

### Task 2.5：素材 API 与搜索索引

- [ ] 实现 list/get/import/derive/update-license/archive API。
- [ ] 支持 kind、tag、brand、license、created_at、usage 的分页筛选。
- [ ] 搜索索引保存名称、标签和摘要，不索引私密正文。
- [ ] ETag、幂等导入、ownership 和跨项目共享权限测试通过。
- [ ] 大型导入返回 job envelope，不在 HTTP 请求内同步转码。

### Task 2.6：素材库前端

- [ ] 工作区库、项目库、品牌包、最近使用和待确认授权视图。
- [ ] 拖放/文件选择批量导入、进度、失败项和重试。
- [ ] 网格/列表虚拟化、搜索、过滤、标签和收藏。
- [ ] 预览图片、视频、音频波形和元数据，不自动下载原文件。
- [ ] 支持拖入时间线创建 overlay/music/sfx clip。
- [ ] 键盘选择、批量操作和屏幕阅读器标签通过。

### Task 2.7：品牌包与模板管理

- [ ] 创建、复制、版本化、导入和导出 BrandPack manifest。
- [ ] 品牌包文件全部使用 AssetRef，不复制不可追踪正文。
- [ ] 模板升级不改写已固定 revision 的项目。
- [ ] 缺失字体/Logo 时明确降级并阻断错误发布。

### Task 2.8：素材库真实媒体门禁

- [ ] 至少覆盖透明 PNG、超大 JPEG、SVG/图标、短视频、长视频、WAV、MP3、字体和 LUT。
- [ ] 损坏文件、伪扩展、压缩炸弹、重复导入和磁盘满测试通过。
- [ ] 1,000 个素材列表和搜索保持可用。
- [ ] 授权阻断、制作包排除原始素材和诊断脱敏通过。

**Asset Gate:** AssetRef、对象存储和授权模型冻结后，允许材料集合与字幕模板使用。

---

## Phase 2B：灵活的材料组织模式

> Phase 2B 可与 2A 并行，但只能消费已经冻结的 AssetRef；两条线不得同时修改 ImportService 和 ProjectManifest。

### Task 3.1：MaterialCollection 领域模型

- [ ] 实现 MaterialCollection、DocumentRef、PresentationRef、Section、PageRef strict 模型。
- [ ] 支持 outline_mode none/generated/selected/merged。
- [ ] page_id 在重排时稳定；替换时显式选择保留身份或创建新身份。
- [ ] 章节、页面和来源引用使用 UUID，不依赖文件名或数组下标。
- [ ] content_hash 只覆盖语义内容，不含绝对路径和时间戳。

### Task 3.2：多文档与多课件导入

- [ ] 导入 API 不再强制一份 Word + 一份 PPT/PDF。
- [ ] 支持 0-N 文档、0-N 课件、图片页面集合和已有项目页面。
- [ ] 同批来源有稳定顺序、角色和启用状态。
- [ ] 解析失败按来源隔离，不破坏已有 collection revision。
- [ ] P03/P04 adapter 可消费 collection，不建立第二套输入模型。

### Task 3.3：无大纲与合并大纲

- [ ] 无大纲模式直接使用页面标题/OCR/人工章节。
- [ ] generated 模式从页面和资料生成候选大纲，但必须人工确认才成为 current。
- [ ] selected 模式选择某一文档为主大纲。
- [ ] merged 模式按来源优先级和人工映射合并多个文档。
- [ ] 生成或合并过程保留 source refs 和冲突证据。

### Task 3.4：章节合并、拆分、排序和禁用

- [ ] 实现 insert/move/split/merge/rename/disable section commands。
- [ ] 实现页面跨章节移动、批量移动、排序和禁用。
- [ ] 所有命令使用 expected_revision 和 command_id。
- [ ] batch command 全成或全败；失败不生成空 revision。
- [ ] 章节 marker 和导出切片通过 adapter 生成，不在材料层保存最终时间。

### Task 3.5：页面替换与差异预览

- [ ] 替换前计算标题、文本、视觉 hash、尺寸和来源差异。
- [ ] 用户选择保留 page_id 时，明确列出旁白、字幕、特效、匹配和时间线失效项。
- [ ] 用户选择新 page_id 时，旧页面进入历史，不自动删除其资产。
- [ ] 替换提交后只失效依赖当前页面的缓存。
- [ ] 支持撤销到替换前 revision。

### Task 3.6：材料集合到时间线的显式同步

- [ ] 实现 append_missing、reconcile_order、manual_map 三种同步计划。
- [ ] GET collection 或 GET timeline 不得隐式同步。
- [ ] 同步先返回 diff preview，再以 timeline batch command 提交。
- [ ] 人工锁定 clip 不被自动重排；冲突显示具体页面和动作。
- [ ] 同步成功记录 collection revision 和 timeline revision 对应关系。

### Task 3.7：材料结构前端工作台

- [ ] 来源列表、章节树、页面缩略图和差异检查器。
- [ ] 多来源导入、角色选择、启用/禁用和解析状态。
- [ ] 章节拖动、合并、拆分、替换页面和批量操作。
- [ ] 同步时间线前显示新增、移动、替换、删除和受影响下游。
- [ ] 50 页、多个来源时使用虚拟化，键盘操作通过。

### Task 3.8：旧项目迁移与材料门禁

- [ ] 旧项目适配成一份 legacy collection，只读打开不落盘。
- [ ] 明确启用后创建 revision 1，原 source_files 保留一个兼容周期。
- [ ] 无大纲、多文档、多课件、图片集合、章节合并和替换 E2E 通过。
- [ ] 迁移前后原素材 hash、页面 ID 和旧成片保持不变。
- [ ] 更新用户手册和迁移报告。

**Materials Gate:** MaterialCollection、PageRef 和 timeline sync contract 冻结后，进入高级字幕阶段。

---

## Phase 3：高级字幕工作台

### Task 4.1：SubtitleDocument V2 与模板契约

- [ ] 实现 language track、cue group、cue、word timing、speaker、translation 和 confirmation 模型。
- [ ] 实现 SubtitleStyleTemplate、画幅覆盖、cue override 和版本化引用。
- [ ] render_mode 支持 burn_in、soft、both、none。
- [ ] cue 时间使用整数微秒并验证不越过 timeline duration。
- [ ] 模板 hash、文档 hash 和旧 SubtitleTimeline adapter 确定性测试通过。

### Task 4.2：旧字幕与词级时间适配

- [ ] 将现有 SubtitleTimeline/P08 输出适配成 V2 revision 1。
- [ ] 保留旧 cue_id、page_id 和 source_word_indexes。
- [ ] 没有词级时间时支持句级高亮降级，不伪造精确 word timing。
- [ ] ASR/HeyGen/本地音频来源统一到 source refs。
- [ ] 适配过程只读，明确启用工作台才持久化 V2。

### Task 4.3：字幕命令引擎

- [ ] 实现 split/merge/move/retime/text/style/speaker/lock/batch-offset commands。
- [ ] 断句不丢失词级时间、source refs 和翻译映射。
- [ ] cue overlap、负时间、零时长、超长文本和越界返回稳定错误码。
- [ ] undo/redo、跨重启幂等和 revision 冲突测试通过。
- [ ] timeline subtitle clips 通过 adapter 引用文档 cue，不复制正文。

### Task 4.4：翻译、术语表和确认流程

- [ ] 实现目标语言、术语表、模型配置摘要和源 revision 输入契约。
- [ ] 翻译作为可暂停、取消、恢复的长任务。
- [ ] 按 cue 保存来源、模型版本、置信度和人工确认。
- [ ] 源 cue 变化只使对应译文 stale；人工锁定译文不自动覆盖。
- [ ] 密钥、认证头、提示正文和完整原文不进入普通日志。
- [ ] 翻译不可用时工作台保留人工双语编辑能力。

### Task 4.5：样式模板服务

- [ ] 支持字体、字号、字重、颜色、描边、阴影、背景、圆角、边距和位置。
- [ ] 支持逐词高亮、卡拉 OK、整句淡入、说话人配色和关键词强调。
- [ ] 支持双语上下、左右和交替布局。
- [ ] 支持 16:9、9:16、1:1、4:5 画幅覆盖。
- [ ] 内置模板只读；用户模板复制、版本化和恢复。
- [ ] 缺失字体和不安全字体有明确降级或阻断。

### Task 4.6：字幕内容编辑器

- [ ] 波形、播放头、cue 列表、页面和时间线联动。
- [ ] 人工断句、合并、拖动边界、批量偏移和文本编辑。
- [ ] 阅读速度、行数、字符数、重叠和未确认翻译实时告警。
- [ ] 大量 cue 使用虚拟化；输入法组合状态不触发快捷键。
- [ ] 键盘可完成定位、分割、合并和微调。

### Task 4.7：字幕样式与双语预览

- [ ] 样式属性面板和模板浏览器。
- [ ] 使用真实 Remotion 字幕组件预览，不另写近似 HTML 渲染器。
- [ ] 画幅切换时显示安全区、presenter 避让和 overlay 冲突。
- [ ] 支持 cue 级 override，并可清除回到模板继承。
- [ ] loading/empty/error/stale/blocked 状态和无障碍测试通过。

### Task 4.8：RenderGraph 与 Remotion 字幕解释器

- [ ] RenderGraph 字幕节点引用 document/template revision 和 cue range。
- [ ] 实现逐词高亮、双语布局、描边、背景和动画的 seek-safe 渲染。
- [ ] 预览和正式渲染使用相同字体解析与 safe-area 计算。
- [ ] reduced motion 只减少字幕动画，不改变 cue 时间。
- [ ] 横屏、竖屏、方屏截图和关键帧回归通过。

### Task 4.9：软字幕与封装

- [ ] 生成 SRT、WebVTT 和 ASS；保留语言、speaker 和样式可表达部分。
- [ ] MP4/MOV/WebM 按容器能力封装软字幕流。
- [ ] both 模式不会在播放器中重复显示两套字幕。
- [ ] 导出报告列出烧录/软字幕产物和语言轨。
- [ ] 制作包不包含翻译密钥或隐私日志。

### Task 4.10：字幕质量与发布门禁

- [ ] 检查 cue 越界、重叠、阅读速度、遮挡、字体、双语缺失和未确认译文。
- [ ] 至少覆盖中英双语、长句、逐词高亮、竖屏、presenter 和 overlay 场景。
- [ ] 软字幕在 Windows 常用播放器和浏览器播放器验证。
- [ ] 旧字幕项目迁移、关闭 flag 和回滚路径通过。
- [ ] 更新用户手册、模板说明和翻译隐私说明。

**Subtitle Gate:** SubtitleDocument V2、StyleTemplate 和 RenderGraph subtitle node 冻结。

---

## Phase 4：跨页转场、连续镜头与媒体覆盖层

### Task 5.1：TransitionPlan 与 continuity 契约

- [ ] 实现视觉 cut/dissolve/wipe/slide/zoom/blur/custom 类型和参数白名单。
- [ ] 实现 audio cut/crossfade/j_cut/l_cut。
- [ ] transition 作为相邻 clip edge，禁止复制成两个独立效果。
- [ ] continuity_group、章节边界和跨边界持续策略模型化。
- [ ] 时长、handle、source range、z-order 和非法循环依赖验证通过。

### Task 5.2：时间线重叠与总时长语义

- [ ] 页面主轨允许被 transition 标记的受控重叠。
- [ ] timeline duration 按区间并集和明确 tail 计算。
- [ ] insert/move/trim/ripple 能维护 transition edge 或明确移除。
- [ ] 删除/替换相邻 clip 时处理悬空 transition。
- [ ] 属性测试覆盖随机重叠、裁剪和恢复后不变量。

### Task 5.3：J/L Cut 与音频边界

- [ ] 视觉边界和 dialogue 音频边界可独立编辑。
- [ ] 默认最大 J/L 窗口、章节限制和 source handle 校验。
- [ ] 边界自动短 crossfade，避免点击声和突变。
- [ ] 字幕跟随实际语音 cue，不跟随视觉页面边界。
- [ ] presenter 原声和 AI 旁白两种模式测试通过。

### Task 5.4：连续镜头和章节级 preset

- [ ] 创建/拆分 continuity group commands。
- [ ] 组内共享背景音乐、调色、镜头运动和覆盖层持续策略。
- [ ] 章节 transition preset 与普通页面 preset 分离。
- [ ] 更换章节结构时只使相关 marker、transition 和导出切片失效。
- [ ] continuity inspector 显示当前继承和 override。

### Task 5.5：RenderGraph V2 重叠编译

- [ ] 视觉节点支持重叠区、z-order、mask 和 transition adapter。
- [ ] 音频节点支持 J/L Cut、crossfade、ducking 和 bus automation。
- [ ] 字幕、presenter、effect 和 overlay 明确跨边界持续规则。
- [ ] 相同输入 graph byte-identical；受影响区间精确到重叠范围。
- [ ] 编译失败保留上一份成功 graph。

### Task 5.6：Remotion 转场解释器

- [ ] 建立 seek-safe transition registry 和参数验证器。
- [ ] 支持开始、中点、结束任意 seek 得到确定画面。
- [ ] 不依赖组件挂载顺序、Date.now 或随机数。
- [ ] 页内 EffectPlan 与页间 transition 各自只控制责任范围。
- [ ] reduced motion 有显式替代，而不是改变总时长。

### Task 5.7：FFmpeg 音频混合与一致性

- [ ] AudioMixGraph 确定性编译为 FFmpeg filter graph。
- [ ] J/L Cut、crossfade、music ducking、gain 和 pan 与预览一致。
- [ ] 使用样本级边界，避免多次浮点换算产生累积漂移。
- [ ] 响度、true peak、静音和音画同步质量检测通过。

### Task 5.8：覆盖层属性编辑器

- [ ] 图片/视频 asset 拖入时间线创建 overlay clip。
- [ ] 支持 position、scale、rotation、anchor、crop、opacity、z-order。
- [ ] 支持 mask、圆角、阴影、边框、fit/fill、循环和 playback rate。
- [ ] 对齐线、安全区吸附、品牌锁和 presenter/subtitle 避让。
- [ ] 跨页持续由 timeline duration 和 continuity group 控制。
- [ ] 背景移除只引用派生资产，不在编辑器内修改原文件。

### Task 5.9：转场与覆盖层工作台

- [ ] 时间线显示 transition handle、重叠范围和 J/L 音频边界。
- [ ] TransitionInspector 提供 preset、duration、easing 和连续性选项。
- [ ] OverlayInspector 与预览画布双向选择和拖动。
- [ ] 拖动期间使用本地预览，提交使用 batch command。
- [ ] 低性能设备可降低预览质量但不改变 graph。

### Task 5.10：真实媒体与性能门禁

- [ ] cut/dissolve/wipe/slide/zoom、J Cut、L Cut 和章节 transition 视觉回归通过。
- [ ] 透明 PNG、带 alpha 视频、4K overlay、Logo 品牌锁和长音乐通过。
- [ ] 50 页连续转场项目可预览、渲染、暂停和恢复。
- [ ] 转场边界音画同步误差在允许范围内。
- [ ] 旧项目默认仍使用 cut；关闭 flag 可回退。

**Continuity Gate:** RenderGraph V2 的 overlap、audio mix、overlay 和 continuity 语义冻结后，进入多规格导出。

---

## Phase 5：多规格导出系统

### Task 6.1：ExportPreset 领域模型和注册表

- [ ] 实现 container、codec、width/height、rational fps、quality、audio、subtitle 和 segment policy。
- [ ] 内置 preset 只读、版本化；用户 preset 可复制、修改和归档。
- [ ] 导出 job 固定引用 preset revision，不读取运行中的 mutable current。
- [ ] 参数范围、容器/编码组合和未知字段严格验证。
- [ ] 平台 preset 记录版本、来源日期和说明，不包含自动发布凭据。

### Task 6.2：参数化现有视频契约

- [ ] 移除 ProjectVideoProps、API DTO、Remotion 和 FFmpeg 路径中的固定 30fps 假设。
- [ ] 支持 24/25/30/50/60fps 和有理数帧率边界。
- [ ] 支持 16:9、9:16、1:1、4:5 与安全自定义尺寸。
- [ ] 所有帧计算统一由 integer microseconds 转换。
- [ ] 旧项目默认 30fps 和原画幅，成片不发生无意变化。

### Task 6.3：多画幅布局编译

- [ ] 实现 fit、responsive、manual_override 三种布局策略。
- [ ] 字幕、presenter、overlay、标题和安全区使用同一 layout resolver。
- [ ] 用户可保存画幅专用 transform override。
- [ ] 画幅变更正确失效布局、预览、graph 和正式渲染。
- [ ] 横屏、竖屏、方屏和 4:5 截图回归通过。

### Task 6.4：编码器能力探测与预检

- [ ] 探测 FFmpeg 编码器、GPU encoder、最大分辨率、像素格式和容器支持。
- [ ] 不可用编码器在提交前阻断，并给出安全替代 preset。
- [ ] 4K、60fps、H.265、VP9/AV1 按实际能力开放，不伪装支持。
- [ ] 磁盘估算包含中间文件、音频、字幕和制作包余量。
- [ ] 能力摘要进入诊断中心但不暴露绝对路径。

### Task 6.5：多 preset 导出任务

- [ ] 一个 ExportBatch 对同一 timeline revision 提交多个 preset。
- [ ] 画布/fps/烧录字幕相同的 preset 可共享中间渲染。
- [ ] 仅码率、音频或容器变化可走安全转码分支。
- [ ] 每个子导出独立进度、状态、错误和产物，不覆盖其他 preset。
- [ ] 暂停、取消、恢复和应用重启测试通过。

### Task 6.6：GIF、短视频切片和章节导出

- [ ] GIF 支持时间范围、尺寸、fps、调色板和大小预估。
- [ ] 短视频切片支持固定时长、marker、章节和人工范围。
- [ ] 切片边界遵守关键帧/重编码策略，避免音画缺口。
- [ ] 章节导出使用 timeline marker 和 continuity group。
- [ ] 文件命名模板防止路径逃逸和覆盖已有成功产物。

### Task 6.7：导出工作台

- [ ] preset 浏览、复制、编辑、能力可用性和磁盘估算。
- [ ] 多选 preset，显示共享渲染与单独转码计划。
- [ ] 输出范围选择：全片、章节、marker、手动区间。
- [ ] 展示各子任务进度、等待原因、错误、重试和产物入口。
- [ ] 对应用/覆盖/删除等动作要求明确确认。

### Task 6.8：质量检测与制作包集成

- [ ] 每个导出产物运行对应规格的 FFprobe 和质量策略。
- [ ] 质量报告记录 preset revision、graph hash 和编码器版本。
- [ ] 制作包包含视频、软字幕、封面、章节、报告和 manifest。
- [ ] 不自动包含素材库原始文件或授权正文。
- [ ] 多产物原子发布；失败不覆盖旧成功版本。

### Task 6.9：多规格真实验收

- [ ] 720p、1080p、4K；24/25/30/60fps 代表组合通过。
- [ ] 16:9、9:16、1:1、4:5 的字幕、presenter、overlay 和转场通过。
- [ ] H.264 必过；其他编码器按环境能力有通过或明确跳过报告。
- [ ] GIF、短视频切片、章节视频、软字幕和制作包通过。
- [ ] Windows 安装版暂停、恢复、磁盘满和编码器不可用通过。

**Export Gate:** ExportPreset、layout、encoder capability、export job 和 package manifest 冻结。

---

## Phase 6：多项目批量生产与资源调度

### Task 7.1：审计并统一现有任务系统

- [ ] 列出主 JobRepository、RenderJobWorker、外围平台 worker 和各自状态机。
- [ ] 选择主 JobRepository 为唯一项目任务权威。
- [ ] 外围任务通过 adapter 投影，不复制任务状态机。
- [ ] 所有长任务补齐 fingerprint、checkpoint、cancel 和 restart recovery。
- [ ] 单消费者 Worker 保留为兼容 executor，不直接删除。

### Task 7.2：BatchPlan、BatchItem 和依赖图

- [ ] 实现 batch revision、priority、time window、failure policy 和 item 输入。
- [ ] BatchItem 只引用项目 revision、操作类型和版本化参数。
- [ ] 依赖图拒绝循环、未知 item 和跨 ownership 引用。
- [ ] 相同 idempotency key 不重复创建批次。
- [ ] 批次修改生成新 revision，不改写运行中 revision。

### Task 7.3：ResourceRequest、ResourceLease 和策略

- [ ] 定义 CPU、内存、GPU/显存、磁盘、Office、浏览器和模型资源。
- [ ] 每个 JobType 注册默认请求和可配置上限。
- [ ] lease 有 owner、generation、expires_at、heartbeat 和 release reason。
- [ ] 过期 lease 只能在进程身份和 generation 校验后回收。
- [ ] 资源预算持久化；非法配置不覆盖上一份成功策略。

### Task 7.4：本地调度器核心

- [ ] 实现 priority queue、同优先级轮转、项目并发上限和资源匹配。
- [ ] 前台预览保留最小 CPU/内存预算。
- [ ] 资源不足进入 waiting_resource，并显示具体类别而非忙循环。
- [ ] 调度事务保证 job transition 与 lease 创建一致。
- [ ] 调度器异常退出不产生重复 lease 或重复执行。

### Task 7.5：依赖、优先级与夜间队列

- [ ] waiting_dependency 在上游成功后原子进入 queued。
- [ ] 上游失败按 stop_all/continue/retry_failed 传播。
- [ ] 支持批次和 item 优先级；提升等待权重但不突破资源上限。
- [ ] 支持本地时间夜间窗口、跨午夜和夏令时安全处理。
- [ ] 睡眠/唤醒、系统重启和时钟回拨恢复测试通过。

### Task 7.6：执行器池与任务隔离

- [ ] CPU、GPU、Office、browser 和 lightweight executor 分池。
- [ ] executor 领取任务前二次确认 lease generation 和输入 fingerprint。
- [ ] 子进程使用 job-scoped 临时目录和进程组。
- [ ] 取消只终止当前 lease 的进程；不杀无关 Node/FFmpeg/Office。
- [ ] 内存或磁盘超预算时暂停或失败，不让主 API OOM。

### Task 7.7：页面级失败重跑与缓存复用

- [ ] RenderGraph 节点映射到页面/区间工件和 checkpoint。
- [ ] 单页失败只重跑该页及依赖重叠区，不重做全部成功页面。
- [ ] 输入 hash 变化时旧 checkpoint 标记 stale。
- [ ] 重试保存新 attempt，旧成功工件继续可审计。
- [ ] 转场跨页失败正确包含相邻 overlap 区间。

### Task 7.8：恢复、租约回收与 exactly-once 发布

- [ ] 启动时扫描 running/leased/pausing 和未完成 batch。
- [ ] 进程消失且 lease 过期后进入 paused 或 retryable，不直接标记成功。
- [ ] publish 使用 generation token、临时路径和 compare-and-swap pointer。
- [ ] 重复执行可复用相同成功工件，但不能重复发布或重复写审计。
- [ ] 断电、强杀、数据库锁、磁盘满和损坏 checkpoint 测试通过。

### Task 7.9：Batch 和 Scheduler API

- [ ] 实现 create/get/list/action/retry-failed/archive batch API。
- [ ] 实现 resources、leases 摘要、policy get/update API。
- [ ] 支持按项目、状态、优先级、计划窗口和失败原因分页筛选。
- [ ] API 不返回项目绝对路径、素材正文或敏感命令行。
- [ ] expected_revision、ownership、ETag 和错误 envelope 通过。

### Task 7.10：批量生产中心与资源监视器

- [ ] 批量导入项目/材料、选择操作、preset、优先级和夜间窗口。
- [ ] 显示批次依赖图、项目进度、等待资源和失败摘要。
- [ ] 支持暂停、继续、取消、重试失败页和调整未运行 item 优先级。
- [ ] 资源视图显示预算、使用、lease 和前台保留，不暴露敏感进程参数。
- [ ] 20+ 项目和大量 item 使用分页/虚拟化。

### Task 7.11：资源与批量门禁

- [ ] 20 个项目批次、不同优先级和依赖顺序正确。
- [ ] CPU、内存、GPU、磁盘、Office 独占限制不被突破。
- [ ] 前台编辑/预览在后台批量运行时仍可用。
- [ ] 夜间开始、跨午夜、睡眠唤醒和重启恢复通过。
- [ ] 单页失败重跑、批次 continue/stop_all/retry_failed 通过。
- [ ] 峰值内存、磁盘和子进程数量写入验收报告。

**Scheduler Gate:** 任务权威唯一、资源租约可恢复、发布 exactly-once 和前台保底全部通过。

---

## Phase 7：七项目主线集成与发布

### Task 8.1：跨项目失效矩阵落地

- [ ] 将设计文档中的依赖矩阵写入 dependency graph 和自动测试。
- [ ] material、asset、timeline、subtitle、effect、transition、preset 变化只失效正确节点。
- [ ] current pointer 切换、restore 和 feature flag 回退都触发正确刷新。
- [ ] 删除/归档素材前检查所有项目引用和历史 revision。
- [ ] 诊断中心能解释“为什么需要重新编译/渲染”。

### Task 8.2：七步工作流接入

- [ ] 第 2 步接入 MaterialCollection 和项目素材视图。
- [ ] 第 3-4 步匹配/旁白消费材料集合，而不是假设单一大纲。
- [ ] 第 5 步音频、字幕和 presenter 进入统一时间线。
- [ ] 第 6 步提供时间线、字幕、转场、overlay 和权威预览。
- [ ] 第 7 步提供多规格导出、质量检测和制作包。
- [ ] 全局导航提供素材库、批量中心和资源监视器。
- [ ] 关闭任一 flag 时仍能完成旧七步流程。

### Task 8.3：旧项目迁移与双读兼容

- [ ] 旧项目只读打开不写 V2 文件。
- [ ] 启用新编辑器前显示迁移预览、磁盘需求和不可逆边界。
- [ ] 迁移创建新 revision 和兼容备份，不覆盖旧正文。
- [ ] 旧 Props/Subtitle/SourceFile 读取至少保留一个发布周期。
- [ ] 迁移中断、重复执行、回滚和降级打开测试通过。
- [ ] 迁移前后原素材和旧成片 hash 不变。

### Task 8.4：安全总门禁

- [ ] 路径穿越、伪 MIME、压缩炸弹、恶意 Office、字体/LUT 和超大媒体攻击测试。
- [ ] command injection、FFmpeg 参数、文件名模板和远程 URL 安全测试。
- [ ] 项目 ownership、跨项目 asset 引用、授权阻断和诊断脱敏测试。
- [ ] scheduler 进程身份、lease generation 和越权取消测试。
- [ ] 制作包、日志、数据库和 API 不包含密钥或绝对用户路径。
- [ ] 建立 `docs/acceptance/p1-production-security-report.md`。

### Task 8.5：性能与资源总门禁

- [ ] 50 页、500 clips、20 tracks 编辑器交互验收。
- [ ] 1,000 素材搜索、缩略图和代理渐进加载验收。
- [ ] 双语字幕、转场、overlay 的横/竖/方屏预览验收。
- [ ] 4K30、1080p60 和多 preset 导出峰值资源验收。
- [ ] 20 项目批次和前台编辑并行验收。
- [ ] 记录 CPU、GPU、内存、磁盘、子进程、队列等待和缓存命中。
- [ ] 建立 `docs/acceptance/p1-production-performance-report.md`。

### Task 8.6：端到端与 Windows 安装版闭环

- [ ] 场景 A：无大纲 + 多套 PPT → 时间线 → 双语字幕 → 横竖屏导出。
- [ ] 场景 B：真人视频 + J/L Cut + overlay + 音乐 → 4K 成片。
- [ ] 场景 C：多文档、多章节、替换页面 → 差异同步 → 失败页重跑。
- [ ] 场景 D：20 项目夜间批次 → 重启恢复 → 质量报告和制作包。
- [ ] Windows 安装、启动、关闭、升级后打开旧项目和新项目。
- [ ] Office/LibreOffice 存在与不存在两种能力降级路径。
- [ ] 断网、睡眠、端口占用、磁盘满、GPU 不可用和强杀恢复。

### Task 8.7：文档、Feature Flag 和分阶段发布

- [ ] 更新用户手册：材料、素材、时间线、字幕、转场、导出和批量中心。
- [ ] 更新管理员/排障文档：资源策略、缓存、代理、迁移和恢复。
- [ ] 为七个 feature flags 定义默认值、依赖、升级和回滚。
- [ ] 发布顺序为只读预览 → 可编辑 → 新预览 → 新渲染 → 默认开启。
- [ ] 每一阶段都有 telemetry/诊断指标和回退条件。
- [ ] 形成 `docs/acceptance/p1-production-release-report.md`。

---

## 4. 推荐实施顺序与并行规则

### 4.1 严格顺序

1. Phase 0：冻结恢复基线和共享契约。
2. Phase 1：完成统一时间线与 RenderGraph V2。
3. Phase 2A/2B：素材库基础层与灵活材料组织。
4. Phase 3：高级字幕工作台。
5. Phase 4：跨页转场、J/L Cut 和媒体覆盖层。
6. Phase 5：多规格导出。
7. Phase 6：批量生产和资源调度。
8. Phase 7：主线集成、迁移、Windows 和发布。

### 4.2 允许并行

- Phase 2A 和 2B 可并行，但 AssetRef、MaterialPageRef 和 shared import adapter 由 Foundation owner 管理。
- Phase 3 的 UX 原型可在 Phase 2 中进行，但正式 subtitle timing/RenderGraph 代码等 Timeline V2 冻结。
- Phase 5 的 preset UX 可在 Phase 4 中进行，但正式编码参数化等 overlap RenderGraph 稳定。
- Phase 6 的调度模拟器可提前开发，但不得在任务恢复契约冻结前接管真实任务。

### 4.3 禁止并行

- 两个窗口同时修改 `domain/models.py`、`storage/migrations.py` 或 OpenAPI。
- 时间线和转场项目分别计算总时长。
- 字幕工作台和 Remotion 字幕层分别维护 cue 时间。
- 素材库和材料组织分别建立重复的文件对象存储。
- 多规格导出另建一套渲染任务状态机。
- 批量调度绕过现有 JobRepository 直接启动 FFmpeg/Node/Office。

## 5. 每阶段固定验证命令类别

具体命令以项目脚本为准，但每个阶段至少执行：

- [ ] Python unit、contract、integration、security tests。
- [ ] Ruff、mypy、migration tests 和 OpenAPI snapshot。
- [ ] Web lint、typecheck、Vitest 和关键 Playwright E2E。
- [ ] Remotion typecheck、tests、关键帧截图和代表性短渲染。
- [ ] FFprobe/质量报告验证真实输出。
- [ ] Windows launcher、安装版、暂停/恢复和关闭进程检查。
- [ ] 修改范围 `git diff --check` 和无意外大文件/密钥扫描。

## 6. 阶段提交规则

每个 Task 形成一个或多个小型独立提交，建议前缀：

```text
feat(timeline): ...
feat(assets): ...
feat(materials): ...
feat(subtitles): ...
feat(transitions): ...
feat(export): ...
feat(scheduler): ...
test(...): ...
docs(...): ...
```

- [ ] 提交只包含本 Task 责任文件和对应测试。
- [ ] 不提交缓存、代理、成片、node_modules、临时数据库或恢复备份。
- [ ] 合并前重放该阶段 gate，并记录测试结果。
- [ ] 集成分支只合并已通过门禁的提交，不手工复制目录。

## 7. 最终验收清单

### 7.1 统一时间线

- [ ] 页面、旁白、真人、字幕、特效、音乐、音效和 overlay 在同一时间线。
- [ ] 拖动、裁剪、分割、吸附、选择、ripple、撤销重做和实时预览可用。
- [ ] 预览、渲染和质量报告记录同一 graph hash。

### 7.2 素材与材料

- [ ] 素材跨项目复用、hash 去重、代理、派生资产、授权和品牌包可用。
- [ ] 支持无大纲、多文档、多课件、章节合并拆分、页面重排和替换。
- [ ] 材料同步时间线前有差异预览，人工锁定编辑不被覆盖。

### 7.3 字幕与连续镜头

- [ ] 字幕支持样式、逐词高亮、双语、翻译、人工断句、模板和软/烧录切换。
- [ ] 跨页重叠转场、J/L Cut、章节连续性和跨页 overlay 可用。
- [ ] 横屏、竖屏和方屏的字幕/presenter/overlay 安全区正确。

### 7.4 导出与批量

- [ ] 720p/1080p/4K、24/25/30/60fps 和多画幅代表组合通过。
- [ ] GIF、短视频切片、章节视频、软字幕和制作包通过。
- [ ] 20 项目批次遵守依赖、优先级、资源上限、失败策略和夜间窗口。
- [ ] 单页失败可重跑，应用重启后任务和批次可恢复。

### 7.5 兼容、安全与发布

- [ ] 旧项目不迁移也可打开和导出；显式迁移可回滚。
- [ ] 原素材、旧成片和 workspace-data 不被无意改写。
- [ ] 安全、性能、Windows、迁移和发布报告齐全。
- [ ] 七个 feature flags 可独立关闭且有明确依赖。
- [ ] 用户手册、排障、诊断和错误提示完整。

**Final Gate:** 上述清单全部通过，且不存在用单元 mock 代替真实媒体、真实 Windows 或安装版验收的情况，才可将七项能力设为默认开启。
