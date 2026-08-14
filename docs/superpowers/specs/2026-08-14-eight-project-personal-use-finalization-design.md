# PPT Video Workbench 八项目个人可用最终收口设计

> 日期：2026-08-14
>
> 状态：Proposed
>
> 目标工作树：`F:\ppt-video-workbench-v3\.worktrees\program-integration-v1`
>
> 审计基线：`codex/program-integration-v1` / `69efe5ac34f2873596c374856a5d715ac4ba147b`
>
> 配套实施计划：[2026-08-14-eight-project-personal-use-finalization.md](../plans/2026-08-14-eight-project-personal-use-finalization.md)

## 1. 设计结论

当前项目已经具备可构建的 Windows 安装包、完整开发态主链和 Effects V2 的主要源码能力，但尚不能宣称“安装后可完整转视频且特效完善”。本轮采用八个严格有序的项目完成最终收口：先补齐 Effects V2 工程和动态验收工具，再创建唯一新候选，随后在该候选上完成安装、真实 PPT、动态特效、恢复、质量和总审计。

当前候选 `rc-personal-69efe5a-20260814T1625Z` 保留为不可变的 V1 安全构建基线，不继续提升为最终候选，原因如下：

- `effects_v2.persistence/preview/render` 均为 `false`。
- `legacy_project_default` 与 `new_project_default` 均为 `v1`。
- 当前候选只有候选身份、安装包和运行时清单，没有同候选的安装版真实 PPT、动态 Effects、恢复、最终 MP4 和人工视听证据。
- Effects V2 工程或策略发生变化后，旧候选的下游证据必须失效。

本轮目标身份链为：

```text
effects_v2_source_complete
  -> clean_source_commit
  -> candidate_id
  -> installer_sha256
  -> runtime_manifest_sha256
  -> feature_policy_sha256
  -> installed_acceptance_run
  -> real_ppt_project/input/graph/spec hashes
  -> effects_dynamic_evidence
  -> recovery_evidence
  -> final_mp4_sha256
  -> automated_quality_report
  -> named_manual_review
  -> final_closure
```

## 2. 当前事实基线

### 2.1 已完成或可复用

- 产品源明确为 `program-integration-v1`，根目录恢复快照不是构建源。
- 当前审计时工作树 clean，分支为 `codex/program-integration-v1`。
- 当前分支相对远端领先 47 个提交；本地提交不能冒充同 commit 的远端 CI 结果。
- Python 全量、Web、Remotion、类型检查和构建已有同源码本地通过记录。
- Windows 构建链已打通；当前安装包、payload manifest 和候选身份可独立校验。
- 开发态 S1/S8 已覆盖项目创建、PPTX/DOCX 导入、本地音频、预检、权威预览、取消重试、刷新恢复和制作包。
- Effects V2 已有 EffectPlan、模板、L0-L3、安全降级、人工锁、批量应用、预览/渲染解释器和恢复合同。
- 仓库包含 30 份 Effects 内部回归 PPTX，可用于工程动态矩阵，但不能代替用户最终成片验收。
- Windows acceptance schema 2.0、候选清单、个人预检、媒体质量、恢复和 DP45 基础工具均已存在。

### 2.2 仍缺少

- 缺少候选绑定的 `effects_dynamic_acceptance.py` 或等价动态验收聚合器。
- 现有 `windows_effect_acceptance.ps1` 只验证 release 和源码测试，不执行安装版动态预览、最终导出和 V1 回退。
- 现有 `windows-acceptance.ps1` 将 legacy project、interruption recovery、full preflight、play from start、final export 和 version rollback 显式标记为 blocked。
- `uninstall_reinstall` 当前只执行卸载，没有验证重新安装和项目重发现。
- 当前候选没有正式 `FINAL_CANDIDATE_BUILT` 阶段报告，也没有同候选四门预检证据。
- 当前 commit 没有正式远端 CI 证据。
- 没有安装版候选上的小型、标准、复杂 PPT 完整流程证据。
- 没有当前候选的 30/30 动态预览、30/30 最终片段和人工动态抽检。
- 没有安装版 API、Worker、Node、FFmpeg 故障注入和 publication 安全证据。
- 没有最终 MP4 的全量机器质量报告和具名人工视听决定。
- 没有 `PERSONAL_USE_READY=PASS` 和第二轮未完成项为零的证据。

## 3. 范围与边界

### 3.1 必须完成的八个项目

| 顺序 | 项目                             | 主要 Gate                                                      |
| ---: | -------------------------------- | -------------------------------------------------------------- |
|  P01 | Effects V2 工程补齐              | `EFFECTS_ENGINE_READY`                                         |
|  P02 | 重新冻结源码、CI 与 Windows 候选 | `SOURCE_CANDIDATE_FROZEN`、`CI_GREEN`、`FINAL_CANDIDATE_BUILT` |
|  P03 | Windows 安装与启动闭环           | `INSTALLED_READY`                                              |
|  P04 | 真实 PPT 完整转视频              | `LOCAL_FLOW_READY`、`UI_EXPORT_READY`                          |
|  P05 | Effects V2 动态专项验收          | `EFFECTS_READY`                                                |
|  P06 | 中断恢复、重装与回滚             | `RECOVERY_READY`                                               |
|  P07 | 媒体质量与人工视听               | `QUALITY_READY`                                                |
|  P08 | 最终总审计与交付                 | `PERSONAL_USE_FUNCTIONAL_READY` 或 `PERSONAL_USE_READY`        |

### 3.2 G04 延期规则

用户已明确将 DP45 长时间稳定性验收延期。本轮按以下方式处理：

- P01-P08 不因等待长稳窗口而停止开发和短流程验收。
- 不伪造 `DP45_READY=PASS`，不把历史 partial/interrupted 证据升级为通过。
- 若 P08 时 G04 仍未执行，允许输出 `PERSONAL_USE_FUNCTIONAL_READY=PASS`，但 `PERSONAL_USE_READY` 必须保持 `blocked_deferred_g04`。
- 未来 G04 必须使用与最终功能候选完全相同的 source、runtime、installer 和 feature policy；若候选已变化，则创建新候选并重跑受影响 Gate。

### 3.3 非阻塞或非目标

- HeyGen 真实 canary 保持 `WAIT_EXTERNAL`，不阻断本地音频和无音频路径。
- 云端、插件市场、团队协作、macOS/Linux 和公开发布不进入本轮。
- 代码签名属于个人使用后的分发加固，不是本轮功能阻塞项。
- 自动化不得代填用户或指定 reviewer 的人工视听签署。
- 不修改、移动或删除用户原始 PPT、正式 workspace、历史安装、恢复数据和其他 worktree。

## 4. 顺序与失效原则

P01 必须先于安装和真实 PPT 验收。原因是 Effects V2 源码、模板或 feature policy 的任何修改都会使安装包、运行时和所有下游证据失效。

```mermaid
flowchart LR
    A["P01 Effects V2 工程补齐"] --> B["P02 新源码与候选"]
    B --> C["P03 安装与启动"]
    C --> D["P04 真实 PPT 全链"]
    D --> E["P05 Effects 动态专项"]
    E --> F["P06 恢复、重装、回滚"]
    F --> G["P07 质量与人工视听"]
    G --> H["P08 最终总审计"]
    H -. "有长稳窗口" .-> I["Deferred G04 DP45"]
    I --> J["PERSONAL_USE_READY"]
```

统一规则：

1. 一个项目完成后直接进入下一项目，不逐项等待确认。
2. 任何源码、依赖、schema、迁移、模板或策略变更都回到 P02 创建新候选。
3. 候选冻结后不原地修改安装包、runtime、feature policy 或证据。
4. 缺少报告、哈希、完成标记、当前候选身份或人工决定时只能 blocked。
5. 失败只修复最早受影响项目，然后顺序重跑全部下游项目。
6. 所有生成物使用新 `run_id`，不覆盖失败或中断现场。

## 5. 目标组件设计

### 5.1 Effects 动态验收聚合器

新增 `scripts/effects_dynamic_acceptance.py`，职责为：

- 强制消费显式 `candidate manifest`、`feature policy`、project manifest、input root 和 output root。
- 验证 candidate、source、runtime、template、EffectPlan 和 RenderGraph 身份一致。
- 记录每页 preview、final clip、关键帧、时长、帧数和 SHA-256。
- 检测 missing、tampered、stale、wrong-candidate、preview/render hash drift、缺帧和时长漂移。
- 输出 `effects-dynamic-acceptance.json`，状态仅允许 `passed | failed | blocked | stale`。
- 不扫描“最新”目录，不接受其他 worktree 或历史候选证据。

配套新增：

- `schemas/effects-dynamic-acceptance-v1.schema.json`。
- `tests/release/test_effects_dynamic_acceptance.py`。
- `tests/fixtures/effects-dynamic-acceptance/` 的 golden/tampered/missing/wrong-candidate fixture。

### 5.2 Windows Effects runner

扩展 `scripts/windows_effect_acceptance.ps1`：

- 参数增加 candidate manifest、artifact manifest、sample manifest、feature policy、dynamic evidence/output/report、InstallRoot 和 WorkspaceRoot；所有路径显式传入并绑定同一候选。
- 仅从安装目录调用 launcher/API/Node/Remotion/FFmpeg；源码测试只作为补充。
- 新增 `effects_dynamic_preview`、`effects_final_export`、`effects_fallback` 三个正式阶段。
- 每阶段写入独立 JSON、日志和相对 evidence refs。
- 验证生产数据库路径被阻断，只操作验收副本。

### 5.3 Windows 全链 runner

完善 `tests/release/windows-acceptance.ps1` 并复用 `scripts/windows_acceptance/` 下已有 helper：

- `artifact_resolution`：候选与 installer hash 一致。
- `clean_install`：安装完成后再标 pass，校验 launcher、API、runtime 和 Web 布局。
- `first_launch`：首次与第二次快捷方式启动均健康，候选身份一致。
- `legacy_project`：复制旧项目并验证只读打开/迁移边界。
- `full_preflight`：使用显式 PPT 副本完成四门预检。
- `play_from_start`：从 0 播放到 ended，记录 stall 和资源错误。
- `final_export`：验证状态机、MP4 和制作包。
- `interruption_recovery`：对受管进程执行有限故障注入。
- `uninstall_reinstall`：实际完成卸载、同候选重装和项目重发现。
- `version_rollback`：使用显式 previous candidate，不搜索最新旧包。
- `process_cleanup` 与 `workspace_retention`：验证进程所有权和数据保留。

### 5.4 候选 feature policy

最终目标策略：

```json
{
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

约束：

- 三个 V2 开关必须成组开启或成组关闭。
- 旧项目不自动迁移，必须显式选择 V2。
- V1 回退不删除 EffectPlan、人工锁和用户设置。
- UI 显示生成代、策略 ID、降级原因和回退入口。
- P05 只验证 P02 已冻结的策略，不在验收后原地改策略。

## 6. 证据与目录模型

```text
test-results/personal-use/<candidate-id>/
├─ candidate/
│  ├─ candidate-identity.json
│  ├─ release-artifacts.json
│  ├─ runtime-manifest.json
│  └─ feature-policy.json
├─ gates/
│  ├─ source-candidate.json
│  ├─ local-ci.json
│  ├─ remote-ci.json
│  └─ final-candidate-built.json
├─ runs/
│  ├─ windows/<run-id>/
│  ├─ real-ppt/<run-id>/
│  ├─ effects/<run-id>/
│  ├─ recovery/<run-id>/
│  └─ quality/<run-id>/
├─ reviews/
│  ├─ effects-review.json
│  └─ final-av-review.json
├─ defects/
├─ final-evidence-manifest.json
└─ personal-use-signoff.json
```

每个阶段报告至少包含：

- `schema_version`、`stage_id`、`run_id`、`candidate_id`、`source_commit`。
- `status`、开始/结束时间、attempt 和 reason codes。
- 输入、配置、runtime、feature policy 和输出 hash。
- evidence refs、缺陷、process registry 和下一 Gate。

大文件可保留在 Git 外，但索引必须记录可解析路径、大小、SHA-256、保留策略和候选身份。

## 7. 项目级完成标准

### P01 Effects V2 工程补齐

- 动态聚合器、schema、fixtures 和测试完整。
- Windows Effects runner 能从安装版执行三个动态阶段。
- feature policy 非法组合失败关闭。
- V1 fallback 不丢 V2 数据。
- 全部定向测试通过，工作树形成可审查 commit。

### P02 重新冻结源码、CI 与候选

- 从 clean commit 生成新 candidate ID。
- Python、Web、Remotion、E2E、contract、release 和 security 本地门禁通过。
- 当前 commit 的远端 required CI 通过；未推送或不可访问时只能 `BLOCKED_EXTERNAL_CI`。
- 生成新安装包、runtime manifest、feature policy 和 release-artifacts manifest。
- 独立 verifier 与四门 preflight 通过。

### P03 Windows 安装与启动

- 全新隔离安装成功，安装后布局完整。
- 首次和第二次启动健康，无黑窗和残留受管进程。
- launcher/API/Web 显示同一 candidate ID。
- workspace/state/logs 与安装目录分离。

### P04 真实 PPT 完整转视频

- 小型、标准、复杂三类 PPT 副本完成 UI 全链。
- 页面、字体、素材、旁白、本地音频、字幕和 fresh preflight 正确。
- 从 0 播放到 ended，最终渲染和制作包成功。
- 最终 MP4 与制作包通过身份和媒体基础校验。
- 原始 PPT hash 前后不变。

### P05 Effects V2 动态专项

- 30/30 动态预览和 30/30 最终片段成功。
- L0-L3、强度、锁定、批量、字幕避让、Presenter/Overlay、seek 和页边界覆盖。
- preview/render 的 plan、graph、template、runtime 身份一致。
- V1 fallback 同项目副本通过。
- 人工动态抽检无 P0/P1。

### P06 中断恢复、重装与回滚

- API、Worker、Node/Remotion、FFmpeg 中断和文件系统故障覆盖。
- attempt/checkpoint/publication 不串线，不伪报 succeeded。
- 上一成功 MP4、制作包和 `latest` 始终安全。
- 同候选重装后项目和任务可恢复；previous candidate 回滚可用。

### P07 媒体质量与人工视听

- ffprobe、decode-to-null、黑帧、冻帧、静音、爆音、响度、同步、字幕和丢帧检查通过。
- 自动质量报告绑定最终 MP4 SHA-256。
- 用户或指定 reviewer 完整播放并具名决定。
- 自动化不代填 `accepted_by`。

### P08 最终总审计与交付

- 所有报告显式列出，不扫描最新。
- candidate/source/installer/runtime/policy/project/MP4/review 身份完全一致。
- P0/P1 为零；P2 具备 owner、规避和具名接受。
- 生成证据清单、签署、七步说明、Effects 使用/回退说明、恢复/重装说明和已知限制。
- 第二轮未完成项审计为零。
- G04 未完成时只允许功能就绪，不允许完整个人使用放行。

## 8. 缺陷与重跑矩阵

| 变化或缺陷                                               | 最早返回项目                 |
| -------------------------------------------------------- | ---------------------------- |
| Effects planner/template/interpreter/flags               | P01                          |
| Python/Node 依赖、schema、migration、API contract        | P02                          |
| build script、installer、runtime、feature policy         | P02                          |
| launcher、安装布局、启动协议                             | P03；修源码后回 P02          |
| PPT import、preflight、timeline、audio、subtitle、export | P04；修源码后回 P02          |
| 动态预览/导出漂移、字幕碰撞、错误降级                    | P05；修源码后回 P01/P02      |
| job/checkpoint/cache/publication/rollback                | P06；修源码后回 P02          |
| 媒体质量、最终 MP4、导出规格                             | P07；修源码后回 P04/P05      |
| 证据 schema、聚合器或身份错误                            | P08；语义变化则回 P02        |
| DP45 runner/config 或长稳缺陷                            | Deferred G04；修源码则回 P02 |

P0/P1 必须修复并重跑；P2 必须记录 owner、影响、规避、`accepted_by` 和 `accepted_at`；P3 进入已知限制。

## 9. 安全与授权边界

- 所有实机验收使用新的 InstallRoot、WorkspaceRoot、DB、TEMP、cache、output、logs 和 ports。
- 只终止当前 run 注册且 PID 创建时间匹配的进程。
- 不访问正式 workspace DB；生产数据库路径必须作为禁止目标参与测试。
- 原始 PPT 只读，使用副本并在前后验证 hash。
- 不自动推送分支、创建 PR、使用付费 Provider、真实凭据或外部云资源；这些动作需要对应授权。
- 失败现场和证据按候选保留，不执行 broad clean/reset/delete。

## 10. 预计工作量

| 项目                      |                           预计 |
| ------------------------- | -----------------------------: |
| P01 Effects V2 工程补齐   |                   1-2 个工作日 |
| P02 新候选、本地门禁与 CI | 1-2 个工作日，不含外部 CI 等待 |
| P03 Windows 安装与启动    |                 0.5-1 个工作日 |
| P04 真实 PPT 全链         |                   1-2 个工作日 |
| P05 动态 Effects 矩阵     |                   1-2 个工作日 |
| P06 恢复、重装与回滚      |                   1-2 个工作日 |
| P07 质量与人工视听        | 0.5-1 个工作日，加人工审片时间 |
| P08 总审计与交付          |                 0.5-1 个工作日 |
| 合计                      |                6.5-13 个工作日 |

缺陷修复和候选重建会增加时间；估算不能替代 Gate。

## 11. 完成定义

八项目功能闭环完成时，用户能够从一个明确的 Windows 安装包启动程序，导入真实 PPT，使用本地音频和字幕，启用或回退 Effects V2，完成预检、播放、最终导出和制作包；程序在刷新、中断、重启、卸载重装和版本回滚后保持项目与上一成功结果安全；最终 MP4 通过自动质量检查和具名人工视听。

状态规则：

- P01-P08 全部通过、G04 延期：`PERSONAL_USE_FUNCTIONAL_READY=PASS`，`PERSONAL_USE_READY=BLOCKED_DEFERRED_G04`。
- P01-P08 和同候选 G04 全部通过：允许写入 `PERSONAL_USE_READY=PASS`。
- 任一必需身份、报告、hash 或人工决定缺失：保持 blocked。
