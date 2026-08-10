import { useEffect, useState } from 'react';

import { api } from '../../../api/client';

export function AudioPipelineActions({
  projectId,
  onChanged,
}: {
  projectId: string;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [devices, setDevices] = useState<Array<'cpu' | 'cuda'>>(['cpu']);
  const [device, setDevice] = useState<'cpu' | 'cuda'>('cpu');

  useEffect(() => {
    void api
      .transcriptionDevices(projectId)
      .then(setDevices)
      .catch(() => setDevices(['cpu']));
  }, [projectId]);

  async function run(operation: () => Promise<unknown>, success: string) {
    setBusy(true);
    try {
      await operation();
      onChanged();
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '音频处理失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="audio-pipeline-actions">
      <label>
        转写设备
        <select
          value={device}
          onChange={(event) => setDevice(event.target.value as 'cpu' | 'cuda')}
        >
          {devices.map((value) => (
            <option key={value} value={value}>
              {value === 'cpu' ? 'CPU（默认，int8）' : 'CUDA（float16）'}
            </option>
          ))}
        </select>
      </label>
      <button
        className="secondary"
        disabled={busy}
        onClick={() => void run(() => api.transcribeAudio(projectId, device), '本地转写已完成')}
      >
        转写本地录音
      </button>
      <button
        className="secondary"
        disabled={busy}
        onClick={() => void run(() => api.compareAudioDifferences(projectId), '差异检查已完成')}
      >
        检查旁白差异
      </button>
      <button
        className="secondary"
        disabled={busy}
        onClick={() => void run(() => api.buildAudioTimeline(projectId), '自动分页已完成')}
      >
        自动分页
      </button>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
