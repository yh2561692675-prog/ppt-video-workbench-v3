# 特效编辑器与模板管理工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 PPT Video Workbench 中交付项目级特效编辑器和本地参数化模板库，并复用 EffectPlan V2、Remotion 注册表、项目素材、预览、预检和最终渲染链路。

**Architecture:** 作者态 `EffectDraftDocument` 独立持久化，Python `EffectPlanCompiler` 在发布时权威编译为现有 EffectPlan V2，并将不可变 `EffectRevisionSnapshot` 与当前 `EffectPlanRecord` 原子落盘。模板库只管理引用内置 renderer key 的声明式数据包；React 工作台通过 FastAPI API 完成编辑、预览、版本管理和安全导入导出。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、pytest、React 19、TypeScript 5.8、Zustand 5、TanStack Query 5、Vitest、Remotion 4.0.340、Playwright 1.54、JSON Schema 2020-12。

## Global Constraints

- 仅支持 Windows 本地单用户工作台；首版不引入云服务、账号、权限或多人协作。
- 继续使用现有 EffectPlan V2 作为发布、预览、预检和最终渲染的唯一运行契约。
- 模板包只能包含 manifest、JSON、缩略图和受限静态素材，不得携带或执行 JavaScript、React、脚本、宏、EXE 或 DLL。
- renderer key 必须命中内置 Remotion 注册表；新增 renderer 只能随工作台代码发布。
- 已发布模板和 EffectPlan revision 不可原地修改；回滚通过创建新版本或新 revision 完成。
- 项目固定引用精确模板 SemVer；模板更新不得自动改变已有项目输出。
- 16:9、9:16、reduced-motion、目标帧和性能检查是模板发布门禁。
- 无效作者态允许保存和恢复，但不能写入 `ProjectManifest.pages[].effect_plan`。
- 多页批量操作必须逻辑原子，不允许部分页面静默成功。
- 不新增运行时 npm 或 Python 依赖；使用标准库、现有 Pydantic、Zustand、TanStack Query 和 Remotion 能力。
- Python 保持 Ruff、Mypy strict 和 pytest 通过；TypeScript 保持 ESLint、Prettier、typecheck、Vitest 和 Playwright 通过。
- 当前 checkout 的 `.git` 指向失效工作树；执行前必须在有效主仓库或由 `superpowers:using-git-worktrees` 创建的有效 worktree 中工作，不得手工改写 `.git` 指针。

---

## 文件结构与职责

### 后端新增文件

| 文件                                             | 单一职责                                          |
| ------------------------------------------------ | ------------------------------------------------- |
| `apps/api/src/workbench/effects/authoring.py`    | 作者态、模板引用和 revision 快照 Pydantic 契约    |
| `apps/api/src/workbench/effects/compiler.py`     | 声明式作者态到 EffectPlan V2 的确定性编译         |
| `apps/api/src/workbench/effects/repository.py`   | 草稿索引、不可变快照、revision 与恢复区原子持久化 |
| `apps/api/src/workbench/effects/service.py`      | 草稿、编译、发布、回滚和批量操作用例              |
| `apps/api/src/workbench/templates/models.py`     | 模板产品、版本、参数 schema、状态与校验报告       |
| `apps/api/src/workbench/templates/package_io.py` | `.pvtmpl` 安全导入、导出、哈希与隔离解压          |
| `apps/api/src/workbench/templates/repository.py` | 本地模板包与可重建索引仓库                        |
| `apps/api/src/workbench/templates/validation.py` | schema、注册表、双画幅、性能和安全门禁编排        |
| `apps/api/src/workbench/templates/service.py`    | 模板创建、复制、校验、发布、弃用、归档和回滚      |
| `apps/api/src/workbench/api/effects.py`          | 项目特效作者 API                                  |
| `apps/api/src/workbench/api/templates.py`        | 模板库 API                                        |
| `schemas/effect-draft-v1.schema.json`            | 作者态对外 JSON Schema                            |
| `schemas/template-package-v1.schema.json`        | 模板 manifest 对外 JSON Schema                    |

### 前端新增文件

| 文件                                                                 | 单一职责                                     |
| -------------------------------------------------------------------- | -------------------------------------------- |
| `apps/web/src/features/effect-editor/model.ts`                       | 前端作者态、摘要、编译诊断和命令类型         |
| `apps/web/src/features/effect-editor/sessionStore.ts`                | Zustand 会话、命令栈、撤销/重做和 dirty 状态 |
| `apps/web/src/features/effect-editor/recoveryStore.ts`               | IndexedDB 断线恢复适配器                     |
| `apps/web/src/features/effect-editor/EffectEditorWorkspace.tsx`      | 编辑器页面编排                               |
| `apps/web/src/features/effect-editor/PageRail.tsx`                   | 页面状态、筛选和多选                         |
| `apps/web/src/features/effect-editor/EffectCanvas.tsx`               | Remotion Player 与错误边界                   |
| `apps/web/src/features/effect-editor/EffectTimeline.tsx`             | 游标、缩放、吸附和片段操作                   |
| `apps/web/src/features/effect-editor/EffectInspector.tsx`            | schema 驱动参数表单与字段诊断                |
| `apps/web/src/features/effect-editor/BatchEffectDialog.tsx`          | 批量影响摘要和原子提交                       |
| `apps/web/src/features/effect-editor/RevisionPanel.tsx`              | revision 历史、差异和回滚                    |
| `apps/web/src/features/template-library/TemplateLibrary.tsx`         | 模板筛选和卡片列表                           |
| `apps/web/src/features/template-library/TemplateDetail.tsx`          | 模板详情页签与版本操作                       |
| `apps/web/src/features/template-library/TemplateParameterEditor.tsx` | schema、默认值、预设和 UI schema 编辑        |
| `apps/web/src/features/template-library/TemplateValidationPanel.tsx` | 校验、双画幅和性能报告                       |
| `apps/web/src/features/template-library/TemplatePackageActions.tsx`  | 模板包导入导出                               |

### 主要修改文件

- `apps/api/src/workbench/domain/effects.py`：为 revision 快照补充稳定辅助函数，不改变 EffectPlan V2。
- `apps/api/src/workbench/domain/models.py`：保持 `PageRecord.effect_plan` 当前运行语义。
- `apps/api/src/workbench/main.py`：构造服务并注册两个新路由。
- `apps/api/src/workbench/video/preview_service.py`：使用已发布 revision/hash，禁止读取草稿。
- `apps/api/src/workbench/cache/dependency_graph.py`：增加页面级与项目级特效失效矩阵。
- `apps/api/src/workbench/diagnostics/package.py`：加入脱敏特效诊断。
- `apps/web/src/api/client.ts`：增加契约与 API 方法。
- `apps/web/src/app/router.tsx`：增加 `/projects/:projectId/effects` 和 `/templates`。
- `apps/web/src/features/workflow/WorkflowShell.tsx`：增加进入特效编辑器入口与 revision/hash 展示。
- `apps/web/src/app/styles.css`：增加工作台响应式布局和状态样式。
- `remotion/src/effects/registry.ts`：补充 renderer 能力描述和只读清单。
- `packages/contracts/project.schema.json`、`packages/contracts/openapi.json`：重新导出契约。

---

### Task 1: 作者态、模板与 revision 契约

**Files:**

- Create: `apps/api/src/workbench/effects/authoring.py`
- Create: `apps/api/src/workbench/templates/__init__.py`
- Create: `apps/api/src/workbench/templates/models.py`
- Create: `schemas/effect-draft-v1.schema.json`
- Create: `schemas/template-package-v1.schema.json`
- Modify: `scripts/export_contracts.py`
- Test: `tests/contract/test_effect_authoring_contract.py`
- Test: `tests/contract/test_template_manifest_contract.py`

**Interfaces:**

- Consumes: `workbench.effects.schema.EffectPlanV2`、`workbench.domain.effects.EffectPlanRecord`。
- Produces: `TemplateRef`、`EffectDraftDocument`、`EffectRevisionSnapshot`、`TemplateManifest`、`TemplateVersionStatus`、`TemplateValidationReport`。

- [ ] **Step 1: 写作者态失败测试**

```python
from uuid import uuid4

import pytest
from pydantic import ValidationError

from workbench.effects.authoring import EffectDraftDocument, TemplateRef


def test_effect_draft_rejects_negative_concurrency_tokens() -> None:
    with pytest.raises(ValidationError):
        EffectDraftDocument(
            project_id=uuid4(),
            page_id=uuid4(),
            base_revision=-1,
            draft_seq=-1,
            template_binding=TemplateRef(
                template_id="progressive-reveal-blue",
                version="1.2.0",
                renderer_key="ProgressiveReveal",
                package_hash="a" * 64,
            ),
        )
```

- [ ] **Step 2: 写模板 manifest 失败测试**

```python
import pytest
from pydantic import ValidationError

from workbench.templates.models import TemplateManifest


def test_template_manifest_rejects_unknown_fields_and_invalid_semver() -> None:
    with pytest.raises(ValidationError):
        TemplateManifest.model_validate(
            {
                "schema_version": "1.0",
                "template_id": "progressive-reveal-blue",
                "version": "latest",
                "renderer_key": "ProgressiveReveal",
                "display_name": "科技蓝逐项揭示",
                "parameter_schema": {"type": "object"},
                "ui_schema": {},
                "defaults": {},
                "presets": [],
                "field_bindings": [],
                "supported_aspect_ratios": ["16:9", "9:16"],
                "page_types": ["content"],
                "reduced_motion_policy": "required",
                "minimum_workbench_version": "0.1.0",
                "catalog_version": "effect-catalog-v2",
                "unknown": True,
            }
        )
```

- [ ] **Step 3: 运行测试并确认缺少模块**

Run: `uv run pytest tests/contract/test_effect_authoring_contract.py tests/contract/test_template_manifest_contract.py -q`

Expected: collection FAIL，错误包含 `No module named 'workbench.effects.authoring'` 或 `No module named 'workbench.templates'`。

- [ ] **Step 4: 实现严格契约**

```python
class AuthoringModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class TemplateRef(AuthoringModel):
    template_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    version: str = Field(pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
    renderer_key: TemplateName
    package_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    preset_id: str | None = None


class EffectDraftDocument(AuthoringModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: UUID
    page_id: UUID
    base_revision: int = Field(ge=0)
    draft_seq: int = Field(ge=0)
    template_binding: TemplateRef
    parameter_values: dict[str, JsonValue] = Field(default_factory=dict)
    timeline_tracks: list[TimelineTrack] = Field(default_factory=list)
    manual_lock: bool = False
    updated_at: datetime
```

在同一文件定义 `TimelineClip`、`TimelineTrack` 和 `EffectRevisionSnapshot`；所有时间字段必须非负，clip 的 `end_ms` 必须大于 `start_ms`，track/clip ID 在各自作用域内唯一。`TemplateManifest` 使用相同的 strict extra-forbid 策略、严格 SemVer、受限 renderer key、双画幅枚举和声明式 `FieldBinding` 联合类型。

- [ ] **Step 5: 导出并比对 JSON Schema**

Run: `uv run python scripts/export_contracts.py`

Expected: `schemas/effect-draft-v1.schema.json` 与 `schemas/template-package-v1.schema.json` 可由模型稳定生成，连续运行两次无 diff。

- [ ] **Step 6: 运行契约、Ruff 与 Mypy**

Run: `uv run pytest tests/contract/test_effect_authoring_contract.py tests/contract/test_template_manifest_contract.py -q`

Expected: PASS。

Run: `uv run ruff check apps/api/src/workbench/effects/authoring.py apps/api/src/workbench/templates tests/contract/test_effect_authoring_contract.py tests/contract/test_template_manifest_contract.py`

Expected: PASS。

Run: `uv run mypy apps/api/src/workbench/effects/authoring.py apps/api/src/workbench/templates`

Expected: PASS with no issues。

- [ ] **Step 7: 提交契约**

```bash
git add apps/api/src/workbench/effects/authoring.py apps/api/src/workbench/templates schemas scripts/export_contracts.py tests/contract
git commit -m "feat: define effect authoring and template contracts"
```

---

### Task 2: 安全模板包与本地模板仓库

**Files:**

- Create: `apps/api/src/workbench/templates/package_io.py`
- Create: `apps/api/src/workbench/templates/repository.py`
- Test: `tests/unit/templates/test_package_io.py`
- Test: `tests/unit/templates/test_repository.py`
- Test: `tests/security/test_template_package_security.py`

**Interfaces:**

- Consumes: `TemplateManifest`。
- Produces: `TemplatePackageReader.inspect(path: Path) -> InspectedTemplatePackage`、`TemplatePackageWriter.export(manifest: TemplateManifest, source_root: Path, destination: Path) -> Path`、`TemplateRepository.get/list/save_draft/install_published/rebuild_index`。

- [ ] **Step 1: 写路径穿越和代码文件拒绝测试**

```python
def test_template_import_rejects_path_traversal_and_executable_content(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.pvtmpl"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.txt", "escape")
        bundle.writestr("renderer.js", "alert(1)")
    with pytest.raises(UnsafeTemplatePackage) as captured:
        TemplatePackageReader().inspect(archive)
    assert captured.value.code == "template_package_unsafe"
    assert not (tmp_path / "escape.txt").exists()
```

- [ ] **Step 2: 写仓库原子安装与索引重建测试**

```python
def test_repository_installs_immutable_version_and_rebuilds_index(tmp_path: Path) -> None:
    repository = TemplateRepository(tmp_path / "template-library")
    package = valid_inspected_package(version="1.2.0")
    installed = repository.install_published(package)
    assert installed.manifest.version == "1.2.0"
    with pytest.raises(TemplateVersionImmutable):
        repository.install_published(package)
    (tmp_path / "template-library" / "index.json").unlink()
    assert repository.rebuild_index() == 1
    assert repository.get("progressive-reveal-blue", "1.2.0").content_hash == installed.content_hash
```

- [ ] **Step 3: 运行测试并确认失败**

Run: `uv run pytest tests/unit/templates tests/security/test_template_package_security.py -q`

Expected: FAIL，缺少 `package_io` 与 `repository`。

- [ ] **Step 4: 实现隔离读取和资源限制**

```python
ALLOWED_SUFFIXES = {".json", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".woff2"}
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_BYTES = 150 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES = 500


def validate_member(info: ZipInfo) -> PurePosixPath:
    path = PurePosixPath(info.filename)
    if path.is_absolute() or ".." in path.parts or ":" in info.filename:
        raise UnsafeTemplatePackage("template_package_unsafe", info.filename)
    if info.file_size > MAX_FILE_BYTES or path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise UnsafeTemplatePackage("template_package_unsafe", info.filename)
    return path
```

读取器必须在写盘前验证全部成员、总文件数、总解压大小、ZIP 压缩比、manifest 哈希清单和 SVG 危险节点。禁止符号链接和硬链接。通过校验后只解压到 `transactions/<uuid>`。

- [ ] **Step 5: 实现内容寻址仓库与原子索引**

```python
class TemplateRepository:
    def install_published(self, package: InspectedTemplatePackage) -> StoredTemplateVersion:
        target = self.packages_root / package.manifest.template_id / package.manifest.version
        if target.exists():
            raise TemplateVersionImmutable(package.manifest.template_id, package.manifest.version)
        staged = self.transactions_root / uuid4().hex
        self._materialize(package, staged)
        os.replace(staged, target)
        self._write_index_atomic(self._scan_packages())
        return self.get(package.manifest.template_id, package.manifest.version)
```

`index.json` 只保存可重建的列表投影；包目录中的 `manifest.json` 和逐文件哈希是内容真相源。导入失败目录移动到 `quarantine/<transaction-id>` 并写入不含绝对路径的 `reason.json`。

- [ ] **Step 6: 验证模板包和仓库测试**

Run: `uv run pytest tests/unit/templates/test_package_io.py tests/unit/templates/test_repository.py tests/security/test_template_package_security.py -q`

Expected: PASS。

Run: `uv run ruff check apps/api/src/workbench/templates tests/unit/templates tests/security/test_template_package_security.py`

Expected: PASS。

- [ ] **Step 7: 提交安全模板仓库**

```bash
git add apps/api/src/workbench/templates tests/unit/templates tests/security/test_template_package_security.py
git commit -m "feat: add secure local template package repository"
```

---

### Task 3: 确定性 EffectPlan 编译器与跨语言黄金样例

**Files:**

- Create: `apps/api/src/workbench/effects/compiler.py`
- Create: `apps/web/src/features/effect-editor/compiler.ts`
- Create: `tests/fixtures/effects/authoring-progressive-reveal.json`
- Create: `tests/fixtures/effects/compiled-progressive-reveal.json`
- Test: `tests/unit/effects/test_authoring_compiler.py`
- Test: `apps/web/src/features/effect-editor/compiler.test.ts`

**Interfaces:**

- Consumes: `EffectDraftDocument`、`TemplateManifest`、页面时长、页型与素材 hashes。
- Produces: `EffectPlanCompiler.compile(request: CompileRequest) -> EffectCompilationResult`；前端 `compileDraft(input: CompileInput): CompileResult` 使用相同字段名。

- [ ] **Step 1: 写 Python 黄金输出测试**

```python
def test_compiler_matches_progressive_reveal_golden_fixture() -> None:
    source = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    result = EffectPlanCompiler().compile(CompileRequest.model_validate(source))
    assert result.plan.model_dump(mode="json") == expected["plan"]
    assert result.template_ref.model_dump(mode="json") == expected["template_ref"]
    assert result.diagnostics == []
```

- [ ] **Step 2: 写 TypeScript 黄金输出测试**

```typescript
import expected from '../../../../../tests/fixtures/effects/compiled-progressive-reveal.json';
import source from '../../../../../tests/fixtures/effects/authoring-progressive-reveal.json';
import { compileDraft } from './compiler';

it('matches the Python golden EffectPlan', () => {
  expect(compileDraft(source).plan).toEqual(expected.plan);
});
```

- [ ] **Step 3: 运行双端测试并确认失败**

Run: `uv run pytest tests/unit/effects/test_authoring_compiler.py -q`

Expected: FAIL，缺少 `EffectPlanCompiler`。

Run: `pnpm --filter @workbench/web test -- src/features/effect-editor/compiler.test.ts`

Expected: FAIL，缺少 `compileDraft`。

- [ ] **Step 4: 实现 Python 权威编译器**

```python
class EffectPlanCompiler:
    def compile(self, request: CompileRequest) -> EffectCompilationResult:
        values = validate_parameter_values(
            request.template.parameter_schema, request.draft.parameter_values
        )
        bound = apply_field_bindings(request.template.field_bindings, values)
        plan = EffectPlanV2.model_validate(
            {
                "page_id": str(request.draft.page_id),
                "page_type": request.page_type,
                "duration_ms": request.duration_ms,
                "aspect_ratio": request.aspect_ratio,
                "template": request.template.renderer_key,
                "template_payload": bound.template_payload,
                "cues": bound.cues,
                "effects": compile_clips(request.draft.timeline_tracks),
                "camera": bound.camera,
                "transition": bound.transition,
                "manual_lock": request.draft.manual_lock,
                "source_hashes": request.source_hashes,
            }
        )
        return EffectCompilationResult(plan=plan, template_ref=request.draft.template_binding)
```

只允许四类 binding：常量、JSON Pointer 取值、枚举映射、带固定 min/max 的线性数值映射。编译输出按 ID、轨道序号和时间稳定排序；规范化 JSON 禁止依赖 dict 插入顺序。

- [ ] **Step 5: 实现 TypeScript 预览编译器**

```typescript
export function compileDraft(input: CompileInput): CompileResult {
  const values = validateParameters(input.template.parameter_schema, input.draft.parameter_values);
  const bound = applyFieldBindings(input.template.field_bindings, values);
  return {
    plan: parseEffectPlan({
      schema_version: '2.0',
      page_id: input.draft.page_id,
      page_type: input.page_type,
      duration_ms: input.duration_ms,
      aspect_ratio: input.aspect_ratio,
      template: input.template.renderer_key,
      template_payload: bound.template_payload,
      cues: bound.cues,
      effects: compileClips(input.draft.timeline_tracks),
      camera: bound.camera,
      transition: bound.transition,
      manual_lock: input.draft.manual_lock,
      source_hashes: input.source_hashes,
    }),
    diagnostics: [],
  };
}
```

- [ ] **Step 6: 运行跨语言测试和类型检查**

Run: `uv run pytest tests/unit/effects/test_authoring_compiler.py tests/contract/test_effect_plan_v2.py -q`

Expected: PASS。

Run: `pnpm --filter @workbench/web test -- src/features/effect-editor/compiler.test.ts`

Expected: PASS。

Run: `pnpm --filter @workbench/web typecheck`

Expected: PASS。

- [ ] **Step 7: 提交编译器**

```bash
git add apps/api/src/workbench/effects/compiler.py apps/web/src/features/effect-editor tests/fixtures/effects tests/unit/effects/test_authoring_compiler.py
git commit -m "feat: compile effect drafts into deterministic v2 plans"
```

---

### Task 4: 草稿索引、恢复区与 revision 仓库

**Files:**

- Create: `apps/api/src/workbench/effects/repository.py`
- Test: `tests/unit/effects/test_authoring_repository.py`
- Test: `tests/integration/test_effect_draft_recovery.py`
- Test: `tests/integration/test_effect_batch_atomicity.py`

**Interfaces:**

- Consumes: `EffectDraftDocument`、`EffectRevisionSnapshot` 和已解析安全项目目录。
- Produces: `EffectAuthoringRepository.load_draft/save_draft/save_batch/list_revisions/write_revision/recover_transactions`。

- [ ] **Step 1: 写乐观并发与批量原子性测试**

```python
def test_save_draft_rejects_stale_sequence(
    repository: EffectAuthoringRepository, draft: EffectDraftDocument
) -> None:
    saved = repository.save_draft(draft, expected_draft_seq=0)
    with pytest.raises(EffectDraftConflict):
        repository.save_draft(draft, expected_draft_seq=0)
    assert repository.load_draft(draft.page_id).draft_seq == saved.draft_seq


def test_batch_failure_keeps_previous_index(
    repository: EffectAuthoringRepository,
    two_drafts: list[EffectDraftDocument],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = repository.read_index()
    monkeypatch.setattr(repository, "_replace_index", raising_write_error)
    with pytest.raises(OSError):
        repository.save_batch(
            two_drafts, expected_sequences={draft.page_id: 0 for draft in two_drafts}
        )
    assert repository.read_index() == before
```

- [ ] **Step 2: 写中断事务恢复测试**

```python
def test_recovery_removes_uncommitted_transaction(project_dir: Path) -> None:
    transaction = project_dir / "effects" / "transactions" / "orphan"
    transaction.mkdir(parents=True)
    (transaction / "state.json").write_text('{"status":"prepared"}', encoding="utf-8")
    repository = EffectAuthoringRepository(project_dir)
    assert repository.recover_transactions() == 1
    assert not transaction.exists()
```

- [ ] **Step 3: 运行测试并确认缺少仓库**

Run: `uv run pytest tests/unit/effects/test_authoring_repository.py tests/integration/test_effect_draft_recovery.py tests/integration/test_effect_batch_atomicity.py -q`

Expected: FAIL，缺少 `EffectAuthoringRepository`。

- [ ] **Step 4: 实现不可变 snapshot 与原子 index**

```python
class EffectAuthoringRepository:
    def save_batch(
        self,
        drafts: Sequence[EffectDraftDocument],
        *,
        expected_sequences: Mapping[UUID, int],
    ) -> list[EffectDraftDocument]:
        current = self.read_index()
        self._assert_sequences(current, expected_sequences)
        staged = [
            self._write_snapshot(draft.model_copy(update={"draft_seq": draft.draft_seq + 1}))
            for draft in drafts
        ]
        next_index = current.with_snapshots(staged)
        self._replace_index(next_index)
        return [self._read_snapshot(item.relative_path) for item in staged]
```

snapshot 文件名使用 `<draft-seq>-<sha256>.json`；`index.json` 保存 page ID 到相对路径、序号和哈希的映射。索引替换前验证所有 snapshot 已存在且哈希匹配。

- [ ] **Step 5: 实现 revision 快照与恢复保留策略**

`write_revision()` 只创建 `<revision>-<plan-hash>.json`，若同名内容不一致则抛 `EffectRevisionImmutable`。每页恢复草稿最多保留 20 个；清理只删除未被 index 引用且不是最近 20 个的 snapshot。

```python
def revision_path(page_id: UUID, record: EffectPlanRecord) -> PurePosixPath:
    return PurePosixPath(
        "effects", "revisions", str(page_id), f"{record.revision}-{record.plan_hash}.json"
    )
```

- [ ] **Step 6: 运行仓库、恢复和安全路径测试**

Run: `uv run pytest tests/unit/effects/test_authoring_repository.py tests/integration/test_effect_draft_recovery.py tests/integration/test_effect_batch_atomicity.py tests/security/test_workspace_paths.py -q`

Expected: PASS。

- [ ] **Step 7: 提交作者态仓库**

```bash
git add apps/api/src/workbench/effects/repository.py tests/unit/effects/test_authoring_repository.py tests/integration/test_effect_draft_recovery.py tests/integration/test_effect_batch_atomicity.py
git commit -m "feat: persist effect drafts and immutable revisions atomically"
```

---

### Task 5: 特效作者服务、发布事务与缓存失效

**Files:**

- Create: `apps/api/src/workbench/effects/service.py`
- Modify: `apps/api/src/workbench/cache/dependency_graph.py`
- Modify: `apps/api/src/workbench/cache/key.py`
- Modify: `apps/api/src/workbench/video/preview_service.py`
- Test: `tests/integration/test_effect_authoring_service.py`
- Test: `tests/unit/cache/test_effect_invalidation.py`
- Test: `tests/integration/test_effect_publish_recovery.py`

**Interfaces:**

- Consumes: `ProjectService`、`TemplateRepository`、`EffectAuthoringRepository`、`EffectPlanCompiler`。
- Produces: `EffectAuthoringService.summary/get_draft/save_draft/compile/publish/revert/preview_batch/commit_batch`。

- [ ] **Step 1: 写发布成功与失败不覆盖测试**

```python
def test_publish_increments_revision_and_updates_manifest(
    service: EffectAuthoringService, page_id: UUID
) -> None:
    published = service.publish(page_id, expected_base_revision=0, expected_draft_seq=1)
    assert published.record.revision == 1
    project = service.project_service.get(published.project_id)
    page = next(item for item in project.pages if item.id == page_id)
    assert page.effect_plan is not None
    assert page.effect_plan.plan_hash == published.record.plan_hash


def test_compile_failure_keeps_previous_published_record(
    service: EffectAuthoringService, page_id: UUID
) -> None:
    before = service.current_record(page_id)
    service.save_invalid_parameter(page_id, "items", [])
    with pytest.raises(EffectPublishBlocked):
        service.publish(page_id, expected_base_revision=before.revision, expected_draft_seq=2)
    assert service.current_record(page_id) == before
```

- [ ] **Step 2: 写精确缓存失效测试**

```python
def test_publishing_one_page_invalidates_page_and_project_video_only() -> None:
    result = effect_invalidation_for_publish(project_id="project-1", page_id="page-2")
    assert result == {
        "page_preview:project-1:page-2",
        "page_render:project-1:page-2",
        "video_preflight:project-1",
        "video_export:project-1",
    }
```

- [ ] **Step 3: 运行测试并确认失败**

Run: `uv run pytest tests/integration/test_effect_authoring_service.py tests/unit/cache/test_effect_invalidation.py tests/integration/test_effect_publish_recovery.py -q`

Expected: FAIL，缺少服务和新失效函数。

- [ ] **Step 4: 实现发布用例与审计事件**

```python
def publish(
    self, page_id: UUID, *, expected_base_revision: int, expected_draft_seq: int
) -> PublishedEffect:
    project, page = self._project_and_page(page_id)
    draft = self.repository.load_draft(page_id)
    self._assert_publish_tokens(page, draft, expected_base_revision, expected_draft_seq)
    template = self.templates.get_published(draft.template_binding)
    compilation = self.compiler.compile(self._compile_request(project, page, draft, template))
    record = self._record_for(page, compilation)
    snapshot = self._snapshot_for(record, draft, compilation)
    self.repository.write_revision(snapshot)
    updated = replace_page_effect_plan(project, page_id, record)
    saved = self.project_service.save(append_effect_audit(updated, snapshot))
    self.cache.invalidate(effect_invalidation_for_publish(str(saved.id), str(page_id)))
    return PublishedEffect(project_id=saved.id, page_id=page_id, record=record, snapshot=snapshot)
```

revision 文件先落盘，manifest 更新失败时只产生可清理孤立快照，当前运行记录不变。manifest 成功后才失效缓存。预览服务只读取 `PageRecord.effect_plan`，不得读取草稿。

- [ ] **Step 5: 实现批量预检令牌和原子提交**

`preview_batch()` 返回 `batch_token`、目标页面、预期序号、字段级错误和变更摘要。`commit_batch()` 重新验证 token 哈希、调用 repository 单次 index 替换，并为每页标记 dirty；批量应用本身不自动发布。

```python
class BatchPreview(AuthoringModel):
    batch_token: str
    expected_sequences: dict[UUID, int]
    changed_pages: list[UUID]
    errors: list[EffectDiagnostic]
```

- [ ] **Step 6: 运行服务、缓存和现有视频测试**

Run: `uv run pytest tests/integration/test_effect_authoring_service.py tests/integration/test_effect_publish_recovery.py tests/unit/cache/test_effect_invalidation.py tests/integration/test_video_preview_routes.py tests/integration/test_video_render_routes.py -q`

Expected: PASS。

- [ ] **Step 7: 提交作者服务**

```bash
git add apps/api/src/workbench/effects/service.py apps/api/src/workbench/cache apps/api/src/workbench/video/preview_service.py tests/integration/test_effect_authoring_service.py tests/integration/test_effect_publish_recovery.py tests/unit/cache/test_effect_invalidation.py
git commit -m "feat: publish effect revisions with precise cache invalidation"
```

---

### Task 6: 模板生命周期、校验门禁与系统模板引导

**Files:**

- Create: `apps/api/src/workbench/templates/validation.py`
- Create: `apps/api/src/workbench/templates/service.py`
- Create: `runtime-assets/templates/system-template-catalog.json`
- Test: `tests/unit/templates/test_service.py`
- Test: `tests/integration/test_template_validation.py`
- Test: `tests/integration/test_system_template_bootstrap.py`
- Test: `tests/performance/test_template_budgets.py`

**Interfaces:**

- Consumes: `TemplateRepository`、Remotion renderer capability snapshot、模板预览执行适配器。
- Produces: `TemplateService.create_version/validate/publish/deprecate/archive/rollback/import_package/export_package` 和 `TemplateValidator.validate`。

- [ ] **Step 1: 写状态机与不可变发布测试**

```python
def test_template_version_requires_validation_before_publish(service: TemplateService) -> None:
    draft = service.create(
        "progressive-reveal-blue", display_name="科技蓝逐项揭示", renderer_key="ProgressiveReveal"
    )
    with pytest.raises(TemplateStateConflict):
        service.publish(draft.template_id, draft.version)
    validated = service.validate(draft.template_id, draft.version)
    assert validated.status == TemplateVersionStatus.VALIDATED
    published = service.publish(draft.template_id, draft.version)
    assert published.status == TemplateVersionStatus.PUBLISHED
    with pytest.raises(TemplateVersionImmutable):
        service.update(published.manifest)
```

- [ ] **Step 2: 写双画幅、reduced-motion 和性能门禁测试**

```python
def test_validation_blocks_missing_portrait_snapshot(
    validator: TemplateValidator, manifest: TemplateManifest
) -> None:
    report = validator.validate(manifest, FakeRendererProbe(missing={"9:16"}))
    assert report.allowed is False
    assert "portrait_snapshot_missing" in report.codes


def test_validation_blocks_renderer_over_budget(
    validator: TemplateValidator, manifest: TemplateManifest
) -> None:
    report = validator.validate(manifest, FakeRendererProbe(elapsed_ratio=2.6))
    assert report.allowed is False
    assert "render_budget_exceeded" in report.codes
```

- [ ] **Step 3: 运行测试并确认失败**

Run: `uv run pytest tests/unit/templates/test_service.py tests/integration/test_template_validation.py tests/integration/test_system_template_bootstrap.py tests/performance/test_template_budgets.py -q`

Expected: FAIL，缺少 `TemplateService` 和 `TemplateValidator`。

- [ ] **Step 4: 实现显式状态转换**

```python
ALLOWED_TRANSITIONS = {
    TemplateVersionStatus.DRAFT: {TemplateVersionStatus.VALIDATED},
    TemplateVersionStatus.VALIDATED: {TemplateVersionStatus.DRAFT, TemplateVersionStatus.PUBLISHED},
    TemplateVersionStatus.PUBLISHED: {TemplateVersionStatus.DEPRECATED},
    TemplateVersionStatus.DEPRECATED: {TemplateVersionStatus.ARCHIVED},
    TemplateVersionStatus.ARCHIVED: set(),
}
```

`rollback(template_id, version)` 读取历史内容、计算下一个补丁版本、创建新的 draft；不改变历史版本。`SafeSlide` 标记为 internal 且禁止 deprecate/archive。

- [ ] **Step 5: 实现校验报告与 13 个系统模板引导**

校验器必须生成机器码和人类可读修复动作，依次检查 manifest、parameter schema/defaults/presets、field bindings、renderer 能力、16:9、9:16、reduced-motion、目标帧、峰值内存和 2.5 倍 SafeSlide 性能阈值。

`system-template-catalog.json` 为现有 13 个 renderer 定义稳定 template ID、`1.0.0` 版本和只读系统标志；应用启动时缺失才安装，已存在版本不覆盖。

- [ ] **Step 6: 运行模板服务、性能与现有 registry 测试**

Run: `uv run pytest tests/unit/templates/test_service.py tests/integration/test_template_validation.py tests/integration/test_system_template_bootstrap.py tests/performance/test_template_budgets.py -q`

Expected: PASS。

Run: `pnpm --filter @workbench/remotion test -- src/effects`

Expected: PASS。

- [ ] **Step 7: 提交模板生命周期**

```bash
git add apps/api/src/workbench/templates runtime-assets/templates tests/unit/templates tests/integration/test_template_validation.py tests/integration/test_system_template_bootstrap.py tests/performance/test_template_budgets.py
git commit -m "feat: add validated template version lifecycle"
```

---

### Task 7: FastAPI 特效与模板接口

**Files:**

- Create: `apps/api/src/workbench/api/effects.py`
- Create: `apps/api/src/workbench/api/templates.py`
- Modify: `apps/api/src/workbench/main.py`
- Modify: `scripts/export_contracts.py`
- Modify: `packages/contracts/openapi.json`
- Test: `tests/integration/test_effect_authoring_routes.py`
- Test: `tests/integration/test_template_routes.py`
- Test: `tests/contract/test_openapi_effects_templates.py`

**Interfaces:**

- Consumes: `EffectAuthoringService`、`TemplateService` 和现有 `Envelope[T]`。
- Produces: 设计文档第 13 节的 HTTP API、稳定错误码和导出的 OpenAPI 契约。

- [ ] **Step 1: 写草稿并发与发布路由测试**

```python
def test_stale_draft_put_returns_409(
    client: TestClient, project_and_page: tuple[str, str], valid_draft: dict[str, object]
) -> None:
    project_id, page_id = project_and_page
    first = client.put(
        f"/api/projects/{project_id}/effects/pages/{page_id}/draft", json=valid_draft
    )
    assert first.status_code == 200
    stale = client.put(
        f"/api/projects/{project_id}/effects/pages/{page_id}/draft", json=valid_draft
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "effect_draft_conflict"
```

- [ ] **Step 2: 写模板导入与版本不可变路由测试**

```python
def test_published_template_put_is_rejected(
    client: TestClient, published_template: tuple[str, str]
) -> None:
    template_id, version = published_template
    response = client.put(
        f"/api/templates/{template_id}/versions/{version}", json={"display_name": "changed"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "template_version_immutable"
```

- [ ] **Step 3: 运行路由测试并确认 404**

Run: `uv run pytest tests/integration/test_effect_authoring_routes.py tests/integration/test_template_routes.py tests/contract/test_openapi_effects_templates.py -q`

Expected: FAIL，路由返回 404。

- [ ] **Step 4: 实现 typed request/response 与错误映射**

```python
def create_effects_router(service: EffectAuthoringService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/effects")

    @router.put("/pages/{page_id}/draft", response_model=Envelope[EffectDraftDocument])
    def save_draft(
        project_id: UUID, page_id: UUID, request: SaveDraftRequest
    ) -> Envelope[EffectDraftDocument]:
        try:
            return envelope(
                service.save_draft(project_id, page_id, request.draft, request.expected_draft_seq)
            )
        except EffectDraftConflict as error:
            raise HTTPException(status_code=409, detail=error.problem()) from error

    return router
```

两个 router 覆盖设计文档全部 endpoint。文件上传使用 `UploadFile` 和受限流式临时文件；导出使用 `FileResponse`，文件名只来自安全 template ID/version。

- [ ] **Step 5: 在应用工厂构造服务并注册路由**

在 `create_app()` 中基于 `configured_root` 创建 `TemplateRepository`、`TemplateService` 和按项目解析目录的 `EffectAuthoringServiceFactory`；写入 `app.state` 便于测试覆盖。路由注册必须位于静态文件 mount 之前。

- [ ] **Step 6: 导出 OpenAPI 并运行接口回归**

Run: `uv run python scripts/export_contracts.py`

Expected: `packages/contracts/openapi.json` 包含 `/api/templates` 和 `/api/projects/{project_id}/effects` 路径。

Run: `uv run pytest tests/integration/test_effect_authoring_routes.py tests/integration/test_template_routes.py tests/contract/test_openapi_effects_templates.py tests/integration/test_project_api.py -q`

Expected: PASS。

- [ ] **Step 7: 提交 API**

```bash
git add apps/api/src/workbench/api/effects.py apps/api/src/workbench/api/templates.py apps/api/src/workbench/main.py scripts/export_contracts.py packages/contracts/openapi.json tests/integration/test_effect_authoring_routes.py tests/integration/test_template_routes.py tests/contract/test_openapi_effects_templates.py
git commit -m "feat: expose effect authoring and template APIs"
```

---

### Task 8: Remotion renderer 能力清单与草稿预览组件

**Files:**

- Modify: `remotion/src/effects/registry.ts`
- Create: `remotion/src/effects/EffectDraftPreview.tsx`
- Modify: `remotion/src/effects/interpreter.tsx`
- Test: `remotion/src/effects/registryCapabilities.test.ts`
- Test: `remotion/src/effects/EffectDraftPreview.test.tsx`
- Test: `tests/contract/test_renderer_catalog_alignment.py`

**Interfaces:**

- Consumes: EffectPlan V2、现有模板组件和 fallback 规则。
- Produces: `RendererCapability`、`listRendererCapabilities()`、`EffectDraftPreview({plan, currentFrame, reducedMotion})`。

- [ ] **Step 1: 写完整 renderer 能力测试**

```typescript
it('publishes immutable capabilities for every catalog renderer', () => {
  const capabilities = listRendererCapabilities();
  expect(capabilities.map((item) => item.key).sort()).toEqual(
    [
      'CardStack',
      'ChapterCurtain',
      'ChartNarration',
      'CompareMode',
      'FocusSpotlight',
      'GaugeAndRatio',
      'MapHighlight',
      'PathBuilder',
      'ProgressiveReveal',
      'RiskAlert',
      'SafeSlide',
      'StatCounter',
      'TagMatrix',
    ].sort(),
  );
  expect(capabilities.every((item) => item.supportedAspectRatios.includes('16:9'))).toBe(true);
  expect(Object.isFrozen(capabilities)).toBe(true);
});
```

- [ ] **Step 2: 写预览错误隔离测试**

```typescript
it('renders SafeSlide fallback for an unsupported effect event', () => {
  const html = renderToStaticMarkup(
    <EffectDraftPreview plan={unknownEffectPlan} currentFrame={12} reducedMotion={false} />,
  );
  expect(html).toContain('aria-label="特效预览降级"');
  expect(html).toContain('SafeSlide');
});
```

- [ ] **Step 3: 运行测试并确认失败**

Run: `pnpm --filter @workbench/remotion test -- src/effects/registryCapabilities.test.ts src/effects/EffectDraftPreview.test.tsx`

Expected: FAIL，缺少能力接口和预览组件。

- [ ] **Step 4: 扩展注册表元数据**

```typescript
export type RendererCapability = Readonly<{
  key: EffectTemplateName;
  payloadKind: string;
  supportedAspectRatios: readonly ('16:9' | '9:16')[];
  performance: 'safe' | 'standard';
  fallback: EffectTemplateName;
  reducedMotion: 'required' | 'native';
  easingPresets: readonly ('linear' | 'ease-out' | 'ease-in-out')[];
}>;

export function listRendererCapabilities(): readonly RendererCapability[] {
  return Object.freeze(
    [...descriptors.values()].map(({ component: _component, name: key, ...rest }) =>
      Object.freeze({ key, ...rest }),
    ),
  );
}
```

为全部 13 个 renderer 提供显式 capability，禁止依赖 register 默认值掩盖遗漏。Python catalog 对齐测试读取一个由 Remotion 构建脚本导出的 JSON 清单并比较 renderer key、payload kind 和画幅。

- [ ] **Step 5: 实现页面级 Error Boundary 和 reduced-motion**

`EffectDraftPreview` 调用现有 interpreter 和 registry；捕获渲染错误后只渲染 SafeSlide，并通过 `onDiagnostic` 返回 renderer key、帧号、画幅和错误类型，不返回素材内容。

```typescript
export function EffectDraftPreview(props: EffectDraftPreviewProps) {
  return (
    <EffectPreviewBoundary plan={props.plan} currentFrame={props.currentFrame} onDiagnostic={props.onDiagnostic}>
      <InterpretedEffect plan={props.plan} currentFrame={props.currentFrame} reducedMotion={props.reducedMotion} />
    </EffectPreviewBoundary>
  );
}
```

- [ ] **Step 6: 运行 Remotion、契约和类型测试**

Run: `pnpm --filter @workbench/remotion test -- src/effects`

Expected: PASS。

Run: `pnpm --filter @workbench/remotion typecheck`

Expected: PASS。

Run: `uv run pytest tests/contract/test_renderer_catalog_alignment.py -q`

Expected: PASS。

- [ ] **Step 7: 提交 renderer 能力**

```bash
git add remotion/src/effects tests/contract/test_renderer_catalog_alignment.py
git commit -m "feat: expose renderer capabilities and isolated draft preview"
```

---

### Task 9: 前端 API 契约、一级导航与路由骨架

**Files:**

- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/app/App.tsx`
- Modify: `apps/web/src/app/router.tsx`
- Create: `apps/web/src/app/AppNav.tsx`
- Create: `apps/web/src/features/effect-editor/EffectProjectPicker.tsx`
- Create: `apps/web/src/features/effect-editor/EffectEditorWorkspace.tsx`
- Create: `apps/web/src/features/template-library/TemplateLibrary.tsx`
- Create: `apps/web/src/features/template-library/TemplateDetail.tsx`
- Modify: `apps/web/src/features/workflow/WorkflowShell.tsx`
- Test: `apps/web/src/api/client.effects.test.ts`
- Test: `apps/web/src/app/App.effects-routes.test.tsx`

**Interfaces:**

- Consumes: Task 7 OpenAPI 路由。
- Produces: typed `EffectDraft`、`EffectSummary`、`TemplateListItem`、`TemplateVersion` 与 `api.effects*`、`api.templates*` 方法；路由 `/effects`、`/projects/:projectId/effects`、`/templates`、`/templates/:templateId`。

- [ ] **Step 1: 写请求路径和 409 错误测试**

```typescript
it('sends concurrency tokens when saving an effect draft', async () => {
  server.use(
    http.put('/api/projects/p1/effects/pages/page-1/draft', async ({ request }) => {
      expect(await request.json()).toMatchObject({ expected_draft_seq: 3 });
      return HttpResponse.json(envelope(savedDraft));
    }),
  );
  await api.saveEffectDraft('p1', 'page-1', savedDraft, 3);
});
```

- [ ] **Step 2: 写路由和工作流入口测试**

```typescript
it('opens the project effect editor from workflow step six', async () => {
  renderAppAt('/projects/project-1/step/6');
  const link = await screen.findByRole('link', { name: '打开特效编辑器' });
  expect(link).toHaveAttribute('href', '/projects/project-1/effects');
});
```

- [ ] **Step 3: 运行前端测试并确认失败**

Run: `pnpm --filter @workbench/web test -- src/api/client.effects.test.ts src/app/App.effects-routes.test.tsx`

Expected: FAIL，缺少 API 方法和路由。

- [ ] **Step 4: 增加 typed API 方法**

```typescript
saveEffectDraft: (projectId: string, pageId: string, draft: EffectDraft, expectedDraftSeq: number) =>
  request<EffectDraft>(`/api/projects/${projectId}/effects/pages/${pageId}/draft`, {
    method: 'PUT',
    body: JSON.stringify({ draft, expected_draft_seq: expectedDraftSeq }),
  }),
publishEffect: (projectId: string, pageId: string, baseRevision: number, draftSeq: number) =>
  request<PublishedEffect>(`/api/projects/${projectId}/effects/pages/${pageId}/publish`, {
    method: 'POST',
    body: JSON.stringify({ expected_base_revision: baseRevision, expected_draft_seq: draftSeq }),
  }),
```

在同一对象加入 summary、draft、compile、revisions、revert、batch preview/commit、template list/detail/create/update/validate/publish/deprecate/archive/rollback/import/export 方法。

- [ ] **Step 5: 增加导航、项目选择器和骨架路由**

`AppNav` 提供“项目”“特效编辑器”“模板库”“诊断”入口；`/effects` 使用现有 `api.listProjects()` 显示项目选择器。项目编辑器和模板库骨架必须有 loading、empty、error 和 retry 状态。

```tsx
<Route path="/effects" element={<EffectProjectPicker />} />
<Route path="/projects/:projectId/effects" element={<EffectEditorWorkspace />} />
<Route path="/templates" element={<TemplateLibrary />} />
<Route path="/templates/:templateId" element={<TemplateDetail />} />
```

- [ ] **Step 6: 运行路由、类型和现有 App 测试**

Run: `pnpm --filter @workbench/web test -- src/api/client.effects.test.ts src/app/App.effects-routes.test.tsx src/app/App.test.tsx`

Expected: PASS。

Run: `pnpm --filter @workbench/web typecheck`

Expected: PASS。

- [ ] **Step 7: 提交前端入口**

```bash
git add apps/web/src/api/client.ts apps/web/src/app apps/web/src/features/effect-editor apps/web/src/features/template-library apps/web/src/features/workflow/WorkflowShell.tsx apps/web/src/api/client.effects.test.ts
git commit -m "feat: add effect editor and template library routes"
```

---

### Task 10: 编辑会话、命令栈、自动保存与断线恢复

**Files:**

- Create: `apps/web/src/features/effect-editor/model.ts`
- Create: `apps/web/src/features/effect-editor/sessionStore.ts`
- Create: `apps/web/src/features/effect-editor/recoveryStore.ts`
- Create: `apps/web/src/features/effect-editor/useEffectAutosave.ts`
- Test: `apps/web/src/features/effect-editor/sessionStore.test.ts`
- Test: `apps/web/src/features/effect-editor/useEffectAutosave.test.tsx`
- Test: `apps/web/src/features/effect-editor/recoveryStore.test.ts`

**Interfaces:**

- Consumes: Task 9 typed API。
- Produces: `createEffectSession(initialDraft)`、`execute(command)`、`undo()`、`redo()`、`useEffectAutosave()`、`EffectRecoveryStore`。

- [ ] **Step 1: 写命令栈和不可变状态测试**

```typescript
it('groups a drag gesture into one undoable command', () => {
  const store = createEffectSession(initialDraft);
  store.getState().beginGesture('move-clip');
  store.getState().execute(moveClip('clip-1', 1200, 2200));
  store.getState().execute(moveClip('clip-1', 1300, 2300));
  store.getState().endGesture();
  store.getState().undo();
  expect(selectClip(store.getState().draft, 'clip-1')).toMatchObject({
    start_ms: 1000,
    end_ms: 2000,
  });
});
```

- [ ] **Step 2: 写 400 ms 自动保存、断线恢复和冲突测试**

```typescript
it('writes IndexedDB recovery after the API becomes unavailable', async () => {
  vi.useFakeTimers();
  api.saveEffectDraft = vi.fn().mockRejectedValue(new TypeError('network'));
  renderHook(() => useEffectAutosave(session));
  act(() => session.getState().execute(setParameter('strength', 0.8)));
  await act(async () => vi.advanceTimersByTimeAsync(400));
  expect(await recoveryStore.get(initialDraft.project_id, initialDraft.page_id)).toMatchObject({
    draft_seq: 3,
  });
  expect(session.getState().persistence).toBe('recovery-only');
});
```

- [ ] **Step 3: 运行会话测试并确认失败**

Run: `pnpm --filter @workbench/web test -- src/features/effect-editor/sessionStore.test.ts src/features/effect-editor/useEffectAutosave.test.tsx src/features/effect-editor/recoveryStore.test.ts`

Expected: FAIL，缺少 store 和 hook。

- [ ] **Step 4: 实现 typed command reducer**

```typescript
export type EffectCommand =
  | { type: 'set-parameter'; key: string; before: JsonValue | undefined; after: JsonValue }
  | { type: 'move-clip'; clipId: string; before: TimeRange; after: TimeRange }
  | { type: 'add-clip'; trackId: string; clip: TimelineClip }
  | { type: 'remove-clip'; trackId: string; clip: TimelineClip }
  | { type: 'set-template'; before: TemplateRef; after: TemplateRef };

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export function applyCommand(draft: EffectDraft, command: EffectCommand): EffectDraft {
  return structuredClone(applyTypedCommand(draft, command));
}
```

Zustand store 只保存当前 draft、past/future command、gesture、selection、dirty、compile 状态和 persistence 状态；不把 React 节点或 API client 放进 store。

- [ ] **Step 5: 实现 IndexedDB 恢复和并发冲突状态**

`EffectRecoveryStore` 使用原生 IndexedDB，key 为 `project_id/page_id`，value 包含 draft、保存时间和最后 API 错误码。服务器保存成功且返回相同/更高 draft_seq 后删除恢复副本。409 时停止自动重试并进入 `conflict`，提供 reload/server、keep-local-copy 两个显式动作。

- [ ] **Step 6: 运行会话、类型和 fake timer 测试**

Run: `pnpm --filter @workbench/web test -- src/features/effect-editor/sessionStore.test.ts src/features/effect-editor/useEffectAutosave.test.tsx src/features/effect-editor/recoveryStore.test.ts`

Expected: PASS。

Run: `pnpm --filter @workbench/web typecheck`

Expected: PASS。

- [ ] **Step 7: 提交编辑会话**

```bash
git add apps/web/src/features/effect-editor/model.ts apps/web/src/features/effect-editor/sessionStore.ts apps/web/src/features/effect-editor/recoveryStore.ts apps/web/src/features/effect-editor/useEffectAutosave.ts apps/web/src/features/effect-editor/*.test.ts apps/web/src/features/effect-editor/*.test.tsx
git commit -m "feat: add recoverable effect editing sessions"
```

---

### Task 11: 特效编辑器布局、时间轴、检查器与即时预览

**Files:**

- Modify: `apps/web/src/features/effect-editor/EffectEditorWorkspace.tsx`
- Create: `apps/web/src/features/effect-editor/PageRail.tsx`
- Create: `apps/web/src/features/effect-editor/EffectCanvas.tsx`
- Create: `apps/web/src/features/effect-editor/EffectTimeline.tsx`
- Create: `apps/web/src/features/effect-editor/EffectInspector.tsx`
- Modify: `apps/web/src/app/styles.css`
- Test: `apps/web/src/features/effect-editor/EffectEditorWorkspace.test.tsx`
- Test: `apps/web/src/features/effect-editor/EffectTimeline.test.tsx`
- Test: `apps/web/src/features/effect-editor/EffectInspector.test.tsx`
- Test: `apps/web/src/features/effect-editor/EffectCanvas.test.tsx`

**Interfaces:**

- Consumes: Task 8 `EffectDraftPreview`、Task 9 API、Task 10 session store。
- Produces: 可操作的四区编辑器、150 ms 即时预览、双画幅/reduced-motion、字段诊断和时间轴命令。

- [ ] **Step 1: 写页面状态与布局测试**

```typescript
it('renders page rail, canvas, timeline, inspector and persistence state', async () => {
  render(<EffectEditorWorkspace />);
  expect(await screen.findByRole('navigation', { name: '项目页面与特效轨道' })).toBeVisible();
  expect(screen.getByRole('region', { name: '特效预览画布' })).toBeVisible();
  expect(screen.getByRole('region', { name: '特效时间轴' })).toBeVisible();
  expect(screen.getByRole('region', { name: '特效参数检查器' })).toBeVisible();
  expect(screen.getByText('已保存')).toBeVisible();
});
```

- [ ] **Step 2: 写拖拽吸附和参数错误测试**

```typescript
it('snaps a clip edge to a narration cue within eight pixels', () => {
  const result = snapRange({ start_ms: 980, end_ms: 1980 }, [1000, 2000], { pixelsPerMs: 0.4, thresholdPx: 8 });
  expect(result).toEqual({ start_ms: 1000, end_ms: 2000 });
});

it('keeps an invalid parameter in the draft and blocks publish', async () => {
  render(<EffectEditorTestHarness schema={itemsSchema} />);
  await userEvent.clear(screen.getByLabelText('揭示项目'));
  expect(screen.getByText('至少需要 1 项')).toBeVisible();
  expect(screen.getByRole('button', { name: '发布特效' })).toBeDisabled();
});
```

- [ ] **Step 3: 运行组件测试并确认失败**

Run: `pnpm --filter @workbench/web test -- src/features/effect-editor/EffectEditorWorkspace.test.tsx src/features/effect-editor/EffectTimeline.test.tsx src/features/effect-editor/EffectInspector.test.tsx src/features/effect-editor/EffectCanvas.test.tsx`

Expected: FAIL，缺少具体编辑器组件。

- [ ] **Step 4: 实现四区工作区和页面状态**

`EffectEditorWorkspace` 查询项目、summary、当前页 draft 和 template；创建 session；页面切换前 flush 自动保存。`PageRail` 显示 unconfigured、draft、invalid、published、stale、fallback 六种状态和多选复选框。

```tsx
<main className="effect-editor-shell">
  <EffectEditorToolbar session={session} onPublish={publish} />
  <PageRail pages={summary.pages} selectedIds={selectedPageIds} onSelect={selectPage} />
  <EffectCanvas
    compileResult={compileResult}
    aspectRatio={aspectRatio}
    reducedMotion={reducedMotion}
  />
  <EffectTimeline draft={draft} cues={pageCues} dispatch={session.getState().execute} />
  <EffectInspector
    template={template}
    draft={draft}
    diagnostics={diagnostics}
    dispatch={session.getState().execute}
  />
</main>
```

- [ ] **Step 5: 实现预览、时间轴和 schema 表单**

参数变化 150 ms 后调用本地 `compileDraft`；成功更新 Player inputProps，失败保留 `lastValidPlan`。时间轴支持选择、添加、复制、删除、移动、缩放和 cue/边界吸附。检查器只渲染允许的 string、number、integer、boolean、enum、array-of-string 控件；遇到未知 schema 关键字显示只读错误并阻止发布。

- [ ] **Step 6: 运行组件、无障碍与类型测试**

Run: `pnpm --filter @workbench/web test -- src/features/effect-editor`

Expected: PASS。

Run: `pnpm --filter @workbench/web typecheck`

Expected: PASS。

Run: `pnpm exec prettier --check apps/web/src/features/effect-editor apps/web/src/app/styles.css`

Expected: PASS。

- [ ] **Step 7: 提交可视化编辑器**

```bash
git add apps/web/src/features/effect-editor apps/web/src/app/styles.css
git commit -m "feat: build the visual effect editing workspace"
```

---

### Task 12: 批量应用、发布、revision 历史与工作流联动

**Files:**

- Create: `apps/web/src/features/effect-editor/BatchEffectDialog.tsx`
- Create: `apps/web/src/features/effect-editor/RevisionPanel.tsx`
- Modify: `apps/web/src/features/effect-editor/EffectEditorWorkspace.tsx`
- Modify: `apps/web/src/features/workflow/WorkflowShell.tsx`
- Modify: `apps/web/src/features/video/PreviewWorkspace.tsx`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/api/src/workbench/video/models.py`
- Modify: `apps/api/src/workbench/video/props_service.py`
- Modify: `remotion/src/video/types.ts`
- Modify: `remotion/src/video/ProjectVideo.tsx`
- Test: `apps/web/src/features/effect-editor/BatchEffectDialog.test.tsx`
- Test: `apps/web/src/features/effect-editor/RevisionPanel.test.tsx`
- Test: `apps/web/src/features/workflow/WorkflowShell.effects.test.tsx`
- Test: `tests/integration/test_effect_preview_revision_alignment.py`

**Interfaces:**

- Consumes: batch preview/commit、publish/revert API 和现有 `PreviewWorkspace.effectPlanMeta`。
- Produces: 批量确认流、发布反馈、历史差异、回滚成新草稿，以及预览/预检/渲染 revision/hash 对齐。

- [ ] **Step 1: 写批量失败不提交和 revision 回滚测试**

```typescript
it('does not enable batch commit when any selected page is incompatible', async () => {
  render(<BatchEffectDialog pageIds={['p1', 'p2']} operation={replaceTemplate} />);
  expect(await screen.findByText('第 2 页不支持 9:16')).toBeVisible();
  expect(screen.getByRole('button', { name: '应用到 2 页' })).toBeDisabled();
});

it('restores a revision as a new dirty draft', async () => {
  render(<RevisionPanel pageId="p1" />);
  await userEvent.click(await screen.findByRole('button', { name: '从 revision 2 创建草稿' }));
  expect(api.revertEffect).toHaveBeenCalledWith('project-1', 'p1', 2);
});
```

- [ ] **Step 2: 写后端 revision/hash 对齐测试**

```python
def test_preview_preflight_and_render_use_the_same_published_revision(
    client: TestClient, published_page: tuple[str, str, int, str]
) -> None:
    project_id, page_id, revision, plan_hash = published_page
    preview = client.get(f"/api/projects/{project_id}/video/preview").json()["data"]
    preview_page = next(item for item in preview["props"]["pages"] if item["page_id"] == page_id)
    assert preview_page["effect_revision"] == revision
    assert preview_page["effect_plan_hash"] == plan_hash
    preflight = client.post(f"/api/projects/{project_id}/video/preflight").json()["data"]
    preflight_page = next(
        item for item in preflight["props"]["pages"] if item["page_id"] == page_id
    )
    assert preflight_page["effect_revision"] == preview_page["effect_revision"]
    assert preflight_page["effect_plan_hash"] == preview_page["effect_plan_hash"]
```

- [ ] **Step 3: 运行测试并确认失败**

Run: `pnpm --filter @workbench/web test -- src/features/effect-editor/BatchEffectDialog.test.tsx src/features/effect-editor/RevisionPanel.test.tsx src/features/workflow/WorkflowShell.effects.test.tsx`

Expected: FAIL，缺少批量与 revision 组件。

Run: `uv run pytest tests/integration/test_effect_preview_revision_alignment.py -q`

Expected: FAIL，预览数据缺少 effect plan meta。

- [ ] **Step 4: 实现批量确认和发布状态**

批量对话框先调用 preview endpoint，逐页显示变更和错误；只在 `errors.length === 0` 时允许 commit，并将 `batch_token` 原样提交。发布按钮必须同时要求：本地 compile 成功、autosave 已确认、无 conflict、模板版本可用。

```typescript
const publishAllowed =
  compile.status === 'valid' &&
  persistence === 'saved' &&
  conflict === null &&
  template.status !== 'missing';
```

- [ ] **Step 5: 实现 revision 面板与工作流 meta**

revision 面板显示 revision、hash 前 12 位、模板 ID/version、发布时间、来源、validation codes 和与当前版本的字段差异。回滚只调用 `revert` 创建 dirty 草稿。工作流第 6 步从项目页面记录汇总 revision/hash，传给 `PreviewWorkspace`；有多个页面时按页展示，不再只支持单个 meta。

后端 `ProjectVideoProps.pages[]` 增加只读 `effect_plan`、`effect_revision` 和 `effect_plan_hash`；`VideoPropsService` 只从已发布 `PageRecord.effect_plan` 填充。Remotion `ProjectVideo` 将每页 plan 传给现有 effect interpreter。未发布页面使用 SafeSlide，且不会读取作者态草稿。

- [ ] **Step 6: 运行前后端集成回归**

Run: `pnpm --filter @workbench/web test -- src/features/effect-editor src/features/workflow/WorkflowShell.effects.test.tsx src/features/video/PreviewWorkspace.test.tsx`

Expected: PASS。

Run: `uv run pytest tests/integration/test_effect_preview_revision_alignment.py tests/integration/test_video_preview_routes.py tests/integration/test_video_render_routes.py -q`

Expected: PASS。

- [ ] **Step 7: 提交批量与版本联动**

```bash
git add apps/web/src/features/effect-editor apps/web/src/features/workflow/WorkflowShell.tsx apps/web/src/features/video/PreviewWorkspace.tsx apps/web/src/features/workflow/WorkflowShell.effects.test.tsx apps/web/src/api/client.ts apps/api/src/workbench/video/models.py apps/api/src/workbench/video/props_service.py remotion/src/video/types.ts remotion/src/video/ProjectVideo.tsx tests/integration/test_effect_preview_revision_alignment.py
git commit -m "feat: add effect batch publishing and revision history"
```

---

### Task 13: 模板库列表、参数编辑、版本操作与包分发 UI

**Files:**

- Modify: `apps/web/src/features/template-library/TemplateLibrary.tsx`
- Modify: `apps/web/src/features/template-library/TemplateDetail.tsx`
- Create: `apps/web/src/features/template-library/TemplateParameterEditor.tsx`
- Create: `apps/web/src/features/template-library/TemplateValidationPanel.tsx`
- Create: `apps/web/src/features/template-library/TemplatePackageActions.tsx`
- Modify: `apps/web/src/app/styles.css`
- Test: `apps/web/src/features/template-library/TemplateLibrary.test.tsx`
- Test: `apps/web/src/features/template-library/TemplateDetail.test.tsx`
- Test: `apps/web/src/features/template-library/TemplatePackageActions.test.tsx`

**Interfaces:**

- Consumes: Task 9 template API。
- Produces: 模板搜索/筛选、详情页签、draft 参数编辑、校验/发布/弃用/归档/回滚和安全包导入导出。

- [ ] **Step 1: 写筛选、发布门禁与导入失败测试**

```typescript
it('hides deprecated and archived versions from the default recommendation view', async () => {
  render(<TemplateLibrary />);
  expect(await screen.findByText('科技蓝逐项揭示')).toBeVisible();
  expect(screen.queryByText('旧风险告警')).not.toBeInTheDocument();
});

it('shows the server remediation for an unsafe package', async () => {
  api.importTemplate = vi.fn().mockRejectedValue(new ApiRequestError('template_package_unsafe', '模板包包含禁止路径', '请重新导出数据模板包', 422));
  render(<TemplatePackageActions />);
  await userEvent.upload(screen.getByLabelText('导入模板包'), unsafeFile);
  expect(await screen.findByText('请重新导出数据模板包')).toBeVisible();
});
```

- [ ] **Step 2: 写已发布版本只读和回滚测试**

```typescript
it('keeps published fields read-only and creates a patch draft on rollback', async () => {
  render(<TemplateDetail templateId="progressive-reveal-blue" />);
  expect(await screen.findByLabelText('模板名称')).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: '回滚此版本' }));
  expect(api.rollbackTemplate).toHaveBeenCalledWith('progressive-reveal-blue', '1.2.0');
});
```

- [ ] **Step 3: 运行模板 UI 测试并确认失败**

Run: `pnpm --filter @workbench/web test -- src/features/template-library`

Expected: FAIL，详情、校验和包操作组件不存在。

- [ ] **Step 4: 实现列表和详情页签**

列表按模板产品聚合，显示最新版本、状态、renderer、画幅、标签、引用数和校验摘要；搜索在 1000 条本地索引上使用 memoized token filter。详情页签固定为“概览、参数、预设、预览、版本、校验、分发”。

```tsx
<TemplateTabs active={activeTab} onChange={setActiveTab}>
  <TemplateOverview />
  <TemplateParameterEditor disabled={version.status !== 'draft'} />
  <TemplatePresets disabled={version.status !== 'draft'} />
  <TemplatePreview />
  <TemplateVersions />
  <TemplateValidationPanel />
  <TemplatePackageActions />
</TemplateTabs>
```

- [ ] **Step 5: 实现状态操作和文件分发**

只有 draft 可编辑，validated 可退回 draft 或发布，published 可弃用，deprecated 可归档。每个危险状态操作显示影响和项目引用数。导入只接受 `.pvtmpl`；导出使用后端提供的下载 URL，不在浏览器重新打包。

- [ ] **Step 6: 运行模板 UI、类型和格式测试**

Run: `pnpm --filter @workbench/web test -- src/features/template-library`

Expected: PASS。

Run: `pnpm --filter @workbench/web typecheck`

Expected: PASS。

Run: `pnpm exec prettier --check apps/web/src/features/template-library apps/web/src/app/styles.css`

Expected: PASS。

- [ ] **Step 7: 提交模板库 UI**

```bash
git add apps/web/src/features/template-library apps/web/src/app/styles.css
git commit -m "feat: build local template management workbench"
```

---

### Task 14: 诊断、日志脱敏、故障注入与性能门禁

**Files:**

- Modify: `apps/api/src/workbench/diagnostics/package.py`
- Modify: `apps/api/src/workbench/diagnostics/redaction.py`
- Create: `apps/api/src/workbench/effects/diagnostics.py`
- Test: `tests/security/test_effect_diagnostic_redaction.py`
- Test: `tests/integration/test_effect_fault_injection.py`
- Test: `tests/performance/test_effect_editor_budgets.py`
- Test: `tests/performance/test_template_library_index.py`

**Interfaces:**

- Consumes: 编译诊断、revision snapshot、模板 manifest、registry capability、缓存事件。
- Produces: 脱敏 `EffectDiagnosticSnapshot`、诊断包条目和可自动执行的性能预算测试。

- [ ] **Step 1: 写自由文本和绝对路径脱敏测试**

```python
def test_effect_diagnostic_excludes_content_and_absolute_paths(tmp_path: Path) -> None:
    snapshot = build_effect_diagnostic(
        draft=draft_with_parameter("title", "机密课程内容"),
        error=RuntimeError(r"failed at F:\secret\source.png"),
    )
    encoded = snapshot.model_dump_json()
    assert "机密课程内容" not in encoded
    assert "F:\\secret" not in encoded
    assert snapshot.parameter_keys == ["title"]
```

- [ ] **Step 2: 写磁盘满、API 中断和 Remotion 错误恢复测试**

```python
def test_disk_full_during_publish_keeps_current_record(
    service: EffectAuthoringService, monkeypatch: pytest.MonkeyPatch, page_id: UUID
) -> None:
    before = service.current_record(page_id)
    monkeypatch.setattr(service.repository, "write_revision", raise_enospc)
    with pytest.raises(OSError):
        service.publish(page_id, expected_base_revision=before.revision, expected_draft_seq=4)
    assert service.current_record(page_id) == before
```

- [ ] **Step 3: 写性能预算测试**

```python
def test_template_index_filters_one_thousand_versions_under_budget(
    template_repository: TemplateRepository,
) -> None:
    seed_template_versions(template_repository, count=1000)
    started = time.perf_counter()
    result = template_repository.list(query="reveal", status="published")
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert result
    assert elapsed_ms <= 150
```

CI 在固定的 1000 条本地 fixture 上验证算法和单次预算；Windows 发布验收对每项运行 20 次、丢弃前 2 次预热样本后计算 P95：编辑器 1.5 s、参数预览 300 ms、草稿保存 500 ms、模板检索 150 ms、页面首帧 800 ms、50 页批量预检 2 s。

- [ ] **Step 4: 运行测试并确认缺少诊断模块**

Run: `uv run pytest tests/security/test_effect_diagnostic_redaction.py tests/integration/test_effect_fault_injection.py tests/performance/test_effect_editor_budgets.py tests/performance/test_template_library_index.py -q`

Expected: FAIL，缺少 effect diagnostics 与预算 fixture。

- [ ] **Step 5: 实现结构化脱敏诊断**

```python
class EffectDiagnosticSnapshot(BaseModel):
    project_id: UUID
    page_id: UUID
    template_id: str
    template_version: str
    renderer_key: str
    revision: int
    plan_hash_prefix: str
    frame: int | None
    aspect_ratio: str
    parameter_keys: list[str]
    validation_codes: list[str]
    error_type: str | None
```

诊断包只包含上述字段、模板 manifest、registry capability 和最近结构化事件；不包含参数值、素材正文、旁白全文、完整 hash、用户名或绝对路径。

- [ ] **Step 6: 运行安全、故障与性能套件**

Run: `uv run pytest tests/security/test_effect_diagnostic_redaction.py tests/integration/test_effect_fault_injection.py tests/performance/test_effect_editor_budgets.py tests/performance/test_template_library_index.py tests/security/test_diagnostic_bundle_redaction.py -q`

Expected: PASS。

- [ ] **Step 7: 提交诊断和门禁**

```bash
git add apps/api/src/workbench/diagnostics apps/api/src/workbench/effects/diagnostics.py tests/security/test_effect_diagnostic_redaction.py tests/integration/test_effect_fault_injection.py tests/performance/test_effect_editor_budgets.py tests/performance/test_template_library_index.py
git commit -m "feat: add effect diagnostics and performance gates"
```

---

### Task 15: E2E 验收、用户文档与发布总门禁

**Files:**

- Create: `tests/e2e/effects-workbench.spec.ts`
- Create: `tests/e2e/template-library.spec.ts`
- Create: `tests/e2e/helpers/effects.ts`
- Create: `tests/fixtures/templates/acceptance-import-1.0.0.pvtmpl`
- Create: `tests/acceptance/effects-template-workbench-plan.md`
- Modify: `docs/user-guide.md`
- Modify: `docs/troubleshooting.md`
- Modify: `docs/effect-template-catalog.md`
- Modify: `CHANGELOG.md`
- Test: `tests/docs/test_documentation_links.py`
- Test: `tests/acceptance/test_effects_template_workbench.py`

**Interfaces:**

- Consumes: 全部前后端功能。
- Produces: 设计文档第 21 节的可执行验收证据、用户操作文档和发布说明。

- [ ] **Step 1: 写编辑到渲染 E2E**

```typescript
test('edits, previews, publishes and renders one page with the same revision', async ({ page }) => {
  await openSeedProject(page, 'effects-acceptance');
  await page.getByRole('link', { name: '打开特效编辑器' }).click();
  await page.getByLabel('特效模板').selectOption('progressive-reveal-blue@1.0.0');
  await page.getByLabel('特效强度').fill('0.8');
  await expect(page.getByText('已保存')).toBeVisible();
  await page.getByRole('button', { name: '发布特效' }).click();
  const meta = await page.getByLabel('当前 EffectPlan 版本').textContent();
  await page.getByRole('link', { name: '返回效果预览' }).click();
  await expect(page.getByLabel('特效计划版本')).toContainText(meta ?? 'revision');
});
```

- [ ] **Step 2: 写模板生命周期与包恢复 E2E**

```typescript
test('publishes and exports an immutable template version', async ({ page }, testInfo) => {
  await page.goto('/templates');
  await createValidatedTemplate(page, 'acceptance-export', 'ProgressiveReveal');
  await page.getByRole('button', { name: '发布 1.0.0' }).click();
  const exportedPath = await captureTemplateDownload(page, testInfo);
  expect(exportedPath).toContain('acceptance-export-1.0.0.pvtmpl');
});

test('imports and lists an exact template package version', async ({ page }) => {
  await page.goto('/templates');
  await importTemplatePackage(page, fixturePath('acceptance-import-1.0.0.pvtmpl'));
  await expect(page.getByText('acceptance-import')).toBeVisible();
  await expect(page.getByText('1.0.0')).toBeVisible();
});
```

- [ ] **Step 3: 写验收矩阵测试**

```python
def test_acceptance_plan_covers_all_design_gates() -> None:
    text = Path("tests/acceptance/effects-template-workbench-plan.md").read_text(encoding="utf-8")
    required = {
        "双画幅",
        "reduced-motion",
        "恶意模板包",
        "多窗口冲突",
        "写盘中断",
        "revision/hash",
        "批量原子性",
    }
    assert required <= {item for item in required if item in text}
```

- [ ] **Step 4: 实现隔离 E2E helpers 并运行新 E2E**

```typescript
export async function captureTemplateDownload(page: Page, testInfo: TestInfo): Promise<string> {
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出模板包' }).click();
  const download = await downloadPromise;
  const target = testInfo.outputPath(download.suggestedFilename());
  await download.saveAs(target);
  return target;
}

export async function importTemplatePackage(page: Page, filePath: string): Promise<void> {
  await page.getByLabel('导入模板包').setInputFiles(filePath);
  await expect(page.getByText('模板包导入成功')).toBeVisible();
}

export function fixturePath(name: string): string {
  return path.resolve('tests', 'fixtures', 'templates', path.basename(name));
}
```

`openSeedProject` 只使用每个 Playwright worker 的隔离 workspace；`createValidatedTemplate` 明确填写最小有效 schema/defaults/bindings 并等待校验完成；`fixturePath` 只解析 `tests/fixtures/templates` 内的固定文件。全局 setup 每次运行前创建空白隔离 workspace，不复用开发者本地 `workspace-data`。

Run: `pnpm e2e -- tests/e2e/effects-workbench.spec.ts tests/e2e/template-library.spec.ts`

Expected: PASS，且失败重跑不依赖前一次残留模板库或项目草稿。

- [ ] **Step 5: 完成用户文档和故障指引**

`docs/user-guide.md` 增加编辑、自动保存、发布、批量应用、模板版本、导入导出和回滚步骤；`docs/troubleshooting.md` 增加 draft conflict、missing template、unsafe package、preview fallback、API disconnected、disk full 的错误码、原因和恢复动作；catalog 记录系统模板 ID、renderer key、payload kind、画幅、fallback 和版本。

- [ ] **Step 6: 运行完整质量门禁**

Run: `uv run pytest -q`

Expected: PASS。

Run: `uv run ruff check .`

Expected: PASS。

Run: `uv run mypy apps/api/src/workbench`

Expected: PASS with no issues。

Run: `pnpm check`

Expected: PASS。

Run: `pnpm e2e`

Expected: PASS。

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/effect-engine-windows-acceptance.ps1`

Expected: exit code 0，报告记录 16:9、9:16、reduced-motion、性能预算和 revision/hash 对齐证据。

- [ ] **Step 7: 提交验收与文档**

```bash
git add tests/e2e tests/acceptance docs/user-guide.md docs/troubleshooting.md docs/effect-template-catalog.md CHANGELOG.md
git commit -m "docs: add effect workbench acceptance and user guidance"
```

---

## 最终完成定义

- [ ] Task 1–15 的独立测试和提交均完成。
- [ ] 设计文档第 21 节的 14 条验收标准均能映射到自动化测试或 Windows 验收证据。
- [ ] 当前项目的已发布 EffectPlan 在迁移前后 plan hash 与渲染结果不发生非预期变化。
- [ ] 所有系统模板和新发布模板通过双画幅、reduced-motion、目标帧与性能门禁。
- [ ] 草稿无效、API 断线、并发冲突、Remotion 异常、模板缺失、磁盘满和写盘中断均有验证过的恢复路径。
- [ ] `.pvtmpl` 安全测试覆盖路径穿越、符号链接、压缩炸弹、恶意 SVG、未知 renderer、代码文件和资源上限。
- [ ] `uv run pytest -q`、`uv run ruff check .`、Mypy strict、`pnpm check`、`pnpm e2e` 和 Windows 特效验收脚本全部通过。
- [ ] 用户指南、故障排查、模板目录和 CHANGELOG 已更新。

## 推荐执行顺序与评审门

1. Task 1–3：契约与编译器评审门。确认作者态、模板 manifest 和双端编译完全一致。
2. Task 4–7：持久化与 API 评审门。重点审查原子性、不可变性、安全路径和错误码。
3. Task 8–10：Remotion 与前端基础评审门。重点审查 renderer 能力、状态边界和断线恢复。
4. Task 11–13：产品工作流评审门。完成可用的编辑器、批量发布与模板库。
5. Task 14–15：质量和发布评审门。完成安全、性能、故障注入、E2E 与文档。
