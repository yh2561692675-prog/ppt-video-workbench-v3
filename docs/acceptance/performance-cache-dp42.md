# DP42 S8 冷热缓存与选择性失效

DP42 对既有 `VideoRenderService` 页面缓存进行隔离验收。验收器每次只在新建、
候选专属的项目目录工作，绝不删除或重用用户目录、全局缓存或任何未知路径。

入口为 `scripts/performance_cache_acceptance.py`。它先验证 candidate manifest 与当前
checkout 一致，再执行三个连续阶段：

1. 冷缓存：8 个页面全部渲染。
2. 热缓存：相同输入必须全部复用。
3. 选择性失效：仅变更第 4 页源图，必须只重渲染第 4 页。

每个阶段记录耗时、逐页命中状态、page cache key、工件 SHA-256、页面缓存图 hash。
工具对 0/8 冷缓存、8/0 热缓存、7/1 选择性失效，以及未修改工件或图 hash 的不一致
均会 fail-closed。

## 干净候选实测

候选 `v1-rc-3995a0666c8d-20260812T172636Z` 绑定源码提交
`3995a0666c8d3713e3a8d0923c213932c9d22236`，manifest SHA-256 为
`484a97ecb25e1b64fab3e61be53a8171079f09d10ccc40571ee0c29898bf1796`。
输入为 `DG2-S8-synthetic-v1`，fixture contract SHA-256 为
`f667d825952a3984ed52e6684c62887a58141399f0191a73e52184fe1b8c04a4`。

| 阶段 | 命中 / 未命中 | 耗时 | 页面缓存图 hash |
| --- | --- | ---: | --- |
| cold | 0 / 8 | 1,341 ms | `bba88d290d7fcf5b49f747e6460fbf0b8ab66f1f8835185f10f9918ea06beb9b` |
| warm | 8 / 0 | 27 ms | `bba88d290d7fcf5b49f747e6460fbf0b8ab66f1f8835185f10f9918ea06beb9b` |
| selective | 7 / 1 | 169 ms | `41380d94f32a0123707f064866556334e216b40024625d66f04f3f5675a1ef78` |

第 4 页源图 SHA-256 从
`b308deeed24d0a55261119fe4185554af35979f5b3264e2b21772148055618a9` 变为
`221f071c2c0da64154c1022793e6dbe00a2f2a6ff0b5580cd8ca4dd6dd817283`；第 4 页
工件改变，其他 7 页工件不变。完整 JSON 证据位于被 Git 忽略的候选结果目录，SHA-256：
`2a9995feb4ce157b50f35779a297e676962bbac52dcb26df81ecd632f58a8f9b`。

该验收仅覆盖页面缓存语义。最终 MP4、制作包、S50、导出压力和长稳负载仍分别由
DP43-DP45 验收。
