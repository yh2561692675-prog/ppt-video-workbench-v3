import { useEffect, useState } from 'react';

import { api, AudioDifference } from '../../../api/client';

const labels = {
  accept_recording: '接受录音',
  change_narration: '改旁白',
  reimport: '重导入',
};

export function AudioDifferences({
  projectId,
  differences: initial,
  onChanged,
}: {
  projectId: string;
  differences: AudioDifference[];
  onChanged?: () => void;
}) {
  const [differences, setDifferences] = useState(initial);
  const [message, setMessage] = useState('');

  useEffect(() => {
    setDifferences(initial);
  }, [initial]);

  async function resolve(item: AudioDifference, resolution: keyof typeof labels) {
    try {
      const saved = await api.resolveAudioDifference(projectId, item.id, resolution);
      setDifferences((current) => current.map((value) => (value.id === saved.id ? saved : value)));
      setMessage(`已处理：${labels[resolution]}`);
      onChanged?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '差异处理失败');
    }
  }

  return (
    <section className="audio-differences">
      <h3>旁白差异</h3>
      {differences.map((item) => (
        <article className="difference-card" key={item.id}>
          <time>{formatTime(item.start_ms)}</time>
          <span>原文：{item.expected || '—'}</span>
          <span>录音：{item.actual || '—'}</span>
          <div className="status-row">
            {Object.entries(labels).map(([value, label]) => (
              <button
                className="secondary"
                key={value}
                disabled={item.status === 'resolved'}
                onClick={() => void resolve(item, value as keyof typeof labels)}
              >
                {label}
              </button>
            ))}
          </div>
        </article>
      ))}
      {message && <p role="status">{message}</p>}
    </section>
  );
}

function formatTime(milliseconds: number): string {
  const minutes = Math.floor(milliseconds / 60_000);
  const seconds = Math.floor((milliseconds % 60_000) / 1000);
  const millis = milliseconds % 1000;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`;
}
