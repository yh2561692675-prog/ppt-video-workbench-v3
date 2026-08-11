# 平台绑定点审计与迁移清单

- Status: Baseline audit
- Audited: 2026-08-11
- Scope: `apps/`、`packages/`、`scripts/`、`installer/`
- Target: ADR-007 `PlatformServices`

## 1. 结论

当前应用可以在不改业务契约的前提下逐步抽取跨平台基础层，但不能直接把 Windows 分支复制到 macOS/Linux。绑定点主要落在五个边界：安装与启动、用户数据路径和原子文件、密钥存储、外部工具/进程、Office 与媒体运行时。

建议先用 Windows adapter 包装现状并执行输出等价测试，再实现 POSIX adapter。迁移顺序应是 composition root → paths/files → credentials → tools/processes → media/office → browser/update/diagnostics；每次只切换一个子协议。

本审计是绑定点清单，不授权改动正在进行的渲染、质量、模板、时间线或 Windows 发布修复。

## 2. 扫描摘要

以下数字来自 2026-08-11 对非依赖、非构建产物代码的文本扫描；它们用于估算和发现，不作为永久静态门禁基线。

| 特征                       |    命中文件数 | 判断                           |
| -------------------------- | ------------: | ------------------------------ |
| `windows`                  |            33 | 安装、文案、测试和运行时混合   |
| `os.name`                  |             7 | 路径、诊断、OCR、原子文件      |
| `sys.platform`             |             1 | DPAPI 密钥存储                 |
| `LOCALAPPDATA` / `APPDATA` |         9 / 9 | 安装、启动和运行目录           |
| `powershell`               | 2（不含备份） | 启动与安装入口                 |
| `libreoffice`              |             9 | Office 能力探测和页面渲染      |
| `subprocess`               |            15 | 媒体、Office、质量、交付和诊断 |
| `ffmpeg` / `ffprobe`       |       28 / 17 | 音视频处理、探测和打包         |

扫描还发现多份 `*.bak` 历史文件。它们不进入运行时迁移范围，但应在可信基线冻结后单独确认归档策略，避免静态检查误报。

## 3. PlatformServices 目标接口

| 子服务        | 职责                                         | 不应泄漏给业务层的细节                  |
| ------------- | -------------------------------------------- | --------------------------------------- |
| `paths`       | 数据、缓存、临时、日志、运行时和项目逻辑路径 | 盘符、`LOCALAPPDATA`、bundle 目录       |
| `files`       | 原子写、锁、权限、可用空间、大小写规则       | `os.replace` 差异、ACL、fsync 组合      |
| `credentials` | 创建、读取、删除命名秘密                     | DPAPI/Keychain/libsecret 实现和密钥明文 |
| `tools`       | 查找和描述 FFmpeg、Node、Office、OCR 等能力  | `PATH`、注册表、bundle 搜索顺序         |
| `processes`   | 参数化启动、超时、取消、资源限制和脱敏日志   | PowerShell/shell 拼接、平台信号差异     |
| `media`       | FFmpeg/FFprobe 能力、编码器和滤镜选择        | 可执行文件路径、硬件编码器探测细节      |
| `office`      | PPTX/PDF 页面渲染与能力降级                  | PowerPoint COM、LibreOffice profile     |
| `browser`     | 安全打开本地/HTTPS 目标                      | `startfile`、`open`、`xdg-open`         |
| `updates`     | 清单验证、下载、安装和重启                   | Inno/DMG/AppImage/pkg 管理器细节        |
| `diagnostics` | 平台、能力、权限和运行时报告                 | 原始系统错误、用户名和秘密路径          |

## 4. 绑定点清单

### 4.1 安装、启动与运行目录

| 位置                                       | 当前绑定                                   | 迁移目标                                     | 风险 |
| ------------------------------------------ | ------------------------------------------ | -------------------------------------------- | ---- |
| `installer/workbench.iss`                  | Inno Setup、PowerShell、`{localappdata}`   | 保留为 Windows packager；统一消费发布清单    | 高   |
| `scripts/launcher.ps1`                     | PowerShell、LOCALAPPDATA、Windows 进程模型 | Windows launcher adapter；POSIX 使用独立入口 | 高   |
| `scripts/build-release.ps1`                | Inno 路径和 Windows 打包工具               | 平台 packager 矩阵                           | 中   |
| `apps/api/workbench.spec`                  | PyInstaller 和捆绑运行时布局               | 共享 release manifest + 平台资源表           | 高   |
| `apps/api/src/workbench/runtime/layout.py` | Program Files 与 bundle 搜索               | `paths` + `tools`                            | 高   |

约束：打包脚本可以保留平台语句，但不得成为业务运行时能力判断的来源；安装清单必须列明二进制、版本、摘要、许可证和平台。

### 4.2 路径与文件系统

| 位置                                          | 当前绑定                     | 迁移目标                | 测试重点                           |
| --------------------------------------------- | ---------------------------- | ----------------------- | ---------------------------------- |
| `storage/project_paths.py`                    | `os.name`、平台特定路径/命令 | `paths`                 | 盘符、UNC、长路径、POSIX、符号链接 |
| `storage/manifest_store.py`                   | Windows 原子替换分支         | `files.atomic_replace`  | 崩溃恢复、占用、权限不足           |
| `video/render_service.py`、`video/publish.py` | 直接 `os.replace`            | `files.atomic_replace`  | 同卷/跨卷、已有目标                |
| `diagnostics/probes.py`                       | 平台命名和文件能力探测       | `diagnostics` + `files` | 脱敏、只读目录、锁行为             |
| 各 `business_modules/*/runner.py`             | 重复临时文件和替换           | 共享原子写 helper       | 中断、残留清理、幂等               |

逻辑项目路径采用 `/` 分隔的安全相对路径；本机绝对路径不进入 API、revision、缓存键或云端 operation。

### 4.3 凭证

| 位置                       | 当前绑定                       | 迁移目标                                | 测试重点                    |
| -------------------------- | ------------------------------ | --------------------------------------- | --------------------------- |
| `settings/secret_store.py` | `sys.platform == win32`、DPAPI | `credentials`                           | 锁屏/无钥匙串/损坏密文/轮换 |
| `settings/heygen_store.py` | 具体秘密存储与本地记录耦合     | provider profile + credential reference | 删除、导出脱敏、迁移        |
| API settings routes        | 捕获 Windows store 错误        | 结构化 capability error                 | HTTP 错误稳定性             |

禁止以环境变量或明文 JSON 作为桌面生产凭证的默认回退。开发环境变量只能由显式 dev adapter 启用，并在诊断报告标记不安全模式。

### 4.4 工具发现与子进程

| 位置                                                                  | 当前绑定                        | 迁移目标                | 风险 |
| --------------------------------------------------------------------- | ------------------------------- | ----------------------- | ---- |
| `environment/detector.py`                                             | `shutil.which`、直接 subprocess | `tools` + `processes`   | 高   |
| `preflight/engine.py`                                                 | 直接发现 Node/FFmpeg/FFprobe    | `tools`                 | 中   |
| `video/process_runner.py`                                             | Popen 生命周期                  | `processes` 的参考实现  | 高   |
| `quality/engine.py`、`p11_render/runner.py`、`p12_delivery/runner.py` | 直接调用外部程序                | `processes`             | 高   |
| `diagnostics/probes.py`                                               | FFmpeg 查找和版本调用           | `tools` + `diagnostics` | 中   |

`processes` 必须只接受可执行文件引用和参数数组，默认 `shell=False`；实现统一超时、取消、子进程树终止、输出上限和敏感参数掩码。

### 4.5 Office、媒体与 OCR

| 位置                                          | 当前绑定                            | 迁移目标              | 降级策略                              |
| --------------------------------------------- | ----------------------------------- | --------------------- | ------------------------------------- |
| `renderers/office_renderer.py`                | LibreOffice、字体探测、临时 profile | `office`              | 无 Office 时返回 capability downgrade |
| `fidelity/static_renderer.py`                 | 具体 Office renderer                | `office.render_pages` | 回退 Python 静态渲染并标注保真度      |
| `audio/ffmpeg.py`、`media/presenter_audio.py` | FFmpeg 命令                         | `media`               | 无编码器时阻止对应操作，不损坏源文件  |
| `media/presenter_probe.py`                    | FFprobe 命令                        | `media.probe`         | 返回未知能力而非猜测                  |
| `ocr/paddle_adapter.py`                       | Windows LOCALAPPDATA 缓存           | `paths.cache_dir`     | 本地 OCR 不可用时允许云 OCR 策略      |

macOS/Linux PoC 的 Office 首选 LibreOffice headless。PowerPoint COM 只能存在于 Windows office adapter，业务契约不得以 COM 类型或 PowerPoint 专有错误为条件。

## 5. 迁移批次与门禁

| 批次 | 范围                         | 入口门禁       | 完成门禁                            |
| ---- | ---------------------------- | -------------- | ----------------------------------- |
| B1   | 本审计和静态白名单           | 无写入业务代码 | 清单覆盖已知绑定点                  |
| B2   | 协议、fake、composition root | F0 可信基线    | 单元测试和依赖方向检查              |
| B3   | paths/files                  | B2             | Windows fixtures 等价、崩溃恢复通过 |
| B4   | credentials                  | B3             | 密钥不落盘、三平台 adapter 契约测试 |
| B5   | tools/processes              | B3             | 取消、超时、树终止、日志脱敏通过    |
| B6   | media/office                 | B5             | 8 页和 50 页基线输出差异受控        |
| B7   | browser/update/diagnostics   | B4-B6          | 安全打开、签名更新和脱敏报告        |
| B8   | Windows 全量切换             | B3-B7          | 开关前后 E2E 等价                   |
| B9   | 删除业务层平台分支           | B8             | 静态检查无新增违规                  |
| B10  | macOS/Linux PoC              | B9             | 导入、预览、编辑、导出 smoke 通过   |
| B11  | 安装/更新/CI                 | B10            | 三平台签名安装与升级回滚通过        |

## 6. 静态检查策略

新增检查只扫描业务 Python/TypeScript 源码，允许以下目录：

- `workbench/platform/` 中的 adapter 与 composition root；
- `scripts/`、`installer/` 和平台打包配置；
- 明确记录理由、负责人和到期批次的临时白名单。

禁止模式包括新增 `sys.platform`、`os.name`、`LOCALAPPDATA`、`APPDATA`、`ProgramFiles`、`startfile`、字符串 shell 命令和业务层 `shutil.which`。门禁比较当前基线与增量，避免历史问题在迁移前阻塞所有提交，但白名单只能减少不能增加。

## 7. 验收样本

Windows 等价集至少包含：

1. 8 页普通 PPTX + Word 大纲的完整流程。
2. 50 页、含中文字体和大素材的压力流程。
3. 无 LibreOffice、无 FFmpeg、无 OCR 模型的能力降级。
4. 数据目录只读、磁盘不足、目标被占用和异常退出恢复。
5. 凭证创建/读取/删除、诊断包导出和秘密扫描。
6. 子进程超时、用户取消、进程树终止和日志截断。

跨平台 PoC 使用相同逻辑输入、规范化 manifest 和允许差异表。编码器元数据、创建时间和容器排列等非语义差异必须先规范化，不能以“二进制完全相同”替代产品结果等价。

## 8. 已知风险与待验证项

- PyInstaller、Node、Remotion 和浏览器运行时在三平台的 bundle 布局尚未用真实安装包验证。
- PowerPoint 专有保真能力在 macOS/Linux 不可等价，需要产品化的能力矩阵与降级提示。
- macOS 签名/notarization、Linux 发行格式与自动更新信任链需要发布环境凭证，不能在本地 PoC 假定完成。
- 文件锁、大小写敏感和符号链接行为需要真实文件系统测试，内存 fake 不足以覆盖。
- 当前工作区存在并发项目和历史备份文件；B2 代码迁移必须等待 F0 冻结后开始。
