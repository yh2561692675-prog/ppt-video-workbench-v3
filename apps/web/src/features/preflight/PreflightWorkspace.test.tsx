import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

import { PreflightWorkspace } from './PreflightWorkspace';

const report = {
  id: 'report-1',
  preflight_run_id: 'run-1',
  project_id: 'project-1',
  checked_at: '2026-08-04T00:00:00Z',
  scope: ['materials', 'content'],
  project_fingerprint: 'd'.repeat(64),
  input_fingerprint: 'a'.repeat(64),
  check_fingerprints: {},
  allowed: false,
  snapshot_path: '09_日志/预检/report.json',
  reused_checks: [],
  executed_checks: ['materials', 'content'],
  fresh: true,
  cache_status: 'fresh' as const,
  is_stale: false,
  issues: [
    {
      issue_id: 'issue-1',
      check: 'materials',
      code: 'page_preview_missing',
      level: 'blocking' as const,
      message: '第1页预览图不存在',
      action: '重新生成页面预览',
      location: { page_id: 'page-1', node: 'materials', relative_path: null, job_id: null },
      fingerprint: 'b'.repeat(64),
      blocking: true,
      confirmed: false,
      confirmed_by: null,
      confirmed_at: null,
    },
    {
      issue_id: 'issue-2',
      check: 'content',
      code: 'ocr_needs_confirmation',
      level: 'confirmation' as const,
      message: '第1页 OCR 需要人工确认',
      action: '定位并人工校对低置信度文字',
      location: { page_id: 'page-1', node: 'ocr', relative_path: null, job_id: null },
      fingerprint: 'c'.repeat(64),
      blocking: false,
      confirmed: false,
      confirmed_by: null,
      confirmed_at: null,
    },
  ],
};

it('groups issues and only offers confirmation for non-blocking issues', () => {
  const onConfirm = vi.fn();
  render(
    <PreflightWorkspace
      projectId="project-1"
      report={report}
      onRun={vi.fn()}
      onRender={vi.fn()}
      onConfirm={onConfirm}
      onExport={vi.fn()}
    />,
  );

  expect(screen.getByText('阻断错误')).toBeInTheDocument();
  expect(screen.getByText('待确认问题')).toBeInTheDocument();
  expect(screen.getByText('第1页预览图不存在')).toBeInTheDocument();
  expect(screen.getByText('第1页 OCR 需要人工确认')).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: '确认并继续' })).toHaveLength(1);
  fireEvent.change(screen.getByPlaceholderText('填写确认说明'), {
    target: { value: '已完成人工复核' },
  });
  fireEvent.click(screen.getByRole('button', { name: '确认并继续' }));
  expect(onConfirm).toHaveBeenCalledWith('issue-2', '规划师', '已完成人工复核');
});

it('disables render while the report is blocked and exports the report', () => {
  const onExport = vi.fn();
  render(
    <PreflightWorkspace
      projectId="project-1"
      report={report}
      onRun={vi.fn()}
      onRender={vi.fn()}
      onConfirm={vi.fn()}
      onExport={onExport}
    />,
  );

  expect(screen.getByRole('button', { name: '开始渲染与导出' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '导出预检报告' }));
  expect(onExport).toHaveBeenCalledTimes(1);
});
