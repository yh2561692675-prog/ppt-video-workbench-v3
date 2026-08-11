import { useState } from 'react';

import type { Project } from '../../api/client';
import { presenterApi, type PresenterSource } from './api';

export function SourcePanel({
  projectId,
  source,
  onChanged,
}: {
  projectId: string;
  source: PresenterSource | null;
  onChanged: (project: Project) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState('');
  async function upload() {
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      onChanged(await presenterApi.importSource(projectId, file));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '真人视频导入失败');
    } finally {
      setBusy(false);
    }
  }
  async function analyze() {
    setAnalyzing(true);
    setError('');
    try {
      onChanged((await presenterApi.analyze(projectId)).project);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Presenter analysis failed');
    } finally {
      setAnalyzing(false);
    }
  }
  return (
    <section className="presenter-zone" aria-label="真人源视频">
      <h3>1. 源视频</h3>
      {source ? (
        <p className="success">
          已导入 · {Math.round(source.duration_ms / 1000)} 秒 · {source.sha256.slice(0, 12)}
        </p>
      ) : (
        <p className="error">尚未导入可用的真人视频</p>
      )}
      <input
        aria-label="选择真人讲解视频"
        type="file"
        accept="video/mp4,video/quicktime"
        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
      />
      <button className="secondary" disabled={!file || busy} onClick={() => void upload()}>
        {busy ? '导入中…' : '导入并预检'}
      </button>
      <button className="primary" disabled={!source || analyzing} onClick={() => void analyze()}>
        {analyzing ? '识别与匹配中…' : '识别并生成时间线'}
      </button>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
