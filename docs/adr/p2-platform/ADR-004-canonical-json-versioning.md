# ADR-004：规范化 JSON、哈希与版本兼容

- Status: Accepted
- Date: 2026-08-11
- Supersedes: None

## Context

Provider 缓存键、对象寻址、revision 内容哈希和同步去重都依赖稳定序列化。语言默认 JSON 输出在键顺序、Unicode、浮点和缺省字段上可能不同。

## Decision

1. 所有跨边界模型携带显式 `schema_version`，首版使用整数 `1`；格式语义改变时递增。
2. 哈希输入使用 UTF-8、Unicode NFC、按代码点排序的对象键、无额外空白、禁止 NaN/Infinity 的规范化 JSON。
3. 时间统一为 UTC RFC 3339，输出使用 `Z`；UUID 使用小写连字符格式。
4. 二进制数据不内嵌 JSON，使用对象引用；金额使用整数最小货币单位，时长使用整数毫秒。
5. 哈希算法为 SHA-256，外部表示为小写十六进制，并附 `sha256:` 前缀。
6. Reader 可接受当前版本和明确登记的旧版本；Writer 只输出当前版本。未知未来版本必须拒绝。

## Consequences

需要共享 canonicalizer 和跨语言 golden fixtures；换来稳定缓存、签名、冲突检测和可重复测试。

## Compatibility

旧模型通过纯函数 upgrader 转换；原始 payload 和升级结果可审计，升级不得原地修改不可变 revision。

## Verification

- Python 与 TypeScript 对 golden fixtures 生成相同字节和 SHA-256。
- 键乱序、等价 Unicode 和时区等价输入得到相同摘要。
- NaN、未知版本和未登记字段策略产生确定错误。
