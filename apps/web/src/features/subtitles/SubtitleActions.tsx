import { useState } from 'react';

import { api } from '../../api/client';

export function SubtitleActions({
  projectId,
  allowed,
  onChanged,
}: {
  projectId: string;
  allowed: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  async function build() {
    setBusy(true);
    try {
      await api.buildSubtitles(projectId);
      onChanged();
      setMessage('字幕时间轴与 SRT 已生成');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '字幕生成失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="audio-pipeline-actions" aria-label="字幕生成">
      <button className="primary" disabled={!allowed || busy} onClick={() => void build()}>
        {busy ? '正在生成字幕…' : '生成字幕'}
      </button>
      {!allowed && <p className="muted">请先通过音频门禁后生成字幕。</p>}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
