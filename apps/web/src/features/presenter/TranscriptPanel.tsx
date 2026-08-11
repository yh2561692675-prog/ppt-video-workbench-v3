import type { PresenterTimeline } from './api';

export function TranscriptPanel({ timeline }: { timeline: PresenterTimeline | null }) {
  const sentenceCount =
    timeline?.anchors.reduce((sum, item) => sum + item.sentence_ids.length, 0) ?? 0;
  return (
    <section className="presenter-zone" aria-label="识别文本">
      <h3>2. 识别文本</h3>
      <p>{timeline ? `已进入时间线的句子：${sentenceCount}` : '等待逐字识别与断句结果'}</p>
      {timeline && timeline.unassigned_ranges.length > 0 && (
        <p className="warning">未分配区间：{timeline.unassigned_ranges.length}</p>
      )}
    </section>
  );
}
