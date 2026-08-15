# Security Policy / 安全政策

## Supported versions / 支持范围

安全修复优先应用到默认分支。项目尚未发布稳定的 `1.x` 版本，因此历史开发快照不承诺单独维护。

| Version                   | Supported |
| ------------------------- | --------- |
| Default branch / 默认分支 | Yes       |
| Older snapshots / 旧快照  | No        |

## Reporting a vulnerability / 报告漏洞

请不要为未修复的安全问题创建公开 Issue，也不要在 Issue、Pull Request、日志、截图或示例文件中粘贴真实 API Key、Token、密码或个人数据。

优先使用本仓库 **Security** 页面中的 **Report a vulnerability** 私下提交报告。如果该入口暂不可用，请先通过维护者的 GitHub 个人资料发起不包含漏洞细节的联系，以建立私密沟通渠道。

报告建议包含：

- 受影响的提交、版本或组件；
- 可复现的最小步骤和预期影响；
- 已知的缓解方法；
- 不含真实密钥和个人数据的测试样例。

维护者确认收到后会评估影响、准备修复并协调披露时间。请在修复发布前避免公开漏洞细节。

## Credential hygiene / 凭据规范

- 外部服务不是本地核心流程的必需条件。
- 凭据应通过应用设置页或本机安全存储提供，不应提交到 Git。
- `.env`、`.env.*`、常见私钥和凭据文件已被忽略；`.env.example` 只允许记录非敏感示例。
- 如果真实密钥曾进入 Git 历史，仅删除当前文件还不够：应立即撤销并轮换该密钥，再评估历史清理。
