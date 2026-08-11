import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { QualityWorkspace } from './QualityWorkspace';

describe('QualityWorkspace', () => {
  it('shows the report result and issue action', () => {
    const onRetry = vi.fn();
    render(
      <QualityWorkspace
        projectId="project-1"
        onRun={vi.fn()}
        onRetry={onRetry}
        report={{
          schema_version: '1.0',
          project_id: 'project-1',
          render_job_id: 'render-job-1',
          report_id: 'report-1',
          input_fingerprint: 'a'.repeat(64),
          result: 'blocked',
          metrics: [],
          sampled_frames: [0, 500],
          analyzer_versions: { 'quality-engine': 'v1' },
          issues: [
            {
              issue_id: 'issue-1',
              code: 'black_frame',
              severity: 'P1',
              scope: 'time_range',
              message: '检测到连续黑帧',
              action: '检查页面素材',
              start_ms: 1000,
              end_ms: 2000,
              evidence_refs: [],
              retry_policy: 'rerender_page',
            },
          ],
        }}
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent('阻断发布');
    expect(screen.getByText('black_frame')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新处理' })).toBeInTheDocument();
  });

  it('confirms non-blocking issues instead of retrying them', () => {
    const onRetry = vi.fn();
    const onConfirm = vi.fn();
    render(
      <QualityWorkspace
        projectId="project-1"
        onRun={vi.fn()}
        onRetry={onRetry}
        onConfirm={onConfirm}
        report={{
          schema_version: '1.0',
          project_id: 'project-1',
          render_job_id: 'render-job-2',
          report_id: 'report-2',
          input_fingerprint: 'b'.repeat(64),
          result: 'pass_with_warnings',
          metrics: [],
          sampled_frames: [],
          analyzer_versions: {},
          issues: [
            {
              issue_id: 'issue-2',
              code: 'subtitle_density_high',
              severity: 'P2',
              scope: 'page',
              evidence_refs: [],
              retry_policy: 'none',
              message: '字幕过长',
              action: '拆分字幕',
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '标记复核' }));
    expect(onConfirm).toHaveBeenCalledWith('issue-2');
    expect(onRetry).not.toHaveBeenCalled();
  });
});
