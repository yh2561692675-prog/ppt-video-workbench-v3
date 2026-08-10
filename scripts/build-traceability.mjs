import fs from 'node:fs/promises';
import path from 'node:path';

import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const repositoryRoot = path.resolve(process.argv[2] ?? process.cwd());
const manifestPath = path.join(repositoryRoot, 'tests', 'acceptance', 'fixtures-manifest.json');
const outputPath = path.join(repositoryRoot, 'docs', 'traceability.xlsx');
const verifyDir = process.env.M8_VERIFY_DIR ?? path.dirname(outputPath);
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));

const workbook = Workbook.create();
const summary = workbook.worksheets.add('Summary');
const traceability = workbook.worksheets.add('Traceability');
const fixtures = workbook.worksheets.add('Fixtures');

const navy = '#0B1F33';
const blue = '#DCEEFF';
const border = '#C8D6E5';
const pending = '#FFF2CC';

function styleTitle(sheet, range) {
  const target = sheet.getRange(range);
  target.format.fill = navy;
  target.format.font = { bold: true, color: '#FFFFFF', size: 16 };
  target.format.horizontalAlignment = 'left';
  target.format.verticalAlignment = 'center';
}

function styleHeader(sheet, range) {
  const target = sheet.getRange(range);
  target.format.fill = blue;
  target.format.font = { bold: true, color: navy };
  target.format.wrapText = true;
  target.format.borders = { preset: 'all', style: 'thin', color: border };
  target.format.verticalAlignment = 'center';
}

function styleBody(sheet, range) {
  const target = sheet.getRange(range);
  target.format.wrapText = true;
  target.format.verticalAlignment = 'top';
  target.format.borders = { preset: 'all', style: 'thin', color: border };
}

summary.showGridLines = false;
summary.mergeCells('A1:F1');
summary.getRange('A1').values = [['M8 V1.0 Acceptance Traceability / 验收追踪矩阵']];
styleTitle(summary, 'A1:F1');
summary.getRange('A1:F1').format.rowHeight = 30;
summary.getRange('A3:B7').values = [
  ['指标 / Metric', '值 / Value'],
  ['需求总数 / Requirements', null],
  ['自动化证据行 / Automated rows', null],
  ['Windows/真实服务待签署行 / Manual pending', null],
  ['当前发布状态 / Release status', 'RC candidate — manual sign-off pending'],
];
styleHeader(summary, 'A3:B3');
styleBody(summary, 'A4:B7');
summary.getRange('B4').formulas = [["=COUNTA('Traceability'!A6:A28)"]];
summary.getRange('B5').formulas = [['=COUNTIF(\'Traceability\'!K6:K28,"automated_evidence")']];
summary.getRange('B6').formulas = [['=COUNTIF(\'Traceability\'!K6:K28,"pending_manual_windows")']];
summary.getRange('A9:F9').merge();
summary.getRange('A9').values = [
  [
    'Note: automated_evidence means Linux/CI only. Windows VM, real voice and audiovisual review require RC1 sign-off / Windows 实机、真实声音和人工视听需单独签署。',
  ],
];
summary.getRange('A9:F9').format = { fill: pending, wrapText: true, verticalAlignment: 'top' };
summary.getRange('A1:F12').format.font = { name: 'Noto Sans CJK SC', size: 10, color: '#17324D' };
summary.getRange('A1:F1').format.font = {
  name: 'Noto Sans CJK SC',
  size: 16,
  bold: true,
  color: '#FFFFFF',
};
summary.getRange('A:A').format.columnWidth = 28;
summary.getRange('B:B').format.columnWidth = 30;
summary.getRange('C:F').format.columnWidth = 16;
summary.getRange('A3:B7').format.rowHeight = 24;
summary.getRange('A9:F9').format.rowHeight = 42;
summary.freezePanes.freezeRows(3);

const traceHeaders = [
  '需求 ID / Requirement ID',
  '领域 / Domain',
  '需求描述 / Requirement',
  '优先级 / Priority',
  '验收测试 ID / Test IDs',
  '前置条件 / Preconditions',
  '步骤 / Steps',
  '期望 / Expected',
  '证据路径 / Evidence',
  '执行环境 / Environment',
  '结果 / Result',
];
const domainEnglish = {
  项目管理: 'Project Management',
  材料导入: 'Material Import',
  页面解析: 'Page Parsing',
  内容匹配: 'Content Matching',
  旁白生成: 'Narration Generation',
  旁白确认: 'Narration Confirmation',
  'HeyGen 配音': 'HeyGen Voice',
  本地录音: 'Local Audio',
  字幕: 'Subtitles',
  'Remotion 渲染': 'Remotion Render',
  完整预检: 'Full Preflight',
  断点续作: 'Recovery',
  完整导出: 'Full Export',
  安装启动: 'Install and Launch',
  稳定版更新: 'Stable Updates',
  图片输入: 'Image Input',
  易用性: 'Usability',
  可靠性: 'Reliability',
  可维护性: 'Maintainability',
  安全性: 'Security',
  可追溯性: 'Traceability',
  兼容性: 'Compatibility',
  输出质量: 'Output Quality',
};
const traceRows = manifest.requirements.map((item) => {
  const isManual =
    item.evidence.some(
      (evidence) => evidence.includes('install-smoke') || evidence.includes('M7-GATE'),
    ) || ['FR-007', 'FR-014', 'FR-015', 'NFR-001', 'NFR-006', 'NFR-007'].includes(item.id);
  return [
    item.id,
    `${item.domain} / ${domainEnglish[item.domain] ?? 'Requirement'}`,
    `${item.id}: ${domainEnglish[item.domain] ?? 'Requirement'} / ${item.description}`,
    item.priority,
    item.test_ids.join(', '),
    'RC 构建可用；对应 fixture/项目已准备',
    `执行 ${item.test_ids.join('、')}；保存机器报告或人工截图`,
    `满足：${item.description}；无 P0/P1`,
    item.evidence.join('\n'),
    isManual ? 'automated_linux + manual_windows' : 'automated_linux',
    isManual ? 'pending_manual_windows' : 'automated_evidence',
  ];
});
traceability.showGridLines = false;
traceability.mergeCells('A1:K1');
traceability.getRange('A1').values = [['M8 Acceptance Traceability Matrix / 需求—验收追踪矩阵']];
styleTitle(traceability, 'A1:K1');
traceability.getRange('A1:K1').format.rowHeight = 30;
traceability.getRange('A5:K5').values = [traceHeaders];
styleHeader(traceability, 'A5:K5');
traceability.getRange(`A6:K${traceRows.length + 5}`).values = traceRows;
styleBody(traceability, `A6:K${traceRows.length + 5}`);
traceability.getRange(`K6:K${traceRows.length + 5}`).conditionalFormats.add('containsText', {
  text: 'pending_manual_windows',
  format: { fill: pending },
});
traceability.tables.add(`A5:K${traceRows.length + 5}`, true, 'TraceabilityTable');
traceability.getRange('A:A').format.columnWidth = 12;
traceability.getRange('B:B').format.columnWidth = 16;
traceability.getRange('C:C').format.columnWidth = 34;
traceability.getRange('D:E').format.columnWidth = 14;
traceability.getRange('F:H').format.columnWidth = 28;
traceability.getRange('I:I').format.columnWidth = 38;
traceability.getRange('J:K').format.columnWidth = 24;
traceability.getRange(`A1:K${traceRows.length + 5}`).format.font = {
  name: 'Noto Sans CJK SC',
  size: 10,
  color: '#17324D',
};
traceability.getRange('A1:K1').format.font = {
  name: 'Noto Sans CJK SC',
  size: 16,
  bold: true,
  color: '#FFFFFF',
};
traceability.getRange('A5:K5').format.rowHeight = 34;
traceability.getRange(`A6:K${traceRows.length + 5}`).format.rowHeight = 48;
traceability.freezePanes.freezeRows(5);

const fixtureHeaders = [
  'Fixture ID',
  '类型 / Kind',
  '名称 / Name',
  '合成配方 / Recipe',
  '执行环境 / Environment',
  '状态 / Status',
  '说明 / Notes',
];
const fixtureRows = manifest.fixtures.map((fixture) => [
  fixture.id,
  fixture.kind,
  fixture.name,
  fixture.recipe,
  fixture.execution,
  fixture.status,
  fixture.notes,
]);
fixtures.showGridLines = false;
fixtures.mergeCells('A1:G1');
fixtures.getRange('A1').values = [['M8 Acceptance Fixtures / 验收数据集清单']];
styleTitle(fixtures, 'A1:G1');
fixtures.getRange('A1:G1').format.rowHeight = 30;
fixtures.getRange('A5:G5').values = [fixtureHeaders];
styleHeader(fixtures, 'A5:G5');
fixtures.getRange(`A6:G${fixtureRows.length + 5}`).values = fixtureRows;
styleBody(fixtures, `A6:G${fixtureRows.length + 5}`);
fixtures.tables.add(`A5:G${fixtureRows.length + 5}`, true, 'FixturesTable');
fixtures.getRange('A:A').format.columnWidth = 13;
fixtures.getRange('B:B').format.columnWidth = 20;
fixtures.getRange('C:C').format.columnWidth = 24;
fixtures.getRange('D:D').format.columnWidth = 36;
fixtures.getRange('E:F').format.columnWidth = 22;
fixtures.getRange('G:G').format.columnWidth = 42;
fixtures.getRange(`A1:G${fixtureRows.length + 5}`).format.font = {
  name: 'Noto Sans CJK SC',
  size: 10,
  color: '#17324D',
};
fixtures.getRange('A1:G1').format.font = {
  name: 'Noto Sans CJK SC',
  size: 16,
  bold: true,
  color: '#FFFFFF',
};
fixtures.getRange('A5:G5').format.rowHeight = 34;
fixtures.getRange(`A6:G${fixtureRows.length + 5}`).format.rowHeight = 30;
fixtures.freezePanes.freezeRows(5);

await fs.mkdir(verifyDir, { recursive: true });
const workbookSummary = await workbook.inspect({
  kind: 'sheet,table',
  maxChars: 6000,
  tableMaxRows: 4,
  tableMaxCols: 6,
});
await fs.writeFile(path.join(verifyDir, 'traceability-inspect.ndjson'), workbookSummary.ndjson);
const formulaErrors = await workbook.inspect({
  kind: 'match',
  searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A',
  options: { useRegex: true, maxResults: 100 },
  summary: 'traceability formula error scan',
});
if (formulaErrors.ndjson.trim() && !formulaErrors.ndjson.includes('matched 0 entries')) {
  throw new Error(`formula error scan failed: ${formulaErrors.ndjson}`);
}
for (const sheetName of ['Summary', 'Traceability', 'Fixtures']) {
  const preview = await workbook.render({ sheetName, autoCrop: 'all', scale: 1, format: 'png' });
  await fs.writeFile(
    path.join(verifyDir, `${sheetName.toLowerCase()}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`wrote ${outputPath}`);
