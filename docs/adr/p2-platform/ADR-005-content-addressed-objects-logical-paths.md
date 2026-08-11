# ADR-005：内容对象与本地逻辑路径

- Status: Accepted
- Date: 2026-08-11
- Supersedes: None

## Context

Windows 盘符、反斜杠和安装目录不能成为云端或跨平台契约。大素材又不适合嵌入 operation 或 revision JSON。

## Decision

1. 二进制内容以 SHA-256 内容对象标识；`object_id` 不包含文件名、用户路径、租户或存储桶信息。
2. 项目模型只保存 POSIX 风格的相对逻辑路径和 `ObjectRef`，禁止绝对路径、盘符、UNC、`..` 和 NUL。
3. `PlatformServices.paths` 负责逻辑路径与本机路径映射；云端对象存储负责 object ID 与物理 key 映射。
4. 上传采用先校验摘要后提交的两阶段流程；下载写临时文件，校验摘要和长度后原子替换。
5. 相同内容可物理去重，但授权、保留期和删除引用按租户/项目元数据隔离，不因哈希相同泄露存在性。

## Consequences

需要对象索引、引用计数/标记清理和路径校验；换来跨平台可移植、增量同步和断点续传能力。

## Compatibility

导入旧项目时扫描文件生成对象引用，同时保留原展示文件名；本地目录布局无需立即改变。

## Verification

- Windows、macOS、Linux 路径 fixtures 映射到相同逻辑路径。
- 路径穿越、大小写冲突、符号链接逃逸和摘要不匹配被拒绝。
- 临时下载中断不覆盖已存在的有效对象。
