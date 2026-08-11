import type { Project } from '../../api/client';
import { MatchReviewPanel } from './MatchReviewPanel';
import { PresenterStylePanel } from './PresenterStylePanel';
import { PresenterTimeline } from './PresenterTimeline';
import { SourcePanel } from './SourcePanel';
import { TranscriptPanel } from './TranscriptPanel';

export function PresenterWorkspace({
  project,
  onChanged,
}: {
  project: Project;
  onChanged: (project: Project) => void;
}) {
  if (project.presentation_mode !== 'human_presenter') return null;
  const timeline = project.presenter_timeline ?? null;
  return (
    <section className="presenter-workspace" aria-label="真人讲解工作台">
      <header>
        <div>
          <span className="eyebrow">HUMAN PRESENTER</span>
          <h2>真人讲解</h2>
        </div>
        <div className="presenter-version">
          r{timeline?.revision ?? '—'} · {timeline?.timeline_hash?.slice(0, 12) ?? '等待时间线'}
        </div>
      </header>
      <div className="presenter-zone-grid">
        <SourcePanel
          projectId={project.id}
          source={project.presenter_source ?? null}
          onChanged={onChanged}
        />
        <TranscriptPanel timeline={timeline} />
        <MatchReviewPanel timeline={timeline} />
        <PresenterStylePanel timeline={timeline} />
        <PresenterTimeline projectId={project.id} timeline={timeline} onChanged={onChanged} />
        <section className="presenter-zone" aria-label="预览与核对">
          <h3>6. 预览与核对</h3>
          <div className="presenter-preview-actions">
            <button className="secondary">预览本页</button>
            <button className="secondary">预览连续区间</button>
            <button className="primary">全片低清预览</button>
          </div>
          <small>
            所有预览使用 r{timeline?.revision ?? '—'} / {timeline?.timeline_hash ?? '尚无 hash'}
          </small>
        </section>
      </div>
    </section>
  );
}
