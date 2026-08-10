import { useEffect, useState } from 'react';

import { api, AudioTimelineRecord } from '../../../api/client';

export function AudioTimeline({
  projectId,
  initialTimeline,
  onChanged,
}: {
  projectId: string;
  initialTimeline: AudioTimelineRecord;
  onChanged?: () => void;
}) {
  const [timeline, setTimeline] = useState(initialTimeline);
  const [drafts, setDrafts] = useState(initialTimeline.boundaries.map((item) => item.time_ms));
  const [history, setHistory] = useState<number[][]>([]);
  const [message, setMessage] = useState('');

  useEffect(() => {
    setTimeline(initialTimeline);
    setDrafts(initialTimeline.boundaries.map((item) => item.time_ms));
    setHistory([]);
  }, [initialTimeline]);

  async function save(index: number) {
    const previous = timeline.boundaries.map((item) => item.time_ms);
    try {
      const saved = await api.updateAudioBoundary(
        projectId,
        timeline.boundaries[index].id,
        drafts[index],
        timeline.version,
      );
      setHistory((current) => [...current, previous]);
      setTimeline(saved);
      setDrafts(saved.boundaries.map((item) => item.time_ms));
      setMessage(`边界已保存（版本 ${saved.version}）`);
      onChanged?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '边界保存失败');
    }
  }

  function undo() {
    const previous = history.at(-1);
    if (!previous) return;
    setDrafts(previous);
    setHistory((current) => current.slice(0, -1));
    setMessage('已恢复上一次边界位置；再次松开分页线可保存。');
  }

  return (
    <section className="audio-timeline">
      <h3>录音分页时间轴</h3>
      <div className="waveform" aria-label="音频波形">
        {drafts.map((value, index) => (
          <label key={timeline.boundaries[index].id}>
            第 {index + 1} 条分页线
            <input
              aria-label={`第 ${index + 1} 条分页线`}
              type="range"
              min={timeline.min_page_ms}
              max={timeline.duration_ms - timeline.min_page_ms}
              value={value}
              onChange={(event) =>
                setDrafts((current) =>
                  current.map((item, position) =>
                    position === index ? Number(event.target.value) : item,
                  ),
                )
              }
              onMouseUp={() => void save(index)}
            />
          </label>
        ))}
      </div>
      <button className="secondary" disabled={!history.length} onClick={undo}>
        撤销边界调整
      </button>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
