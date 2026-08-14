# DP43 S50 大项目验收

DP43 使用候选专属、短路径的 S50 合成媒体夹具执行产品实际导出链路：50 页图片与
50 段唯一 WAV、字幕、页面 FFmpeg 渲染、页面音视频合成、最终拼接和制作包发布。
夹具的每页 WAV 内容不同，遵循产品“页面音频不得重用 cache key”的门禁，而不会绕过
字幕或预检。

运行目录在 Windows 路径预算预检后创建。它仍绑定完整 candidate manifest SHA-256，
但磁盘路径只使用短哈希前缀，避免深层制作包临时文件超出 Windows 限制。旧的失败尝试
保留在忽略的 `test-results` 中，不会被覆盖或计入本次结果。

## 实测结果

候选 `v1-rc-245ee7e848ff-20260812T181222Z` 绑定源码
`245ee7e848ff7048abf32f3369d3dd9bd8836028`，candidate manifest SHA-256：
`fee67ffd32ccfed45deab80fb682f17ae925fc6501c88cf058aac9942492b378`。

| 项目              | 实测                                                                                               |
| ----------------- | -------------------------------------------------------------------------------------------------- |
| 页面数 / 目标时长 | 50 / 15,000 ms                                                                                     |
| 总耗时            | 61,838 ms                                                                                          |
| 中断 / 恢复       | 第 10 页持久检查点中断；恢复后复用 10 页                                                           |
| 检查点数          | 66                                                                                                 |
| 最终 MP4          | H.264 + AAC，15,050 ms，SHA-256 `0f3493eef22b342bd5306ad87786c4677b62d075d6bd4ba5d3f0bce6711b4779` |
| 字幕 SRT SHA-256  | `b1c31f2d16c6898aa940a277f7544fe6119fb001c97dcdcc648e68ef5f1c7848`                                 |
| 制作包            | 58 个清单工件；manifest SHA-256 `78e7a05f5896649249dc140e51f6daaa510079cf67f0ff762b8c1e79d61d8295` |
| 运行后临时文件    | 0 个 `.tmp`                                                                                        |
| 采样              | 57 个样本，无缺失根；最高 RSS：harness 238,821,376 bytes、FFmpeg 202,006,528 bytes                 |
| 最低可用临时磁盘  | 26,056,806,400 bytes                                                                               |

采样完整记录了 import、preflight、page render、checkpoint、mux 和 package 的阶段边界。
GPU 指标保持 `null`，因为未加载厂商专用探针。S50 真实证据 JSON 的 SHA-256 为：
`a01f6a7a191b7e3680d8f56c4f73bbf8121d9acbe8af7c99bf9fff426f5f1aae`。

本结果只覆盖本机 FFmpeg、AI 旁白合成夹具和产品制作包链路；未声称真实外部 Provider、
Remotion 浏览器渲染、云执行器或真人讲解媒体已经通过。
