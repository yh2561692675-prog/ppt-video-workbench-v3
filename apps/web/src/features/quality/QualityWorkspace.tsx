import { useMemo } from 'react';

import type { QualityReport } from '../../api/client';

export type QualitySeverity = 'P0' | 'P1' | 'P2' | 'P3';

export type QualityIssueView = QualityReport['issues'][number];
export type QualityReportView = QualityReport;

interface QualityWorkspaceProps {
  projectId: string;
  report: QualityReportView | null;
  onRun: () => void;
  onRetry: (issueId: string) => void;
  onConfirm?: (issueId: string) => void;
}

const resultLabels: Record<QualityReportView['result'], string> = {
  pass: '质量检测通过',
  pass_with_warnings: '通过，但有提示',
  blocked: '质量检测阻断发布',
};

export function QualityWorkspace({
  projectId,
  report,
  onRun,
  onRetry,
  onConfirm,
}: QualityWorkspaceProps) {
  const groupedIssues = useMemo(() => {
    const groups = new Map<QualitySeverity, QualityIssueView[]>();
    for (const issue of report?.issues ?? []) {
      groups.set(issue.severity, [...(groups.get(issue.severity) ?? []), issue]);
    }
    return (['P0', 'P1', 'P2', 'P3'] as QualitySeverity[]).flatMap((severity) => {
      const issues = groups.get(severity) ?? [];
      return issues.length ? [{ severity, issues }] : [];
    });
  }, [report]);

  return (
    <section className="quality-workspace" aria-label="成片质量检测">
      <div className="quality-heading">
        <div>
          <h3>成片质量检测</h3>
          <p className="muted">项目 {projectId} 的成片、时间线、字幕和音视频完整性检查。</p>
        </div>
        <button className="primary" onClick={onRun}>
          运行质量检测
        </button>
      </div>

      {!report ? (
        <p className="muted">尚未生成质量报告。</p>
      ) : (
        <>
          <div className={`quality-result quality-${report.result}`} role="status">
            {resultLabels[report.result]}
          </div>
          <div className="quality-summary">
            <span>问题 {report.issues.length} 项</span>
            <span>抽检帧 {report.sampled_frames.length} 个</span>
            <span>分析器 {Object.values(report.analyzer_versions).join(', ') || '—'}</span>
          </div>
          <div className="quality-groups">
            {groupedIssues.map(({ severity, issues }) => (
              <section key={severity} className={`quality-group quality-${severity.toLowerCase()}`}>
                <h4>
                  {severity} · {issues.length} 项
                </h4>
                <ul>
                  {issues.map((issue) => (
                    <li key={issue.issue_id} className="quality-issue">
                      <div>
                        <strong>{issue.code}</strong>
                        <span>{issue.message}</span>
                        <small>{issue.action}</small>
                        {issue.start_ms != null && issue.end_ms != null && (
                          <small>
                            {issue.start_ms}ms – {issue.end_ms}ms
                          </small>
                        )}
                      </div>
                      <button
                        className="secondary"
                        onClick={() =>
                          severity === 'P0' || severity === 'P1'
                            ? onRetry(issue.issue_id)
                            : (onConfirm ?? onRetry)(issue.issue_id)
                        }
                      >
                        {severity === 'P0' || severity === 'P1' ? '重新处理' : '标记复核'}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
