import type { PresenterTimeline } from './api';

export function PresenterStylePanel({ timeline }: { timeline: PresenterTimeline | null }) {
  return (
    <section className="presenter-zone" aria-label="小窗样式">
      <h3>4. 小窗样式</h3>
      <p>
        {timeline
          ? `${timeline.segments.length} 个出镜片段；隐藏片段不影响原声。`
          : '生成时间线后可调整位置与大小。'}
      </p>
      {timeline?.segments.map((segment, index) => (
        <span className="status-pill" key={`${segment.start_ms}-${index}`}>
          {segment.layout} · {Math.round(segment.width_ratio * 100)}%
        </span>
      ))}
    </section>
  );
}
