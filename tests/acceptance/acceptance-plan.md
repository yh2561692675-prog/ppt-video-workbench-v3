# M8 RC 验收计划

## 执行规则

每个验收用例必须填写前置条件、步骤、期望、结果、证据路径和环境。`automated_linux` 表示当前容器可复现；`manual_windows` 表示必须在 Windows 10/11 干净 VM 或目标用户机器执行；`manual_real_service` 表示需要受控真实接口和明确额度，不在本容器自动触发。

## 用例索引

| ID         | 场景                                       | 环境                                  | 证据                                                 |
| ---------- | ------------------------------------------ | ------------------------------------- | ---------------------------------------------------- |
| AC-001     | 创建、关闭、重开和恢复项目                 | automated_linux + manual_windows      | `tests/e2e/project-lifecycle.spec.ts`                |
| AC-002     | Word/PPTX/PDF/音频安全导入                 | automated_linux                       | `tests/integration/test_material_import.py`          |
| AC-003     | 搜索/扫描 PDF 与图片解析                   | automated_linux + manual_windows      | `tests/integration/test_image_pipeline.py`           |
| AC-004     | 自动匹配与人工修正                         | automated_linux                       | `tests/integration/test_matching_api.py`             |
| AC-005/006 | 旁白生成、编辑、版本、确认                 | automated_linux + manual_windows      | `tests/integration/test_narration_generation_api.py` |
| AC-007     | Fake HeyGen、真实 2 页声音                 | automated_linux + manual_real_service | `tests/integration/test_heygen_retry.py`             |
| AC-008     | 本地录音转写、差异、分页                   | automated_linux + manual_windows      | `tests/integration/test_m4_tasks_16_20_gate.py`      |
| AC-009/010 | 字幕、预览、Remotion 渲染                  | automated_linux                       | `tests/integration/test_m5_gate.py`                  |
| AC-011/012 | 预检、暂停、恢复、局部重做                 | automated_linux + manual_windows      | `tests/integration/test_preflight_routes.py`         |
| AC-013     | 完整制作包                                 | automated_linux + manual_windows      | `M5-GATE.md`                                         |
| AC-014/015 | 安装、启动、更新、回滚                     | automated_linux + manual_windows      | `M7-GATE.md`                                         |
| AC-016     | 多图片自然排序和人工调整                   | automated_linux + manual_windows      | `tests/integration/test_material_import.py`          |
| AC-017—023 | 易用性、可靠性、安全、追溯、兼容和输出质量 | automated_linux + manual_windows      | `tests/acceptance/fixtures-manifest.json`            |

机器可检索的验收 ID：`AC-001`、`AC-002`、`AC-003`、`AC-004`、`AC-005`、`AC-006`、`AC-007`、`AC-008`、`AC-009`、`AC-010`、`AC-011`、`AC-012`、`AC-013`、`AC-014`、`AC-015`、`AC-016`、`AC-017`、`AC-018`、`AC-019`、`AC-020`、`AC-021`、`AC-022`、`AC-023`。

## 真实项目步骤

1. Windows 干净 VM 安装 RC，不打开命令行；确认快捷方式、中文用户名和工作区位置。
2. 导入真实 Word+PPTX，完成本地录音路线；记录 MP4、SRT、旁白 DOCX、分页音频、Remotion 工程、配置、预检报告、日志和清单。
3. 导入 Word+扫描 PDF，定位 OCR 低置信度并人工修正；再导入 Word+多图片，确认自然排序与拖拽排序。
4. 选 2 页在受控额度下执行真实声音路线，记录请求、缓存和费用证据；失败页不得重复计费。
5. 在 OCR、转写、真实声音和渲染阶段各暂停/关闭一次，重新启动后确认断点恢复和局部重做。
6. 修改一页旁白，确认只重做受影响页面；检查字幕同步、画面裁切、爆音、静音、错页和核心内容。
7. 卸载并确认项目、设置、日志和最终制作包留存；按 [RC1 报告](../docs/acceptance-report-RC1.md) 填写结果。

## 签署门槛

P0=0、P1=0；P2 每项有处置；所有必需产物存在；追踪矩阵无空缺；自动化和实机证据可回溯。任意一项未完成，状态保持 `pending_manual_windows`，不得打 V1.0 tag。
