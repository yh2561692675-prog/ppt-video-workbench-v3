import { useState } from 'react';

import type { PreflightIssue, PreflightReport } from '../../api/client';

interface PreflightWorkspaceProps {
  projectId: string;
  report: PreflightReport | null;
  onRun: () => void;
  onConfirm: (issueId: string, actor: string, note: string) => void;
  onExport: () => void;
}

const levelLabels: Record<PreflightIssue['level'], string> = {
  blocking: '阻断错误',
  confirmation: '待确认问题',
  required_warning: '必须确认的警告',
  info: '信息提示',
};

export function PreflightWorkspace({
  projectId,
  report,
  onRun,
  onConfirm,
  onExport,
}: PreflightWorkspaceProps) {
  const [actor, setActor] = useState('规划师');
  const [notes, setNotes] = useState<Record<string, string>>({});

  const groups = report
    ? (Object.entries(levelLabels).map(([level, label]) => ({
        level: level as PreflightIssue['level'],
        label,
        issues: report.issues.filter((issue) => issue.level === level),
      })) as Array<{ level: PreflightIssue['level']; label: string; issues: PreflightIssue[] }>)
    : [];

  function confirm(issueId: string) {
    const note = notes[issueId]?.trim();
    if (!note) return;
    onConfirm(issueId, actor.trim() || '规划师', note);
  }

  return (
    <section className="preflight-workspace" aria-label="结构化预检与确认">
      <div className="preflight-heading">
        <div>
          <h3>结构化预检与确认</h3>
          <p className="muted">项目 {projectId} 的每个问题都包含定位和可执行修复动作。</p>
        </div>
        <div className="preview-actions">
          <button className="secondary" onClick={onRun}>
            重新运行预检
          </button>
          <button className="secondary" onClick={onExport} disabled={!report}>
            导出预检报告
          </button>
          <button className="primary" disabled={!report?.allowed}>
            开始渲染与导出
          </button>
        </div>
      </div>

      {!report ? (
        <p className="muted">尚未运行预检。</p>
      ) : (
        <>
          <div className={report.allowed ? 'preflight-result success' : 'preflight-result error'}>
            {report.allowed ? '预检已通过，可以进入渲染。' : '预检未通过，请先处理下列问题。'}
          </div>
          <p className="muted">最后检查：{new Date(report.checked_at).toLocaleString()}</p>
          <label className="preflight-actor">
            确认人
            <input value={actor} onChange={(event) => setActor(event.target.value)} />
          </label>
          <div className="preflight-groups">
            {groups.map(
              ({ level, label, issues }) =>
                issues.length > 0 && (
                  <section key={level} className={`preflight-group preflight-${level}`}>
                    <h4>{label}</h4>
                    <ul>
                      {issues.map((issue) => (
                        <li key={issue.issue_id} className="preflight-issue">
                          <div>
                            <strong>{issue.code}</strong>
                            <span>{issue.message}</span>
                            <small>
                              {issue.location.page_id ? `页面 ${issue.location.page_id} · ` : ''}
                              {issue.location.node ?? '项目级'}
                              {issue.location.relative_path
                                ? ` · ${issue.location.relative_path}`
                                : ''}
                            </small>
                            <small>修复：{issue.action}</small>
                          </div>
                          {(level === 'confirmation' || level === 'required_warning') &&
                            !issue.confirmed && (
                              <div className="preflight-confirm">
                                <input
                                  placeholder="填写确认说明"
                                  value={notes[issue.issue_id] ?? ''}
                                  onChange={(event) =>
                                    setNotes((current) => ({
                                      ...current,
                                      [issue.issue_id]: event.target.value,
                                    }))
                                  }
                                />
                                <button
                                  className="secondary"
                                  onClick={() => confirm(issue.issue_id)}
                                >
                                  确认并继续
                                </button>
                              </div>
                            )}
                          {issue.confirmed && (
                            <span className="success">已确认：{issue.confirmed_by}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </section>
                ),
            )}
          </div>
        </>
      )}
    </section>
  );
}
