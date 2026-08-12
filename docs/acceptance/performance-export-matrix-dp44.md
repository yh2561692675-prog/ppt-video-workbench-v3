# DP44 导出规格与合成图谱验收

DP44 在候选 `7454d21a610148128ca278fc68054584e2c6ce70` 上完成。本验收将原有页面导出
链路和 RenderGraph 全片链路拆开执行，避免把 SRT 旁产物或纯契约测试误报为最终媒体能力。

## 候选与不可变证据

- 候选：`v1-rc-7454d21a6101-20260812T191907Z`
- 候选清单 SHA-256：`05064d8ecb370617c94e6a91ba1a25062c6dcd5f583235314e176cb7bbecfd07`
- 页面规格矩阵：`test-results/export-matrix/c-05064d8ecb37/r-matrix-20260813T032054Z-1a16dffb/output-matrix-acceptance-v1.json`
- 页面规格矩阵 SHA-256：`3e224b95ec7fb3a97a91d547c7563ed466b91064634872aa73b095b4b5a28904`
- 图谱媒体矩阵：`test-results/render-graph-matrix/c-05064d8ecb37/r-graph-20260813T031911Z-e7a98d42/render-graph-matrix-acceptance-v1.json`
- 图谱媒体矩阵 SHA-256：`9fafa70915dcd4204651bd63ed88706ea8cfd71be8a4d022a4459e9aba354f6e`

两份 JSON 均为候选专属、不可覆盖的 `test-results` 证据。每份都记录相同的候选提交和
候选清单摘要；不依赖用户项目、外部 Provider 或云端服务。

## 已实际执行

页面导出矩阵通过产品 `VideoExportService`、真实 FFmpeg mux 和最终媒体探测，五项均通过：

| 画幅 | 分辨率 | 帧率 | 最终媒体 |
| --- | --- | ---: | --- |
| 16:9 | 1280×720 | 24 | H.264 + AAC |
| 16:9 | 1280×720 | 25 | H.264 + AAC |
| 16:9 | 1920×1080 | 30 | H.264 + AAC |
| 9:16 | 1080×1920 | 60 | H.264 + AAC |
| 1:1 | 1080×1080 | 30 | H.264 + AAC |

每项同时验证冻结的 `render.config.json`、SRT、实际宽高、帧率、时长和编解码器。

图谱媒体矩阵通过打包的 Node/Remotion、Microsoft Edge 与打包 FFmpeg/FFprobe 实际渲染
2 秒成片。它验证：两张图片叠化、定时文字覆盖层、逐词烧录字幕、ASS/SRT/VTT 字幕包及
最终 MP4 的 `mov_text` 软字幕轨，以及两路 WAV 的 FFmpeg 混音。最终媒体拥有视频、AAC
音频和字幕三类流；与无这些效果的基线帧比较，0.5 秒的烧录字幕/覆盖层差异为 `5224884`
像素强度单位，1.0 秒的转场差异为 `674675`。

## 入队保护

- 允许的 V1 画布限于已验证的 720p/1080p 组合和 4K 16:9，帧率限于 24/25/30/60。
- 4K 必须同时满足 `WORKBENCH_EXPORT_4K_ENABLED` 与启动器确认的
  `WORKBENCH_EXPORT_4K_HARDWARE_READY`；本候选未开启，未声称已执行 4K。
- GIF 虽可在预设目录中展示，但 V1 任务会在入队前以
  `export_container_not_supported` 明确阻断；本候选未声称 GIF 可执行。
- Windows 矩阵运行目录使用候选清单哈希短路径并预估最深 FFmpeg 临时文件路径。此前完整
  候选 ID 会使 `.page-0001.tmp.mp4` 达 262 字符并由 FFmpeg 返回 `No such file or directory`；
  修复后保持完整候选 ID 在证据内，运行路径则安全缩短。

## 回归

- Python：Ruff、`mypy --strict`（10 个相关源文件）均通过；相关导出、渲染、RenderGraph、
  API 与性能测试共 **53 passed**。
- Remotion：输出配置与 RenderGraph 的 Vitest **7 passed**，`tsc --noEmit` 与 Prettier 均通过。

## 边界与下一步

本停点完成本机候选上的 720p/1080p 规格压力、字幕/覆盖层/转场/混音的真实媒体闭环。
它不替代 4K 硬件准入、GIF 执行器、真实外部 Provider、签名发行或长时稳定性测试。

下一项为 DP45：候选绑定的长稳压力、恢复性与资源曲线验收。所有 DP44 运行产物均位于被
忽略的 `test-results`，不修改用户项目。
