# M3 旁白工作台阶段验收

验收日期：2026-08-03  
验收分支：`feature/m3-narration-workbench`

## 范围

- Task 11：OpenAI-Compatible 配置、DPAPI 凭证保护边界、连接测试和错误脱敏。
- Task 12：仅使用当前页与匹配大纲的结构化旁白生成、来源/数字校验和一次 JSON 修复。
- Task 13：不可变旁白版本、乐观并发、编辑、撤销式恢复和网页编辑器。
- Task 14：单页/批量确认、冲突处理说明、不可变审计与后端音频门禁。
- Task 15：固定路径的旁白确认版 DOCX、输出副本和 LibreOffice 渲染验证。

## 自动化证据

| 验收项         | 结果         | 证据                                            |
| -------------- | ------------ | ----------------------------------------------- |
| Python 测试    | 101/101 通过 | `uv run pytest`，包含 M1—M3 全量回归            |
| 前端组件测试   | 9/9 通过     | Vitest 覆盖设置、生成、版本、确认和既有工作流   |
| 浏览器生命周期 | 1/1 通过     | Playwright 创建、重开、刷新、暂停/继续          |
| 静态检查       | 通过         | Ruff、mypy strict、ESLint、Prettier、TypeScript |
| 生产构建       | 通过         | Vite 与 Remotion 构建                           |
| 契约漂移       | 通过         | `project.schema.json` 与类型化 OpenAPI 快照     |

## 8 页阶段场景

`tests/integration/test_m3_gate.py` 使用确定性 OpenAI-Compatible fake transport 完整验证：

1. 建立 8 页课件文本和 8 个匹配大纲。
2. 逐页调用生成 API；每次提示只包含当前页和当前匹配大纲。
3. 人工修改第 3 页，再恢复到历史版本；恢复生成新的不可变 revision。
4. 批量确认 8 个当前 revision；后端音频门禁放行。
5. 导出 `04_旁白/旁白确认版.docx`，并核对 8 页标题顺序。
6. 修改任意已确认页；该页确认立即失效，音频门禁重新锁定。
7. 项目仅记录 profile ID、Base URL 摘要、模型和使用时间，测试密钥不进入项目清单。

批量确认另有原子性回归：任意一页 revision 无效时，整批不产生确认或审计写入。

## DOCX 结构与视觉验证

- 8 页按 `order` 输出；封面、页面标题、缩略图/缺图占位、确认旁白、字数、预计时长和确认时间齐全。
- 重复导出覆盖固定文件，不产生编号副本；`08_输出/旁白确认版.docx` 与权威文件一致。
- 中文样式使用 Noto CJK 字体；7 张缩略图和 1 个缺图占位均通过结构检查。
- 长段落 fixture 经 LibreOffice 转为 PDF；所有渲染页均非空，长文本未截断，8 个标题顺序正确。
- 已逐页检查渲染 PNG；封面、普通页、长段落续页和缺图占位均无裁切或页脚重叠。

## 安全与环境说明

- 日志、API 响应、项目 JSON 和设置 JSON 的测试密钥明文扫描为零命中。
- Linux 自动化使用可注入的确定性凭证保护器验证存储边界；真实 Windows DPAPI 仍需 Windows 实机补充验收。
- 旁白生成使用离线 fake transport 验证 OpenAI-Compatible 合同和材料约束；真实服务商连通性由设置页按用户配置单独测试。
- LibreOffice/PDF 渲染已在当前 Linux 环境验证；Windows Word 字体与分页一致性留作安装包阶段实机回归。
