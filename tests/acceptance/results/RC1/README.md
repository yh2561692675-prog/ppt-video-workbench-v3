# RC1 实机证据目录

先在 Windows 源码根目录运行 `scripts/build-release.ps1`。只有它生成
`release/ppt-video-workbench-setup.exe` 后，才运行 `tests/release/install-smoke.ps1`
和后续 RC1 场景；不得用源码目录替代安装器结果。

本目录只接受受控 Windows 10/11 RC1 验收产物、截图和机器报告。当前 Linux 容器没有真实 Windows、Office、用户声音或人工视听证据，因此状态保持 `pending_manual_windows`。

完成验收后按场景写入子目录：

- `RC-LOCAL/`：真实 Word+PPTX、本地录音和完整制作包；
- `RC-SCAN/`：Word+扫描 PDF、OCR 低置信度定位与人工修正；
- `RC-IMAGES/`：Word+多图片、自然排序与人工排序；
- `RC-HEYGEN/`：受控额度下 2 页真实声音、请求/缓存/费用记录；
- `RC-RECOVERY/`：OCR、转写、声音和渲染阶段暂停/关闭/恢复；
- `RC-AUDIOVISUAL/`：音画、字幕、裁切、爆音、静音、错页和核心内容检查截图。

将 `evidence-manifest.json` 中的 `result`、证据路径、缺陷严重度和签署字段更新后，再重新运行 M8 Gate。不得用合成 fixture 或命令行输出替代真实项目签署。
