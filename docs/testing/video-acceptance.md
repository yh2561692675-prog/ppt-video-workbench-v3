# Effect Engine V2 视频验收

验收使用临时夹具，不直接写入真实用户项目。必须记录项目 ID、目录、Props schema、catalog version、每页 plan hash、缓存命中和导出包路径。

## 必过项

- 12 个公共模板与 SafeSlide 均在 16:9、9:16 下通过 Remotion 关键帧测试。
- 旧项目无 effect 字段可读取；显式生成后 Props 变为 schema 2。
- 计划 hash 在 API、Props、分段 cache key、导出逐页文件中一致。
- 锁定计划不被重新生成覆盖；revision 冲突返回 409。
- 配音、字幕、旁白、页面正文和预览路径在生成前后相等。
- 关闭并重新启动 API 后项目 ID、目录、revision 和 hash 保持一致。
- 修改单页计划只使该页分段缓存失效。
- 同步最终渲染请求能创建并开始。

## 命令

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-video-quality-gates.ps1
```
