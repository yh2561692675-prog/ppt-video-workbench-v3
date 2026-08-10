import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import {
  api,
  DiagnosticCheck,
  DiagnosticPackage,
  DiagnosticReport,
  DiagnosticStatus,
} from '../../api/client';

const GROUPS: Array<{
  status: DiagnosticStatus;
  title: string;
  description: string;
}> = [
  { status: 'red', title: '需要处理', description: '会影响启动、配音、渲染或数据可靠性' },
  { status: 'yellow', title: '建议检查', description: '当前可继续使用，但部分能力未确认或未配置' },
  { status: 'green', title: '正常', description: '检查通过，无需处理' },
];

export function DiagnosticCenter() {
  const [report, setReport] = useState<DiagnosticReport | null>(null);
  const [diagnosticPackage, setDiagnosticPackage] = useState<DiagnosticPackage | null>(null);
  const run = useMutation({
    mutationFn: api.runDiagnostics,
    onSuccess: (value) => {
      setReport(value);
      setDiagnosticPackage(null);
    },
  });
  const createPackage = useMutation({
    mutationFn: api.createDiagnosticPackage,
    onSuccess: setDiagnosticPackage,
  });

  return (
    <main className="page diagnostic-page">
      <header className="topbar">
        <div>
          <Link className="eyebrow" to="/">
            返回项目中心
          </Link>
          <h1>一键健康检查与日志诊断</h1>
        </div>
        <div className="diagnostic-actions">
          {report ? (
            <span className={`diagnostic-overall diagnostic-${report.overall_status}`}>
              {overallLabel(report.overall_status)}
            </span>
          ) : null}
          <button className="primary" disabled={run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? '正在检查…' : '开始一键检查'}
          </button>
        </div>
      </header>

      <section className="panel diagnostic-intro">
        <div>
          <h2>一次检查 13 类运行条件</h2>
          <p className="muted">
            覆盖安装、运行库、FFmpeg、磁盘、权限、端口、数据库、配置、HeyGen、临时目录和视频编码。
          </p>
        </div>
        <p className="diagnostic-safe-note">
          诊断只读运行，不自动删除或修改项目；导出的诊断包默认脱敏。
        </p>
      </section>

      {run.isError ? (
        <section className="panel diagnostic-error" role="alert">
          <h2>诊断请求未完成</h2>
          <p>{errorText(run.error)}</p>
          <p className="muted">原有视频制作流程仍可继续使用。</p>
        </section>
      ) : null}

      {report ? (
        <>
          <section className="diagnostic-summary" aria-label="诊断汇总">
            {GROUPS.map((group) => (
              <article
                className={`diagnostic-summary-card diagnostic-${group.status}`}
                key={group.status}
              >
                <strong>{report.summary[group.status]}</strong>
                <span>{group.title}</span>
              </article>
            ))}
          </section>

          {GROUPS.map((group) => {
            const checks = report.checks.filter((check) => check.status === group.status);
            if (!checks.length) return null;
            return (
              <section className="panel diagnostic-group" key={group.status}>
                <div className="diagnostic-group-heading">
                  <div>
                    <h2>{group.title}</h2>
                    <p className="muted">{group.description}</p>
                  </div>
                  <span className={`diagnostic-count diagnostic-${group.status}`}>
                    {checks.length} 项
                  </span>
                </div>
                <div className="diagnostic-checks">
                  {checks.map((check) => (
                    <DiagnosticCard check={check} key={check.check_id} />
                  ))}
                </div>
              </section>
            );
          })}

          <section className="panel diagnostic-package-panel">
            <div>
              <h2>脱敏诊断包</h2>
              <p className="muted">包含结构化报告、修复建议、文件哈希和限长日志摘录。</p>
            </div>
            <button
              className="secondary"
              disabled={createPackage.isPending}
              onClick={() => createPackage.mutate()}
            >
              {createPackage.isPending ? '正在生成…' : '生成脱敏诊断包'}
            </button>
            {diagnosticPackage ? (
              <p className="success" aria-live="polite">
                诊断包已生成：{diagnosticPackage.relative_path}
              </p>
            ) : null}
            {createPackage.isError ? (
              <p className="error" role="alert">
                {errorText(createPackage.error)}
              </p>
            ) : null}
          </section>
        </>
      ) : (
        <section className="panel diagnostic-empty">
          <h2>尚未运行检查</h2>
          <p className="muted">点击“开始一键检查”，通常数秒内可得到结果。</p>
        </section>
      )}
    </main>
  );
}

function DiagnosticCard({ check }: { check: DiagnosticCheck }) {
  return (
    <article className={`diagnostic-check diagnostic-${check.status}`}>
      <div className="diagnostic-check-title">
        <h3>{check.label}</h3>
        <code>{check.code}</code>
      </div>
      <p>{check.summary}</p>
      <dl>
        <div>
          <dt>影响</dt>
          <dd>{check.impact}</dd>
        </div>
        <div>
          <dt>处理建议</dt>
          <dd>{check.remediation}</dd>
        </div>
      </dl>
    </article>
  );
}

function overallLabel(status: DiagnosticStatus): string {
  if (status === 'red') return '需要处理';
  if (status === 'yellow') return '建议检查';
  return '全部正常';
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : '未知错误，请稍后重试';
}
