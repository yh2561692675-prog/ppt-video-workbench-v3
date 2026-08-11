# Windows 全流程实机执行报告（2026-08-11）

## 结论

“安装 → 启动 → 导入 PPT → 配音 → 单页/批量渲染 → 失败恢复 → 最终合成 → 重启恢复 → 卸载/回滚”的工程全流程已完成。

- 最终正式安装包候选：`rc-d8848a2-20260811T095432Z`
- 安装包：`release/ppt-video-workbench-setup.exe`
- 安装包大小：`273875909` 字节
- 安装包 SHA-256：`656c527d7cd6be327f0612ace108c173c24c94e65214c3e150bb603028dadd0c`
- payload manifest SHA-256：`408981c49ada7a23b7513edd1021416e327253bee1951f28f5ac16f8c411c205`
- 最终视频 SHA-256：`613bb98836f24e99a4243ad20297850d65e9410c5e74a197fc0fe6681ff0bc34`
- 发布产物独立复核：`RELEASE_ARTIFACTS_VERIFY=PASS`

## 执行矩阵

| 环节             | 结果 | 核心证据                                                                                                       |
| ---------------- | ---- | -------------------------------------------------------------------------------------------------------------- |
| 安装包发现与校验 | 通过 | `release-artifacts.json` 精确解析安装包；size/hash 二次复核通过                                                |
| 全新安装         | 通过 | 最终候选安装日志记录 `Installation process succeeded`；launcher/uninstaller 均落盘                             |
| 首次启动         | 通过 | 无控制台 launcher 启动；`/api/health` 返回 200；实例版本 `0.1.0`                                               |
| 导入 PPT/提纲    | 通过 | 真实 4 页 PPTX 与 DOCX 导入，解析得到 4 页、4 个匹配                                                           |
| 旧项目兼容       | 通过 | 中文路径旧项目在打包运行时中成功重新解析；4 页、4 匹配                                                         |
| 配音             | 通过 | 4 页旁白修订均确认；16 秒 WAV 导入并标准化为 16 kHz；生成 4 个字幕 cue                                         |
| 完整预检         | 通过 | 视频预检与完整预检均 `allowed=true`、0 issue                                                                   |
| 单页渲染         | 通过 | 第 1 页 MP4：745476 字节，SHA-256 `ddf98f035d50bd643e33fe8a8056b509221cf09206f751595971988a9928a16c`           |
| 批量渲染         | 通过 | 4 页全部完成，最终任务 `82b90b25-f563-4005-bc0e-c7b6055abcb5` 为 `succeeded / 100%`                            |
| 失败恢复         | 通过 | API 在渲染中断；重启后任务恢复为 `paused`、错误码 `render_worker_interrupted`、进度 35%；正式 retry 子任务成功 |
| 最终合成         | 通过 | H.264 1920×1080、AAC、16.063997 秒、480 帧；FFmpeg 从 0 到结尾完整解码，退出码 0                               |
| 从头播放         | 通过 | Edge CDP 实际播放：`currentTime 0 → 16.063997`、`ended=true`、`readyState=4`、0 media error、0 JS exception    |
| 重启恢复         | 通过 | 重启后项目可查询，成功任务仍为 `succeeded / 100%`，最终视频路径仍存在                                          |
| 版本回滚         | 通过 | 激活隔离坏槽 `0.1.1-bad` 后两次启动失败，自动回滚：active=`0.1.0`、previous=`0.1.1-bad`、健康检查通过          |
| 关闭清理         | 通过 | 修复后 `shutdown --wait` 在 6.185 秒内清除 API PID、supervisor PID 和 `instance.json`                          |
| 卸载/重装        | 通过 | 旧候选卸载后工作区保留；最终候选重装并复开成功；最终卸载日志为 `Uninstallation process succeeded`              |
| 工作区保留       | 通过 | 最终安装目录不存在；外置工作区和 1,625,250 字节最终视频仍存在                                                  |

## 实机过程中发现并修复的问题

1. Windows 字体预检只依赖 `fc-match`，导致已安装中文字体仍被误判缺失。现已增加 Windows 字体注册表检测。
2. LibreOffice 使用中文源/输出路径时崩溃或超时。现改为 ASCII 临时输入、profile 和输出目录，完成后再复制回目标路径。
3. 打包 launcher 的 `shutdown --wait` 在 Windows 使用 POSIX 风格 `os.kill(SIGTERM)`，API 与 supervisor 无法可靠退出。现改为 Win32 `OpenProcess`、`TerminateProcess`、`WaitForSingleObject`，并同时清理旧 supervisor。
4. 中断后的原任务耗尽最大尝试次数。使用产品正式 `retry` 动作创建带 `parent_job_id` 的子任务，完整渲染成功，父子审计关系保留。

## 验证命令结果

- Web：43 个测试文件、84 个测试项通过。
- Remotion：12 个测试文件、32 个测试项通过。
- 启动器、桌面、Office 路径针对性回归：12 个测试通过。
- Ruff：涉及启动器、Office renderer、验收脚本和测试的检查全部通过。
- 完整发布构建：退出码 0，耗时 828.2 秒。
- 最终发布清单复核：通过。

## 边界说明

- 打包环境未预置离线 ASR 模型，生产 ASR 接口按设计返回 `audio_transcription_rejected`。本次对已知测试音频使用验收专用 transcript 注入器，随后差异检查为 0；这不是对生产 ASR 模型下载/推理能力的替代证明。
- 业务链在候选 `rc-d8848a2-20260811T083238Z` 上完成；实机发现并修复 launcher 关闭缺陷后，重新构建为最终候选 `rc-d8848a2-20260811T095432Z`，并完成最终候选的安装、启动、旧工作区/成功任务恢复、关闭和卸载。因此本报告证明工程全流程与最终安装包回归通过，但不伪装成“同一 candidate_id 的一次性发布冻结签署”。
- 如要执行正式发布冻结，仍应在批准的验收机上对最终 candidate_id 重新生成 schema 2.0 单次连续证据包，并使用真实可用的 ASR 配置。
