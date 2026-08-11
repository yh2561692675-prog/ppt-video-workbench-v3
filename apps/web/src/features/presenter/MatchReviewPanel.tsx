import type { PresenterTimeline } from './api';

export function MatchReviewPanel({ timeline }: { timeline: PresenterTimeline | null }) {
  return (
    <section className="presenter-zone" aria-label="匹配复核">
      <h3>3. 匹配复核</h3>
      {!timeline ? (
        <p>尚无页面匹配结果</p>
      ) : (
        <ul className="presenter-review-list">
          {timeline.anchors.map((anchor, index) => (
            <li key={anchor.page_id} className={`presenter-${anchor.status}`}>
              第 {index + 1} 页 · 置信度 {(anchor.confidence * 100).toFixed(0)}% · {anchor.status}
              {anchor.manual_lock && <strong> · 已锁定</strong>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
