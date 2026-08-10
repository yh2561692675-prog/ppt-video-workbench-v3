# Effect Engine V2 发布与回滚

发布开关顺序：persistence → preview → render。非法组合在启动时拒绝。当前渲染接口保持同步，不引入 job ID。

回滚只关闭 preview/render 开关；保留可选 `effect_plan` 字段、Props 快照和导出审计，不删除或重建项目 manifest。

发布记录必须包含：构建版本、`installer/runtime-manifest.json`、质量门禁输出、安装目录、备份位置、验收项目 ID、剩余风险。
