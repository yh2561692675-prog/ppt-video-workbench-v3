import { useState } from 'react';

import type { Project } from '../../api/client';
import { presenterApi } from './api';

export function PresenterModeEntry({
  projectId,
  onChanged,
}: {
  projectId: string;
  onChanged: (project: Project) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function enablePresenterMode() {
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      onChanged(await presenterApi.importSource(projectId, file));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '真人讲解视频导入失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="presenter-mode-entry" aria-label="真人讲解模式入口">
      <div>
        <span className="eyebrow">OPTIONAL · INTERNAL RC</span>
        <h3>改用真人讲解视频</h3>
        <p className="muted">
          默认继续使用 AI 配音。选择 MP4 或 MOV 后才会启用真人原声时间轴，现有 PPT 页面不会被改写。
        </p>
      </div>
      <input
        aria-label="选择用于启用真人模式的视频"
        type="file"
        accept="video/mp4,video/quicktime"
        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
      />
      <button
        className="secondary"
        disabled={!file || busy}
        onClick={() => void enablePresenterMode()}
      >
        {busy ? '正在导入并预检…' : '启用真人讲解并导入'}
      </button>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
