# M2 材料解析阶段验收记录

日期：2026-08-03
分支：`feature/m2-material-parsing`

## 结论

M2 Task 6—10 的代码、自动化测试、Linux/LibreOffice 集成测试和浏览器回归已完成。自动化阶段门禁通过；Windows CPU-only PaddleOCR 真实 8 页扫描 PDF 基准仍按原计划保留为实机补充门禁，当前结果不得替代该项。

## 已实施范围

- Task 6：DOCX、PPTX、PDF、JPG/JPEG、PNG、WebP、BMP、TIFF 文件头校验、安全复制、SHA-256、同名保护、图片自然排序、人工改序和审计。
- Task 7：Word 标题、段落、表格、合并单元格、正文顺序、来源定位、缓存键与 `03_文字识别/大纲结构.json`。
- Task 8：PPTX 页序、文本框、表格、隐藏页标识、LibreOffice PDF 转换、空白页阻断、引擎版本和 1920×1080 预览。
- Task 9：可搜索/混合/扫描 PDF、旋转页、加密阻断、常见图片、多页 TIFF、EXIF、透明背景、安全画布、PaddleOCR 可选运行时与低置信度 bbox。
- Task 10：固定权重匹配、候选分解、空页/重复页/标题冲突、人工改绑、原因记录和审计。
- Gate 补齐：统一“导入→解析→匹配→写回 `project.json`”服务；源哈希＋解析版本＋OCR 策略缓存；关闭并重开后复用页面、匹配和预览，不重复 OCR。

## 自动化证据

- `bash scripts/check.sh`：通过。
- Python：56/56 通过。
- Web Vitest：5/5 通过。
- Playwright：1/1 通过。
- Ruff：通过。
- mypy strict：通过。
- ESLint、Prettier：通过。
- TypeScript `tsc --noEmit`：通过。
- Web 与 Remotion 生产构建：通过。
- 8 页 PPTX：页数 8/8、预览 1920×1080、末页文本抽样通过。
- 8 页匹配抽样：8/8 标题候选一一对应。
- 重启缓存测试：第二次处理命中同一缓存键，OCR 未再次调用，预览文件时间戳未变化。
- 审查回归：混合 Word＋图片自然排序、同页 PDF 文本＋OCR 合并、缺失字体前置阻断、旧 PDF 缓存清除、加密 PDF 结构化错误均通过。

## 覆盖的材料 fixture

- Word：标题、正文、空段、表格、合并单元格、中文编号、损坏包。
- PPTX：文本框、表格、备注忽略、隐藏页、缺失 LibreOffice、缺失字体、8 页真实转换。
- PDF：可搜索、混合、纯扫描、90° 旋转、AES-256 加密、低置信度 OCR。
- 图片：JPG、PNG、WebP、BMP、多页 TIFF、EXIF 旋转、RGBA 透明背景、超像素限制、多图自然排序与人工改序。

## 运行时锁定

- `paddleocr==3.4.1` 与 `paddlepaddle==3.3.1` 已进入 `ocr` 可选依赖锁文件。
- PaddleX 缓存通过 `PADDLE_PDX_CACHE_HOME` 定向到可写目录，避免只读 HOME 导入失败。
- LibreOffice 实际版本会随每次解析结果记录；当前 Linux 集成环境识别为 LibreOfficeDev 26.8 系列。

## 尚待 Windows 实机完成

- CPU-only Windows 基准机下载中文 OCR 模型。
- 8 页扫描 PDF 的总耗时、峰值内存和模型下载大小。
- Windows 中文用户名/中文路径下的 LibreOffice、PaddleOCR 与图片批次实测。
- 对真实 PowerPoint 与 LibreOffice 预览进行字体、裁切和隐藏页视觉对比。

上述事项是平台实机证据缺口，不是自动化代码失败；在完成前，M2 只能判定为“自动化门禁通过、Windows 补充门禁待验”。
