# PPT Video Workbench 个人 Windows 可用正式收口设计

> 日期：2026-08-15
>
> 状态：Approved for implementation
>
> 产品工作树：`F:\ppt-video-workbench-v3\.worktrees\program-integration-v1`
>
> 当前分支：`codex/program-integration-v1`
>
> 当前 HEAD：`cc0f0c6b5d5cb8c6c08b95fd59fce71b19dfb522`
>
> 当前冻结候选：`rc-cc0f0c6-20260814T174100Z`
>
> 配套实施计划：[2026-08-15-personal-windows-formal-closure.md](../plans/2026-08-15-personal-windows-formal-closure.md)

## 1. 结论

第二层“个人 Windows 可用”尚未正式关闭。当前状态是 P01 已完成、P02 部分完成、P03-P08 尚未绑定同一个最终候选完成正式验收；DP45 的通过证据属于旧候选，不能自动继承到最终候选。

本轮采用以下推荐方案：

1. 保留 `rc-cc0f0c6-20260814T174100Z` 为不可变的 V1 安全候选和安装链基线，不继续在其上形成最终 V2 结论。
2. P02 先完成剩余源码门禁和最终策略确认，使用现有 V2 接受策略生成一个新的唯一最终候选。
3. P03-P08 只对该最终 V2 候选执行，不混用 `cc0f0c6`、`bfe03a8` 或其他历史候选证据。
4. P08 先形成 `PERSONAL_USE_FUNCTIONAL_READY`；DP45 八小时窗口可在其后执行。
5. 最终候选 DP45 未通过前，`PERSONAL_USE_READY` 保持 `BLOCKED_DEFERRED_G04`；通过后再提升为 `PASS`。

这避免了一个关键矛盾：如果先在 `cc0f0c6` V1 候选上重跑 P03/P04，随后为了 P05 切换到 V2 策略，那么策略和安装包变化会使 P03/P04 证据立即失效，必须全部重跑。

## 2. 当前事实基线

### 2.1 仓库与候选

| 项目                     | 当前事实                                                           |
| ------------------------ | ------------------------------------------------------------------ |
| 方案创建前工作树         | clean；本方案创建后仅新增两份未提交 Markdown 文档                  |
| 分支                     | `codex/program-integration-v1`                                     |
| HEAD                     | `cc0f0c6b5d5cb8c6c08b95fd59fce71b19dfb522`                         |
| 相对 upstream            | behind 0 / ahead 62                                                |
| 当前候选                 | `rc-cc0f0c6-20260814T174100Z`                                      |
| installer SHA-256        | `9adae02108a45ebfa1d28690b0ee8a548b5b977d2007cb08e8fa50b256acb508` |
| runtime manifest SHA-256 | `d0c63edc8a64846c84edc529dfe656a362be5c5bfc4c0618f3032fe942a8577a` |
| feature policy           | `effects-v1-safe-default`                                          |

### 2.2 八项目状态

| 顺序 | 项目                | 当前状态           | 本轮目标 Gate                                                                 |
| ---: | ------------------- | ------------------ | ----------------------------------------------------------------------------- |
|  P01 | Effects V2 工程     | 已完成             | `EFFECTS_ENGINE_READY=PASS`                                                   |
|  P02 | 源码、CI、最终候选  | 部分完成           | `SOURCE_CANDIDATE_FROZEN=PASS`、`CI_GREEN=PASS`、`FINAL_CANDIDATE_BUILT=PASS` |
|  P03 | Windows 安装启动    | 待最终候选复验     | `INSTALLED_READY=PASS`                                                        |
|  P04 | 真实 PPT 完整转视频 | 未收口             | `LOCAL_FLOW_READY=PASS`、`UI_EXPORT_READY=PASS`                               |
|  P05 | Effects V2 动态验收 | 未收口             | `EFFECTS_READY=PASS`                                                          |
|  P06 | 恢复、重装、回滚    | 未收口             | `RECOVERY_READY=PASS`                                                         |
|  P07 | 媒体质量与人工视听  | 未收口             | `QUALITY_READY=PASS`                                                          |
|  P08 | 最终审计交付        | 未开始最终版       | `PERSONAL_USE_FUNCTIONAL_READY=PASS`                                          |
|  G04 | DP45 最终候选长稳   | 历史候选通过两小时 | `DP45_READY=PASS`、`PERSONAL_USE_READY=PASS`                                  |

### 2.3 已有能力与不可复用边界

可以复用的工程能力：

- Effects V2 的计划、模板、解释器、L0-L3 风险分级、人工锁、批量应用、预览和渲染合同。
- 候选身份、发行构建、runtime manifest、安装包清单和独立校验器。
- Windows schema 2.0 验收入口、真实 PPT 导入、开发态 S1/S8、恢复测试、媒体质量引擎和 DP45 runner。
- 旧候选两小时 DP45 运行可作为容量和流程基线。

不能直接提升为最终证据的内容：

- 其他 source commit、candidate ID、installer、runtime 或 feature policy 的结果。
- synthetic provider、静态帧、单元测试或开发态 E2E 替代安装版真实流程。
- 旧候选最终 MP4、质量报告、人工审片或 DP45。
- 超时、运行中、无完成标记或中断的长任务。
- 自动生成的人工签署人、接受决定和审片意见。

## 3. 收口目标与非目标

### 3.1 必须达成

- 一套 clean source commit、candidate ID、installer、runtime manifest 和 V2 feature policy 的唯一身份链。
- 普通 Windows 用户的安装、首次启动、第二次启动、卸载重装和工作区保留。
- 小型、标准、复杂三类 PPT 的非 synthetic 完整 UI 转视频流程。
- 当前候选 30 页 Effects V2 动态预览、最终片段、V1 回退和人工抽检。
- API、Worker、Node、FFmpeg 的物理中断恢复，以及同候选重装和显式上一版本回滚。
- 当前候选最终 MP4 的自动媒体检查和具名人工视听决定。
- P01-P08 证据统一聚合，未完成项复核除明确延期 G04 外为零。

### 3.2 非目标

- HeyGen 真实 canary 保持 `WAIT_EXTERNAL`，不阻断本地音频链。
- macOS/Linux、团队协作、云端发布、公开分发和代码签名不属于本层功能收口。
- 不修改用户原始 PPT，不接触正式 workspace，不复用生产数据库。
- 不在缺少显式授权时推送远端、创建 PR、发布安装包或上传用户文件。

## 4. 最终候选策略

### 4.1 推荐策略

最终候选使用现有 `schemas/feature-policy-effects-v2-acceptance.json` 的行为语义：

```json
{
  "policy_id": "effects-v2-acceptance",
  "legacy_project_default": "v1",
  "new_project_default": "v2",
  "effects_v2": {
    "persistence": true,
    "preview": true,
    "render": true
  },
  "allow_fallback": true
}
```

约束如下：

- persistence、preview、render 三个开关必须同时开启或同时关闭。
- 旧项目默认 V1，不自动迁移；新项目默认 V2。
- 用户可显式回退 V1/L0，回退不删除 EffectPlan、人工锁和用户设置。
- 候选构建时将 candidate ID 写入规范化策略；P03-P08 不再修改策略。
- 如果策略内容、policy ID 或模板发生变化，返回 P02 创建新候选。

### 4.2 `cc0f0c6` 的定位

`rc-cc0f0c6-20260814T174100Z` 保留用于：

- 验证 V1 安全默认和回退行为。
- 作为版本回滚测试的 previous candidate 候选之一。
- 对照安装包尺寸、启动性能和 runtime 布局。

它不用于声明 Effects V2 完善，也不承载最终 P03-P08 Gate。

## 5. 唯一身份链

```text
clean final source commit
  -> final candidate ID
  -> uv.lock / pnpm-lock.yaml hashes
  -> normalized V2 feature policy hash
  -> runtime manifest hash
  -> installer hash
  -> Windows installed candidate identity
  -> PPT input and project snapshot hashes
  -> EffectPlan / RenderGraph / export spec hashes
  -> render job / attempt / publication identity
  -> final MP4 and production package hashes
  -> automatic quality report
  -> named manual reviews
  -> P01-P08 final audit
  -> optional final-candidate DP45
```

任何链上节点变化，都必须依据第 11 节的失效矩阵重跑受影响项目。

## 6. 证据模型

每个候选使用独立根目录：

```text
test-results/personal-use/<candidate-id>/
├─ candidate/
│  ├─ candidate-identity.json
│  ├─ release-artifacts.json
│  ├─ runtime-manifest.json
│  └─ feature-policy.json
├─ gates/
│  ├─ p01-effects-engine-ready.json
│  ├─ p02-source-candidate.json
│  ├─ p03-installed-ready.json
│  ├─ p04-local-flow.json
│  ├─ p05-effects-ready.json
│  ├─ p06-recovery-ready.json
│  └─ p07-quality-ready.json
├─ runs/
│  ├─ local-gates/<run-id>/
│  ├─ windows/<run-id>/
│  ├─ real-ppt/<run-id>/
│  ├─ effects/<run-id>/
│  ├─ recovery/<run-id>/
│  ├─ quality/<run-id>/
│  └─ dp45/<run-id>/
├─ reviews/
│  ├─ effects-manual-review.json
│  └─ final-av-review.json
├─ defects/
├─ final-evidence-manifest.json
├─ personal-use-signoff.json
└─ final-audit.json
```

阶段报告至少包含：

- `schema_version`、`stage_id`、`run_id`、`candidate_id`、`source_commit`。
- `status`、`started_at`、`finished_at`、`attempt`、`reason_codes`。
- 输入、配置、策略、runtime、installer 和输出 SHA-256。
- 相对 `evidence_refs`、process registry、缺陷列表和下一 Gate。
- 人工 Gate 的 `reviewer`、`reviewed_at`、`decision` 和被审 artifact hash。

状态只允许：`passed`、`failed`、`blocked`、`cancelled`、`stale`。`running` 或超时不能视为通过。

## 7. 项目设计

### 7.1 P01：Effects V2 工程基线确认

P01 不重新开发已完成能力，只做最终候选前的只读复核：

- 专项测试覆盖动态聚合器、Windows Effects 隔离、主线解释器、批量恢复和 V1 fallback。
- feature policy schema 拒绝不完整的 V2 开关组合。
- 30 页教育样本清单和 ground truth 可解析，所有来源 hash 匹配。
- P01 只在源码发生回归时重新打开；正常情况下输出当前 commit 的 `EFFECTS_ENGINE_READY=PASS`。

### 7.2 P02：源码、CI 与最终候选

P02 是本轮唯一允许产生最终候选的阶段：

1. 先补齐所有下游验收工具，特别是 Windows runner 中仍被硬编码为 `blocked` 的阶段、安装版 30 页动态 evidence 生成器、物理故障注入、单个最终 MP4 质量入口，以及功能收口/完整收口两级聚合语义；这些工具属于候选源码，必须在冻结前完成。
2. 完成本地完整门禁，包括 Python、ruff、mypy、pytest、Web、Remotion、Playwright、contract、release 和 security。
3. 修复门禁问题后形成 clean commit；每次源码修复都会使旧候选失效。
4. 确认 V2 最终策略并生成新 candidate ID。
5. 分支当前领先远端 62 个提交；远端 push/CI 属于外部写操作，必须在获得授权后执行。
6. required CI 必须绑定最终 source commit；无远端结果时写 `BLOCKED_EXTERNAL_CI`。
7. 使用显式 V2 policy 构建 installer/runtime，并执行独立 `-Verify`。
8. 完成 source/build/runtime/project 四门 preflight。

P02 完成后冻结候选；所有下游项目只接受该候选。

### 7.3 P03：Windows 安装与启动

P03 使用新的隔离 InstallRoot、WorkspaceRoot、StateRoot、LogRoot 和端口范围：

- 普通用户静默安装成功，安装目录原先不存在。
- launcher、API、Web、Node、FFmpeg/FFprobe、Remotion runtime 和 feature policy 完整。
- 首次启动、关闭、第二次启动和重装后启动分别通过。
- API 只绑定 loopback；candidate、runtime 和 policy 身份一致。
- 工作区与安装目录隔离；卸载不删除 workspace。
- 只终止本次 run 登记且创建时间匹配的 PID。

### 7.4 P04：真实 PPT 完整转视频

输入矩阵：

| 档位 |     页数 | 必须覆盖                                           |
| ---- | -------: | -------------------------------------------------- |
| 小型 |   2-5 页 | 文本、图片、本地音频、字幕、快速导出               |
| 标准 |  8-15 页 | 图表、图片、长文本、分页、特效、取消重试           |
| 复杂 | 30-50 页 | 嵌入媒体、字体替换、复杂布局、长字幕、恢复和制作包 |

每份 PPT 必须：

- 使用授权副本，开始和结束时原文件 SHA-256 不变。
- 从安装版 UI 新建项目并导入，核对页数、标题、图片、图表、字体和引用。
- 使用真实本地音频；本地 ASR 模型必须由受控模型清单提供并校验 hash。
- 完成旁白确认、音频分页、字幕生成与至少一次人工修订。
- 应用 V2 推荐、人工锁和批量应用，完成 fresh preflight。
- 从 0 播放到 ended，随后由 UI 提交最终导出。
- 刷新 UI 和重启 launcher 后仍能发现项目、job、attempt 和 publication。
- 生成最终 MP4、SRT 和制作包，验证 manifest、大小和 hash。

内部样本可以关闭工程 Gate，但不能替代用户最终成片签署；若未使用用户样本，必须保留 `USER_SAMPLE_REVIEW_PENDING`。

### 7.5 P05：Effects V2 动态专项

使用 `fixtures/effects/education-v2` 的 30 页矩阵：

- 10 类页面各 3 页，覆盖 L0-L3 和四档强度。
- 30/30 动态预览和 30/30 最终片段成功。
- preview/render 的 EffectPlan、RenderGraph、template、runtime 和 policy hash 一致。
- 检查从头、seek、中段、页边界和结束帧，无缺帧、错误候选或时长漂移。
- 检查字幕安全区、Presenter/Overlay 避让、镜头运动、转场和信息裁切。
- 使用项目副本关闭 V2，验证 V1 预览/导出和 V2 数据保留。
- 每类至少人工抽检 1 页，P0/P1 必须为零。

### 7.6 P06：恢复、重装与回滚

故障矩阵：

| 故障               | 注入点               | 通过条件                          |
| ------------------ | -------------------- | --------------------------------- |
| API 中断           | 已写入 checkpoint 后 | 重启后状态可恢复，不伪报成功      |
| Worker 中断        | 分页或渲染中         | 已完成页复用，未完成页继续        |
| Node/Remotion 中断 | 预览或最终渲染中     | attempt 可重试，graph/spec 不漂移 |
| FFmpeg 中断        | 分页与最终合成各一次 | staging 清理，上一成功 MP4 保留   |
| 输出锁/不可写      | publish 前           | 稳定 publication 和 latest 不损坏 |
| 端口冲突           | launcher 启动时      | 明确错误并可安全重试              |
| TEMP 不可写/低磁盘 | 中间产物阶段         | fail-closed，有可操作诊断         |

随后执行：

- 取消、一次安全重试、UI 刷新和 launcher 重启。
- 同候选卸载重装，原项目和输出仍存在。
- 使用显式 previous candidate 执行升级和回滚。
- active/previous 指针和 payload hash 正确；回滚不删除 V2 数据。

### 7.7 P07：媒体质量与人工视听

对 P04 的每个最终 MP4 执行：

- ffprobe、完整 decode-to-null、容器、codec、分辨率、fps、像素格式和时长检查。
- 黑帧、冻帧、异常静音、爆音、LUFS、true peak、音画时长差和丢帧检查。
- 字幕时间、边界、安全区、遮挡和软/烧录策略检查。
- final MP4 与 project snapshot、graph、spec、runtime、job、attempt、publication 身份一致。
- 自动报告绑定 MP4 SHA-256。

人工视听必须由用户或指定 reviewer 完整播放最终成片并具名决定。自动化只能生成待审清单，不能填写 `accepted_by`。

### 7.8 P08：最终审计与交付

P08 显式读取 P01-P07 报告，不搜索“最新”文件：

- 所有报告的 candidate、source、installer、runtime、policy 和 artifact hashes 一致。
- 所有 evidence refs 存在、位于候选根内且 hash 匹配。
- P0/P1 为零；P2 有 owner、规避方案和具名接受；P3 登记限制。
- 当前工作树 clean，HEAD 与最终 source commit 一致。
- 生成最终证据清单、签署、七步操作说明、Effects V2 回退说明和恢复说明。
- 第二轮搜索 unchecked、TODO、blocked、not_run、stale 和 failed；除 G04 外为零。

P08 输出：

- `PERSONAL_USE_FUNCTIONAL_READY=PASS`：P01-P08 均关闭。
- `PERSONAL_USE_READY=BLOCKED_DEFERRED_G04`：最终候选 DP45 尚未执行。
- `PERSONAL_USE_READY=PASS`：P01-P08 和最终候选 G04 全部通过。

## 8. G04：最终候选 DP45

历史 `bfe03a8` 两小时 DP45 只作为历史容量基线。正式收口采用两段式：

1. 先运行 2 小时资格检查，确认配置、隔离、采样和恢复无明显问题。
2. 有完整窗口后运行 8 小时 S50/批量等价负载，作为最终 `DP45_READY` 证据。

八小时 Gate 至少满足：

- duration 和 minimum cycles 同时满足，正式 completion marker 存在。
- normal、recovery、cancel/retry、cache reuse 和 publication retention 均被覆盖。
- 无孤儿进程、端口泄漏、失控临时文件和上一成功 publication 损坏。
- ledger、资源 JSONL、completion、config 和 report hash 一致。
- TEMP/TMP/TMPDIR 使用独立 F 盘根，不复用历史 run。
- candidate/source/runtime/policy 与 P08 最终候选一致。

## 9. Gate 判定规则

- P0/P1：立即阻塞，必须修复并从最早受影响项目重跑。
- P2：默认阻塞；只有具名 owner、明确影响、规避方案、`accepted_by` 和 `accepted_at` 才能接受。
- P3：登记为已知限制，不阻塞个人使用。
- 外部 CI、人工审片、用户样本或长稳窗口缺失时使用 `blocked`，不得降级为 warning 后宣布通过。
- synthetic、mock、fixture 和源码测试必须在报告中标注 scope，不能冒充物理安装或真实媒体证据。

## 10. 人工与外部边界

需要用户或外部系统参与的项目：

- 远端 push 和 required CI。
- 用户指定或授权的真实 PPT 样本。
- 大体积本地 ASR 模型的下载或受控导入。
- Effects 动态抽检和最终成片视听签署。
- 八小时 DP45 时间窗口。

这些边界不阻止本地工程继续，但相应 Gate 必须保持 blocked。

## 11. 证据失效与重跑矩阵

| 变化                       | 最早返回项目 | 必须重跑                             |
| -------------------------- | ------------ | ------------------------------------ |
| Effects 源码、模板、schema | P01          | P01-P08、G04                         |
| 其他源码、依赖、lockfile   | P02          | P02-P08、G04                         |
| feature policy             | P02          | P02-P08、G04                         |
| installer/runtime 打包     | P02          | P02-P08、G04                         |
| Windows runner 逻辑        | P03          | P03-P08、G04（若影响进程/资源）      |
| PPT、音频、字幕输入        | P04          | P04、P07、P08；影响 Effects 时加 P05 |
| Effects 动态验收缺陷修复   | P01 或 P05   | 从修改层级向下重跑                   |
| 恢复/发布代码              | P02          | P02-P08、G04                         |
| 质量规则                   | P07          | P07-P08；若媒体需重导出则返回 P04    |
| 人工决定变化               | P07          | P07-P08                              |
| DP45 配置变化              | G04          | G04-P08 最终状态更新                 |

## 12. 最终交付物

- 唯一 Windows installer 路径、大小和 SHA-256。
- 唯一 runtime manifest 和 feature policy 路径及 SHA-256。
- 小型、标准、复杂 PPT 的输入、项目、最终 MP4 和制作包身份链。
- P01-P08 Gate JSON、日志、缺陷和证据清单。
- Effects V2 30 页动态报告和人工抽检记录。
- 恢复、重装、回滚报告。
- 自动质量报告和具名人工视听记录。
- `final-evidence-manifest.json`、`personal-use-signoff.json` 和 `final-audit.json`。
- 用户七步操作说明、Effects V2 使用/回退说明、恢复/回滚说明和已知限制。
- 最终候选 DP45 报告；若延期，交付物中保留明确 blocker。

## 13. 成功定义

只有同时满足以下条件，才可以说“个人 Windows 可完整跑一遍，Effects V2 已完善”：

1. 最终 V2 候选的 P01-P08 全部通过。
2. 至少三类真实 PPT 从安装版完成非 synthetic 转视频。
3. 当前候选的 30 页动态 Effects、回退、恢复和质量均通过。
4. 最终 MP4 已由具名 reviewer 完整审看并接受。
5. 安装包、runtime、policy、PPT、项目、MP4 和签署全部绑定同一候选。

DP45 八小时通过后，才可进一步将 `PERSONAL_USE_READY` 提升为无延期项的最终 PASS。
