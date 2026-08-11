# 参考视频特效、节奏与表现形式引擎实施记录

## 2026-08-10

### E00 — EffectPlan V2 与 V1 兼容

- 变更：新增 `effects/schema.py`、`effects/__init__.py`、`schemas/effect-plan-v2.schema.json`、`remotion/src/types.ts` 和 `remotion/src/effects/effectPlanSchema.ts`。
- 测试：`.venv\Scripts\python.exe -m pytest tests/contract/test_effect_plan_v2.py -v` → `2 passed`（现有 `.pytest_cache` 权限警告）。
- 测试：`pnpm --dir remotion test -- effectPlanSchema` → `2 passed`。
- 类型检查：`pnpm --dir remotion typecheck` → 通过。

### E07 — 自动模板决策与强度策略

- 变更：新增 `effects/template_catalog.py`、`effects/decision.py` 和 `tests/fixtures/effects/decision-cases.json`。
- 测试：`.venv\Scripts\python.exe -m pytest tests/unit/effects/test_decision.py -v` → `3 passed`（现有 `.pytest_cache` 权限警告）。
- 覆盖：指标、图表、对比、地图、密集文本五类推荐；密集文本使用 `restrained`；`manual_lock` 优先。

### E05 — 对比、风险、路径和标签模板

- 变更：新增 `CompareMode.tsx`、`RiskAlert.tsx`、`PathBuilder.tsx` 和 `TagMatrix.tsx`。
- 测试：`pnpm --dir remotion test -- semanticTemplates` → `4 passed`。
- 约束：风险只产生一个脉冲，模板不输出旋转、弹跳或无限循环。

### E06 — 卡片堆叠、地图点亮和语义背景

- 变更：新增 `effects/backgrounds.py`、`SemanticBackground.tsx`、`CardStack.tsx` 和 `MapHighlight.tsx`。
- 测试：`.venv\Scripts\python.exe -m pytest tests/unit/effects/test_background_policy.py -v` → `6 passed`（现有 `.pytest_cache` 权限警告）。
- 测试：`pnpm --dir remotion test -- SemanticBackground` → `2 passed`。
- 类型检查：`pnpm --dir remotion typecheck` → 通过。

### E03 — 章节幕与内容速览

- 变更：新增 `ChapterCurtain.tsx`、`NarrativePreview.tsx` 和 `tests/visual/effects/chapter-curtain.json`。
- 测试：`pnpm --dir remotion test -- ChapterCurtain` → `4 passed`。
- 类型检查：`pnpm --dir remotion typecheck` → 通过。
- 视觉基线 JSON 解析 → 通过；参考视频元数据来自用户提供的本地 MP4。

### E04 — 数据计数、比例环和图表叙事

- 变更：新增 `StatCounter.tsx`、`GaugeAndRatio.tsx`、`ChartNarration.tsx` 和 `effects/chart.py`。
- 测试：`pnpm --dir remotion test -- dataTemplates` → `4 passed`。
- 测试：`.venv\Scripts\python.exe -m pytest tests/integration/test_chart_render.py -v` → `2 passed`（现有 `.pytest_cache` 权限警告）。
- 类型检查：`pnpm --dir remotion typecheck` → 通过。
- 兼容修正：`pyproject.toml` 将根目录加入 Python path，避免根级效果包与现有 API 效果包导入歧义。
- Git：根目录 `.git` 指向失效临时工作树，未执行 commit、reset、checkout 或初始化。

### E01 — 节奏计算器与页面五段式

- 变更：新增 `effects/rhythm.py`，提供页面五段式、整数毫秒、提示点裁剪、短页面装饰降级和人工锁定保留。
- 测试：`.venv\Scripts\python.exe -m pytest tests/unit/effects/test_rhythm.py -v` → `4 passed`（现有 `.pytest_cache` 权限警告）。

### E02 — 基础模板注册表和确定性解释器

- 变更：新增 `remotion/src/effects/registry.ts`、`interpreter.tsx`、`SafeSlide.tsx`、`ProgressiveReveal.tsx`、`FocusSpotlight.tsx`。
- 测试：`pnpm --dir remotion test -- interpreter` → `3 passed`。
- 回归测试：`pnpm --dir remotion test` → `4 files / 10 tests passed`。
- 类型检查：`pnpm --dir remotion typecheck` → 通过。

### E08 - 16:9 / 9:16 layout and safety zones

- Changes: added `remotion/src/effects/layout/aspectLayout.ts` for both aspect ratios, caption safe zones, presenter PiP, and content occupancy.
- Test: `pnpm --dir remotion test -- aspectLayout` -> `2 passed`.
- Typecheck: `pnpm --dir remotion typecheck` -> passed.

### E09 - pre-render validation, fallback, and dependency invalidation

- Changes: added `effects/validator.py`, `effects/fallback.py`, and `cache/dependency_graph.py`; covers dual cameras, caption overlap, cues before speech, long transitions, infinite loops, and manual-lock preservation.
- Test: `.venv\\Scripts\\python.exe -m pytest tests/unit/effects/test_validator.py tests/unit/cache/test_effect_invalidation.py -v` -> `7 passed`.
- Note: pytest still reports the pre-existing `.pytest_cache` permission warning; it does not affect results.

### E10 - effect controls and full preview

- Changes: added `apps/web/src/features/effects/RhythmPanel.tsx`, `TemplatePanel.tsx`, and `BatchEffectStatus.tsx`; `PreviewWorkspace` now accepts optional EffectPlan revision/hash metadata and control content.
- Tests: `pnpm --dir apps/web test -- EffectControls PreviewWorkspace` -> `7 passed`; `pnpm --dir apps/web test` -> `25 files / 42 tests passed`; `pnpm --dir apps/web typecheck` -> passed.
- Compatibility fix: non-JSON HTTP errors now produce a readable `ApiRequestError` instead of leaking JSON parse errors; `client.error.test.ts` passes.

### E11 - visual regression, batch recovery, and presenter collision

- Changes: added 40-page manifest (`tests/fixtures/effects/manifest.json`), structural visual regression runner, `effects/batch.py`, `effects/presenter.py`, and integration tests.
- Tests: `.venv\\Scripts\\python.exe -m pytest tests/integration/test_effect_batch_recovery.py tests/integration/test_presenter_effect_collision.py -v` -> `3 passed`.
- Visual manifest: `.venv\\Scripts\\python.exe tests/visual/effects/run_visual_regression.py` -> `40 pages`, `10 categories`, no structural errors.
- Gate note: existing `scripts/check.ps1` could not start `uv.exe` in the sandbox; elevated retry stalled at `uv sync --frozen` and was terminated. No visual screenshots or Windows acceptance evidence were fabricated.

### E12 - Windows acceptance preparation (manual gate pending)

- Changes: added `scripts/effect-engine-windows-acceptance.ps1`, `tests/acceptance/effect-engine-plan.md`, `docs/effect-engine-acceptance-report-RC1.md`, and `docs/effect-template-catalog.md`; updated `CHANGELOG.md`.
- Preparation check: `powershell -ExecutionPolicy Bypass -File scripts/effect-engine-windows-acceptance.ps1 -PlanOnly` passed and confirmed the supplied reference video exists.
- Safety: the script performs no installation, GUI automation, protected-path writes, or acceptance claim unless a human executes and records the manual checklist.

### E12 - isolated Windows acceptance evidence (partial)

- Temporary workspace: `F:\ppt-video-workbench-v3\\.tmp\\workspace-acceptance`; copied project data and generated a separate `workspace.db`, cache, logs, and output directory.
- Real browser evidence: isolated Edge preview/preflight passed; step 7 render-ready UI reached; start/middle/end MP4 frames extracted and visually inspected.
- Output: 1920x1080, 30 fps, 8:02.74 H.264/AAC MP4 plus SRT. SHA-256 values are recorded in `docs/effect-engine-acceptance-report-RC1.md`.
- Boundary: original `F:\\Video\\workspace.db` and `F:\\app\\app` were not used for writes. Installer/antivirus/manual release sign-off remain pending.

### E12 - isolated installer and installed-runtime smoke evidence

- Installer package hash: `release/ppt-video-workbench-setup.exe` SHA-256 `BA588D7675A767B025C3783E3922153D0F223CA8C372B2C0E269FABAA8E68284`.
- A non-elevated isolated install was attempted first and rolled back with exit code 4 because the runner denied the HKCU uninstall key (`RegCreateKeyEx code 5`) and desktop shortcut creation (`IPersistFile::Save code 0x80070005`). No formal acceptance was inferred from that attempt.
- A second attempt with controlled elevated permission succeeded (exit code 0) into `F:\\ppt-video-workbench-v3\\.tmp\\installed-acceptance-elevated`; no writes were made to `F:\\app\\app` or `F:\\Video\\workspace.db`.
- Installed-runtime smoke check passed: `release/api/workbench.exe` SHA-256 `69E8FBD0F095BA799E660ABA9E29EA5F8B0570C7A49B26846B205F5C78050B62`; Web root HTTP 200; API `http://127.0.0.1:29999/api/health` HTTP 200/status `ok`; temporary project recovered at step 7; video preflight HTTP 200 with `allowed=true` and no issues.
- `Get-MpComputerStatus` was attempted read-only and returned Access Denied. Antivirus and human operator sign-off remain explicitly pending; no evidence was fabricated.

### HeyGen 配音界面 - 配置加载状态修复

- 根因：`HeyGenAudioPanel` 在配置请求尚未完成或失败时直接用空数组渲染“尚未保存配置”，同时禁用配置下拉框；已有配置并未丢失，原 API 在 `27268` 返回 6 个配置。
- 修复：增加配置/音色加载状态、失败提示和重试入口；加载期间显示明确状态，不再误报未配置；音色请求期间禁用生成和试听按钮。
- 回归测试：`pnpm --dir apps/web test -- HeyGenAudioPanel` -> `3 passed`；全量 Web 测试 `25 files / 43 tests passed`；`pnpm --dir apps/web typecheck` 和生产构建均通过。
- 临时浏览器复现：复制配置到 `.tmp\\workspace-acceptance` 后，配置下拉框可显示 6 个选项；原始项目和安装目录未写入。
- 真实配置接口核对：`Video` 配置可返回 2 个音色；旧配置 `222` 返回 HTTP 422，因此使用时应选择 `Video`，界面不会把失效密钥误显示为可用音色。

### HeyGen 配音界面 - DPAPI 解密失败提示修复

- 根因：临时运行上下文无法解密由其他 Windows 用户保护的 HeyGen API Key，异常此前未被路由捕获，前端只能显示 HTTP 500。
- 修复：`heygen_settings.py` 捕获 `SecretStoreUnavailable`，返回 422 结构化错误 `heygen_secret_store_unavailable`，并提示“请在当前 Windows 用户下重新保存 HeyGen API Key”；语音列表和试听接口均覆盖。
- 测试：`.venv\\Scripts\\python.exe -m pytest tests/integration/test_heygen_retry.py -k secret_store_failure -q` -> `1 passed`；完整 `test_heygen_retry.py` -> `13 passed`。
- 说明：这不会伪造 HeyGen 成功。若当前用户没有可解密的密钥，界面会明确要求重新保存；原始 `F:\\app\\app` 和 `F:\\Video\\workspace.db` 未修改。
