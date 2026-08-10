# Effect Engine V2 Mainline Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 EffectPlan V2 作为单一、可持久化、可编辑、可预检和可缓存的契约，完整接入 PPT Video Workbench 的 API、Web、Remotion、分段渲染与导出主链，同时保持旧项目与已有音频/字幕/页面数据不变。

**Architecture:** Python `workbench.effects` 是计划与校验的唯一权威；显式 Effects API 管理计划；`ProjectVideoProps V2` 把已验证计划下发给 Remotion；`PageScene` 按局部帧解释模板；页面计划哈希参与缓存与导出。GET 不写项目，锁定计划不被自动覆盖，异步渲染任务化留给后续项目。

**Tech Stack:** Python 3.11、FastAPI、Pydantic、pytest、React、TypeScript、Vitest、Remotion、FFmpeg、npm workspace、Windows 打包工具链。

## Global Constraints

- 先读仓库根目录及目标子目录中的 `AGENTS.md`，以最深层规则为准。
- 当前副本的 `.git` 指向失效的外部 worktree，禁止 `git init`、修复 gitdir、`git reset --hard` 或 `git clean`。只有在有效 Git worktree 中才执行本计划列出的提交命令；否则保留工作树和验证证据。
- 现有修改默认属于用户。每项开始前运行只读状态检查，避免覆盖无关改动。
- 禁止直接改动真实 Workbench 用户项目。自动测试与写入验收必须使用临时目录或专用夹具。
- 不重建或覆盖已有配音、字幕、旁白、页面正文和页面预览图。
- 对项目数据的所有写入必须走现有原子保存与备份机制；GET 接口不得写盘。
- 不增加大模型、外部地图、在线素材或付费 API。
- 不降低门禁、不删除失败测试、不把真实错误改成忽略。
- 每个任务遵循 red → green → refactor；先确认测试按预期失败，再做最小实现。
- 每项完成后运行该项测试；所有任务完成后再运行全量相关门禁与 Windows 验收。

---

## Task 1: 建立唯一的 EffectPlan V2 Python 契约

**Files:**

- Create: `apps/api/src/workbench/effects/__init__.py`
- Create: `apps/api/src/workbench/effects/schema.py`
- Create: `apps/api/src/workbench/effects/payloads.py`
- Create: `apps/api/src/workbench/effects/catalog.py`
- Create: `apps/api/src/workbench/effects/errors.py`
- Create: `contracts/effect-plan-v2.schema.json`
- Modify: `apps/api/pyproject.toml`
- Modify: `tests/contract/test_effect_plan_v2.py`
- Modify: `tests/unit/effects/test_validator.py`
- Modify: `tests/unit/effects/test_background_policy.py`
- Test: `tests/contract/test_effect_plan_v2.py`
- Test: `tests/unit/effects/test_effect_payloads.py`
- Test: `tests/unit/effects/test_catalog.py`

**Produces:** 唯一权威 `workbench.effects` 包、13 个模板的判别 payload、稳定 JSON Schema 快照。  
**Consumes:** 现有两套 prototype schema 与模板目录测试，保留已验证的枚举和约束。

### Step 1: 写失败的契约测试

新增测试，明确模板不能再从 `effects[0].type` 推导：

```python
def test_effect_plan_requires_explicit_template_and_matching_payload() -> None:
    plan = EffectPlanV2.model_validate(
        {
            "schema_version": "2.0",
            "template": "ProgressiveReveal",
            "template_payload": {
                "kind": "progressive_reveal",
                "items": ["A", "B"],
            },
            **minimal_visual_specs(),
        }
    )
    assert plan.template == "ProgressiveReveal"

    with pytest.raises(ValidationError):
        EffectPlanV2.model_validate(
            {
                **plan.model_dump(),
                "template": "StatCounter",
            }
        )
```

为 12 个用户模板和 `SafeSlide` 参数化正例，并覆盖数组上下限、字符串长度、有限数值、未知字段和未知模板反例。

### Step 2: 运行测试并确认失败原因

Run:

```powershell
python -m pytest tests/contract/test_effect_plan_v2.py tests/unit/effects/test_effect_payloads.py tests/unit/effects/test_catalog.py -q
```

Expected: FAIL，原因是 `workbench.effects`、显式 `template` 或对应 payload 尚不存在；不得接受因导入到旧根目录 `effects` 而产生的伪通过。

### Step 3: 实现最小权威模型

核心接口：

```python
TemplateName = Literal[
    "ProgressiveReveal", "ChapterCurtain", "StatCounter",
    "ChartNarration", "CompareMode", "FocusSpotlight",
    "CardStack", "GaugeAndRatio", "PathBuilder", "TagMatrix",
    "RiskAlert", "MapHighlight", "SafeSlide",
]

TemplatePayload = Annotated[
    ProgressiveRevealPayload
    | ChapterCurtainPayload
    | StatCounterPayload
    | ChartNarrationPayload
    | CompareModePayload
    | FocusSpotlightPayload
    | CardStackPayload
    | GaugeAndRatioPayload
    | PathBuilderPayload
    | TagMatrixPayload
    | RiskAlertPayload
    | MapHighlightPayload
    | SafeSlidePayload,
    Field(discriminator="kind"),
]
```

`EffectPlanV2` 使用 model validator 验证 `template ↔ payload.kind` 映射。模型配置使用 `extra="forbid"`，数值必须有限。

### Step 4: 建立完整目录与 Schema 快照

`catalog.py` 输出固定顺序的 12 个用户模板；`SafeSlide` 标记 `internal=True`；`NarrativePreview` 不进入目录。通过 Pydantic 生成 `contracts/effect-plan-v2.schema.json`，并写快照测试证明重复生成字节一致。

### Step 5: 迁移测试导入并消除生产包歧义

把现有 `tests/**/effects` 导入改为 `workbench.effects`。调整 `apps/api/pyproject.toml`，确保 wheel 只发布 `workbench`。运行：

```powershell
python -m pytest tests/contract/test_effect_plan_v2.py tests/unit/effects -q
python -m build apps/api
```

Expected: PASS；构建产物只含 `workbench/effects`。确认所有引用迁移后再删除重复 prototype 包；若当前 Git 元数据失效，先记录删除清单并延后到有效 worktree，避免不可追踪删除。

### Step 6: Commit（仅有效 Git worktree）

```powershell
git add apps/api/src/workbench/effects apps/api/pyproject.toml contracts/effect-plan-v2.schema.json tests/contract tests/unit/effects
git commit -m "feat(effects): define canonical effect plan v2 contract"
```

---

## Task 2: 让项目清单向后兼容地持久化特效计划

**Files:**

- Create: `apps/api/src/workbench/domain/effects.py`
- Modify: `apps/api/src/workbench/domain/models.py`
- Modify: `apps/api/src/workbench/services/project_service.py`
- Test: `tests/unit/domain/test_effect_plan_record.py`
- Test: `tests/unit/domain/test_manifest_effect_compatibility.py`
- Test: `tests/integration/test_effect_manifest_persistence.py`

**Produces:** `EffectPlanRecord`、`EffectProjectPolicy`、旧 manifest 默认兼容、原子保存和备份证据。  
**Consumes:** Task 1 的 `EffectPlanV2` 与现有 `ManifestStore`。

### Step 1: 写旧项目兼容和 revision 失败测试

```python
def test_v1_manifest_without_effect_fields_loads_without_rewrite(tmp_path: Path) -> None:
    project_file = copy_fixture("project-v1.json", tmp_path)
    before = project_file.read_bytes()
    manifest = ProjectService(tmp_path).load(PROJECT_ID)
    assert manifest.effect_policy.aspect_ratio == "16:9"
    assert all(page.effect_plan is None for page in manifest.pages)
    assert project_file.read_bytes() == before

def test_effect_record_rejects_client_hash_mismatch() -> None:
    record = build_effect_record(plan=valid_plan(), plan_hash="bad")
    with pytest.raises(EffectHashMismatch):
        validate_record_hash(record)
```

另测：schema_version 仍为 1、默认策略、锁定字段、revision 下限、datetime 序列化、保存生成 `.bak`。

### Step 2: 确认测试按预期失败

```powershell
python -m pytest tests/unit/domain/test_effect_plan_record.py tests/unit/domain/test_manifest_effect_compatibility.py tests/integration/test_effect_manifest_persistence.py -q
```

Expected: FAIL，缺少 effect 字段与模型。

### Step 3: 实现领域记录与默认策略

```python
class EffectPlanRecord(BaseModel):
    revision: int = Field(ge=1)
    plan: EffectPlanV2
    plan_hash: str
    input_fingerprint: str
    source: Literal["automatic", "manual", "migrated", "fallback"]
    status: Literal["ready", "fallback", "stale", "invalid"]
    locked: bool = False
    decision_reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    validation_codes: list[str] = Field(default_factory=list)
    updated_at: datetime
```

在 `PageRecord` 增加 `effect_plan: EffectPlanRecord | None = None`，在 `ProjectManifest` 增加 default factory policy；不提升 manifest schema 版本。

### Step 4: 保持迁移和保存无损

更新迁移字段白名单，使未知旧字段处理规则保持原样。写集成测试证明：

- load 不改文件；
- 显式保存才增加 effect 字段；
- 已有 narration/audio/subtitles/render/preview JSON 前后相等；
- 原子替换失败时旧文件仍可读；
- 成功写前产生完整备份。

### Step 5: 运行门禁

```powershell
python -m pytest tests/unit/domain tests/integration/test_effect_manifest_persistence.py -q
python -m pytest tests/unit/services/test_project_service.py -q
```

Expected: PASS。

### Step 6: Commit（仅有效 Git worktree）

```powershell
git add apps/api/src/workbench/domain apps/api/src/workbench/services/project_service.py tests/unit/domain tests/integration/test_effect_manifest_persistence.py
git commit -m "feat(project): persist effect plans without rewriting legacy data"
```

---

## Task 3: 实现确定性规划器、fingerprint 与 SafeSlide 回退

**Files:**

- Create: `apps/api/src/workbench/effects/fingerprint.py`
- Create: `apps/api/src/workbench/effects/planner.py`
- Create: `apps/api/src/workbench/effects/validator.py`
- Modify: `apps/api/src/workbench/effects/catalog.py`
- Test: `tests/unit/effects/test_fingerprint.py`
- Test: `tests/unit/effects/test_planner.py`
- Test: `tests/unit/effects/test_validator.py`
- Test: `tests/integration/test_effect_batch_planning.py`

**Produces:** 相同输入产生相同 hash；锁定、复用、重算和 fallback 的稳定语义。  
**Consumes:** 页面提取、字幕 cue、timeline、策略与 Task 1/2 模型。

### Step 1: 写确定性和锁定测试

```python
def test_planner_is_deterministic() -> None:
    first = planner.plan(build_input())
    second = planner.plan(build_input())
    assert first.plan == second.plan
    assert first.plan_hash == second.plan_hash
    assert first.input_fingerprint == second.input_fingerprint

def test_locked_changed_input_becomes_stale_without_overwrite() -> None:
    existing = ready_record(locked=True)
    result = planner.reconcile(changed_input(), existing)
    assert result.record.plan_hash == existing.plan_hash
    assert result.record.status == "stale"
```

另测固定 tie-break、同 fingerprint 不增 revision、force 不覆盖锁定、校验失败生成带错误码的 `SafeSlide`。

### Step 2: 运行失败测试

```powershell
python -m pytest tests/unit/effects/test_fingerprint.py tests/unit/effects/test_planner.py tests/unit/effects/test_validator.py tests/integration/test_effect_batch_planning.py -q
```

Expected: FAIL，缺少规划服务。

### Step 3: 实现规范化与哈希

```python
def canonical_json(value: BaseModel | Mapping[str, object]) -> bytes: ...

def calculate_plan_hash(plan: EffectPlanV2) -> str:
    return hashlib.sha256(canonical_json(plan)).hexdigest()

def calculate_input_fingerprint(value: EffectPlanningInput) -> str: ...
```

规范化排序映射键，保留数组语义顺序，统一 UUID/datetime 表示，拒绝 NaN/Infinity；不包含时间戳、绝对路径或临时 URL。

### Step 4: 实现 planner 和 validator

公开接口：

```python
class EffectPlanner:
    def reconcile(
        self,
        planning_input: EffectPlanningInput,
        existing: EffectPlanRecord | None,
        *,
        force: bool = False,
    ) -> EffectPlanningResult: ...
```

模板评分必须由显式规则表和固定目录顺序决定。payload 构造失败时生成 `SafeSlide`，`source="fallback"`、`status="fallback"`，并保留原因。

### Step 5: 批量与性能测试

在固定 40 页夹具上验证两次规划 hash 完全一致、锁定页跳过、无输入时仍生成 SafeSlide。性能测试只记录并断言宽松门槛：40 页本地规划 < 2s。

```powershell
python -m pytest tests/unit/effects tests/integration/test_effect_batch_planning.py -q
```

Expected: PASS。

### Step 6: Commit（仅有效 Git worktree）

```powershell
git add apps/api/src/workbench/effects tests/unit/effects tests/integration/test_effect_batch_planning.py
git commit -m "feat(effects): add deterministic page effect planner"
```

---

## Task 4: 增加 Effects Service、API 与并发编辑

**Files:**

- Create: `apps/api/src/workbench/effects/service.py`
- Create: `apps/api/src/workbench/api/effects.py`
- Modify: `apps/api/src/workbench/main.py`
- Modify: `apps/api/src/workbench/cache/dependency_graph.py`
- Test: `tests/unit/effects/test_effect_service.py`
- Test: `tests/integration/test_effects_routes.py`
- Test: `tests/integration/test_effect_concurrency.py`
- Test: `tests/integration/test_effect_data_preservation.py`

**Produces:** 只读 catalog/workspace API 与显式 generate/edit/unlock API。  
**Consumes:** Task 2 持久化和 Task 3 planner。

### Step 1: 写路由行为测试

```python
def test_get_effect_workspace_has_no_write_side_effect(client, project_path) -> None:
    before = snapshot_tree(project_path)
    response = client.get(f"/api/projects/{PROJECT_ID}/effects")
    assert response.status_code == 200
    assert snapshot_tree(project_path) == before

def test_stale_revision_returns_409(client) -> None:
    response = client.put(
        f"/api/projects/{PROJECT_ID}/effects/pages/{PAGE_ID}",
        json={**valid_edit(), "expected_revision": 2},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "effect_revision_conflict"
```

覆盖 catalog、批量生成、force 锁保护、typed payload 422、unlock revision、自定义错误码与数据保持。

### Step 2: 运行失败测试

```powershell
python -m pytest tests/unit/effects/test_effect_service.py tests/integration/test_effects_routes.py tests/integration/test_effect_concurrency.py tests/integration/test_effect_data_preservation.py -q
```

Expected: FAIL，路由/服务不存在。

### Step 3: 实现 EffectService

```python
class EffectService:
    def get_workspace(self, project_id: UUID) -> EffectWorkspaceResponse: ...
    def generate(self, project_id: UUID, request: GenerateEffectsRequest) -> GenerateEffectsResponse: ...
    def update_page(self, project_id: UUID, page_id: UUID, request: UpdateEffectRequest) -> EffectMutationResponse: ...
    def unlock_page(self, project_id: UUID, page_id: UUID, expected_revision: int) -> EffectMutationResponse: ...
```

读取接口只计算 current fingerprint 和 validation view，不保存。所有 mutation 在同一个项目级临界区内重新读取、检查 revision、写备份、原子保存并产生失效计划。

### Step 4: 实现 FastAPI 路由和稳定错误映射

挂载以下路径：

```text
GET  /api/projects/{project_id}/effects/catalog
GET  /api/projects/{project_id}/effects
POST /api/projects/{project_id}/effects/generate
PUT  /api/projects/{project_id}/effects/pages/{page_id}
POST /api/projects/{project_id}/effects/pages/{page_id}/unlock
```

客户端请求模型不得含 `plan_hash`、`input_fingerprint`、`updated_at` 或任意本地路径。

### Step 5: 验证审计与数据保护

测试每次 mutation 的审计只包含 ID、revision、hash、operation、codes；不含全文 payload 或凭证。比较 mutation 前后 narration、audio、subtitles、page content 和 preview refs 完全一致。

```powershell
python -m pytest tests/integration/test_effects_routes.py tests/integration/test_effect_concurrency.py tests/integration/test_effect_data_preservation.py -q
```

Expected: PASS。

### Step 6: Commit（仅有效 Git worktree）

```powershell
git add apps/api/src/workbench/effects/service.py apps/api/src/workbench/api/effects.py apps/api/src/workbench/main.py apps/api/src/workbench/cache/dependency_graph.py tests/integration/test_effects_routes.py tests/integration/test_effect_concurrency.py tests/integration/test_effect_data_preservation.py
git commit -m "feat(api): expose effect planning and editing endpoints"
```

---

## Task 5: 升级 Props V2、画幅与视频预检

**Files:**

- Modify: `apps/api/src/workbench/video/models.py`
- Modify: `apps/api/src/workbench/video/props_service.py`
- Modify: `apps/api/src/workbench/video/preview_service.py`
- Modify: `apps/api/src/workbench/preflight/checks/video.py`
- Modify: `apps/api/src/workbench/api/video.py`
- Test: `tests/unit/video/test_props_v2.py`
- Test: `tests/unit/video/test_effect_preflight.py`
- Test: `tests/integration/test_video_props_effects.py`
- Test: `tests/contract/test_video_props_v2.py`

**Produces:** 只读 `ProjectVideoProps V2`，包含每页计划、revision、hash 和真实画幅。  
**Consumes:** 已持久化 `EffectPlanRecord`；缺失计划由 Workflow 显式 generate，不在 GET 中写入。

### Step 1: 写 Props 与预检失败测试

```python
def test_props_v2_contains_exact_persisted_effect_hash(project_with_effects) -> None:
    props = VideoPropsService().build(project_with_effects)
    assert props.schema_version == 2
    assert props.template_version == "effect-engine-v2"
    assert props.pages[0].effect_plan_hash == project_with_effects.pages[0].effect_plan.plan_hash

@pytest.mark.parametrize(
    ("aspect", "width", "height"),
    [("16:9", 1920, 1080), ("9:16", 1080, 1920)],
)
def test_props_dimensions_follow_effect_policy(aspect, width, height): ...
```

预检参数化缺失、stale、invalid、未知模板、payload 错误、timing 错误和 presenter collision。

### Step 2: 运行失败测试

```powershell
python -m pytest tests/unit/video/test_props_v2.py tests/unit/video/test_effect_preflight.py tests/integration/test_video_props_effects.py tests/contract/test_video_props_v2.py -q
```

Expected: FAIL，模型仍是 Props V1。

### Step 3: 实现 Props V2 投影

```python
class VideoPagePropsV2(VideoPageProps):
    effect_plan: EffectPlanV2
    effect_plan_revision: int = Field(ge=1)
    effect_plan_hash: str

class ProjectVideoProps(BaseModel):
    schema_version: Literal[2] = 2
    template_version: Literal["effect-engine-v2"] = "effect-engine-v2"
    catalog_version: str
    width: Literal[1920, 1080]
    height: Literal[1080, 1920]
```

构建前再次计算 hash，拒绝记录污染。不得在 props GET/preview GET 中生成或保存计划。

### Step 4: 扩展预检码

实现：`effect_plan_missing`、`effect_plan_stale`、`effect_plan_invalid`、`effect_template_unsupported`、`effect_payload_invalid`、`effect_timing_invalid`、`effect_presenter_collision`。未锁定显式 fallback 作为 required warning；锁定 stale/invalid 阻断。

### Step 5: 运行相关回归

```powershell
python -m pytest tests/unit/video tests/integration/test_video_props_effects.py tests/contract -q
```

Expected: PASS；已有预览路径、音频时间线和字幕预检测试继续通过。

### Step 6: Commit（仅有效 Git worktree）

```powershell
git add apps/api/src/workbench/video apps/api/src/workbench/preflight/checks/video.py apps/api/src/workbench/api/video.py tests/unit/video tests/integration/test_video_props_effects.py tests/contract
git commit -m "feat(video): emit and preflight effect-aware props v2"
```

---

## Task 6: 把特效纳入页面缓存与依赖失效

**Files:**

- Modify: `apps/api/src/workbench/video/render_service.py`
- Modify: `apps/api/src/workbench/cache/dependency_graph.py`
- Modify: `apps/api/src/workbench/cache/key.py`
- Test: `tests/unit/video/test_effect_cache_key.py`
- Test: `tests/unit/cache/test_effect_invalidation.py`
- Test: `tests/integration/test_partial_effect_rerender.py`

**Produces:** 特效变化只重渲染必要页面；相同 hash 不造成缓存抖动。  
**Consumes:** Props V2、目录版本、画幅、presenter 与现有原子页面缓存。

### Step 1: 写缓存命中/失效测试

```python
def test_effect_hash_changes_only_one_page_cache_key() -> None:
    before = cache_keys(project_props())
    after = cache_keys(project_props(page_2_effect_hash="changed"))
    assert before[0] == after[0]
    assert before[1] != after[1]

def test_equal_regenerated_hash_does_not_invalidate() -> None:
    plan = dependency_graph.effect_plan_regenerated(PAGE_ID, changed=False)
    assert plan.page_segments == set()
    assert not plan.final_video
```

### Step 2: 运行失败测试

```powershell
python -m pytest tests/unit/video/test_effect_cache_key.py tests/unit/cache/test_effect_invalidation.py tests/integration/test_partial_effect_rerender.py -q
```

Expected: FAIL，cache key/graph 尚不识别特效。

### Step 3: 扩展 cache key

把以下字段放入规范化 key：`effect_plan_hash`、`catalog_version`、`width`、`height`、presenter asset/anchor/enabled，并保留现有 page props、subtitle placement、reduced motion、preview SHA。

### Step 4: 新增依赖事件

```python
def effect_plan_changed(page_id: UUID) -> InvalidationPlan: ...
def effect_plan_regenerated(changes: Mapping[UUID, bool]) -> InvalidationPlan: ...
def effect_policy_changed() -> InvalidationPlan: ...
def effect_catalog_upgraded(affected_page_ids: set[UUID]) -> InvalidationPlan: ...
```

策略或画幅变化标记所有自动计划 stale；锁定计划也 stale，但不覆盖其内容。

### Step 5: 验证部分重渲染与原子恢复

模拟 3 页渲染：修改第 2 页计划后仅第 2 页调用 Remotion；第 2 页失败时第 1/3 页缓存仍有效，不写最终成品。

```powershell
python -m pytest tests/unit/video/test_effect_cache_key.py tests/unit/cache/test_effect_invalidation.py tests/integration/test_partial_effect_rerender.py -q
```

Expected: PASS。

### Step 6: Commit（仅有效 Git worktree）

```powershell
git add apps/api/src/workbench/video apps/api/src/workbench/cache tests/unit/video tests/unit/cache tests/integration/test_partial_effect_rerender.py
git commit -m "feat(render): invalidate page cache by effect plan hash"
```

---

## Task 7: 建立 TypeScript 契约解析器与完整模板 registry

**Files:**

- Create: `remotion/src/effects/contract.ts`
- Create: `remotion/src/effects/catalog.ts`
- Modify: `remotion/src/effects/interpreter.tsx`
- Modify: `remotion/src/effects/templates/ProgressiveReveal.tsx`
- Modify: `remotion/src/effects/templates/ChapterCurtain.tsx`
- Modify: `remotion/src/effects/templates/StatCounter.tsx`
- Modify: `remotion/src/effects/templates/ChartNarration.tsx`
- Modify: `remotion/src/effects/templates/CompareMode.tsx`
- Modify: `remotion/src/effects/templates/FocusSpotlight.tsx`
- Modify: `remotion/src/effects/templates/CardStack.tsx`
- Modify: `remotion/src/effects/templates/GaugeAndRatio.tsx`
- Modify: `remotion/src/effects/templates/PathBuilder.tsx`
- Modify: `remotion/src/effects/templates/TagMatrix.tsx`
- Modify: `remotion/src/effects/templates/RiskAlert.tsx`
- Modify: `remotion/src/effects/templates/MapHighlight.tsx`
- Modify: `remotion/src/effects/templates/SafeSlide.tsx`
- Test: `remotion/src/effects/__tests__/contract.test.ts`
- Test: `remotion/src/effects/__tests__/catalog.test.ts`
- Test: `remotion/src/effects/__tests__/interpreter.test.tsx`
- Test: `remotion/src/effects/__tests__/schema-parity.test.ts`

**Produces:** TS 对 Props 中 EffectPlan 的严格解析与 13 模板完整 registry。  
**Consumes:** `contracts/effect-plan-v2.schema.json` 与现有模板组件。

### Step 1: 写 parity 和 registry 失败测试

```ts
it('registers all persisted template names exactly once', () => {
  expect(Object.keys(effectTemplateRegistry).sort()).toEqual(
    [...persistedTemplateNames].sort(),
  );
});

it('rejects a payload that does not match the template', () => {
  expect(() => parseEffectPlan({
    ...validPlan,
    template: 'StatCounter',
    template_payload: {kind: 'progressive_reveal', items: ['A']},
  })).toThrow(/effect_payload_invalid/);
});
```

### Step 2: 运行失败测试

```powershell
pnpm --filter @workbench/remotion exec vitest run src/effects/__tests__/contract.test.ts src/effects/__tests__/catalog.test.ts src/effects/__tests__/interpreter.test.tsx src/effects/__tests__/schema-parity.test.ts
```

Expected: FAIL，旧 interpreter 仍从 `effects[0].type` 推导且 registry 不完整。

### Step 3: 实现严格 TS 类型和解析

```ts
export type EffectTemplateProps<TPlan extends EffectPlanV2 = EffectPlanV2> = {
  plan: TPlan;
  page: VideoPagePropsV2;
  localFrame: number;
  fps: number;
  width: number;
  height: number;
  reducedMotion: boolean;
};

export function parseEffectPlan(input: unknown): EffectPlanV2;
```

解析器拒绝未知字段、未知模板、payload kind 不匹配、NaN/Infinity、越界数组与数值。schema parity 测试比较模板名、required 字段、枚举和边界，不在运行时加载 Python。

### Step 4: 统一 13 个模板签名

登记 12 用户模板 + `SafeSlide`。迁移现有组件到 `EffectTemplateProps`；补齐缺失模板最小可读实现。`NarrativePreview` 不登记。

### Step 5: 移除错误推导并验证类型

`interpreter.tsx` 只读取 `plan.template`，先解析再从 registry 取组件；未知模板抛出带页 ID 的 `effect_template_unsupported`。

```powershell
pnpm --filter @workbench/remotion exec vitest run src/effects/__tests__
pnpm --filter @workbench/remotion typecheck
```

Expected: PASS。

### Step 6: Commit（仅有效 Git worktree）

```powershell
git add remotion/src/effects contracts/effect-plan-v2.schema.json
git commit -m "feat(remotion): validate and register effect plan v2 templates"
```

---

## Task 8: 用 PageScene 接通 ProjectVideo 主渲染链

**Files:**

- Create: `remotion/src/video/PageScene.tsx`
- Modify: `remotion/src/effects/backgrounds/SemanticBackground.tsx`
- Create: `remotion/src/effects/PresenterLayer.tsx`
- Modify: `remotion/src/video/ProjectVideo.tsx`
- Create: `remotion/src/video/SubtitleLayer.tsx`
- Modify: `remotion/src/Root.tsx`
- Modify: `remotion/src/effects/templates/ProgressiveReveal.tsx`
- Modify: `remotion/src/effects/templates/ChapterCurtain.tsx`
- Modify: `remotion/src/effects/templates/StatCounter.tsx`
- Modify: `remotion/src/effects/templates/ChartNarration.tsx`
- Modify: `remotion/src/effects/templates/CompareMode.tsx`
- Modify: `remotion/src/effects/templates/FocusSpotlight.tsx`
- Modify: `remotion/src/effects/templates/CardStack.tsx`
- Modify: `remotion/src/effects/templates/GaugeAndRatio.tsx`
- Modify: `remotion/src/effects/templates/PathBuilder.tsx`
- Modify: `remotion/src/effects/templates/TagMatrix.tsx`
- Modify: `remotion/src/effects/templates/RiskAlert.tsx`
- Modify: `remotion/src/effects/templates/MapHighlight.tsx`
- Modify: `remotion/src/effects/templates/SafeSlide.tsx`
- Test: `remotion/src/video/__tests__/PageScene.test.tsx`
- Test: `remotion/src/video/__tests__/ProjectVideo.effects.test.tsx`
- Test: `remotion/src/effects/__tests__/template-frames.test.tsx`
- Test: `remotion/src/effects/__tests__/aspect-ratios.test.tsx`

**Produces:** 每页按局部帧渲染背景、原图、模板、讲解员和顶层字幕。  
**Consumes:** Task 5 Props V2 与 Task 7 interpreter。

### Step 1: 写层级、局部帧和 reduced-motion 测试

```tsx
it('renders subtitle above presenter and effect layers', () => {
  const view = renderPageScene({frame: 45});
  expect(view.layerOrder()).toEqual([
    'semantic-background',
    'source-page-image',
    'effect-template',
    'presenter',
    'subtitles',
  ]);
});

it('passes page-local frame to the template', () => {
  renderProjectAtFrame(secondPage.startFrame + 12);
  expect(templateSpy).toHaveBeenCalledWith(expect.objectContaining({localFrame: 12}));
});
```

另测每页 `premountFor={fps}`、字幕 placement、无字幕、长文本、16:9/9:16 安全区、reduced motion 保留语义顺序。

### Step 2: 运行失败测试

```powershell
pnpm --filter @workbench/remotion exec vitest run src/video/__tests__/PageScene.test.tsx src/video/__tests__/ProjectVideo.effects.test.tsx src/effects/__tests__/template-frames.test.tsx src/effects/__tests__/aspect-ratios.test.tsx
```

Expected: FAIL，ProjectVideo 仍固定渲染 TechBoardTemplate。

### Step 3: 实现 PageScene

```tsx
export const PageScene: React.FC<PageSceneProps> = ({page, fps, width, height, reducedMotion}) => {
  const localFrame = useCurrentFrame();
  return (
    <AbsoluteFill data-layer="page-scene">
      <SemanticBackground {...{page, localFrame, fps, reducedMotion}} />
      <SourcePageImage page={page} />
      <EffectInterpreter plan={page.effectPlan} {...{page, localFrame, fps, width, height, reducedMotion}} />
      <PresenterLayer page={page} />
      <SubtitleLayer page={page} localFrame={localFrame} />
    </AbsoluteFill>
  );
};
```

字幕层最后渲染并拥有最高 z-index。安全区按 `min(width / 1920, height / 1080)` 缩放。

### Step 4: 重构 ProjectVideo 的页面序列

每页使用：

```tsx
<Sequence
  key={page.pageId}
  from={page.startFrame}
  durationInFrames={page.durationFrames}
  premountFor={fps}
>
  <PageScene page={page} {...compositionMetrics} />
</Sequence>
```

音频仍使用现有页面时间线。`cut|crossfade|mask` 仅做页内 entrance/exit，不缩短 duration、不跨页重叠。

### Step 5: 使所有模板逐帧且可 seek

移除 CSS animation/transition/Tailwind animation。统一使用 `interpolate`、clamp 与显式 easing。对每个模板采集 start/mid/end DOM 或图像快照；随机定位必须替换为确定性索引函数。

### Step 6: 运行 Remotion 门禁

```powershell
pnpm --filter @workbench/remotion exec vitest run
pnpm exec eslint remotion/src --max-warnings=0
pnpm exec prettier --check remotion/src
pnpm --filter @workbench/remotion typecheck
pnpm --filter @workbench/remotion build
```

Expected: PASS。

### Step 7: Commit（仅有效 Git worktree）

```powershell
git add remotion/src
git commit -m "feat(remotion): render effect plans through page scene"
```

---

## Task 9: 接入 Web 特效工作台与 Workflow

**Files:**

- Create: `apps/web/src/features/effects/api.ts`
- Create: `apps/web/src/features/effects/types.ts`
- Create: `apps/web/src/features/effects/EffectWorkspace.tsx`
- Create: `apps/web/src/features/effects/TemplatePicker.tsx`
- Create: `apps/web/src/features/effects/EffectPageEditor.tsx`
- Create: `apps/web/src/features/effects/EffectStatusBadge.tsx`
- Modify: `apps/web/src/features/video/PreviewWorkspace.tsx`
- Modify: `apps/web/src/features/workflow/WorkflowShell.tsx`
- Test: `apps/web/src/features/effects/EffectWorkspace.test.tsx`
- Test: `apps/web/src/features/effects/EffectPageEditor.test.tsx`
- Modify: `apps/web/src/features/workflow/WorkflowShell.test.tsx`

**Produces:** 真实 API 驱动的生成、编辑、锁定、冲突处理与视频预检前补齐流程。  
**Consumes:** Task 4 API 和现有 PreviewWorkspace 接口。

### Step 1: 写用户流程失败测试

```tsx
it('keeps edits local until Save is clicked', async () => {
  renderWorkspace();
  await user.selectOptions(screen.getByLabelText('模板'), 'StatCounter');
  expect(api.updatePage).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', {name: '保存'}));
  expect(api.updatePage).toHaveBeenCalledWith(expect.objectContaining({expectedRevision: 3}));
});

it('preserves the draft on a revision conflict', async () => {
  api.updatePage.mockRejectedValue(revisionConflict());
  await editAndSave();
  expect(screen.getByDisplayValue('本地修改')).toBeInTheDocument();
  expect(screen.getByText(/项目已在其他位置更新/)).toBeInTheDocument();
});
```

另测生成缺失页、重算未锁定页、lock/unlock、fallback/stale/invalid 状态、未保存离开提示、GET 不触发 mutation。

### Step 2: 运行失败测试

```powershell
pnpm --filter @workbench/web exec vitest run src/features/effects/EffectWorkspace.test.tsx src/features/effects/EffectPageEditor.test.tsx src/features/workflow/WorkflowShell.test.tsx
```

Expected: FAIL，特效工作台不存在。

### Step 3: 实现 typed API client 与状态模型

```ts
export interface EffectsApi {
  getCatalog(projectId: string): Promise<EffectCatalogResponse>;
  getWorkspace(projectId: string): Promise<EffectWorkspaceResponse>;
  generate(projectId: string, request: GenerateEffectsRequest): Promise<GenerateEffectsResponse>;
  updatePage(projectId: string, pageId: string, request: UpdateEffectRequest): Promise<EffectMutationResponse>;
  unlockPage(projectId: string, pageId: string, expectedRevision: number): Promise<EffectMutationResponse>;
}
```

网络模型与编辑 draft 分离，保存成功才替换服务端快照。

### Step 4: 实现结构化编辑器

根据 catalog schema 渲染受限字段组件，不提供任意 JSON textarea。显示 revision、短 hash、规划理由、validation codes 与 fallback 原因。锁定状态禁用自动重算但允许显式解锁。

### Step 5: 接入 Workflow

进入特效步骤时读 workspace。启动视频预检前：若存在 missing 且项目允许自动生成，显式 POST `generate` 后重新读取；锁定 stale/invalid 直接显示阻断，不自动解锁或 fallback。

### Step 6: 运行 Web 门禁

```powershell
pnpm --filter @workbench/web exec vitest run
pnpm exec eslint apps/web/src --max-warnings=0
pnpm exec prettier --check apps/web/src
pnpm --filter @workbench/web typecheck
pnpm --filter @workbench/web build
```

Expected: PASS。

### Step 7: Commit（仅有效 Git worktree）

```powershell
git add apps/web/src/features/effects apps/web/src/features/video/PreviewWorkspace.tsx apps/web/src/features/workflow/WorkflowShell.tsx apps/web/src/features/workflow/WorkflowShell.test.tsx
git commit -m "feat(web): add effect plan workspace to video workflow"
```

---

## Task 10: 完善导出包、媒体校验与显式恢复

**Files:**

- Modify: `apps/api/src/workbench/video/package_service.py`
- Modify: `apps/api/src/workbench/video/render_service.py`
- Create: `apps/api/src/workbench/video/effect_audit.py`
- Test: `tests/unit/video/test_effect_export_package.py`
- Test: `tests/unit/video/test_media_probe_aspect_ratio.py`
- Test: `tests/integration/test_effect_render_recovery.py`
- Test: `tests/integration/test_effect_export_round_trip.py`

**Produces:** 可复现的 EffectCatalog、逐页计划、审计摘要与按 Props 画幅校验。  
**Consumes:** Props V2、页面缓存和现有同步 exporter。

### Step 1: 写发布包与画幅失败测试

```python
def test_export_contains_effect_contract_and_hashes(exported_package: Path) -> None:
    assert (exported_package / "Remotion工程/EffectCatalog.json").is_file()
    page_plan = read_json(exported_package / "Remotion工程/effect-plans/page-0001.json")
    props = read_json(exported_package / "Remotion工程/ProjectVideoProps.json")
    assert page_plan["plan_hash"] == props["pages"][0]["effect_plan_hash"]

def test_probe_accepts_vertical_output_matching_props():
    validate_media_probe(probe(width=1080, height=1920), props(width=1080, height=1920))
```

### Step 2: 运行失败测试

```powershell
python -m pytest tests/unit/video/test_effect_export_package.py tests/unit/video/test_media_probe_aspect_ratio.py tests/integration/test_effect_render_recovery.py tests/integration/test_effect_export_round_trip.py -q
```

Expected: FAIL，导出包无 effect 文件且 probe 硬编码横屏。

### Step 3: 写出自包含的 effect 文件

在 `Remotion工程/effect-plans/` 按稳定页序号输出。`EffectAuditSummary.json` 包含目录版本、ready/fallback 数量、warning、每页 revision/hash/status，不包含凭证或完整正文。

### Step 4: 修正媒体探测与恢复语义

`validate_media_probe` 接受 expected width/height/fps/duration。Remotion 运行时 effect 错误使当前导出失败并保留分类证据；不得静默修改项目。显式 fallback 重试必须先通过 Effects mutation 产生新 revision，再重新渲染。

### Step 5: 验证 round trip 与同步渲染兼容

从导出 `ProjectVideoProps.json` 和逐页计划重新验证 hash 与 schema；模拟中断后复用未变页缓存，重新生成最终文件。当前 `/video/render` 仍同步返回，不引入 job ID。

```powershell
python -m pytest tests/unit/video tests/integration/test_effect_render_recovery.py tests/integration/test_effect_export_round_trip.py -q
```

Expected: PASS。

### Step 6: Commit（仅有效 Git worktree）

```powershell
git add apps/api/src/workbench/video tests/unit/video tests/integration/test_effect_render_recovery.py tests/integration/test_effect_export_round_trip.py
git commit -m "feat(export): package effect plans and validate target aspect"
```

---

## Task 11: 建立端到端、视觉和 40 页门禁

**Files:**

- Create: `tests/fixtures/effects/six-page-project.json`
- Modify: `tests/fixtures/effects/manifest.json`
- Create: `tests/e2e/test_effect_engine_mainline.py`
- Create: `tests/e2e/test_effect_engine_restart.py`
- Create: `tests/e2e/test_effect_engine_40_pages.py`
- Create: `remotion/src/effects/__tests__/visual-regression.test.ts`
- Create: `scripts/run-video-quality-gates.ps1`
- Create: `docs/testing/video-acceptance.md`

**Produces:** 可重复的 6 页/40 页全链门禁与关键帧视觉基线。  
**Consumes:** 前 10 项全部产物。

### Step 1: 建立不含真实用户数据的夹具

6 页夹具覆盖：ProgressiveReveal、StatCounter、CompareMode、FocusSpotlight、MapHighlight、SafeSlide。40 页夹具覆盖全部目录、横竖屏策略变更、锁定/未锁定、字幕上下 placement、presenter enabled/disabled。

### Step 2: 写主链端到端失败测试

```python
def test_effect_plan_survives_restart_and_matches_render_props(app_factory, fixture_project):
    first = app_factory(fixture_project)
    generated = first.post_generate_effects()
    first.close()

    second = app_factory(fixture_project)
    props = second.get_video_props()
    assert [p["effect_plan_hash"] for p in props["pages"]] == generated.plan_hashes
    assert second.video_preflight()["blocking"] is False
```

另测：只改第 3 页计划只重渲染第 3 页、发布包 round trip、所有字幕/音频字段前后相等、最终同步渲染可开始。

### Step 3: 运行测试并收集基线失败

```powershell
python -m pytest tests/e2e/test_effect_engine_mainline.py tests/e2e/test_effect_engine_restart.py tests/e2e/test_effect_engine_40_pages.py -q
pnpm --filter @workbench/remotion exec vitest run src/effects/__tests__/visual-regression.test.ts
```

Expected: 首次在未接通的断点失败；逐项修正真实错误，不更新快照掩盖布局回归。

### Step 4: 增加视觉关键帧门禁

每模板采集 16:9 与 9:16 的 start/mid/end 帧，检查：

- 文本不越过安全区；
- 字幕不被遮挡；
- presenter 不覆盖关键内容；
- 原页证据层存在；
- reduced motion 帧无运动偏差但语义内容完整。

基线更新必须附带人工查看记录和变更原因。

### Step 5: 将门禁接入统一脚本

`scripts/run-video-quality-gates.ps1` 依次执行契约、Python、Web、Remotion、E2E、类型、lint 和 build，任何一步非零即停止并保留输出。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-video-quality-gates.ps1
```

Expected: 所有门禁 PASS；报告明确 6 页和 40 页渲染数量、缓存命中、fallback 数量和耗时。

### Step 6: Commit（仅有效 Git worktree）

```powershell
git add tests/fixtures/effects tests/e2e remotion/src/effects/__tests__ scripts/run-video-quality-gates.ps1 docs/testing/video-acceptance.md
git commit -m "test(effects): gate the complete effect video mainline"
```

---

## Task 12: Windows 构建、安装级验收与分阶段发布

**Files:**

- Create: `apps/api/src/workbench/effects/feature_flags.py`
- Create: `apps/web/src/features/effects/featureFlags.ts`
- Modify: `installer/runtime-manifest.json`
- Create: `docs/release/effect-engine-v2-rollout.md`
- Modify: `docs/testing/video-acceptance.md`
- Create: `tests/acceptance/effect-engine-v2-checklist.md`

**Produces:** 可回滚 feature flags、Windows 发布产物、真实运行接口证据和验收记录。  
**Consumes:** Task 11 的统一门禁；继续使用同步 render endpoint。

### Step 1: 写 feature flag 组合测试

覆盖：

```text
persistence=false, preview=false, render=false -> 完整旧链
persistence=true,  preview=false, render=false -> 可写计划但旧预览/渲染
persistence=true,  preview=true,  render=false -> V2 预览、旧最终渲染
persistence=true,  preview=true,  render=true  -> V2 全主链
```

非法组合（preview/render 开启但 persistence 关闭）启动时失败并给出明确配置错误。

### Step 2: 运行发布前全量门禁

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-video-quality-gates.ps1
pnpm lint
pnpm typecheck
pnpm build
```

Expected: PASS。记录每条命令、退出码、测试数量和产物路径。

### Step 3: 构建 Windows 发布目录和安装包

先读取仓库现有 package scripts 与发布文档，使用项目既有命令，不新造旁路打包流程。验证 runtime manifest 包含新的 API 包、Web bundle、Remotion bundle、contract snapshot 和版本号。

若安装器触发 Windows UAC，只暂停在授权窗口并明确提示用户点击“是”；其余普通安装与覆盖更新自动完成。

### Step 4: 使用临时验收项目做真实运行验收

通过实际启动器传入非空 workspace 路径，验证：

1. 原验收项目 ID 与目录一致；
2. 显式生成 6/6 或 40/40 计划；
3. Effects GET、Props V2、结构化预检和视频预检通过；
4. 所有页面预览 URL 可访问；
5. 音频时间线与字幕内容校验前后相等；
6. 关闭并重启后 plan revision/hash 不变；
7. 最终同步渲染能够创建并开始；
8. 单页计划修改只造成对应页缓存 miss；
9. 发布包的 effect plan hash 与 Props 一致。

不要以真实用户的“航空航天”项目做写入测试；如需要只读核验，先确认不会触发自动生成或保存。

### Step 5: 记录发布与回滚证据

`docs/release/effect-engine-v2-rollout.md` 写入：构建版本、开关阶段、验证命令、安装目录、备份位置、已知风险和回滚步骤。回滚只关闭 preview/render 开关，不删除 `effect_plan` 字段、不降级 project.json。

### Step 6: 最终完成性核验

```powershell
rg -n "apps/api/src/effects|from effects|import effects" apps tests
rg -n "effects\[0\].*type|TechBoardTemplate" remotion/src
rg -n "transition:|animation:" remotion/src/effects remotion/src/video
```

Expected:

- 无生产引用指向重复 Python effect 包；
- 无从 `effects[0].type` 推导模板；
- `TechBoardTemplate` 不再是 V2 主链入口；
- 无 CSS transition/animation 驱动模板时间。

### Step 7: Commit（仅有效 Git worktree）

```powershell
git add apps/api/src/workbench/effects/feature_flags.py apps/web/src/features/effects/featureFlags.ts installer/runtime-manifest.json docs/release/effect-engine-v2-rollout.md docs/testing/video-acceptance.md tests/acceptance/effect-engine-v2-checklist.md
git commit -m "chore(release): stage effect engine v2 mainline rollout"
```

---

## Final Verification Matrix

| 门禁 | 命令/证据 | 必须结果 |
|---|---|---|
| Python 契约/单元 | `python -m pytest tests/contract tests/unit/effects tests/unit/domain tests/unit/video -q` | PASS |
| API/集成 | `python -m pytest tests/integration/test_effect*.py tests/integration/test_video_props_effects.py tests/integration/test_partial_effect_rerender.py -q` | PASS |
| E2E | `python -m pytest tests/e2e/test_effect_engine_*.py -q` | 6 页/40 页/重启 PASS |
| Web | `pnpm --filter @workbench/web exec vitest run` | PASS |
| Remotion | `pnpm --filter @workbench/remotion exec vitest run` | 13 模板与画幅 PASS |
| 静态检查 | `pnpm lint` | PASS |
| 类型检查 | `pnpm typecheck` | PASS |
| 构建 | `pnpm build` 与现有 `scripts/build-release.ps1` | PASS，产物完整 |
| 缓存 | 单页计划修改的 render spy 与缓存报告 | 仅目标页 miss |
| 数据保护 | manifest 前后字段 diff 与备份 | 音频/字幕/旁白/页面/预览不变 |
| 重启恢复 | 实际进程关闭重启后的 API 响应 | revision/hash 一致 |
| 最终渲染 | 实际同步 render 请求 | 成功创建并开始 |

## 后续独立项目接口

异步渲染任务化后续只依赖以下稳定产物：

- 不可变 `ProjectVideoProps V2` 快照及其整体 hash；
- 每页 `effect_plan_hash` 和页面缓存键；
- `VideoPreflightReport`；
- 导出目标、页面缓存目录和 EffectAuditSummary；
- 当前同步 exporter 的单次调用边界。

后续项目可在这些接口外增加 job ID、队列、进度、取消和恢复，不应再次改写 EffectPlan 契约或模板解释规则。
