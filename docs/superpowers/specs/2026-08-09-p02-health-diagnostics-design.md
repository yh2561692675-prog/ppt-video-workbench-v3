# P02 一键健康检查与日志诊断中心设计

**版本：** V1.0  
**日期：** 2026-08-09  
**前置门禁：** `P01_WINDOWS_ACCEPTANCE=PASS`

## 1. 目标

在不改变 PPT、配音、HeyGen、Remotion 和视频导出主流程的前提下，提供一个可从主界面或 PowerShell 一键运行的健康诊断中心。用户必须能看到“哪里异常、影响什么、怎样处理”，并能导出默认脱敏的诊断包。

P02 的发布门禁为：20 个已知故障注入用例至少识别 19 个；诊断包不包含 API Key、Bearer Token、Cookie、请求正文、Windows 用户名或完整本机路径；任何单项检查或整个诊断中心异常都不得阻断主程序启动和原有视频流程。

## 2. 方案选择

采用“扩展现有环境检查器”的增量方案。诊断领域模型、检查编排、脱敏与打包拆成独立文件；现有 `/api/environment` 保持兼容，新建 `/api/diagnostics` 只读接口和前端页面。外围主控不可用时，P02 仍能完成本机基础诊断；HeyGen 等外部探测失败只形成结构化检查结果，不向主程序启动路径抛出异常。

不采用以下方案：

- 不新建常驻 Windows 服务，避免增加 P01 已验收安装链的进程与权限风险；
- 不在诊断时自动修复或删除文件，所有修复动作仅提供安全说明；
- 不读取、回显或打包密钥明文，不改变 `F:\Video` 目录和缓存策略；
- 不修改本地录音与 HeyGen 的独立音频路线规则。

## 3. 组件边界

| 组件                    | 责任                                                                     | 失败行为                                     |
| ----------------------- | ------------------------------------------------------------------------ | -------------------------------------------- |
| `diagnostics.models`    | 状态、分类、证据、报告和包清单                                           | 只做严格数据校验                             |
| `diagnostics.probes`    | 安装、运行时、磁盘、权限、端口、SQLite、配置、HeyGen、临时目录和编码探测 | 返回受控探测结果，不写用户产物               |
| `diagnostics.center`    | 隔离执行每个检查、汇总红黄绿状态                                         | 单项崩溃转换为 `INTERNAL` 红项，继续其他检查 |
| `diagnostics.redaction` | 对键名、文本、路径和用户名脱敏                                           | 无法安全处理的文件不进入包                   |
| `diagnostics.package`   | 原子生成 JSON、Markdown、日志摘录和 manifest                             | 失败只影响导出，不影响运行报告               |
| `/api/diagnostics`      | 运行检查、读取最近结果、生成诊断包                                       | 返回结构化降级报告，不传播未处理异常         |
| `DiagnosticCenter.tsx`  | 一键运行、分组展示、导出包                                               | API 失败显示降级提示，项目制作入口仍可用     |

## 4. 检查项与判定

诊断中心固定输出 13 组检查：

1. `installation_manifest`：发布清单、Web、API、运行时关键文件；
2. `python_runtime`：Python DLL 与 VC++ 运行库；
3. `ffmpeg_runtime`：FFmpeg/FFprobe 可执行性与版本；
4. `disk_space`：大于等于 5 GiB 为绿，1—5 GiB 为黄，低于 1 GiB 为红；
5. `workspace_permissions`：在工作区执行创建、刷新、原子替换和删除；
6. `loopback_port`：仅探测 `127.0.0.1` 本地端口可绑定性；
7. `database_integrity`：已存在 SQLite 库执行 `PRAGMA quick_check`；
8. `configuration`：工作区、运行时根和端点引用合法且一致；
9. `heygen_connectivity`：有启用配置时探测供应商连通性；
10. `heygen_voices`：声音列表可读取且不为空；
11. `secret_references`：仅检查密钥引用是否存在，不读取明文；
12. `temporary_directory`：临时目录创建、写入和清理；
13. `video_encoder`：FFmpeg 可识别 H.264 编码器。

每项状态为 `green`、`yellow` 或 `red`。总体状态取最严重值。每项必须包含错误分类、稳定错误码、用户说明、影响、修复建议和脱敏证据。

## 5. 错误分类

只允许使用统一十类：`ENVIRONMENT`、`CONFIGURATION`、`AUTHENTICATION`、`NETWORK`、`PROVIDER`、`INPUT`、`PROCESSING`、`STORAGE`、`QA`、`INTERNAL`。外部 401/403 归入 `AUTHENTICATION`，429/5xx 归入 `PROVIDER`，连接和 DNS 错误归入 `NETWORK`，编码器缺失归入 `PROCESSING`。

## 6. 诊断包安全

诊断包只允许包含：`diagnostic-report.json`、`diagnostic-report.md`、`manifest.json`、`README.txt` 和经过脱敏、限长、白名单筛选的日志摘录。包内文件均记录大小和 SHA-256。

脱敏规则：

- 键名命中 `key`、`token`、`secret`、`authorization`、`cookie`、`password` 时值替换为 `***`；
- Bearer、API Key、JWT 和常见查询令牌替换为 `***`；
- Windows 用户目录折叠为 `%USERPROFILE%`，工作区根折叠为 `%WORKBENCH_WORKSPACE%`；
- 不收集请求正文、PPT 内容、旁白正文、音频或视频文件；
- 每个日志最多保留末尾 256 KiB，诊断包总日志预算 2 MiB。

## 7. 非阻断与兼容

`create_app()` 不等待诊断检查，也不在启动时访问 HeyGen。路由创建失败时安装一个不可用诊断中心，主程序仍返回 `/api/health = 200`。现有 `/api/environment` 和 `doctor.ps1` 保留，新脚本优先调用 P02 接口，旧版 API 不支持时回退到环境接口。

## 8. 测试与验收

- 单元测试覆盖状态汇总、异常隔离、分类和脱敏；
- 集成测试覆盖三个 API、报告持久化和诊断包内容；
- 20 个故障注入样例计算识别率，要求至少 95%；
- 安全测试向配置与日志注入假密钥、Cookie、JWT、用户名和路径，压缩包全文不得出现原值；
- 前端测试覆盖一键运行、红黄绿分组、修复建议和导出入口；
- 回归测试必须保留 P01 V11、HeyGen R23、`F:\Video` 和原有视频流程。

## 9. 自检

本设计没有自动修复、外网监听、密钥明文、数据删除、音频路线合并或供应商重复提交。所有检查可单独失败并被转换为结构化结果；范围与 P02 门禁一一对应，没有待定项。
