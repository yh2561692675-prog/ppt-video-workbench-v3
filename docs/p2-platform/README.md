# P2 平台能力文档

P2 平台能力由三个相互独立、默认关闭的部分组成：多供应商 Provider、跨平台服务层、可选云端协作。现有 Windows 本地单用户流程仍是默认和受支持路径。

- [用户指南](user-guide.md)：选择 Provider、预算、平台降级、同步状态和冲突处理。
- [管理员指南](admin-guide.md)：组织策略、区域、配额、executor、撤销和生产门禁。
- [开发者指南](developer-guide.md)：新增 Provider/平台适配器、Cloud API 兼容规则和测试门禁。
- [发布状态与边界](release-status.md)：各平台成熟度、Cloud beta 范围和待外部签署证据。

任何文档中的 `pass` 只代表所列自动化或真实证据；fake Provider、单机 Cloud 原型和 CI 平台探测不能替代真实供应商、真实双设备或签名发行验收。
