# 安装版独立渲染运行时设计

## 目标

让 Windows 安装包在不访问开发仓库、全局 `pnpm` 或开发期 Node 模块的情况下完成 Remotion 页面渲染。安装包携带 Node、Remotion bundle、FFmpeg 和 FFprobe；浏览器使用系统 Microsoft Edge，并在缺失时给出可操作诊断。

## 方案选择

不采用“继续从 Python 源文件推导仓库根目录后调用 `pnpm`”，因为安装目录没有源码工作树。也不采用首次启动在线下载，避免离线、企业网络和版本漂移造成的首次导出失败。当前采用运行时随安装包发布、Edge 由系统提供的方案，体积与可靠性平衡最佳。

## 运行时布局

发布目录新增 `runtime/`：`node/node.exe` 为 Node 入口；`remotion/` 包含 `pnpm deploy --prod` 产生的 CLI/依赖和视频入口 `src/index.ts`；`ffmpeg/` 包含 `ffmpeg.exe`、`ffprobe.exe` 及 DLL。`scripts/prepare-runtime.ps1` 在 Windows 发布机从已安装 Node、FFmpeg/FFprobe 与锁定 Remotion 依赖生成 `runtime-assets/`。`scripts/build-release.ps1` 只复制和校验这些资产，不下载或猜测版本。

## 定位与执行

`RuntimeLayout` 优先读取 `WORKBENCH_RUNTIME_ROOT`，否则从已打包 API 可执行文件旁的发布根目录定位 `runtime/`。`RemotionPageRenderer` 直接执行 `node.exe <remotion-cli.js> render <runtime/remotion/src/index.ts> ...`，不再执行 `pnpm` 或回溯源码目录。运行时清单记录 API、Web、Node、Remotion CLI/入口、FFmpeg、FFprobe 的 SHA-256 与大小。

## 失败体验与验证

任何关键组件缺失均在构建期终止；导出前缺失则返回组件名与“重新运行准备运行时脚本并重建安装包”的动作。缺少 Edge 时提示安装/启用 Edge 或设置 `WORKBENCH_REMOTION_BROWSER_EXECUTABLE`。Linux 只验证合同；Windows 仍须执行准备、构建和两页 MP4 实机验收，不能把 Linux 测试等同于 Windows 导出成功。
